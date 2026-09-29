"""Stable permission keys shared by the mobile app and its Desk configuration."""

MOBILE_MODULES = {
	"dashboard": "Dashboard",
	"accounting": "Accounting & Finance",
	"selling": "Selling",
	"buying": "Buying",
	"inventory": "Inventory",
	"crm": "CRM",
	"hr": "HR & Payroll",
	"projects": "Projects",
	"manufacturing": "Manufacturing",
	"assets": "Assets",
	"quality": "Quality",
	"support": "Support",
	"users": "Users & Roles",
	"workflows": "Workflows",
	"reports": "Reports",
	"face_attendance": "Face Attendance",
	"attendance": "Attendance",
	"leave": "Leave",
	"payroll": "Payslips",
	"approvals": "Approvals",
	"notifications": "Notifications",
	"employees": "Employees",
	"locations": "Locations",
	"profile": "Profile",
}

MODULE_DOCTYPES = {
	"accounting": ["Account", "Journal Entry", "Sales Invoice", "Purchase Invoice", "Payment Entry", "Cost Center", "Budget"],
	"selling": ["Customer", "Lead", "Opportunity", "Quotation", "Sales Order", "Delivery Note", "Sales Invoice"],
	"buying": ["Supplier", "Material Request", "Request for Quotation", "Supplier Quotation", "Purchase Order", "Purchase Receipt", "Purchase Invoice"],
	"inventory": ["Item", "Warehouse", "Stock Entry", "Stock Reconciliation", "Serial No", "Batch"],
	"crm": ["Contact", "Communication", "Lead"],
	"hr": ["Employee", "Attendance", "Leave Application", "Expense Claim", "Salary Slip", "Payroll Entry"],
	"projects": ["Project", "Task", "Timesheet"],
	"manufacturing": ["BOM", "Work Order", "Job Card", "Production Plan"],
	"assets": ["Asset", "Asset Category", "Asset Movement", "Asset Repair"],
	"quality": ["Quality Inspection", "Quality Goal", "Quality Action"],
	"support": ["Issue", "Maintenance Visit", "Warranty Claim"],
	"users": ["User", "Role", "User Permission"],
	"workflows": ["Workflow", "Workflow Action", "Assignment Rule"],
	"reports": ["Report"],
	"attendance": ["Attendance", "Employee Checkin"],
	"leave": ["Leave Application", "Leave Allocation", "Leave Ledger Entry"],
	"payroll": ["Salary Slip"],
	"approvals": ["Workflow Action", "Leave Application", "Expense Claim"],
	"notifications": ["Notification Log"],
	"employees": ["Employee"],
	"locations": ["Face Attendance Settings"],
}

# Only these module documents are browsable through the mobile ERP Modules
# screen. Other DocTypes in MODULE_DOCTYPES secure feature APIs and are not
# exposed as invented checkbox entries.
MOBILE_DOCUMENT_MODULES = (
	"accounting",
	"selling",
	"buying",
	"inventory",
	"crm",
	"hr",
	"projects",
	"manufacturing",
	"assets",
	"quality",
	"support",
	"users",
	"workflows",
)

# These are React Navigation route keys, not ERPNext roles or DocTypes.
SCREEN_MODULES = {
	"employee_home": "dashboard",
	"admin_dashboard": "dashboard",
	"owner_dashboard": "dashboard",
	"erp_modules": None,
	"erp_employee_directory": "employees",
	"erp_module_documents": None,  # resolved from the route's moduleKey
	"erp_document_detail": None,  # resolved from the route's DocType
	"erp_reports": "reports",
	"erp_report_detail": "reports",
	"erp_accounting": "accounting",
	"erp_selling": "selling",
	"erp_buying": "buying",
	"erp_inventory": "inventory",
	"erp_crm": "crm",
	"erp_hr_payroll": "hr",
	"erp_projects": "projects",
	"erp_manufacturing": "manufacturing",
	"erp_assets": "assets",
	"erp_quality": "quality",
	"erp_support": "support",
	"erp_users_roles": "users",
	"erp_workflows": "workflows",
	"attendance_hub": "attendance",
	"qid_scanner": "face_attendance",
	"attendance_result": "attendance",
	"employee_list": "employees",
	"today_attendance_list": "attendance",
	"correction_request": "attendance",
	"face_register": "face_attendance",
	"face_attendance": "face_attendance",
	"add_employee": "employees",
	"add_location": "locations",
	"leads": "crm",
	"crm_dashboard": "crm",
	"my_profile": "profile",
	"approvals": "approvals",
	"notifications": "notifications",
	"leave": "leave",
	"payslips": "payroll",
	"location_selection": "face_attendance",
}

