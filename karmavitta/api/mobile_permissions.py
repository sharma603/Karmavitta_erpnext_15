"""Mobile-only visibility controls, always intersected with ERPNext permissions."""

from __future__ import annotations

import frappe
from frappe import _

from karmavitta.mobile_app_management.catalog import (
	ACTION_FIELDS,
	MODULE_DOCTYPES,
	MODULE_ROUTE_MODULES,
	MOBILE_MODULES,
	QUICK_ACTION_KEYS,
	SCREEN_MODULES,
	WIDGET_KEYS,
	get_mobile_screen_registry,
)


def _require_mobile_admin() -> None:
	if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
		frappe.throw(_("System Manager permission is required to configure mobile app access."), frappe.PermissionError)


def _validate_system_user(user: str) -> None:
	if not user:
		frappe.throw(_("Select an ERPNext User first."))
	row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
	if not row or not row.enabled or row.user_type != "System User":
		frappe.throw(_("Select an enabled ERPNext System User."))


def validate_mobile_permission_rule(target_type: str, target_key: str) -> None:
	target_type = (target_type or "").strip()
	target_key = (target_key or "").strip()
	if not target_key:
		frappe.throw(_("A mobile permission key is required."))

	if target_type == "Module":
		if target_key not in MOBILE_MODULES:
			frappe.throw(_("Unknown mobile module key: {0}.").format(target_key))
		return

	if target_type == "Screen":
		if target_key in SCREEN_MODULES:
			return
		if target_key.startswith("doctype:"):
			doctype = target_key.removeprefix("doctype:").strip()
			if doctype and frappe.db.exists("DocType", doctype):
				return
		frappe.throw(_("Unknown mobile screen key: {0}.").format(target_key))

	if target_type == "Report":
		if target_key.startswith("report:") and frappe.db.exists("Report", target_key.removeprefix("report:").strip()):
			return
		frappe.throw(_("Use a saved Report key in the form report:Report Name."))

	if target_type == "Dashboard Widget":
		if target_key.startswith("widget:") and target_key.removeprefix("widget:") in WIDGET_KEYS:
			return
		frappe.throw(_("Unknown dashboard widget key: {0}.").format(target_key))

	if target_type == "Quick Action":
		if target_key.startswith("action:") and target_key.removeprefix("action:") in QUICK_ACTION_KEYS:
			return
		frappe.throw(_("Unknown quick action key: {0}.").format(target_key))

	frappe.throw(_("Rule Type must be Module, Screen, Report, Dashboard Widget, or Quick Action."))


def _get_mobile_screen_registry() -> list[dict]:
	"""Include only real, enabled ERPNext reports in the mobile screen catalog."""
	reports = []
	if frappe.db.exists("DocType", "Report"):
		reports = frappe.get_all(
			"Report",
			filters={"disabled": 0},
			fields=["name", "report_name"],
			limit_page_length=0,
		)
	return get_mobile_screen_registry(reports)


@frappe.whitelist()
def get_mobile_permission_catalog():
	"""Return the canonical mobile module/screen registry for Desk clients."""
	_require_mobile_admin()
	return {
		"modules": [
			{"key": key, "label": label}
			for key, label in MOBILE_MODULES.items()
		],
		"screens": _get_mobile_screen_registry(),
	}


def _user_profiles_for_setup(user: str, company: str | None = None) -> list[dict]:
	if company:
		return _profiles_for_scope("User", user, company)
	profiles = frappe.get_all(
		"Mobile App Permission",
		filters={"applies_to": "User", "user": user},
		fields=["name", "company", "enabled"],
		order_by="company asc, modified desc",
		limit_page_length=0,
	)
	global_profiles = [profile for profile in profiles if not profile.company]
	return global_profiles or profiles


