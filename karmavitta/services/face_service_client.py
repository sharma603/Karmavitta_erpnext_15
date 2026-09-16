"""HTTP client for the Karmavritta Face Recognition Service (ArcFace).

Never logs images, embeddings, or API keys.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe.utils import cint, flt

from karmavitta.face_attendance.utils import get_settings


class FaceServiceError(Exception):
	def __init__(self, message: str, code: str = "FACE_SERVICE_ERROR", payload: dict | None = None):
		super().__init__(message)
		self.code = code
		self.payload = payload or {}


def face_service_enabled(settings=None) -> bool:
	settings = settings or get_settings()
	backend = (getattr(settings, "recognition_backend", None) or "arcface_service").strip().lower()
	url = (getattr(settings, "face_service_url", None) or "").strip()
	# Only ArcFace backend is supported
	return backend in {"arcface_service", "insightface", "arcface"} and bool(url)


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


def health(settings=None) -> dict[str, Any]:
	settings = settings or get_settings()
	try:
		import requests

		resp = requests.get(_url(settings, "/health"), timeout=10)
		return resp.json()
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

	if face_image is None or face_image == "":
		raise FaceServiceError("face_image is required", "INVALID_IMAGE")

	content_type = "image/jpeg"
	filename = "face.jpg"

	if isinstance(face_image, (bytes, bytearray)):
		return bytes(face_image), filename, content_type

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
	try:
		data = base64.b64decode(raw, validate=False)
	except Exception as exc:  # noqa: BLE001
		raise FaceServiceError("Invalid face_image encoding", "INVALID_IMAGE") from exc
	if not data:
		raise FaceServiceError("Empty face_image", "INVALID_IMAGE")
	return data, filename, content_type
