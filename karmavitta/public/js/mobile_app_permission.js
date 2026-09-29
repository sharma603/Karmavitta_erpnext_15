const CATALOG_METHOD = 'karmavitta.api.mobile_permissions.get_mobile_permission_catalog';
const MATRIX_METHOD = 'karmavitta.api.mobile_permissions.get_mobile_permission_matrix';
const USER_METHOD = 'karmavitta.api.mobile_permissions.get_mobile_user_summary';
const CHILD_FIELD = 'screens';

function escapeHtml(value) {
	return String(value || '').replace(/[&<>"']/g, character => ({
		'&': '&amp;',
		'<': '&lt;',
		'>': '&gt;',
		'"': '&quot;',
		"'": '&#39;',
	})[character]);
}

function setUserQuery(frm) {
	frm.set_query('user', () => ({
		filters: {user_type: 'System User', enabled: 1},
	}));
}

function showUserSummary(frm, user, requestId) {
	const field = frm.fields_dict.user_summary;
	if (!field) return;
	if (!user) {
		field.$wrapper.html('<div class="karmavitta-permission-empty">Choose an enabled ERPNext System User to load their roles and mobile screens.</div>');
		return;
	}
	field.$wrapper.html('<div class="karmavitta-permission-empty">Loading user details…</div>');
	frappe.call({method: USER_METHOD, args: {user}}).then(response => {
		if (requestId !== frm.__mobileUserRequestId || !frm.fields_dict.user_summary) return;
		const data = response.message || {};
		const assignedRoles = data.roles || [];
		const roleSummary = assignedRoles.length
			? `${assignedRoles.slice(0, 4).map(role => `<span class="karmavitta-role-chip">${escapeHtml(role)}</span>`).join('')}${assignedRoles.length > 4 ? `<span class="karmavitta-role-more" title="${escapeHtml(assignedRoles.join(', '))}">+${assignedRoles.length - 4} more</span>` : ''}`
			: '<span class="karmavitta-no-roles">No roles assigned</span>';
		field.$wrapper.html(`
			<div class="karmavitta-user-summary">
				<div class="karmavitta-user-avatar">${escapeHtml((data.full_name || user).slice(0, 1).toUpperCase())}</div>
				<div class="karmavitta-user-copy">
					<strong>${escapeHtml(data.full_name || user)}</strong>
					<span>${escapeHtml(data.email || user)}</span>
					<div class="karmavitta-user-meta"><span class="karmavitta-user-status ${data.enabled ? 'is-enabled' : 'is-disabled'}">${data.enabled ? 'Enabled' : 'Disabled'} ERPNext user</span><div class="karmavitta-user-roles" aria-label="Assigned ERPNext roles">${roleSummary}</div></div>
				</div>
			</div>`);
	}).catch(() => {
		if (requestId === frm.__mobileUserRequestId) {
			field.$wrapper.html('<div class="karmavitta-permission-empty">User details could not be loaded.</div>');
		}
	});
}

function currentValues(frm, catalog, matrix) {
	const values = {};
	const savedRows = frm.doc[CHILD_FIELD] || [];
	for (const item of catalog.screens || []) {
		const row = savedRows.find(entry => entry.screen_name === item.key);
		if (frm.__mobileScreenValues && Object.hasOwn(frm.__mobileScreenValues, item.key)) {
			values[item.key] = Boolean(frm.__mobileScreenValues[item.key]);
		} else if (row) values[item.key] = Boolean(row.enabled);
		else values[item.key] = Boolean(matrix.values?.[item.key]);
	}
	for (const item of catalog.screens || []) {
		if (item.kind !== 'module') continue;
		if ((catalog.screens || []).some(child => child.module === item.module && child.kind !== 'module' && values[child.key])) {
			values[item.key] = true;
		}
	}
	return values;
}

function groupItems(items) {
	const groups = new Map();
	for (const item of items) {
		const key = item.module || 'other_screens';
		if (!groups.has(key)) {
			groups.set(key, {
				key,
				label: item.module_label || 'Other Screens',
				parent: null,
				items: [],
			});
		}
		const group = groups.get(key);
		if (item.kind === 'module') group.parent = item;
		else group.items.push(item);
	}
	return Array.from(groups.values());
}

