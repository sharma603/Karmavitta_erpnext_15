"""Helpers for face attendance mobile integration."""

from __future__ import annotations

import json
import math

import frappe
from frappe.utils import cint, flt, get_datetime, getdate, now_datetime, time_diff_in_seconds


def get_settings():
	return frappe.get_cached_doc("Face Attendance Settings")


def validate_mobile_api_key(api_key: str | None):
	settings = get_settings()
	if not settings.enabled:
		frappe.throw("Face Attendance is disabled", frappe.ValidationError)
	if not api_key or api_key != settings.mobile_api_key:
		frappe.throw("Invalid Mobile API Key", frappe.AuthenticationError)


def haversine_meters(lat1, lon1, lat2, lon2) -> float:
	r = 6371000
	phi1, phi2 = math.radians(lat1), math.radians(lat2)
	dphi = math.radians(lat2 - lat1)
	dlambda = math.radians(lon2 - lon1)
	a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
	return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _is_junk_location_name(name: str) -> bool:
	"""Skip accidental child rows like \"1\" that pollute geofence matching."""
	cleaned = (name or "").strip()
	if not cleaned:
		return True
	# Numeric-only short labels are almost never real site names
	if cleaned.isdigit() and len(cleaned) <= 2:
		return True
	return False


def get_attendance_locations(settings=None):
	"""Locations for mobile picker + geofence.

	Includes:
	1) ERPNext Assets → Location (leaf records, e.g. \"doha\")
	2) Face Attendance Settings → Allowed Locations (Geofence)
	"""
	settings = settings or get_settings()
	default_radius = cint(settings.geofence_radius_meters) or 500
	rows = []
	seen = set()

	# Assets > Location master
	if frappe.db.exists("DocType", "Location"):
		for loc in frappe.get_all(
			"Location",
			filters={"is_group": 0},
			fields=["name", "location_name", "latitude", "longitude"],
			order_by="location_name asc",
			limit_page_length=500,
		):
			name = (loc.location_name or loc.name or "").strip()
			if _is_junk_location_name(name):
				continue
			key = name.lower()
			if key in seen:
				continue
			seen.add(key)
			rows.append(
				{
					"location_name": name,
					"latitude": loc.latitude,
					"longitude": loc.longitude,
					"radius_meters": default_radius,
					"source": "Location",
				}
			)

	# Face Attendance Settings child table (extra geofences)
	for row in settings.allowed_locations or []:
		if not cint(row.enabled):
			continue
		name = (row.location_name or "").strip()
		if _is_junk_location_name(name):
			continue
		key = name.lower()
		if key in seen:
			continue
		seen.add(key)
		rows.append(
			{
				"location_name": name,
				"latitude": row.latitude,
				"longitude": row.longitude,
				"radius_meters": cint(row.radius_meters) or default_radius,
				"source": "Geofence",
			}
		)

	return rows


def validate_geofence(
	latitude,
	longitude,
	settings=None,
	preferred_location: str | None = None,
):
	"""Validate GPS against allowed locations.

	Phone GPS is often ±30–100m, so effective radius uses a practical floor.

	When the app sends preferred_location (selected site), only that fence is
	checked — other pins must not reject a valid selection. If the master pin
	is wrong but the employee selected a known site, soft-pass unless
	strict_geofence is enabled.
	"""
	settings = settings or get_settings()
	if not settings.require_gps:
		return {"ok": True, "location_name": preferred_location or None}

	if latitude is None or longitude is None:
		frappe.throw("GPS location is required for attendance")

	# GPS accuracy floor — 100m fences reject almost everyone indoors
	GPS_RADIUS_FLOOR_M = 300
	strict = cint(getattr(settings, "strict_geofence", 0) or 0)

	all_locations = [
		row
		for row in get_attendance_locations(settings)
		if row.get("latitude") is not None and row.get("longitude") is not None
	]
	if not all_locations:
		# No geofence points configured — allow attendance, keep selected name
		return {
			"ok": True,
			"location_name": preferred_location or "Open Location",
		}

	def effective_radius(row) -> float:
		configured = flt(row.get("radius_meters") or settings.geofence_radius_meters or 500)
		return max(configured, GPS_RADIUS_FLOOR_M)

	pref = (preferred_location or "").strip()
	pref_key = pref.lower() if pref else ""
	matched_preferred = []
	if pref_key:
		matched_preferred = [
			row
			for row in all_locations
			if (row.get("location_name") or "").strip().lower() == pref_key
		]

	# App sent a selected site that is not a geofence pin — trust the picker
	# (GPS still stored). Strict mode requires a matching pin.
	if pref and not matched_preferred:
		if strict:
			frappe.throw(
				(
					f"Selected location '{pref}' is not in Allowed Locations / Assets → Location. "
					f"Add it in Face Attendance Settings, or turn off Strict Geofence."
				),
				title="Unknown Location",
			)
		return {"ok": True, "location_name": pref, "soft_pass": True}

	# Selected site only — never let another pin (e.g. junk \"1\") reject check-in
	candidates = matched_preferred if matched_preferred else list(all_locations)

	best_row = None
	best_distance = None
	for row in candidates:
		radius = effective_radius(row)
		distance = haversine_meters(
			float(latitude),
			float(longitude),
			float(row["latitude"]),
			float(row["longitude"]),
		)
		if best_distance is None or distance < best_distance:
			best_distance = distance
			best_row = row
		if distance <= radius:
			return {
				"ok": True,
				"location_name": row["location_name"],
				"distance_m": round(distance, 2),
			}

	# Soft-pass: selected known site, but ERPNext map pin/radius is wrong.
	# GPS is still stored on the log for audit. Enable Strict Geofence to block.
	if pref and matched_preferred and not strict:
		return {
			"ok": True,
			"location_name": matched_preferred[0]["location_name"],
			"distance_m": round(best_distance, 2) if best_distance is not None else None,
			"soft_pass": True,
		}

	# Helpful error — include nearest fence + phone GPS so admins can fix pins
	nearest_name = (best_row or {}).get("location_name") or pref or "allowed location"
	nearest_radius = effective_radius(best_row) if best_row else GPS_RADIUS_FLOOR_M
	dist_txt = f"{round(best_distance)} m" if best_distance is not None else "unknown"
	phone_txt = f"{float(latitude):.6f}, {float(longitude):.6f}"
	frappe.throw(
		(
			f"You are outside allowed attendance locations. "
			f"Nearest: {nearest_name} ({dist_txt} away, allowed {int(nearest_radius)} m). "
			f"Phone GPS: {phone_txt}. "
			f"Update Assets → Location latitude/longitude for {nearest_name}, "
			f"or increase Default Geofence Radius in Face Attendance Settings."
		),
		title="Outside Geofence",
	)


