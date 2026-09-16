# Copyright (c) 2026, Synergy and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint, random_string


class FaceAttendanceSettings(Document):
	def validate(self):
		if not self.mobile_api_key:
			self.mobile_api_key = random_string(32)

		# ── High-level ArcFace enforcement ──
		if getattr(self, "recognition_backend", None) != "arcface_service":
			self.recognition_backend = "arcface_service"
		if getattr(self, "biometric_model_name", None) not in (None, "", "ArcFace"):
			if (self.biometric_model_name or "").lower() != "arcface":
				self.biometric_model_name = "ArcFace"
		if getattr(self, "biometric_model_version", None) not in (None, "", "insightface-buffalo_l-1.0"):
			if "arcface" not in (self.biometric_model_version or "").lower() and "insightface" not in (self.biometric_model_version or "").lower():
				self.biometric_model_version = "insightface-buffalo_l-1.0"
		if cint(getattr(self, "biometric_embedding_dimension", None)) != 512:
			self.biometric_embedding_dimension = 512
		if getattr(self, "face_similarity_metric", None) != "cosine":
			self.face_similarity_metric = "cosine"

		# ── High-level threshold hardening (ArcFace scale 0.35–0.60) ──
		if self.min_face_match_score is not None:
			self.min_face_match_score = max(0.0, min(float(self.min_face_match_score), 1.0))
			if float(self.min_face_match_score) < 0.35:
				self.min_face_match_score = 0.40
			if float(self.min_face_match_score) > 0.60:
				self.min_face_match_score = 0.40

		if getattr(self, "face_match_threshold", None) is not None:
			self.face_match_threshold = max(0.0, min(float(self.face_match_threshold), 1.0))
			if float(self.face_match_threshold) < 0.35:
				self.face_match_threshold = 0.40
			if float(self.face_match_threshold) > 0.60:
				self.face_match_threshold = 0.40

		if getattr(self, "face_duplicate_threshold", None) is not None:
			self.face_duplicate_threshold = max(0.0, min(float(self.face_duplicate_threshold), 1.0))
			if float(self.face_duplicate_threshold) < 0.35:
				self.face_duplicate_threshold = 0.45
			if float(self.face_duplicate_threshold) > 0.65:
				self.face_duplicate_threshold = 0.45

		if getattr(self, "face_same_person_update_threshold", None) is not None:
			self.face_same_person_update_threshold = max(0.0, min(float(self.face_same_person_update_threshold), 1.0))

		# ── High-level service validation ──
		if getattr(self, "face_service_url", None):
			url = str(self.face_service_url).strip()
			if not (url.startswith("http://") or url.startswith("https://")):
				frappe.throw("Face Service URL must start with http:// or https:// (e.g. http://127.0.0.1:8090)")
			# normalize
			self.face_service_url = url.rstrip("/")
		elif self.recognition_backend == "arcface_service":
			frappe.throw("Face Service URL is required for ArcFace backend")

		if getattr(self, "face_service_timeout_seconds", None) is not None:
			self.face_service_timeout_seconds = max(5, min(int(self.face_service_timeout_seconds), 120))

		if getattr(self, "face_service_api_key", None):
			key = str(self.face_service_api_key).strip()
			if len(key) < 16:
				frappe.throw("Face Service API Key must be at least 16 characters (32 recommended)")
		elif self.recognition_backend == "arcface_service" and not self.is_new():
			# allow empty on first insert; enforce after
			pass

		# ── High-level mobile / geofence / HR defaults ──
		if self.min_minutes_between_checkin_checkout is not None:
			self.min_minutes_between_checkin_checkout = max(
				0, int(self.min_minutes_between_checkin_checkout)
			)
		if getattr(self, "geofence_radius_meters", None) is not None:
			self.geofence_radius_meters = max(100, min(int(self.geofence_radius_meters), 5000))
		if getattr(self, "max_checkins_per_day", None) is not None:
			self.max_checkins_per_day = max(1, min(int(self.max_checkins_per_day), 100))

		# Enforce enterprise security defaults
		if not getattr(self, "mobile_api_key", None):
			self.mobile_api_key = random_string(32)


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
