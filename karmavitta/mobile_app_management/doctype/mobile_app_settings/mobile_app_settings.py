from __future__ import annotations

import frappe
from frappe.model.document import Document


class MobileAppSettings(Document):
	def validate(self):
		self.app_name = (self.app_name or "Karmavitta").strip()[:140]
		self.permission_version = max(1, int(self.permission_version or 1))
		self.session_timeout_minutes = max(5, min(1440, int(self.session_timeout_minutes or 60)))

	def on_update(self):
		previous = self.get_doc_before_save()
		if not previous:
			return
		tracked_fields = (
			"app_name",
			"enabled",
			"default_allow_mobile_access",
			"default_landing_screen",
			"allow_offline_mode",
			"session_timeout_minutes",
			"force_permission_refresh",
		)
		if any(previous.get(field) != self.get(field) for field in tracked_fields):
			from karmavitta.mobile_app_management.doctype.mobile_app_permission.mobile_app_permission import (
				_bump_mobile_permission_version,
			)

			_bump_mobile_permission_version()