@frappe.whitelist()
def get_mobile_permission_matrix(
	user: str | None = None,
	profile_name: str | None = None,
	applies_to: str | None = None,
	identity: str | None = None,
	company: str | None = None,
):
	"""Load a user's saved screen values; new profiles start with every screen off."""
	_require_mobile_admin()
	user = (user or identity or "").strip()
	if applies_to == "Role":
		frappe.throw(_("Mobile screen access is configured per ERPNext User."))
	_validate_system_user(user)

	profiles = _user_profiles_for_setup(user, company)
	if profile_name:
		if not frappe.db.exists("Mobile App Permission", profile_name):
			frappe.throw(_("The selected mobile permission profile no longer exists."))
		profile = frappe.get_doc("Mobile App Permission", profile_name)
		if profile.user != user:
			frappe.throw(_("This profile belongs to a different ERPNext User."), frappe.PermissionError)
		profiles = [profile]

	selected_profile = profiles[0] if profiles else None
	if selected_profile:
		profile_doc = frappe.get_doc("Mobile App Permission", selected_profile.name)
		if profile_doc.screens:
			values = {row.screen_name: bool(row.enabled) for row in profile_doc.screens}
			# Support child rows from early builds where group keys and route keys
			# shared the same namespace.
			for module_key in MOBILE_MODULES:
				values.setdefault(f"module:{module_key}", values.get(module_key, False))
			return {"values": values, "saved": True, "profile_name": profile_doc.name}

	# New screen configurations are explicit per-user choices. Legacy rules
	# from this user's own profile may seed the form, but role defaults must not
	# silently preselect screens for a newly configured user.
	user_index = _rule_index(_load_rules(profiles))
	role_indexes = []
	modules = {
		key: bool(_effective_rule(("Module", key), user_index, role_indexes, False)["enabled"])
		for key in MOBILE_MODULES
	}
	values = {}
	for item in _get_mobile_screen_registry():
		if item["kind"] == "module":
			values[item["key"]] = modules.get(item["module_key"], False)
		elif item["kind"] == "route":
			values[item["key"]] = bool(
				_effective_rule(
					("Screen", item["key"]), user_index, role_indexes,
					modules.get(item.get("module_key"), False),
				)["enabled"]
			)
		elif item["kind"] == "report":
			values[item["key"]] = bool(
				_effective_rule(
					("Report", item["key"]), user_index, role_indexes,
					modules.get("reports", False),
				)["enabled"]
			)
		elif item["kind"] == "doctype":
			module_enabled = any(modules.get(key, False) for key in _doctype_modules(item["doctype"]))
			values[item["key"]] = bool(
				_effective_rule(("Screen", item["key"]), user_index, role_indexes, module_enabled)["enabled"]
			)
	return {"values": values, "saved": False, "profile_name": selected_profile.name if selected_profile else None}


@frappe.whitelist()
def get_mobile_user_summary(user: str):
	_require_mobile_admin()
	user = (user or "").strip()
	_validate_system_user(user)
	row = frappe.db.get_value("User", user, ["full_name", "email", "enabled", "user_type"], as_dict=True)
	return {
		"name": user,
		"full_name": row.full_name or user,
		"email": row.email or user,
		"enabled": bool(row.enabled),
		"user_type": row.user_type,
		"roles": frappe.get_roles(user),
	}


