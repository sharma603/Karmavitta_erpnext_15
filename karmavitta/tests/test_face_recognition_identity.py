"""Two-employee safety tests for 1:N face recognition identity.

Uses synthetic L2-normalized vectors (no real face images / embeddings from production).
"""

from __future__ import annotations

import math
import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from karmavitta.face_attendance.biometric import (
	cosine_similarity,
	l2_normalize,
	recognize_employee_from_embedding,
)


def _unit_vector(seed: int, dim: int = 64) -> list[float]:
	"""Deterministic nearly-orthogonal unit vector for tests."""
	raw = [math.sin((seed + 1) * (i + 1) * 0.173) for i in range(dim)]
	return l2_normalize(raw)


class TestFaceRecognitionIdentity(FrappeTestCase):
	def test_cosine_self_is_one(self):
		v = _unit_vector(1)
		self.assertAlmostEqual(cosine_similarity(v, v), 1.0, places=5)

	def test_orthogonal_pairs_are_low(self):
		a = _unit_vector(1)
		b = _unit_vector(99)
		# Different seeds → low similarity for this construction
		self.assertLess(cosine_similarity(a, b), 0.35)

	@patch("karmavitta.face_attendance.biometric.write_audit")
	@patch("karmavitta.face_attendance.biometric._log_recognition_debug")
	@patch("frappe.db.set_value")
	@patch("frappe.get_all")
	def test_face_a_returns_employee_a(self, get_all, _set_value, _debug, _audit):
		va = _unit_vector(1)
		vb = _unit_vector(99)
		get_all.return_value = [
			frappe._dict(
				name="FB-A",
				employee="HR-EMP-00001",
				employee_name="Employee A",
				biometric_template=va,
			),
			frappe._dict(
				name="FB-B",
				employee="HR-EMP-00002",
				employee_name="Employee B",
				biometric_template=vb,
			),
		]
		# Near-perfect probe of A
		probe = l2_normalize([x + 0.001 for x in va])
		result = recognize_employee_from_embedding(probe, threshold=0.70, margin=0.10)
		self.assertTrue(result["success"])
		self.assertEqual(result["employee"], "HR-EMP-00001")

	@patch("karmavitta.face_attendance.biometric.write_audit")
	@patch("karmavitta.face_attendance.biometric._log_recognition_debug")
	@patch("frappe.db.set_value")
	@patch("frappe.get_all")
	def test_face_b_returns_employee_b(self, get_all, _set_value, _debug, _audit):
		va = _unit_vector(1)
		vb = _unit_vector(99)
		get_all.return_value = [
			frappe._dict(
				name="FB-A",
				employee="HR-EMP-00001",
				employee_name="Employee A",
				biometric_template=va,
			),
			frappe._dict(
				name="FB-B",
				employee="HR-EMP-00002",
				employee_name="Employee B",
				biometric_template=vb,
			),
		]
		probe = l2_normalize([x + 0.001 for x in vb])
		result = recognize_employee_from_embedding(probe, threshold=0.70, margin=0.10)
		self.assertTrue(result["success"])
		self.assertEqual(result["employee"], "HR-EMP-00002")

	@patch("karmavitta.face_attendance.biometric.write_audit")
	@patch("karmavitta.face_attendance.biometric._log_recognition_debug")
	@patch("frappe.get_all")
	def test_unknown_face_returns_no_employee(self, get_all, _debug, _audit):
		va = _unit_vector(1)
		vb = _unit_vector(99)
		unknown = _unit_vector(7)
		get_all.return_value = [
			frappe._dict(
				name="FB-A",
				employee="HR-EMP-00001",
				employee_name="Employee A",
				biometric_template=va,
			),
			frappe._dict(
				name="FB-B",
				employee="HR-EMP-00002",
				employee_name="Employee B",
				biometric_template=vb,
			),
		]
		result = recognize_employee_from_embedding(unknown, threshold=0.70, margin=0.10)
		self.assertFalse(result["success"])
		self.assertIsNone(result.get("employee"))
		self.assertEqual(result.get("code") or result.get("error_code"), "FACE_NOT_RECOGNIZED")

	@patch("karmavitta.face_attendance.biometric.write_audit")
	@patch("karmavitta.face_attendance.biometric._log_recognition_debug")
	@patch("frappe.get_all")
	def test_ambiguous_faces_rejected(self, get_all, _debug, _audit):
		base = _unit_vector(1)
		# Two nearly identical templates → ambiguous
		va = base
		vb = l2_normalize([x + 0.0001 for x in base])
		get_all.return_value = [
			frappe._dict(
				name="FB-A",
				employee="HR-EMP-00001",
				employee_name="Employee A",
				biometric_template=va,
			),
			frappe._dict(
				name="FB-B",
				employee="HR-EMP-00002",
				employee_name="Employee B",
				biometric_template=vb,
			),
		]
		result = recognize_employee_from_embedding(base, threshold=0.50, margin=0.10)
		self.assertFalse(result["success"])
		self.assertEqual(result.get("code") or result.get("error_code"), "FACE_AMBIGUOUS")


if __name__ == "__main__":
	unittest.main()
