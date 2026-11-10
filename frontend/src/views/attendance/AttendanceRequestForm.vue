<template>
	<ion-page>
		<ion-content :fullscreen="true">
			<FormView
				v-if="formFields.data"
				doctype="Attendance Request"
				v-model="attendanceRequest"
				:isSubmittable="true"
				:fields="formFields.data"
				:id="props.id"
				@validateForm="validateForm"
				@formReloaded="onFormReloaded"
			/>
		</ion-content>
	</ion-page>
</template>

<script setup>
import { IonPage, IonContent } from "@ionic/vue"
import { createResource } from "frappe-ui"
import { ref, watch, inject } from "vue"

import FormView from "@/components/FormView.vue"

const employee = inject("$employee")
const __ = inject("$translate")

const props = defineProps({
	id: {
		type: String,
		required: false,
	},
})

// reactive object to store form data
const attendanceRequest = ref({})

// get form fields
const formFields = createResource({
	url: "hrms.api.get_doctype_fields",
	params: { doctype: "Attendance Request" },
	auto: true,
	transform(data) {
		// the missed punch choice is filled per date from the server, with the resulting status as
		// description, so it is rendered as a list (Link + documentList) instead of a plain select
		const missed_punch = data.find((field) => field.fieldname === "missed_punch")
		if (missed_punch) {
			missed_punch.fieldtype = "Link"
			missed_punch.options = ""
			missed_punch.documentList = []
		}
		if (props.id) return data
		return data.filter(
			(field) => !["employee", "employee_name", "status", "company"].includes(field.fieldname)
		)
	},
	onSuccess() {
		applyMissedPunchLayout()
	},
})

// form scripts
watch(
	() => attendanceRequest.value.employee,
	(employee_id) => {
		if (props.id && employee_id !== employee.data.name) {
			// if employee is not the current user, set form as read only
			setFormReadOnly()
		}
	}
)

// the to date this form filled in, as opposed to one the user picked or the saved doc has
let autoFilledToDate = null

watch(
	() => attendanceRequest.value.from_date,
	(from_date) => {
		// a date input emits partial years while typing (0002, 0020, ...), so keep an
		// auto filled to date in step with from date until the user sets it themselves
		const to_date = attendanceRequest.value.to_date
		if (!to_date || to_date === autoFilledToDate) {
			attendanceRequest.value.to_date = autoFilledToDate = from_date
		}
	}
)

watch(
	() => [attendanceRequest.value.from_date, attendanceRequest.value.to_date],
	([from_date, to_date]) => {
		validateDates(from_date, to_date)
	}
)

watch(
	() => attendanceRequest.value.half_day,
	(half_day) => {
		const half_day_date = formFields.data.find((field) => field.fieldname === "half_day_date")
		half_day_date.hidden = !half_day || isMissedPunch()
	}
)

watch(
	() => [attendanceRequest.value.reason, attendanceRequest.value.from_date],
	() => {
		applyMissedPunchLayout()
		setMissedPunchOptions()
	}
)

// helper functions
function isMissedPunch() {
	return attendanceRequest.value.reason === "Missed Punch"
}

function getField(fieldname) {
	return formFields.data?.find((field) => field.fieldname === fieldname)
}

// Missed Punch: one date (no to date, no half day), and a choice among the punches missing that day
function applyMissedPunchLayout() {
	if (!formFields.data) return
	const missed = isMissedPunch()
	const to_date = getField("to_date")
	const half_day = getField("half_day")
	const half_day_date = getField("half_day_date")
	const missed_punch = getField("missed_punch")
	if (to_date) to_date.hidden = missed
	if (half_day) half_day.hidden = missed
	if (half_day_date) half_day_date.hidden = missed || !attendanceRequest.value.half_day
	if (missed_punch) {
		missed_punch.hidden = !missed
		missed_punch.reqd = missed
	}
	if (missed) {
		attendanceRequest.value.to_date = attendanceRequest.value.from_date
		attendanceRequest.value.half_day = 0
		attendanceRequest.value.half_day_date = null
	}
}

function setMissedPunchOptions() {
	const missed_punch = getField("missed_punch")
	const from_date = getField("from_date")
	if (!missed_punch || !from_date) return
	if (!isMissedPunch() || !attendanceRequest.value.from_date) {
		from_date.error_message = ""
		return
	}
	if (props.id) {
		// a saved request keeps showing its own choice; the day may be regularised already
		const value = attendanceRequest.value.missed_punch
		missed_punch.documentList = value ? [{ label: __(value), value }] : []
		return
	}
	createResource({
		url: "hrms.hr.doctype.attendance_request.attendance_request.get_missed_punch_options",
		params: {
			employee: employee.data.name,
			date: attendanceRequest.value.from_date,
			shift: attendanceRequest.value.shift,
		},
		onSuccess(details) {
			missed_punch.documentList = (details.options || []).map((option) => ({
				label: __(option.value),
				value: option.value,
				description: __("day becomes {0}", [__(option.status)]),
			}))
			if (
				attendanceRequest.value.missed_punch &&
				!details.options?.some((option) => option.value === attendanceRequest.value.missed_punch)
			) {
				attendanceRequest.value.missed_punch = null
			}
			const punches = details.punches ? __("Punches: {0}.", [details.punches]) : ""
			from_date.error_message = details.eligible ? "" : [details.message, punches].join(" ")
		},
	}).reload()
}

function setFormReadOnly() {
	formFields.data.map((field) => (field.read_only = true))
}

function validateDates(from_date, to_date) {
	if (!(from_date && to_date)) return

	const error_message = from_date > to_date ? __("To Date cannot be before From Date") : ""

	const from_date_field = formFields.data.find((field) => field.fieldname === "from_date")
	from_date_field.error_message = error_message
}

function onFormReloaded() {
	// the reloaded to date is the saved one, so a later from date change leaves it alone
	autoFilledToDate = null
}

function validateForm() {
	attendanceRequest.value.employee = employee.data.name
}
</script>
