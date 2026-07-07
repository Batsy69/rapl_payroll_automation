# Copyright (c) 2026, RAPL and contributors

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from rapl_payroll_automation.api.payroll_automation_utils import (
	additional_salary_already_exists,
	create_and_submit_additional_salary,
	get_automation_settings,
	get_total_working_days,
)


class RAPLLateMarkProcessing(Document):
	def on_submit(self):
		settings = get_automation_settings()
		errors = []
		for row in self.entries:
			if not row.amount or row.amount <= 0:
				continue
			if additional_salary_already_exists(row.employee, settings.late_mark_salary_component, self.end_date):
				errors.append(f"{row.employee}: already processed for this period, skipped")
				continue
			doc = create_and_submit_additional_salary(
				row.employee, settings.late_mark_salary_component, row.amount, self.start_date, self.end_date
			)
			row.db_set("additional_salary", doc.name, update_modified=False)

		if errors:
			frappe.msgprint(
				_("Some rows were skipped:") + "<br>" + "<br>".join(errors),
				indicator="orange",
				title=_("Late Mark Processing -- Notes"),
			)


@frappe.whitelist()
def get_employees(docname, all_employees=False, employees=None):
	"""
	Three mutually exclusive modes (checked in this priority order):
	  1. `employees` given (list of Employee IDs, from the manual multi-select
	     picker) -- use exactly this list, no other filter applied.
	  2. all_employees=True -- every active Employee, regardless of attendance.
	  3. all_employees=False (default), employees=None -- employees with any
	     submitted Attendance in the period (no other gate -- unlike Overtime,
	     Late Mark has no equivalent of custom_ot; presence of Attendance is
	     the only automatic criterion).
	"""
	doc = frappe.get_doc("RAPL Late Mark Processing", docname)
	settings = get_automation_settings()
	start_date, end_date = doc.start_date, doc.end_date

	if isinstance(employees, str):
		employees = frappe.parse_json(employees)
	if isinstance(all_employees, str):
		all_employees = all_employees.lower() in ("1", "true", "yes")

	if employees:
		employees = list(employees)
	elif all_employees:
		employees = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name")
	else:
		employees = sorted(
			set(
				frappe.get_all(
					"Attendance",
					filters={"attendance_date": ["between", [start_date, end_date]], "docstatus": 1},
					pluck="employee",
				)
			)
		)

	doc.entries = []
	errors = []
	working_days = get_total_working_days(start_date, end_date)

	for emp in employees:
		if additional_salary_already_exists(emp, settings.late_mark_salary_component, end_date):
			errors.append(f"{emp}: already processed for this period, excluded")
			continue

		monthly_salary = frappe.db.get_value("Employee", emp, "custom_monthly_salary")
		row = doc.append("entries", {})
		row.employee = emp

		if not monthly_salary:
			errors.append(f"{emp}: missing custom_monthly_salary, added with 0 (edit manually)")
			row.late_fraction_total = 0
			row.per_day_rate = 0
			row.amount = 0
			continue

		total_fraction = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(custom_late_deduction_fraction), 0)
			FROM `tabAttendance`
			WHERE employee = %(employee)s
				AND attendance_date BETWEEN %(start)s AND %(end)s
				AND docstatus = 1
			""",
			{"employee": emp, "start": start_date, "end": end_date},
		)[0][0]
		total_fraction = flt(total_fraction)
		per_day_rate = flt(monthly_salary) / working_days

		row.late_fraction_total = round(total_fraction, 4)
		row.per_day_rate = round(per_day_rate, 2)
		row.amount = round(total_fraction * per_day_rate, 2)

	doc.save()

	if errors:
		frappe.msgprint("<br>".join(errors), indicator="orange", title=_("Get Employees -- Notes"))

	return doc.name
