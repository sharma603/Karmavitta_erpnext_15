# Copyright (c) 2026, Synergy and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class FaceBiometric(Document):
	def validate(self):
		self.employee_name = frappe.db.get_value("Employee", self.employee, "employee_name") or self.employee
		self.company = frappe.db.get_value("Employee", self.employee, "company")

		# Only one Active+enabled template per employee (enforced in API too)
		if self.enabled and self.registration_status == "Active":
			others = frappe.get_all(
				"Face Biometric",
				filters={
					"employee": self.employee,
					"enabled": 1,
					"registration_status": "Active",
					"name": ["!=", self.name],
				},
				pluck="name",
			)
			if others:
				frappe.throw(
					"This employee already has an active biometric template. "
					"Disable or delete it before activating another.",
					frappe.ValidationError,
				)

		# Never leave empty template on Active
		if self.registration_status == "Active" and not self.biometric_template:
			frappe.throw("Active biometric requires a template", frappe.ValidationError)

		# Validate dimension matches JSON length when present
		vector = None
		if self.biometric_template:
			try:
				vector = (
					json.loads(self.biometric_template)
					if isinstance(self.biometric_template, str)
					else self.biometric_template
				)
			except Exception:
				frappe.throw("biometric_template must be valid JSON", frappe.ValidationError)
			if not isinstance(vector, list) or not vector:
				frappe.throw("biometric_template must be a non-empty JSON array", frappe.ValidationError)
			if self.embedding_dimension and len(vector) != int(self.embedding_dimension):
				frappe.throw(
					f"embedding_dimension ({self.embedding_dimension}) does not match template length ({len(vector)})",
					frappe.ValidationError,
				)

		# Server-side uniqueness: same face must not belong to another employee
		if (
			self.enabled
			and self.registration_status == "Active"
			and vector
			and len(vector) >= 64
			and not self.flags.get("skip_duplicate_face_check")
		):
			from karmavitta.face_attendance.biometric import (
				biometric_settings,
				find_duplicate_biometric,
				l2_normalize,
			)

			cfg = biometric_settings()
			normalized = l2_normalize([flt(x) for x in vector])
			dup = find_duplicate_biometric(
				normalized,
				exclude_employee=self.employee,
				threshold=cfg["duplicate_threshold"],
			)
			if dup and dup.get("employee"):
				# Privacy: do not name the matched employee
				score = flt(dup.get("score"))
				frappe.throw(
					"This face looks too similar to another registered employee "
					f"(match score {score:.2f}). If this is a different person, retry "
					"with a clearer straight-on photo.",
					frappe.ValidationError,
				)
