// Attendance calendar on the Employee form, in place of the dashboard heatmap: one block of week
// columns per month (so a month starting mid-week starts a new column), each day coloured by its
// attendance status as in the Monthly Attendance Sheet, and each month headed by present /
// working days. Clicking a day shows its first and last punch under the calendar (one time when
// there was a single punch). Desk draws its own heatmap on a canvas with a value scale, which
// cannot show statuses.
frappe.provide("hrms");

hrms.ATTENDANCE_CALENDAR_STATUSES = {
	P: { label: __("Present"), colour: "#51cf66" },
	HD: { label: __("Half Day"), colour: "#fcc419" },
	SP: { label: __("Single Punch"), colour: "#ffa8a8" },
	"✓": { label: __("Approved via Request"), colour: "#4dabf7" },
	A: { label: __("Absent"), colour: "#adb5bd" },
	H: { label: __("Holiday / Weekly Off"), colour: "#e9ecef" },
};

frappe.ui.form.on("Employee", {
	refresh(frm) {
		if (frm.is_new() || !frm.dashboard?.data?.heatmap) return;
		hrms.render_attendance_calendar(frm);
	},
});

hrms.render_attendance_calendar = function (frm) {
	const area = frm.dashboard.heatmap_area;
	if (!area) return;

	frappe
		.xcall("hrms.overrides.employee_master.get_attendance_heatmap", { employee: frm.doc.name })
		.then((data) => {
			area.body.find(".heatmap").hide();
			area.body.find(".attendance-calendar").remove();
			area.body.prepend(hrms.attendance_calendar_html(data));
			area.body.find(".attendance-calendar").on("click", "[data-day]", function () {
				const calendar = $(this).closest(".attendance-calendar");
				calendar.find("[data-day]").css("outline", "");
				$(this).css("outline", "2px solid var(--text-color)");
				calendar.find(".attendance-day-details").html(hrms.attendance_day_details_html(data, $(this).data("day")));
			});
			area.show();
		});
};

