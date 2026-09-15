"""Raise Face Duplicate Threshold — 0.50 caused false 'already registered' for different people."""

from __future__ import annotations

import frappe
from frappe.utils import flt


def execute():
	if not frappe.db.exists("DocType", "Face Attendance Settings"):
		return

	doc = frappe.get_single("Face Attendance Settings")
	changed = False

	dup = flt(getattr(doc, "face_duplicate_threshold", None) or 0)
	# Only auto-bump clearly unsafe values (< 0.68)
	if dup < 0.68:
		doc.face_duplicate_threshold = 0.72
		changed = True

	match = flt(getattr(doc, "face_match_threshold", None) or 0)
	if match and match < 0.50:
		doc.face_match_threshold = 0.58
		changed = True

	same = flt(getattr(doc, "face_same_person_update_threshold", None) or 0)
	if same and same < 0.40:
		doc.face_same_person_update_threshold = 0.50
		changed = True

	if changed:
		doc.save(ignore_permissions=True)