@frappe.whitelist()
def get_mobile_permission_profiles(search: str | None = None):
	_require_mobile_admin()
	needle = (search or "").strip().casefold()
	profiles = frappe.get_all(
		"Mobile App Permission",
		filters={"applies_to": "User"},
		fields=["name", "user", "enabled", "modified"],
		order_by="modified desc",
		limit_page_length=1000,
	)
	if not profiles:
		return []
	user_names = sorted({profile.user for profile in profiles if profile.user})
	if not user_names:
		return []
	users = frappe.get_all(
		"User",
		filters={"name": ["in", user_names]},
		fields=["name", "full_name", "email"],
		limit_page_length=0,
	)
	users_by_name = {user.name: user for user in users}
	profile_names = [profile.name for profile in profiles]
	screen_rows = frappe.get_all(
		"Mobile App Permission Screen",
		filters={"parent": ["in", profile_names], "parenttype": "Mobile App Permission", "parentfield": "screens"},
		fields=["parent", "enabled", "screen_name", "screen_label"],
		limit_page_length=0,
	)
	screens_by_profile = {}
	for row in screen_rows:
		screens_by_profile.setdefault(row.parent, []).append(row)
	registry_by_key = {item["key"]: item for item in _get_mobile_screen_registry()}
	total_screens = sum(item["kind"] != "module" for item in registry_by_key.values())
	result = []
	for profile in profiles:
		user = users_by_name.get(profile.user)
		if not user:
			continue
		name = user.full_name or profile.user
		email = user.email or profile.user
		if needle and needle not in f"{name} {email} {profile.user}".casefold():
			continue
		rows = screens_by_profile.get(profile.name, [])
		selected_rows = [
			row for row in rows
			if row.enabled
			and row.screen_name in registry_by_key
			and registry_by_key[row.screen_name].get("kind") != "module"
		]
		result.append({
			"name": profile.name,
			"user": profile.user,
			"full_name": name,
			"email": email,
			"enabled": bool(profile.enabled),
			"selected_screens": len(selected_rows),
			"total_screens": total_screens,
			"selected_screen_labels": [row.screen_label for row in selected_rows],
			"modified": profile.modified,
		})
	return result


@frappe.whitelist()
def delete_mobile_permission_profile(name: str):
	_require_mobile_admin()
	if not frappe.db.exists("Mobile App Permission", name):
		frappe.throw(_("Mobile App Permission profile not found."))
	doc = frappe.get_doc("Mobile App Permission", name)
	if doc.applies_to != "User":
		frappe.throw(_("Only user screen profiles can be deleted from this page."), frappe.PermissionError)
	doc.delete(ignore_permissions=True)
	return {"deleted": True}


def _get_mobile_settings():
	if not frappe.db.exists("DocType", "Mobile App Settings"):
		return {
			"app_name": "Karmavitta",
			"enabled": True,
			"default_allow_mobile_access": False,
			"default_landing_screen": "EmployeeHome",
			"permission_version": 1,
			"allow_offline_mode": True,
		}
	settings = frappe.get_single("Mobile App Settings")
	return {
		"app_name": settings.app_name or "Karmavitta",
		"enabled": bool(settings.enabled),
		"default_allow_mobile_access": bool(settings.default_allow_mobile_access),
		"default_landing_screen": settings.default_landing_screen or "EmployeeHome",
		"permission_version": int(settings.permission_version or 1),
		"allow_offline_mode": bool(settings.allow_offline_mode),
		"force_permission_refresh": bool(settings.force_permission_refresh),
		"session_timeout_minutes": int(settings.session_timeout_minutes or 60),
	}


def _accessible_companies() -> list[str]:
	# This endpoint runs as the authenticated session user; get_list applies that
	# user's Company permissions and User Permissions automatically.
	try:
		return frappe.get_list("Company", pluck="name", limit_page_length=0)
	except frappe.PermissionError:
		return []


def _choose_company(user: str, company: str | None, companies: list[str]) -> str | None:
	if company:
		if company not in companies:
			frappe.throw(_("You do not have access to company {0}.").format(company), frappe.PermissionError)
		return company

	try:
		default_company = frappe.defaults.get_user_default("Company", user)
	except Exception:
		default_company = None
	if default_company in companies:
		return default_company
	return companies[0] if companies else None


def _profiles_for_scope(applies_to: str, identity: str, company: str | None) -> list[dict]:
	field = "user" if applies_to == "User" else "role"
	profiles = frappe.get_all(
		"Mobile App Permission",
		filters={"applies_to": applies_to, field: identity},
		fields=["name", "company", "enabled"],
		limit_page_length=0,
	)
	if company:
		exact = [p for p in profiles if p.company == company]
		if exact:
			return exact
	return [p for p in profiles if not p.company]


def _load_rules(profiles: list[dict]) -> list[dict]:
	if not profiles:
		return []
	return frappe.get_all(
		"Mobile App Permission Rule",
		filters={"parent": ["in", [p.name for p in profiles]], "parenttype": "Mobile App Permission"},
		fields=["parent", "target_type", "target_key", "enabled", *ACTION_FIELDS.values()],
		limit_page_length=0,
	)


