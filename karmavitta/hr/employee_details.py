"""Read-only Employee Details page APIs.

Uses the standard ERPNext Employee DocType and related HRMS records.
Respects Frappe permissions; never bypasses Employee access.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

import frappe
from frappe.utils import add_days, cint, flt, formatdate, getdate, nowdate


LIST_FIELDS = [
	"name",
	"employee_name",
	"image",
	"status",
	"designation",
	"department",
	"branch",
	"company",
	"date_of_joining",
	"cell_number",
	"user_id",
]

EMPLOYEE_FIELDS = [
	"name",
	"employee",
	"employee_name",
	"image",
	"status",
	"company",
	"department",
	"designation",
	"branch",
	"reports_to",
	"date_of_joining",
	"gender",
	"date_of_birth",
	"cell_number",
	"company_email",
	"personal_email",
	"prefered_email",
	"current_address",
	"permanent_address",
	"emergency_phone_number",
	"person_to_be_contacted",
	"relation",
	"holiday_list",
	"user_id",
	"salary_mode",
	"bank_name",
	"bank_ac_no",
	"iban",
	"ctc",
	"salary_currency",
	"passport_number",
	"date_of_issue",
	"valid_upto",
	"place_of_issue",
	"attendance_device_id",
	"marital_status",
	"blood_group",
]


def _exists(doctype: str) -> bool:
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except Exception:
		return False


def _has_perm(doctype: str, ptype: str = "read") -> bool:
	return _exists(doctype) and frappe.has_permission(doctype, ptype)


def _employee_meta_fields() -> set[str]:
	if not _exists("Employee"):
		return set()
	return {df.fieldname for df in frappe.get_meta("Employee").fields}


def _pick_employee_fields() -> list[str]:
	available = _employee_meta_fields()
	extra = [
		"employment_type",
		"grade",
		"default_shift",
		"payroll_cost_center",
		"expense_approver",
		"leave_approver",
		"shift_request_approver",
	]
	fields = [f for f in EMPLOYEE_FIELDS if f in available or f == "name"]
	for field in extra:
		if field in available:
			fields.append(field)
	# Custom identity / document fields if Customize Form added them
	for field in available:
		if field.startswith("custom_") and field not in fields:
			fields.append(field)
	return fields


def _safe_get_all(doctype: str, **kwargs):
	if not _has_perm(doctype):
		return []
	try:
		return frappe.get_all(doctype, **kwargs)
	except Exception:
		frappe.log_error(title=f"Employee Details {doctype}", message=frappe.get_traceback())
		return []


def _avatar(image: str | None, name: str | None) -> dict:
	initials = "".join(part[:1] for part in (name or "?").split()[:2]).upper()
	return {"image": image or "", "initials": initials or "?"}


def _status_badge(status: str | None) -> dict:
	value = (status or "Unknown").strip() or "Unknown"
	kind = "neutral"
	lower = value.lower()
	if lower in {"active"}:
		kind = "success"
	elif lower in {"inactive", "left", "suspended"}:
		kind = "danger"
	elif "leave" in lower:
		kind = "warning"
	return {"label": value, "kind": kind}


def _fmt(value) -> str:
	if value in (None, ""):
		return "—"
	if isinstance(value, date) or hasattr(value, "strftime"):
		try:
			return formatdate(value)
		except Exception:
			return str(value)
	return str(value)


def _require_employee_read():
	if not frappe.has_permission("Employee", "read"):
		frappe.throw("Not permitted to view Employee", frappe.PermissionError)


def _load_employee(employee: str):
	_require_employee_read()
	if not employee or not frappe.db.exists("Employee", employee):
		frappe.throw("Employee not found", frappe.DoesNotExistError)
	if not frappe.has_permission("Employee", "read", employee):
		frappe.throw("Not permitted to view this employee", frappe.PermissionError)
	fields = _pick_employee_fields()
	doc = frappe.get_doc("Employee", employee)
	data = {field: doc.get(field) for field in fields}
	data["name"] = doc.name
	if doc.get("reports_to"):
		data["reports_to_name"] = frappe.db.get_value("Employee", doc.reports_to, "employee_name")
	else:
		data["reports_to_name"] = None
	return data


def _month_bounds(today=None):
	today = getdate(today or nowdate())
	start = today.replace(day=1)
	if today.month == 12:
		end = today.replace(year=today.year + 1, month=1, day=1)
		end = add_days(end, -1)
	else:
		end = today.replace(month=today.month + 1, day=1)
		end = add_days(end, -1)
	return start, end, today


def _attendance_summary(employee: str) -> dict:
	start, end, today = _month_bounds()
	rows = _safe_get_all(
		"Attendance",
		filters={"employee": employee, "attendance_date": ["between", [start, end]], "docstatus": 1},
		fields=["name", "attendance_date", "status", "late_entry", "early_exit", "working_hours", "shift"],
		order_by="attendance_date desc",
		limit=400,
	)
	present = absent = late = 0
	current = "No record"
	for row in rows:
		status = (row.status or "").lower()
		if status in {"present", "work from home", "wfh"}:
			present += 1
		elif status == "absent":
			absent += 1
		if cint(row.late_entry):
			late += 1
		if str(row.attendance_date) == str(today):
			current = row.status or current
	on_leave_today = False
	leave_today = _safe_get_all(
		"Leave Application",
		filters={
			"employee": employee,
			"status": "Approved",
			"docstatus": 1,
			"from_date": ["<=", today],
			"to_date": [">=", today],
		},
		fields=["name"],
		limit=1,
	)
	if leave_today:
		on_leave_today = True
		current = "On Leave"
	return {
		"present_days": present,
		"absent_days": absent,
		"late_entries": late,
		"current_status": current,
		"on_leave": on_leave_today,
		"month_start": str(start),
		"month_end": str(end),
		"history": [
			{
				"name": row.name,
				"date": _fmt(row.attendance_date),
				"status": row.status,
				"late": bool(cint(row.late_entry)),
				"hours": flt(row.working_hours),
				"shift": row.shift,
			}
			for row in rows[:30]
		],
	}


def _leave_summary(employee: str) -> dict:
	today = getdate(nowdate())
	balances = []
	total_balance = 0.0
	taken = 0.0
	if _has_perm("Leave Ledger Entry"):
		try:
			from hrms.hr.doctype.leave_application.leave_application import get_leave_details

			details = get_leave_details(employee, today) or {}
			leave_allocation = details.get("leave_allocation") or {}
			for leave_type, info in leave_allocation.items():
				remaining = flt(info.get("remaining_leaves"))
				total_balance += remaining
				taken += flt(info.get("leaves_taken"))
				balances.append(
					{
						"leave_type": leave_type,
						"allocated": flt(info.get("total_leaves")),
						"taken": flt(info.get("leaves_taken")),
						"pending": flt(info.get("leaves_pending_approval")),
						"remaining": remaining,
					}
				)
		except Exception:
			pass
	applications = _safe_get_all(
		"Leave Application",
		filters={"employee": employee},
		fields=["name", "leave_type", "from_date", "to_date", "total_leave_days", "status", "docstatus"],
		order_by="from_date desc",
		limit=20,
	)
	upcoming = [
		{
			"name": row.name,
			"leave_type": row.leave_type,
			"from_date": _fmt(row.from_date),
			"to_date": _fmt(row.to_date),
			"days": flt(row.total_leave_days),
		}
		for row in applications
		if row.status == "Approved" and row.docstatus == 1 and getdate(row.from_date) >= today
	][:5]
	allocations = _safe_get_all(
		"Leave Allocation",
		filters={"employee": employee, "docstatus": 1},
		fields=["name", "leave_type", "from_date", "to_date", "new_leaves_allocated", "total_leaves_allocated"],
		order_by="from_date desc",
		limit=12,
	)
	return {
		"total_balance": round(total_balance, 2),
		"leave_taken": round(taken, 2),
		"upcoming": upcoming,
		"balances": balances,
		"allocations": [
			{
				"name": row.name,
				"leave_type": row.leave_type,
				"from_date": _fmt(row.from_date),
				"to_date": _fmt(row.to_date),
				"allocated": flt(row.total_leaves_allocated or row.new_leaves_allocated),
			}
			for row in allocations
		],
		"applications": [
			{
				"name": row.name,
				"leave_type": row.leave_type,
				"from_date": _fmt(row.from_date),
				"to_date": _fmt(row.to_date),
				"days": flt(row.total_leave_days),
				"status": row.status,
			}
			for row in applications
		],
	}


def _payroll_summary(employee: str, emp: dict) -> dict:
	assignments = _safe_get_all(
		"Salary Structure Assignment",
		filters={"employee": employee, "docstatus": 1},
		fields=["name", "salary_structure", "from_date", "base", "payroll_payable_account"],
		order_by="from_date desc",
		limit=8,
	)
	slips = _safe_get_all(
		"Salary Slip",
		filters={"employee": employee, "docstatus": ["!=", 2]},
		fields=["name", "start_date", "end_date", "status", "net_pay", "gross_pay", "posting_date"],
		order_by="end_date desc",
		limit=12,
	)
	latest = slips[0] if slips else None
	structure = assignments[0].salary_structure if assignments else None
	payroll_status = latest.status if latest else "No salary slip"
	return {
		"salary_structure": structure or "—",
		"latest_slip": latest.name if latest else "—",
		"latest_net_pay": flt(latest.net_pay) if latest else None,
		"payroll_status": payroll_status,
		"cost_center": emp.get("payroll_cost_center") or "—",
		"bank": {
			"mode": emp.get("salary_mode"),
			"bank_name": emp.get("bank_name"),
			"account": emp.get("bank_ac_no"),
			"iban": emp.get("iban"),
			"currency": emp.get("salary_currency"),
			"ctc": emp.get("ctc"),
		},
		"assignments": [
			{
				"name": row.name,
				"salary_structure": row.salary_structure,
				"from_date": _fmt(row.from_date),
				"base": flt(row.base),
			}
			for row in assignments
		],
		"slips": [
			{
				"name": row.name,
				"period": f"{_fmt(row.start_date)} – {_fmt(row.end_date)}",
				"status": row.status,
				"net_pay": flt(row.net_pay),
				"gross_pay": flt(row.gross_pay),
			}
			for row in slips
		],
	}


def _document_status(issue, expiry, today):
	if not expiry:
		return {"label": "Valid", "kind": "success"} if issue else {"label": "Missing", "kind": "neutral"}
	exp = getdate(expiry)
	if exp < today:
		return {"label": "Expired", "kind": "danger"}
	if exp <= add_days(today, 30):
		return {"label": "Expiring Soon", "kind": "warning"}
	return {"label": "Valid", "kind": "success"}


def _collect_documents(employee: str, emp: dict) -> dict:
	today = getdate(nowdate())
	docs = []

	passport = {
		"title": "Passport",
		"number": emp.get("passport_number"),
		"issue_date": emp.get("date_of_issue"),
		"expiry_date": emp.get("valid_upto"),
		"extra": emp.get("place_of_issue"),
		"doctype": "Employee",
		"name": employee,
	}
	docs.append(passport)

	# Custom fields commonly used for Qatar ID / visa / permit
	custom_map = [
		("Qatar ID / National ID", ["custom_qid", "custom_qatar_id", "custom_national_id", "national_id"]),
		("Visa", ["custom_visa_number", "custom_visa_no", "visa_number"]),
		("Work Permit", ["custom_work_permit", "custom_work_permit_no", "work_permit_number"]),
		("Employment Contract", ["custom_contract_no"]),
	]
	for title, keys in custom_map:
		number = None
		issue = expiry = None
		for key in keys:
			if emp.get(key):
				number = emp.get(key)
				break
		for key, target in (
			(f"{keys[0]}_issue", "issue"),
			(f"{keys[0]}_expiry", "expiry"),
			("custom_visa_expiry", "expiry"),
			("custom_qid_expiry", "expiry"),
			("custom_work_permit_expiry", "expiry"),
			("contract_end_date", "expiry"),
		):
			if emp.get(key) and target == "issue":
				issue = emp.get(key)
			if emp.get(key) and target == "expiry":
				expiry = emp.get(key)
		if number or issue or expiry:
			docs.append(
				{
					"title": title,
					"number": number,
					"issue_date": issue,
					"expiry_date": expiry or (emp.get("contract_end_date") if title == "Employment Contract" else None),
					"extra": None,
					"doctype": "Employee",
					"name": employee,
				}
			)

	files = []
	if _has_perm("File"):
		files = _safe_get_all(
			"File",
			filters={"attached_to_doctype": "Employee", "attached_to_name": employee, "is_folder": 0},
			fields=["name", "file_name", "file_url", "creation"],
			order_by="creation desc",
			limit=50,
		)
	# Classify attachments by filename
	classified = {
		"CV / Resume": [],
		"Educational certificates": [],
		"Professional certificates": [],
		"Other documents": [],
	}
	for f in files:
		label = (f.file_name or "").lower()
		item = {
			"title": f.file_name,
			"number": None,
			"issue_date": None,
			"expiry_date": None,
			"extra": f.file_url,
			"doctype": "File",
			"name": f.name,
			"file_url": f.file_url,
		}
		if any(k in label for k in ("cv", "resume", "curriculum")):
			classified["CV / Resume"].append(item)
		elif any(k in label for k in ("edu", "degree", "diploma", "school", "university")):
			classified["Educational certificates"].append(item)
		elif any(k in label for k in ("cert", "license", "licence", "professional")):
			classified["Professional certificates"].append(item)
		else:
			classified["Other documents"].append(item)

	for title, items in classified.items():
		if not items:
			docs.append(
				{
					"title": title,
					"number": None,
					"issue_date": None,
					"expiry_date": None,
					"extra": None,
					"doctype": None,
					"name": None,
				}
			)
		else:
			for item in items:
				item["group"] = title
				docs.append(item)

	out = []
	expiring = expired = 0
	for doc in docs:
		status = _document_status(doc.get("issue_date"), doc.get("expiry_date"), today)
		if status["label"] == "Expiring Soon":
			expiring += 1
		elif status["label"] == "Expired":
			expired += 1
		out.append(
			{
				**doc,
				"issue_date": _fmt(doc.get("issue_date")) if doc.get("issue_date") else "—",
				"expiry_date": _fmt(doc.get("expiry_date")) if doc.get("expiry_date") else "—",
				"status": status,
			}
		)
	return {
		"total": len([d for d in out if d.get("number") or d.get("file_url") or (d.get("expiry_date") not in (None, "—"))]),
		"expiring": expiring,
		"expired": expired,
		"items": out,
	}


def _performance_summary(employee: str) -> dict:
	appraisals = _safe_get_all(
		"Appraisal",
		filters={"employee": employee},
		fields=["name", "appraisal_cycle", "final_score", "total_score", "status", "start_date", "end_date"],
		order_by="modified desc",
		limit=10,
	)
	goals = _safe_get_all(
		"Goal",
		filters={"employee": employee},
		fields=["name", "goal_name", "status", "progress", "start_date", "end_date"],
		order_by="modified desc",
		limit=20,
	)
	active_goals = [g for g in goals if (g.status or "").lower() not in {"completed", "cancelled"}]
	skills = []
	if _has_perm("Employee Skill Map"):
		maps = _safe_get_all(
			"Employee Skill Map",
			filters={"employee": employee},
			fields=["name"],
			limit=1,
		)
		if maps:
			try:
				doc = frappe.get_doc("Employee Skill Map", maps[0].name)
				for row in doc.get("employee_skills") or []:
					skills.append(
						{
							"skill": row.get("skill"),
							"proficiency": row.get("proficiency") or row.get("rating"),
						}
					)
			except Exception:
				pass
	training = _safe_get_all(
		"Training Event",
		filters={},
		fields=["name", "event_name", "status", "start_time"],
		order_by="modified desc",
		limit=8,
	)
	# Training Event employees is a child table; keep a light status
	training_status = training[0].status if training else "No training"
	latest = appraisals[0] if appraisals else None
	return {
		"latest_rating": flt(latest.final_score or latest.total_score) if latest else None,
		"latest_appraisal": latest.name if latest else None,
		"active_goals": len(active_goals),
		"training_status": training_status,
		"appraisals": [
			{
				"name": row.name,
				"cycle": row.appraisal_cycle,
				"score": flt(row.final_score or row.total_score),
				"status": row.status,
			}
			for row in appraisals
		],
		"goals": [
			{
				"name": row.name,
				"goal": row.goal_name or row.name,
				"status": row.status,
				"progress": flt(row.progress),
			}
			for row in goals
		],
		"skills": skills,
		"training": [
			{"name": row.name, "event": row.event_name or row.name, "status": row.status}
			for row in training
		],
	}


def _activity(employee: str, emp: dict) -> list[dict]:
	items = []
	versions = _safe_get_all(
		"Version",
		filters={"ref_doctype": "Employee", "docname": employee},
		fields=["name", "creation", "owner"],
		order_by="creation desc",
		limit=12,
	)
	for row in versions:
		items.append(
			{
				"title": "Employee record updated",
				"detail": row.owner,
				"when": _fmt(row.creation),
				"doctype": "Version",
				"name": row.name,
			}
		)
	for doctype, title_field, label in (
		("Leave Application", "leave_type", "Leave"),
		("Attendance", "status", "Attendance"),
		("Employee Promotion", "promotion_date", "HR action"),
		("Employee Transfer", "transfer_date", "HR action"),
	):
		rows = _safe_get_all(
			doctype,
			filters={"employee": employee},
			fields=["name", "modified", title_field] if _exists(doctype) else ["name"],
			order_by="modified desc",
			limit=8,
		)
		for row in rows:
			items.append(
				{
					"title": f"{label}: {row.get(title_field) or row.name}",
					"detail": doctype,
					"when": _fmt(row.modified),
					"doctype": doctype,
					"name": row.name,
				}
			)
	comments = _safe_get_all(
		"Comment",
		filters={"reference_doctype": "Employee", "reference_name": employee, "comment_type": "Comment"},
		fields=["name", "content", "creation", "comment_by"],
		order_by="creation desc",
		limit=10,
	)
	for row in comments:
		items.append(
			{
				"title": "Comment",
				"detail": frappe.utils.strip_html(row.content or "")[:180],
				"when": _fmt(row.creation),
				"doctype": "Comment",
				"name": row.name,
			}
		)
	items.sort(key=lambda x: x.get("when") or "", reverse=True)
	return items[:40]


@frappe.whitelist()
def get_employee_directory(search: str | None = None, status: str | None = None, limit: int = 100):
	_require_employee_read()
	available = _employee_meta_fields()
	fields = [f for f in LIST_FIELDS if f in available or f == "name"]
	if "employee" in available and "employee" not in fields:
		fields.append("employee")
	filters = {}
	if status == "Inactive":
		filters["status"] = ["in", ["Inactive", "Left"]]
	elif status and status != "All":
		filters["status"] = status
	or_filters = None
	if search:
		term = f"%{search}%"
		or_filters = [
			["employee_name", "like", term],
			["name", "like", term],
			["department", "like", term],
			["designation", "like", term],
		]
	page_length = cint(limit)
	if page_length < 0:
		page_length = 200
	rows = frappe.get_list(
		"Employee",
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		order_by="employee_name asc",
		limit_page_length=page_length,
	)
	counts = defaultdict(int)
	all_status = frappe.get_list("Employee", fields=["status"], limit_page_length=0)
	for row in all_status:
		counts[row.status or "Unknown"] += 1
		counts["All"] += 1
	directory = []
	for row in rows:
		joining = row.get("date_of_joining")
		directory.append(
			{
				**row,
				"employee_id": row.get("employee") or row.get("name"),
				"avatar": _avatar(row.get("image"), row.get("employee_name")),
				"badge": _status_badge(row.get("status")),
				"date_of_joining": _fmt(joining),
				"date_of_joining_iso": str(joining) if joining else "",
			}
		)
	return {
		"success": True,
		"totals": {
			"all": counts.get("All", 0),
			"active": counts.get("Active", 0),
			"inactive": counts.get("Inactive", 0) + counts.get("Left", 0),
			"on_leave": counts.get("On Leave", 0),
			"by_status": dict(counts),
		},
		"employees": directory,
		"can_create": frappe.has_permission("Employee", "create"),
	}


@frappe.whitelist()
def get_employee_profile(employee: str):
	emp = _load_employee(employee)
	attendance = _attendance_summary(employee)
	leave = _leave_summary(employee)
	payroll = _payroll_summary(employee, emp)
	documents = _collect_documents(employee, emp)
	performance = _performance_summary(employee)
	employment_status = emp.get("status")
	if attendance.get("on_leave") and (employment_status or "").lower() == "active":
		badge = {"label": "On Leave", "kind": "warning"}
	else:
		badge = _status_badge(employment_status)

	profile = {
		"employee": emp.get("name"),
		"employee_id": emp.get("employee") or emp.get("name"),
		"full_name": emp.get("employee_name"),
		"photo": emp.get("image"),
		"avatar": _avatar(emp.get("image"), emp.get("employee_name")),
		"status": employment_status,
		"badge": badge,
		"designation": emp.get("designation"),
		"department": emp.get("department"),
		"branch": emp.get("branch"),
		"reports_to": emp.get("reports_to"),
		"reports_to_name": emp.get("reports_to_name"),
		"date_of_joining": _fmt(emp.get("date_of_joining")),
		"employment_type": emp.get("employment_type"),
		"company": emp.get("company"),
		"grade": emp.get("grade"),
		"shift": emp.get("default_shift"),
		"holiday_list": emp.get("holiday_list"),
		"can_write": frappe.has_permission("Employee", "write", employee),
	}
	return {
		"success": True,
		"profile": profile,
		"employee": emp,
		"cards": {
			"attendance": attendance,
			"leave": leave,
			"payroll": payroll,
			"documents": documents,
			"performance": performance,
		},
		"activity": _activity(employee, emp),
	}
