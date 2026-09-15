"""Sync Face Attendance Log → HRMS Employee Checkin + Attendance."""

from __future__ import annotations

import frappe
from frappe.utils import flt, get_datetime, getdate, time_diff_in_hours


def sync_face_log_to_hrms(face_log) -> dict:
	"""Create/update Employee Checkin and HR Attendance for a verified face log.

	Returns dict with created/updated document names (best-effort; never blocks face log).
	"""
	result = {
		"employee_checkin": None,
		"attendance": None,
		"errors": [],
	}

	if getattr(face_log, "verification_status", None) and face_log.verification_status != "Verified":
		return result

	settings = frappe.get_cached_doc("Face Attendance Settings")
	sync_checkin = bool(getattr(settings, "sync_to_employee_checkin", 0))
	sync_attendance = bool(getattr(settings, "sync_to_hr_attendance", 1))

	# If Attendance sync is on, always create Checkin too when HRMS is present
	if sync_attendance:
		sync_checkin = True

	if not sync_checkin and not sync_attendance:
		return result

	if not frappe.db.exists("DocType", "Employee Checkin") and not frappe.db.exists(
		"DocType", "Attendance"
	):
		result["errors"].append("HRMS DocTypes not installed")
		return result

	try:
		if sync_checkin and frappe.db.exists("DocType", "Employee Checkin"):
			result["employee_checkin"] = _create_employee_checkin(
				face_log, skip_auto_attendance=sync_attendance
			)
	except Exception as exc:
		frappe.log_error(
			title="Karmavitta Employee Checkin Sync Failed",
			message=frappe.get_traceback(),
		)
		result["errors"].append(f"Employee Checkin: {exc}")

	try:
		if sync_attendance and frappe.db.exists("DocType", "Attendance"):
			result["attendance"] = _upsert_hr_attendance(face_log)
	except Exception as exc:
		frappe.log_error(
			title="Karmavitta HR Attendance Sync Failed",
			message=frappe.get_traceback(),
		)
		result["errors"].append(f"Attendance: {exc}")

	# Persist links on Face Attendance Log when fields exist
	updates = {}
	if result["employee_checkin"] and hasattr(face_log, "employee_checkin"):
		updates["employee_checkin"] = result["employee_checkin"]
	if result["attendance"] and hasattr(face_log, "attendance"):
		updates["attendance"] = result["attendance"]
	if updates and face_log.name:
		frappe.db.set_value("Face Attendance Log", face_log.name, updates, update_modified=False)

	return result


def _create_employee_checkin(face_log, skip_auto_attendance: bool = False) -> str | None:
	log_time = get_datetime(face_log.log_time)
	# Avoid exact-duplicate checkin at same second
	existing = frappe.db.exists(
		"Employee Checkin",
		{
			"employee": face_log.employee,
			"time": log_time,
			"log_type": face_log.log_type,
		},
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Employee Checkin",
			"employee": face_log.employee,
			"log_type": face_log.log_type,
			"time": log_time,
			"device_id": face_log.device_id,
			"latitude": face_log.latitude,
			"longitude": face_log.longitude,
			"skip_auto_attendance": 1 if skip_auto_attendance else 0,
		}
	)
	# Face geofence is enforced by Karmavitta; don't fail on HR shift-location radius
	doc.flags.ignore_permissions = True
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_day_attendance(employee: str, attendance_date):
	name = frappe.db.exists(
		"Attendance",
		{
			"employee": employee,
			"attendance_date": attendance_date,
			"docstatus": ["<", 2],
		},
	)
	if not name:
		return None
	return frappe.get_doc("Attendance", name)


def _upsert_hr_attendance(face_log) -> str | None:
	attendance_date = getdate(face_log.log_time)
	log_time = get_datetime(face_log.log_time)
	log_type = (face_log.log_type or "IN").upper()

	existing = _get_day_attendance(face_log.employee, attendance_date)

	# Do not override On Leave
	if existing and existing.status == "On Leave":
		return existing.name

	if existing and existing.docstatus == 1:
		return _update_submitted_attendance(existing, log_type, log_time)

	if existing and existing.docstatus == 0:
		return _update_draft_attendance(existing, log_type, log_time)

	# Create new Present attendance
	attendance = frappe.new_doc("Attendance")
	attendance.employee = face_log.employee
	attendance.attendance_date = attendance_date
	attendance.status = "Present"
	if log_type == "IN":
		attendance.in_time = log_time
	else:
		attendance.out_time = log_time
	attendance.insert(ignore_permissions=True)
	attendance.submit()
	return attendance.name


def _update_draft_attendance(attendance, log_type: str, log_time) -> str:
	if log_type == "IN":
		if not attendance.in_time or get_datetime(log_time) < get_datetime(attendance.in_time):
			attendance.in_time = log_time
	else:
		if not attendance.out_time or get_datetime(log_time) > get_datetime(attendance.out_time):
			attendance.out_time = log_time

	if attendance.status not in ("Present", "Work From Home", "Half Day"):
		attendance.status = "Present"

	_refresh_working_hours(attendance)
	attendance.save(ignore_permissions=True)
	if attendance.docstatus == 0:
		attendance.submit()
	return attendance.name


def _update_submitted_attendance(attendance, log_type: str, log_time) -> str:
	"""Update in/out on submitted Attendance without cancel (HRMS-compatible)."""
	values = {}

	if log_type == "IN":
		current_in = attendance.in_time
		if not current_in or get_datetime(log_time) < get_datetime(current_in):
			values["in_time"] = log_time
	else:
		current_out = attendance.out_time
		if not current_out or get_datetime(log_time) > get_datetime(current_out):
			values["out_time"] = log_time

	if attendance.status not in ("Present", "Work From Home", "Half Day", "On Leave"):
		values["status"] = "Present"

	# Compute working hours from merged times
	in_time = values.get("in_time") or attendance.in_time
	out_time = values.get("out_time") or attendance.out_time
	if in_time and out_time:
		values["working_hours"] = flt(time_diff_in_hours(in_time, out_time), 2)

	if values:
		frappe.db.set_value("Attendance", attendance.name, values, update_modified=True)

	return attendance.name


def _refresh_working_hours(attendance) -> None:
	if attendance.in_time and attendance.out_time:
		attendance.working_hours = flt(
			time_diff_in_hours(attendance.in_time, attendance.out_time), 2
		)
