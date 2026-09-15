"""Prepare ArcFace migration metadata — does NOT disable working FaceNet templates.

FaceNet and ArcFace live in incompatible vector spaces. When Recognition Backend
is switched to arcface_service, FaceNet templates are ignored by matching.
Employees must re-register faces with ArcFace images.
"""

from __future__ import annotations

import frappe


def execute():
	if not frappe.db.exists("DocType", "Face Attendance Settings"):
		return

	# Ensure new fields exist after migrate; keep facenet_local until admin enables service
	doc = frappe.get_single("Face Attendance Settings")
	if not getattr(doc, "recognition_backend", None):
		doc.db_set("recognition_backend", "facenet_local", update_modified=False)

	# Count legacy templates for ops visibility (no embedding data logged)
	legacy = frappe.db.count(
		"Face Biometric",
		{
			"enabled": 1,
			"registration_status": "Active",
			"model_name": ["in", ["FaceNet", "facenet", ""]],
		},
	)
	frappe.logger("karmavitta").info(
		f"ArcFace migration prepare: {legacy} active FaceNet templates remain "
		"(ignored once recognition_backend=arcface_service)"
	)
