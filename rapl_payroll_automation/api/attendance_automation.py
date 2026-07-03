# Copyright (c) 2026, RAPL and contributors
#
# Attendance `validate` hook: Late Mark bands + Half Day + Early Exit.
#
# Registered in hooks.py as:
#   doc_events = {
#       "Attendance": {
#           "validate": "rapl_payroll_automation.api.attendance_automation.apply_attendance_deduction_logic"
#       }
#   }
#
# Fires on every Attendance save, including the auto-attendance flow
# (attendance.save() then attendance.submit() back-to-back -- verified in
# employee_checkin.py's create_or_update_attendance/mark_attendance_and_link_log).
#
# Rules implemented (all confirmed with the user across extensive design discussion):
#   09:30-09:45  grace, no deduction
#   09:46-10:00  1/6 day deduction (custom Additional Salary, via bulk function)
#   10:01-10:34  1/4 day deduction (custom Additional Salary, via bulk function)
#   10:35+       Half Day (native mechanism -- status="Half Day", half_day_status="Absent")
#   checkout before 17:00  ALSO Half Day (stacks additively with any late-arrival fraction)
#
# Native Half Day mechanism verified: get_half_absent_days() + payment_days
# reduction via Fraction of Daily Salary for Half Day (0.500) already delivers
# exactly a half-day pay cut through existing `Depends on Payment Days`
# proration -- no custom deduction component needed for the two Half Day
# triggers, only for the two fractional bands.
#
# leave_type is MANDATORY whenever status is Half Day/On Leave (verified:
# mandatory_depends_on on the Attendance doctype). We use a dedicated Leave
# Type (settings.half_day_leave_type) that is explicitly validated (at the
# Settings doctype level) to have BOTH is_lwp and is_ppl unticked, to avoid
# a double-deduction against payment_days (see payroll_automation_utils.py
# docstring and the Settings doctype's validate_half_day_leave_type()).

from frappe.utils import getdate, get_datetime
import frappe

from rapl_payroll_automation.api.payroll_automation_utils import (
	get_all_holiday_dates,
	get_automation_settings,
	get_datetime_combine,
)
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee


def apply_attendance_deduction_logic(doc, method):
	# --- Guard 1: leave-application-driven day (incl. half-day paid leave) ---
	# check_leave_record() (native, runs earlier in Attendance's own validate())
	# will have already set doc.leave_type from a real, approved Leave
	# Application if one exists for this date. If it did, don't let our
	# attendance-time logic override that -- a genuine leave decision takes
	# priority over our automated lateness/early-exit rules.
	if doc.leave_type:
		return

	# --- Guard 2: no check-in data at all (Absent, or genuinely not yet arrived) ---
	if not doc.in_time:
		return

	# doc.in_time/out_time can arrive as plain strings (not yet cast to
	# datetime) on a fresh, client-submitted document at this point in the
	# save lifecycle -- confirmed via a real TypeError in production
	# ('str' - 'datetime.datetime'). get_datetime() is idempotent: safe to
	# call whether the value is already a datetime or still a string.
	doc.in_time = get_datetime(doc.in_time)
	if doc.out_time:
		doc.out_time = get_datetime(doc.out_time)

	settings = get_automation_settings()

	# --- Guard 3: Sunday or any holiday, per the configured Holiday List ---
	# Voluntary-attendance days (overtime only) -- late-mark/half-day/early-exit
	# rules don't apply here at all. Driven entirely by the Holiday List, not a
	# hardcoded weekday check, so this respects whatever "Weekly Off" is
	# actually configured (confirmed = Sunday for RAPL's "Public Holidays 2026").
	holiday_list = get_holiday_list_for_employee(doc.employee)
	if get_all_holiday_dates(holiday_list, doc.attendance_date, doc.attendance_date):
		return

	shift = frappe.get_cached_doc("Shift Type", settings.reference_shift_type)
	shift_start = get_datetime_combine(doc.attendance_date, shift.start_time)

	minutes_late = (doc.in_time - shift_start).total_seconds() / 60

	# Reset our own field every run so re-validation (e.g. amend) recomputes cleanly
	doc.custom_late_deduction_fraction = 0
	is_half_day = False

	grace_minutes = _time_diff_minutes(shift.start_time, settings.late_mark_grace_until)
	band1_minutes = _time_diff_minutes(shift.start_time, settings.late_mark_band1_until)
	band2_minutes = _time_diff_minutes(shift.start_time, settings.late_mark_band2_until)

	if minutes_late <= grace_minutes:
		pass  # grace period, no deduction
	elif minutes_late <= band1_minutes:
		doc.custom_late_deduction_fraction = settings.late_mark_band1_fraction
	elif minutes_late <= band2_minutes:
		doc.custom_late_deduction_fraction = settings.late_mark_band2_fraction
	else:
		is_half_day = True  # 10:35+ arrival (or configured equivalent)

	# --- Early exit check -- stacks additively with any late-arrival fraction above ---
	if doc.out_time:
		early_exit_cutoff = get_datetime_combine(doc.attendance_date, settings.early_exit_cutoff)
		if doc.out_time < early_exit_cutoff:
			is_half_day = True

	if is_half_day:
		doc.status = "Half Day"
		doc.half_day_status = "Absent"
		doc.leave_type = settings.half_day_leave_type


def _time_diff_minutes(start_time, end_time):
	"""
	Minutes between two Time-field values (both HH:MM:SS strings/timedeltas).
	Used to convert the Settings doctype's configured band-boundary Times into
	minutes-since-shift-start, so the comparison against `minutes_late` works
	regardless of what the actual shift start time is configured as.
	"""
	import datetime

	def _to_seconds(t):
		if isinstance(t, datetime.timedelta):
			return t.total_seconds()
		# Time fields sometimes arrive as strings "HH:MM:SS"
		h, m, s = [int(x) for x in str(t).split(":")]
		return h * 3600 + m * 60 + s

	return (_to_seconds(end_time) - _to_seconds(start_time)) / 60
