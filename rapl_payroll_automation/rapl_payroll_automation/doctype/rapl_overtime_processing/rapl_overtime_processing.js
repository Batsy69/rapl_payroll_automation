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
	},
});

function get_employees(frm, all_employees) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the document first (so the period is stored), then click Get Employees again."));
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