function renderMatrix(frm, catalog, matrix) {
	const field = frm.fields_dict.screen_access_matrix;
	if (!field) return;
	const wrapper = field.$wrapper;
	wrapper.off('.karmavittaMobile');
	const searchText = frm.__mobileSearchText || '';
	const items = catalog.screens || [];
	const values = currentValues(frm, catalog, matrix || {});
	frm.__mobileScreenCatalog = items;
	frm.__mobileScreenValues = values;
	const groups = groupItems(items);
	if (!frm.__mobileOpenModules) frm.__mobileOpenModules = new Set();

	const markup = groups.map(group => {
		const open = frm.__mobileOpenModules.has(group.key);
		const childEnabled = group.items.filter(item => values[item.key]).length;
		const selected = group.parent ? Boolean(values[group.parent.key]) : childEnabled > 0;
		const partial = childEnabled > 0 && childEnabled < group.items.length;
		const parentControl = group.parent
			? `<label class="karmavitta-module-toggle"><input type="checkbox" data-module-parent="${escapeHtml(group.parent.key)}" ${selected ? 'checked' : ''} ${partial ? 'data-partial="1"' : ''}><span>${escapeHtml(group.label)}</span></label>`
			: `<strong class="karmavitta-module-title">${escapeHtml(group.label)}</strong>`;
		const entries = group.items.map(item => `
			<label class="karmavitta-screen-row" data-screen-label="${escapeHtml(`${item.label} ${group.label}`.toLowerCase())}">
				<span class="karmavitta-screen-name">${escapeHtml(item.label)}</span>
				<span class="karmavitta-switch-wrap">
					<input type="checkbox" class="karmavitta-screen-toggle" data-screen-key="${escapeHtml(item.key)}" ${values[item.key] ? 'checked' : ''}>
					<span class="karmavitta-switch" aria-hidden="true"></span>
					<span class="karmavitta-switch-state">${values[item.key] ? 'ON' : 'OFF'}</span>
				</span>
			</label>`).join('');
		const groupActions = `
			<div class="karmavitta-module-actions">
				<button type="button" class="btn btn-xs btn-default" data-group-action="on" data-group="${escapeHtml(group.key)}">Enable all</button>
				<button type="button" class="btn btn-xs btn-default" data-group-action="off" data-group="${escapeHtml(group.key)}">Disable all</button>
			</div>`;
		return `
			<section class="karmavitta-screen-group ${open ? 'is-open' : ''}" data-group="${escapeHtml(group.key)}">
				<div class="karmavitta-group-heading">
					<button type="button" class="karmavitta-expand" aria-label="${open ? 'Collapse' : 'Expand'} ${escapeHtml(group.label)}" data-expand-group="${escapeHtml(group.key)}">${open ? '−' : '+'}</button>
					${parentControl}
					${groupActions}
				</div>
				<div class="karmavitta-screen-list" ${open ? '' : 'hidden'}>${entries || '<div class="text-muted">No individual screens in this module.</div>'}</div>
			</section>`;
	}).join('');

	wrapper.html(`
		<style>
			.karmavitta-permission-empty{padding:14px 16px;border:1px dashed var(--border-color);border-radius:10px;color:var(--text-muted);background:var(--subtle-fg)}
			.karmavitta-user-summary{display:flex;align-items:center;gap:12px;padding:14px 16px;background:var(--subtle-fg);border:1px solid var(--border-color);border-radius:10px}
			.karmavitta-user-avatar{display:grid;place-items:center;width:42px;height:42px;flex:0 0 42px;border-radius:50%;background:var(--primary);color:#fff;font-size:17px;font-weight:700}
			.karmavitta-user-copy{display:flex;flex-direction:column;gap:4px;min-width:0}.karmavitta-user-copy strong{font-size:14px}.karmavitta-user-copy>span{color:var(--text-muted);font-size:12px;overflow-wrap:anywhere}
			.karmavitta-user-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.karmavitta-user-status,.karmavitta-role-chip,.karmavitta-role-more{display:inline-flex;align-items:center;border-radius:999px;padding:3px 8px;background:var(--subtle-fg);color:var(--text-muted);font-size:11px;line-height:1.4}.karmavitta-user-status.is-enabled{background:var(--green-100);color:var(--green-700)}.karmavitta-user-status.is-disabled{background:var(--red-100);color:var(--red-700)}.karmavitta-user-roles{display:flex;align-items:center;gap:5px;flex-wrap:wrap}.karmavitta-role-chip{background:var(--blue-50);color:var(--text-color)}.karmavitta-role-more{cursor:help}
			.karmavitta-screen-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:0 0 14px}
			.karmavitta-screen-search{min-width:min(100%,320px);flex:1}.karmavitta-screen-actions{display:flex;gap:7px;flex-wrap:wrap}
			.karmavitta-screen-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,430px),1fr));gap:12px;align-items:start}
			.karmavitta-screen-group{border:1px solid var(--border-color);border-radius:10px;background:var(--card-bg);overflow:hidden}
			.karmavitta-group-heading{display:flex;align-items:center;gap:9px;min-height:48px;padding:7px 10px;background:var(--subtle-fg)}
			.karmavitta-expand{width:27px;height:27px;border:0;border-radius:6px;background:var(--card-bg);color:var(--text-color);font-size:18px;line-height:1;cursor:pointer}
			.karmavitta-module-toggle{display:flex;align-items:center;gap:8px;flex:1;margin:0;font-weight:650;cursor:pointer}.karmavitta-module-toggle input{accent-color:var(--primary)}
			.karmavitta-module-title{flex:1}.karmavitta-module-actions{display:flex;gap:5px}.karmavitta-module-actions .btn{padding:3px 7px}
			.karmavitta-screen-list{padding:4px 12px 9px}.karmavitta-screen-row{display:flex;align-items:center;justify-content:space-between;gap:14px;min-height:39px;border-bottom:1px solid var(--border-color);margin:0;font-weight:400}.karmavitta-screen-row:last-child{border-bottom:0}
			.karmavitta-screen-name{overflow-wrap:anywhere}.karmavitta-switch-wrap{display:flex;align-items:center;gap:7px;flex:0 0 auto}.karmavitta-screen-toggle{position:absolute;opacity:0;width:1px;height:1px}.karmavitta-switch{width:36px;height:20px;border-radius:99px;background:var(--border-color);position:relative;transition:background .15s;cursor:pointer}.karmavitta-switch:after{content:'';position:absolute;top:3px;left:3px;width:14px;height:14px;border-radius:50%;background:white;box-shadow:0 1px 3px #0003;transition:transform .15s}.karmavitta-screen-toggle:checked+.karmavitta-switch{background:var(--primary)}.karmavitta-screen-toggle:checked+.karmavitta-switch:after{transform:translateX(16px)}.karmavitta-switch-state{width:26px;font-size:10px;color:var(--text-muted);font-weight:600}
			.karmavitta-save-bar{display:flex;justify-content:flex-end;gap:8px;margin-top:16px;padding-top:14px;border-top:1px solid var(--border-color)}.karmavitta-unsaved{margin-right:auto;align-self:center;color:var(--orange-600);font-size:12px}
		</style>
		<div class="karmavitta-screen-toolbar">
			<input type="search" class="form-control karmavitta-screen-search" value="${escapeHtml(searchText)}" placeholder="Search screens…" aria-label="Search screens">
			<div class="karmavitta-screen-actions">
				<button type="button" class="btn btn-xs btn-default" data-bulk="on">Select All</button>
				<button type="button" class="btn btn-xs btn-default" data-bulk="off">Deselect All</button>
				<button type="button" class="btn btn-xs btn-default" data-expand="all">Expand All</button>
				<button type="button" class="btn btn-xs btn-default" data-expand="none">Collapse All</button>
			</div>
		</div>
		<div class="karmavitta-screen-grid">${markup}</div>
		<div class="karmavitta-save-bar"><span class="karmavitta-unsaved" ${frm.__mobileDirty ? '' : 'hidden'}>Unsaved changes</span>
			<button type="button" class="btn btn-default" data-form-action="cancel">Cancel</button>
			<button type="button" class="btn btn-default" data-form-action="continue">Save and Continue</button>
			<button type="button" class="btn btn-primary" data-form-action="save">Save</button>
		</div>`);

	wrapper.find('.karmavitta-module-toggle input[data-partial="1"]').prop('indeterminate', true);
	wrapper.on('change.karmavittaMobile', '.karmavitta-screen-search', function () {
		const query = this.value.trim().toLowerCase();
		const matchingGroups = new Set();
		wrapper.find('.karmavitta-screen-row').each(function () {
			const matches = !query || this.dataset.screenLabel.includes(query);
			$(this).toggle(matches);
			if (query && matches) matchingGroups.add(this.closest('.karmavitta-screen-group').dataset.group);
		});
		wrapper.find('.karmavitta-screen-group').each(function () {
			const groupKey = this.dataset.group;
			const hasMatch = !query || matchingGroups.has(groupKey);
			$(this).toggle(hasMatch);
			const expandForSearch = Boolean(query && matchingGroups.has(groupKey));
			$(this).find('.karmavitta-screen-list').prop('hidden', query ? !expandForSearch : !frm.__mobileOpenModules.has(groupKey));
			$(this).toggleClass('is-open', query ? expandForSearch : frm.__mobileOpenModules.has(groupKey));
		});
	});
	wrapper.find('.karmavitta-screen-search').on('input.karmavittaMobile', function () {
		frm.__mobileSearchText = this.value.trim().toLowerCase();
		$(this).trigger('change');
	});
	if (searchText) wrapper.find('.karmavitta-screen-search').trigger('change');
	wrapper.on('click.karmavittaMobile', '[data-expand-group]', function () {
		const key = this.dataset.expandGroup;
		if (frm.__mobileOpenModules.has(key)) frm.__mobileOpenModules.delete(key);
		else frm.__mobileOpenModules.add(key);
		renderMatrix(frm, {screens: items}, {values});
	});
	wrapper.on('click.karmavittaMobile', '[data-expand]', function () {
		frm.__mobileOpenModules = this.dataset.expand === 'all'
			? new Set(groups.map(group => group.key))
			: new Set();
		renderMatrix(frm, {screens: items}, {values});
	});
	wrapper.on('change.karmavittaMobile', '.karmavitta-module-toggle input', function () {
		const group = groups.find(entry => entry.parent?.key === this.dataset.moduleParent);
		if (!group) return;
		const checked = this.checked;
		values[group.parent.key] = checked;
		for (const item of group.items) values[item.key] = checked;
		markDirty(frm, wrapper);
		renderMatrix(frm, {screens: items}, {values});
	});
	wrapper.on('change.karmavittaMobile', '.karmavitta-screen-toggle', function () {
		const key = this.dataset.screenKey;
		values[key] = this.checked;
		const item = items.find(entry => entry.key === key);
		const group = groups.find(entry => entry.key === item?.module);
		if (this.checked && group?.parent) values[group.parent.key] = true;
		if (this.checked && (item?.kind === 'doctype' || item?.kind === 'report')) {
			const entryRoute = group?.items.find(entry => entry.module_route);
			if (entryRoute) values[entryRoute.key] = true;
		}
		const selectedChildren = group?.items.filter(entry => values[entry.key]).length || 0;
		if (group?.parent && selectedChildren === 0) values[group.parent.key] = false;
		markDirty(frm, wrapper);
		renderMatrix(frm, {screens: items}, {values});
	});
	wrapper.on('click.karmavittaMobile', '[data-group-action]', function () {
		const group = groups.find(entry => entry.key === this.dataset.group);
		if (!group) return;
		const enabled = this.dataset.groupAction === 'on';
		if (group.parent) values[group.parent.key] = enabled;
		for (const item of group.items) values[item.key] = enabled;
		markDirty(frm, wrapper);
		renderMatrix(frm, {screens: items}, {values});
	});
	wrapper.on('click.karmavittaMobile', '[data-bulk]', function () {
		const enabled = this.dataset.bulk === 'on';
		for (const item of items) values[item.key] = enabled;
		markDirty(frm, wrapper);
		renderMatrix(frm, {screens: items}, {values});
	});
	wrapper.on('click.karmavittaMobile', '[data-form-action]', function () {
		const action = this.dataset.formAction;
		if (action === 'cancel') return frappe.set_route('mobile-app-permissions');
		frm.save().then(() => {
			if (action === 'continue') frappe.new_doc('Mobile App Permission');
		});
	});
}

