"""API key / payload security helpers. Never log secrets or embeddings."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import settings

_ALLOWED_TYPES = {
	"image/jpeg",
	"image/jpg",
	"image/png",
	"image/webp",
	"application/octet-stream",
}

# Simple per-process rate limit: key -> timestamps
_RATE: dict[str, deque[float]] = defaultdict(deque)


def validate_api_key(api_key: str | None) -> None:
	expected = (settings.face_service_api_key or "").strip()
	if not expected or expected == "change-me-face-service-key":
		# Still require header match against configured value
		pass
	provided = (api_key or "").strip()
	if not provided or provided != expected:
		raise HTTPException(
			status_code=401,
			detail={"success": False, "code": "UNAUTHORIZED", "message": "Invalid API key"},
		)
	_rate_limit(provided)


def check_content_type(content_type: str | None) -> None:
	ct = (content_type or "").split(";")[0].strip().lower()
	if ct and ct not in _ALLOWED_TYPES:
		raise HTTPException(
			status_code=400,
			detail={"success": False, "code": "INVALID_IMAGE", "message": f"Unsupported content type: {ct}"},
		)


def check_payload_size(nbytes: int) -> None:
	if nbytes <= 0 or nbytes > settings.max_image_bytes:
		raise HTTPException(
			status_code=400,
			detail={
				"success": False,
				"code": "INVALID_IMAGE",
				"message": f"Image size must be 1..{settings.max_image_bytes} bytes",
			},
		)


def _rate_limit(key: str) -> None:
	now = time.time()
	window = 60.0
	q = _RATE[key]
	while q and now - q[0] > window:
		q.popleft()
	if len(q) >= settings.rate_limit_per_minute:
		raise HTTPException(
			status_code=429,
			detail={"success": False, "code": "RATE_LIMITED", "message": "Too many requests"},
		)
	q.append(now)
