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
# Salary Slip: before_validate pre-fetches Overtime + Conveyance totals into
#   custom_overtime_for_pt / custom_conveyance_for_deductions, which PF/PT/ESI
#   formulas must reference (see rapl_payroll_automation/api/salary_slip_hooks.py
#   docstring for why before_validate specifically, not validate).
doc_events = {
	"Attendance": {
		"validate": "rapl_payroll_automation.api.attendance_automation.apply_attendance_deduction_logic",
	},
	"Salary Slip": {
		"before_validate": "rapl_payroll_automation.api.salary_slip_hooks.set_precomputed_fields",
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
