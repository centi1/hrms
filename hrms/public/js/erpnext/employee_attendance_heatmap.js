// Colour the attendance heatmap on the Employee form by attendance status (same codes as the
// Monthly Attendance Sheet) and show present / working days next to each month name.
frappe.provide("hrms");

hrms.ATTENDANCE_HEATMAP_COLOURS = {
	P: "#51cf66", // present
	HD: "#fcc419", // half day
	SP: "#ffa8a8", // single punch
	"✓": "#4dabf7", // approved via attendance request
};

frappe.ui.form.on("Employee", {
	refresh(frm) {
		if (frm.is_new() || !frm.dashboard?.data?.heatmap) return;
		hrms.colour_attendance_heatmap(frm);
	},
});

hrms.colour_attendance_heatmap = function (frm) {
	const dashboard = frm.dashboard;
	if (!dashboard.__attendance_colours) {
		// re-apply whenever the dashboard (re)loads the heatmap data
		const update_heatmap = dashboard.update_heatmap.bind(dashboard);
		dashboard.update_heatmap = (data) => {
			update_heatmap(data);
			hrms.apply_attendance_heatmap_colours(dashboard);
		};
		dashboard.__attendance_colours = true;
	}

	frappe
		.xcall("hrms.overrides.employee_master.get_attendance_heatmap", { employee: frm.doc.name })
		.then((data) => {
			dashboard.__attendance_heatmap = data;
			hrms.apply_attendance_heatmap_colours(dashboard);
		});
};

hrms.apply_attendance_heatmap_colours = function (dashboard) {
	const data = dashboard.__attendance_heatmap;
	const svg = dashboard.heatmap_area?.body.find("svg");
	if (!data || !svg?.length) return;

	svg.find("rect.day").each(function () {
		const colour = hrms.ATTENDANCE_HEATMAP_COLOURS[data.days[this.getAttribute("data-date")]];
		if (colour) this.setAttribute("fill", colour);
	});

	// month labels are drawn in order from the heatmap's start date (one year ago)
	const months = [];
	for (let m = moment().subtract(1, "year").startOf("month"); m <= moment(); m.add(1, "month")) {
		months.push(m.clone());
	}
	let index = 0;
	svg.find("text.domain-name").each(function () {
		const label = (this.getAttribute("data-month") || this.textContent).trim().slice(0, 3).toUpperCase();
		while (index < months.length && months[index].format("MMM").toUpperCase() !== label) index++;
		if (index >= months.length) return;

		const summary = data.months[months[index].format("YYYY-MM")];
		this.setAttribute("data-month", label);
		this.textContent = summary ? `${label} ${summary}` : label;
		if (summary) this.setAttribute("font-size", "8");
		index++;
	});
};
