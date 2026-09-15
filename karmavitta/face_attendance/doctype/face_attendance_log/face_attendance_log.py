# Copyright (c) 2026, Synergy and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from karmavitta.face_attendance.hr_sync import sync_face_log_to_hrms


class FaceAttendanceLog(Document):
	def before_insert(self):
		if not self.log_time:
			self.log_time = now_datetime()

	def validate(self):
		settings = frappe.get_cached_doc("Face Attendance Settings")
		if not settings.enabled:
			frappe.throw("Face Attendance is disabled in settings")

		self._validate_daily_limit(settings)

	def after_insert(self):
		# Sync to HRMS Employee Checkin + Attendance (best-effort)
		sync_face_log_to_hrms(self)

	def _validate_daily_limit(self, settings):
		if not settings.max_checkins_per_day:
			return

		count = frappe.db.count(
			"Face Attendance Log",
			{
				"employee": self.employee,
				"log_time": [">=", getdate(self.log_time)],
			},
		)
		# Current row is not committed yet in some paths; allow == limit - 0 after insert check
		# Count includes rows already saved; this insert is not counted yet.
		if count >= settings.max_checkins_per_day:
			frappe.throw(
				f"Daily check-in limit ({settings.max_checkins_per_day}) reached for this employee"
			)
