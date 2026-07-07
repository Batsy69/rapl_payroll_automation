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
