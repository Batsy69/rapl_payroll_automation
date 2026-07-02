# RAPL Payroll Automation

Custom Overtime, Late Mark, Half Day, and Early Exit payroll automation for
Rinix Automation Pvt Ltd (RAPL), built on Frappe/ERPNext/HRMS **version-16**.

This app was designed against verified `version-16` source behavior (not
`develop`) -- every mechanism it relies on (Additional Salary merge timing,
`before_validate` hook ordering, native Half Day payment_days reduction, the
Holiday List `weekly_off` mechanism, etc.) was traced against the actual
framework code before being built. See the accompanying **RAPL Payroll Setup
Guide** and **RAPL Component Reconciliation** documents for the full design
rationale and every decision this app implements.

## Requires

- ERPNext (`erpnext`)
- HRMS (`hrms`)
- `version-16` branch specifically -- several mechanisms this app depends on
  (e.g. `before_validate` timing, `get_half_absent_days()`, Holiday List's
  `select_weekly_off` parameter) were verified against this branch. Re-verify
  against source if installing on a different version.

## What this app does

- **Overtime**: computes hourly OT pay per employee, branching on Employee
  Grade (different working-days denominator per grade), with a 45-minute
  minimum threshold on regular days and full-hours-no-threshold on
  Sunday/holidays (raw span, no break deduction).
- **Late Mark**: time-band deductions for late arrival (9:46-10:00 = 1/6 day,
  10:01-10:34 = 1/4 day).
- **Half Day**: automatic, via native HRMS proration (not a custom
  deduction) -- triggered by arrival at/after 10:35, or checkout before
  17:00 (both stack additively with any late-mark fraction).
- **PF/PT/ESI fix**: pre-fetches Overtime + Conveyance totals (which arrive
  via Additional Salary, invisible to Salary Structure formulas otherwise)
  so these three statutory deductions calculate correctly.
- **Dashboard**: user-initiated (never scheduled), pre-flight data check,
  editable preview before anything is created, then bulk-creates Additional
  Salary records.

All specific band times, fractions, thresholds, and the Grade-denominator
mapping are configurable via **RAPL Payroll Automation Settings**
(Setup > RAPL Payroll Automation Settings) -- no code changes needed to
adjust a rule.

## Setup steps (in order)

1. **Install this app** on your bench:
   ```
   bench get-app rapl_payroll_automation /path/to/this/folder
   bench --site [your-site] install-app rapl_payroll_automation
   ```

2. **Create the one custom field this app depends on but does not create
   itself** -- Customize Form > Attendance:
   | Field | Type |
   |---|---|
   | `custom_late_deduction_fraction` | Float |

   (The two Salary Slip custom fields -- `custom_overtime_for_pt` and
   `custom_conveyance_for_deductions` -- should already exist if you followed
   the design conversation; if not, create them the same way, on Salary Slip.)

3. **Create a dedicated Leave Type** for automated Half Days -- e.g. named
   "Attendance-Based Half Day" -- with **both** `Is LWP` and
   `Is Partially Paid Leave` **unticked**. This is not optional: using an
   LWP/PPL-flagged Leave Type here causes a verified double-deduction bug
   (see `rapl_payroll_automation/doctype/rapl_payroll_automation_settings/rapl_payroll_automation_settings.py`
   -- the Settings doctype actively validates against this and will refuse to
   save if you pick the wrong kind of Leave Type).

4. **Confirm your Holiday List has `Weekly Off` set to Sunday.** The entire
   Sunday/holiday detection mechanism (for both Late Mark and Overtime)
   depends on this. Check under HR > Holiday List.

5. **Confirm `Working Hours Threshold for Half Day` stays at 0** in Payroll
   Settings -- a nonzero value activates native auto-attendance's own
   hours-based Half Day marking, which will conflict with this app's
   check-in-time-based logic.

6. **Configure RAPL Payroll Automation Settings** (Setup > RAPL Payroll
   Automation Settings):
   - Reference Shift Type
   - Half Day Leave Type (the dedicated one from step 3)
   - Late Mark band times/fractions (defaults match RAPL's locked design)
   - Early Exit cutoff
   - OT minimum minutes, hours divisor, rate base fieldname
   - Overtime / Late Mark Salary Component names
   - Grade OT Denominator Rules (child table) -- add a row per Employee
     Grade, ticking "Exclude Weekly Off" for grades like Floor (Sunday
     excluded from the OT rate denominator) and leaving it unticked for
     grades like Office (Sunday included).

7. **Update the PF, PT, and ESI Salary Component formulas** to reference
   `custom_overtime_for_pt` and `custom_conveyance_for_deductions` instead of
   the (now-dead) `OT`/`CON` component-abbreviation references. See the
   Component Reconciliation document for the exact corrected formulas.

8. **Remove Overtime from the Salary Structure** if it's currently a live
   formula component there -- it must be Additional-Salary-only, or it will
   double-pay once this automation goes live.

9. **Pilot test** on one payroll period with a small employee subset (one
   Floor grade, one Office grade employee) before trusting this for the full
   workforce. Manually cross-check the computed amounts by hand.

## Not yet built (see Component Reconciliation doc for full checklist)

- Audit-log doctype for automation runs (currently only `msgprint` output)
- Whether Employee Grade should be made a mandatory field
- Staging/UAT plan beyond the pilot-test recommendation above

## Structure

```
rapl_payroll_automation/
├── doctype/
│   ├── rapl_payroll_automation_settings/   (Single -- all configurable rules)
│   └── rapl_grade_ot_denominator_rule/     (child table -- Grade -> denominator rule)
├── api/
│   ├── payroll_automation_utils.py         (shared helpers)
│   ├── attendance_automation.py            (Late Mark / Half Day / Early Exit)
│   ├── salary_slip_hooks.py                (PF/PT/ESI visibility fix)
│   ├── overtime_automation.py              (Overtime bulk preview + process)
│   ├── late_mark_automation.py             (Late Mark bulk preview + process)
│   └── payroll_preflight_check.py          (pre-flight data quality check)
└── page/
    └── payroll_automation_dashboard/       (user-facing dashboard)
```

## Important caveat

This app was designed and written through detailed source verification, but
**has not been executed against a live Frappe bench.** Treat it as a
thoroughly-designed first draft to debug against, not a tested,
drop-in-and-trust deliverable. Test each piece (the Attendance script in
isolation, then the bulk functions against a single employee, then the full
Dashboard flow) before relying on it for real payroll.