function markDirty(frm, wrapper) {
	frm.__mobileDirty = true;
	frm.dirty();
	wrapper.find('.karmavitta-unsaved').prop('hidden', false);
}

function loadMatrix(frm) {
	const field = frm.fields_dict.screen_access_matrix;
	if (!field) return;
	const user = frm.doc.user;
	if (!user) {
		field.$wrapper.html('<div class="karmavitta-permission-empty">Select a user above to load the mobile app screens available in this app.</div>');
		return;
	}
	field.$wrapper.html('<div class="karmavitta-permission-empty">Loading registered mobile screens…</div>');
	const requestId = (frm.__mobileMatrixRequestId || 0) + 1;
	frm.__mobileMatrixRequestId = requestId;
	showUserSummary(frm, user, (frm.__mobileUserRequestId = (frm.__mobileUserRequestId || 0) + 1));
	const args = {user};
	if (!frm.is_new()) args.profile_name = frm.doc.name;
	Promise.all([
		frappe.call({method: CATALOG_METHOD}),
		frappe.call({method: MATRIX_METHOD, args}),
	]).then(([catalogResponse, matrixResponse]) => {
		if (requestId !== frm.__mobileMatrixRequestId || !frm.fields_dict.screen_access_matrix) return;
		const catalog = catalogResponse.message || {screens: []};
		const matrix = matrixResponse.message || {values: {}};
		if (frm.is_new() && matrix.profile_name) {
			frappe.show_alert({message: __('A permission record already exists for this user. Opening it so you can update it.'), indicator: 'blue'});
			return frappe.set_route('Form', 'Mobile App Permission', matrix.profile_name);
		}
		renderMatrix(frm, catalog, matrix);
	}).catch(() => {
		if (requestId === frm.__mobileMatrixRequestId) {
			field.$wrapper.html('<div class="karmavitta-permission-empty">Could not load registered screens. Check your connection and try again.</div>');
		}
	});
}

