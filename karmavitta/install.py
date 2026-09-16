"""Post-install setup for Karmavitta Face Attendance."""

from __future__ import annotations

import frappe
from frappe.utils import cint


def after_install():
	_ensure_settings()
	_ensure_workspace()
	_ensure_procfile_entry()
	frappe.db.commit()


def after_migrate():
	_ensure_workspace()
	_ensure_face_biometric_workspace_link()
	_enable_hr_sync_defaults()
	_ensure_arcface_defaults()
	_ensure_procfile_entry()
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


def _ensure_procfile_entry():
	"""Add face_service to bench Procfile so `bench start` auto-runs it.

	Runs on install/migrate. Safe to re-run: skips if an entry already exists.
	The bench_start.sh script itself auto-creates .venv/.env on first run.
	"""
	try:
		import os

		from frappe.utils import get_bench_path

		bench_path = get_bench_path()
		procfile = os.path.join(bench_path, "Procfile")
		if not os.path.exists(procfile):
			return
		with open(procfile) as f:
			content = f.read()
		if "face_service:" in content or "face_service/scripts/bench_start.sh" in content:
			return
		with open(procfile, "a") as f:
			if content and not content.endswith("\n"):
				f.write("\n")
			f.write("\n# Karmavitta ArcFace face recognition (apps/karmavitta/face_service)\n")
			f.write("face_service: bash apps/karmavitta/face_service/scripts/bench_start.sh\n")
	except Exception:
		frappe.log_error(title="Karmavitta Procfile Setup", message=frappe.get_traceback())


def _ensure_arcface_defaults():
	"""Idempotent ArcFace-only enforcement for installs and migrates."""
	if not frappe.db.exists("DocType", "Face Attendance Settings"):
		return
	try:
		doc = frappe.get_single("Face Attendance Settings")
		changed = False

		if getattr(doc, "recognition_backend", None) != "arcface_service":
			doc.db_set("recognition_backend", "arcface_service", update_modified=False)
			changed = True
		if (getattr(doc, "biometric_model_name", None) or "").lower() != "arcface":
			doc.db_set("biometric_model_name", "ArcFace", update_modified=False)
			changed = True
		if getattr(doc, "biometric_model_version", None) != "insightface-buffalo_l-1.0":
			doc.db_set("biometric_model_version", "insightface-buffalo_l-1.0", update_modified=False)
			changed = True
		if cint(getattr(doc, "biometric_embedding_dimension", None)) != 512:
			doc.db_set("biometric_embedding_dimension", 512, update_modified=False)
			changed = True
		if getattr(doc, "face_similarity_metric", None) != "cosine":
			doc.db_set("face_similarity_metric", "cosine", update_modified=False)
			changed = True
		if not getattr(doc, "face_service_url", None):
			doc.db_set("face_service_url", "http://127.0.0.1:8090", update_modified=False)
			changed = True
		if cint(getattr(doc, "face_service_timeout_seconds", None) or 0) != 30:
			if not getattr(doc, "face_service_timeout_seconds", None):
				doc.db_set("face_service_timeout_seconds", 30, update_modified=False)
				changed = True

		# Thresholds — old FaceNet scale was >=0.65
		for field, val in [
			("face_duplicate_threshold", 0.45),
			("face_match_threshold", 0.40),
			("min_face_match_score", 0.40),
		]:
			cur = getattr(doc, field, None)
			try:
				cur_f = float(cur) if cur is not None else 0
			except Exception:
				cur_f = 0
			if cur_f == 0 or cur_f >= 0.65:
				doc.db_set(field, val, update_modified=False)
				changed = True

		if not getattr(doc, "face_same_person_update_threshold", None):
			doc.db_set("face_same_person_update_threshold", 0.50, update_modified=False)
			changed = True

		if changed:
			frappe.clear_cache()
	except Exception:
		frappe.log_error(title="Karmavitta ArcFace Defaults", message=frappe.get_traceback())


def _ensure_settings():
	if frappe.db.exists("Face Attendance Settings", "Face Attendance Settings"):
		_ensure_arcface_defaults()
		return

	doc = frappe.new_doc("Face Attendance Settings")
	# ── High-level enterprise defaults ──
	doc.enabled = 1
	doc.default_company = None  # set below
	doc.mobile_api_key = None  # auto-generated in validate
	# Mobile App Rules
	doc.min_face_match_score = 0.40
	doc.checkin_photo_required = 0
	doc.allow_offline_sync = 1
	doc.max_checkins_per_day = 20
	doc.require_gps = 1
	doc.geofence_radius_meters = 500
	doc.strict_geofence = 0
	doc.auto_log_type = "Auto"
	doc.min_minutes_between_checkin_checkout = 10
	# Integration
	doc.sync_to_employee_checkin = 1
	doc.sync_to_hr_attendance = 1
	doc.kiosk_mode_enabled = 1
	# Face Biometric — ArcFace only
	doc.biometric_model_name = "ArcFace"
	doc.biometric_model_version = "insightface-buffalo_l-1.0"
	doc.biometric_embedding_dimension = 512
	doc.face_similarity_metric = "cosine"
	doc.face_duplicate_threshold = 0.45
	doc.face_match_threshold = 0.40
	doc.face_same_person_update_threshold = 0.50
	doc.liveness_provider = "none"
	# ArcFace Service
	doc.recognition_backend = "arcface_service"
	doc.face_service_url = "http://127.0.0.1:8090"
	# leave face_service_api_key empty — admin must set per server (see .env)
	doc.face_service_timeout_seconds = 30

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
