# Copyright (c) 2026, Synergy and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import random_string


class FaceAttendanceSettings(Document):
	def validate(self):
		if not self.mobile_api_key:
			self.mobile_api_key = random_string(32)

		if self.min_face_match_score is not None:
			self.min_face_match_score = max(0.0, min(float(self.min_face_match_score), 1.0))
			# Prevent Desk values that accept wrong people (FaceNet impostors ~0.55–0.65)
			if float(self.min_face_match_score) < 0.68:
				self.min_face_match_score = 0.70

		if getattr(self, "face_match_threshold", None) is not None:
			self.face_match_threshold = max(0.0, min(float(self.face_match_threshold), 1.0))
			if float(self.face_match_threshold) < 0.68:
				self.face_match_threshold = 0.70

		if self.min_minutes_between_checkin_checkout is not None:
			self.min_minutes_between_checkin_checkout = max(
				0, int(self.min_minutes_between_checkin_checkout)
			)


def _require_settings_write():
	if not frappe.has_permission("Face Attendance Settings", "write"):
		frappe.throw("Not permitted", frappe.PermissionError)


@frappe.whitelist()
def get_mobile_api_key():
	"""Return plaintext Mobile API Key for authorized Desk users (download / reveal)."""
	_require_settings_write()
	doc = frappe.get_single("Face Attendance Settings")
	key = (doc.mobile_api_key or "").strip()
	if not key:
		key = random_string(32)
		doc.mobile_api_key = key
		doc.save(ignore_permissions=True)
		frappe.clear_cache()
	return {"mobile_api_key": key}


@frappe.whitelist()
def regenerate_mobile_api_key():
	"""Generate a new Mobile API Key. Old key stops working immediately."""
	_require_settings_write()
	doc = frappe.get_single("Face Attendance Settings")
	new_key = random_string(32)
	doc.mobile_api_key = new_key
	doc.save(ignore_permissions=True)
	frappe.clear_cache()
	frappe.msgprint(
		"New Mobile API Key generated. Update mobile devices that still use the old key.",
		indicator="orange",
		alert=True,
	)
	return {"mobile_api_key": new_key}
