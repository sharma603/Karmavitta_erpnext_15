"""Mobile app APIs for Karmavitta Face Attendance."""

from __future__ import annotations

import json

import frappe
from frappe.utils import cint, flt, getdate, now_datetime

from karmavitta.face_attendance.utils import (
	can_manage_employee_face,
	get_active_face_profile,
	get_employee_for_user,
	get_settings,
	mobile_config_dict,
	parse_face_encoding,
	resolve_log_type,
	validate_checkout_gap,
	validate_geofence,
	validate_mobile_api_key,
)


def _ok(**kwargs):
	return {"success": True, **kwargs}


def _fail(message, **kwargs):
	return {"success": False, "message": message, **kwargs}


@frappe.whitelist(allow_guest=True)
def get_config(api_key: str | None = None):
	"""Public config for mobile app bootstrap (requires Mobile API Key)."""
	try:
		validate_mobile_api_key(api_key)
		settings = get_settings()
		return _ok(config=mobile_config_dict(settings), site=frappe.utils.get_url())
	except Exception as exc:
		return _fail(str(exc))


@frappe.whitelist()
def get_my_profile():
	employee = get_employee_for_user()
	if not employee:
		return _fail("No active employee linked to this user")

	# Prefer Face Biometric (current), fall back to legacy Employee Face Profile
	profile = frappe.db.get_value(
		"Face Biometric",
		{"employee": employee, "enabled": 1, "registration_status": "Active"},
		["name", "registration_status", "registered_on", "model_name"],
		as_dict=True,
	)
	if profile:
		return _ok(
			employee=employee,
			registered=True,
			profile={
				"name": profile.name,
				"status": profile.registration_status,
				"registered_on": str(profile.registered_on) if profile.registered_on else None,
				"model_name": profile.model_name,
				"source": "Face Biometric",
			},
		)

	legacy = frappe.db.get_value(
		"Employee Face Profile",
		{"employee": employee},
		["name", "status", "profile_image", "registered_on"],
		as_dict=True,
	)
	registered = bool(legacy and legacy.status == "Active")
	return _ok(
		employee=employee,
		registered=registered,
		profile={
			**(legacy or {}),
			"source": "Employee Face Profile" if legacy else None,
		},
	)


@frappe.whitelist()
def get_face_status(employee: str | None = None):
	"""Return face registration status for an employee (self or permitted user)."""
	session_employee = get_employee_for_user()
	target = employee or session_employee
	if not target:
		return _fail("Employee is required")

	if employee and employee != session_employee:
		if not can_manage_employee_face(employee):
			return _fail("Not permitted to view face profile for this employee")

	# Prefer Face Biometric
	bio = frappe.db.get_value(
		"Face Biometric",
		{"employee": target},
		[
			"name",
			"registration_status",
			"enabled",
			"registered_on",
			"registered_device_id",
			"model_name",
			"model_version",
			"embedding_dimension",
		],
		as_dict=True,
	)
	if bio:
		registered = bool(bio.enabled and bio.registration_status == "Active")
		return _ok(
			employee=target,
			registered=registered,
			profile={
				"name": bio.name,
				"status": bio.registration_status,
				"registered_on": str(bio.registered_on) if bio.registered_on else None,
				"registered_device": bio.registered_device_id,
				"model_name": bio.model_name,
				"model_version": bio.model_version,
				"embedding_dimension": bio.embedding_dimension,
				"source": "Face Biometric",
			},
			registration_status=bio.registration_status,
			model_name=bio.model_name,
		)

	legacy = frappe.db.get_value(
		"Employee Face Profile",
		{"employee": target},
		["name", "status", "profile_image", "registered_on", "registered_device"],
		as_dict=True,
	)
	registered = bool(legacy and legacy.status == "Active")
	return _ok(
		employee=target,
		registered=registered,
		profile=legacy or {},
		registration_status=(legacy.status if legacy else None),
	)


