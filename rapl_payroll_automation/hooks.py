app_name = "rapl_payroll_automation"
app_title = "RAPL Payroll Automation"
app_publisher = "Rinix Automation Pvt Ltd"
app_description = "Custom Overtime, Late Mark, Half Day, and Early Exit payroll automation for RAPL, built on Frappe HRMS (version-16)."
app_email = "admin@rinix.example"
app_license = "mit"

# This app reads/writes Employee, Attendance, Shift Type, Leave Type, Salary
# Slip, Salary Component, Additional Salary, Salary Structure Assignment --
# all from ERPNext/HRMS. Both must be installed first.
required_apps = ["erpnext", "hrms"]

# Doc events -----------------------------------------------------------------
# Attendance: Late Mark bands, Half Day (10:35+ arrival OR pre-17:00 exit),
#   Sunday/holiday guard (Holiday-List-driven), paid-leave guard.
# Salary Slip: two hooks --
#   before_validate: pre-fetches Overtime + Conveyance totals into
#     custom_overtime_for_pt / custom_conveyance_for_deductions -- reference/
#     audit fields on the slip only, no longer read by any formula (see
#     salary_slip_hooks.py module docstring for why: a same-day HRMS update
#     moved formula evaluation to Salary Structure Assignment, which never
#     sees the Salary Slip at all, so a Salary-Slip-field-based fix stopped
#     being viable).
#   validate: runs AFTER Salary Slip's own calculate_net_pay() completes,
#     directly overwrites PF/PT/ESI deduction amounts with the correct
#     Conveyance+Overtime-inclusive figures, computed in plain Python --
#     bypasses the formula sandbox entirely. See salary_slip_hooks.py for
#     the full architecture explanation.
doc_events = {
	"Attendance": {
		"validate": "rapl_payroll_automation.api.attendance_automation.apply_attendance_deduction_logic",
	},
	"Salary Slip": {
		"before_validate": "rapl_payroll_automation.api.salary_slip_hooks.set_precomputed_fields",
		"validate": "rapl_payroll_automation.api.salary_slip_hooks.correct_statutory_deductions",
	},
}

# Fixtures ---------------------------------------------------------------
# The one remaining custom field this app depends on but does not create
# itself (Attendance.custom_late_deduction_fraction) should either be:
#   (a) created manually via Customize Form on the target site, OR
#   (b) added here as a Custom Field fixture once the app is installed on a
#       bench and the field has been created once via the UI (export via
#       `bench --site [site] export-fixtures`).
# Left empty deliberately -- see README.md "Setup Steps" for the manual step.
fixtures = []
