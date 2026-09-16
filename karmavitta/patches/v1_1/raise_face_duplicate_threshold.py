"""Legacy threshold fix — now ArcFace-only, keep as no-op for ArcFace values."""

from __future__ import annotations

import frappe
from frappe.utils import flt


def execute():
	if not frappe.db.exists("DocType", "Face Attendance Settings"):
		return

	doc = frappe.get_single("Face Attendance Settings")
	dup = flt(getattr(doc, "face_duplicate_threshold", None) or 0)
	# Only bump old legacy-scale values that cause false FACE_ALREADY_REGISTERED.
	# ArcFace uses 0.40-0.50, so skip those.
	if dup and 0.60 <= dup < 0.82:
		doc.face_duplicate_threshold = 0.85
		doc.save(ignore_permissions=True)
