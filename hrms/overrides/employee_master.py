# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.model.naming import set_name_by_naming_series
from frappe.query_builder import Interval
from frappe.query_builder.functions import Count, CurDate, UnixTimestamp
from frappe.utils import add_years, cint, get_link_to_form, getdate

from erpnext.setup.doctype.employee.employee import Employee


class EmployeeMaster(Employee):
	def autoname(self):
		naming_method = frappe.db.get_single_value("HR Settings", "emp_created_by")
		if not naming_method:
			frappe.throw(_("Please setup Employee Naming System in Human Resource > HR Settings"))
		else:
			if naming_method == "Naming Series":
				set_name_by_naming_series(self)
			elif naming_method == "Employee Number":
				self.name = self.employee_number
			elif naming_method == "Full Name":
				self.set_employee_name()
				self.name = self.employee_name

		self.employee = self.name


def validate_onboarding_process(doc, method=None):
	"""Validates Employee Creation for linked Employee Onboarding"""
	job_applicant = doc.get("job_applicant")
	job_offer = doc.get("job_offer")

	filters = {"docstatus": 1, "boarding_status": ("!=", "Completed")}
	if job_offer:
		filters["job_offer"] = job_offer
	elif job_applicant:
		filters["job_applicant"] = job_applicant
	else:
		return

	employee_onboarding = frappe.get_all("Employee Onboarding", filters=filters)
	if employee_onboarding:
		onboarding = frappe.get_doc("Employee Onboarding", employee_onboarding[0].name)
		onboarding.validate_employee_creation()
		onboarding.db_set("employee", doc.name)


def publish_update(doc, method=None):
	import hrms

	hrms.refetch_resource("hrms:employee", doc.user_id)


def update_job_applicant_and_offer(doc, method=None):
	"""Updates Job Applicant and Job Offer status as 'Accepted' and submits them"""
	job_applicant = doc.get("job_applicant")
	job_offer = get_linked_job_offer(doc, job_applicant)

	if job_offer and job_offer.status in ("Rejected", "Cancelled"):
		frappe.msgprint(
			_(
				"Linked Job Offer {0} was {1}. Please update the Job Offer status if this hire was intended."
			).format(get_link_to_form("Job Offer", job_offer.name), frappe.bold(_(job_offer.status))),
			title=_("Job Offer Status Not Updated"),
			indicator="orange",
		)
		return

	if job_applicant:
		applicant_status_before_change = frappe.db.get_value("Job Applicant", job_applicant, "status")
		if applicant_status_before_change != "Accepted":
			frappe.db.set_value("Job Applicant", job_applicant, "status", "Accepted")
			frappe.msgprint(
				_("Updated the status of linked Job Applicant {0} to {1}").format(
					get_link_to_form("Job Applicant", job_applicant), frappe.bold(_("Accepted"))
				)
			)

	if not job_offer or job_offer.status == "Accepted":
		return

	job_offer.status = "Accepted"
	job_offer.flags.ignore_mandatory = True
	job_offer.flags.ignore_permissions = True
	job_offer.save()

	msg = _("Updated the status of Job Offer {0} for {1} to {2}").format(
		get_link_to_form("Job Offer", job_offer.name),
		frappe.bold(job_offer.applicant_name),
		frappe.bold(_("Accepted")),
	)
	if job_offer.docstatus == 0:
		msg += "<br>" + _("You may add additional details, if any, and submit the offer.")

	frappe.msgprint(msg)


def get_linked_job_offer(doc, job_applicant: str | None):
	offer_name = doc.get("job_offer")
	if not offer_name and job_applicant:
		offer_name = frappe.db.get_value(
			"Job Offer",
			{"job_applicant": job_applicant, "docstatus": ["!=", 2]},
			"name",
			order_by="creation desc",
		)
	if not offer_name:
		return None

	job_offer = frappe.get_doc("Job Offer", offer_name)
	return None if job_offer.docstatus == 2 else job_offer


def update_approver_role(doc, method=None):
	"""Adds relevant approver role for the user linked to Employee"""
	if doc.leave_approver:
		user = frappe.get_doc("User", doc.leave_approver)
		user.flags.ignore_permissions = True
		user.add_roles("Leave Approver")

	if doc.expense_approver:
		user = frappe.get_doc("User", doc.expense_approver)
		user.flags.ignore_permissions = True
		user.add_roles("Expense Approver")


def update_approver_user_roles(doc, method=None):
	approver_roles = set()
	if frappe.db.exists("Employee", {"leave_approver": doc.name}):
		approver_roles.add("Leave Approver")

	if frappe.db.exists("Employee", {"expense_approver": doc.name}):
		approver_roles.add("Expense Approver")

	if approver_roles:
		doc.append_roles(*approver_roles)


def update_employee_transfer(doc, method=None):
	"""Unsets Employee ID in Employee Transfer if doc is deleted"""
	if frappe.db.exists("Employee Transfer", {"new_employee_id": doc.name, "docstatus": 1}):
		emp_transfer = frappe.get_doc("Employee Transfer", {"new_employee_id": doc.name, "docstatus": 1})
		emp_transfer.db_set("new_employee_id", "")


