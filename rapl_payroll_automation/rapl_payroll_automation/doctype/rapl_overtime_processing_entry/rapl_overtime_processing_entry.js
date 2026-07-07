// Copyright (c) 2026, RAPL and contributors
//
// Grid row-level recalculation: Amount = OT Hours x Rate/hr, whenever either
// changes. Same standard Frappe pattern ERPNext itself uses for qty x rate =
// amount on Sales Order Item / Purchase Order Item etc. One-way only: editing
// Amount directly does not push a value back into OT Hours/Rate.

frappe.ui.form.on("RAPL Overtime Processing Entry", {
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
