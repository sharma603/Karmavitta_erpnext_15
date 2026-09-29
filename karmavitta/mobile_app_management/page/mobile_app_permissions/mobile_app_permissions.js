const LIST_METHOD = 'karmavitta.api.mobile_permissions.get_mobile_permission_profiles';
const DELETE_METHOD = 'karmavitta.api.mobile_permissions.delete_mobile_permission_profile';

function escapeMobilePermissionHtml(value) {
	return String(value || '').replace(/[&<>"']/g, character => ({
		'&': '&amp;',
		'<': '&lt;',
		'>': '&gt;',
		'"': '&quot;',
		"'": '&#39;',
	})[character]);
}

frappe.pages['mobile-app-permissions'].on_page_load = function (wrapper) {
	new MobileAppPermissionsPage(wrapper);
};

class MobileAppPermissionsPage {
	constructor(wrapper) {
		this.wrapper = wrapper;
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __('Mobile App Permissions'),
			single_column: true,
		});
		this.$main = $(wrapper).find('.layout-main-section');
		this.page.set_primary_action(__('Add Mobile App Permission'), () => {
			frappe.new_doc('Mobile App Permission');
		}, 'add');
		this.renderShell();
		this.bindEvents();
		this.load();
	}

	renderShell() {
		this.$main.html(`
			<div class="karmavitta-mobile-permissions-page">
				<div class="karmavitta-mobile-permissions-intro">
					<p>${__('Configure which screens each user can access in the mobile app.')}</p>
				</div>
				<div class="karmavitta-mobile-permissions-search">
					<input class="form-control" type="search" placeholder="${__('Search by user name or email')}" aria-label="${__('Search by user name or email')}">
					<span class="text-muted">${__('Search existing user screen configurations')}</span>
				</div>
				<div class="karmavitta-mobile-permissions-table-wrap">
					<div class="karmavitta-mobile-permissions-table"></div>
				</div>
			</div>
			<style>
				.karmavitta-mobile-permissions-page{padding:20px 22px 28px}
				.karmavitta-mobile-permissions-intro{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:22px}
				.karmavitta-mobile-permissions-intro h3{margin:0 0 5px;font-size:20px;font-weight:650}
				.karmavitta-mobile-permissions-intro p{margin:0;color:var(--text-muted)}
				.karmavitta-mobile-permissions-search{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:12px}
				.karmavitta-mobile-permissions-search input{max-width:440px}
				.karmavitta-mobile-permissions-table-wrap{overflow:auto;border:1px solid var(--border-color);border-radius:10px;background:var(--card-bg)}
				.karmavitta-mobile-permissions-table table{width:100%;border-collapse:collapse;min-width:820px}
				.karmavitta-mobile-permissions-table th,.karmavitta-mobile-permissions-table td{padding:12px 14px;border-bottom:1px solid var(--border-color);text-align:left;vertical-align:middle}
				.karmavitta-mobile-permissions-table th{background:var(--subtle-fg);font-size:12px;font-weight:650;white-space:nowrap}
				.karmavitta-mobile-permissions-table tbody tr:last-child td{border-bottom:0}
				.karmavitta-mobile-user-name{font-weight:600}.karmavitta-mobile-user-email{color:var(--text-muted);font-size:12px;margin-top:2px}
				.karmavitta-mobile-state{display:inline-flex;padding:3px 9px;border-radius:99px;font-size:11px;font-weight:650}
				.karmavitta-mobile-state.on{background:var(--green-100);color:var(--green-700)}.karmavitta-mobile-state.off{background:var(--red-100);color:var(--red-700)}
				.karmavitta-mobile-actions{display:flex;gap:6px;white-space:nowrap}.karmavitta-mobile-actions .btn{padding:4px 9px}
				.karmavitta-mobile-empty{padding:38px 20px;text-align:center;color:var(--text-muted)}
				.karmavitta-mobile-permissions-table .btn-link{padding:0}
				@media(max-width:700px){.karmavitta-mobile-permissions-page{padding:12px}.karmavitta-mobile-permissions-intro{align-items:flex-start;flex-direction:column}.karmavitta-mobile-permissions-search{align-items:stretch;flex-direction:column;gap:5px}}
			</style>`);
		this.$search = this.$main.find('input[type="search"]');
		this.$table = this.$main.find('.karmavitta-mobile-permissions-table');
	}

	bindEvents() {
		this.$main.on('click', '.karmavitta-mobile-permissions-table [data-action="view"]', event => {
			const profile = this.rows.find(row => row.name === event.currentTarget.dataset.name);
			if (profile) this.view(profile);
		});
		this.$main.on('click', '.karmavitta-mobile-permissions-table [data-action="edit"]', event => {
			frappe.set_route('Form', 'Mobile App Permission', event.currentTarget.dataset.name);
		});
		this.$main.on('click', '.karmavitta-mobile-permissions-table [data-action="delete"]', event => {
			this.remove(event.currentTarget.dataset.name);
		});
		let timer;
		this.$search.on('input', () => {
			clearTimeout(timer);
			timer = setTimeout(() => this.load(), 220);
		});
	}

	async load() {
		this.$table.html(`<div class="karmavitta-mobile-empty">${__('Loading user permissions…')}</div>`);
		try {
			const response = await frappe.call({method: LIST_METHOD, args: {search: this.$search.val() || ''}});
			this.rows = response.message || [];
			this.renderRows();
		} catch (error) {
			this.$table.html(`<div class="karmavitta-mobile-empty">${__('Unable to load mobile permissions. Please refresh this page.')}</div>`);
		}
	}

	renderRows() {
		if (!this.rows.length) {
			this.$table.html(`<div class="karmavitta-mobile-empty">${__('No user configurations found. Select Add Mobile App Permission to configure an existing ERPNext user.')}</div>`);
			return;
		}
		const body = this.rows.map(row => `
			<tr>
				<td><div class="karmavitta-mobile-user-name">${escapeMobilePermissionHtml(row.full_name)}</div><div class="karmavitta-mobile-user-email">${escapeMobilePermissionHtml(row.user)}</div></td>
				<td>${escapeMobilePermissionHtml(row.email)}</td>
				<td><span class="karmavitta-mobile-state ${row.enabled ? 'on' : 'off'}">${row.enabled ? __('Enabled') : __('Disabled')}</span></td>
				<td>${row.selected_screens} / ${row.total_screens} ${__('screens enabled')}</td>
				<td>${escapeMobilePermissionHtml(frappe.datetime.str_to_user(row.modified))}</td>
				<td><div class="karmavitta-mobile-actions">
					<button type="button" class="btn btn-xs btn-default" data-action="view" data-name="${escapeMobilePermissionHtml(row.name)}">${__('View')}</button>
					<button type="button" class="btn btn-xs btn-default" data-action="edit" data-name="${escapeMobilePermissionHtml(row.name)}">${__('Edit')}</button>
					<button type="button" class="btn btn-xs btn-default" data-action="delete" data-name="${escapeMobilePermissionHtml(row.name)}">${__('Delete')}</button>
				</div></td>
			</tr>`).join('');
		this.$table.html(`
			<table><thead><tr><th>${__('User')}</th><th>${__('Email')}</th><th>${__('Enabled')}</th><th>${__('Selected Screens')}</th><th>${__('Last Updated')}</th><th>${__('Actions')}</th></tr></thead>
			<tbody>${body}</tbody></table>`);
	}

	view(profile) {
		const screens = (profile.selected_screen_labels || []).map(label => `<li>${escapeMobilePermissionHtml(label)}</li>`).join('');
		const dialog = new frappe.ui.Dialog({
			title: profile.full_name,
			fields: [{fieldtype: 'HTML', fieldname: 'details'}],
			primary_action_label: __('Edit'),
			primary_action: () => {
				dialog.hide();
				frappe.set_route('Form', 'Mobile App Permission', profile.name);
			},
		});
		dialog.fields_dict.details.$wrapper.html(`
			<p><strong>${__('Email')}:</strong> ${escapeMobilePermissionHtml(profile.email)}</p>
			<p><strong>${__('Mobile App Access')}:</strong> ${profile.enabled ? __('Enabled') : __('Disabled')}</p>
			<p><strong>${__('Selected Screens')}:</strong> ${profile.selected_screens}</p>
			<div style="max-height:50vh;overflow:auto"><ul>${screens || `<li>${__('No screens enabled')}</li>`}</ul></div>`);
		dialog.show();
	}

	remove(name) {
		frappe.confirm(__('Delete this user mobile screen configuration?'), async () => {
			await frappe.call({method: DELETE_METHOD, args: {name}});
			frappe.show_alert({message: __('Mobile app permission deleted.'), indicator: 'green'});
			this.load();
		});
	}
}
