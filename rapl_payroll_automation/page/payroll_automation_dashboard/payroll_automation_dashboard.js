// Copyright (c) 2026, RAPL and contributors
//
// Payroll Automation Dashboard.
// User-initiated, never scheduled. Flow:
//   1. Select period, click Load
//   2. Pre-flight check runs -> popup if issues found -> user fixes/retries
//      or proceeds excluding flagged employees
//   3. Editable preview table renders (Overtime + Late Mark) -- nothing has
//      been created yet at this point, this is the dry-run step
//   4. User can edit any amount inline
//   5. "Confirm & Process" creates + submits the Additional Salary records
//      using whatever is currently showing in each cell (edited or computed)

frappe.pages["payroll-automation-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Payroll Automation Dashboard",
		single_column: true,
	});

	new PayrollAutomationDashboard(page);
};

class PayrollAutomationDashboard {
	constructor(page) {
		this.page = page;
		this.excluded_employees = [];
		this.overtime_rows = [];
		this.late_mark_rows = [];
		this.setup_controls();
	}

	setup_controls() {
		this.from_date_field = this.page.add_field({
			label: "From Date",
			fieldname: "from_date",
			fieldtype: "Date",
		});
		this.to_date_field = this.page.add_field({
			label: "To Date",
			fieldname: "to_date",
			fieldtype: "Date",
		});

		this.page.set_primary_action("Load", () => this.load(), "refresh");

		this.body = $('<div class="payroll-automation-body" style="margin-top: 20px;"></div>').appendTo(
			this.page.body
		);
	}

	get_period() {
		return {
			start_date: this.from_date_field.get_value(),
			end_date: this.to_date_field.get_value(),
		};
	}

	load() {
		const { start_date, end_date } = this.get_period();
		if (!start_date || !end_date) {
			frappe.msgprint("Select both From Date and To Date first.");
			return;
		}

		frappe.call({
			method: "rapl_payroll_automation.api.payroll_preflight_check.run_preflight_check",
			args: { start_date, end_date },
			freeze: true,
			freeze_message: "Running pre-flight check...",
			callback: (r) => {
				const { issues, flagged_employees } = r.message;
				if (issues && issues.length) {
					this.show_preflight_dialog(issues, flagged_employees, start_date, end_date);
				} else {
					this.load_preview(start_date, end_date, []);
				}
			},
		});
	}

	show_preflight_dialog(issues, flagged_employees, start_date, end_date) {
		let rows_html = issues
			.map(
				(i) =>
					`<tr><td>${i.employee_name || i.employee}</td><td>${i.reason}</td></tr>`
			)
			.join("");

		const d = new frappe.ui.Dialog({
			title: "Pre-flight Check -- Issues Found",
			fields: [
				{
					fieldtype: "HTML",
					options: `
						<p>The following issues were found. Fix the underlying data and click Load again,
						or proceed excluding the flagged employees below (everyone else will be processed normally).</p>
						<table class="table table-bordered">
							<thead><tr><th>Employee</th><th>Issue</th></tr></thead>
							<tbody>${rows_html}</tbody>
						</table>
					`,
				},
			],
			primary_action_label: "Proceed, excluding flagged employees",
			primary_action: () => {
				d.hide();
				this.load_preview(start_date, end_date, flagged_employees);
			},
			secondary_action_label: "Cancel",
		});
		d.show();
	}

	load_preview(start_date, end_date, excluded_employees) {
		this.excluded_employees = excluded_employees;

		frappe.call({
			method: "rapl_payroll_automation.api.overtime_automation.compute_overtime_preview",
			args: { start_date, end_date },
			freeze: true,
			freeze_message: "Computing Overtime...",
			callback: (r) => {
				this.overtime_rows = (r.message.rows || []).filter(
					(row) => !excluded_employees.includes(row.employee)
				);
				this.report_errors(r.message.errors, "Overtime");

				frappe.call({
					method: "rapl_payroll_automation.api.late_mark_automation.compute_late_mark_preview",
					args: { start_date, end_date },
					freeze: true,
					freeze_message: "Computing Late Mark...",
					callback: (r2) => {
						this.late_mark_rows = (r2.message.rows || []).filter(
							(row) => !excluded_employees.includes(row.employee)
						);
						this.report_errors(r2.message.errors, "Late Mark");
						this.render_preview(start_date, end_date);
					},
				});
			},
		});
	}

	report_errors(errors, label) {
		if (errors && errors.length) {
			frappe.msgprint({
				title: `${label} -- Notes`,
				message: errors.join("<br>"),
				indicator: "orange",
			});
		}
	}