# One registry drives the Desk configuration form and the mobile permission API.
# Module and route keys are the stable identifiers already consumed by React
# Native; DocTypes use the existing permission key format ``doctype:<name>``.
SCREEN_LABELS = {
	"employee_home": "Home",
	"admin_dashboard": "Master Dashboard",
	"owner_dashboard": "Owner Dashboard",
	"erp_modules": "ERP Modules",
	"erp_employee_directory": "Employee Directory",
	"erp_module_documents": "Module Records",
	"erp_document_detail": "Record Details",
	"erp_reports": "Reports & Analytics",
	"erp_report_detail": "Report Details",
	"erp_accounting": "Accounting Dashboard",
	"erp_selling": "Selling Dashboard",
	"erp_buying": "Buying Dashboard",
	"erp_inventory": "Inventory Dashboard",
	"erp_crm": "CRM Dashboard",
	"erp_hr_payroll": "HR Dashboard",
	"erp_projects": "Projects Dashboard",
	"erp_manufacturing": "Manufacturing Dashboard",
	"erp_assets": "Assets Dashboard",
	"erp_quality": "Quality Dashboard",
	"erp_support": "Support Dashboard",
	"erp_users_roles": "Users and Roles",
	"erp_workflows": "Workflows and Approvals",
	"attendance_hub": "Attendance",
	"qid_scanner": "Face Attendance Scanner",
	"attendance_result": "Attendance Result",
	"employee_list": "Employee List",
	"today_attendance_list": "Today's Attendance",
	"correction_request": "Attendance Correction Request",
	"face_register": "Face Registration",
	"face_attendance": "Face Check-In",
	"add_employee": "Add Employee",
	"add_location": "Attendance Locations",
	"leads": "Lead Capture",
	"crm_dashboard": "CRM Overview",
	"my_profile": "My Profile",
	"approvals": "Approvals",
	"notifications": "Notifications",
	"leave": "Leave",
	"payslips": "Payslips",
	"location_selection": "Attendance Location Selection",
}

DOCTYPE_LABELS = {
	"Account": "Chart of Accounts",
	"Journal Entry": "Journal Entry",
	"Sales Invoice": "Sales Invoice",
	"Purchase Invoice": "Purchase Invoice",
	"Payment Entry": "Payment Entry",
	"Cost Center": "Cost Centers",
	"Budget": "Budgets",
	"Customer": "Customers",
	"Lead": "Leads",
	"Opportunity": "Opportunities",
	"Quotation": "Quotations",
	"Sales Order": "Sales Orders",
	"Delivery Note": "Delivery Notes",
	"Supplier": "Suppliers",
	"Material Request": "Material Requests",
	"Request for Quotation": "Requests for Quotation",
	"Supplier Quotation": "Supplier Quotations",
	"Purchase Order": "Purchase Orders",
	"Purchase Receipt": "Purchase Receipts",
	"Item": "Items",
	"Warehouse": "Warehouses",
	"Stock Entry": "Stock Entries",
	"Stock Reconciliation": "Stock Reconciliations",
	"Serial No": "Serial Numbers",
	"Batch": "Batches",
	"Contact": "Contacts",
	"Communication": "Communications",
	"Employee": "Employees",
	"Attendance": "Attendance Records",
	"Leave Application": "Leave Applications",
	"Expense Claim": "Expense Claims",
	"Salary Slip": "Salary Slips",
	"Payroll Entry": "Payroll Entries",
	"Project": "Projects",
	"Task": "Tasks",
	"Timesheet": "Timesheets",
	"BOM": "Bills of Materials",
	"Work Order": "Work Orders",
	"Job Card": "Job Cards",
	"Production Plan": "Production Plans",
	"Asset": "Assets",
	"Asset Category": "Asset Categories",
	"Asset Movement": "Asset Movements",
	"Asset Repair": "Asset Repairs",
	"Quality Inspection": "Quality Inspections",
	"Quality Goal": "Quality Goals",
	"Quality Action": "Quality Actions",
	"Issue": "Support Issues",
	"Maintenance Visit": "Maintenance Visits",
	"Warranty Claim": "Warranty Claims",
	"User": "Users",
	"Role": "Roles",
	"User Permission": "User Permissions",
	"Company": "Companies",
	"Branch": "Branches",
	"Workflow": "Workflows",
	"Workflow Action": "Workflow Actions",
	"Assignment Rule": "Assignment Rules",
	"Report": "Reports",
	"Employee Checkin": "Employee Check-ins",
	"Leave Allocation": "Leave Allocations",
	"Leave Ledger Entry": "Leave Ledger",
	"Notification Log": "Notifications",
	"Face Attendance Settings": "Attendance Locations",
}

