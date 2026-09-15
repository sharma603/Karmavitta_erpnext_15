"""Post-install setup for Karmavitta Face Attendance."""

from __future__ import annotations

import frappe
from frappe.utils import cint


def after_install():
	_ensure_settings()
	_ensure_workspace()
	frappe.db.commit()


def after_migrate():
	_ensure_workspace()
	_ensure_face_biometric_workspace_link()
	_enable_hr_sync_defaults()
	frappe.db.commit()


def _enable_hr_sync_defaults():
	"""Turn on HRMS sync flags for existing sites after migrate."""
	if not frappe.db.exists("DocType", "Face Attendance Settings"):
		return
	try:
		doc = frappe.get_single("Face Attendance Settings")
		changed = False
		if hasattr(doc, "sync_to_employee_checkin") and not doc.sync_to_employee_checkin:
			doc.sync_to_employee_checkin = 1
			changed = True
		if hasattr(doc, "sync_to_hr_attendance") and not doc.sync_to_hr_attendance:
			doc.sync_to_hr_attendance = 1
			changed = True
		# Kiosk Face Attendance without login (API key only)
		if hasattr(doc, "kiosk_mode_enabled") and not doc.kiosk_mode_enabled:
			doc.kiosk_mode_enabled = 1
			changed = True
		# 100m is too tight for phone GPS — raise to a practical default
		if hasattr(doc, "geofence_radius_meters"):
			radius = cint(doc.geofence_radius_meters or 0)
			if radius and radius < 300:
				doc.geofence_radius_meters = 500
				changed = True
		if changed:
			doc.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Karmavitta HR sync defaults", message=frappe.get_traceback())


def _ensure_settings():
	if frappe.db.exists("Face Attendance Settings", "Face Attendance Settings"):
		return

	doc = frappe.new_doc("Face Attendance Settings")
	doc.enabled = 1
	if hasattr(doc, "kiosk_mode_enabled"):
		doc.kiosk_mode_enabled = 1
	companies = frappe.get_all("Company", pluck="name", limit=1)
	if companies:
		doc.default_company = companies[0]
	doc.insert(ignore_permissions=True)


def _ensure_workspace():
	title = "Face Attendance"
	if frappe.db.exists("Workspace", {"title": title}) or frappe.db.exists("Workspace", title):
		return

	try:
		ws = frappe.new_doc("Workspace")
		ws.label = title
		ws.title = title
		ws.public = 1
		ws.sequence_id = 2
		ws.content = "[]"
		for row in [
			{
				"type": "Link",
				"label": "Settings",
				"link_type": "DocType",
				"link_to": "Face Attendance Settings",
				"onboard": 1,
			},
			{
				"type": "Link",
				"label": "Face Biometric",
				"link_type": "DocType",
				"link_to": "Face Biometric",
				"onboard": 1,
			},
			{
				"type": "Link",
				"label": "Attendance Logs",
				"link_type": "DocType",
				"link_to": "Face Attendance Log",
				"onboard": 1,
			},
		]:
			ws.append("links", row)
		ws.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Karmavitta Workspace Setup", message=frappe.get_traceback())


def _ensure_face_biometric_workspace_link():
	"""Add Face Biometric shortcut to existing Face Attendance workspace."""
	if not frappe.db.exists("DocType", "Face Biometric"):
		return
	ws_name = frappe.db.get_value("Workspace", {"title": "Face Attendance"}, "name")
	if not ws_name:
		return
	try:
		ws = frappe.get_doc("Workspace", ws_name)
		existing = {(row.link_type, row.link_to) for row in (ws.links or [])}
		if ("DocType", "Face Biometric") in existing:
			return
		ws.append(
			"links",
			{
				"type": "Link",
				"label": "Face Biometric",
				"link_type": "DocType",
				"link_to": "Face Biometric",
				"onboard": 1,
			},
		)
		ws.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Face Biometric Workspace Link", message=frappe.get_traceback())
