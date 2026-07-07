# Copyright (c) 2026, RAPL and contributors
#
# RAPL Overtime Processing -- submittable document replacing the old
# hand-rolled Dashboard Page. Uses the native Frappe Grid for the `entries`
# child table, which gives add-row / delete-row / multi-select-bulk-delete /
# full inline editing for free -- none of that needed to be custom-built.
#
# Workflow: create a new document, set the period, click "Get Employees"
# (populates `entries` -- either eligible employees only, or every employee
# if "Get All Employees" is used), freely add/remove/edit rows using the
# native grid controls, then Submit to create the actual Additional Salary
# records.

import frappe
from frappe import _
from frappe.model.document import Document

from rapl_payroll_automation.api.payroll_automation_utils import (
	additional_salary_already_exists,
	create_and_submit_additional_salary,
	get_all_holiday_dates,
	get_automation_settings,
	get_datetime_combine,
	get_grade_ot_rule,
	get_total_working_days,
	get_weekly_off_dates,
)
from rapl_payroll_automation.api.overtime_automation import get_attendance_for_employee
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from frappe.utils import flt, get_datetime


class RAPLOvertimeProcessing(Document):
	def on_submit(self):
		settings = get_automation_settings()
		errors = []
		for row in self.entries:
			if not row.amount or row.amount <= 0:
				continue
			if additional_salary_already_exists(row.employee, settings.overtime_salary_component, self.end_date):
				errors.append(f"{row.employee}: already processed for this period, skipped")
				continue
			doc = create_and_submit_additional_salary(
				row.employee, settings.overtime_salary_component, row.amount, self.start_date, self.end_date
			)
			row.db_set("additional_salary", doc.name, update_modified=False)

		if errors:
			frappe.msgprint(
				_("Some rows were skipped:") + "<br>" + "<br>".join(errors),
				indicator="orange",
				title=_("Overtime Processing -- Notes"),
			)


@frappe.whitelist()
def get_employees(docname, all_employees=False, employees=None):
	"""
	Populates the `entries` child table on a RAPL Overtime Processing document.

	Three mutually exclusive modes (checked in this priority order):
	  1. `employees` given (list of Employee IDs, from the manual multi-select
	     picker) -- use exactly this list, no other filter applied.
	  2. all_employees=True -- every active Employee, regardless of attendance
	     or custom_ot.
	  3. all_employees=False (default), employees=None -- only employees with
	     (a) Present attendance in the period AND (b) Employee.custom_ot = 1 --
	     the actual OT-eligible workforce.
	"""
	doc = frappe.get_doc("RAPL Overtime Processing", docname)
	settings = get_automation_settings()
	start_date, end_date = doc.start_date, doc.end_date

	if isinstance(employees, str):
		employees = frappe.parse_json(employees)
	if isinstance(all_employees, str):
		all_employees = all_employees.lower() in ("1", "true", "yes")

	if employees:
		employees = list(employees)  # explicit manual selection -- use as-is, no filtering
	elif all_employees:
		employees = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name")
	else:
		attendance_employees = set(
			frappe.get_all(
				"Attendance",
				filters={
					"attendance_date": ["between", [start_date, end_date]],
					"docstatus": 1,
					"status": "Present",
				},
				pluck="employee",
			)
		)
		ot_eligible_employees = set(
			frappe.get_all("Employee", filters={"custom_ot": 1, "status": "Active"}, pluck="name")
		)
		employees = sorted(attendance_employees & ot_eligible_employees)

	doc.entries = []
	errors = []
	for emp in employees:
		if additional_salary_already_exists(emp, settings.overtime_salary_component, end_date):
			errors.append(f"{emp}: already processed for this period, excluded")
			continue
		result = _compute_employee_overtime(emp, start_date, end_date, settings, errors)
		row = doc.append("entries", {})
		row.employee = emp
		if result:
			row.ot_hours = result["ot_hours"]
			row.ot_rate = result["ot_rate"]
			row.amount = result["ot_amount"]
		else:
			row.ot_hours = 0
			row.ot_rate = 0
			row.amount = 0

	doc.save()

	if errors:
		frappe.msgprint(
			"<br>".join(errors), indicator="orange", title=_("Get Employees -- Notes")
		)

	return doc.name


def _compute_employee_overtime(emp, start_date, end_date, settings, errors):
	"""Same calculation as overtime_automation.py's version -- kept local here
	to avoid the two modules depending on each other's private helpers."""
	grade = frappe.db.get_value("Employee", emp, "grade")
	monthly_salary = frappe.db.get_value("Employee", emp, settings.ot_rate_base_fieldname)

	if not monthly_salary:
		errors.append(f"{emp}: missing '{settings.ot_rate_base_fieldname}', added with 0 (edit manually)")
		return None

	rule = get_grade_ot_rule(settings, grade)
	if rule is None:
		errors.append(f"{emp}: no OT rule configured for grade '{grade}', added with 0 (edit manually)")
		return None

	holiday_list = get_holiday_list_for_employee(emp)
	all_holidays = get_all_holiday_dates(holiday_list, start_date, end_date)
	sunday_dates = get_weekly_off_dates(holiday_list, start_date, end_date)

	base_working_days = get_total_working_days(start_date, end_date)
	ot_working_days = base_working_days - len(sunday_dates) if rule else base_working_days
	if ot_working_days <= 0:
		errors.append(f"{emp}: computed OT working days <= 0, added with 0 (edit manually)")
		return None

	hourly_rate = flt(monthly_salary) / ot_working_days / flt(settings.ot_hours_divisor)
	shift = frappe.get_cached_doc("Shift Type", settings.reference_shift_type)

	total_ot_hours = 0.0
	for day in get_attendance_for_employee(emp, start_date, end_date):
		try:
			if not day.in_time or not day.out_time:
				continue
			day.in_time = get_datetime(day.in_time)
			day.out_time = get_datetime(day.out_time)

			if day.attendance_date in all_holidays:
				ot_hours = flt(day.working_hours) if day.working_hours else (
					day.out_time - day.in_time
				).total_seconds() / 3600
			else:
				shift_end_dt = get_datetime_combine(day.attendance_date, shift.end_time)
				minutes_over = (day.out_time - shift_end_dt).total_seconds() / 60
				ot_hours = 0 if minutes_over <= settings.ot_minimum_minutes else minutes_over / 60

			total_ot_hours += max(ot_hours, 0)
		except Exception as day_err:
			errors.append(f"{emp} / {day.attendance_date}: {day_err} -- day skipped")

	return {
		"ot_hours": round(total_ot_hours, 2),
		"ot_rate": round(hourly_rate, 2),
		"ot_amount": round(total_ot_hours * hourly_rate, 2),
	}