@frappe.whitelist()
def register_face(
	face_encoding,
	profile_image: str | None = None,
	device_id: str | None = None,
	device_name: str | None = None,
	employee: str | None = None,
	allow_update: int | str | bool | None = 0,
):
	"""Register or update employee face profile from mobile app.

	- Default: registers for the logged-in user's linked Employee
	- Admin/HR with write permission can pass `employee` to enroll another person
	- If face already registered, pass allow_update=1 to replace template
	- Blocks registering a face that already belongs to another employee
	"""
	session_employee = get_employee_for_user()
	target = employee or session_employee
	if not target:
		return _fail(
			"No employee found. Link Employee.user_id to this login, or pass employee id."
		)

	# Admin/HR may enroll any employee; others only themselves
	if not can_manage_employee_face(target):
		return _fail("Not permitted to register face for this employee")

	if not frappe.db.exists("Employee", target):
		return _fail(f"Employee {target} not found")

	if isinstance(face_encoding, str):
		face_encoding = json.loads(face_encoding)

	encoding = parse_face_encoding(face_encoding)
	if not encoding:
		return _fail("face_encoding is required")

	# Legacy pose/bounds encodings cannot enforce one-face-one-employee.
	# Require FaceNet biometric API for registration.
	from karmavitta.face_attendance.utils import is_biometric_face_encoding

	if not is_biometric_face_encoding(encoding):
		return _fail(
			"Real FaceNet biometric required. Use Face Registration in the mobile app "
			"(karmavitta.api.biometric.register_face).",
			code="BIOMETRIC_REQUIRED",
		)

	# Delegate to authoritative biometric register (duplicate check vs ALL employees)
	from karmavitta.face_attendance.biometric import register_face_biometric

	return register_face_biometric(
		employee=target,
		biometric_template=encoding,
		embedding_dimension=len(encoding) if isinstance(encoding, list) else None,
		device_id=device_id,
		allow_update=str(allow_update).lower() in ("1", "true", "yes"),
	)


@frappe.whitelist(allow_guest=True)
def list_active_face_profiles(api_key: str | None = None):
	"""Return active face encodings for on-device matching (kiosk / admin attendance).

	Prefers Face Biometric (real embeddings). Falls back to legacy profiles.
	Guest access requires a valid Mobile API Key.
	"""
	try:
		validate_mobile_api_key(api_key)
		from karmavitta.face_attendance.biometric import list_active_biometric_templates_for_match

		biometric_profiles = list_active_biometric_templates_for_match()
		if biometric_profiles:
			return _ok(profiles=biometric_profiles, count=len(biometric_profiles))

		profiles = frappe.get_all(
			"Employee Face Profile",
			filters={"status": "Active"},
			fields=["name", "employee", "face_encoding", "profile_image", "registered_on"],
		)
		employee_ids = [p.employee for p in profiles if p.employee]
		employees = {}
		if employee_ids:
			employees = {
				row.name: row.employee_name
				for row in frappe.get_all(
					"Employee",
					filters={"name": ["in", employee_ids]},
					fields=["name", "employee_name"],
				)
			}
		payload = []
		for row in profiles:
			encoding = None
			if row.face_encoding:
				try:
					encoding = (
						json.loads(row.face_encoding)
						if isinstance(row.face_encoding, str)
						else row.face_encoding
					)
				except Exception:
					encoding = None
			payload.append(
				{
					"profile": row.name,
					"employee": row.employee,
					"employee_name": employees.get(row.employee) or row.employee,
					"face_encoding": encoding,
					"profile_image": row.profile_image,
					"registered_on": str(row.registered_on) if row.registered_on else None,
				}
			)
		return _ok(profiles=payload, count=len(payload))
	except Exception as exc:
		return _fail(str(exc))