@frappe.whitelist()
def get_timeline_data(doctype: str, name: str) -> dict:
	"""Return timeline for attendance"""
	from frappe.desk.notifications import get_open_count

	if doctype != "Employee":
		frappe.throw(_("Timeline data is only available for Employee"))

	out = {}

	frappe.has_permission("Employee", "read", name, throw=True)
	frappe.has_permission("Attendance", "read", throw=True)

	open_count = get_open_count(doctype, name)
	out["count"] = open_count["count"]

	Attendance = frappe.qb.DocType("Attendance")

	timeline_data = dict(
		(
			frappe.qb.from_(Attendance)
			.select(
				UnixTimestamp(Attendance.attendance_date),
				Count("*"),
			)
			.where(
				(Attendance.employee == name)
				& (Attendance.docstatus == 1)
				& (Attendance.attendance_date > (CurDate() - Interval(years=1)))
				& (Attendance.status.isin(["Present", "Half Day"]))
			)
			.groupby(Attendance.attendance_date)
		).run()
	)

	out["timeline_data"] = timeline_data
	return out


@frappe.whitelist()
def get_attendance_heatmap(employee: str) -> dict:
	"""Colour codes for the Employee attendance calendar, matching the Monthly Attendance Sheet:
	{"days": {"YYYY-MM-DD": "P" | "HD" | "SP" | "✓" | "A" | "H"}, "months": {"YYYY-MM": "present/working"},
	"start": first day shown, "end": today}.
	Working days count from the employee's first attendance record (or joining) up to today."""
	from hrms.hr.report.monthly_attendance_sheet.monthly_attendance_sheet import (
		get_attendance_markers,
		get_month_summaries,
		get_pending_punch_markers,
	)
	from hrms.utils import get_date_range
	from hrms.utils.holiday_list import get_holiday_dates_between_range

	frappe.has_permission("Employee", "read", employee, throw=True)
	frappe.has_permission("Attendance", "read", throw=True)

	end = getdate()
	start = add_years(end, -1)
	company, joined = frappe.db.get_value("Employee", employee, ["company", "date_of_joining"])

	attendance = frappe.get_all(
		"Attendance",
		filters={"employee": employee, "docstatus": 1, "attendance_date": ("between", [start, end])},
		fields=["name", "employee", "attendance_date", "status", "half_day_status", "shift", "attendance_request"],
		order_by="attendance_date",
	)
	markers = get_attendance_markers(attendance)
	markers.update(
		get_pending_punch_markers(
			frappe._dict(
				filter_based_on="Date Range", start_date=start, end_date=end, companies=[company], employee=employee
			)
		)
	)

	days, status_by_date = {}, {}
	codes = {"Present": "P", "Work From Home": "P", "Half Day": "HD", "Absent": "A"}
	for d in attendance:
		marker = markers.get((d.employee, d.shift or "", d.attendance_date))
		code = "✓" if marker == "✓" else marker if marker == "SP" else codes.get(d.status)
		if code:
			days[str(d.attendance_date)] = code
		status_by_date[d.attendance_date] = (
			f"Half Day/Other Half {d.half_day_status or 'Absent'}" if d.status == "Half Day" else d.status
		)
	# today's punches, before attendance is marked
	for (_employee, _shift, day), marker in markers.items():
		if str(day) not in days and marker in ("SP", "P", "HD"):
			days[str(day)] = marker

	if attendance:
		first = max(attendance[0].attendance_date, getdate(joined) if joined else attendance[0].attendance_date)
		holidays = set(get_holiday_dates_between_range(employee, first, end, raise_exception_for_holiday_list=False))
		for date in get_date_range(first, end):
			date = getdate(date)
			status_by_date.setdefault(date, "Holiday" if date in holidays else None)
			if date in holidays:
				status_by_date[date] = "Holiday"
				days.setdefault(str(date), "H")

	months = {key.replace("month_", "").replace("_", "-"): value for key, value in get_month_summaries(status_by_date).items()}
	return {"days": days, "months": months, "start": str(start), "end": str(end)}


@frappe.whitelist()
def get_assignable_masters(company: str) -> dict[str, bool]:
	"""Return whether a submitted master exists for each gated Employee assignment action"""
	masters = {
		"Leave Policy": {"docstatus": 1},
		"Salary Structure": {"docstatus": 1, "is_active": "Yes", "company": company},
		"Shift Schedule": {"docstatus": 1},
	}

	return {
		doctype: frappe.has_permission(doctype, "select")
		and bool(frappe.get_list(doctype, filters=filters, limit=1, pluck="name"))
		for doctype, filters in masters.items()
	}


@frappe.whitelist()
def get_retirement_date(date_of_birth: str | None = None):
	if date_of_birth:
		try:
			retirement_age = cint(frappe.db.get_single_value("HR Settings", "retirement_age") or 60)
			dt = add_years(getdate(date_of_birth), retirement_age)
			return dt.strftime("%Y-%m-%d")
		except ValueError:
			# invalid date
			return
