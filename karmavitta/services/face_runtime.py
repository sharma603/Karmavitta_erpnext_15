"""In-process ArcFace inference for managed Frappe hosting.

The engine is initialized lazily and cached once per Frappe worker process. This
lets Frappe Cloud use ArcFace without starting a separate FastAPI process.
"""

from __future__ import annotations

import traceback
from typing import Any

import frappe

from karmavitta.services.face_service_client import FaceServiceError


def _settings():
	from face_service.app.config import settings

	return settings


def _engine():
	from face_service.app.models.face_engine import get_face_engine

	engine = get_face_engine()
	if not engine.ready:
		try:
			engine.initialize_model()
		except Exception as exc:  # noqa: BLE001
			frappe.log_error(
				title="ArcFace model initialization failed",
				message=traceback.format_exc(),
			)
			raise FaceServiceError(
				"ArcFace could not load its model in this Frappe worker. Check the app build and worker logs.",
				code="MODEL_NOT_READY",
			) from exc
	return engine


def _decode_image(image_bytes: bytes):
	import cv2
	import numpy as np

	cfg = _settings()
	if not image_bytes:
		raise FaceServiceError("Empty image payload", code="INVALID_IMAGE")
	if len(image_bytes) > cfg.max_image_bytes:
		raise FaceServiceError("Image exceeds the 5 MB limit", code="IMAGE_TOO_LARGE")

	image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
	if image is None:
		raise FaceServiceError("Unable to decode image", code="INVALID_IMAGE")
	height, width = image.shape[:2]
	if min(height, width) < cfg.min_image_side:
		raise FaceServiceError("Image is too small", code="INVALID_IMAGE")
	if max(height, width) > cfg.max_image_side:
		raise FaceServiceError("Image is too large", code="INVALID_IMAGE")
	return image


def _embedding(image_bytes: bytes) -> dict[str, Any]:
	from face_service.app.services.recognition import embed_from_image

	result = embed_from_image(_engine(), _decode_image(image_bytes), allow_multiple=False)
	if not result.get("success"):
		raise FaceServiceError(
			result.get("message") or "Face image was rejected",
			code=result.get("code") or "FACE_RECOGNITION_FAILED",
			payload=result,
		)
	return result


def register_from_image(
	*,
	image_bytes: bytes,
	exclude_employee: str | None = None,
	company: str | None = None,
	settings=None,
) -> dict[str, Any]:
	from face_service.app.services import matching

	from karmavitta.face_attendance.biometric import biometric_settings
	from karmavitta.services.face_service_client import list_arcface_templates_for_company

	cfg = _settings()
	app_cfg = biometric_settings(settings)
	embed = _embedding(image_bytes)
	templates = list_arcface_templates_for_company(company)
	duplicate = matching.find_duplicate(
		embed["embedding"],
		templates,
		threshold=app_cfg["duplicate_threshold"],
		exclude_employee=exclude_employee,
		required_model=cfg.model_name,
		required_version=cfg.model_version,
		required_dim=cfg.embedding_dimension,
	)
	if duplicate:
		payload = {
			"success": False,
			"code": "DUPLICATE_FACE",
			"message": "This face is already registered with another employee. Please contact your administrator.",
			"score": duplicate["score"],
			"model_name": cfg.model_name,
			"model_version": cfg.model_version,
			"embedding_dimension": cfg.embedding_dimension,
		}
		raise FaceServiceError(payload["message"], code=payload["code"], payload=payload)

	return {
		"success": True,
		"code": "OK",
		"message": "Face embedding ready for registration",
		"embedding": embed["embedding"],
		"model_name": cfg.model_name,
		"model_version": cfg.model_version,
		"embedding_dimension": cfg.embedding_dimension,
		"template_version": cfg.template_version,
		"quality": embed.get("quality"),
	}


def verify_from_image(
	*,
	image_bytes: bytes,
	company: str | None = None,
	settings=None,
) -> dict[str, Any]:
	from face_service.app.services import matching

	from karmavitta.face_attendance.biometric import biometric_settings
	from karmavitta.services.face_service_client import list_arcface_templates_for_company

	cfg = _settings()
	app_cfg = biometric_settings(settings)
	templates = list_arcface_templates_for_company(company)
	if not templates:
		raise FaceServiceError(
			"No ArcFace biometric templates registered. Employees must register their faces.",
			"NO_ARCFACE_TEMPLATES",
		)

	embed = _embedding(image_bytes)
	match = matching.identify(
		embed["embedding"],
		templates,
		match_threshold=app_cfg["match_threshold"],
		margin=app_cfg["match_margin"],
		required_model=cfg.model_name,
		required_version=cfg.model_version,
		required_dim=cfg.embedding_dimension,
		company=company,
	)
	if not match.get("matched"):
		payload = {
			"success": False,
			"matched": False,
			"code": match.get("code") or "NO_MATCH",
			"message": match.get("message") or "Face could not be verified.",
			"score": match.get("score"),
			"model_name": cfg.model_name,
			"model_version": cfg.model_version,
		}
		raise FaceServiceError(payload["message"], code=payload["code"], payload=payload)

	return {
		"success": True,
		"matched": True,
		"employee": match["employee"],
		"score": match["score"],
		"margin": match.get("margin"),
		"code": "OK",
		"message": "Face verified",
		"model_name": cfg.model_name,
		"model_version": cfg.model_version,
		"embedding_dimension": cfg.embedding_dimension,
	}


def health(*, initialize_model: bool = False) -> dict[str, Any]:
	"""Report runtime readiness and optionally load/download the model on demand."""
	try:
		import cv2  # noqa: F401
		import insightface  # noqa: F401
		import numpy  # noqa: F401
		import onnxruntime  # noqa: F401

		from face_service.app.models.face_engine import get_face_engine

		engine = get_face_engine()
		if initialize_model and not engine.ready:
			engine.initialize_model()
		info = engine.diagnostics()
		return {
			"success": True,
			"status": "ready" if engine.ready else "dependencies_available",
			"mode": "in_process",
			"ready": engine.ready,
			"model_loaded": engine.ready,
			"message": (
				"ArcFace model loaded successfully in this Frappe worker."
				if engine.ready
				else "ArcFace packages are available. Load the model to confirm full readiness."
			),
			**info,
		}
	except Exception as exc:  # noqa: BLE001
		try:
			from face_service.app.models.face_engine import get_face_engine

			info = get_face_engine().diagnostics()
		except Exception:  # noqa: BLE001
			info = {}
		return {
			"success": False,
			"status": "error",
			"mode": "in_process",
			"model_loaded": False,
			"message": f"ArcFace runtime could not initialize: {exc}",
			**info,
		}
