// Copyright (c) 2026, Synergy and contributors
// Hide Mobile API Key (sensitive) + Generate / Download / Show actions

frappe.ui.form.on("Face Attendance Settings", {
	refresh(frm) {
		setup_mobile_api_key_ui(frm);
	},
});

function setup_mobile_api_key_ui(frm) {
	const field = frm.get_field("mobile_api_key");
	if (!field) {
		return;
	}

	const mask_display = () => {
		if (field.$input && field.$input.length) {
			field.$input.attr("type", "password");
			field.$input.attr("autocomplete", "new-password");
		}
		field.$wrapper.find(".control-value, .like-disabled-input").css({
			"-webkit-text-security": "disc",
			"font-family": "text-security-disc, monospace",
			letterSpacing: "0.12em",
		});
	};

	const unmask_display = () => {
		if (field.$input && field.$input.length) {
			field.$input.attr("type", "text");
		}
		field.$wrapper.find(".control-value, .like-disabled-input").css({
			"-webkit-text-security": "none",
			letterSpacing: "normal",
		});
	};

	mask_display();

	// Avoid stacking buttons on every refresh
	frm.fields_dict.mobile_api_key.$wrapper.find(".kv-api-key-actions").remove();

	const $actions = $(`
		<div class="kv-api-key-actions" style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 8px;">
			<button type="button" class="btn btn-xs btn-default kv-toggle-key">
				${__("Show Key")}
			</button>
			<button type="button" class="btn btn-xs btn-primary kv-generate-key">
				${__("Generate New Key")}
			</button>
			<button type="button" class="btn btn-xs btn-default kv-download-key">
				${__("Download Key")}
			</button>
			<button type="button" class="btn btn-xs btn-default kv-copy-key">
				${__("Copy Key")}
			</button>
		</div>
		<p class="text-muted small" style="margin-top: 6px;">
			${__("This key is sensitive. Show only when needed. Generating a new key invalidates the old one.")}
		</p>
	`);

	field.$wrapper.append($actions);

	let revealed = false;

	$actions.find(".kv-toggle-key").on("click", () => {
		if (!revealed) {
			frappe.call({
				method:
					"karmavitta.face_attendance.doctype.face_attendance_settings.face_attendance_settings.get_mobile_api_key",
				freeze: true,
				callback(r) {
					const key = r.message && r.message.mobile_api_key;
					if (!key) {
						frappe.msgprint(__("No API key found"));
						return;
					}
					frm.doc.mobile_api_key = key;
					frm.refresh_field("mobile_api_key");
					unmask_display();
					revealed = true;
					$actions.find(".kv-toggle-key").text(__("Hide Key"));
				},
			});
		} else {
			mask_display();
			revealed = false;
			$actions.find(".kv-toggle-key").text(__("Show Key"));
		}
	});

	$actions.find(".kv-generate-key").on("click", () => {
		frappe.confirm(
			__(
				"Generate a new Mobile API Key? The current key will stop working on all devices until they are updated."
			),
			() => {
				frappe.call({
					method:
						"karmavitta.face_attendance.doctype.face_attendance_settings.face_attendance_settings.regenerate_mobile_api_key",
					freeze: true,
					freeze_message: __("Generating key…"),
					callback(r) {
						const key = r.message && r.message.mobile_api_key;
						if (!key) {
							return;
						}
						frm.reload_doc().then(() => {
							frm.doc.mobile_api_key = key;
							frm.refresh_field("mobile_api_key");
							const f = frm.get_field("mobile_api_key");
							if (f) {
								if (f.$input && f.$input.length) {
									f.$input.attr("type", "text");
								}
								f.$wrapper.find(".control-value, .like-disabled-input").css({
									"-webkit-text-security": "none",
									letterSpacing: "normal",
								});
							}
							frappe.show_alert({
								message: __("New key generated — copy or download it now"),
								indicator: "green",
							});
						});
					},
				});
			}
		);
	});

	$actions.find(".kv-download-key").on("click", () => {
		frappe.call({
			method:
				"karmavitta.face_attendance.doctype.face_attendance_settings.face_attendance_settings.get_mobile_api_key",
			freeze: true,
			callback(r) {
				const key = r.message && r.message.mobile_api_key;
				if (!key) {
					frappe.msgprint(__("No API key found"));
					return;
				}
				download_text_file(
					"karmavitta-mobile-api-key.txt",
					[
						"ERPNext Karmavitta — Mobile API Key",
						"Keep this file private.",
						"",
						`Site: ${frappe.boot.sitename || window.location.host}`,
						`Mobile API Key: ${key}`,
						"",
						"Generated: " + frappe.datetime.now_datetime(),
					].join("\n")
				);
				frappe.show_alert({
					message: __("API key file downloaded"),
					indicator: "green",
				});
			},
		});
	});

	$actions.find(".kv-copy-key").on("click", () => {
		frappe.call({
			method:
				"karmavitta.face_attendance.doctype.face_attendance_settings.face_attendance_settings.get_mobile_api_key",
			freeze: true,
			callback(r) {
				const key = r.message && r.message.mobile_api_key;
				if (!key) {
					frappe.msgprint(__("No API key found"));
					return;
				}
				if (navigator.clipboard && navigator.clipboard.writeText) {
					navigator.clipboard.writeText(key).then(() => {
						frappe.show_alert({
							message: __("API key copied"),
							indicator: "green",
						});
					});
				} else {
					frappe.utils.copy_to_clipboard(key);
				}
			},
		});
	});
}

function download_text_file(filename, content) {
	const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = filename;
	document.body.appendChild(a);
	a.click();
	document.body.removeChild(a);
	URL.revokeObjectURL(url);
}
