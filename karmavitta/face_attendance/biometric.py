"""Server-side face biometric template helpers.

Embeddings are never logged. Duplicate checks compare against ALL active templates.
"""

from __future__ import annotations

import json
import math
from typing import Any

import frappe
from frappe.utils import cint, flt, now_datetime

from karmavitta.face_attendance.utils import can_manage_employee_face, get_settings


DEFAULT_MODEL_NAME = "ArcFace"
DEFAULT_MODEL_VERSION = "insightface-buffalo_l-1.0"
DEFAULT_EMBEDDING_DIM = 512
# ArcFace cosine (InsightFace buffalo_l):
# - same person typically high, different people well separated
# Thresholds are authoritative in face_service (0.40 match / 0.45 duplicate)
# Keep local thresholds in sync but service is the source of truth for images.
DEFAULT_DUPLICATE_THRESHOLD = 0.45
DEFAULT_MATCH_THRESHOLD = 0.40
DEFAULT_MATCH_MARGIN = 0.05
DEFAULT_SAME_PERSON_UPDATE = 0.50
# Guard misconfigured Desk values that falsely reject different people
MIN_DUPLICATE_THRESHOLD = 0.40


def _ok(**kwargs):
	return {"success": True, **kwargs}


def _fail(message: str, error_code: str | None = None, **kwargs):
	payload = {"success": False, "message": message, **kwargs}
	if error_code:
		payload["error_code"] = error_code
		payload["code"] = error_code
	return payload


def biometric_settings(settings=None) -> dict[str, Any]:
	settings = settings or get_settings()
	duplicate = flt(getattr(settings, "face_duplicate_threshold", None)) or DEFAULT_DUPLICATE_THRESHOLD
	# Guard misconfigured Desk values that falsely reject different people
	if duplicate < MIN_DUPLICATE_THRESHOLD:
		duplicate = DEFAULT_DUPLICATE_THRESHOLD
	match = flt(
		getattr(settings, "face_match_threshold", None)
		or getattr(settings, "min_face_match_score", None)
	) or DEFAULT_MATCH_THRESHOLD
	# Floor match so very low Desk values cannot accept wrong people (ArcFace floor ~0.35)
	if match < 0.35:
		match = DEFAULT_MATCH_THRESHOLD
	# Also respect Minimum Face Match Score if higher
	min_score = flt(getattr(settings, "min_face_match_score", None) or 0)
	if min_score > match:
		match = min_score
	return {
		"model_name": getattr(settings, "biometric_model_name", None) or DEFAULT_MODEL_NAME,
		"model_version": getattr(settings, "biometric_model_version", None) or DEFAULT_MODEL_VERSION,
		"embedding_dimension": cint(
			getattr(settings, "biometric_embedding_dimension", None) or DEFAULT_EMBEDDING_DIM
		),
		"similarity_metric": getattr(settings, "face_similarity_metric", None) or "cosine",
		"duplicate_threshold": duplicate,
		"match_threshold": match,
		"match_margin": DEFAULT_MATCH_MARGIN,
		"same_person_update_threshold": flt(
			getattr(settings, "face_same_person_update_threshold", None)
		)
		or DEFAULT_SAME_PERSON_UPDATE,
		"liveness_provider": getattr(settings, "liveness_provider", None) or "none",
	}


def parse_template(raw) -> list[float] | None:
	if raw is None or raw == "":
		return None
	if isinstance(raw, list):
		vector = raw
	elif isinstance(raw, str):
		vector = json.loads(raw)
	else:
		return None
	if not isinstance(vector, list) or not vector:
		return None
	out = []
	for item in vector:
		out.append(flt(item))
	return out


