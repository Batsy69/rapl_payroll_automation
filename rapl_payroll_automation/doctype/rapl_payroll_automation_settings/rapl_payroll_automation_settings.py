# Copyright (c) 2026, RAPL and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class RAPLPayrollAutomationSettings(Document):
	def validate(self):
		self.validate_half_day_leave_type()
		self.validate_grade_rules_not_duplicated()
		self.validate_band_ordering()

	def validate_half_day_leave_type(self):
		"""
		CRITICAL check: half_day_leave_type must NOT be an LWP or PPL leave type.

		Verified against hrms/payroll/doctype/salary_slip/salary_slip.py:
		- calculate_lwp_ppl_and_absent_days_based_on_attendance() adds to `lwp`
		  whenever status="Half Day" AND leave_type is set AND that leave_type
		  is in leave_type_map (i.e. is_lwp=1 or is_ppl=1).
		- get_half_absent_days() independently counts status="Half Day" AND
		  half_day_status="Absent" with NO leave_type awareness at all.
		Both subtract from payment_days. If half_day_leave_type is LWP/PPL,
		BOTH mechanisms fire on our automated half-day records, causing a
		double deduction (a full day's pay lost instead of half a day's).
		"""
		if not self.half_day_leave_type:
			return

		is_lwp, is_ppl = frappe.db.get_value(
			"Leave Type", self.half_day_leave_type, ["is_lwp", "is_ppl"]
		)
		if is_lwp or is_ppl:
			frappe.throw(
				_(
					"Half Day Leave Type '{0}' has 'Is LWP' or 'Is Partially Paid Leave' "
					"ticked. This WILL cause a double-deduction on every automated Half Day "
					"(verified: both calculate_lwp_ppl_and_absent_days_based_on_attendance() "
					"and get_half_absent_days() would fire on the same Attendance record). "
					"Create a dedicated Leave Type with BOTH flags unticked instead."
				).format(self.half_day_leave_type)
			)

	def validate_grade_rules_not_duplicated(self):
		seen = set()
		for row in self.grade_ot_rules:
			if row.grade in seen:
				frappe.throw(_("Grade '{0}' appears more than once in Grade OT Rules (row {1})").format(row.grade, row.idx))
			seen.add(row.grade)

	def validate_band_ordering(self):
		"""Sanity check: grace < band1 < band2, so the bands are logically ordered."""
		if not (self.late_mark_grace_until < self.late_mark_band1_until < self.late_mark_band2_until):
			frappe.throw(
				_(
					"Late Mark bands must be in increasing order: Grace Until < Band 1 Until < Band 2 Until."
				)
			)
