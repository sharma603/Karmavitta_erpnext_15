# Copyright (c) 2026, Synergy and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class EmployeeFaceProfile(Document):
	def validate(self):
		if self.face_encoding:
			try:
				json.loads(self.face_encoding)
			except json.JSONDecodeError as exc:
				frappe.throw(f"Face Encoding must be valid JSON: {exc}")

		if self.status == "Active" and not self.face_encoding:
			frappe.throw("Face Encoding is required when status is Active")

		# One employee can only have one face profile document
		if self.employee:
			duplicate = frappe.db.exists(
				"Employee Face Profile",
				{"employee": self.employee, "name": ["!=", self.name or ""]},
			)
			if duplicate:
				frappe.throw(
					f"Face profile already exists for employee {self.employee}. "
					"Update the existing profile instead of creating a duplicate."
				)
