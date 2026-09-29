"""Desk / console diagnostics for face recognition — never prints embeddings."""

from __future__ import annotations

import frappe
from frappe.utils import cint

from karmavitta.face_attendance.utils import get_settings
from karmavitta.services.face_service_client import face_service_enabled, health, recognition_mode


def _is_frappe_cloud() -> bool:
	try:
		from frappe.utils.frappecloud import on_frappecloud

		return bool(on_frappecloud())
	except Exception:
		return False


@frappe.whitelist()
def face_recognition_diagnostics(initialize_model=0):
	"""Safe ops report for Face Attendance Settings + optional ArcFace service."""
	if not frappe.has_permission("Face Attendance Settings", "read"):
		frappe.throw("Not permitted", frappe.PermissionError)
	initialize_model = bool(cint(initialize_model))
	if initialize_model and not frappe.has_permission("Face Attendance Settings", "write"):
		frappe.throw("Write permission is required to initialize the ArcFace model", frappe.PermissionError)

	settings = get_settings()
	mode = recognition_mode(settings)
	face_service_url = (getattr(settings, "face_service_url", None) or "").strip()
	try:
		service_key = settings.get_password("face_service_api_key", raise_exception=False) or ""
	except Exception:
		service_key = getattr(settings, "face_service_api_key", None) or ""
		if settings.is_dummy_password(str(service_key)):
			service_key = ""
	face_service_key_configured = bool(service_key)
	active = frappe.db.count("Face Biometric", {"enabled": 1, "registration_status": "Active"})
	arcface = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabFace Biometric`
		WHERE enabled=1 AND registration_status='Active'
		  AND LOWER(IFNULL(model_name,'')) LIKE '%%arcface%%'
		"""
	)[0][0]

	payload = {
		"success": True,
		"recognition_mode": mode,
		"recognition_backend": getattr(settings, "recognition_backend", None) or "arcface_service",
		"biometric_model_name": settings.biometric_model_name,
		"biometric_model_version": settings.biometric_model_version,
		"embedding_dimension": settings.biometric_embedding_dimension,
		"face_match_threshold": settings.face_match_threshold,
		"face_duplicate_threshold": settings.face_duplicate_threshold,
		"min_face_match_score": settings.min_face_match_score,
		"active_templates": active,
		"active_arcface_templates": cint_safe(arcface),
		"face_service_enabled": face_service_enabled(settings),
		"face_service_url": face_service_url,
		"face_service_api_key_configured": face_service_key_configured,
		"mobile_api_key_configured": bool((getattr(settings, "mobile_api_key", None) or "").strip()),
		"face_service_health": None,
		"hosting": "frappe_cloud" if _is_frappe_cloud() else "self_hosted",
		"configuration_required": mode == "unconfigured"
		or (mode == "external_service" and (not face_service_url or not face_service_key_configured)),
	}
	if face_service_enabled(settings):
		payload["face_service_health"] = health(settings, initialize_model=initialize_model)
	return payload


def cint_safe(v):
	try:
		return int(v)
	except Exception:
		return 0