hrms.attendance_calendar_html = function (data) {
	const statuses = hrms.ATTENDANCE_CALENDAR_STATUSES;
	const cell = (colour, title = "", day = "") =>
		`<div title="${title}"${
			day ? ` data-day="${day}"` : ""
		} style="width:11px;height:11px;border-radius:2px;background:${colour}${
			day ? ";cursor:pointer" : ""
		}"></div>`;
	const blank = '<div style="width:11px;height:11px"></div>';

	// start at the first month with any attendance, not a year of empty months
	const first_day = Object.keys(data.days).sort()[0] || data.start;
	const months = [];
	const end = moment(data.end);
	for (let month = moment(first_day).startOf("month"); month <= end; month.add(1, "month")) {
		months.push(month.clone());
	}

	const blocks = months.map((month) => {
		// weeks start on Monday: the 1st sits in its weekday's row of the month's first column
		const first_row = (month.day() + 6) % 7;
		const days_in_month = month.daysInMonth();
		const columns = Math.ceil((first_row + days_in_month) / 7);
		let html = "";
		for (let column = 0; column < columns; column++) {
			html += '<div style="display:flex;flex-direction:column;gap:2px">';
			for (let row = 0; row < 7; row++) {
				const day_number = column * 7 + row - first_row + 1;
				if (day_number < 1 || day_number > days_in_month) {
					html += blank;
					continue;
				}
				const day = month.clone().date(day_number);
				if (day.isAfter(end, "day")) {
					html += blank;
					continue;
				}
				const key = day.format("YYYY-MM-DD");
				const status = statuses[data.days[key]];
				const punches = hrms.attendance_day_punches_text(data, key);
				const title = `${day.format("DD MMM YYYY, ddd")} · ${status ? status.label : __("No attendance")}${
					punches ? ` · ${punches}` : ""
				}`;
				html += cell(status ? status.colour : "#f8f9fa", frappe.utils.escape_html(title), key);
			}
			html += "</div>";
		}
		const summary = data.months[month.format("YYYY-MM")];
		return `
			<div style="display:flex;flex-direction:column;gap:4px">
				<div class="text-muted" style="font-size:11px;white-space:nowrap;min-height:16px">
					${month.format("MMM")}${
						summary
							? ` <span style="font-weight:600;color:var(--text-color)" title="${__(
									"Present days / working days"
							  )}">${summary}</span>`
							: ""
					}
				</div>
				<div style="display:flex;gap:2px">${html}</div>
			</div>`;
	});

	const weekdays = ["Mon", "", "Wed", "", "Fri", "", "Sun"]
		.map((day) => `<div style="height:11px;line-height:11px">${day ? __(day) : ""}</div>`)
		.join("");
	const legend = Object.values(statuses)
		.map(
			(status) =>
				`<span style="display:inline-flex;align-items:center;gap:4px;margin-right:12px">${cell(
					status.colour
				)}${status.label}</span>`
		)
		.join("");

	return `
		<div class="attendance-calendar" style="padding:8px 0">
			<div style="display:flex;gap:10px;overflow-x:auto;padding-bottom:4px">
				<div class="text-muted" style="display:flex;flex-direction:column;gap:2px;margin-top:20px;font-size:10px">
					${weekdays}
				</div>
				${blocks.join("")}
			</div>
			<div class="attendance-day-details" style="font-size:12px;margin-top:8px;min-height:18px">
				<span class="text-muted">${__("Click a day to see its punches")}</span>
			</div>
			<div class="text-muted" style="font-size:11px;margin-top:10px">${legend}</div>
		</div>`;
};

// "9:02 AM" from the server's "09:02:41"
hrms.attendance_punch_time = (time) => moment(time, "HH:mm:ss").format("h:mm A");

// a day's punches in one line of plain text, for the hover title: "First punch 9:02 AM, last punch 6:34 PM"
hrms.attendance_day_punches_text = function (data, day) {
	const punches = (data.punches || {})[day];
	if (!punches) return "";
	const first = hrms.attendance_punch_time(punches.first);
	if (!punches.last) return __("Single punch {0}", [first]);
	return __("First punch {0}, last punch {1}", [first, hrms.attendance_punch_time(punches.last)]);
};

// the line under the calendar for the clicked day: date, status, first and last punch. A punch that
// fell outside the shift's punch windows is marked "not counted".
hrms.attendance_day_details_html = function (data, day) {
	const status = hrms.ATTENDANCE_CALENDAR_STATUSES[data.days[day]];
	const punches = (data.punches || {})[day];
	const not_counted = (counted) =>
		counted === false ? ` <span style="color:var(--red-500)">(${__("not counted")})</span>` : "";
	const punch = (label, time, counted) =>
		`<span style="margin-left:14px"><span class="text-muted">${label}</span> <b>${hrms.attendance_punch_time(
			time
		)}</b>${not_counted(counted)}</span>`;

	let html = `<b>${moment(day).format("ddd, DD MMM YYYY")}</b>
		<span style="margin-left:10px">${status ? status.label : __("No attendance")}</span>`;
	if (!punches) {
		html += `<span class="text-muted" style="margin-left:14px">${__("No punches")}</span>`;
	} else if (!punches.last) {
		html += punch(__("Single punch"), punches.first, punches.first_counted);
		if (punches.count > 1) {
			html += `<span class="text-muted" style="margin-left:14px">${__("punched {0} times within the hour", [
				punches.count,
			])}</span>`;
		}
	} else {
		html += punch(__("First punch"), punches.first, punches.first_counted);
		html += punch(__("Last punch"), punches.last, punches.last_counted);
		if (punches.count > 2) {
			html += `<span class="text-muted" style="margin-left:14px">${__("{0} punches in all", [punches.count])}</span>`;
		}
	}
	return html;
};
