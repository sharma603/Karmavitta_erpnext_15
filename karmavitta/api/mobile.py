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
	"""Dashboard graph data: total / present / absent / late / on_leave today.

	Present = distinct employees with at least one IN log today.
	Late = first IN after shift start + 15 min grace (else 09:15).
	On Leave = HR Attendance count (0 when HRMS is absent).
	Requires login (admin dashboard use).
	"""
	try:
		settings = get_settings()
		company = company or settings.default_company
		today = getdate(now_datetime())
		filters = {"status": "Active"}
		if company:
			filters["company"] = company

		total = frappe.db.count("Employee", filters=filters)

		log_filters = {
			"log_type": "IN",
			"log_time": [">=", today],
		}
		if company:
			log_filters["company"] = company
		today_logs = frappe.get_all(
			"Face Attendance Log",
			filters=log_filters,
			fields=["employee", "log_time"],
			order_by="log_time asc",
		)
		first_in: dict[str, object] = {}
		for row in today_logs:
			if row.employee and row.employee not in first_in and row.log_time:
				first_in[row.employee] = row.log_time.time()
		shift_cache: dict[str, object] = {}
		late = sum(
			1
			for emp, first_time in first_in.items()
			if first_time > _late_cutoff_for(emp, shift_cache, today)
		)

		on_leave = 0
		try:
			if frappe.db.exists("DocType", "Attendance"):
				leave_filters = {
					"attendance_date": today,
					"status": "On Leave",
					"docstatus": ["!=", 2],
				}
				if company:
					leave_filters["company"] = company
				on_leave = frappe.db.count("Attendance", filters=leave_filters)
		except Exception:
			pass

		present = min(len(first_in), total)
		return _ok(
			total=total,
			present=present,
			absent=max(total - present, 0),
			late=late,
			on_leave=on_leave,
		)
	except Exception as exc:
		return _fail(str(exc))


def _late_cutoff_for(employee, cache, today):
	"""Latest allowed first-IN time. Shift start + 15 min grace, else 09:15."""
	from datetime import date, datetime, time, timedelta

	if employee in cache:
		return cache[employee]
	cutoff = time(9, 15)
	try:
		if frappe.db.exists("DocType", "Shift Type"):
			shift = frappe.db.get_value("Employee", employee, "default_shift")
			if shift:
				start = frappe.db.get_value("Shift Type", shift, "start_time")
				if start is not None:
					if isinstance(start, timedelta):
						secs = int(start.total_seconds())
					else:
						secs = start.hour * 3600 + start.minute * 60 + start.second
					cutoff = (
						datetime.combine(today, time(0, 0))
						+ timedelta(seconds=secs + 900)
					).time()
	except Exception:
		pass
	cache[employee] = cutoff
	return cutoff


