"""HTTP client for the Karmavritta Face Recognition Service (ArcFace).

Never logs images, embeddings, or API keys.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils import cint, flt

from karmavitta.face_attendance.utils import get_settings

BUILT_IN_RUNTIME = "Built-in (same Frappe app)"
EXTERNAL_RUNTIME = "External Face Service"


class FaceServiceError(Exception):
	def __init__(self, message: str, code: str = "FACE_SERVICE_ERROR", payload: dict | None = None):
		super().__init__(message)
		self.code = code
		self.payload = payload or {}


def face_service_enabled(settings=None) -> bool:
	"""Whether ArcFace is configured, remotely or inside a managed Frappe worker."""
	return recognition_mode(settings) != "unconfigured"


def _is_frappe_cloud() -> bool:
	try:
		from frappe.utils.frappecloud import on_frappecloud

		return bool(on_frappecloud())
	except Exception:
		return False


def recognition_mode(settings=None) -> str:
	settings = settings or get_settings()
	backend = (getattr(settings, "recognition_backend", None) or "arcface_service").strip().lower()
	url = (getattr(settings, "face_service_url", None) or "").strip()
	if backend not in {"arcface_service", "insightface", "arcface"}:
		return "unconfigured"

	selected_mode = (getattr(settings, "face_recognition_mode", None) or "").strip()
	if selected_mode == BUILT_IN_RUNTIME:
		return "in_process"
	if selected_mode == EXTERNAL_RUNTIME:
		return "external_service" if url else "unconfigured"

	# Backwards compatibility for settings created before the runtime selector existed.
	if url:
		return "external_service"
	if _is_frappe_cloud():
		return "in_process"
	return "unconfigured"


def _headers(settings) -> dict[str, str]:
	key = ""
	try:
		# Password fields need get_password()
		key = settings.get_password("face_service_api_key") or ""
	except Exception:
		key = (getattr(settings, "face_service_api_key", None) or "").strip()
	return {"X-API-Key": key.strip()}


def _url(settings, path: str) -> str:
	base = (getattr(settings, "face_service_url", None) or "").rstrip("/")
	if not base:
		raise FaceServiceError("Face service URL is not configured", "FACE_SERVICE_NOT_CONFIGURED")
	return f"{base}{path}"


def _post_multipart(path: str, *, files: dict, data: dict, settings=None) -> dict[str, Any]:
	settings = settings or get_settings()
	try:
		import requests
	except ImportError as exc:
		raise FaceServiceError("Python package 'requests' is required", "DEPENDENCY_MISSING") from exc

	timeout = cint(getattr(settings, "face_service_timeout_seconds", None) or 30)
	try:
		resp = requests.post(
			_url(settings, path),
			headers=_headers(settings),
			files=files,
			data=data,
			timeout=timeout,
		)
	except Exception as exc:  # noqa: BLE001
		frappe.log_error(title="Face Service Request Failed", message=str(exc)[:500])
		raise FaceServiceError("Face recognition service unavailable", "FACE_SERVICE_UNAVAILABLE") from exc

	try:
		payload = resp.json()
	except Exception:
		payload = {"success": False, "code": "FACE_SERVICE_ERROR", "message": resp.text[:200]}

	if resp.status_code >= 400 or not payload.get("success", resp.status_code < 400):
		code = payload.get("code") or "FACE_SERVICE_ERROR"
		msg = payload.get("message") or "Face recognition failed"
		raise FaceServiceError(msg, code=code, payload=payload)

	return payload


def health(settings=None, *, initialize_model: bool = False) -> dict[str, Any]:
	"""Check the selected ArcFace runtime and its current readiness."""
	settings = settings or get_settings()
	if recognition_mode(settings) == "in_process":
		from karmavitta.services.face_runtime import health as in_process_health

		return in_process_health(initialize_model=initialize_model)

	try:
		import requests

		resp = requests.get(
			_url(settings, "/diagnostics"),
			headers=_headers(settings),
			timeout=10,
		)
		try:
			payload = resp.json()
		except Exception:
			payload = {}
		if resp.status_code == 401:
			return {
				"success": False,
				"status": "unauthorized",
				"message": "Face Service API Key does not match the configured service key",
			}
		if resp.status_code >= 400 or not payload.get("success"):
			return {
				"success": False,
				"status": "error",
				"message": payload.get("message") or f"Face service returned HTTP {resp.status_code}",
			}
		payload["status"] = "ok" if payload.get("ready") else "degraded"
		return payload
	except Exception as exc:  # noqa: BLE001
		return {"success": False, "status": "error", "message": str(exc)}


def list_arcface_templates_for_company(company: str | None = None) -> list[dict[str, Any]]:
	"""Authorized biometric population for matching (ArcFace only)."""
	filters = {"enabled": 1, "registration_status": "Active"}
	rows = frappe.get_all(
		"Face Biometric",
		filters=filters,
		fields=[
			"name",
			"employee",
			"employee_name",
			"company",
			"biometric_template",
			"embedding_dimension",
			"model_name",
			"model_version",
			"enabled",
		],
		limit_page_length=5000,
	)
	from karmavitta.face_attendance.biometric import parse_template

	out = []
	for row in rows:
		model = (row.model_name or "").strip().lower()
		if model and model not in {"arcface", "insightface"} and "arcface" not in model:
			# Skip non-ArcFace templates (legacy)
			continue
		if company and row.company and str(row.company) != str(company):
			continue
		vector = parse_template(row.biometric_template)
		if not vector:
			continue
		out.append(
			{
				"employee": row.employee,
				"embedding": vector,
				"model_name": row.model_name,
				"model_version": row.model_version,
				"embedding_dimension": row.embedding_dimension or len(vector),
				"company": row.company,
				"enabled": bool(row.enabled),
			}
		)
	return out


def register_from_image(
	*,
	image_bytes: bytes,
	filename: str = "face.jpg",
	content_type: str = "image/jpeg",
	exclude_employee: str | None = None,
	company: str | None = None,
	settings=None,
) -> dict[str, Any]:
	settings = settings or get_settings()
	if recognition_mode(settings) == "in_process":
		from karmavitta.services.face_runtime import register_from_image as register_locally

		return register_locally(
			image_bytes=image_bytes,
			exclude_employee=exclude_employee,
			company=company,
			settings=settings,
		)

	templates = list_arcface_templates_for_company(company)
	files = {"image": (filename, image_bytes, content_type)}
	data = {
		"templates_json": json.dumps(templates),
		"exclude_employee": exclude_employee or "",
		"company": company or "",
	}
	return _post_multipart("/face/register", files=files, data=data, settings=settings)


def verify_from_image(
	*,
	image_bytes: bytes,
	filename: str = "face.jpg",
	content_type: str = "image/jpeg",
	company: str | None = None,
	settings=None,
) -> dict[str, Any]:
	settings = settings or get_settings()
	if recognition_mode(settings) == "in_process":
		from karmavitta.services.face_runtime import verify_from_image as verify_locally

		return verify_locally(
			image_bytes=image_bytes,
			company=company,
			settings=settings,
		)

	templates = list_arcface_templates_for_company(company)
	if not templates:
		raise FaceServiceError(
			"No ArcFace biometric templates registered. Employees must re-register faces.",
			"NO_ARCFACE_TEMPLATES",
		)
	files = {"image": (filename, image_bytes, content_type)}
	data = {
		"templates_json": json.dumps(templates),
		"company": company or "",
	}
	return _post_multipart("/face/verify", files=files, data=data, settings=settings)


def decode_image_payload(face_image) -> tuple[bytes, str, str]:
	"""Accept base64 data-URL / raw base64 / binary."""
	import base64

	max_image_bytes = 5 * 1024 * 1024
	max_encoded_chars = ((max_image_bytes + 2) // 3) * 4 + 512

	if face_image is None or face_image == "":
		raise FaceServiceError("face_image is required", "INVALID_IMAGE")

	content_type = "image/jpeg"
	filename = "face.jpg"

	if isinstance(face_image, (bytes, bytearray)):
		data = bytes(face_image)
		if len(data) > max_image_bytes:
			raise FaceServiceError("Image exceeds the 5 MB limit", "IMAGE_TOO_LARGE")
		return data, filename, content_type

	raw = str(face_image).strip()
	if raw.startswith("data:"):
		header, _, b64 = raw.partition(",")
		if "image/png" in header:
			content_type = "image/png"
			filename = "face.png"
		elif "image/webp" in header:
			content_type = "image/webp"
			filename = "face.webp"
		raw = b64
	if len(raw) > max_encoded_chars:
		raise FaceServiceError("Image exceeds the 5 MB limit", "IMAGE_TOO_LARGE")
	try:
		data = base64.b64decode(raw, validate=False)
	except Exception as exc:  # noqa: BLE001
		raise FaceServiceError("Invalid face_image encoding", "INVALID_IMAGE") from exc
	if not data:
		raise FaceServiceError("Empty face_image", "INVALID_IMAGE")
	if len(data) > max_image_bytes:
		raise FaceServiceError("Image exceeds the 5 MB limit", "IMAGE_TOO_LARGE")
	return data, filename, content_type