def _rule_index(rules: list[dict]) -> dict[tuple[str, str], list[dict]]:
	indexed: dict[tuple[str, str], list[dict]] = {}
	for row in rules:
		indexed.setdefault((row.target_type, row.target_key), []).append(row)
	return indexed


def _role_rule_value(role_indexes: list[dict], key: tuple[str, str]) -> dict | None:
	rows = [row for index in role_indexes for row in index.get(key, [])]
	if not rows:
		return None
	allowed_rows = [row for row in rows if row.enabled]
	return {
		"enabled": bool(allowed_rows),
		**{
			field: any(bool(row.get(field)) for row in allowed_rows)
			for field in ACTION_FIELDS.values()
		},
	}


def _effective_rule(
	key: tuple[str, str],
	user_index: dict,
	role_indexes: list[dict],
	default_enabled: bool,
) -> dict:
	rows = user_index.get(key)
	if rows:
		row = rows[-1]
		return {"enabled": bool(row.get("enabled")), **{field: bool(row.get(field)) for field in ACTION_FIELDS.values()}}
	role_value = _role_rule_value(role_indexes, key)
	if role_value is not None:
		return role_value
	return {"enabled": default_enabled, **{field: True for field in ACTION_FIELDS.values()}}


def _erp_action_permissions(doctype: str, user: str) -> dict[str, bool]:
	permissions = {}
	for action in ACTION_FIELDS:
		try:
			permission_type = "read" if action == "view" else "write" if action == "edit" else action
			permissions[action] = bool(
				frappe.has_permission(doctype, permission_type, user=user, throw=False)
			)
		except Exception:
			permissions[action] = False
	return permissions


def _module_erp_access(module_key: str, user: str) -> bool:
	doctypes = MODULE_DOCTYPES.get(module_key, [])
	if not doctypes:
		return True
	for doctype in doctypes:
		if not frappe.db.exists("DocType", doctype):
			continue
		try:
			if frappe.has_permission(doctype, "read", user=user, throw=False):
				return True
		except Exception:
			continue
	return False


def _doctype_modules(doctype: str) -> list[str]:
	return [module_key for module_key, doctypes in MODULE_DOCTYPES.items() if doctype in doctypes]


def _allowed_report_names(user: str) -> set[str]:
	try:
		rows = frappe.get_list(
			"Report",
			filters={"disabled": 0},
			fields=["name", "ref_doctype"],
			limit_page_length=0,
		)
	except Exception:
		return set()
	return {
		row.name
		for row in rows
		if not row.ref_doctype
		or (
			_erp_action_permissions(row.ref_doctype, user)["view"]
			and frappe.has_permission(row.ref_doctype, "report", user=user, throw=False)
		)
	}


def _saved_user_screen_permissions(user: str, company: str | None) -> tuple[dict, dict] | tuple[None, None]:
	"""Return the selected user's explicit screen rows, if they have a saved matrix."""
	profiles = _profiles_for_scope("User", user, company)
	for profile in profiles:
		rows = frappe.get_all(
			"Mobile App Permission Screen",
			filters={"parent": profile.name, "parenttype": "Mobile App Permission", "parentfield": "screens"},
			fields=["screen_name", "enabled"],
			limit_page_length=0,
		)
		if rows:
			values = {row.screen_name: bool(row.enabled) for row in rows}
			for module_key in MOBILE_MODULES:
				values.setdefault(f"module:{module_key}", values.get(module_key, False))
			return profile, values
	return None, None


