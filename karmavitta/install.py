"""Post-install setup for Karmavitta Face Attendance."""

from __future__ import annotations

from urllib.parse import urlsplit

import frappe
from frappe.utils import cint, random_string

from karmavitta.services.face_service_client import BUILT_IN_RUNTIME, EXTERNAL_RUNTIME


def _is_managed_hosting() -> bool:
	"""Return whether this site cannot start a custom local process."""
	try:
		from frappe.utils.frappecloud import on_frappecloud

		return bool(on_frappecloud())
	except Exception:
		return False


def after_install():
	_ensure_settings()
	_ensure_workspace()
	_ensure_mobile_management()
	_ensure_procfile_entry()
	_ensure_local_face_service_config()
	frappe.db.commit()


def after_migrate():
	_ensure_settings()
	_ensure_workspace()
	_ensure_mobile_management()
	_ensure_face_biometric_workspace_link()
	_enable_hr_sync_defaults()
	_ensure_procfile_entry()
	_ensure_local_face_service_config()
	frappe.db.commit()


def _ensure_mobile_management():
	"""Create the singleton mobile settings and its separate Desk workspace."""
	if not frappe.db.exists("DocType", "Mobile App Settings"):
		return
	try:
		settings = frappe.get_single("Mobile App Settings")
		if not settings.permission_version:
			settings.permission_version = 1
		if not settings.app_name:
			settings.app_name = "Karmavitta"
		if not settings.default_landing_screen:
			settings.default_landing_screen = "EmployeeHome"
		if settings.enabled is None:
			settings.enabled = 1
		if settings.default_allow_mobile_access is None:
			settings.default_allow_mobile_access = 0
		if settings.allow_offline_mode is None:
			settings.allow_offline_mode = 1
		if not settings.session_timeout_minutes:
			settings.session_timeout_minutes = 60
		settings.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Karmavitta Mobile Settings Setup", message=frappe.get_traceback())

	if not frappe.db.exists("DocType", "Mobile App Permission"):
		return
	try:
		title = "Mobile App Management"
		ws_name = frappe.db.get_value("Workspace", {"title": title}, "name")
		if not ws_name and frappe.db.exists("Workspace", title):
			ws_name = title
		is_new = not ws_name
		ws = frappe.new_doc("Workspace") if is_new else frappe.get_doc("Workspace", ws_name)
		if is_new:
			ws.label = title
			ws.title = title
			ws.module = title
			ws.public = 1
			ws.sequence_id = 3
			ws.content = "[]"
		# Keep the simple user-to-screen page as the primary entry point. The
		# legacy profile DocType stays installed for existing permission records.
		legacy_links = [
			row for row in (ws.links or [])
			if row.link_type == "DocType" and row.link_to == "Mobile App Permission"
		]
		changed = bool(legacy_links)
		if legacy_links:
			ws.links = [row for row in ws.links if row not in legacy_links]
		links = [("DocType", "Mobile App Settings", "Mobile App Settings")]
		if frappe.db.exists("Page", "mobile-app-permissions"):
			links.append(("Page", "mobile-app-permissions", "Mobile App Permissions"))
		existing_links = {(row.link_type, row.link_to): row for row in (ws.links or [])}
		for link_type, link_to, label in links:
			key = (link_type, link_to)
			if key not in existing_links:
				ws.append("links", {"type": "Link", "label": label, "link_type": link_type, "link_to": link_to, "onboard": 1})
				changed = True
		if is_new:
			ws.insert(ignore_permissions=True)
		elif changed:
			ws.save(ignore_permissions=True)
		if is_new or changed:
			frappe.clear_cache()
	except Exception:
		frappe.log_error(title="Karmavitta Mobile Workspace Setup", message=frappe.get_traceback())


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
	"""Add face_service to a self-hosted bench Procfile so `bench start` can run it.

	Runs on self-hosted install/migrate. Safe to re-run: skips if an entry already exists.
	The bench_start.sh script itself auto-creates .venv/.env on first run.
	"""
	if _is_managed_hosting():
		return
	if frappe.db.exists("DocType", "Face Attendance Settings"):
		settings = frappe.get_single("Face Attendance Settings")
		if settings.get("face_recognition_mode") == BUILT_IN_RUNTIME:
			return
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


def _ensure_local_face_service_config():
	"""Create matching local service credentials and select a free port."""
	if _is_managed_hosting() or not frappe.db.exists("DocType", "Face Attendance Settings"):
		return

	try:
		import os
		import socket
		from frappe.utils import get_bench_path

		service_root = os.path.join(get_bench_path(), "apps", "karmavitta", "face_service")
		env_path = os.path.join(service_root, ".env")
		if not os.path.isdir(service_root):
			return

		settings = frappe.get_single("Face Attendance Settings")
		if settings.get("face_recognition_mode") == BUILT_IN_RUNTIME:
			return
		key = settings.get_password("face_service_api_key", raise_exception=False) or ""
		if not key or key == "change-me-face-service-key":
			key = random_string(48)
			settings.face_service_api_key = key
			settings.save(ignore_permissions=True)
		elif settings.get("face_service_api_key") and not settings.is_dummy_password(settings.face_service_api_key):
			# Migrate any legacy plaintext value into Frappe's encrypted password store.
			settings.save(ignore_permissions=True)
		key = settings.get_password("face_service_api_key", raise_exception=False) or key

		port = _read_env_port(env_path)
		expected_existing_url = f"http://127.0.0.1:{port}" if port else ""
		if not port or (
			(settings.face_service_url or "").rstrip("/") != expected_existing_url
			and not _port_is_available(socket, port)
		):
			port = _available_port(socket, 8090)

		env_values = {}
		if os.path.exists(env_path):
			with open(env_path) as env_file:
				for line in env_file:
					if "=" in line and not line.lstrip().startswith("#"):
						name, value = line.rstrip("\n").split("=", 1)
						env_values[name.strip()] = value.strip()
		env_values["FACE_SERVICE_API_KEY"] = key
		env_values["FACE_SERVICE_PORT"] = str(port)
		env_values["FACE_SERVICE_HOST"] = "127.0.0.1"
		with open(env_path, "w") as env_file:
			for name, value in env_values.items():
				env_file.write(f"{name}={value}\n")
		os.chmod(env_path, 0o600)

		current_url = (settings.face_service_url or "").rstrip("/")
		expected_url = f"http://127.0.0.1:{port}"
		if current_url != expected_url:
			settings.db_set("face_service_url", expected_url, update_modified=False)
			frappe.clear_cache()
	except Exception:
		frappe.log_error(title="Karmavitta Face Service Setup", message=frappe.get_traceback())


