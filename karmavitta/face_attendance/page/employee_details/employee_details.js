frappe.pages["employee-details"].on_page_load = function (wrapper) {
	frappe.employee_details_page = new karmavitta.EmployeeDetailsPage(wrapper);
};

frappe.pages["employee-details"].on_page_show = function () {
	if (frappe.employee_details_page) {
		frappe.employee_details_page.sync_route();
	}
};

frappe.provide("karmavitta");

karmavitta.EmployeeDetailsPage = class EmployeeDetailsPage {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Employee Details"),
			single_column: true,
		});
		this.$main = $(wrapper).find(".layout-main-section");
		this.state = {
			view: "list",
			layout: "table",
			employees: [],
			totals: {},
			profile: null,
			search: "",
			status: "All",
			department: "All",
			branch: "All",
			designation: "All",
			sort: "joined_desc",
			page: 1,
			page_size: 10,
			can_create: true,
		};
		this.ensure_profile_styles();
		$(this.wrapper).addClass("kv-ed-desk");
		$(this.wrapper).find(".page-head").hide();
		$(this.wrapper).find(".page-body").addClass("full-width");
		this.render_shell();
		this.bind();
		this.sync_route();
	}

		sync_route() {
		const route = frappe.get_route() || [];
		const employee = route[1];
		if (employee) {
			this.load_profile(employee);
		} else {
			this.load_directory();
		}
	}

	ensure_profile_styles() {
		if (document.getElementById("kv-ed-profile-css")) return;
		const stylesheet = document.createElement("link");
		stylesheet.id = "kv-ed-profile-css";
		stylesheet.rel = "stylesheet";
		stylesheet.href = "/assets/karmavitta/css/employee_details.css?v=20261001g";
		document.head.appendChild(stylesheet);
	}

	escape(value) {
		return frappe.utils.escape_html(String(value == null || value === "" ? "—" : value));
	}

	badge(badge) {
		const kind = (badge && badge.kind) || "neutral";
		const label = this.escape((badge && badge.label) || "—");
		return `<span class="kv-ed-badge kv-ed-badge--${kind}">${label}</span>`;
	}

	avatar(avatar, size = 44) {
		const image = avatar && avatar.image;
		const raw = (avatar && avatar.initials) || "?";
		const initials = this.escape(raw);
		if (image) {
			return `<img class="kv-ed-avatar" src="${frappe.utils.escape_html(image)}" alt="" style="width:${size}px;height:${size}px">`;
		}
		const tone = this.avatar_tone(raw);
		return `<span class="kv-ed-avatar kv-ed-avatar--fallback" style="width:${size}px;height:${size}px;background:${tone[0]};color:${tone[1]}">${initials}</span>`;
	}

	empty(text) {
		return `<div class="kv-ed-empty">${this.escape(text)}</div>`;
	}

	link_row(doctype, name, label) {
		if (!doctype || !name) return this.escape(label);
		return `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${this.escape(label || name)}</a>`;
	}

	render_shell() {
		this.$main.html(`
			<div class="kv-ed-page">
				<div class="kv-ed-content"></div>
			</div>
		`);
		this.$content = this.$main.find(".kv-ed-content");
	}

	bind() {
		this.$main.on("input", "[data-ed-search]", () => {
			this.state.search = this.$main.find("[data-ed-search]").val() || "";
			this.state.page = 1;
			this.render_directory();
		});
		this.$main.on("change", "[data-ed-status]", () => {
			this.state.status = this.$main.find("[data-ed-status]").val() || "All";
			this.state.page = 1;
			this.render_directory();
		});
		this.$main.on("change", "[data-ed-department]", () => {
			this.state.department = this.$main.find("[data-ed-department]").val() || "All";
			this.state.page = 1;
			this.render_directory();
		});
		this.$main.on("change", "[data-ed-branch]", () => {
			this.state.branch = this.$main.find("[data-ed-branch]").val() || "All";
			this.state.page = 1;
			this.render_directory();
		});
		this.$main.on("change", "[data-ed-designation]", () => {
			this.state.designation = this.$main.find("[data-ed-designation]").val() || "All";
			this.state.page = 1;
			this.render_directory();
		});
		this.$main.on("change", "[data-ed-sort]", () => {
			this.state.sort = this.$main.find("[data-ed-sort]").val() || "joined_desc";
			this.state.page = 1;
			this.render_directory();
		});
		this.$main.on("click", "[data-ed-filter]", (event) => {
			this.state.status = event.currentTarget.dataset.edFilter || "All";
			this.state.page = 1;
			this.render_directory();
		});
		this.$main.on("change", "[data-ed-page-size]", () => {
			const value = this.$main.find("[data-ed-page-size]").val() || "10";
			this.state.page_size = value === "all" ? "all" : Number(value);
			this.state.page = 1;
			this.render_directory();
		});
		this.$main.on("click", "[data-ed-page]", (event) => {
			const action = event.currentTarget.dataset.edPage;
			if (action === "prev") {
				this.state.page -= 1;
			} else if (action === "next") {
				this.state.page += 1;
			} else {
				this.state.page = Number(action) || 1;
			}
			this.render_directory();
		});
		this.$main.on("click", "[data-ed-layout]", (event) => {
			this.state.layout = event.currentTarget.dataset.edLayout || "table";
			this.render_directory();
		});
		this.$main.on("click", "[data-ed-more]", (event) => {
			event.stopPropagation();
			this.$main.find(".kv-ed-more-panel").toggleClass("is-open");
		});
		this.$main.on("click", "[data-ed-menu]", (event) => {
			event.stopPropagation();
			const $menu = $(event.currentTarget).siblings(".kv-ed-menu");
			const wasOpen = !$menu.is("[hidden]");
			this.$main.find(".kv-ed-menu").attr("hidden", true);
			if (!wasOpen) {
				$menu.removeAttr("hidden");
			}
		});
		this.$main.on("click", "[data-ed-employee]", (event) => {
			if ($(event.target).closest(".kv-ed-actions, a, button").length) {
				return;
			}
			const name = event.currentTarget.dataset.edEmployee;
			if (name) {
				frappe.set_route("employee-details", name);
			}
		});
		this.$main.on("click", "[data-ed-open]", (event) => {
			event.stopPropagation();
			const name = event.currentTarget.dataset.edOpen;
			if (name) {
				frappe.set_route("employee-details", name);
			}
		});
		this.$main.on("click", "[data-ed-form]", (event) => {
			event.stopPropagation();
			const name = event.currentTarget.dataset.edForm;
			if (name) {
				frappe.set_route("Form", "Employee", name);
			}
		});
		this.$main.on("click", "[data-ed-new]", () => frappe.new_doc("Employee"));
		this.$main.on("click", "[data-ed-back]", () => frappe.set_route("employee-details"));
		this.$main.on("click", "[data-ed-tab]", (event) => {
			this.show_tab(event.currentTarget.dataset.edTab);
		});
		this.$main.on("click", "[data-ed-open-form]", () => {
			if (this.state.profile) {
				frappe.set_route("Form", "Employee", this.state.profile.profile.employee);
			}
		});
		$(document).on("click.kv-ed", (event) => {
			if (!$(event.target).closest(".kv-ed-more").length) {
				this.$main.find(".kv-ed-more-panel").removeClass("is-open");
			}
			if (!$(event.target).closest(".kv-ed-actions").length) {
				this.$main.find(".kv-ed-menu").attr("hidden", true);
			}
		});
	}

	set_busy(busy) {
		this.page.set_indicator(busy ? __("Loading") : "", busy ? "orange" : "");
	}

	load_directory() {
		this.state.view = "list";
		this.page.set_title(__("Employee Details"));
		this.set_busy(true);
		frappe.call({
			method: "karmavitta.hr.employee_details.get_employee_directory",
			args: { search: "", status: "All", limit: 0 },
		}).then((r) => {
			this.set_busy(false);
			const message = r.message || {};
			this.state.employees = (message.employees || []).map((emp) => ({
				...emp,
				employee_id: emp.employee_id || emp.employee || emp.name,
			}));
			this.state.totals = message.totals || {};
			this.state.can_create = message.can_create !== false;
			this.render_directory();
		}).catch(() => {
			this.set_busy(false);
			this.$content.html(this.empty(__("Unable to load employees.")));
		});
	}

	load_profile(employee) {
		this.state.view = "profile";
		this.set_busy(true);
		frappe.call({
			method: "karmavitta.hr.employee_details.get_employee_profile",
			args: { employee },
		}).then((r) => {
			this.set_busy(false);
			this.state.profile = r.message;
			this.render_profile();
		}).catch(() => {
			this.set_busy(false);
			this.$content.html(this.empty(__("Unable to load this employee profile.")));
		});
	}

	icon(name) {
		const paths = {
			people: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M9 11a3.5 3.5 0 1 0-3.5-3.5A3.5 3.5 0 0 0 9 11Zm6.5 1a3 3 0 1 0-3-3 3 3 0 0 0 3 3ZM9 13c-3.04 0-6 1.46-6 3.5V19h9.2a5.7 5.7 0 0 1-.2-1.5c0-1.7.7-3.2 1.8-4.3A8.3 8.3 0 0 0 9 13Zm6.5 1c-.7 0-1.4.08-2 .24A4.2 4.2 0 0 1 16.5 18c0 .35-.04.69-.1 1H22v-1.2c0-1.7-2.46-2.8-6.5-2.8Z"/></svg>`,
			person: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4Zm0 2c-3.3 0-8 1.7-8 5v1h16v-1c0-3.3-4.7-5-8-5Z"/></svg>`,
			plane: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5Z"/></svg>`,
			minus: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M7 11h10v2H7z"/></svg>`,
			search: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14Zm9 3-4.3-4.3"/></svg>`,
			filter: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" d="M4 5h16l-6 7.2V19l-4 2v-8.8L4 5Z"/></svg>`,
			sort: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" d="M8 7v12M8 7 5 10M8 7l3 3M16 17V5M16 17l-3-3M16 17l3-3"/></svg>`,
			list: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 6h2v2H4V6Zm4 0h12v2H8V6ZM4 11h2v2H4v-2Zm4 0h12v2H8v-2ZM4 16h2v2H4v-2Zm4 0h12v2H8v-2Z"/></svg>`,
			grid: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M4 4h7v7H4V4Zm9 0h7v7h-7V4ZM4 13h7v7H4v-7Zm9 0h7v7h-7v-7Z"/></svg>`,
			dots: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="6" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="18" r="1.6" fill="currentColor"/></svg>`,
			calendar: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="17" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M7.5 3v4M16.5 3v4M4 9.5h16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
			leaf: `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M20.8 3.2C11.3 3.4 5.1 5 3.6 10.7c-.9 3.3 1.6 6.3 4.9 5.5 5.7-1.4 9.4-7.1 12.3-13ZM4 21c2.2-5.4 6.1-8.6 11.3-11.3C11.8 14 8 17.2 4 21Z"/></svg>`,
			wallet: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="15" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3.5 9h17M16 14h.01" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>`,
			document: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3.5h7l5 5v12H7a2 2 0 0 1-2-2v-13a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M14 3.8v5h5M9 13h6M9 16.5h6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
			chart: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V12h4v8M10 20V5h4v15M16 20V9h4v11" fill="currentColor"/></svg>`,
			id: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="8" cy="11" r="2" fill="currentColor"/><path d="M5.5 16c.4-1.7 1.3-2.5 2.5-2.5s2.1.8 2.5 2.5M13 10h5M13 14h5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`,
			org: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="5" rx="1" fill="none" stroke="currentColor" stroke-width="1.7"/><rect x="3" y="16" width="6" height="5" rx="1" fill="none" stroke="currentColor" stroke-width="1.7"/><rect x="15" y="16" width="6" height="5" rx="1" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 8v4M6 16v-4h12v4" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>`,
			briefcase: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="7" width="18" height="14" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3.5 12h17M10 12v2h4v-2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>`,
			phone: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3.5h10a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-13a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M10 17.5h4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
			pin: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="10" r="2.2" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>`,
			shield: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 20 6v5c0 5-3.2 8.3-8 10-4.8-1.7-8-5-8-10V6l8-3Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="m9 12 2 2 4-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
			back: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14.5 5-7 7 7 7M8 12h12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
		};
		return paths[name] || "";
	}

	avatar_tone(initials) {
		const palette = [
			["#FFE7D1", "#E07A2F"],
			["#E9E1FF", "#7A57C5"],
			["#E4EEFF", "#3B6FD8"],
			["#FFE3EC", "#D45B7C"],
			["#FFF1D0", "#D4922A"],
			["#DFF6EA", "#1C9A62"],
		];
		const key = String(initials || "?");
		let hash = 0;
		for (let i = 0; i < key.length; i++) {
			hash = (hash + key.charCodeAt(i) * (i + 3)) % palette.length;
		}
		return palette[hash];
	}

	option_list(field) {
		const values = new Set();
		(this.state.employees || []).forEach((emp) => {
			if (emp[field]) {
				values.add(emp[field]);
			}
		});
		return Array.from(values).sort((a, b) => String(a).localeCompare(String(b)));
	}

	select_options(values, current, allLabel) {
		const options = [`<option value="All">${this.escape(allLabel)}</option>`];
		values.forEach((value) => {
			const selected = current === value ? " selected" : "";
			options.push(`<option value="${frappe.utils.escape_html(value)}"${selected}>${this.escape(value)}</option>`);
		});
		return options.join("");
	}

	visible_employees() {
		const query = (this.state.search || "").trim().toLowerCase();
		const rows = (this.state.employees || []).filter((emp) => {
			if (this.state.status === "Inactive") {
				if (!["Inactive", "Left"].includes(emp.status)) {
					return false;
				}
			} else if (this.state.status && this.state.status !== "All" && (emp.status || "") !== this.state.status) {
				return false;
			}
			if (this.state.department !== "All" && (emp.department || "") !== this.state.department) {
				return false;
			}
			if (this.state.branch !== "All" && (emp.branch || "") !== this.state.branch) {
				return false;
			}
			if (this.state.designation !== "All" && (emp.designation || "") !== this.state.designation) {
				return false;
			}
			if (!query) {
				return true;
			}
			const blob = [emp.employee_name, emp.employee_id, emp.name, emp.department, emp.designation, emp.branch]
				.join(" ")
				.toLowerCase();
			return blob.includes(query);
		});
		const sort = this.state.sort || "joined_desc";
		rows.sort((a, b) => {
			if (sort === "name_asc" || sort === "name_desc") {
				const cmp = String(a.employee_name || "").localeCompare(String(b.employee_name || ""));
				return sort === "name_asc" ? cmp : -cmp;
			}
			const cmp = String(a.date_of_joining_iso || "").localeCompare(String(b.date_of_joining_iso || ""));
			return sort === "joined_asc" ? cmp : -cmp;
		});
		return rows;
	}

	status_pill(emp) {
		const badge = emp.badge || { label: emp.status || "—", kind: "neutral" };
		const kind = badge.kind || "neutral";
		return `<span class="kv-ed-pill kv-ed-pill--${kind}"><i></i>${this.escape(badge.label)}</span>`;
	}

	actions_menu(name) {
		const safe = frappe.utils.escape_html(name);
		return `
			<div class="kv-ed-actions">
				<button type="button" class="kv-ed-action-btn" data-ed-menu="${safe}" aria-label="${__("Actions")}">${this.icon("dots")}</button>
				<div class="kv-ed-menu" hidden>
					<button type="button" data-ed-open="${safe}">${__("View profile")}</button>
					<button type="button" data-ed-form="${safe}">${__("Open Employee form")}</button>
				</div>
			</div>
		`;
	}

	render_directory() {
		const totals = this.state.totals || {};
		const filteredEmployees = this.visible_employees();
		const total = filteredEmployees.length;
		const pageSize = this.state.page_size === "all" ? Math.max(total, 1) : Math.max(Number(this.state.page_size) || 10, 1);
		const pageCount = Math.max(Math.ceil(total / pageSize), 1);
		const page = Math.min(Math.max(Number(this.state.page) || 1, 1), pageCount);
		this.state.page = page;
		const startIndex = total ? (page - 1) * pageSize : 0;
		const endIndex = Math.min(startIndex + pageSize, total);
		const employees = filteredEmployees.slice(startIndex, endIndex);
		const searchFocused = document.activeElement && document.activeElement.matches && document.activeElement.matches("[data-ed-search]");
		const caret = searchFocused ? document.activeElement.selectionStart : null;
		const rows = employees.map((emp) => `
			<tr class="kv-ed-row" data-ed-employee="${frappe.utils.escape_html(emp.name)}">
				<td>
					<div class="kv-ed-person">
						${this.avatar(emp.avatar, 36)}
						<div class="kv-ed-person-name">${this.escape(emp.employee_name)}</div>
					</div>
				</td>
				<td class="kv-ed-id">${this.escape(emp.employee_id || emp.name)}</td>
				<td>${this.status_pill(emp)}</td>
				<td>${this.escape(emp.designation)}</td>
				<td>${this.escape(emp.department)}</td>
				<td>${this.escape(emp.branch)}</td>
				<td>${this.escape(emp.date_of_joining)}</td>
				<td class="kv-ed-actions-cell">${this.actions_menu(emp.name)}</td>
			</tr>
		`).join("");
		const cards = employees.map((emp) => `
			<article class="kv-ed-grid-card" data-ed-employee="${frappe.utils.escape_html(emp.name)}">
				<div class="kv-ed-grid-top">
					${this.avatar(emp.avatar, 44)}
					${this.actions_menu(emp.name)}
				</div>
				<div class="kv-ed-person-name">${this.escape(emp.employee_name)}</div>
				<div class="kv-ed-id">${this.escape(emp.employee_id || emp.name)}</div>
				<div class="kv-ed-grid-meta">${this.status_pill(emp)}</div>
				<div class="kv-ed-muted">${this.escape(emp.designation)} · ${this.escape(emp.department)}</div>
			</article>
		`).join("");
		const sortOptions = [
			["joined_desc", __("Joined Date (Newest)")],
			["joined_asc", __("Joined Date (Oldest)")],
			["name_asc", __("Name (A–Z)")],
			["name_desc", __("Name (Z–A)")],
		];
		const statusOptions = ["All", "Active", "On Leave", "Inactive", "Suspended", "Left"];
		const pageSizeOptions = [10, 20, 50]
			.map((size) => `<option value="${size}" ${this.state.page_size === size ? "selected" : ""}>${size}</option>`)
			.concat([`<option value="all" ${this.state.page_size === "all" ? "selected" : ""}>${__("All")}</option>`])
			.join("");
		const pageNumbers = [];
		const firstPage = Math.max(1, page - 2);
		const lastPage = Math.min(pageCount, page + 2);
		if (firstPage > 1) {
			pageNumbers.push(`<button type="button" class="kv-ed-page-btn" data-ed-page="1">1</button>`);
			if (firstPage > 2) pageNumbers.push(`<span class="kv-ed-page-ellipsis">…</span>`);
		}
		for (let pageNumber = firstPage; pageNumber <= lastPage; pageNumber++) {
			pageNumbers.push(`<button type="button" class="kv-ed-page-btn${pageNumber === page ? " is-active" : ""}" data-ed-page="${pageNumber}"${pageNumber === page ? ' aria-current="page"' : ""}>${pageNumber}</button>`);
		}
		if (lastPage < pageCount) {
			if (lastPage < pageCount - 1) pageNumbers.push(`<span class="kv-ed-page-ellipsis">…</span>`);
			pageNumbers.push(`<button type="button" class="kv-ed-page-btn" data-ed-page="${pageCount}">${pageCount}</button>`);
		}
		const newButton = this.state.can_create
			? `<button type="button" class="kv-ed-new" data-ed-new><span>+</span>${__("New Employee")}</button>`
			: "";

		this.$content.html(`
			<div class="kv-ed-hero">
				<div>
					<div class="kv-ed-crumb">${__("HR Directory")} <span>›</span> ${__("Employee Details")}</div>
					<h1>${__("Employee Details")}</h1>
				</div>
				${newButton}
			</div>
			<div class="kv-ed-cards kv-ed-cards--totals">
				${this.metric_card("people", "total", __("Total Employees"), totals.all || 0, __("All records you can access"), "All")}
				${this.metric_card("person", "active", __("Active"), totals.active || 0, __("Currently employed"), "Active")}
				${this.metric_card("plane", "leave", __("On Leave"), totals.on_leave || 0, __("Status On Leave"), "On Leave")}
				${this.metric_card("minus", "inactive", __("Inactive / Left"), totals.inactive || 0, __("Not currently active"), "Inactive")}
			</div>
			<div class="kv-ed-toolbar">
				<label class="kv-ed-search">
					${this.icon("search")}
					<input data-ed-search type="search" placeholder="${__("Search name, ID, department or designation...")}" value="${frappe.utils.escape_html(this.state.search || "")}">
				</label>
				<select class="kv-ed-select" data-ed-department>
					${this.select_options(this.option_list("department"), this.state.department, __("All Departments"))}
				</select>
				<select class="kv-ed-select" data-ed-status>
					${statusOptions.map((status) => {
						const label = status === "All" ? __("All Status") : __(status);
						return `<option value="${status}" ${this.state.status === status ? "selected" : ""}>${label}</option>`;
					}).join("")}
				</select>
				<div class="kv-ed-more">
					<button type="button" class="kv-ed-select kv-ed-more-btn" data-ed-more>${this.icon("filter")}<span>${__("More Filters")}</span></button>
					<div class="kv-ed-more-panel">
						<label>${__("Branch")}
							<select data-ed-branch>${this.select_options(this.option_list("branch"), this.state.branch, __("All Branches"))}</select>
						</label>
						<label>${__("Designation")}
							<select data-ed-designation>${this.select_options(this.option_list("designation"), this.state.designation, __("All Designations"))}</select>
						</label>
					</div>
				</div>
			</div>
			<section class="kv-ed-board">
				<div class="kv-ed-board-head">
					<div>
						<h2>${total} ${total === 1 ? __("Employee") : __("Employees")}</h2>
						<p>${total === (this.state.employees || []).length ? __("Showing all employee records") : __("Showing filtered employee records")}</p>
					</div>
					<div class="kv-ed-board-tools">
						<label class="kv-ed-sort">
							${this.icon("sort")}
							<span>${__("Sort by")}</span>
							<select data-ed-sort>
								${sortOptions.map(([value, label]) => `<option value="${value}" ${this.state.sort === value ? "selected" : ""}>${label}</option>`).join("")}
							</select>
						</label>
						<div class="kv-ed-layout">
							<button type="button" class="${this.state.layout === "table" ? "is-active" : ""}" data-ed-layout="table" aria-label="${__("List view")}">${this.icon("list")}</button>
							<button type="button" class="${this.state.layout === "grid" ? "is-active" : ""}" data-ed-layout="grid" aria-label="${__("Grid view")}">${this.icon("grid")}</button>
						</div>
					</div>
				</div>
				${this.state.layout === "grid"
					? `<div class="kv-ed-grid-view">${cards || this.empty(__("No employees found."))}</div>`
					: `<div class="kv-ed-table-wrap">
						<table class="kv-ed-table">
							<thead>
								<tr>
									<th>${__("Employee")}</th>
									<th>${__("Employee ID")}</th>
									<th>${__("Status")}</th>
									<th>${__("Designation")}</th>
									<th>${__("Department")}</th>
									<th>${__("Branch")}</th>
									<th>${__("Joined Date")}</th>
									<th class="kv-ed-actions-cell">${__("Actions")}</th>
								</tr>
							</thead>
							<tbody>${rows || `<tr><td colspan="8">${this.empty(__("No employees found."))}</td></tr>`}</tbody>
						</table>
					</div>`}
				<div class="kv-ed-board-foot">
					<div class="kv-ed-page-summary">
						<span>${__("Showing {0} to {1} of {2} employees", [total ? startIndex + 1 : 0, endIndex, total])}</span>
						<label class="kv-ed-page-size">${__("Rows per page")}
							<select data-ed-page-size>${pageSizeOptions}</select>
						</label>
					</div>
					<nav class="kv-ed-pagination" aria-label="${__("Employee pages")}">
						<button type="button" class="kv-ed-page-btn" data-ed-page="prev" ${page <= 1 ? "disabled" : ""}>${__("Previous")}</button>
						${pageNumbers.join("")}
						<button type="button" class="kv-ed-page-btn" data-ed-page="next" ${page >= pageCount ? "disabled" : ""}>${__("Next")}</button>
					</nav>
				</div>
			</section>
		`);
		if (searchFocused) {
			const input = this.$main.find("[data-ed-search]").get(0);
			if (input) {
				input.focus();
				if (caret != null) {
					input.setSelectionRange(caret, caret);
				}
			}
		}
	}

	metric_card(icon, tone, title, value, hint, filter) {
		const active = this.state.status === filter ? " is-active" : "";
		return `
			<button type="button" class="kv-ed-stat-card kv-ed-stat-card--${tone}${active}" data-ed-filter="${frappe.utils.escape_html(filter || "All")}">
				<span class="kv-ed-stat-icon">${this.icon(icon)}</span>
				<span class="kv-ed-stat-copy">
					<span class="kv-ed-card-label">${this.escape(title)}</span>
					<span class="kv-ed-card-value">${this.escape(value)}</span>
					<span class="kv-ed-muted">${this.escape(hint)}</span>
				</span>
			</button>
		`;
	}

	kv(label, value) {
		return `
			<div class="kv-ed-kv">
				<div class="kv-ed-kv-label">${this.escape(label)}</div>
				<div class="kv-ed-kv-value">${value}</div>
			</div>
		`;
	}

	table(headers, rows_html) {
		if (!rows_html) return this.empty(__("No records"));
		return `
			<div class="kv-ed-table-wrap">
				<table class="kv-ed-table">
					<thead><tr>${headers.map((h) => `<th>${this.escape(h)}</th>`).join("")}</tr></thead>
					<tbody>${rows_html}</tbody>
				</table>
			</div>
		`;
	}

	render_profile() {
		const data = this.state.profile || {};
		const p = data.profile || {};
		const emp = data.employee || {};
		const cards = data.cards || {};
		this.page.set_title(p.full_name || __("Employee Details"));
		this.$content.html(`
			<div class="kv-ed-profile-heading">
				<div>
					<div class="kv-ed-crumb"><button type="button" data-ed-back>${__("HR Directory")}</button><span>›</span>${__("Employee Details")}</div>
					<h1>${this.escape(p.full_name)}</h1>
				</div>
				<div class="kv-ed-profile-actions">
					<button class="kv-ed-back" data-ed-back type="button">${this.icon("back")} ${__("Back to Employees")}</button>
					<button class="kv-ed-open-form" data-ed-open-form type="button">${this.icon("briefcase")} ${__("Open Employee Form")}</button>
				</div>
			</div>
			<section class="kv-ed-profile">
				${this.avatar(p.avatar, 64)}
				<div class="kv-ed-profile-main">
					<div class="kv-ed-profile-title">
						<h2>${this.escape(p.full_name)}</h2>
						${this.badge(p.badge)}
					</div>
					<div class="kv-ed-profile-meta">
						${this.profile_meta("id", p.employee_id)}
						${this.profile_meta("org", p.company)}
						${this.profile_meta("document", p.designation)}
						${this.profile_meta("person", p.department)}
						${this.profile_meta("org", `${__("Reports To")}: ${p.reports_to_name || p.reports_to || "—"}`)}
						${this.profile_meta("calendar", `${__("Joined")}: ${p.date_of_joining || "—"}`)}
						${this.profile_meta("briefcase", p.employment_type)}
					</div>
				</div>
			</section>
			<div class="kv-ed-cards">
				${this.summary_card(__("Attendance"), [
					[__("Present days"), cards.attendance && cards.attendance.present_days],
					[__("Absent days"), cards.attendance && cards.attendance.absent_days],
					[__("Late entries"), cards.attendance && cards.attendance.late_entries],
					[__("Current status"), cards.attendance && cards.attendance.current_status],
				], "calendar", "blue")}
				${this.summary_card(__("Leave"), [
					[__("Total leave balance"), cards.leave && cards.leave.total_balance],
					[__("Leave taken"), cards.leave && cards.leave.leave_taken],
					[__("Upcoming approved"), (cards.leave && cards.leave.upcoming && cards.leave.upcoming.length) || 0],
				], "leaf", "green")}
				${this.summary_card(__("Payroll"), [
					[__("Salary structure"), cards.payroll && cards.payroll.salary_structure],
					[__("Latest salary slip"), cards.payroll && cards.payroll.latest_slip],
					[__("Payroll status"), cards.payroll && cards.payroll.payroll_status],
				], "wallet", "orange")}
				${this.summary_card(__("Documents"), [
					[__("Total documents"), cards.documents && cards.documents.total],
					[__("Expiring"), cards.documents && cards.documents.expiring],
					[__("Expired"), cards.documents && cards.documents.expired],
				], "document", "purple")}
				${this.summary_card(__("Performance"), [
					[__("Latest appraisal"), (cards.performance && cards.performance.latest_rating) ?? "—"],
					[__("Active goals / KPIs"), cards.performance && cards.performance.active_goals],
					[__("Training status"), cards.performance && cards.performance.training_status],
				], "chart", "red")}
			</div>
			<div class="kv-ed-tabs" role="tablist">
				${["overview","employment","attendance","payroll","documents","performance","activity"].map((id, idx) => {
					const labels = [__("Overview"), __("Employment"), __("Attendance & Leave"), __("Payroll"), __("Documents"), __("Performance"), __("Activity")];
					return `<button type="button" class="kv-ed-tab ${idx === 0 ? "is-active" : ""}" data-ed-tab="${id}">${labels[idx]}</button>`;
				}).join("")}
			</div>
			<div class="kv-ed-tab-panels">
				<section data-ed-panel="overview">${this.render_overview(emp)}</section>
				<section data-ed-panel="employment" hidden>${this.render_employment(p, emp)}</section>
				<section data-ed-panel="attendance" hidden>${this.render_attendance(cards)}</section>
				<section data-ed-panel="payroll" hidden>${this.render_payroll(cards.payroll || {})}</section>
				<section data-ed-panel="documents" hidden>${this.render_documents(cards.documents || {})}</section>
				<section data-ed-panel="performance" hidden>${this.render_performance(cards.performance || {})}</section>
				<section data-ed-panel="activity" hidden>${this.render_activity(data.activity || [])}</section>
			</div>
		`);
	}

	profile_meta(icon, label) {
		return `<span class="kv-ed-profile-meta-item">${this.icon(icon)}<span>${this.escape(label)}</span></span>`;
	}

	panel_heading(icon, title, tone) {
		return `<div class="kv-ed-panel-heading"><span class="kv-ed-panel-icon kv-ed-panel-icon--${tone}">${this.icon(icon)}</span><h3>${this.escape(title)}</h3></div>`;
	}

	summary_card(title, rows, icon, tone) {
		return `
			<div class="kv-ed-card kv-ed-summary-card kv-ed-summary-card--${tone}">
				<div class="kv-ed-summary-heading">
					<span class="kv-ed-summary-icon">${this.icon(icon)}</span>
					<div class="kv-ed-card-label">${this.escape(title)}</div>
				</div>
				${(rows || []).map(([label, value]) => `
					<div class="kv-ed-stat">
						<span>${this.escape(label)}</span>
						<strong>${this.escape(value)}</strong>
					</div>
				`).join("")}
			</div>
		`;
	}

	render_overview(emp) {
		return `
			<div class="kv-ed-grid">
				<div class="kv-ed-panel">
					${this.panel_heading("person", __("Personal Information"), "orange")}
					${this.kv(__("Full name"), this.escape(emp.employee_name))}
					${this.kv(__("Gender"), this.escape(emp.gender))}
					${this.kv(__("Date of birth"), this.escape(frappe.format(emp.date_of_birth, { fieldtype: "Date" })))}
					${this.kv(__("Marital status"), this.escape(emp.marital_status))}
					${this.kv(__("Blood group"), this.escape(emp.blood_group))}
				</div>
				<div class="kv-ed-panel">
					${this.panel_heading("phone", __("Contact Information"), "blue")}
					${this.kv(__("Mobile"), this.escape(emp.cell_number))}
					${this.kv(__("Company email"), this.escape(emp.company_email))}
					${this.kv(__("Personal email"), this.escape(emp.personal_email))}
					${this.kv(__("Preferred email"), this.escape(emp.prefered_email))}
					${this.kv(__("User ID"), this.escape(emp.user_id))}
				</div>
				<div class="kv-ed-panel">
					${this.panel_heading("pin", __("Address"), "green")}
					<div class="kv-ed-address-block"><span>${__("Current address")}</span><strong>${this.escape(emp.current_address)}</strong></div>
					<div class="kv-ed-address-block"><span>${__("Permanent address")}</span><strong>${this.escape(emp.permanent_address)}</strong></div>
				</div>
				<div class="kv-ed-panel">
					${this.panel_heading("shield", __("Emergency Contact"), "red")}
					${this.kv(__("Person to contact"), this.escape(emp.person_to_be_contacted))}
					${this.kv(__("Relation"), this.escape(emp.relation))}
					${this.kv(__("Emergency phone"), this.escape(emp.emergency_phone_number))}
				</div>
			</div>
		`;
	}

	render_employment(p, emp) {
		return `
			<div class="kv-ed-grid">
				<div class="kv-ed-panel">
					<h3>${__("Employment")}</h3>
					${this.kv(__("Company"), this.escape(p.company))}
					${this.kv(__("Department"), this.escape(p.department))}
					${this.kv(__("Designation"), this.escape(p.designation))}
					${this.kv(__("Branch"), this.escape(p.branch))}
					${this.kv(__("Grade"), this.escape(p.grade))}
					${this.kv(__("Employment Type"), this.escape(p.employment_type))}
				</div>
				<div class="kv-ed-panel">
					<h3>${__("Work setup")}</h3>
					${this.kv(__("Work location / Branch"), this.escape(p.branch))}
					${this.kv(__("Shift"), this.escape(p.shift))}
					${this.kv(__("Reports To"), this.escape(p.reports_to_name || p.reports_to))}
					${this.kv(__("Holiday List"), this.escape(p.holiday_list))}
					${this.kv(__("Date of Joining"), this.escape(p.date_of_joining))}
					${this.kv(__("Attendance Device ID"), this.escape(emp.attendance_device_id))}
				</div>
			</div>
		`;
	}

	render_attendance(cards) {
		const att = cards.attendance || {};
		const leave = cards.leave || {};
		const history = (att.history || []).map((row) => `
			<tr>
				<td>${this.link_row("Attendance", row.name, row.date)}</td>
				<td>${this.escape(row.status)}</td>
				<td>${row.late ? this.badge({ label: __("Late"), kind: "warning" }) : "—"}</td>
				<td>${this.escape(row.hours)}</td>
				<td>${this.escape(row.shift)}</td>
			</tr>
		`).join("");
		const balances = (leave.balances || []).map((row) => `
			<tr>
				<td>${this.escape(row.leave_type)}</td>
				<td>${this.escape(row.allocated)}</td>
				<td>${this.escape(row.taken)}</td>
				<td>${this.escape(row.remaining)}</td>
			</tr>
		`).join("");
		const applications = (leave.applications || []).map((row) => `
			<tr>
				<td>${this.link_row("Leave Application", row.name, row.leave_type)}</td>
				<td>${this.escape(row.from_date)} – ${this.escape(row.to_date)}</td>
				<td>${this.escape(row.days)}</td>
				<td>${this.badge(_status_from_text(row.status))}</td>
			</tr>
		`).join("");
		return `
			<div class="kv-ed-grid">
				<div class="kv-ed-panel kv-ed-panel--wide">
					<h3>${__("Attendance history")}</h3>
					<p class="kv-ed-muted">${__("Monthly summary")} ${this.escape(att.month_start)} – ${this.escape(att.month_end)}</p>
					${this.table([__("Date"), __("Status"), __("Late"), __("Hours"), __("Shift")], history)}
				</div>
				<div class="kv-ed-panel">
					<h3>${__("Leave balance")}</h3>
					${this.table([__("Type"), __("Allocated"), __("Taken"), __("Remaining")], balances)}
				</div>
				<div class="kv-ed-panel kv-ed-panel--wide">
					<h3>${__("Leave applications")}</h3>
					${this.table([__("Leave"), __("Dates"), __("Days"), __("Status")], applications)}
				</div>
			</div>
		`;
	}

	render_payroll(payroll) {
		const slips = (payroll.slips || []).map((row) => `
			<tr>
				<td>${this.link_row("Salary Slip", row.name, row.name)}</td>
				<td>${this.escape(row.period)}</td>
				<td>${this.escape(row.status)}</td>
				<td>${this.escape(row.gross_pay)}</td>
				<td>${this.escape(row.net_pay)}</td>
			</tr>
		`).join("");
		const assignments = (payroll.assignments || []).map((row) => `
			<tr>
				<td>${this.link_row("Salary Structure Assignment", row.name, row.salary_structure)}</td>
				<td>${this.escape(row.from_date)}</td>
				<td>${this.escape(row.base)}</td>
			</tr>
		`).join("");
		const bank = payroll.bank || {};
		return `
			<div class="kv-ed-grid">
				<div class="kv-ed-panel">
					<h3>${__("Bank details")}</h3>
					${this.kv(__("Salary mode"), this.escape(bank.mode))}
					${this.kv(__("Bank"), this.escape(bank.bank_name))}
					${this.kv(__("Account"), this.escape(bank.account))}
					${this.kv(__("IBAN"), this.escape(bank.iban))}
					${this.kv(__("Payroll cost center"), this.escape(payroll.cost_center))}
					${this.kv(__("CTC"), this.escape(bank.ctc))}
				</div>
				<div class="kv-ed-panel kv-ed-panel--wide">
					<h3>${__("Salary structure")}</h3>
					${this.table([__("Structure"), __("From date"), __("Base")], assignments)}
					<h3 class="kv-ed-sub">${__("Salary history")}</h3>
					${this.table([__("Slip"), __("Period"), __("Status"), __("Gross"), __("Net")], slips)}
				</div>
			</div>
		`;
	}

	render_documents(documents) {
		const rows = (documents.items || []).map((row) => {
			const warn = row.status && (row.status.kind === "warning" || row.status.kind === "danger") ? "kv-ed-doc-warn" : "";
			const title = row.file_url
				? `<a href="${frappe.utils.escape_html(row.file_url)}" target="_blank">${this.escape(row.title)}</a>`
				: this.escape(row.title);
			return `
				<tr class="${warn}">
					<td>${title}</td>
					<td>${this.escape(row.number)}</td>
					<td>${this.escape(row.issue_date)}</td>
					<td>${this.escape(row.expiry_date)}</td>
					<td>${this.badge(row.status)}</td>
				</tr>
			`;
		}).join("");
		return `
			<div class="kv-ed-panel">
				<h3>${__("Employee documents")}</h3>
				<p class="kv-ed-muted">${__("Passport and identity fields come from Employee. Files attached to the Employee record are listed as CV, education, and certificates. Customize Form can add Qatar ID, visa, and permit fields.")}</p>
				${this.table([__("Document"), __("Number"), __("Issue date"), __("Expiry date"), __("Status")], rows)}
			</div>
		`;
	}

	render_performance(perf) {
		const goals = (perf.goals || []).map((row) => `
			<tr>
				<td>${this.link_row("Goal", row.name, row.goal)}</td>
				<td>${this.escape(row.status)}</td>
				<td>${this.escape(row.progress)}%</td>
			</tr>
		`).join("");
		const appraisals = (perf.appraisals || []).map((row) => `
			<tr>
				<td>${this.link_row("Appraisal", row.name, row.name)}</td>
				<td>${this.escape(row.cycle)}</td>
				<td>${this.escape(row.score)}</td>
				<td>${this.escape(row.status)}</td>
			</tr>
		`).join("");
		const skills = (perf.skills || []).map((row) => `
			<tr><td>${this.escape(row.skill)}</td><td>${this.escape(row.proficiency)}</td></tr>
		`).join("");
		const training = (perf.training || []).map((row) => `
			<tr>
				<td>${this.link_row("Training Event", row.name, row.event)}</td>
				<td>${this.escape(row.status)}</td>
			</tr>
		`).join("");
		return `
			<div class="kv-ed-grid">
				<div class="kv-ed-panel kv-ed-panel--wide">
					<h3>${__("Employee goals / KPIs")}</h3>
					${this.table([__("Goal"), __("Status"), __("Progress")], goals)}
				</div>
				<div class="kv-ed-panel">
					<h3>${__("Appraisals")}</h3>
					${this.table([__("Appraisal"), __("Cycle"), __("Rating"), __("Status")], appraisals)}
				</div>
				<div class="kv-ed-panel">
					<h3>${__("Skills")}</h3>
					${this.table([__("Skill"), __("Proficiency")], skills)}
				</div>
				<div class="kv-ed-panel">
					<h3>${__("Training")}</h3>
					${this.table([__("Event"), __("Status")], training)}
				</div>
			</div>
		`;
	}

	render_activity(items) {
		if (!items.length) return this.empty(__("No recent activity"));
		return `
			<div class="kv-ed-timeline">
				${items.map((item) => `
					<div class="kv-ed-timeline-item">
						<div class="kv-ed-timeline-when">${this.escape(item.when)}</div>
						<div class="kv-ed-timeline-title">${this.escape(item.title)}</div>
						<div class="kv-ed-muted">${item.doctype && item.name ? this.link_row(item.doctype, item.name, item.detail) : this.escape(item.detail)}</div>
					</div>
				`).join("")}
			</div>
		`;
	}

	show_tab(tab) {
		this.$main.find("[data-ed-tab]").removeClass("is-active");
		this.$main.find(`[data-ed-tab="${tab}"]`).addClass("is-active");
		this.$main.find("[data-ed-panel]").attr("hidden", true);
		this.$main.find(`[data-ed-panel="${tab}"]`).removeAttr("hidden");
	}
};

function _status_from_text(status) {
	const value = String(status || "");
	const lower = value.toLowerCase();
	if (["approved", "present", "active"].includes(lower)) return { label: value, kind: "success" };
	if (["rejected", "cancelled", "absent", "expired"].includes(lower)) return { label: value, kind: "danger" };
	if (["open", "pending", "draft", "late"].includes(lower)) return { label: value, kind: "warning" };
	return { label: value || "—", kind: "neutral" };
}
