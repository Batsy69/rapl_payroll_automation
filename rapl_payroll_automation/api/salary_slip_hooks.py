# Copyright (c) 2026, RAPL and contributors
#
# Salary Slip `before_validate` hook.
#
# Registered in hooks.py as:
#   doc_events = {
#       "Salary Slip": {
#           "before_validate": "rapl_payroll_automation.api.salary_slip_hooks.set_precomputed_fields"
#       }
#   }
#
# WHY before_validate and not validate: verified against frappe/model/document.py
# -- run_before_save_methods() calls run_method("before_validate") as its own
# separate step, strictly BEFORE run_method("validate"). Salary Slip's own
# validate() is what calls calculate_net_pay() (all formula evaluation,
# including PF/PT/ESI). A plain `validate` doc_event would fire AFTER formulas
# already ran with stale/zero data -- confirmed via Document.hook()'s
# compose(): the doctype's own method (fn) runs first, doc_events hooks run
# after. before_validate is the only checkpoint early enough to matter.
# Salary Slip has no existing before_validate() of its own (confirmed: no
# `def before_validate` in salary_slip.py) -- no collision risk.
#
# WHY this is needed at all: PF, PT, and ESI formulas reference Conveyance and
# Overtime amounts, but both arrive via Additional Salary, which merges onto
# the slip AFTER deduction formulas evaluate (add_structure_components runs
# before add_additional_salary_components -- verified in salary_slip.py).
# Without this fix, PF/PT/ESI always compute as if Conveyance=0 and OT=0.
#
# Custom fields this populates (must exist on Salary Slip):
#   custom_overtime_for_pt          (Currency)
#   custom_conveyance_for_deductions (Currency)
#
# Formulas that must reference these fields (not the dead OT/CON abbreviations):
#   PF:  1800 if (B+custom_conveyance_for_deductions)>15000 else (B+custom_conveyance_for_deductions)*0.12
#   PT:  every band's income test uses (B+HRA+custom_conveyance_for_deductions+custom_overtime_for_pt)
#   ESI: (B+HRA+custom_conveyance_for_deductions+custom_overtime_for_pt)*0.0075

from rapl_payroll_automation.api.payroll_automation_utils import (
	get_additional_salary_total,
	get_automation_settings,
)


def set_precomputed_fields(doc, method):
	if not doc.employee or not doc.start_date or not doc.end_date:
		return

	settings = get_automation_settings()

	doc.custom_overtime_for_pt = get_additional_salary_total(
		doc.employee, settings.overtime_salary_component, doc.start_date, doc.end_date
	)
	doc.custom_conveyance_for_deductions = get_additional_salary_total(
		doc.employee, "Conveyance", doc.start_date, doc.end_date
	)
