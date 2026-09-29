"""Post-install setup for Karmavitta Face Attendance."""

from __future__ import annotations

import json
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
	"""Create a populated Mobile App Management workspace and its entry points."""
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
		changed = False
		page_exists = frappe.db.exists("Page", "mobile-app-permissions")
		shortcuts = [
			{
				"label": "Permission Profiles",
				"link_to": "Mobile App Permission",
				"type": "DocType",
				"doc_view": "List",
				"color": "Blue",
			},
			{
				"label": "Mobile App Settings",
				"link_to": "Mobile App Settings",
				"type": "DocType",
				"doc_view": "List",
				"color": "Green",
			},
		]
		links = [
			{"type": "Card Break", "label": "Access & Profiles", "link_count": 1},
			{
				"type": "Link",
				"label": "Permission Profiles",
				"link_type": "DocType",
				"link_to": "Mobile App Permission",
				"onboard": 1,
			},
		]
		content_blocks = [
			{
				"id": "karmavitta_mobile_management_title",
				"type": "header",
				"data": {"text": '<span class="h4"><b>Mobile App Control Center</b></span>', "col": 12},
			},
			{
				"id": "karmavitta_mobile_management_help",
				"type": "paragraph",
				"data": {
					"text": "Manage which ERPNext users can sign in to the mobile app and choose the screens each user can access.",
					"col": 12,
				},
			},
		]
		if page_exists:
			shortcuts.insert(0, {
				"label": "Mobile App Permissions",
				"link_to": "mobile-app-permissions",
				"type": "Page",
				"color": "Blue",
			})
			links[1:1] = [{
				"type": "Link",
				"label": "Mobile App Permissions",
				"link_type": "Page",
				"link_to": "mobile-app-permissions",
				"onboard": 1,
			}]
			links[0]["link_count"] = 2
			content_blocks.append({"id": "karmavitta_mobile_management_spacer", "type": "spacer", "data": {"col": 12}})
			content_blocks.append({
				"id": "karmavitta_mobile_management_shortcuts_title",
				"type": "header",
				"data": {"text": '<span class="h4"><b>Quick Access</b></span>', "col": 12},
			})
			content_blocks.append({
				"id": "karmavitta_mobile_management_shortcut_page",
				"type": "shortcut",
				"data": {"shortcut_name": "Mobile App Permissions", "col": 4},
			})
		content_blocks.extend([
			{
				"id": "karmavitta_mobile_management_shortcut_profiles",
				"type": "shortcut",
				"data": {"shortcut_name": "Permission Profiles", "col": 4},
			},
			{
				"id": "karmavitta_mobile_management_shortcut_settings",
				"type": "shortcut",
				"data": {"shortcut_name": "Mobile App Settings", "col": 4},
			},
			{"id": "karmavitta_mobile_management_spacer2", "type": "spacer", "data": {"col": 12}},
			{
				"id": "karmavitta_mobile_management_cards_title",
				"type": "header",
				"data": {"text": '<span class="h4"><b>Management</b></span>', "col": 12},
			},
			{
				"id": "karmavitta_mobile_management_access_card",
				"type": "card",
				"data": {"card_name": "Access & Profiles", "col": 6},
			},
			{
				"id": "karmavitta_mobile_management_settings_card",
				"type": "card",
				"data": {"card_name": "Configuration", "col": 6},
			},
		])
		links.extend([
			{"type": "Card Break", "label": "Configuration", "link_count": 1},
			{
				"type": "Link",
				"label": "Mobile App Settings",
				"link_type": "DocType",
				"link_to": "Mobile App Settings",
				"onboard": 1,
			},
		])

		managed_targets = {
			("Page", "mobile-app-permissions"),
			("DocType", "Mobile App Permission"),
			("DocType", "Mobile App Settings"),
		}
		managed_card_labels = {"Access & Profiles", "Configuration"}
		preserved_links = [
			row for row in (ws.links or [])
			if (row.link_type, row.link_to) not in managed_targets
			and not (row.type == "Card Break" and row.label in managed_card_labels)
		]
		previous_managed_links = [
			(row.type, row.label, row.link_type, row.link_to, row.link_count)
			for row in (ws.links or [])
			if (row.link_type, row.link_to) in managed_targets
			or (row.type == "Card Break" and row.label in managed_card_labels)
		]
		desired_managed_links = [
			(row["type"], row["label"], row.get("link_type"), row.get("link_to"), row.get("link_count", 0))
			for row in links
		]
		if previous_managed_links != desired_managed_links:
			ws.links = preserved_links
			for link in links:
				ws.append("links", link)
			changed = True

		existing_shortcuts = {row.label: row for row in (ws.shortcuts or [])}
		for shortcut in shortcuts:
			existing = existing_shortcuts.get(shortcut["label"])
			if not existing:
				ws.append("shortcuts", shortcut)
				changed = True
			elif any(getattr(existing, field, None) != value for field, value in shortcut.items()):
				for field, value in shortcut.items():
					setattr(existing, field, value)
				changed = True

		try:
			current_content = json.loads(ws.content or "[]")
		except (TypeError, ValueError):
			current_content = []
		if not isinstance(current_content, list):
			current_content = []
		current_ids = {block.get("id") for block in current_content if isinstance(block, dict)}
		for block in content_blocks:
			if block["id"] not in current_ids:
				current_content.append(block)
				changed = True
		updated_content = json.dumps(current_content, ensure_ascii=False)
		if ws.content != updated_content:
			ws.content = updated_content
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
			ws.module = title
			ws.public = 1
			ws.sequence_id = 2
			ws.content = "[]"
		else:
			ws = frappe.get_doc("Workspace", ws_name)

		workspace_changed = False
		shortcut_definitions = [
			("Face Attendance Settings", "Face Attendance Settings", "Green"),
			("Attendance Logs", "Face Attendance Log", "Blue"),
			("Face Biometric", "Face Biometric", "Blue"),
			("Employee Face Profiles", "Employee Face Profile", "Grey"),
			("Registration Audit", "Face Registration Audit", "Grey"),
		]
		shortcuts = [
			{
				"label": label,
				"link_to": doctype,
				"type": "DocType",
				"doc_view": "List",
				"color": color,
			}
			for label, doctype, color in shortcut_definitions
			if frappe.db.exists("DocType", doctype)
		]
		group_definitions = [
			("Attendance & Settings", [shortcut_definitions[0], shortcut_definitions[1]]),
			("Face Identity", [shortcut_definitions[2], shortcut_definitions[3], shortcut_definitions[4]]),
		]
		links = []
		content_blocks = [
			{
				"id": "karmavitta_face_attendance_title",
				"type": "header",
				"data": {"text": '<span class="h4"><b>Face Attendance Operations</b></span>', "col": 12},
			},
			{
				"id": "karmavitta_face_attendance_help",
				"type": "paragraph",
				"data": {
					"text": "Review attendance activity, manage face registrations, and configure locations and verification settings.",
					"col": 12,
				},
			},
			{"id": "karmavitta_face_attendance_spacer1", "type": "spacer", "data": {"col": 12}},
			{
				"id": "karmavitta_face_attendance_shortcuts_title",
				"type": "header",
				"data": {"text": '<span class="h4"><b>Quick Access</b></span>', "col": 12},
			},
		]
		for index, (label, doctype, color) in enumerate(shortcut_definitions):
			if not frappe.db.exists("DocType", doctype):
				continue
			content_blocks.append({
				"id": f"karmavitta_face_attendance_shortcut_{index}",
				"type": "shortcut",
				"data": {"shortcut_name": label, "col": 3},
			})
		content_blocks.append({"id": "karmavitta_face_attendance_spacer2", "type": "spacer", "data": {"col": 12}})
		content_blocks.append({
			"id": "karmavitta_face_attendance_cards_title",
			"type": "header",
			"data": {"text": '<span class="h4"><b>Management</b></span>', "col": 12},
		})
		for index, (group_label, group_links) in enumerate(group_definitions):
			available_links = [
				item for item in group_links if frappe.db.exists("DocType", item[1])
			]
			if not available_links:
				continue
			links.append({"type": "Card Break", "label": group_label, "link_count": len(available_links)})
			for label, doctype, _color in available_links:
				links.append({
					"type": "Link",
					"label": label,
					"link_type": "DocType",
					"link_to": doctype,
					"onboard": 1,
				})
			content_blocks.append({
				"id": f"karmavitta_face_attendance_card_{index}",
				"type": "card",
				"data": {"card_name": group_label, "col": 4},
			})

		managed_targets = {("DocType", doctype) for _label, doctype, _color in shortcut_definitions}
		# Face Attendance Location is a child table managed inside settings, not a standalone screen.
		managed_targets.add(("DocType", "Face Attendance Location"))
		managed_card_labels = {label for label, _items in group_definitions} | {"Location Management"}
		managed_content_prefix = "karmavitta_face_attendance_"
		kept_shortcuts = [
			row for row in (ws.shortcuts or []) if row.label != "Face Attendance Locations"
		]
		if len(kept_shortcuts) != len(ws.shortcuts or []):
			ws.shortcuts = kept_shortcuts
			workspace_changed = True
		preserved_links = [
			row for row in (ws.links or [])
			if (row.link_type, row.link_to) not in managed_targets
			and not (row.type == "Card Break" and row.label in managed_card_labels)
		]
		previous_managed_links = [
			(row.type, row.label, row.link_type, row.link_to, row.link_count)
			for row in (ws.links or [])
			if (row.link_type, row.link_to) in managed_targets
			or (row.type == "Card Break" and row.label in managed_card_labels)
		]
		desired_managed_links = [
			(row["type"], row["label"], row.get("link_type"), row.get("link_to"), row.get("link_count", 0))
			for row in links
		]
		if previous_managed_links != desired_managed_links:
			ws.links = preserved_links
			for link in links:
				ws.append("links", link)
			workspace_changed = True

		existing_shortcuts = {row.label: row for row in (ws.shortcuts or [])}
		for shortcut in shortcuts:
			existing = existing_shortcuts.get(shortcut["label"])
			if not existing:
				ws.append("shortcuts", shortcut)
				workspace_changed = True
			elif any(getattr(existing, field, None) != value for field, value in shortcut.items()):
				for field, value in shortcut.items():
					setattr(existing, field, value)
				workspace_changed = True

		try:
			current_content = json.loads(ws.content or "[]")
		except (TypeError, ValueError):
			current_content = []
		if not isinstance(current_content, list):
			current_content = []
		managed_positions = [
			index for index, block in enumerate(current_content)
			if isinstance(block, dict)
			and isinstance(block.get("id"), str)
			and block["id"].startswith(managed_content_prefix)
		]
		first_managed_position = min(managed_positions, default=len(current_content))
		insertion_index = sum(
			1 for block in current_content[:first_managed_position]
			if not (
				isinstance(block, dict)
				and isinstance(block.get("id"), str)
				and block["id"].startswith(managed_content_prefix)
			)
		)
		kept_content = [
			block for block in current_content
			if not (
				isinstance(block, dict)
				and isinstance(block.get("id"), str)
				and block["id"].startswith(managed_content_prefix)
			)
		]
		updated_blocks = kept_content[:insertion_index] + content_blocks + kept_content[insertion_index:]
		if updated_blocks != current_content:
			current_content = updated_blocks
			workspace_changed = True
		updated_content = json.dumps(current_content, ensure_ascii=False)
		if ws.content != updated_content:
			ws.content = updated_content
			workspace_changed = True

		if is_new:
			ws.insert(ignore_permissions=True)
		elif workspace_changed:
			ws.save(ignore_permissions=True)
		if is_new or workspace_changed:
			frappe.clear_cache()
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
