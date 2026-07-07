// Copyright (c) 2026, RAPL and contributors
//
// Grid row-level recalculation: Amount = Fraction Total x Per-Day Rate,
// whenever either changes. Same pattern as rapl_overtime_processing_entry.js.

frappe.ui.form.on("RAPL Late Mark Processing Entry", {
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
