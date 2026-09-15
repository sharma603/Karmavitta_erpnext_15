"""Pluggable liveness / anti-spoofing interface (stub)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class LivenessEngine(ABC):
	@abstractmethod
	def check(self, image_bgr: np.ndarray, face: Any | None = None) -> dict[str, Any]:
		"""Return {passed: bool, code: str, score: float|None}."""


class NoOpLivenessEngine(LivenessEngine):
	def check(self, image_bgr: np.ndarray, face: Any | None = None) -> dict[str, Any]:
		return {"passed": True, "code": "LIVENESS_SKIPPED", "score": None}
