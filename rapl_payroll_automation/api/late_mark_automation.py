# Copyright (c) 2026, RAPL and contributors
#
# Late Mark bulk automation. Same two-phase pattern as overtime_automation.py.
#
# Only sums custom_late_deduction_fraction (populated by
# attendance_automation.py's validate hook) -- this is only ever 0, 0.1667, or
# 0.25. The 0.5 (Half Day) case is deliberately excluded here: it's delivered
# entirely through the native payment_days mechanism (status="Half Day" +
# half_day_status="Absent"), not through this Additional Salary path. Summing
# it here too would double-deduct.
#
# Per-day rate = custom_monthly_salary / total_working_days, where
# total_working_days is the SAME get_total_working_days() used for Overtime's
# "Office" grade denominator -- confirmed identical (calendar days in the
# period, since RAPL has "Include holidays in Total no. of Working Days"
# checked). Not Grade-dependent for Late Mark specifically -- confirmed with
# the user that RAPL's Late Mark policy is uniform across Floor/Office.

import frappe
from frappe.utils import flt

from rapl_payroll_automation.api.payroll_automation_utils import (
	additional_salary_already_exists,
	create_and_submit_additional_salary,
	get_automation_settings,
	get_total_working_days,
)


def _ensure_late_deduction_field_exists():
	"""
	Fails clearly, up front, if custom_late_deduction_fraction hasn't been
	created on Attendance yet -- instead of letting the raw SQL query below
	crash with an opaque "unknown column" error. This field must be created
	manually via Customize Form (Attendance -> Float field, precision 4);
	it isn't created by this app's install (see README.md Setup step 2).
	"""
	if not frappe.db.has_column("Attendance", "custom_late_deduction_fraction"):
		frappe.throw(
			"Attendance is missing the 'custom_late_deduction_fraction' field. "
			"Create it via Customize Form (Attendance, Float, precision 4) "
			"before running Late Mark automation -- see README.md Setup step 2."
		)


def get_employees_with_attendance_in_period(start_date, end_date, employees=None):
	"""
	Lists ALL employees with attendance in the period -- not filtered to
	custom_late_deduction_fraction > 0. This is deliberate: every employee
	should be editable in the Dashboard's preview table, including those
	whose computed amount is 0 (e.g. attendance predating this app's
	install, where the fraction field was never populated), so a manual
	correction can be typed directly into their row instead of needing a
	separate "add employee" step.
	"""
	rows = frappe.get_all(
		"Attendance",
		filters={
			"attendance_date": ["between", [start_date, end_date]],
			"docstatus": 1,
		},
		pluck="employee",
		distinct=True,
	)
	result = sorted(set(rows))
	if employees:
		result = [e for e in result if e in employees]
	return result


def _compute_employee_late_mark(emp, start_date, end_date, settings):
	monthly_salary = frappe.db.get_value("Employee", emp, "custom_monthly_salary")
	if not monthly_salary:
		return None, f"{emp}: missing custom_monthly_salary, skipped"

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

	working_days = get_total_working_days(start_date, end_date)
	per_day_rate = flt(monthly_salary) / working_days
	amount = total_fraction * per_day_rate

	return {
		"employee": emp,
		"employee_name": frappe.db.get_value("Employee", emp, "employee_name"),
		"late_fraction_total": round(total_fraction, 4),
		"per_day_rate": round(per_day_rate, 2),
		"late_mark_amount": round(amount, 2),
	}, None


@frappe.whitelist()
def compute_late_mark_preview(start_date, end_date, employees=None):
	_ensure_late_deduction_field_exists()

	settings = get_automation_settings()
	if isinstance(employees, str):
		employees = frappe.parse_json(employees)

	emp_list = get_employees_with_attendance_in_period(start_date, end_date, employees)
	errors = []
	rows = []
	for emp in emp_list:
		if additional_salary_already_exists(emp, settings.late_mark_salary_component, end_date):
			errors.append(f"{emp}: already processed for this period, excluded from preview")
			continue
		result, err = _compute_employee_late_mark(emp, start_date, end_date, settings)
		if err:
			errors.append(err)
			continue
		if result:
			rows.append(result)

	return {"rows": rows, "errors": errors}


@frappe.whitelist()
def process_late_mark(start_date, end_date, rows):
	settings = get_automation_settings()
	if isinstance(rows, str):
		rows = frappe.parse_json(rows)

	count, errors = 0, []
	for row in rows:
		emp = row.get("employee")
		amount = flt(row.get("late_mark_amount"))
		if amount <= 0:
			continue
		try:
			if additional_salary_already_exists(emp, settings.late_mark_salary_component, end_date):
				errors.append(f"{emp}: already processed for this period, skipped")
				continue
			create_and_submit_additional_salary(
				emp, settings.late_mark_salary_component, amount, start_date, end_date
			)
			count += 1
		except Exception as e:
			errors.append(f"{emp}: {e}")

	return {"count": count, "errors": errors}