def _make_effective_configuration(user: str, roles: list[str], company: str | None, settings: dict) -> dict:
	user_profiles = _profiles_for_scope("User", user, company)
	user_active = bool(user_profiles[0].enabled) if user_profiles else None
	_screen_profile, saved_screens = _saved_user_screen_permissions(user, company)
	user_index = _rule_index(_load_rules(user_profiles))

	all_role_profiles = []
	for role in roles:
		all_role_profiles.extend(_profiles_for_scope("Role", role, company))
	role_profiles = [profile for profile in all_role_profiles if profile.enabled]
	role_indexes = [_rule_index(_load_rules([profile])) for profile in role_profiles]
	default_enabled = bool(settings["default_allow_mobile_access"]) and not bool(user_profiles or all_role_profiles)

	if user_active is False:
		default_enabled = False
		user_index = {("Module", key): [{"enabled": False}] for key in MOBILE_MODULES}
	mobile_access = bool(
		settings["enabled"]
		and user_active is not False
		and (not all_role_profiles or role_profiles or user_active is True)
	)

	modules = {}
	for key in MOBILE_MODULES:
		if key == "face_attendance":
			face_enabled = bool(
				frappe.db.exists("DocType", "Face Attendance Settings")
				and frappe.db.get_single_value("Face Attendance Settings", "enabled")
			)
		else:
			face_enabled = True
		config = _effective_rule(("Module", key), user_index, role_indexes, default_enabled)
		modules[key] = bool(mobile_access and face_enabled and config["enabled"] and _module_erp_access(key, user))

	screens = {}
	for screen_key, module_key in SCREEN_MODULES.items():
		if module_key:
			default_screen_enabled = modules.get(module_key, False)
		else:
			# Dynamic routes are enabled only by an explicit screen rule or a
			# site-wide default when no mobile profiles exist.
			default_screen_enabled = default_enabled
		config = _effective_rule(("Screen", screen_key), user_index, role_indexes, default_screen_enabled)
		screens[screen_key] = bool(mobile_access and config["enabled"])

	doctype_access = {}
	actions = {}
	for doctype in sorted({dt for doctypes in MODULE_DOCTYPES.values() for dt in doctypes}):
		module_keys = _doctype_modules(doctype)
		module_enabled = any(modules.get(key, False) for key in module_keys)
		config = _effective_rule(("Screen", f"doctype:{doctype}"), user_index, role_indexes, module_enabled)
		erp_actions = _erp_action_permissions(doctype, user)
		actions[doctype] = {
			action: bool(module_enabled and config["enabled"] and config.get(ACTION_FIELDS[action]) and erp_actions[action])
			for action in ACTION_FIELDS
		}
		doctype_access[doctype] = actions[doctype]["view"]

	# A saved checkbox matrix is the user's mobile visibility whitelist. It does
	# not grant ERPNext rights: each selected module and DocType is still bounded
	# by the user's real ERPNext permissions.
	if saved_screens is not None:
		registry = _get_mobile_screen_registry()
		for item in registry:
			selected = bool(saved_screens.get(item["key"], False))
			if item["kind"] == "module":
				module_key = item["module_key"]
				face_enabled = True
				if module_key == "face_attendance":
					face_enabled = bool(
						frappe.db.exists("DocType", "Face Attendance Settings")
						and frappe.db.get_single_value("Face Attendance Settings", "enabled")
					)
				modules[module_key] = bool(
					mobile_access and selected and face_enabled and _module_erp_access(module_key, user)
				)
			elif item["kind"] == "route":
				module_key = item.get("module_key")
				screens[item["key"]] = bool(
					mobile_access
					and selected
					and (modules.get(module_key, False) if module_key else True)
				)
			elif item["kind"] == "doctype":
				doctype = item["doctype"]
				module_enabled = any(modules.get(key, False) for key in _doctype_modules(doctype))
				erp_actions = _erp_action_permissions(doctype, user)
				actions[doctype] = {
					action: bool(mobile_access and selected and module_enabled and erp_actions[action])
					for action in ACTION_FIELDS
				}
				doctype_access[doctype] = actions[doctype]["view"]


	# Generic React Navigation containers follow the underlying enabled module,
	# DocType, or report and do not need independent user-facing checkboxes.
	screens["erp_module_documents"] = bool(
		mobile_access and any(allowed for key, allowed in modules.items() if key != "dashboard")
	)
	screens["erp_document_detail"] = bool(mobile_access and any(doctype_access.values()))
	screens["erp_report_detail"] = bool(
		mobile_access and modules.get("reports", False) and screens.get("erp_reports", False)
	)
	if saved_screens is None:
		for route_key, module_key in MODULE_ROUTE_MODULES.items():
			route_config = _effective_rule(
				("Screen", route_key), user_index, role_indexes, modules.get(module_key, False)
			)
			screens[route_key] = bool(
				mobile_access and modules.get(module_key, False) and route_config["enabled"]
			)
	module_routes = {**MODULE_ROUTE_MODULES, "erp_reports": "reports"}
	can_open_module_list = any(
		modules.get(module_key, False) and screens.get(route_key, False)
		for route_key, module_key in module_routes.items()
		if route_key != "my_profile"
	)
	screens["erp_modules"] = bool(mobile_access and can_open_module_list)

	allowed_reports = _allowed_report_names(user)
	reports = {}
	for report_name in allowed_reports:
		key = f"report:{report_name}"
		config = _effective_rule(("Report", key), user_index, role_indexes, modules.get("reports", False))
		reports[report_name] = bool(modules.get("reports", False) and config["enabled"])
	if saved_screens is not None:
		for report_name in allowed_reports:
			reports[report_name] = bool(
				mobile_access
				and modules.get("reports", False)
				and saved_screens.get(f"report:{report_name}", False)
			)

	widget_modules = {
		"attendance_summary": "attendance",
		"leave_balance": "leave",
		"payroll_summary": "payroll",
		"finance_overview": "accounting",
		"quick_actions": "dashboard",
		"recent_activity": "dashboard",
	}
	dashboard_screens = ("employee_home", "admin_dashboard", "owner_dashboard")
	widget_screens = {
		"attendance_summary": ("attendance_hub",),
		"leave_balance": ("leave",),
		"payroll_summary": ("payslips",),
		"finance_overview": ("erp_accounting",),
		"quick_actions": dashboard_screens,
		"recent_activity": dashboard_screens,
	}
	widgets = {}
	for key, module_key in widget_modules.items():
		config = _effective_rule(
			("Dashboard Widget", f"widget:{key}"),
			user_index,
			role_indexes,
			modules.get(module_key, False),
		)
		selected_widget_screen = (
			any(screens.get(screen_key, False) for screen_key in widget_screens[key])
			if saved_screens is not None
			else config["enabled"]
		)
		widgets[key] = bool(mobile_access and modules.get(module_key, False) and selected_widget_screen)

	quick_action_modules = {
		"check_in": ("face_attendance",),
		"check_out": ("face_attendance",),
		"apply_leave": ("leave",),
		"request_correction": ("attendance",),
		"register_face": ("face_attendance", "employees"),
		"add_employee": ("employees",),
		"create_lead": ("crm",),
	}
	quick_action_permissions = {
		# Face Attendance has its own protected API and per-user checks. These
		# toggles control entry points only; its established flow stays untouched.
		"check_in": (None, None),
		"check_out": (None, None),
		"apply_leave": ("Leave Application", "create"),
		"request_correction": ("Attendance", "write"),
		"register_face": ("Employee", "write"),
		"add_employee": ("Employee", "create"),
		"create_lead": ("Lead", "create"),
	}
	quick_action_screens = {
		"check_in": "face_attendance",
		"check_out": "face_attendance",
		"apply_leave": "leave",
		"request_correction": "correction_request",
		"register_face": "face_register",
		"add_employee": "add_employee",
		"create_lead": "leads",
	}
	quick_actions = {}
	for key, required_modules in quick_action_modules.items():
		config = _effective_rule(
			("Quick Action", f"action:{key}"), user_index, role_indexes, default_enabled
		)
		doctype, permission_type = quick_action_permissions[key]
		allowed_by_erp = True if not doctype else bool(
			frappe.db.exists("DocType", doctype)
			and frappe.has_permission(doctype, permission_type, user=user, throw=False)
		)
		selected_action_screen = (
			bool(screens.get(quick_action_screens[key], False))
			if saved_screens is not None
			else config["enabled"]
		)
		quick_actions[key] = bool(
			mobile_access
			and selected_action_screen
			and all(modules.get(module_key, False) for module_key in required_modules)
			and allowed_by_erp
		)

	return {
		"mobile_access": mobile_access,
		"user": user,
		"company": company,
		"app_name": settings["app_name"],
		"default_landing_screen": settings["default_landing_screen"],
		"roles": roles,
		"permission_version": settings["permission_version"],
		"force_permission_refresh": settings.get("force_permission_refresh", False),
		"allow_offline_mode": settings["allow_offline_mode"],
		"session_timeout_minutes": settings.get("session_timeout_minutes", 60),
		"modules": modules,
		"screens": screens,
		"doctypes": doctype_access,
		"actions": actions,
		"reports": reports,
		"widgets": widgets,
		"quick_actions": quick_actions,
		"allowed_companies": [],
		"screen_configuration_enabled": saved_screens is not None,
	}


