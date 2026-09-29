// Copyright (c) 2026, Synergy and contributors
// Hide Mobile API Key (sensitive) + Generate / Download / Show actions

frappe.ui.form.on("Face Attendance Settings", {
	refresh(frm) {
		setup_mobile_api_key_ui(frm);
		setup_face_service_key_ui(frm);
		setup_arcface_runtime_check(frm);
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

function setup_face_service_key_ui(frm) {
	const field = frm.get_field("face_service_api_key");
	if (!field) return;

	field.$wrapper.find(".kv-face-service-key-actions").remove();
	field.$wrapper.find(".kv-face-service-key-value").remove();
	let revealed = false;
	const $actions = $(`
		<div class="kv-face-service-key-actions" style="margin-top: 8px;">
			<div style="display: flex; flex-wrap: wrap; gap: 8px;">
				<button type="button" class="btn btn-xs btn-default kv-show-service-key">${__("Show Saved Key")}</button>
				<button type="button" class="btn btn-xs btn-default kv-copy-service-key">${__("Copy Saved Key")}</button>
			</div>
		</div>
	`);
	field.$wrapper.append($actions);
	const updateKeyActions = () => {
		const externalServiceConfigured =
			frm.doc.face_recognition_mode === "External Face Service" &&
			Boolean((frm.doc.face_service_url || "").trim());
		$actions.find(".kv-show-service-key, .kv-copy-service-key").toggle(externalServiceConfigured);
		if (!externalServiceConfigured) {
			field.$wrapper.find(".kv-face-service-key-value").remove();
			revealed = false;
		}
	};
	updateKeyActions();
	frm.fields_dict.face_service_url?.$input?.on("change", updateKeyActions);
	frm.fields_dict.face_recognition_mode?.$input?.on("change", updateKeyActions);

	const loadKey = (callback) => {
		frappe.call({
			method: "karmavitta.face_attendance.doctype.face_attendance_settings.face_attendance_settings.get_face_service_api_key",
			freeze: true,
			callback(r) {
				const key = r.message && r.message.face_service_api_key;
				if (!key) {
					frappe.msgprint(__("No external service key is configured"));
					return;
				}
				callback(key);
			},
		});
	};

	$actions.find(".kv-show-service-key").on("click", () => {
		if (revealed) {
			field.$wrapper.find(".kv-face-service-key-value").remove();
			revealed = false;
			$actions.find(".kv-show-service-key").text(__("Show Saved Key"));
			return;
		}
		loadKey((key) => {
			field.$wrapper.append($('<div class="kv-face-service-key-value" style="margin-top: 6px;"><code></code></div>').find("code").text(key).end());
			revealed = true;
			$actions.find(".kv-show-service-key").text(__("Hide Saved Key"));
		});
	});

	$actions.find(".kv-copy-service-key").on("click", () => {
		loadKey((key) => {
			const copied = () => frappe.show_alert({ message: __("Face service key copied"), indicator: "green" });
			const fallbackCopy = () => {
				frappe.utils.copy_to_clipboard(key);
				copied();
			};
			if (navigator.clipboard && navigator.clipboard.writeText) {
				navigator.clipboard.writeText(key).then(copied).catch(fallbackCopy);
			} else {
				fallbackCopy();
			}
		});
	});

}

function setup_arcface_runtime_check(frm) {
	const field = frm.get_field("arcface_runtime_check");
	if (!field) return;
	field.$wrapper.find(".kv-arcface-runtime-actions").remove();
	const $actions = $(`
		<div class="kv-arcface-runtime-actions" style="margin-top: 8px;">
			<button type="button" class="btn btn-xs btn-default kv-check-arcface">${__("Check ArcFace")}</button>
			<div class="kv-arcface-runtime-status text-muted small" role="status" style="margin-top: 8px;"></div>
		</div>
	`);
	field.$wrapper.append($actions);
	const $status = $actions.find(".kv-arcface-runtime-status");
	const setStatus = (message, type = "muted") => {
		$status.removeClass("text-muted text-success text-warning text-danger").addClass(`text-${type}`).text(message);
	};
	const refreshModeHint = () => {
		if (frm.doc.face_recognition_mode === "Built-in (same Frappe app)") {
			setStatus(_("Built-in mode: ArcFace runs inside this Frappe site. The first check may download and load the model."), "muted");
		} else {
			setStatus(_("External mode: enter a reachable service URL and matching API key, then check the connection."), "muted");
		}
	};
	refreshModeHint();
	frm.fields_dict.face_recognition_mode?.$input?.on("change", refreshModeHint);

	$actions.find(".kv-check-arcface").on("click", () => {
		const initializeModel = frm.doc.face_recognition_mode === "Built-in (same Frappe app)";
		$status.text(initializeModel
			? __("Loading and checking the ArcFace model. First use can take several minutes…")
			: __("Checking the external ArcFace service…"));
		frappe.call({
			method: "karmavitta.api.diagnostics.face_recognition_diagnostics",
			args: { initialize_model: initializeModel ? 1 : 0 },
			freeze: true,
			freeze_message: initializeModel
				? __("Initializing ArcFace. The first run may download the model and take several minutes.")
				: __("Checking the external ArcFace service."),
			callback(r) {
				const result = r.message || {};
				if (result.recognition_mode === "in_process") {
					const health = result.face_service_health || {};
					if (health.success && health.model_loaded) {
						setStatus(health.message || _("ArcFace model loaded and ready inside Frappe."), "success");
					} else if (health.success) {
						setStatus(health.message || _("ArcFace packages are available, but the model is not loaded."), "warning");
					} else {
						setStatus(health.message || _("Built-in ArcFace could not initialize."), "danger");
					}
				} else if (result.recognition_mode === "unconfigured") {
					setStatus(_("Choose Built-in or External mode. External mode needs a service URL and API key."), "warning");
				} else if (!result.face_service_api_key_configured) {
					setStatus(_("Service key is missing. Enter the key configured on the external ArcFace service."), "warning");
				} else if (result.face_service_health && result.face_service_health.status === "ok") {
					setStatus(_("External ArcFace service is online and ready."), "success");
				} else {
					const detail = result.face_service_health && result.face_service_health.message;
					setStatus(detail || _("ArcFace service is configured but not responding as ready."), "danger");
				}
			},
			error() {
				setStatus(_("Could not complete the ArcFace check. Review Frappe worker logs for details."), "danger");
			},
		});
	});
}