def l2_normalize(vector: list[float]) -> list[float]:
	norm = math.sqrt(sum(x * x for x in vector))
	if norm <= 0:
		frappe.throw("Invalid embedding: zero norm", frappe.ValidationError)
	return [x / norm for x in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
	length = min(len(left), len(right))
	if length <= 0:
		return 0.0
	dot = 0.0
	for i in range(length):
		dot += left[i] * right[i]
	# Prefer pre-normalized vectors; still normalize defensively
	a = math.sqrt(sum(left[i] * left[i] for i in range(length)))
	b = math.sqrt(sum(right[i] * right[i] for i in range(length)))
	if a <= 0 or b <= 0:
		return 0.0
	return dot / (a * b)


def validate_embedding_payload(
	biometric_template,
	embedding_dimension: int | None,
	model_name: str | None,
	model_version: str | None,
	settings_cfg: dict[str, Any] | None = None,
) -> list[float]:
	cfg = settings_cfg or biometric_settings()
	expected_dim = cint(embedding_dimension) or cfg["embedding_dimension"]
	expected_model = (model_name or cfg["model_name"]).strip()
	expected_version = (model_version or cfg["model_version"]).strip()

	if expected_model != cfg["model_name"]:
		frappe.throw(
			f"Unsupported model_name '{expected_model}'. Server expects '{cfg['model_name']}'.",
			frappe.ValidationError,
		)
	if expected_version != cfg["model_version"]:
		frappe.throw(
			f"Unsupported model_version '{expected_version}'. Server expects '{cfg['model_version']}'.",
			frappe.ValidationError,
		)

	vector = parse_template(biometric_template)
	if not vector:
		frappe.throw("biometric_template is required", frappe.ValidationError)
	if len(vector) != expected_dim:
		frappe.throw(
			f"embedding_dimension mismatch: got {len(vector)}, expected {expected_dim}",
			frappe.ValidationError,
		)
	# Reject obvious non-biometric / fake vectors (all zeros, tiny length already caught)
	if all(abs(x) < 1e-12 for x in vector):
		frappe.throw("Invalid embedding", frappe.ValidationError)

	return l2_normalize(vector)


def write_audit(
	*,
	employee: str | None,
	event: str,
	result: str,
	error_code: str | None = None,
	model_name: str | None = None,
	model_version: str | None = None,
	embedding_dimension: int | None = None,
	device_id: str | None = None,
	best_score: float | None = None,
	threshold_used: float | None = None,
	remarks: str | None = None,
):
	"""Persist audit without storing embeddings or matched employee identity."""
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Face Registration Audit",
				"employee": employee,
				"employee_name": frappe.db.get_value("Employee", employee, "employee_name")
				if employee
				else None,
				"event": event,
				"result": result,
				"error_code": error_code,
				"model_name": model_name,
				"model_version": model_version,
				"embedding_dimension": embedding_dimension,
				"device_id": device_id,
				"best_score": best_score,
				"threshold_used": threshold_used,
				"actor_user": frappe.session.user if frappe.session.user != "Guest" else None,
				"event_time": now_datetime(),
				"remarks": remarks,
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		# Audit must not break registration path; do not log embedding
		frappe.log_error(title="Face Biometric Audit Failed", message=frappe.get_traceback())


def find_duplicate_biometric(
	vector: list[float],
	*,
	exclude_employee: str | None = None,
	threshold: float,
) -> dict[str, Any] | None:
	"""Compare against ALL active enabled biometrics.

	Uses direct SQL so permlevel-restricted `biometric_template` is always readable
	during the authoritative uniqueness check (mobile roles must not bypass this).

	Returns a match dict only when score >= threshold; otherwise None.
	"""
	if not vector or len(vector) < 64:
		return None

	# Floor: never treat weak/impostor-range scores as duplicates
	effective_threshold = max(flt(threshold), MIN_DUPLICATE_THRESHOLD)

	rows = frappe.db.sql(
		"""
		SELECT name, employee, biometric_template, embedding_dimension
		FROM `tabFace Biometric`
		WHERE IFNULL(enabled, 0) = 1
			AND registration_status = 'Active'
			AND biometric_template IS NOT NULL
			AND biometric_template != ''
		""",
		as_dict=True,
	)

	best = None
	best_score = -1.0
	for row in rows:
		if exclude_employee and row.employee == exclude_employee:
			continue
		other = parse_template(row.biometric_template)
		if not other or len(other) < 64:
			continue
		# Dimension mismatch → different model / corrupt row — skip
		if len(other) != len(vector):
			continue
		score = cosine_similarity(vector, other)
		if score > best_score:
			best_score = score
			best = row

	if best is not None and best_score >= effective_threshold:
		return {
			"employee": best.employee,
			"profile": best.name,
			"score": round(best_score, 4),
			"threshold_used": effective_threshold,
		}
	return None


def get_active_biometric(employee: str) -> str | None:
	return frappe.db.get_value(
		"Face Biometric",
		{"employee": employee, "enabled": 1, "registration_status": "Active"},
		"name",
	)


def register_face_biometric(
	*,
	employee: str,
	biometric_template,
	embedding_dimension: int | None = None,
	model_name: str | None = None,
	model_version: str | None = None,
	template_version: str | None = "arcface-1",
	device_id: str | None = None,
	allow_update: bool = False,
	admin_override: bool = False,
) -> dict[str, Any]:
	if not employee or not frappe.db.exists("Employee", employee):
		return _fail("Employee not found", "INVALID_EMPLOYEE")

	if not can_manage_employee_face(employee):
		write_audit(
			employee=employee,
			event="Register",
			result="Rejected",
			error_code="NOT_PERMITTED",
			device_id=device_id,
		)
		return _fail("Not permitted to register face for this employee", "NOT_PERMITTED")

	cfg = biometric_settings()
	try:
		vector = validate_embedding_payload(
			biometric_template,
			embedding_dimension,
			model_name,
			model_version,
			cfg,
		)
	except Exception as exc:
		write_audit(
			employee=employee,
			event="Register",
			result="Rejected",
			error_code="INVALID_EMBEDDING",
			device_id=device_id,
			remarks=str(exc)[:140],
		)
		return _fail(str(exc), "INVALID_EMBEDDING")

	existing_name = get_active_biometric(employee)
	existing_doc = frappe.get_doc("Face Biometric", existing_name) if existing_name else None

	# Existing employee template handling
	if existing_doc and not allow_update and not admin_override:
		own = parse_template(existing_doc.biometric_template)
		own_score = cosine_similarity(vector, own) if own else 0.0
		if own_score >= cfg["same_person_update_threshold"]:
			write_audit(
				employee=employee,
				event="Register",
				result="Rejected",
				error_code="ALREADY_REGISTERED",
				device_id=device_id,
				best_score=own_score,
				threshold_used=cfg["same_person_update_threshold"],
				model_name=cfg["model_name"],
				model_version=cfg["model_version"],
				embedding_dimension=cfg["embedding_dimension"],
			)
			return _fail(
				"Face already registered for this employee. Tap Update Face to replace it.",
				"ALREADY_REGISTERED",
				registered=True,
			)
		# Different face trying to replace without approval
		if not existing_doc.reregistration_requested:
			write_audit(
				employee=employee,
				event="Register",
				result="Rejected",
				error_code="REREGISTRATION_REQUIRED",
				device_id=device_id,
				best_score=own_score,
			)
			return _fail(
				"This employee already has a different face template. Request admin re-registration approval.",
				"REREGISTRATION_REQUIRED",
			)
		if not existing_doc.reregistration_approved_by and not admin_override:
			write_audit(
				employee=employee,
				event="Register",
				result="Rejected",
				error_code="ADMIN_APPROVAL_REQUIRED",
				device_id=device_id,
			)
			return _fail(
				"Re-registration is requested but not yet approved by an administrator.",
				"ADMIN_APPROVAL_REQUIRED",
			)

	# CRITICAL: compare against ALL other active employees (server-side)
	dup = find_duplicate_biometric(
		vector,
		exclude_employee=employee,
		threshold=cfg["duplicate_threshold"],
	)
	dup_score = (dup or {}).get("score")
	if dup and dup.get("employee"):
		write_audit(
			employee=employee,
			event="Register",
			result="Duplicate",
			error_code="FACE_ALREADY_REGISTERED",
			device_id=device_id,
			best_score=dup_score,
			threshold_used=dup.get("threshold_used") or cfg["duplicate_threshold"],
			model_name=cfg["model_name"],
			model_version=cfg["model_version"],
			embedding_dimension=cfg["embedding_dimension"],
			# Do NOT store matched employee in remarks
			remarks="Duplicate face vs another active biometric",
		)
		# Privacy: do not reveal which employee matched; include score for support
		score_txt = f"{flt(dup_score):.2f}" if dup_score is not None else "?"
		return _fail(
			"This face looks too similar to another registered employee "
			f"(match score {score_txt}). If this is a different person, retry with "
			"brighter light and a straight-on photo. If it is the same person, open "
			"their employee record and use Update Face.",
			"FACE_ALREADY_REGISTERED",
			best_score=dup_score,
			threshold_used=dup.get("threshold_used") or cfg["duplicate_threshold"],
		)

	template_json = json.dumps(vector)
	now = now_datetime()

	if existing_doc:
		doc = existing_doc
	else:
		# Soft-delete prior non-active rows for unique employee constraint safety
		prior = frappe.db.get_value("Face Biometric", {"employee": employee}, "name")
		doc = frappe.get_doc("Face Biometric", prior) if prior else frappe.new_doc(
			"Face Biometric"
		)
		if not prior:
			doc.employee = employee

	doc.biometric_template = template_json
	doc.embedding_dimension = cfg["embedding_dimension"]
	doc.model_name = cfg["model_name"]
	doc.model_version = cfg["model_version"]
	doc.template_version = template_version or "arcface-1"
	doc.registration_status = "Active"
	doc.enabled = 1
	doc.registered_device_id = device_id
	doc.updated_on = now
	if not doc.registered_on:
		doc.registered_on = now
	doc.reregistration_requested = 0
	doc.reregistration_approved_by = None
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	write_audit(
		employee=employee,
		event="Update" if existing_name else "Register",
		result="Success",
		device_id=device_id,
		best_score=dup_score,
		threshold_used=cfg["duplicate_threshold"],
		model_name=cfg["model_name"],
		model_version=cfg["model_version"],
		embedding_dimension=cfg["embedding_dimension"],
	)

	return _ok(
		employee=employee,
		profile=doc.name,
		registration_status=doc.registration_status,
		registered=True,
		updated=bool(existing_name),
		registered_on=str(doc.registered_on),
		model_name=doc.model_name,
		model_version=doc.model_version,
		embedding_dimension=doc.embedding_dimension,
	)


def _log_recognition_debug(candidates: list[tuple[str, float]], *, threshold: float, margin: float, best_emp: str | None, best_score: float, final: str | None, reason: str):
	"""Temporary debug aid — employee IDs and scores only (never embeddings/images)."""
	try:
		lines = ["Recognition request"]
		for emp, score in candidates:
			lines.append(f"Candidate: {emp}  Similarity: {round(score, 4)}")
		if candidates:
			top_emp, top_score = max(candidates, key=lambda x: x[1])
			lines.append(f"Best candidate: {top_emp}")
			lines.append(f"Best similarity: {round(top_score, 4)}")
		else:
			lines.append("Best candidate: (none)")
			lines.append("Best similarity: n/a")
		lines.append(f"Threshold: {round(threshold, 4)}")
		lines.append(f"Margin: {round(margin, 4)}")
		lines.append(f"Final employee: {final or '(none)'}")
		lines.append(f"Decision: {reason}")
		# Error Log title is searchable in Desk → Error Log
		frappe.log_error(title="Face Recognition Debug", message="\n".join(lines))
	except Exception:
		pass


def recognize_employee_from_embedding(
	vector: list[float],
	*,
	threshold: float,
	margin: float,
	device_id: str | None = None,
) -> dict[str, Any]:
	"""1:N identification — employee comes ONLY from highest valid biometric match.

	Never uses previous employee, last attendance, or client-claimed identity.
	"""
	rows = frappe.get_all(
		"Face Biometric",
		filters={"enabled": 1, "registration_status": "Active"},
		fields=["name", "employee", "employee_name", "biometric_template"],
	)

	candidates: list[tuple[str, float]] = []
	best_emp = None
	best_name = None
	best_doc = None
	best_score = -1.0
	second_score = -1.0

	for row in rows:
		other = parse_template(row.biometric_template)
		if not other:
			continue
		score = cosine_similarity(vector, other)
		candidates.append((row.employee, score))
		if score > best_score:
			second_score = best_score
			best_score = score
			best_emp = row.employee
			best_name = row.employee_name
			best_doc = row.name
		elif score > second_score:
			second_score = score

	candidates.sort(key=lambda x: x[1], reverse=True)
	scored_count = len(candidates)

	# Solo gallery: only one enrolled face — require strict score so strangers
	# are rejected as "not recognized".
	SOLO_GALLERY_FLOOR = 0.40
	effective_threshold = float(threshold)
	if scored_count == 1:
		effective_threshold = max(effective_threshold, SOLO_GALLERY_FLOOR)

	if not best_emp or best_score < effective_threshold:
		_log_recognition_debug(
			candidates,
			threshold=effective_threshold,
			margin=margin,
			best_emp=best_emp,
			best_score=best_score,
			final=None,
			reason="below_threshold_solo" if scored_count == 1 else "below_threshold",
		)
		write_audit(
			employee=None,
			event="Verify",
			result="Rejected",
			error_code="FACE_NOT_RECOGNIZED",
			device_id=device_id,
			best_score=best_score if best_score >= 0 else None,
			threshold_used=effective_threshold,
		)
		msg = "Face not recognized"
		if scored_count <= 1:
			msg = (
				"Face not recognized. If this is a new employee, register their face first. "
				"Only enrolled faces can mark attendance."
			)
		return _fail(
			msg,
			"FACE_NOT_RECOGNIZED",
			score=round(best_score, 4) if best_score >= 0 else None,
		)

	ambiguous = scored_count > 1 and second_score >= 0 and (best_score - second_score) < margin
	if ambiguous:
		_log_recognition_debug(
			candidates,
			threshold=effective_threshold,
			margin=margin,
			best_emp=best_emp,
			best_score=best_score,
			final=None,
			reason="ambiguous_margin",
		)
		write_audit(
			employee=None,
			event="Verify",
			result="Rejected",
			error_code="FACE_AMBIGUOUS",
			device_id=device_id,
			best_score=best_score,
			threshold_used=effective_threshold,
			remarks=f"best={best_emp} second_score={round(second_score, 4)}",
		)
		return _fail(
			"Face match is ambiguous between employees. Re-register faces with clearer photos.",
			"FACE_AMBIGUOUS",
			score=round(best_score, 4),
		)

	if best_doc:
		frappe.db.set_value("Face Biometric", best_doc, "last_verified", now_datetime())

	_log_recognition_debug(
		candidates,
		threshold=effective_threshold,
		margin=margin,
		best_emp=best_emp,
		best_score=best_score,
		final=best_emp,
		reason="matched",
	)
	write_audit(
		employee=best_emp,
		event="Verify",
		result="Success",
		device_id=device_id,
		best_score=best_score,
		threshold_used=effective_threshold,
	)
	return _ok(
		employee=best_emp,
		employee_name=best_name,
		score=round(best_score, 4),
		matched=True,
		similarity=round(best_score, 4),
	)


def verify_face_biometric(
	*,
	biometric_template,
	employee: str | None = None,
	embedding_dimension: int | None = None,
	model_name: str | None = None,
	model_version: str | None = None,
	device_id: str | None = None,
) -> dict[str, Any]:
	cfg = biometric_settings()
	try:
		vector = validate_embedding_payload(
			biometric_template,
			embedding_dimension,
			model_name,
			model_version,
			cfg,
		)
	except Exception as exc:
		return _fail(str(exc), "INVALID_EMBEDDING")

	threshold = cfg["match_threshold"]
	margin = flt(cfg.get("match_margin") or DEFAULT_MATCH_MARGIN)

	# Explicit 1:1 verify against a claimed employee (registration / login flows)
	if employee:
		name = get_active_biometric(employee)
		if not name:
			return _fail("No active face biometric for this employee", "NOT_REGISTERED")
		doc = frappe.get_doc("Face Biometric", name)
		other = parse_template(doc.biometric_template)
		score = cosine_similarity(vector, other) if other else 0.0
		if score < threshold:
			write_audit(
				employee=employee,
				event="Verify",
				result="Rejected",
				error_code="FACE_MISMATCH",
				device_id=device_id,
				best_score=score,
				threshold_used=threshold,
			)
			return _fail("Face did not match", "FACE_MISMATCH", score=round(score, 4))
		doc.last_verified = now_datetime()
		doc.save(ignore_permissions=True)
		write_audit(
			employee=employee,
			event="Verify",
			result="Success",
			device_id=device_id,
			best_score=score,
			threshold_used=threshold,
		)
		return _ok(
			employee=employee,
			employee_name=doc.employee_name,
			score=round(score, 4),
			matched=True,
			similarity=round(score, 4),
		)

	# Attendance / kiosk: 1:N — identity from biometrics only
	return recognize_employee_from_embedding(
		vector,
		threshold=threshold,
		margin=margin,
		device_id=device_id,
	)


def get_face_registration_status(employee: str) -> dict[str, Any]:
	if not employee:
		return _fail("Employee is required", "INVALID_EMPLOYEE")
	if not can_manage_employee_face(employee):
		return _fail("Not permitted", "NOT_PERMITTED")

	name = frappe.db.get_value("Face Biometric", {"employee": employee}, "name")
	if not name:
		return _ok(employee=employee, registered=False, registration_status=None)

	row = frappe.db.get_value(
		"Face Biometric",
		name,
		[
			"name",
			"registration_status",
			"enabled",
			"registered_on",
			"model_name",
			"model_version",
			"embedding_dimension",
			"reregistration_requested",
			"reregistration_approved_by",
		],
		as_dict=True,
	)
	# Never return biometric_template
	registered = bool(row.enabled and row.registration_status == "Active")
	return _ok(
		employee=employee,
		registered=registered,
		profile=row.name,
		registration_status=row.registration_status,
		enabled=bool(row.enabled),
		registered_on=str(row.registered_on) if row.registered_on else None,
		model_name=row.model_name,
		model_version=row.model_version,
		embedding_dimension=row.embedding_dimension,
		reregistration_requested=bool(row.reregistration_requested),
		reregistration_approved=bool(row.reregistration_approved_by),
	)


def request_face_reregistration(employee: str, remarks: str | None = None) -> dict[str, Any]:
	if not can_manage_employee_face(employee):
		return _fail("Not permitted", "NOT_PERMITTED")
	name = get_active_biometric(employee)
	if not name:
		return _fail("No active biometric to re-register", "NOT_REGISTERED")
	doc = frappe.get_doc("Face Biometric", name)
	doc.reregistration_requested = 1
	doc.reregistration_approved_by = None
	if remarks:
		doc.remarks = remarks
	doc.save(ignore_permissions=True)
	write_audit(employee=employee, event="Re-register Request", result="Pending", remarks=remarks)
	return _ok(employee=employee, reregistration_requested=True)


def approve_face_reregistration(employee: str) -> dict[str, Any]:
	roles = set(frappe.get_roles())
	if not roles.intersection({"System Manager", "HR Manager"}) and frappe.session.user != "Administrator":
		return _fail("Only HR/System Manager can approve re-registration", "NOT_PERMITTED")
	name = get_active_biometric(employee) or frappe.db.get_value(
		"Face Biometric", {"employee": employee}, "name"
	)
	if not name:
		return _fail("Biometric record not found", "NOT_REGISTERED")
	doc = frappe.get_doc("Face Biometric", name)
	doc.reregistration_requested = 1
	doc.reregistration_approved_by = frappe.session.user
	doc.save(ignore_permissions=True)
	write_audit(employee=employee, event="Re-register Approve", result="Success")
	return _ok(employee=employee, approved_by=frappe.session.user)


def disable_face_template(employee: str) -> dict[str, Any]:
	if not can_manage_employee_face(employee):
		return _fail("Not permitted", "NOT_PERMITTED")
	name = get_active_biometric(employee)
	if not name:
		return _fail("No active biometric", "NOT_REGISTERED")
	doc = frappe.get_doc("Face Biometric", name)
	doc.enabled = 0
	doc.registration_status = "Disabled"
	doc.save(ignore_permissions=True)
	write_audit(employee=employee, event="Disable", result="Success")
	return _ok(employee=employee, disabled=True)


def delete_face_template(employee: str) -> dict[str, Any]:
	roles = set(frappe.get_roles())
	if not roles.intersection({"System Manager", "HR Manager"}) and frappe.session.user != "Administrator":
		return _fail("Not permitted", "NOT_PERMITTED")
	name = frappe.db.get_value("Face Biometric", {"employee": employee}, "name")
	if not name:
		return _fail("Biometric record not found", "NOT_REGISTERED")
	frappe.delete_doc("Face Biometric", name, ignore_permissions=True)
	write_audit(employee=employee, event="Delete", result="Success")
	return _ok(employee=employee, deleted=True)


def list_active_biometric_templates_for_match() -> list[dict[str, Any]]:
	"""Return templates for authorized kiosk matching (admin/API key flows only)."""
	rows = frappe.get_all(
		"Face Biometric",
		filters={"enabled": 1, "registration_status": "Active"},
		fields=[
			"name",
			"employee",
			"employee_name",
			"biometric_template",
			"embedding_dimension",
			"model_name",
			"model_version",
		],
	)
	out = []
	for row in rows:
		vector = parse_template(row.biometric_template)
		if not vector:
			continue
		out.append(
			{
				"profile": row.name,
				"employee": row.employee,
				"employee_name": row.employee_name,
				"face_encoding": vector,
				"embedding_dimension": row.embedding_dimension,
				"model_name": row.model_name,
				"model_version": row.model_version,
			}
		)
	return out
