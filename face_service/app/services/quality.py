"""Face quality checks before embedding."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from app.config import settings
from app.models.face_engine import FaceEngine


def assess_image(engine: FaceEngine, image_bgr: np.ndarray) -> dict[str, Any]:
	faces = engine.detect_faces(image_bgr)
	if not faces:
		return {
			"success": False,
			"code": "NO_FACE",
			"message": "No face detected",
			"face_count": 0,
		}
	if len(faces) > 1:
		return {
			"success": False,
			"code": "MULTIPLE_FACES",
			"message": "Multiple faces detected",
			"face_count": len(faces),
		}

	face = faces[0]
	bbox = getattr(face, "bbox", None)
	face_w = face_h = 0
	if bbox is not None and len(bbox) >= 4:
		face_w = float(bbox[2] - bbox[0])
		face_h = float(bbox[3] - bbox[1])
	if min(face_w, face_h) < settings.min_face_pixels:
		return {
			"success": False,
			"code": "FACE_TOO_SMALL",
			"message": "Face is too small",
			"face_count": 1,
			"quality": {"face_width": face_w, "face_height": face_h},
		}

	gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
	blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
	brightness = float(np.mean(gray))
	det_score = float(getattr(face, "det_score", 0.0) or 0.0)

	if blur < settings.blur_variance_min:
		return {
			"success": False,
			"code": "LOW_QUALITY",
			"message": "Image is too blurry",
			"face_count": 1,
			"quality": {"blur_variance": blur, "brightness": brightness, "det_score": det_score},
		}
	if brightness < 30 or brightness > 240:
		return {
			"success": False,
			"code": "LOW_QUALITY",
			"message": "Poor lighting",
			"face_count": 1,
			"quality": {"blur_variance": blur, "brightness": brightness, "det_score": det_score},
		}
	if det_score and det_score < 0.5:
		return {
			"success": False,
			"code": "LOW_QUALITY",
			"message": "Low face detection confidence",
			"face_count": 1,
			"quality": {"blur_variance": blur, "brightness": brightness, "det_score": det_score},
		}

	return {
		"success": True,
		"code": "OK",
		"message": "Face quality acceptable",
		"face_count": 1,
		"quality": {
			"blur_variance": round(blur, 2),
			"brightness": round(brightness, 2),
			"det_score": round(det_score, 4),
			"face_width": round(face_w, 1),
			"face_height": round(face_h, 1),
		},
	}
