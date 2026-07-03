# Copyright (c) 2026, RAPL and contributors
#
# Overtime bulk automation. Called from the Payroll Automation Dashboard.
#
# Two-phase design (mirrors HRMS's own filter_employees_for_overtime_slip_creation
# + create_overtime_slips_for_employees pattern, verified in overtime_slip.py):
#   1. compute_overtime_preview()  -- read-only, returns computed amounts for
#      the Dashboard's editable preview table. Creates nothing.
#   2. process_overtime()          -- takes the (possibly user-edited) preview
#      rows and actually creates + submits Additional Salary records.
#
# Rules implemented (all locked during design discussion):
#   Rate base:       custom_monthly_salary (Employee field, = Basic+HRA by construction)
#   Rate divisor:    settings.ot_hours_divisor (8 -- break time excluded)
#   Floor grade:     working days EXCLUDING Sunday (via get_weekly_off_dates)
#   Office grade:    working days INCLUDING Sunday (same as get_total_working_days)
#   Regular day:     >45 min past shift end counts as OT (minutes/60, true hour
#                    fraction, NOT literal minutes-as-decimal); <=45 min = 0
#   Sunday/holiday:  full hours worked count as OT, NO 45-min threshold, RAW
#                    SPAN (no break deduction -- confirmed different from the
#                    regular-day 8-hour-divisor convention)
#   Grade source:    Employee.grade, mapped via settings.grade_ot_rules (Floor/
#                    Office in RAPL's case, but not hardcoded -- reads the
#                    child table so a 3rd grade just needs a new settings row)

import frappe
from frappe.utils import flt, getdate, get_datetime

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
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee


def get_employees_with_attendance_in_period(start_date, end_date, employees=None):
	filters = {
		"attendance_date": ["between", [start_date, end_date]],
		"docstatus": 1,
		"status": "Present",
	}
	rows = frappe.get_all("Attendance", filters=filters, pluck="employee", distinct=True)
	result = sorted(set(rows))
	if employees:
		result = [e for e in result if e in employees]
	return result


def get_attendance_for_employee(employee, start_date, end_date):
	"""Explicit filters: docstatus=1 (submitted only), status=Present only --
	Absent/On Leave/draft/cancelled records must never reach the OT calculation."""
	return frappe.get_all(
		"Attendance",
		filters={
			"employee": employee,
			"attendance_date": ["between", [start_date, end_date]],
			"docstatus": 1,
			"status": "Present",
		},
		fields=["name", "attendance_date", "in_time", "out_time", "working_hours"],
	)


def _compute_employee_overtime(emp, start_date, end_date, settings, errors):
	"""Returns (ot_hours_total, ot_rate, ot_amount) for one employee, or None if skipped."""
	grade = frappe.db.get_value("Employee", emp, "grade")
	monthly_salary = frappe.db.get_value("Employee", emp, settings.ot_rate_base_fieldname)

	if not monthly_salary:
		errors.append(f"{emp}: missing '{settings.ot_rate_base_fieldname}', skipped")
		return None

	rule = get_grade_ot_rule(settings, grade)
	if rule is None:
		errors.append(f"{emp}: no OT rule configured for grade '{grade}', skipped")
		return None

	holiday_list = get_holiday_list_for_employee(emp)
	all_holidays = get_all_holiday_dates(holiday_list, start_date, end_date)  # Sunday + named holidays -- threshold exception
	sunday_dates = get_weekly_off_dates(holiday_list, start_date, end_date)  # Sunday ONLY -- denominator split

	base_working_days = get_total_working_days(start_date, end_date)
	ot_working_days = base_working_days - len(sunday_dates) if rule else base_working_days

	if ot_working_days <= 0:
		errors.append(f"{emp}: computed OT working days <= 0, skipped")
		return None

	hourly_rate = flt(monthly_salary) / ot_working_days / flt(settings.ot_hours_divisor)

	shift = frappe.get_cached_doc("Shift Type", settings.reference_shift_type)
	shift_end = shift.end_time

	total_ot_hours = 0.0
	for day in get_attendance_for_employee(emp, start_date, end_date):
		try:
			if not day.in_time or not day.out_time:
				continue  # incomplete day, silently skipped (surfaced separately by pre-flight check)

			# Defensive cast (frappe.get_all() usually returns proper datetime
			# objects already, but this matches the same fix applied in
			# attendance_automation.py after a confirmed 'str' vs 'datetime'
			# TypeError there -- cheap to guard here too).
			day.in_time = get_datetime(day.in_time)
			day.out_time = get_datetime(day.out_time)

			if day.attendance_date in all_holidays:
				# Sunday/holiday: full raw span, no break deduction, no threshold
				ot_hours = flt(day.working_hours) if day.working_hours else (
					day.out_time - day.in_time
				).total_seconds() / 3600
			else:
				shift_end_dt = get_datetime_combine(day.attendance_date, shift_end)
				minutes_over = (day.out_time - shift_end_dt).total_seconds() / 60
				if minutes_over <= settings.ot_minimum_minutes:
					ot_hours = 0
				else:
					ot_hours = minutes_over / 60

			total_ot_hours += max(ot_hours, 0)
		except Exception as day_err:
			errors.append(f"{emp} / {day.attendance_date}: {day_err} -- day skipped, other days still processed")

	ot_amount = total_ot_hours * hourly_rate
	return {
		"employee": emp,
		"employee_name": frappe.db.get_value("Employee", emp, "employee_name"),
		"grade": grade,
		"ot_hours": round(total_ot_hours, 2),
		"ot_rate": round(hourly_rate, 2),
		"ot_amount": round(ot_amount, 2),
	}


@frappe.whitelist()
def compute_overtime_preview(start_date, end_date, employees=None):
	"""
	Read-only preview for the Dashboard. Computes but does NOT create anything.
	`employees` (optional): list of employee IDs to restrict to (e.g. after the
	pre-flight check excludes some). If omitted, processes everyone with
	Present attendance in the period.
	"""
	settings = get_automation_settings()
	if isinstance(employees, str):
		employees = frappe.parse_json(employees)

	emp_list = get_employees_with_attendance_in_period(start_date, end_date, employees)
	errors = []
	rows = []
	for emp in emp_list:
		if additional_salary_already_exists(emp, settings.overtime_salary_component, end_date):
			errors.append(f"{emp}: already processed for this period, excluded from preview")
			continue
		result = _compute_employee_overtime(emp, start_date, end_date, settings, errors)
		if result:
			rows.append(result)

	return {"rows": rows, "errors": errors}


@frappe.whitelist()
def process_overtime(start_date, end_date, rows):
	"""
	Takes the (possibly user-edited) preview rows from the Dashboard and
	actually creates + submits Additional Salary records. `rows` must be a
	list of dicts with at least "employee" and "ot_amount" -- whatever
	ot_amount is showing (computed or manually edited) is what gets used;
	there's no distinction between the two at this point.
	"""
	settings = get_automation_settings()
	if isinstance(rows, str):
		rows = frappe.parse_json(rows)

	count, errors = 0, []
	for row in rows:
		emp = row.get("employee")
		amount = flt(row.get("ot_amount"))
		if amount <= 0:
			continue
		try:
			if additional_salary_already_exists(emp, settings.overtime_salary_component, end_date):
				errors.append(f"{emp}: already processed for this period, skipped")
				continue
			create_and_submit_additional_salary(
				emp, settings.overtime_salary_component, amount, start_date, end_date
			)
			count += 1
		except Exception as e:
			errors.append(f"{emp}: {e}")

	return {"count": count, "errors": errors}
