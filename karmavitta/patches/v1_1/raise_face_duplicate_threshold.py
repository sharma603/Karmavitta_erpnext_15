"""Raise Face Duplicate Threshold — 0.72 still blocked different people on FaceNet."""

from __future__ import annotations

import frappe
from frappe.utils import flt


def execute():
	if not frappe.db.exists("DocType", "Face Attendance Settings"):
		return

	doc = frappe.get_single("Face Attendance Settings")
	dup = flt(getattr(doc, "face_duplicate_threshold", None) or 0)
	# Bump legacy defaults that cause false FACE_ALREADY_REGISTERED
	if dup and dup < 0.82:
		doc.face_duplicate_threshold = 0.85
		doc.save(ignore_permissions=True)