def _read_env_port(env_path: str) -> int | None:
	try:
		import re

		if not __import__("os").path.exists(env_path):
			return None
		with open(env_path) as env_file:
			match = re.search(r"(?m)^\s*FACE_SERVICE_PORT\s*=\s*(\d+)", env_file.read())
		port = int(match.group(1)) if match else 0
		return port if 1024 <= port <= 65535 else None
	except Exception:
		return None


def _available_port(socket_module, start: int = 8090) -> int:
	for port in range(start, start + 100):
		try:
			with socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM) as probe:
				probe.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)
				probe.bind(("127.0.0.1", port))
				return port
		except OSError:
			continue
	return start


def _port_is_available(socket_module, port: int) -> bool:
	try:
		with socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM) as probe:
			probe.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)
			probe.bind(("127.0.0.1", port))
			return True
	except OSError:
		return False


def _ensure_arcface_defaults():
	"""Idempotent ArcFace-only enforcement for installs and migrates."""
	if not frappe.db.exists("DocType", "Face Attendance Settings"):
		return
	try:
		doc = frappe.get_single("Face Attendance Settings")
		changed = False
		service_url = (doc.get("face_service_url") or "").strip()
		runtime_mode = (doc.get("face_recognition_mode") or "").strip()
		local_service_url = urlsplit(service_url).hostname in {"localhost", "127.0.0.1", "0.0.0.0"}

		# A Cloud site's localhost URL points back to its own worker, not to an
		# installable face-service process. Repair legacy configs to built-in mode.
		if _is_managed_hosting() and local_service_url:
			doc.db_set("face_service_url", "", update_modified=False)
			service_url = ""
			runtime_mode = BUILT_IN_RUNTIME
			doc.db_set("face_recognition_mode", runtime_mode, update_modified=False)
			changed = True

		if not runtime_mode:
			runtime_mode = EXTERNAL_RUNTIME if service_url else BUILT_IN_RUNTIME
			doc.db_set("face_recognition_mode", runtime_mode, update_modified=False)
			changed = True

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
		if (
			runtime_mode != BUILT_IN_RUNTIME
			and not getattr(doc, "face_service_url", None)
			and not _is_managed_hosting()
		):
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
		doc = frappe.get_single("Face Attendance Settings")
		mobile_key = (doc.mobile_api_key or "").strip()
		service_key = doc.get_password("face_service_api_key", raise_exception=False) or ""
		stored_service_key = (doc.get("face_service_api_key") or "").strip()
		service_key_needed = (doc.get("face_recognition_mode") or "") == EXTERNAL_RUNTIME
		changed = False

		if not mobile_key:
			doc.mobile_api_key = random_string(32)
			changed = True
		if service_key_needed and (not service_key or service_key == "change-me-face-service-key"):
			doc.face_service_api_key = random_string(48)
			changed = True
		elif service_key_needed and stored_service_key and not doc.is_dummy_password(stored_service_key):
			# Re-save legacy values written directly to tabSingles so Frappe encrypts them.
			changed = True

		if changed:
			if _is_managed_hosting():
				doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)
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
	doc.face_recognition_mode = BUILT_IN_RUNTIME if _is_managed_hosting() else EXTERNAL_RUNTIME
	doc.face_service_url = "" if _is_managed_hosting() else "http://127.0.0.1:8090"
	doc.face_service_api_key = None if _is_managed_hosting() else random_string(48)
	doc.face_service_timeout_seconds = 30
	if _is_managed_hosting():
		doc.flags.ignore_mandatory = True

	companies = frappe.get_all("Company", pluck="name", limit=1)
	if companies:
		doc.default_company = companies[0]
	doc.insert(ignore_permissions=True)


def _ensure_workspace():
	title = "Face Attendance"
	try:
		ws_name = frappe.db.get_value("Workspace", {"title": title}, "name")
		if not ws_name and frappe.db.exists("Workspace", title):
			ws_name = title

		is_new = not ws_name
		if is_new:
			ws = frappe.new_doc("Workspace")
			ws.label = title
			ws.title = title
			ws.public = 1
			ws.sequence_id = 2
			ws.content = "[]"
		else:
			ws = frappe.get_doc("Workspace", ws_name)

		links = [
			{
				"type": "Link",
				"label": "Face Attendance Settings",
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
		]
		existing_links = {(row.link_type, row.link_to): row for row in (ws.links or [])}
		workspace_changed = False
		for row in links:
			key = (row["link_type"], row["link_to"])
			existing_link = existing_links.get(key)
			if not existing_link:
				ws.append("links", row)
				workspace_changed = True
			elif existing_link.label != row["label"]:
				existing_link.label = row["label"]
				workspace_changed = True

		if is_new:
			ws.insert(ignore_permissions=True)
		elif workspace_changed:
			ws.save(ignore_permissions=True)
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