@frappe.whitelist()
def get_mobile_permission_version():
	"""Return the inexpensive change token used by active mobile clients."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Log in with your ERPNext User account to load mobile permissions."), frappe.PermissionError)

	if not frappe.db.exists("DocType", "Mobile App Settings"):
		version = 1
	else:
		version = int(frappe.db.get_single_value("Mobile App Settings", "permission_version") or 1)
	return {"user": user, "permission_version": version}


@frappe.whitelist()
def get_mobile_permissions(company: str | None = None):
	"""Return mobile visibility and ERPNext-intersected actions for the logged-in user."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Log in with your ERPNext User account to load mobile permissions."), frappe.PermissionError)

	settings = _get_mobile_settings()
	roles = frappe.get_roles(user)
	companies = _accessible_companies()
	selected_company = _choose_company(user, company, companies)
	result = _make_effective_configuration(user, roles, selected_company, settings)
	result["allowed_companies"] = companies
	return result


@frappe.whitelist()
def get_mobile_screen_permissions(user: str | None = None, company: str | None = None):
	"""Return the saved screen registry for an admin, or effective access for the logged-in user."""
	session_user = frappe.session.user
	if not session_user or session_user == "Guest":
		frappe.throw(_("Log in with your ERPNext User account to load mobile permissions."), frappe.PermissionError)
	requested_user = (user or "").strip()
	if requested_user and requested_user != session_user:
		_require_mobile_admin()
	target_user = requested_user or session_user
	_validate_system_user(target_user)

	if target_user == session_user:
		companies = _accessible_companies()
		selected_company = _choose_company(target_user, company, companies)
	else:
		selected_company = company
		if not selected_company:
			try:
				selected_company = frappe.defaults.get_user_default("Company", target_user)
			except Exception:
				selected_company = None

	settings = _get_mobile_settings()
	roles = frappe.get_roles(target_user)
	permissions = _make_effective_configuration(target_user, roles, selected_company, settings)
	permissions["company"] = selected_company
	_, saved_screens = _saved_user_screen_permissions(target_user, selected_company)
	registry = _get_mobile_screen_registry()
	result_screens = []
	for item in registry:
		if item["kind"] == "module":
			enabled = bool(permissions["modules"].get(item["module_key"], False))
			if item.get("route_key") in permissions["screens"]:
				enabled = enabled and bool(permissions["screens"].get(item["route_key"], False))
		elif item["kind"] == "route":
			enabled = bool(permissions["screens"].get(item["key"], False))
		elif item["kind"] == "doctype":
			enabled = bool(permissions["doctypes"].get(item["doctype"], False))
		else:
			enabled = bool(permissions["reports"].get(item["report_name"], False))
		result_screens.append({
			"name": item["key"],
			"label": item["label"],
			"module": item["module_label"],
			"enabled": enabled,
		})

	return {
		"user": target_user,
		"screens": result_screens,
		"configured": saved_screens is not None,
		"permissions": permissions,
	}