@frappe.whitelist(allow_guest=True)
def checkin(
	api_key: str | None = None,
	employee: str | None = None,
	log_type: str | None = None,
	face_match_score: float | None = None,
	latitude: float | None = None,
	longitude: float | None = None,
	device_id: str | None = None,
	device_name: str | None = None,
	capture_image: str | None = None,
	remarks: str | None = None,
	location_name: str | None = None,
	biometric_template=None,
	embedding_dimension: int | None = None,
	model_name: str | None = None,
	model_version: str | None = None,
	face_image=None,
	company: str | None = None,
):
	"""Create attendance ONLY after authoritative face identification.

	Identity rules:
	1. arcface_service + face_image → ArcFace 1:N (authoritative).
	2. Else biometric_template → legacy FaceNet 1:N.
	3. Client-sent employee is never trusted for identity.
	4. Check In / Out uses that employee's own last log only.
	"""
	try:
		validate_mobile_api_key(api_key)
		settings = get_settings()

		# Guest kiosk devices must have Kiosk Mode enabled in Face Attendance Settings
		if frappe.session.user == "Guest" and not settings.kiosk_mode_enabled:
			return _fail(
				"Kiosk mode is disabled. Enable it in Face Attendance Settings, or login.",
				code="KIOSK_DISABLED",
			)

		# Client-claimed employee must never drive attendance identity
		_client_claimed_employee = (employee or "").strip() or None
		employee = None
		employee_name_verified = None

		from karmavitta.face_attendance.biometric import biometric_settings, verify_face_biometric
		from karmavitta.services.face_service_client import (
			FaceServiceError,
			decode_image_payload,
			face_service_enabled,
			verify_from_image,
		)

		if face_service_enabled(settings):
			if not face_image:
				return _fail(
					"face_image is required when ArcFace face service is enabled.",
					code="FACE_IMAGE_REQUIRED",
				)
			try:
				image_bytes, filename, content_type = decode_image_payload(face_image)
				verified = verify_from_image(
					image_bytes=image_bytes,
					filename=filename,
					content_type=content_type,
					company=company or settings.default_company,
					settings=settings,
				)
			except FaceServiceError as exc:
				return _fail(str(exc), code=exc.code)

			if not verified.get("success") or not verified.get("matched"):
				return _fail(
					verified.get("message") or "Face not recognized",
					code=verified.get("code") or "NO_MATCH",
					similarity=verified.get("score"),
				)
			employee = verified.get("employee")
			face_match_score = verified.get("score")
			employee_name_verified = frappe.db.get_value("Employee", employee, "employee_name")
		else:
			if biometric_template is None or biometric_template == "":
				return _fail(
					"Face embedding is required. Update the mobile app and try again.",
					code="EMBEDDING_REQUIRED",
				)

			# Force 1:N recognition — never pass client employee into verify
			verified = verify_face_biometric(
				biometric_template=biometric_template,
				employee=None,
				embedding_dimension=embedding_dimension,
				model_name=model_name,
				model_version=model_version,
				device_id=device_id,
			)
			if not verified.get("success"):
				return _fail(
					verified.get("message") or "Face not recognized",
					code=verified.get("code") or verified.get("error_code") or "FACE_NOT_RECOGNIZED",
					similarity=verified.get("score"),
				)

			employee = verified.get("employee")
			face_match_score = verified.get("score")
			employee_name_verified = verified.get("employee_name")

			cfg = biometric_settings(settings)
			min_score = max(flt(settings.min_face_match_score), flt(cfg["match_threshold"]), 0.68)
			if flt(face_match_score) < min_score:
				return _fail(
					f"Face match score too low ({face_match_score}). Minimum is {min_score}",
					code="FACE_SCORE_TOO_LOW",
					similarity=face_match_score,
				)

		if not employee:
			return _fail("Face not recognized", code="FACE_NOT_RECOGNIZED")

		if not frappe.db.exists("Employee", employee):
			return _fail(f"Employee {employee} not found")

		# Optional: log mismatch if phone claimed a different employee (debug only)
		if _client_claimed_employee and _client_claimed_employee != employee:
			frappe.logger("karmavitta").warning(
				f"Face checkin ignored client employee {_client_claimed_employee}; "
				f"server matched {employee}"
			)

		get_active_face_profile(employee)
		geo = validate_geofence(
			latitude,
			longitude,
			settings,
			preferred_location=location_name,
		)

		# Per-employee IN/OUT only (never global / previous scanner state)
		final_log_type = resolve_log_type(employee, log_type, settings)
		try:
			validate_checkout_gap(employee, final_log_type, settings)
		except Exception as gap_exc:
			return _fail(
				str(gap_exc),
				code="CHECK_OUT_TOO_SOON",
				minimumMinutes=cint(
					getattr(settings, "min_minutes_between_checkin_checkout", 10) or 0
				),
				employee=employee,
			)

		# Guest kiosk cannot upload photos to Desk — skip photo requirement without login
		photo_required = bool(settings.checkin_photo_required) and frappe.session.user != "Guest"
		if photo_required and not capture_image:
			return _fail("Capture image is required")

		employee_name = (
			employee_name_verified
			or frappe.db.get_value("Employee", employee, "employee_name")
			or employee
		)
		resolved_location = (
			geo.get("location_name")
			or location_name
			or remarks
		)

		doc = frappe.get_doc(
			{
				"doctype": "Face Attendance Log",
				"employee": employee,
				"log_type": final_log_type,
				"log_time": now_datetime(),
				"verification_status": "Verified",
				"face_match_score": flt(face_match_score),
				"device_id": device_id,
				"device_name": device_name,
				"latitude": latitude,
				"longitude": longitude,
				"location_name": resolved_location,
				"capture_image": capture_image,
				"remarks": remarks,
			}
		)
		doc.insert(ignore_permissions=True)
		doc.reload()

		return _ok(
			log=doc.name,
			log_type=doc.log_type,
			log_time=str(doc.log_time),
			location_name=doc.location_name,
			employee=employee,
			employee_name=employee_name,
			face_match_score=flt(face_match_score),
			similarity=flt(face_match_score),
			employee_checkin=getattr(doc, "employee_checkin", None),
			attendance=getattr(doc, "attendance", None),
		)
	except Exception as exc:
		frappe.log_error(title="Karmavitta Check-in Failed", message=frappe.get_traceback())
		return _fail(str(exc))


@frappe.whitelist()
def get_today_logs(employee: str | None = None):
	employee = employee or get_employee_for_user()
	if not employee:
		return _fail("Employee is required")

	logs = frappe.get_all(
		"Face Attendance Log",
		filters={"employee": employee, "log_time": [">=", getdate(now_datetime())]},
		fields=[
			"name",
			"log_type",
			"log_time",
			"verification_status",
			"face_match_score",
			"location_name",
			"device_name",
		],
		order_by="log_time desc",
	)
	return _ok(logs=logs)


