// Copyright (c) 2026, RAPL and contributors
//
// Two triggers:
// 1. employee change -- auto-fetches OT Hours/Rate/Amount from the server
//    for a row added via the native grid's own "Add Row" (rows added via
//    "Select Employees Manually" or either "Get Employees" button already
//    get this from get_employees() on the parent, server-side -- this
//    trigger covers the one remaining path that had nothing wired up).
// 2. ot_hours/ot_rate change -- recalculates Amount = Hours x Rate,
//    same standard grid-trigger pattern ERPNext itself uses for qty x rate.

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
		recalculate_amount(frm, cdt, cdn);
	},
	ot_rate(frm, cdt, cdn) {
		recalculate_amount(frm, cdt, cdn);
	},
});

function recalculate_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	row.amount = flt(row.ot_hours) * flt(row.ot_rate);
	frm.refresh_field("entries");
}
