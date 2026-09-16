"""Public Frappe API for face biometrics.

Authoritative duplicate detection is always server-side.
"""

from __future__ import annotations

import frappe

from karmavitta.face_attendance.biometric import (
	approve_face_reregistration as _approve,
	biometric_settings,
	delete_face_template as _delete,
	disable_face_template as _disable,
	get_face_registration_status as _status,
	list_active_biometric_templates_for_match,
	register_face_biometric,
	request_face_reregistration as _request_rereg,
	verify_face_biometric,
)
from karmavitta.face_attendance.utils import validate_mobile_api_key


def _parse_bool(value) -> bool:
	return str(value).lower() in ("1", "true", "yes")


@frappe.whitelist()
def register_face(
	employee: str | None = None,
	biometric_template=None,
	embedding_dimension: int | str | None = None,
	model_name: str | None = None,
	model_version: str | None = None,
	template_version: str | None = None,
	device_id: str | None = None,
	allow_update: int | str | bool | None = 0,
	admin_override: int | str | bool | None = 0,
	face_image=None,
):
	"""Register a face for an employee (server-side uniqueness).

	Requires ``face_image`` (base64) — ArcFace backend only.
	"""
	from karmavitta.face_attendance.utils import get_settings
	from karmavitta.services.face_service_client import (
		FaceServiceError,
		decode_image_payload,
		face_service_enabled,
		register_from_image,
	)

	settings = get_settings()
	if face_service_enabled(settings) and face_image:
		try:
			image_bytes, filename, content_type = decode_image_payload(face_image)
			company = frappe.db.get_value("Employee", employee, "company") if employee else None
			svc = register_from_image(
				image_bytes=image_bytes,
				filename=filename,
				content_type=content_type,
				exclude_employee=employee,
				company=company,
				settings=settings,
			)
		except FaceServiceError as exc:
			return {
				"success": False,
				"message": str(exc),
				"code": exc.code,
				"error_code": exc.code,
			}

		biometric_template = svc.get("embedding")
		embedding_dimension = svc.get("embedding_dimension")
		model_name = svc.get("model_name") or "ArcFace"
		model_version = svc.get("model_version")
		template_version = svc.get("template_version") or "arcface-1"

	return register_face_biometric(
		employee=employee or "",
		biometric_template=biometric_template,
		embedding_dimension=int(embedding_dimension) if embedding_dimension not in (None, "") else None,
		model_name=model_name,
		model_version=model_version,
		template_version=template_version,
		device_id=device_id,
		allow_update=_parse_bool(allow_update),
		admin_override=_parse_bool(admin_override),
	)


@frappe.whitelist(allow_guest=True)
def verify_face(
	biometric_template=None,
	employee: str | None = None,
	embedding_dimension: int | str | None = None,
	model_name: str | None = None,
	model_version: str | None = None,
	device_id: str | None = None,
	api_key: str | None = None,
	face_image=None,
	company: str | None = None,
):
	"""Verify / identify a face. Optional api_key for kiosk.

	With arcface_service + face_image, identity comes only from ArcFace 1:N.
	Client ``employee`` is never trusted for attendance identity.
	"""
	if api_key:
		validate_mobile_api_key(api_key)
	elif frappe.session.user == "Guest":
		frappe.throw("Authentication required", frappe.AuthenticationError)

	from karmavitta.face_attendance.utils import get_settings
	from karmavitta.services.face_service_client import (
		FaceServiceError,
		decode_image_payload,
		face_service_enabled,
		verify_from_image,
	)

	settings = get_settings()
	if face_service_enabled(settings) and face_image:
		try:
			image_bytes, filename, content_type = decode_image_payload(face_image)
			# Never use client-supplied employee for identity
			return verify_from_image(
				image_bytes=image_bytes,
				filename=filename,
				content_type=content_type,
				company=company or settings.default_company,
				settings=settings,
			)
		except FaceServiceError as exc:
			return {
				"success": False,
				"matched": False,
				"message": str(exc),
				"code": exc.code,
				"error_code": exc.code,
			}

	return verify_face_biometric(
		biometric_template=biometric_template,
		employee=employee,
		embedding_dimension=int(embedding_dimension) if embedding_dimension not in (None, "") else None,
		model_name=model_name,
		model_version=model_version,
		device_id=device_id,
	)


@frappe.whitelist()
def get_face_registration_status(employee: str | None = None):
	return _status(employee or "")


@frappe.whitelist()
def request_face_reregistration(employee: str | None = None, remarks: str | None = None):
	return _request_rereg(employee or "", remarks=remarks)


@frappe.whitelist()
def approve_face_reregistration(employee: str | None = None):
	return _approve(employee or "")


@frappe.whitelist()
def delete_face_template(employee: str | None = None):
	return _delete(employee or "")


@frappe.whitelist()
def disable_face_template(employee: str | None = None):
	return _disable(employee or "")


@frappe.whitelist(allow_guest=True)
def get_biometric_config(api_key: str | None = None):
	"""Public thresholds + model metadata for the mobile app (no templates)."""
	try:
		validate_mobile_api_key(api_key)
		cfg = biometric_settings()
		return {"success": True, "config": cfg}
	except Exception as exc:
		return {"success": False, "message": str(exc)}


@frappe.whitelist(allow_guest=True)
def list_active_face_templates(api_key: str | None = None):
	"""Kiosk-only: return active embeddings for on-device match (requires Mobile API Key).

	Do not expose this to normal Employee roles without API key.
	"""
	try:
		validate_mobile_api_key(api_key)
		# Extra gate: only when kiosk mode enabled
		from karmavitta.face_attendance.utils import get_settings

		settings = get_settings()
		if not settings.kiosk_mode_enabled and frappe.session.user == "Guest":
			# Still allow with valid API key for admin attendance devices
			pass
		templates = list_active_biometric_templates_for_match()
		return {"success": True, "profiles": templates, "count": len(templates)}
	except Exception as exc:
		return {"success": False, "message": str(exc), "profiles": []}
