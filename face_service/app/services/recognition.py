"""Embedding generation from images."""

from __future__ import annotations

from typing import Any

import numpy as np

from app.config import settings
from app.models.face_engine import FaceEngine
from app.services import quality


def embed_from_image(
	engine: FaceEngine,
	image_bgr: np.ndarray,
	*,
	allow_multiple: bool = False,
) -> dict[str, Any]:
	q = quality.assess_image(engine, image_bgr)
	if not q.get("success"):
		# For registration with allow_multiple, still reject multi/no face for attendance-grade embeds
		if q.get("code") == "MULTIPLE_FACES" and allow_multiple:
			pass
		else:
			return q

	faces = engine.detect_faces(image_bgr)
	if not faces:
		return {"success": False, "code": "NO_FACE", "message": "No face detected", "face_count": 0}
	if len(faces) > 1 and not allow_multiple:
		return {
			"success": False,
			"code": "MULTIPLE_FACES",
			"message": "Multiple faces detected",
			"face_count": len(faces),
		}

	# Largest face by bbox area
	def _area(f: Any) -> float:
		b = getattr(f, "bbox", None)
		if b is None or len(b) < 4:
			return 0.0
		return float((b[2] - b[0]) * (b[3] - b[1]))

	face = max(faces, key=_area)
	try:
		emb = engine.generate_embedding(face)
	except Exception as exc:  # noqa: BLE001
		return {"success": False, "code": "MODEL_ERROR", "message": "Unable to generate embedding"}

	return {
		"success": True,
		"code": "OK",
		"message": "Embedding generated",
		"embedding": emb.astype(float).tolist(),
		"model_name": settings.model_name,
		"model_version": settings.model_version,
		"embedding_dimension": settings.embedding_dimension,
		"quality": q.get("quality"),
	}
