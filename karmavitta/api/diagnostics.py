"""Desk / console diagnostics for face recognition — never prints embeddings."""

from __future__ import annotations

import frappe

from karmavitta.face_attendance.utils import get_settings
from karmavitta.services.face_service_client import face_service_enabled, health


@frappe.whitelist()
def face_recognition_diagnostics():
	"""Safe ops report for Face Attendance Settings + optional ArcFace service."""
	if not frappe.has_permission("Face Attendance Settings", "read"):
		frappe.throw("Not permitted", frappe.PermissionError)

	settings = get_settings()
	active = frappe.db.count("Face Biometric", {"enabled": 1, "registration_status": "Active"})
	arcface = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabFace Biometric`
		WHERE enabled=1 AND registration_status='Active'
		  AND LOWER(IFNULL(model_name,'')) LIKE '%%arcface%%'
		"""
	)[0][0]
	facenet = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabFace Biometric`
		WHERE enabled=1 AND registration_status='Active'
		  AND (LOWER(IFNULL(model_name,'')) LIKE '%%facenet%%' OR IFNULL(model_name,'')='')
		"""
	)[0][0]

	payload = {
		"success": True,
		"recognition_backend": getattr(settings, "recognition_backend", None) or "facenet_local",
		"biometric_model_name": settings.biometric_model_name,
		"biometric_model_version": settings.biometric_model_version,
		"embedding_dimension": settings.biometric_embedding_dimension,
		"face_match_threshold": settings.face_match_threshold,
		"face_duplicate_threshold": settings.face_duplicate_threshold,
		"min_face_match_score": settings.min_face_match_score,
		"active_templates": active,
		"active_arcface_templates": cint_safe(arcface),
		"active_facenet_templates": cint_safe(facenet),
		"face_service_enabled": face_service_enabled(settings),
		"face_service_url": getattr(settings, "face_service_url", None),
		"face_service_health": None,
	}
	if face_service_enabled(settings):
		payload["face_service_health"] = health(settings)
	return payload


def cint_safe(v):
	try:
		return int(v)
	except Exception:
		return 0
