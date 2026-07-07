// Copyright (c) 2026, RAPL and contributors

frappe.ui.form.on("RAPL Late Mark Processing", {
	refresh(frm) {
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

// --- Child table (RAPL Late Mark Processing Entry) row-level triggers ---
// Must live here, in the PARENT's own client script -- see the equivalent
// comment in rapl_overtime_processing.js for the full explanation (verified
// against real ERPNext core: child tables have no form route of their own,
// so a separate .js file for one is never auto-loaded).
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
				frappe.model.set_value(cdt, cdn, "late_fraction_total", r.message.late_fraction_total);
				frappe.model.set_value(cdt, cdn, "per_day_rate", r.message.per_day_rate);
				frappe.model.set_value(cdt, cdn, "amount", r.message.amount);
				if (r.message.errors && r.message.errors.length) {
					frappe.msgprint(r.message.errors.join("<br>"));
				}
			},
		});
	},
	late_fraction_total(frm, cdt, cdn) {
		recalculate_late_mark_amount(frm, cdt, cdn);
	},
	per_day_rate(frm, cdt, cdn) {
		recalculate_late_mark_amount(frm, cdt, cdn);
	},
});

function recalculate_late_mark_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	row.amount = flt(row.late_fraction_total) * flt(row.per_day_rate);
	frm.refresh_field("entries");
}