@frappe.whitelist()
def get_today_attendance_summary(company: str | None = None):
	"""Dashboard graph data: total / present / absent for today.

	Present = distinct employees with at least one IN log today.
	Requires login (admin dashboard use).
	"""
	try:
		settings = get_settings()
		company = company or settings.default_company
		filters = {"status": "Active"}
		if company:
			filters["company"] = company

		total = frappe.db.count("Employee", filters=filters)

		log_filters = {
			"log_type": "IN",
			"log_time": [">=", getdate(now_datetime())],
		}
		if company:
			log_filters["company"] = company
		present_employees = frappe.get_all(
			"Face Attendance Log",
			filters=log_filters,
			fields=["employee"],
		)
		present = len({row.employee for row in present_employees if row.employee})
		present = min(present, total)
		return _ok(total=total, present=present, absent=max(total - present, 0))
	except Exception as exc:
		return _fail(str(exc))


@frappe.whitelist(allow_guest=True)
def sync_offline_logs(logs, api_key: str | None = None):
	"""Bulk sync offline attendance logs from mobile."""
	try:
		validate_mobile_api_key(api_key)
		settings = get_settings()
		if frappe.session.user == "Guest" and not settings.kiosk_mode_enabled:
			return _fail("Kiosk mode is disabled", code="KIOSK_DISABLED")
		if not settings.allow_offline_sync:
			return _fail("Offline sync is disabled")

		if isinstance(logs, str):
			logs = json.loads(logs)

		created = []
		errors = []
		for row in logs or []:
			try:
				employee = row.get("employee") or get_employee_for_user()
				get_active_face_profile(employee)
				geo = validate_geofence(row.get("latitude"), row.get("longitude"), settings)
				doc = frappe.get_doc(
					{
						"doctype": "Face Attendance Log",
						"employee": employee,
						"log_type": row.get("log_type") or resolve_log_type(employee, None, settings),
						"log_time": row.get("log_time") or now_datetime(),
						"verification_status": row.get("verification_status") or "Verified",
						"face_match_score": flt(row.get("face_match_score")),
						"device_id": row.get("device_id"),
						"device_name": row.get("device_name"),
						"latitude": row.get("latitude"),
						"longitude": row.get("longitude"),
						"location_name": geo.get("location_name"),
						"capture_image": row.get("capture_image"),
						"remarks": row.get("remarks") or "Offline sync",
					}
				)
				doc.insert(ignore_permissions=True)
				created.append(doc.name)
			except Exception as exc:
				errors.append({"row": row, "error": str(exc)})

		return _ok(created=created, errors=errors)
	except Exception as exc:
		return _fail(str(exc))


@frappe.whitelist(allow_guest=True)
def list_employees_for_kiosk(company: str | None = None, api_key: str | None = None):
	"""Return active employees with face registration status for kiosk/mobile picker."""
	try:
		validate_mobile_api_key(api_key)
		settings = get_settings()
		if not settings.kiosk_mode_enabled and frappe.session.user == "Guest":
			return _fail("Kiosk mode is disabled")

		company = company or settings.default_company
		filters = {"status": "Active"}
		if company:
			filters["company"] = company

		employees = frappe.get_all(
			"Employee",
			filters=filters,
			fields=["name", "employee_name", "company", "image"],
			order_by="employee_name asc",
		)

		# Prefer Face Biometric; fall back to legacy Employee Face Profile
		biometric = {
			row.employee: row
			for row in frappe.get_all(
				"Face Biometric",
				filters={"enabled": 1, "registration_status": "Active"},
				fields=["employee", "name", "registered_on", "model_name"],
			)
		}
		legacy = {
			row.employee: row
			for row in frappe.get_all(
				"Employee Face Profile",
				filters={"status": "Active"},
				fields=["employee", "name", "profile_image", "registered_on"],
			)
		}

		for emp in employees:
			bio = biometric.get(emp.name)
			leg = legacy.get(emp.name)
			if bio:
				emp["face_profile"] = {
					"name": bio.name,
					"profile_image": None,
					"registered_on": str(bio.registered_on) if bio.registered_on else None,
					"model_name": bio.model_name,
					"source": "Face Biometric",
				}
				emp["face_registered"] = True
			elif leg:
				emp["face_profile"] = {
					"name": leg.name,
					"profile_image": leg.profile_image,
					"registered_on": str(leg.registered_on) if leg.registered_on else None,
					"source": "Employee Face Profile",
				}
				emp["face_registered"] = True
			else:
				emp["face_profile"] = None
				emp["face_registered"] = False

		return _ok(employees=employees)
	except Exception as exc:
		return _fail(str(exc))