def resolve_log_type(employee: str, requested: str | None = None, settings=None) -> str:
	settings = settings or get_settings()
	mode = (requested or settings.auto_log_type or "Auto").upper()

	if mode in ("IN", "OUT"):
		return mode
	if mode == "ASK USER":
		if requested in ("IN", "OUT"):
			return requested
		frappe.throw("Log type (IN/OUT) is required")

	# Auto mode: alternate based on last log today
	last = frappe.db.get_value(
		"Face Attendance Log",
		{
			"employee": employee,
			"log_time": [">=", getdate(now_datetime())],
		},
		"log_type",
		order_by="log_time desc",
	)
	return "OUT" if last == "IN" else "IN"


def validate_checkout_gap(employee: str, log_type: str, settings=None):
	"""Block OUT if not enough minutes have passed since last IN today."""
	settings = settings or get_settings()
	if (log_type or "").upper() != "OUT":
		return

	min_minutes = cint(getattr(settings, "min_minutes_between_checkin_checkout", 0) or 0)
	if min_minutes <= 0:
		return

	last_in = frappe.db.get_value(
		"Face Attendance Log",
		{
			"employee": employee,
			"log_type": "IN",
			"verification_status": "Verified",
			"log_time": [">=", getdate(now_datetime())],
		},
		["name", "log_time"],
		as_dict=True,
		order_by="log_time desc",
	)
	if not last_in or not last_in.log_time:
		return

	elapsed = time_diff_in_seconds(now_datetime(), get_datetime(last_in.log_time))
	required_seconds = min_minutes * 60
	if elapsed < required_seconds:
		remaining = max(1, int((required_seconds - elapsed + 59) // 60))
		frappe.throw(
			(
				f"Check-out can be marked only after {min_minutes} minutes from check-in. "
				f"Please wait about {remaining} more minute(s)."
			),
			frappe.ValidationError,
		)


def get_employee_for_user(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	if user == "Guest":
		return None
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"})


def get_active_face_profile(employee: str):
	"""Return active Face Biometric (ArcFace only)."""
	biometric = frappe.db.get_value(
		"Face Biometric",
		{"employee": employee, "enabled": 1, "registration_status": "Active"},
		"name",
	)
	if not biometric:
		frappe.throw("No active face profile found for this employee")
	return frappe.get_doc("Face Biometric", biometric)


def mobile_config_dict(settings=None):
	settings = settings or get_settings()
	return {
		"enabled": bool(settings.enabled),
		"min_face_match_score": flt(settings.min_face_match_score),
		"checkin_photo_required": bool(settings.checkin_photo_required),
		"allow_offline_sync": bool(settings.allow_offline_sync),
		"require_gps": bool(settings.require_gps),
		"geofence_radius_meters": settings.geofence_radius_meters,
		"auto_log_type": settings.auto_log_type,
		"min_minutes_between_checkin_checkout": cint(
			getattr(settings, "min_minutes_between_checkin_checkout", 10) or 0
		),
		"kiosk_mode_enabled": bool(settings.kiosk_mode_enabled),
		"sync_to_employee_checkin": bool(getattr(settings, "sync_to_employee_checkin", 0)),
		"sync_to_hr_attendance": bool(getattr(settings, "sync_to_hr_attendance", 1)),
		"default_company": settings.default_company,
		"allowed_locations": get_attendance_locations(settings),
		"recognition_backend": getattr(settings, "recognition_backend", None) or "arcface_service",
		"biometric": {
			"model_name": getattr(settings, "biometric_model_name", None) or "ArcFace",
			"model_version": getattr(settings, "biometric_model_version", None) or "insightface-buffalo_l-1.0",
			"embedding_dimension": cint(
				getattr(settings, "biometric_embedding_dimension", None) or 512
			),
			"similarity_metric": getattr(settings, "face_similarity_metric", None) or "cosine",
			"duplicate_threshold": max(
				flt(getattr(settings, "face_duplicate_threshold", None) or 0.45),
				0.40,
			),
			"match_threshold": max(
				flt(
					getattr(settings, "face_match_threshold", None)
					or getattr(settings, "min_face_match_score", None)
					or 0.40
				),
				flt(getattr(settings, "min_face_match_score", None) or 0),
				0.35,
			),
			"match_margin": 0.05,
			"same_person_update_threshold": flt(
				getattr(settings, "face_same_person_update_threshold", None) or 0.50
			),
			"liveness_provider": getattr(settings, "liveness_provider", None) or "none",
			"requires_face_image": True,
		},
	}


def parse_face_encoding(raw):
	if not raw:
		return None
	if isinstance(raw, (list, dict)):
		return raw
	return json.loads(raw)


def cosine_similarity(left, right) -> float:
	"""Cosine similarity for two numeric vectors."""
	if not left or not right:
		return 0.0
	length = min(len(left), len(right))
	if length <= 0:
		return 0.0

	dot = 0.0
	a = 0.0
	b = 0.0
	for i in range(length):
		x = flt(left[i])
		y = flt(right[i])
		dot += x * y
		a += x * x
		b += y * y

	if a <= 0 or b <= 0:
		return 0.0
	return dot / (math.sqrt(a) * math.sqrt(b))


def encoding_vector_length(face_encoding) -> int:
	encoding = parse_face_encoding(face_encoding)
	if isinstance(encoding, list):
		return len(encoding)
	if isinstance(encoding, dict):
		vector = encoding.get("vector") or encoding.get("embedding") or encoding.get("data")
		if isinstance(vector, list):
			return len(vector)
	return 0


def is_biometric_face_encoding(face_encoding) -> bool:
	"""True for real ArcFace embeddings. Pose/bounds vectors are ~10-D."""
	encoding = parse_face_encoding(face_encoding)
	if isinstance(encoding, dict):
		kind = str(encoding.get("type") or encoding.get("kind") or "").lower()
		if kind in ("pose", "pose_v1", "bounds"):
			return False
		if kind in ("embedding", "arcface", "biometric"):
			return True
	# Camera-kit pose encodings are short; real face models are typically 128+ dims
	return encoding_vector_length(encoding) >= 64


def find_duplicate_face_employee(face_encoding, exclude_employee: str | None = None, min_score: float = 0.92):
	"""Legacy helper — now checks Face Biometric only (ArcFace)."""
	encoding = parse_face_encoding(face_encoding)
	if not encoding:
		return None

	if not is_biometric_face_encoding(encoding):
		return None

	vector = encoding
	if isinstance(encoding, dict):
		vector = encoding.get("vector") or encoding.get("embedding") or encoding.get("data")
	if not isinstance(vector, list) or not vector:
		return None

	from karmavitta.face_attendance.biometric import parse_template, cosine_similarity as bio_cosine

	rows = frappe.get_all(
		"Face Biometric",
		filters={"enabled": 1, "registration_status": "Active"},
		fields=["name", "employee", "employee_name", "biometric_template"],
	)
	best = None
	best_score = 0.0
	for row in rows:
		if exclude_employee and row.employee == exclude_employee:
			continue
		other = parse_template(row.biometric_template)
		if not other:
			continue
		score = bio_cosine(vector, other)
		if score > best_score:
			best_score = score
			best = row

	if best and best_score >= min_score:
		return {
			"employee": best.employee,
			"employee_name": best.employee_name or best.employee,
			"profile": best.name,
			"score": round(best_score, 4),
		}
	return None


def can_manage_employee_face(target_employee: str | None = None) -> bool:
	"""Admin/HR can enroll any employee; others only their linked Employee."""
	user = frappe.session.user
	if not user or user == "Guest":
		return False
	if user == "Administrator":
		return True

	roles = set(frappe.get_roles(user))
	if roles.intersection(
		{
			"System Manager",
			"HR Manager",
			"HR User",
			"Employee Manager",
		}
	):
		return True

	if frappe.has_permission("Face Biometric", "write"):
		return True
	if frappe.has_permission("Employee", "write"):
		return True

	if not target_employee:
		return False
	return get_employee_for_user(user) == target_employee


def get_face_profile_for_employee(employee: str) -> str | None:
	"""Return existing Face Biometric name for employee, if any."""
	return frappe.db.get_value("Face Biometric", {"employee": employee}, "name")
