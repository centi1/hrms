# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

from datetime import datetime

import frappe
from frappe.utils import add_days, add_months, get_time, get_year_ending, get_year_start, getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.hr.doctype.attendance.attendance import mark_attendance
from hrms.hr.doctype.attendance_request.attendance_request import OverlappingAttendanceRequestError
from hrms.hr.doctype.leave_application.test_leave_application import make_allocation_record
from hrms.hr.doctype.leave_type.test_leave_type import create_leave_type
from hrms.payroll.doctype.salary_slip.test_salary_slip import (
	make_leave_application,
)
from hrms.tests.test_utils import add_date_to_holiday_list, get_first_sunday, get_non_holiday_date
from hrms.tests.utils import HRMSTestSuite


class TestAttendanceRequest(HRMSTestSuite):
	def setUp(self):
		self.holiday_list = "Salary Slip Test Holiday List"
		self.employee = get_employee()
		# anchor to a working day so tests that mark attendance for "today" do not
		# fail when the suite runs on a weekend / holiday
		self.date = get_non_holiday_date(self.employee.name)

	def test_attendance_request_overlap(self):
		create_attendance_request(employee=self.employee.name, reason="On Duty", company="_Test Company")

		today = getdate()
		dateranges = [
			(add_days(today, -2), today),
			(today, today),
			(today, add_days(today, 1)),
			(add_days(today, -2), add_days(today, 2)),
		]
		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"reason": "On Duty",
				"company": "_Test Company",
			}
		)

		for entry in dateranges:
			attendance_request.from_date = entry[0]
			attendance_request.to_date = entry[1]
			self.assertRaises(OverlappingAttendanceRequestError, attendance_request.save)

		# no overlap
		attendance_request.from_date = add_days(today, -3)
		attendance_request.to_date = add_days(today, -2)
		attendance_request.save()

	def test_on_duty_attendance_request(self):
		"Test creation of Attendance from Attendance Request, on duty."
		attendance_request = create_attendance_request(
			employee=self.employee.name,
			reason="On Duty",
			company="_Test Company",
			from_date=self.date,
			to_date=self.date,
		)
		records = self.get_attendance_records(attendance_request.name)

		self.assertEqual(len(records), 1)
		self.assertEqual(records[0].status, "Present")
		self.assertEqual(records[0].docstatus, 1)

		# cancelling attendance request cancels linked attendances
		attendance_request.cancel()

		# cancellation alters docname
		# fetch attendance value again to avoid stale docname
		records = self.get_attendance_records(attendance_request.name)
		self.assertEqual(records[0].docstatus, 2)

	def test_work_from_home_attendance_request(self):
		"Test creation of Attendance from Attendance Request, work from home."
		attendance_request = create_attendance_request(
			employee=self.employee.name, reason="Work From Home", company="_Test Company"
		)
		records = self.get_attendance_records(attendance_request.name)

		self.assertEqual(records[0].status, "Work From Home")

		# cancelling attendance request cancels linked attendances
		attendance_request.cancel()
		records = self.get_attendance_records(attendance_request.name)
		self.assertEqual(records[0].docstatus, 2)

	def test_overwrite_attendance(self):
		attendance_name = mark_attendance(self.employee.name, self.date, "Absent")

		attendance_request = create_attendance_request(
			employee=self.employee.name,
			reason="Work From Home",
			company="_Test Company",
			from_date=self.date,
			to_date=self.date,
		)
		prev_attendance = frappe.get_doc("Attendance", attendance_name)

		# attendance request should overwrite attendance status from Absent to Work From Home
		self.assertEqual(prev_attendance.status, "Work From Home")
		self.assertEqual(prev_attendance.attendance_request, attendance_request.name)

	def test_skip_attendance_on_holiday(self):
		today = getdate()
		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		add_date_to_holiday_list(today, self.holiday_list)

		attendance_request = create_attendance_request(
			employee=self.employee.name, reason="On Duty", company="_Test Company"
		)

		records = self.get_attendance_records(attendance_request.name)
		# only 1 attendance marked for yesterday
		# attendance skipped for today since its a holiday
		self.assertEqual(len(records), 1)
		self.assertEqual(records[0].status, "Present")

	def test_skip_attendance_on_leave(self):
		self.from_date = get_year_start(add_months(getdate(), -1))
		self.to_date = get_year_ending(getdate())

		frappe.delete_doc_if_exists("Leave Type", "Test Skip Attendance", force=1)
		leave_type = frappe.get_doc(leave_type_name="Test Skip Attendance", doctype="Leave Type").insert()

		make_allocation_record(leave_type=leave_type.name, from_date=self.from_date, to_date=self.to_date)
		today = getdate()
		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		make_leave_application(self.employee.name, today, today, leave_type.name)
		attendance_request = create_attendance_request(
			employee=self.employee.name, reason="On Duty", company="_Test Company"
		)
		records = self.get_attendance_records(attendance_request.name)

		# only 1 attendance marked for yesterday
		# attendance skipped for today since its a leave
		self.assertEqual(len(records), 1)
		self.assertEqual(records[0].attendance_date, add_days(today, -1))
		self.assertEqual(records[0].status, "Present")

	def test_include_holidays_check(self):
		# Create a holiday on today's date
		today = getdate()
		add_date_to_holiday_list(today, self.holiday_list)

		# Create an Attendance Request with include_holidays checked
		attendance_request = create_attendance_request(
			employee=self.employee.name,
			reason="On Duty",
			company="_Test Company",
			include_holidays=1,  # Set include_holidays to True
		)

		# Check if the attendance record is created on the holiday
		records = self.get_attendance_records(attendance_request.name)
		self.assertEqual(len(records), 2)
		self.assertEqual(records[0].status, "Present")
		self.assertEqual(records[0].attendance_date, today)

	def get_attendance_records(self, attendance_request: str) -> list[dict]:
		return frappe.db.get_all(
			"Attendance",
			{
				"attendance_request": attendance_request,
			},
			["status", "docstatus", "attendance_date"],
		)

	def test_validate_no_attendance_to_create(self):
		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		today = getdate()
		yesterday = add_days(today, -1)
		# marking absent for two days
		for day in [yesterday, today]:
			mark_attendance(self.employee.name, day, "Present")
		# attendance request with the same status for the same days
		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": yesterday,
				"to_date": today,
				"reason": "On Duty",
				"company": "_Test Company",
			}
		)
		self.assertRaises(frappe.ValidationError, attendance_request.save)

		# adding an extra day to the attendance request
		attendance_request.to_date = add_days(today, 1)
		attendance_request.save()
		attendance_request.submit()
		# attendance created for the third day
		records = self.get_attendance_records(attendance_request.name)
		self.assertEqual(records[0].status, "Present")

	def test_half_day_status_change(self):
		# when new attendance is created via attendance request
		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": self.date,
				"to_date": self.date,
				"reason": "On Duty",
				"half_day": 1,
				"half_day_date": self.date,
				"company": "_Test Company",
			}
		).save()
		attendance_request.submit()

		half_day_status = frappe.get_value(
			"Attendance", {"attendance_request": attendance_request.name}, "half_day_status"
		)
		self.assertEqual(half_day_status, "Absent")

	def test_half_day_status_change_when_existing_attendance_is_updated(self):
		# when existing attendance is updated via attendance request
		frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee.name,
				"attendance_date": self.date,
				"status": "Absent",
				"company": "_Test Company",
			}
		).insert()

		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": self.date,
				"to_date": self.date,
				"reason": "On Duty",
				"half_day": 1,
				"half_day_date": self.date,
				"company": "_Test Company",
			}
		).save()
		attendance_request.submit()

		half_day_status = frappe.get_value(
			"Attendance", {"attendance_request": attendance_request.name}, "half_day_status"
		)
		self.assertEqual(half_day_status, "Absent")

	def test_half_day_absent_half_to_present(self):
		"""Test attendance request updates half_day_status from Absent to Present when existing Half Day attendance has the other half marked absent"""
		today = self.date

		mark_attendance(self.employee.name, today, "Half Day", half_day_status="Absent")

		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": today,
				"to_date": today,
				"reason": "On Duty",
				"half_day": 1,
				"half_day_date": today,
				"company": "_Test Company",
			}
		).save()
		attendance_request.submit()

		updated = frappe.db.get_value(
			"Attendance",
			{"employee": self.employee.name, "attendance_date": today, "docstatus": 1},
			["status", "half_day_status"],
			as_dict=True,
		)
		self.assertEqual(updated.status, "Half Day")
		self.assertEqual(updated.half_day_status, "Present")

	def test_half_day_with_shift_auto_absent(self):
		"""Test half-day attendance request after shift_type auto-flags the other half as absent due to missing checkins"""
		from_date = get_year_start(add_months(getdate(), -1))
		to_date = get_year_ending(getdate())
		today = getdate()

		frappe.delete_doc_if_exists("Leave Type", "Test Half Day Leave", force=1)
		leave_type = frappe.get_doc(leave_type_name="Test Half Day Leave", doctype="Leave Type").insert()
		make_allocation_record(leave_type=leave_type.name, from_date=from_date, to_date=to_date)
		frappe.db.delete("Holiday", {"parent": self.holiday_list})

		# 1) Submit half-day leave
		leave_application = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee.name,
				"leave_type": leave_type.name,
				"from_date": today,
				"to_date": today,
				"half_day": 1,
				"half_day_date": today,
				"status": "Approved",
			}
		).insert()
		leave_application.submit()

		# 2) Create shift type + assignment
		shift_type = create_shift("Test Half Day Shift", "09:00:00", "17:00:00")
		shift_type.process_attendance_after = add_days(today, -1)
		shift_type.last_sync_of_checkin = add_days(today, 1)
		shift_type.enable_auto_attendance = 1
		shift_type.save()
		create_shift_assignment(self.employee.name, shift_type.name, add_days(today, -1), add_days(today, 1))

		# 3) Shift auto-attendance marks the other half absent when no checkins exist
		frappe.get_doc("Shift Type", shift_type.name).mark_absent_for_half_day_dates(self.employee.name)
		self.assertEqual(
			frappe.db.get_value(
				"Attendance", {"leave_application": leave_application.name}, "half_day_status"
			),
			"Absent",
		)

		# 4) Attendance request for the other half updates the same attendance
		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": today,
				"to_date": today,
				"reason": "On Duty",
				"half_day": 1,
				"half_day_date": today,
				"company": "_Test Company",
			}
		).save()
		attendance_request.submit()

		# Verify
		attendance = frappe.get_all(
			"Attendance",
			filters={"employee": self.employee.name, "attendance_date": today, "docstatus": 1},
			fields=[
				"status",
				"half_day_status",
				"modify_half_day_status",
				"attendance_request",
			],
		)
		self.assertEqual(len(attendance), 1)
		self.assertEqual(attendance[0].status, "Half Day")
		self.assertEqual(attendance[0].half_day_status, "Present")
		self.assertEqual(attendance[0].modify_half_day_status, 0)
		self.assertEqual(attendance[0].attendance_request, attendance_request.name)

	def test_half_day_request_on_full_leave_day(self):
		"""Half day leave on a different date of a multi-day leave must not unblock a half day request"""
		today = getdate()
		leave_start = add_days(today, -2)
		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		leave_type = create_leave_type(leave_type_name="Test Half Day Leave")
		make_allocation_record(
			leave_type=leave_type.name,
			from_date=get_year_start(add_months(today, -1)),
			to_date=get_year_ending(today),
		)
		make_leave_application(
			self.employee.name, leave_start, today, leave_type.name, half_day=1, half_day_date=leave_start
		)

		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": today,
				"to_date": today,
				"reason": "On Duty",
				"half_day": 1,
				"half_day_date": today,
				"company": "_Test Company",
			}
		)
		self.assertEqual(
			attendance_request.get_attendance_warnings(),
			[{"date": today, "reason": "On Leave", "action": "Skip"}],
		)

	def test_half_day_request_on_two_half_day_leaves(self):
		"""Two half day leaves on the same date cover the whole day, so a half day request is blocked"""
		today = getdate()
		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		leave_type = create_leave_type(leave_type_name="Test Half Day Leave")
		make_allocation_record(
			leave_type=leave_type.name,
			from_date=get_year_start(add_months(today, -1)),
			to_date=get_year_ending(today),
		)
		for _ in range(2):
			make_leave_application(
				self.employee.name, today, today, leave_type.name, half_day=1, half_day_date=today
			)

		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": today,
				"to_date": today,
				"reason": "On Duty",
				"half_day": 1,
				"half_day_date": today,
				"company": "_Test Company",
			}
		)
		self.assertEqual(
			attendance_request.get_attendance_warnings(),
			[{"date": today, "reason": "On Leave", "action": "Skip"}],
		)

	def test_expired_shift_assignment_is_auto_fetched(self):
		"""Backdated attendance requests should auto-fetch the shift even after the
		assignment has been marked Inactive by mark_expired_shift_assignments_as_inactive."""
		from hrms.hr.doctype.shift_assignment.shift_assignment import (
			mark_expired_shift_assignments_as_inactive,
		)

		today = getdate()
		shift_start = add_days(today, -10)
		shift_end = add_days(today, -5)

		shift_type = create_shift("Test Expired Shift", "09:00:00", "17:00:00")
		create_shift_assignment(self.employee.name, shift_type.name, shift_start, shift_end)

		# Cron auto-marks the assignment Inactive because its end_date is in the past
		mark_expired_shift_assignments_as_inactive()

		assignment_status = frappe.db.get_value(
			"Shift Assignment",
			{"employee": self.employee.name, "shift_type": shift_type.name},
			"status",
		)
		self.assertEqual(assignment_status, "Inactive")

		# Attendance request for the now-expired shift period — shift should still be auto-fetched
		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": shift_start,
				"to_date": shift_end,
				"reason": "On Duty",
				"company": "_Test Company",
			}
		).save()

		self.assertEqual(attendance_request.shift, shift_type.name)

	def test_open_ended_shift_assignment_is_auto_fetched(self):
		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		shift_type = create_shift("Test Open Ended Shift", "09:00:00", "17:00:00")
		create_shift_assignment(self.employee.name, shift_type.name, getdate(), None)

		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": getdate(),
				"to_date": getdate(),
				"reason": "On Duty",
			}
		).save()

		self.assertEqual(attendance_request.shift, shift_type.name)

	def test_default_shift_is_auto_fetched(self):
		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		shift_type = create_shift("Test Default Shift", "09:00:00", "17:00:00")
		frappe.db.set_value("Employee", self.employee.name, "default_shift", shift_type.name)
		# an assignment stopped before its end date no longer applies
		stopped_shift = create_shift("Test Stopped Shift", "09:00:00", "17:00:00")
		create_shift_assignment(self.employee.name, stopped_shift.name, getdate(), getdate()).db_set(
			"status", "Inactive"
		)

		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": getdate(),
				"to_date": getdate(),
				"reason": "On Duty",
			}
		).save()

		self.assertEqual(attendance_request.shift, shift_type.name)

		# the stopped shift may still have applied on the requested date, so it can be selected
		attendance_request.shift = stopped_shift.name
		attendance_request.save()

	def test_shift_not_assigned_to_employee(self):
		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		assigned_shift = create_shift("Test Assigned Shift", "09:00:00", "17:00:00")
		other_shift = create_shift("Test Other Shift", "09:00:00", "17:00:00")
		create_shift_assignment(self.employee.name, assigned_shift.name, getdate(), getdate())

		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": getdate(),
				"to_date": getdate(),
				"reason": "On Duty",
				"shift": other_shift.name,
			}
		)

		self.assertRaises(frappe.ValidationError, attendance_request.save)

	def test_shift_change_within_request_period(self):
		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		shift_1 = create_shift("Test Assigned Shift", "09:00:00", "17:00:00")
		shift_2 = create_shift("Test Other Shift", "09:00:00", "17:00:00")
		create_shift_assignment(
			self.employee.name, shift_1.name, add_days(getdate(), -1), add_days(getdate(), -1)
		)
		create_shift_assignment(self.employee.name, shift_2.name, getdate(), getdate())

		attendance_request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": self.employee.name,
				"from_date": add_days(getdate(), -1),
				"to_date": getdate(),
				"reason": "On Duty",
			}
		)

		# the shift changes within the period, so no single shift is filled in
		attendance_request.save()
		self.assertFalse(attendance_request.shift)

		# attendance is not marked on a holiday, so only the working day's shift is filled in
		add_date_to_holiday_list(getdate(), self.holiday_list)
		attendance_request.save()
		self.assertEqual(attendance_request.shift, shift_1.name)

	def test_overwrite_attendance_without_shift(self):
		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		shift_type = create_shift("Test Assigned Shift", "09:00:00", "17:00:00")
		create_shift_assignment(self.employee.name, shift_type.name, getdate(), getdate())
		attendance_name = mark_attendance(self.employee.name, getdate(), "Absent")

		create_attendance_request(employee=self.employee.name, from_date=getdate(), to_date=getdate())

		attendance = frappe.db.get_value("Attendance", attendance_name, ["status", "shift"], as_dict=True)
		self.assertEqual(attendance.status, "Present")
		self.assertEqual(attendance.shift, shift_type.name)

	def test_overwrite_attendance_under_a_previous_overlapping_shift(self):
		# the day was marked under the employee's shift of that time; the default shift has changed
		# since, so the request fetches the new one: the old record is updated, not duplicated
		# (Athen 2026-11-10: "Attendance ... already marked for an overlapping shift Workshop")
		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		old_shift = create_shift("Test Old Default Shift", "09:00:00", "18:30:00")
		new_shift = create_shift("Test New Default Shift", "09:10:00", "18:30:00")
		attendance_name = mark_attendance(self.employee.name, self.date, "Absent", shift=old_shift.name)
		frappe.db.set_value("Employee", self.employee.name, "default_shift", new_shift.name)
		self.addCleanup(frappe.db.set_value, "Employee", self.employee.name, "default_shift", None)

		request = create_attendance_request(
			employee=self.employee.name, from_date=self.date, to_date=self.date
		)

		self.assertEqual(request.shift, new_shift.name)
		attendance = frappe.db.get_value(
			"Attendance", attendance_name, ["status", "shift", "attendance_request"], as_dict=True
		)
		self.assertEqual(
			(attendance.status, attendance.shift, attendance.attendance_request),
			("Present", old_shift.name, request.name),
		)
		self.assertEqual(
			frappe.db.count("Attendance", {"employee": self.employee.name, "attendance_date": self.date}), 1
		)

	def test_missed_punch_request(self):
		# Athen's rule (user 2026-11-10): one date on which the employee did punch, a choice among
		# the punches missing that day, and the day becomes what that punch would have made it
		from hrms.hr.doctype.attendance_request.attendance_request import get_missed_punch_details
		from hrms.hr.doctype.employee_checkin.test_employee_checkin import make_checkin
		from hrms.hr.doctype.shift_type.test_shift_type import make_shift_assignment, setup_shift_type

		frappe.db.delete("Holiday", {"parent": self.holiday_list})
		shift = setup_shift_type(
			shift_type="Missed Punch Test",
			start_time="09:00:00",
			end_time="18:30:00",
			determine_check_in_and_check_out="Strictly based on Log Type in Employee Checkin",
			attendance_rule="Punch Windows",
			morning_check_in_until="09:10:59",
			half_day_window_start="13:00:00",
			half_day_window_end="14:00:00",
			status_for_other_punches="Absent",
		)
		date = self.date

		def punch(time, log_type):
			return make_checkin(employee, datetime.combine(date, get_time(time)), log_type=log_type)

		def options(employee):
			details = get_missed_punch_details(employee, date)
			return details.eligible, details.message, [(o["value"], o["status"]) for o in details.options]

		# afternoon check-in and check-out at the shift end: only the morning punch is missing
		employee = make_employee("test_missed_punch_half@example.com", company="_Test Company")
		make_shift_assignment(shift.name, employee, date)
		punch("13:19:00", "IN")
		punch("18:32:00", "OUT")
		attendance = mark_attendance(employee, date, "Half Day", shift=shift.name)
		self.assertEqual(options(employee), (True, "", [("Morning punch", "Present")]))

		# only the evening punch: the morning punch makes the day Present, a lunch-time one a half day
		other = make_employee("test_missed_punch_evening@example.com", company="_Test Company")
		make_shift_assignment(shift.name, other, date)
		make_checkin(other, datetime.combine(date, get_time("18:32:00")), log_type="OUT")
		mark_attendance(other, date, "Absent", shift=shift.name)
		self.assertEqual(
			options(other), (True, "", [("Morning punch", "Present"), ("Lunch-time punch", "Half Day")])
		)

		# no punch at all is not a missed punch
		nobody = make_employee("test_missed_punch_none@example.com", company="_Test Company")
		make_shift_assignment(shift.name, nobody, date)
		eligible, message, _options = options(nobody)
		self.assertFalse(eligible)
		self.assertIn("No punch on", message)

		# the request: one day only, no half day, and only a punch that is missing
		request = frappe.get_doc(
			{
				"doctype": "Attendance Request",
				"employee": employee,
				"from_date": date,
				"to_date": add_days(date, 1),
				"half_day": 1,
				"half_day_date": date,
				"reason": "Missed Punch",
				"missed_punch": "Lunch-time punch",
				"company": "_Test Company",
			}
		)
		self.assertRaises(frappe.ValidationError, request.insert)
		request.missed_punch = "Morning punch"
		request.insert()
		self.assertEqual((request.to_date, request.half_day, request.shift), (date, 0, shift.name))

		request.submit()
		attendance = frappe.db.get_value(
			"Attendance", attendance, ["status", "shift", "attendance_request"], as_dict=True
		)
		self.assertEqual(
			(attendance.status, attendance.shift, attendance.attendance_request),
			("Present", shift.name, request.name),
		)
		self.assertFalse(get_missed_punch_details(employee, date).eligible)

	@HRMSTestSuite.change_settings("HR Settings", {"allow_multiple_shift_assignments": True})
	def test_overlap_with_different_shifts(self):
		shift_1 = create_shift("Morning Shift", "08:00:00", "12:00:00")
		shift_2 = create_shift("Evening Shift", "14:00:00", "18:00:00")

		create_shift_assignment(
			self.employee.name, shift_1.name, add_days(self.date, -1), add_days(self.date, 1)
		)
		create_shift_assignment(
			self.employee.name, shift_2.name, add_days(self.date, -1), add_days(self.date, 1)
		)

		today = self.date

		frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee.name,
				"attendance_date": today,
				"status": "Absent",
				"shift": shift_1.name,
				"company": "_Test Company",
			}
		).insert()

		frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee.name,
				"attendance_date": today,
				"status": "Absent",
				"shift": shift_2.name,
				"company": "_Test Company",
			}
		).insert()

		create_attendance_request(
			employee=self.employee.name,
			reason="On Duty",
			company="_Test Company",
			from_date=today,
			to_date=today,
			shift=shift_1.name,
		)

		# same dates with a different shift should NOT overlap
		self.assertTrue(
			create_attendance_request(
				employee=self.employee.name,
				reason="On Duty",
				company="_Test Company",
				from_date=today,
				to_date=today,
				shift=shift_2.name,
			)
		)

		attendances = frappe.db.get_all(
			"Attendance",
			{"employee": self.employee.name, "attendance_date": today, "status": "Present"},
			pluck="name",
		)

		self.assertEqual(len(attendances), 2)


def get_employee():
	return frappe.get_doc("Employee", "_T-Employee-00001")


def create_attendance_request(**args: dict) -> dict:
	args = frappe._dict(args)
	today = getdate()

	attendance_request = frappe.get_doc(
		{
			"doctype": "Attendance Request",
			"employee": args.employee or get_employee().name,
			"from_date": add_days(today, -1),
			"to_date": today,
			"reason": "On Duty",
			"company": "_Test Company",
			"shift": args.shift or None,
		}
	)

	if args:
		attendance_request.update(args)

	return attendance_request.submit()


def create_shift(name, start_time, end_time):
	if frappe.db.exists("Shift Type", name):
		return frappe.get_doc("Shift Type", name)
	return frappe.get_doc(
		{"doctype": "Shift Type", "__newname": name, "start_time": start_time, "end_time": end_time}
	).insert()


def create_shift_assignment(employee, shift_type, start_date, end_date):
	return frappe.get_doc(
		{
			"doctype": "Shift Assignment",
			"employee": employee,
			"shift_type": shift_type,
			"start_date": start_date,
			"end_date": end_date,
			"company": "_Test Company",
		}
	).submit()