@frappe.whitelist()
def get_my_attendance_dashboard():
	"""Dashboard design data: company week/month chart + personal stats + recent.

	Week: Mon–Sun daily present/absent/late (late = first IN after shift/grace).
	Month: W1–W4 average daily counts. Stats/recent: logged-in user's month.
	"""
	from collections import defaultdict
	from datetime import timedelta

	try:
		employee = get_employee_for_user()
		settings = get_settings()
		company = settings.default_company
		now = now_datetime()
		today = getdate(now)

		emp_filters = {"status": "Active"}
		if company:
			emp_filters["company"] = company
		total = frappe.db.count("Employee", filters=emp_filters)

		monday = today - timedelta(days=today.weekday())
		month_start = today.replace(day=1)
		query_start = min(monday, month_start)

		log_filters = {"log_type": "IN", "log_time": [">=", query_start]}
		if company:
			log_filters["company"] = company
		month_logs = frappe.get_all(
			"Face Attendance Log",
			filters=log_filters,
			fields=["employee", "log_time"],
			order_by="log_time asc",
		)

		day_first: dict[str, dict[str, object]] = defaultdict(dict)
		for row in month_logs:
			if not row.employee or not row.log_time:
				continue
			day_iso = getdate(row.log_time).isoformat()
			if row.employee not in day_first[day_iso]:
				day_first[day_iso][row.employee] = row.log_time.time()

		shift_cache: dict[str, object] = {}

		leave_by_day: dict[str, int] = defaultdict(int)
		try:
			if frappe.db.exists("DocType", "Attendance"):
				leave_filters = {
					"status": "On Leave",
					"attendance_date": [">=", query_start],
					"docstatus": ["!=", 2],
				}
				if company:
					leave_filters["company"] = company
				for row in frappe.get_all(
					"Attendance", filters=leave_filters, fields=["attendance_date"]
				):
					leave_by_day[getdate(row.attendance_date).isoformat()] += 1
		except Exception:
			pass

		def day_counts(day_iso, is_future):
			if is_future:
				return {"present": 0, "absent": 0, "late": 0, "leave": 0}
			firsts = day_first.get(day_iso, {})
			leave = leave_by_day.get(day_iso, 0)
			late = sum(
				1
				for emp, t in firsts.items()
				if t > _late_cutoff_for(emp, shift_cache, today)
			)
			present = len(firsts)
			# absent = remaining after present + leave; late is subset of present
			absent = max(total - present - leave, 0)
			return {
				"present": present,
				"absent": absent,
				"late": late,
				"leave": leave,
			}

		labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
		week = []
		for i in range(7):
			day = monday + timedelta(days=i)
			counts = day_counts(day.isoformat(), day > today)
			week.append({"label": labels[i], "date": day.isoformat(), **counts})

		next_month = (month_start + timedelta(days=32)).replace(day=1)
		last_day = (next_month - timedelta(days=1)).day
		month = []
		for label, start_no, end_no in [
			("W1", 1, 7),
			("W2", 8, 14),
			("W3", 15, 21),
			("W4", 22, last_day),
		]:
			present_sum = absent_sum = late_sum = leave_sum = days = 0
			for day_no in range(start_no, end_no + 1):
				day = month_start + timedelta(days=day_no - 1)
				if day > today:
					continue
				counts = day_counts(day.isoformat(), False)
				present_sum += counts["present"]
				absent_sum += counts["absent"]
				late_sum += counts["late"]
				leave_sum += counts["leave"]
				days += 1
			if days:
				month.append(
					{
						"label": label,
						"present": round(present_sum / days),
						"absent": round(absent_sum / days),
						"late": round(late_sum / days),
						"leave": round(leave_sum / days),
					}
				)
			else:
				month.append(
					{"label": label, "present": 0, "absent": 0, "late": 0, "leave": 0}
				)

		working = sum(
			1
			for day_no in range(1, today.day + 1)
			if (month_start + timedelta(days=day_no - 1)).weekday() != 6
		)
		my_days: dict[str, object] = {}
		for day_iso, firsts in day_first.items():
			if employee and employee in firsts:
				my_days[day_iso] = firsts[employee]
		my_late_days = (
			{
				day_iso
				for day_iso, first_in in my_days.items()
				if first_in > _late_cutoff_for(employee, shift_cache, today)
			}
			if employee
			else set()
		)
		leave = half = 0
		try:
			if employee and frappe.db.exists("DocType", "Attendance"):
				records = frappe.get_all(
					"Attendance",
					filters={
						"employee": employee,
						"attendance_date": [">=", month_start],
						"docstatus": ["!=", 2],
					},
					fields=["status", "late_entry", "attendance_date"],
				)
				leave = sum(1 for r in records if r.status == "On Leave")
				half = sum(1 for r in records if r.status == "Half Day")
				my_late_days |= {
					getdate(r.attendance_date).isoformat()
					for r in records
					if r.status == "Present" and cint(r.late_entry)
				}
		except Exception:
			pass
		my_present = len(set(my_days) - my_late_days)
		my_late = len(my_late_days)
		my_absent = max(working - my_present - my_late - leave - half, 0)

		recent = []
		if employee:
			my_logs = frappe.get_all(
				"Face Attendance Log",
				filters={"employee": employee},
				fields=["log_type", "log_time"],
				order_by="log_time desc",
				limit=200,
			)
			by_day: dict[str, list] = defaultdict(list)
			for row in my_logs:
				by_day[getdate(row.log_time).isoformat()].append(row)
			yesterday_iso = (today - timedelta(days=1)).isoformat()
			for day_iso in sorted(by_day, reverse=True)[:3]:
				rows = by_day[day_iso]
				ins = [r.log_time for r in rows if r.log_type == "IN"]
				outs = [r.log_time for r in rows if r.log_type == "OUT"]
				day = getdate(day_iso)
				if day_iso == today.isoformat():
					day_label = "Today"
				elif day_iso == yesterday_iso:
					day_label = "Yesterday"
				else:
					day_label = day.strftime("%A")
				in_label = min(ins).strftime("%I:%M %p").lstrip("0") if ins else "--"
				out_label = max(outs).strftime("%I:%M %p").lstrip("0") if outs else "--"
				recent.append(
					{
						"label": day_label,
						"time": f"{in_label} → {out_label}",
						"status": "Late" if day_iso in my_late_days else "Present",
					}
				)

		return _ok(
			week=week,
			month=month,
			stats={
				"working": working,
				"present": my_present,
				"absent": my_absent,
				"late": my_late,
				"leave": leave,
				"half": half,
			},
			recent=recent,
		)
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
