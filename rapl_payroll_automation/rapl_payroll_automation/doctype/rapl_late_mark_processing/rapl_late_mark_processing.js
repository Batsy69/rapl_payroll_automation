// Copyright (c) 2026, RAPL and contributors

const MAX_BANDS = 5;

frappe.ui.form.on("RAPL Late Mark Processing", {
	refresh(frm) {
		setup_band_columns(frm);

		if (frm.doc.docstatus !== 0) return;

		frm.add_custom_button(__("Get Employees (With Attendance)"), () => {
			if (!frm.doc.start_date || !frm.doc.end_date) {
				frappe.msgprint(__("Set From Date and To Date first."));
				return;
			}
			get_employees(frm, false);
		});

		frm.add_custom_button(__("Get All Employees"), () => {
			if (!frm.doc.start_date || !frm.doc.end_date) {
				frappe.msgprint(__("Set From Date and To Date first."));
				return;
			}
			frappe.confirm(
				__("This adds EVERY active employee, regardless of attendance. Continue?"),
				() => get_employees(frm, true)
			);
		});

		frm.add_custom_button(__("Select Employees Manually"), () => {
			new frappe.ui.form.MultiSelectDialog({
				doctype: "Employee",
				target: frm,
				setters: {
					employee_name: undefined,
					department: undefined,
					grade: undefined,
				},
				get_query() {
					return { filters: { status: "Active" } };
				},
				action(selections) {
					if (!selections || !selections.length) return;
					if (!frm.doc.start_date || !frm.doc.end_date) {
						frappe.msgprint(__("Set From Date and To Date first, then save, before selecting employees."));
						return;
					}
					if (frm.is_new()) {
						frappe.msgprint(__("Save the document once (with dates set) before selecting employees."));
						return;
					}
					frappe.call({
						method: "rapl_payroll_automation.rapl_payroll_automation.doctype.rapl_late_mark_processing.rapl_late_mark_processing.get_employees",
						args: { docname: frm.doc.name, employees: selections },
						freeze: true,
						freeze_message: __("Adding selected employees..."),
						callback: () => frm.reload_doc(),
					});
				},
			});
		});
	},
});

function get_employees(frm, all_employees) {
	if (frm.is_new()) {
		frappe.msgprint(__("Save the document once (with dates set) before fetching employees."));
		return;
	}
	frappe.call({
		method: "rapl_payroll_automation.rapl_payroll_automation.doctype.rapl_late_mark_processing.rapl_late_mark_processing.get_employees",
		args: { docname: frm.doc.name, all_employees },
		freeze: true,
		freeze_message: __("Fetching employees..."),
		callback: () => frm.reload_doc(),
	});
}

// --- Dynamic column labeling/hiding for band_1_count .. band_5_count ---
// The doctype always has exactly 5 fixed columns (Frappe doctypes have a
// fixed schema -- can't literally grow columns at runtime). This function
// renames each column's header to match the actual band Label configured
// in RAPL Payroll Automation Settings, and hides any column beyond however
// many bands are actually defined -- so it LOOKS fully dynamic even though
// the underlying fields are fixed. Verified against real Frappe Grid
// source (grid.js): update_docfield_property(fieldname, property, value)
// is a generic public method (docfield[property] = value under the hood),
// used here for both "label" and "hidden".
function setup_band_columns(frm) {
	frappe.call({
		method: "rapl_payroll_automation.rapl_payroll_automation.doctype.rapl_late_mark_processing.rapl_late_mark_processing.get_band_labels",
		callback(r) {
			const labels = r.message || [];
			frm.__late_mark_band_labels = labels; // cached for recalculate_late_mark_amount's fraction lookup
			fetch_band_fractions(frm, labels);

			const grid = frm.fields_dict["entries"].grid;
			for (let i = 1; i <= MAX_BANDS; i++) {
				const fieldname = `band_${i}_count`;
				if (i <= labels.length) {
					grid.update_docfield_property(fieldname, "label", labels[i - 1]);
					grid.toggle_display(fieldname, true);
				} else {
					grid.toggle_display(fieldname, false);
				}
			}
			frm.refresh_field("entries");
		},
	});
}

function fetch_band_fractions(frm, labels) {
	// get_band_labels() only returns labels (cheap); fetch fractions
	// separately via the Settings doctype directly for the recalculation
	// trigger's own use.
	frappe.db.get_doc("RAPL Payroll Automation Settings", "RAPL Payroll Automation Settings").then((settings) => {
		const bands = (settings.late_mark_bands || []).sort((a, b) =>
			a.from_time < b.from_time ? -1 : 1
		);
		frm.__late_mark_band_fractions = bands.map((b) => flt(b.fraction));
	});
}

// --- Child table (RAPL Late Mark Processing Entry) row-level triggers ---
// Must live here, in the PARENT's own client script -- see the equivalent
// comment in rapl_overtime_processing.js for the full explanation.
frappe.ui.form.on("RAPL Late Mark Processing Entry", {
	employee(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.employee) return;
		if (!frm.doc.start_date || !frm.doc.end_date) {
			frappe.msgprint(__("Set From Date and To Date on the parent document first, then save, before adding rows."));
			return;
		}
		if (frm.is_new()) {
			frappe.msgprint(__("Save the document once (with dates set) before adding rows -- a new row needs a saved parent to fetch Late Mark details against."));
			return;
		}
		frappe.call({
			method: "rapl_payroll_automation.rapl_payroll_automation.doctype.rapl_late_mark_processing.rapl_late_mark_processing.get_employee_late_mark_details",
			args: { docname: frm.doc.name, employee: row.employee },
			freeze: true,
			freeze_message: __("Fetching Late Mark details..."),
			callback: (r) => {
				if (!r.message) return;
				const counts = r.message.band_counts || [];
				for (let i = 0; i < MAX_BANDS; i++) {
					frappe.model.set_value(cdt, cdn, `band_${i + 1}_count`, counts[i] || 0);
				}
				frappe.model.set_value(cdt, cdn, "per_day_rate", r.message.per_day_rate);
				frappe.model.set_value(cdt, cdn, "amount", r.message.amount);
				if (r.message.errors && r.message.errors.length) {
					frappe.msgprint(r.message.errors.join("<br>"));
				}
			},
		});
	},
	band_1_count(frm, cdt, cdn) { recalculate_late_mark_amount(frm, cdt, cdn); },
	band_2_count(frm, cdt, cdn) { recalculate_late_mark_amount(frm, cdt, cdn); },
	band_3_count(frm, cdt, cdn) { recalculate_late_mark_amount(frm, cdt, cdn); },
	band_4_count(frm, cdt, cdn) { recalculate_late_mark_amount(frm, cdt, cdn); },
	band_5_count(frm, cdt, cdn) { recalculate_late_mark_amount(frm, cdt, cdn); },
	per_day_rate(frm, cdt, cdn) { recalculate_late_mark_amount(frm, cdt, cdn); },
});

function recalculate_late_mark_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const fractions = frm.__late_mark_band_fractions || [];
	let total_fraction = 0;
	for (let i = 0; i < MAX_BANDS; i++) {
		const count = flt(row[`band_${i + 1}_count`]);
		const fraction = fractions[i] || 0;
		total_fraction += count * fraction;
	}
	row.amount = total_fraction * flt(row.per_day_rate);
	frm.refresh_field("entries");
}
