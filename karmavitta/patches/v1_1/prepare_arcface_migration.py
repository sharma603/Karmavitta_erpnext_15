"""Migrate to ArcFace-only — remove legacy backend.

ArcFace is now the only supported backend. This patch enforces
recognition_backend=arcface_service and updates thresholds.
Employees with legacy templates must re-register.
"""

from __future__ import annotations

import frappe


def execute():
	if not frappe.db.exists("DocType", "Face Attendance Settings"):
		return

	doc = frappe.get_single("Face Attendance Settings")
	# Enforce ArcFace-only
	doc.db_set("recognition_backend", "arcface_service", update_modified=False)
	if (getattr(doc, "biometric_model_name", None) or "").lower() != "arcface":
		doc.db_set("biometric_model_name", "ArcFace", update_modified=False)
	if (getattr(doc, "biometric_model_version", None) or "") not in ("insightface-buffalo_l-1.0",):
		doc.db_set("biometric_model_version", "insightface-buffalo_l-1.0", update_modified=False)
	# Update thresholds to ArcFace defaults if still on legacy values
	if (doc.face_match_threshold or 0) >= 0.68:
		doc.db_set("face_match_threshold", 0.40, update_modified=False)
	if (doc.face_duplicate_threshold or 0) >= 0.80:
		doc.db_set("face_duplicate_threshold", 0.45, update_modified=False)
	if (doc.min_face_match_score or 0) >= 0.68:
		doc.db_set("min_face_match_score", 0.40, update_modified=False)

	# Count legacy (non-ArcFace) templates for ops visibility
	legacy = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabFace Biometric`
		WHERE enabled=1 AND registration_status='Active'
		  AND LOWER(IFNULL(model_name,'')) NOT LIKE '%%arcface%%'
		"""
	)[0][0]
	if legacy:
		frappe.logger("karmavitta").info(
			f"ArcFace migration: {legacy} legacy templates remain (require re-registration)"
		)
