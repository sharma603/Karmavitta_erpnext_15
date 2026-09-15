"""Cosine matching — Top-1 / Top-2 with threshold + margin. No identity leakage."""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from app.config import settings


def parse_templates_json(raw: str, company: str | None = None) -> list[dict[str, Any]]:
	try:
		data = json.loads(raw)
	except Exception as exc:  # noqa: BLE001
		raise ValueError(f"Invalid templates_json: {exc}") from exc
	if not isinstance(data, list):
		raise ValueError("templates_json must be a JSON list")
	return _filter_templates(data, company=company)


def _filter_templates(
	templates: list[dict[str, Any]],
	*,
	company: str | None = None,
) -> list[dict[str, Any]]:
	out = []
	for row in templates:
		if not row.get("enabled", True):
			continue
		if company and row.get("company") and str(row.get("company")) != str(company):
			continue
		emp = (row.get("employee") or "").strip()
		emb = row.get("embedding")
		if not emp or not isinstance(emb, list) or not emb:
			continue
		out.append(row)
	return out


def _compatible(row: dict[str, Any], required_model: str, required_version: str, required_dim: int) -> bool:
	"""Never compare FaceNet with ArcFace (or mismatched dims)."""
	model = (row.get("model_name") or "").strip()
	version = (row.get("model_version") or "").strip()
	dim = int(row.get("embedding_dimension") or len(row.get("embedding") or []))
	if dim != required_dim:
		return False
	# Require ArcFace family; reject legacy FaceNet
	if model and model.lower() not in {required_model.lower(), "arcface", "insightface"}:
		return False
	if version and required_version and version != required_version:
		# Allow same model_name with matching pack prefix
		if not version.startswith("insightface") and version != required_version:
			return False
	return True


def cosine(a: np.ndarray, b: np.ndarray) -> float:
	a = np.asarray(a, dtype=np.float32).reshape(-1)
	b = np.asarray(b, dtype=np.float32).reshape(-1)
	n = min(a.size, b.size)
	if n <= 0:
		return -1.0
	a = a[:n]
	b = b[:n]
	na = float(np.linalg.norm(a))
	nb = float(np.linalg.norm(b))
	if na <= 1e-12 or nb <= 1e-12:
		return -1.0
	return float(np.dot(a, b) / (na * nb))


def find_duplicate(
	probe: list[float],
	templates: list[dict[str, Any]],
	*,
	threshold: float,
	exclude_employee: str | None,
	required_model: str,
	required_version: str,
	required_dim: int,
) -> dict[str, Any] | None:
	probe_v = np.asarray(probe, dtype=np.float32)
	best_score = -1.0
	for row in templates:
		emp = (row.get("employee") or "").strip()
		if exclude_employee and emp == exclude_employee:
			continue
		if not _compatible(row, required_model, required_version, required_dim):
			continue
		score = cosine(probe_v, np.asarray(row["embedding"], dtype=np.float32))
		if score > best_score:
			best_score = score
		if score >= threshold:
			# Do not reveal which employee
			return {"score": round(score, 4)}
	return None


def identify(
	probe: list[float],
	templates: list[dict[str, Any]],
	*,
	match_threshold: float,
	margin: float,
	required_model: str,
	required_version: str,
	required_dim: int,
	company: str | None = None,
) -> dict[str, Any]:
	templates = _filter_templates(templates, company=company)
	probe_v = np.asarray(probe, dtype=np.float32)

	scored: list[tuple[str, float]] = []
	for row in templates:
		if not _compatible(row, required_model, required_version, required_dim):
			continue
		emp = (row.get("employee") or "").strip()
		score = cosine(probe_v, np.asarray(row["embedding"], dtype=np.float32))
		scored.append((emp, score))

	if not scored:
		return {
			"matched": False,
			"code": "NO_MATCH",
			"message": "No compatible biometric templates available",
		}

	scored.sort(key=lambda x: x[1], reverse=True)
	best_emp, best_score = scored[0]
	second_score = scored[1][1] if len(scored) > 1 else -1.0
	gap = best_score - second_score if second_score >= 0 else best_score

	if best_score < match_threshold:
		return {
			"matched": False,
			"code": "NO_MATCH",
			"message": "Face could not be verified.",
			"score": round(best_score, 4),
		}
	if len(scored) > 1 and gap < margin:
		return {
			"matched": False,
			"code": "LOW_CONFIDENCE",
			"message": "Face match is ambiguous.",
			"score": round(best_score, 4),
		}

	return {
		"matched": True,
		"employee": best_emp,
		"score": round(best_score, 4),
		"margin": round(gap, 4),
		"code": "OK",
	}
