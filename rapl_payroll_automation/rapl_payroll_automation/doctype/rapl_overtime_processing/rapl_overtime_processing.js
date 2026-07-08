// Copyright (c) 2026, RAPL and contributors

frappe.ui.form.on("RAPL Overtime Processing", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;

		frm.add_custom_button(__("Get Employees (Eligible Only)"), () => {
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
				__("This adds EVERY active employee, regardless of attendance or OT eligibility. Continue?"),
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
						method: "rapl_payroll_automation.rapl_payroll_automation.doctype.rapl_overtime_processing.rapl_overtime_processing.get_employees",
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
		method: "rapl_payroll_automation.rapl_payroll_automation.doctype.rapl_overtime_processing.rapl_overtime_processing.get_employees",
		args: { docname: frm.doc.name, all_employees },
		freeze: true,
		freeze_message: __("Fetching employees..."),
		callback: () => frm.reload_doc(),
	});
}

// --- Child table (RAPL Overtime Processing Entry) row-level triggers ---
// IMPORTANT: this code must live HERE, in the PARENT doctype's own client
// script -- not in a separate rapl_overtime_processing_entry.js file.
// Verified against real ERPNext core: Sales Order Item (the same
// qty x rate = amount pattern) has NO standalone .js file of its own; that
// trigger code lives inside sales_order.js (the parent). A child table
// (istable=1) has no form route of its own, so Frappe never auto-loads a
// separate file for it -- frappe.ui.form.on("Child Doctype Name", {...})
// only actually runs if the code registering it is inside a file that DOES
// get loaded, which for a child table means the parent's own file.
frappe.ui.form.on("RAPL Overtime Processing Entry", {
	employee(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.employee) return;
		if (!frm.doc.start_date || !frm.doc.end_date) {
			frappe.msgprint(__("Set From Date and To Date on the parent document first, then save, before adding rows."));
			return;
		}
		if (frm.is_new()) {
			frappe.msgprint(__("Save the document once (with dates set) before adding rows -- a new row needs a saved parent to fetch OT details against."));
			return;
		}
		frappe.call({
			method: "rapl_payroll_automation.rapl_payroll_automation.doctype.rapl_overtime_processing.rapl_overtime_processing.get_employee_ot_details",
			args: { docname: frm.doc.name, employee: row.employee },
			freeze: true,
			freeze_message: __("Fetching OT details..."),
			callback: (r) => {
				if (!r.message) return;
				frappe.model.set_value(cdt, cdn, "ot_hours", r.message.ot_hours);
				frappe.model.set_value(cdt, cdn, "ot_rate", r.message.ot_rate);
				frappe.model.set_value(cdt, cdn, "amount", r.message.ot_amount);
				if (r.message.errors && r.message.errors.length) {
					frappe.msgprint(r.message.errors.join("<br>"));
				}
			},
		});
	},
	ot_hours(frm, cdt, cdn) {
		recalculate_ot_amount(frm, cdt, cdn);
	},
	ot_rate(frm, cdt, cdn) {
		recalculate_ot_amount(frm, cdt, cdn);
	},
});

function recalculate_ot_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	// Hours stay exact (never rounded, per design) -- only the final
	// Amount rounds, to whole rupees, matching the server-side calculation.
	row.amount = Math.round(flt(row.ot_hours) * flt(row.ot_rate));
	frm.refresh_field("entries");
}
