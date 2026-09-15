"""Unit tests for matching — no InsightFace model download required."""

from __future__ import annotations

import math

import numpy as np

from app.services.matching import cosine, find_duplicate, identify


def _unit(seed: int, dim: int = 512) -> list[float]:
	raw = [math.sin((seed + 1) * (i + 1) * 0.113) for i in range(dim)]
	v = np.asarray(raw, dtype=np.float32)
	v = v / np.linalg.norm(v)
	return v.astype(float).tolist()


def test_cosine_self():
	a = _unit(1)
	assert cosine(np.array(a), np.array(a)) > 0.999


def test_face_a_returns_employee_a():
	va, vb = _unit(1), _unit(99)
	templates = [
		{"employee": "HR-EMP-00001", "embedding": va, "model_name": "ArcFace", "model_version": "insightface-buffalo_l-1.0", "embedding_dimension": 512},
		{"employee": "HR-EMP-00002", "embedding": vb, "model_name": "ArcFace", "model_version": "insightface-buffalo_l-1.0", "embedding_dimension": 512},
	]
	probe = (np.array(va) + 0.001)
	probe = (probe / np.linalg.norm(probe)).tolist()
	r = identify(
		probe,
		templates,
		match_threshold=0.3,
		margin=0.05,
		required_model="ArcFace",
		required_version="insightface-buffalo_l-1.0",
		required_dim=512,
	)
	assert r["matched"] and r["employee"] == "HR-EMP-00001"


def test_face_b_returns_employee_b():
	va, vb = _unit(1), _unit(99)
	templates = [
		{"employee": "HR-EMP-00001", "embedding": va, "model_name": "ArcFace", "model_version": "insightface-buffalo_l-1.0", "embedding_dimension": 512},
		{"employee": "HR-EMP-00002", "embedding": vb, "model_name": "ArcFace", "model_version": "insightface-buffalo_l-1.0", "embedding_dimension": 512},
	]
	probe = (np.array(vb) + 0.001)
	probe = (probe / np.linalg.norm(probe)).tolist()
	r = identify(
		probe,
		templates,
		match_threshold=0.3,
		margin=0.05,
		required_model="ArcFace",
		required_version="insightface-buffalo_l-1.0",
		required_dim=512,
	)
	assert r["matched"] and r["employee"] == "HR-EMP-00002"


def test_unknown_no_match():
	va, vb, u = _unit(1), _unit(99), _unit(7)
	templates = [
		{"employee": "HR-EMP-00001", "embedding": va, "model_name": "ArcFace", "model_version": "insightface-buffalo_l-1.0", "embedding_dimension": 512},
		{"employee": "HR-EMP-00002", "embedding": vb, "model_name": "ArcFace", "model_version": "insightface-buffalo_l-1.0", "embedding_dimension": 512},
	]
	r = identify(
		u,
		templates,
		match_threshold=0.85,
		margin=0.05,
		required_model="ArcFace",
		required_version="insightface-buffalo_l-1.0",
		required_dim=512,
	)
	assert not r["matched"]
	assert r["code"] == "NO_MATCH"


def test_duplicate_rejected():
	va = _unit(1)
	templates = [
		{"employee": "HR-EMP-00001", "embedding": va, "model_name": "ArcFace", "model_version": "insightface-buffalo_l-1.0", "embedding_dimension": 512},
	]
	dup = find_duplicate(
		va,
		templates,
		threshold=0.4,
		exclude_employee="HR-EMP-00002",
		required_model="ArcFace",
		required_version="insightface-buffalo_l-1.0",
		required_dim=512,
	)
	assert dup is not None


def test_facenet_template_not_compared():
	va = _unit(1)
	templates = [
		{"employee": "HR-EMP-00001", "embedding": va, "model_name": "FaceNet", "model_version": "1.0", "embedding_dimension": 512},
	]
	r = identify(
		va,
		templates,
		match_threshold=0.1,
		margin=0.01,
		required_model="ArcFace",
		required_version="insightface-buffalo_l-1.0",
		required_dim=512,
	)
	assert not r["matched"]


def test_company_scope():
	va, vb = _unit(1), _unit(99)
	templates = [
		{"employee": "A1", "embedding": va, "model_name": "ArcFace", "model_version": "insightface-buffalo_l-1.0", "embedding_dimension": 512, "company": "CoA"},
		{"employee": "B1", "embedding": vb, "model_name": "ArcFace", "model_version": "insightface-buffalo_l-1.0", "embedding_dimension": 512, "company": "CoB"},
	]
	r = identify(
		va,
		templates,
		match_threshold=0.3,
		margin=0.05,
		required_model="ArcFace",
		required_version="insightface-buffalo_l-1.0",
		required_dim=512,
		company="CoA",
	)
	assert r["matched"] and r["employee"] == "A1"
