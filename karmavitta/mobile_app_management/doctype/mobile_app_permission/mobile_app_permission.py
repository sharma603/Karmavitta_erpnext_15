from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from karmavitta.api.mobile_permissions import _get_mobile_screen_registry, validate_mobile_permission_rule


class MobileAppPermission(Document):
	def validate(self):
		self._validate_scope()
		self._validate_unique_profile()
		self._validate_rules()
		self._validate_screens()

	def _validate_scope(self):
		# Screen-based profiles are user-scoped. The custom screen picker does not
		# expose the legacy Applies To field, so normalize it before applying the
		# existing scope and uniqueness checks.
		if not self.applies_to and self.user and not self.role:
			self.applies_to = "User"

		if self.applies_to == "User":
			if not self.user or self.role:
				frappe.throw(_("Select one ERPNext User and leave Role empty."))
			user = frappe.db.get_value("User", self.user, ["enabled", "user_type"], as_dict=True)
			if not user or not user.enabled or user.user_type != "System User":
				frappe.throw(_("Select an enabled ERPNext System User."))
		elif self.applies_to == "Role":
			if not self.role or self.user:
				frappe.throw(_("Select one ERPNext Role and leave User empty."))
		else:
			frappe.throw(_("Applies To must be User or Role."))

	def _validate_unique_profile(self):
		field = "user" if self.applies_to == "User" else "role"
		profiles = frappe.get_all(
			"Mobile App Permission",
			filters={"applies_to": self.applies_to, field: self.get(field)},
			fields=["name", "company"],
			limit_page_length=0,
		)
		company = self.company or None
		if any(
			profile.name != self.name and (profile.company or None) == company
			for profile in profiles
		):
			frappe.throw(_("A mobile permission profile already exists for this {0} and company.").format(self.applies_to))
		if self.applies_to == "User" and self.screens:
			for profile in profiles:
				if profile.name == self.name:
					continue
				if frappe.db.count(
					"Mobile App Permission Screen",
					{"parent": profile.name, "parenttype": "Mobile App Permission", "parentfield": "screens"},
				):
					frappe.throw(_("A screen permission configuration already exists for this user."))

	def _validate_rules(self):
		seen = set()
		for row in self.rules or []:
			validate_mobile_permission_rule(row.target_type, row.target_key)
			key = (row.target_type, row.target_key)
			if key in seen:
				frappe.throw(_("Duplicate mobile permission rule: {0}.").format(row.target_key))
			seen.add(key)

	def _validate_screens(self):
		items = _get_mobile_screen_registry()
		registry = {item["key"]: item for item in items}
		sort_order = {item["key"]: index for index, item in enumerate(items)}
		seen = set()
		for row in self.screens or []:
			item = registry.get(row.screen_name)
			if not item:
				frappe.throw(_("Unknown mobile screen: {0}.").format(row.screen_name))
			if row.screen_name in seen:
				frappe.throw(_("Duplicate mobile screen: {0}.").format(row.screen_name))
			seen.add(row.screen_name)
			row.screen_label = item["label"]
			row.module = item["module_label"]
			row.sort_order = sort_order[row.screen_name]

	def on_update(self):
		_bump_mobile_permission_version()

	def on_trash(self):
		_bump_mobile_permission_version()


def _bump_mobile_permission_version():
	if not frappe.db.exists("DocType", "Mobile App Settings"):
		return
	version = int(frappe.db.get_single_value("Mobile App Settings", "permission_version") or 0)
	frappe.db.set_single_value("Mobile App Settings", "permission_version", version + 1)
	frappe.clear_cache(doctype="Mobile App Settings")
	frappe.cache().delete_value("karmavitta_mobile_permissions")