	render_preview(start_date, end_date) {
		this.body.empty();

		this.body.append(`<h4>Overtime</h4>`);
		this.build_editable_table(
			this.body,
			this.overtime_rows,
			[
				{ field: "employee_name", label: "Employee" },
				{ field: "grade", label: "Grade" },
				{ field: "ot_hours", label: "OT Hours" },
				{ field: "ot_rate", label: "Rate/hr" },
				{ field: "ot_amount", label: "Amount", editable: true },
			],
			"ot_amount"
		);
		this.add_manual_row_button(this.body, "ot_amount", this.overtime_rows, () =>
			this.render_preview(start_date, end_date)
		);

		this.body.append(`<h4 style="margin-top: 30px;">Late Mark</h4>`);
		this.build_editable_table(
			this.body,
			this.late_mark_rows,
			[
				{ field: "employee_name", label: "Employee" },
				{ field: "late_fraction_total", label: "Fraction Total" },
				{ field: "per_day_rate", label: "Per-Day Rate" },
				{ field: "late_mark_amount", label: "Amount", editable: true },
			],
			"late_mark_amount"
		);
		this.add_manual_row_button(this.body, "late_mark_amount", this.late_mark_rows, () =>
			this.render_preview(start_date, end_date)
		);

		const confirm_btn = $(
			'<button class="btn btn-primary" style="margin-top: 20px;">Confirm & Process</button>'
		).appendTo(this.body);
		confirm_btn.on("click", () => this.confirm_and_process(start_date, end_date));
	}

	build_editable_table(container, rows, columns, editable_field) {
		if (!rows.length) {
			container.append("<p class='text-muted'>No entries for this period.</p>");
			return;
		}

		const table = $('<table class="table table-bordered"></table>').appendTo(container);
		const thead = $("<thead><tr></tr></thead>").appendTo(table);
		columns.forEach((c) => thead.find("tr").append(`<th>${c.label}</th>`));

		const tbody = $("<tbody></tbody>").appendTo(table);
		rows.forEach((row, idx) => {
			const tr = $("<tr></tr>").appendTo(tbody);
			columns.forEach((c) => {
				if (c.editable) {
					const td = $("<td></td>").appendTo(tr);
					const input = $(
						`<input type="number" step="0.01" class="form-control" value="${row[c.field]}">`
					).appendTo(td);
					input.on("change", (e) => {
						rows[idx][editable_field] = parseFloat(e.target.value) || 0;
					});
				} else {
					tr.append(`<td>${row[c.field]}</td>`);
				}
			});
		});
	}

	add_manual_row_button(container, amount_field, rows_array, on_added) {
		const btn = $(
			'<button class="btn btn-default btn-sm" style="margin-top: 8px;">+ Add Employee Manually</button>'
		).appendTo(container);

		btn.on("click", () => {
			const d = new frappe.ui.Dialog({
				title: "Add Employee Manually",
				fields: [
					{
						fieldname: "employee",
						fieldtype: "Link",
						options: "Employee",
						label: "Employee",
						reqd: 1,
					},
					{
						fieldname: "amount",
						fieldtype: "Currency",
						label: "Amount",
						reqd: 1,
					},
				],
				primary_action_label: "Add",
				primary_action: (values) => {
					// Bypasses the computed calculation entirely -- useful for
					// backfilling periods that predate this app (no underlying
					// Attendance-derived data to compute from), or any other
					// one-off manual correction. Same shape as a computed row,
					// so process_overtime/process_late_mark handle it identically.
					const existing = rows_array.find((r) => r.employee === values.employee);
					if (existing) {
						existing[amount_field] = values.amount;
					} else {
						frappe.db.get_value("Employee", values.employee, "employee_name").then((r) => {
							rows_array.push({
								employee: values.employee,
								employee_name: r.message.employee_name || values.employee,
								[amount_field]: values.amount,
							});
							d.hide();
							on_added();
						});
						return;
					}
					d.hide();
					on_added();
				},
			});
			d.show();
		});
	}

	confirm_and_process(start_date, end_date) {
		frappe.confirm(
			"This will create and submit Additional Salary records for every row shown. Continue?",
			() => {
				frappe.call({
					method: "rapl_payroll_automation.api.overtime_automation.process_overtime",
					args: { start_date, end_date, rows: this.overtime_rows },
					freeze: true,
					freeze_message: "Processing Overtime...",
					callback: (r) => {
						this.report_errors(r.message.errors, "Overtime processing");
						frappe.call({
							method: "rapl_payroll_automation.api.late_mark_automation.process_late_mark",
							args: { start_date, end_date, rows: this.late_mark_rows },
							freeze: true,
							freeze_message: "Processing Late Mark...",
							callback: (r2) => {
								this.report_errors(r2.message.errors, "Late Mark processing");
								frappe.msgprint({
									title: "Done",
									message: `Overtime: ${r.message.count} processed. Late Mark: ${r2.message.count} processed.`,
									indicator: "green",
								});
							},
						});
					},
				});
			}
		);
	}
}
