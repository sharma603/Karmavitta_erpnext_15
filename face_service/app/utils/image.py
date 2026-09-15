"""Image decode / validation helpers."""

from __future__ import annotations

import numpy as np
from fastapi import HTTPException

from app.config import settings


def decode_upload_bytes(raw: bytes) -> np.ndarray:
	import cv2

	if not raw:
		raise HTTPException(
			status_code=400,
			detail={"success": False, "code": "INVALID_IMAGE", "message": "Empty image payload"},
		)
	arr = np.frombuffer(raw, dtype=np.uint8)
	image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
	if image is None:
		raise HTTPException(
			status_code=400,
			detail={"success": False, "code": "INVALID_IMAGE", "message": "Unable to decode image"},
		)
	h, w = image.shape[:2]
	if min(h, w) < settings.min_image_side:
		raise HTTPException(
			status_code=400,
			detail={"success": False, "code": "INVALID_IMAGE", "message": "Image too small"},
		)
	if max(h, w) > settings.max_image_side:
		raise HTTPException(
			status_code=400,
			detail={"success": False, "code": "INVALID_IMAGE", "message": "Image too large"},
		)
	return image