function persistScreens(frm) {
	if (!frm.doc.user) frappe.throw(__('Select an ERPNext User before saving.'));
	if (!frm.__mobileScreenCatalog?.length) frappe.throw(__('Load the mobile app screens before saving.'));
	// New screen profiles apply to the selected ERPNext user across companies.
	frm.doc.applies_to = 'User';
	frm.doc.role = null;
	frm.doc.company = null;
	frm.clear_table(CHILD_FIELD);
	frm.__mobileScreenCatalog.forEach((item, index) => {
		const row = frm.add_child(CHILD_FIELD);
		row.screen_name = item.key;
		row.screen_label = item.label;
		row.module = item.module_label;
		row.enabled = frm.__mobileScreenValues?.[item.key] ? 1 : 0;
		row.sort_order = index;
	});
}

frappe.ui.form.on('Mobile App Permission', {
	setup(frm) {
		setUserQuery(frm);
	},
	refresh(frm) {
		setUserQuery(frm);
		loadMatrix(frm);
		if (frm.is_new()) {
			frm.page.set_secondary_action(__('Cancel'), () => frappe.set_route('mobile-app-permissions'));
		}
	},
	user(frm) {
		frm.__mobileScreenCatalog = null;
		frm.__mobileScreenValues = null;
		frm.__mobileDirty = false;
		loadMatrix(frm);
	},
	validate(frm) {
		persistScreens(frm);
	},
	after_save(frm) {
		frm.__mobileDirty = false;
		frm.__mobileScreenValues = null;
	},
});
