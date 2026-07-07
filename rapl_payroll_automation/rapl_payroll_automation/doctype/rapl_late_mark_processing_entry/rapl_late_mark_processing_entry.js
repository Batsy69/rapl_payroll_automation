// Copyright (c) 2026, RAPL and contributors
//
// Same pattern as rapl_overtime_processing_entry.js: employee-select
// auto-fetch (for rows added via native grid Add Row) + fraction/rate
// change auto-recalculating Amount.

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
		recalculate_amount(frm, cdt, cdn);
	},
	per_day_rate(frm, cdt, cdn) {
		recalculate_amount(frm, cdt, cdn);
	},
});

function recalculate_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	row.amount = flt(row.late_fraction_total) * flt(row.per_day_rate);
	frm.refresh_field("entries");
}
