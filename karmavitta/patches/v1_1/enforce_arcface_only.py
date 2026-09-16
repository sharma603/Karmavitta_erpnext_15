"""Enforce ArcFace-only — remove FaceNet backend (migrate after FaceNet removal)."""

from __future__ import annotations

import frappe


def execute():
	if not frappe.db.exists("DocType", "Face Attendance Settings"):
		return
	doc = frappe.get_single("Face Attendance Settings")
	changed = False
	if getattr(doc, "recognition_backend", None) != "arcface_service":
		doc.db_set("recognition_backend", "arcface_service", update_modified=False)
		changed = True
	if (getattr(doc, "biometric_model_name", None) or "").lower() != "arcface":
		doc.db_set("biometric_model_name", "ArcFace", update_modified=False)
		changed = True
	if getattr(doc, "biometric_model_version", None) != "insightface-buffalo_l-1.0":
		doc.db_set("biometric_model_version", "insightface-buffalo_l-1.0", update_modified=False)
		changed = True
	from frappe.utils import cint
	if cint(getattr(doc, "biometric_embedding_dimension", None)) != 512:
		doc.db_set("biometric_embedding_dimension", 512, update_modified=False)
		changed = True
	if getattr(doc, "face_similarity_metric", None) != "cosine":
		doc.db_set("face_similarity_metric", "cosine", update_modified=False)
		changed = True
	if not getattr(doc, "face_service_url", None):
		doc.db_set("face_service_url", "http://127.0.0.1:8090", update_modified=False)
		changed = True
	# Thresholds
	for field, val in [
		("face_match_threshold", 0.40),
		("face_duplicate_threshold", 0.45),
		("min_face_match_score", 0.40),
	]:
		cur = getattr(doc, field, None)
		try:
			cur_f = float(cur) if cur is not None else 0
		except Exception:
			cur_f = 0
		# Old FaceNet scale was >=0.65 ; ArcFace is ~0.40
		if cur_f >= 0.65 or cur_f == 0:
			doc.db_set(field, val, update_modified=False)
			changed = True
	if changed:
		frappe.logger("karmavitta").info("Enforced ArcFace-only settings")
