"""InsightFace / ArcFace face engine — loaded once at process start."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import numpy as np

from app.config import settings

logger = logging.getLogger("karmavritta.face_engine")


class FaceEngine:
	def __init__(self) -> None:
		self._app = None
		self._lock = threading.RLock()
		self._ready = False
		self._init_error: str | None = None
		self._last_inference_ms: float | None = None
		self._inference_count = 0

	@property
	def ready(self) -> bool:
		return self._ready

	def initialize_model(self) -> None:
		with self._lock:
			if self._ready:
				return
			try:
				from insightface.app import FaceAnalysis

				providers = [settings.onnx_provider]
				# Fallback CPU if CUDA requested but unavailable
				if settings.onnx_provider == "CUDAExecutionProvider":
					providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

				app = FaceAnalysis(
					name=settings.insightface_model_pack,
					providers=providers,
				)
				app.prepare(ctx_id=settings.ctx_id, det_size=settings.det_size)
				self._app = app
				self._ready = True
				self._init_error = None
				logger.info(
					"FaceEngine ready model_pack=%s providers=%s dim=%s",
					settings.insightface_model_pack,
					providers,
					settings.embedding_dimension,
				)
			except Exception as exc:  # noqa: BLE001
				self._ready = False
				self._init_error = str(exc)
				logger.exception("FaceEngine failed to initialize")
				raise

	def shutdown(self) -> None:
		with self._lock:
			self._app = None
			self._ready = False

	def detect_faces(self, image_bgr: np.ndarray) -> list[Any]:
		self._ensure_ready()
		started = time.perf_counter()
		# InsightFace FaceAnalysis.get is thread-aware enough for read-only inference;
		# serialize to be safe across concurrent requests on some ONNX builds.
		with self._lock:
			faces = self._app.get(image_bgr)
		self._last_inference_ms = (time.perf_counter() - started) * 1000
		self._inference_count += 1
		return list(faces or [])

	def generate_embedding(self, face: Any) -> np.ndarray:
		"""Return L2-normalized ArcFace embedding from an InsightFace face object."""
		emb = getattr(face, "normed_embedding", None)
		if emb is None:
			raw = getattr(face, "embedding", None)
			if raw is None:
				raise ValueError("Face object has no embedding")
			emb = self.normalize_embedding(np.asarray(raw, dtype=np.float32))
		else:
			emb = np.asarray(emb, dtype=np.float32)
		return self.validate_embedding(emb)

	def normalize_embedding(self, embedding: np.ndarray) -> np.ndarray:
		vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
		norm = float(np.linalg.norm(vec))
		if norm <= 1e-12:
			raise ValueError("Invalid embedding: zero norm")
		return (vec / norm).astype(np.float32)

	def validate_embedding(self, embedding: np.ndarray) -> np.ndarray:
		vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
		if vec.shape[0] != settings.embedding_dimension:
			raise ValueError(
				f"embedding_dimension mismatch: got {vec.shape[0]}, expected {settings.embedding_dimension}"
			)
		if not np.isfinite(vec).all():
			raise ValueError("Invalid embedding: NaN or Infinity")
		norm = float(np.linalg.norm(vec))
		if abs(norm - 1.0) > 0.05:
			vec = self.normalize_embedding(vec)
		return vec.astype(np.float32)

	def diagnostics(self) -> dict[str, Any]:
		providers: list[str] = []
		try:
			import onnxruntime as ort

			providers = list(ort.get_available_providers())
		except Exception:  # noqa: BLE001
			providers = []
		device = "GPU" if "CUDAExecutionProvider" in providers and settings.ctx_id >= 0 else "CPU"
		return {
			"ready": self._ready,
			"init_error": self._init_error,
			"model_name": settings.model_name,
			"model_version": settings.model_version,
			"insightface_model_pack": settings.insightface_model_pack,
			"embedding_dimension": settings.embedding_dimension,
			"template_version": settings.template_version,
			"onnx_providers": providers,
			"configured_provider": settings.onnx_provider,
			"device": device,
			"det_size": list(settings.det_size),
			"inference_count": self._inference_count,
			"last_inference_ms": self._last_inference_ms,
			# Never include embeddings
		}

	def _ensure_ready(self) -> None:
		if not self._ready or self._app is None:
			raise RuntimeError(self._init_error or "FaceEngine not initialized")


_ENGINE: FaceEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_face_engine() -> FaceEngine:
	global _ENGINE
	with _ENGINE_LOCK:
		if _ENGINE is None:
			_ENGINE = FaceEngine()
		return _ENGINE
