"""Service configuration — thresholds must be calibrated per deployment."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
	model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

	# Auth
	face_service_api_key: str = "change-me-face-service-key"
	cors_origins: list[str] = ["*"]

	# Model — InsightFace ArcFace recognition pack (verify commercial license before shipping)
	model_name: str = "ArcFace"
	model_version: str = "insightface-buffalo_l-1.0"
	insightface_model_pack: str = "buffalo_l"
	embedding_dimension: int = 512
	template_version: str = "arcface-1"
	det_size: tuple[int, int] = (640, 640)
	ctx_id: int = -1  # -1 CPU, >=0 GPU index
	onnx_provider: str = "CPUExecutionProvider"  # or CUDAExecutionProvider

	# Matching — calibrate on real data; these are starting points for ArcFace cosine
	face_match_threshold: float = 0.40
	face_duplicate_threshold: float = 0.45
	face_match_margin: float = 0.05

	# Image limits
	max_image_bytes: int = 5 * 1024 * 1024
	min_image_side: int = 80
	max_image_side: int = 4096
	min_face_pixels: int = 80
	blur_variance_min: float = 40.0

	# Rate limit (simple in-process)
	rate_limit_per_minute: int = 120


@lru_cache
def get_settings() -> Settings:
	return Settings()


settings = get_settings()
