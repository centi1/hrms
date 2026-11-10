// Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
frappe.ui.form.on("Attendance Request", {
	refresh(frm) {
		frm.trigger("show_attendance_warnings");
		frm.trigger("set_missed_punch_options");
	},

	show_attendance_warnings(frm) {
		if (!frm.is_new() && frm.doc.docstatus === 0) {
			frm.dashboard.clear_headline();

			const shift_warning = frm.doc.__onload?.shift_warning;
			if (shift_warning) {
				frm.dashboard.set_headline(shift_warning.message, shift_warning.indicator);
			}

			frm.call("get_attendance_warnings").then((r) => {
				if (r.message?.length) {
					frm.dashboard.reset();
					frm.dashboard.add_section(
						frappe.render_template("attendance_warnings", {
							warnings: r.message || [],
						}),
						__("Attendance Warnings"),
					);
					frm.dashboard.show();
				}
			});
		}
	},

	employee(frm) {
		if (frm.doc.employee && frm.doc.from_date && !frm.doc.shift) {
			frm.trigger("set_employee_shift");
		}
		frm.trigger("set_missed_punch_options");
	},

	from_date(frm) {
		if (frm.doc.employee && frm.doc.from_date && !frm.doc.shift) {
			frm.trigger("set_employee_shift");
		}
		frm.trigger("set_missed_punch_options");
	},

	reason(frm) {
		frm.trigger("set_missed_punch_options");
	},

	// Missed Punch: one date, and only the punches missing on it are offered, with what the day becomes
	set_missed_punch_options(frm) {
		if (frm.doc.reason !== "Missed Punch" || frm.doc.docstatus !== 0) return;
		if (frm.doc.to_date !== frm.doc.from_date) frm.set_value("to_date", frm.doc.from_date);
		if (!frm.doc.employee || !frm.doc.from_date) return;

		frappe.call({
			method: "hrms.hr.doctype.attendance_request.attendance_request.get_missed_punch_options",
			args: { employee: frm.doc.employee, date: frm.doc.from_date, shift: frm.doc.shift },
			callback(r) {
				const details = r.message || {};
				const options = [{ label: "", value: "" }].concat(
					(details.options || []).map((o) => ({ label: o.label, value: o.value })),
				);
				frm.set_df_property("missed_punch", "options", options);
				if (frm.doc.missed_punch && !options.some((o) => o.value === frm.doc.missed_punch)) {
					frm.set_value("missed_punch", "");
				}
				const punches = details.punches
					? __("Punches on {0}: {1}", [frappe.datetime.str_to_user(frm.doc.from_date), details.punches])
					: "";
				if (details.eligible) {
					frm.set_df_property("missed_punch", "description", punches);
					frm.dashboard.clear_headline();
				} else {
					frm.set_df_property("missed_punch", "description", "");
					frm.dashboard.set_headline(
						[details.message, punches].filter(Boolean).join(" "),
						"orange",
					);
				}
			},
		});
	},

	set_employee_shift(frm) {
		if (!frm.doc.employee || !frm.doc.from_date) return;

		frappe.call({
			method: "hrms.hr.doctype.attendance.attendance.get_employee_shift",
			args: {
				employee: frm.doc.employee,
				for_date: frm.doc.from_date,
				consider_default_shift: true,
			},
			callback(r) {
				if (r.message && !frm.doc.shift) {
					frm.set_value("shift", r.message);
				}
			},
		});
	},
});