# These generic React Navigation containers follow their selected module,
# record, or report and do not need duplicate checkboxes.
DYNAMIC_CONTAINER_ROUTES = {
	"erp_modules",
	"erp_module_documents",
	"erp_document_detail",
	"erp_report_detail",
}

# Route screens whose legacy visibility falls back to a module rule. In the
# new matrix they remain separately selectable from their module group.
MODULE_ROUTE_MODULES = {
	"erp_accounting": "accounting",
	"erp_selling": "selling",
	"erp_buying": "buying",
	"erp_inventory": "inventory",
	"erp_crm": "crm",
	"erp_hr_payroll": "hr",
	"erp_projects": "projects",
	"erp_manufacturing": "manufacturing",
	"erp_assets": "assets",
	"erp_quality": "quality",
	"erp_support": "support",
	"erp_users_roles": "users",
	"erp_workflows": "workflows",
	"erp_reports": "reports",
	"face_attendance": "face_attendance",
	"my_profile": "profile",
}


def get_mobile_screen_registry(reports: list[dict] | None = None) -> list[dict]:
	"""Return registered modules and real app routes/DocTypes in display order."""
	registry = []
	module_order = MOBILE_DOCUMENT_MODULES
	for module_key, label in MOBILE_MODULES.items():
		registry.append({
			"key": f"module:{module_key}",
			"label": label,
			"module": module_key,
			"module_label": label,
			"kind": "module",
			"module_key": module_key,
			"route_key": None,
		})

	for route_key, module_key in SCREEN_MODULES.items():
		if route_key in DYNAMIC_CONTAINER_ROUTES:
			continue  # Generic reusable navigation containers are derived.
		module_label = MOBILE_MODULES.get(module_key, "Other Screens")
		registry.append({
			"key": route_key,
			"label": SCREEN_LABELS.get(route_key, route_key.replace("_", " ").title()),
			"module": module_key or "other_screens",
			"module_label": module_label,
			"kind": "route",
			"module_key": module_key if module_key in MOBILE_MODULES else None,
			"route_key": route_key,
			"module_route": route_key in MODULE_ROUTE_MODULES,
		})

	seen_doctypes = set()
	for module_key in module_order:
		for doctype in MODULE_DOCTYPES.get(module_key, []):
			if doctype in seen_doctypes:
				continue
			seen_doctypes.add(doctype)
			registry.append({
				"key": f"doctype:{doctype}",
				"label": DOCTYPE_LABELS.get(doctype, doctype),
				"module": module_key,
				"module_label": MOBILE_MODULES[module_key],
				"kind": "doctype",
				"module_key": module_key,
				"doctype": doctype,
			})
	for report in reports or []:
		report_name = (report.get("name") or "").strip()
		if not report_name:
			continue
		registry.append({
			"key": f"report:{report_name}",
			"label": report.get("report_name") or report_name,
			"module": "reports",
			"module_label": MOBILE_MODULES["reports"],
			"kind": "report",
			"module_key": "reports",
			"report_name": report_name,
		})
	return registry

WIDGET_KEYS = {
	"attendance_summary",
	"leave_balance",
	"payroll_summary",
	"finance_overview",
	"quick_actions",
	"recent_activity",
}

QUICK_ACTION_KEYS = {
	"check_in",
	"check_out",
	"apply_leave",
	"request_correction",
	"register_face",
	"add_employee",
	"create_lead",
}

ACTION_FIELDS = {
	"view": "can_view",
	"create": "can_create",
	"edit": "can_edit",
	"submit": "can_submit",
	"cancel": "can_cancel",
	"delete": "can_delete",
	"print": "can_print",
	"export": "can_export",
	"share": "can_share",
}
