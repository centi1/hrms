<template>
	<div class="flex flex-col w-full gap-5" v-if="calendarEvents.data">
		<div class="text-lg text-gray-800 font-bold">{{ __("Attendance Calendar") }}</div>

		<div class="flex flex-col gap-6 bg-white py-6 px-3.5 rounded-lg border-none">
			<!-- Month Change -->
			<div class="flex flex-row justify-between items-center px-4">
				<Button
					icon="chevron-left"
					variant="ghost"
					@click="firstOfMonth = firstOfMonth.subtract(1, 'M')"
				/>
				<span class="text-lg text-gray-800 font-bold">
					{{ firstOfMonth.format("MMMM") }} {{ firstOfMonth.format("YYYY") }}
					<span class="text-gray-600 font-semibold" :title="__('Present days / working days')">
						({{ presentDays }}/{{ workingDays }})
					</span>
				</span>
				<Button
					icon="chevron-right"
					variant="ghost"
					@click="firstOfMonth = firstOfMonth.add(1, 'M')"
				/>
			</div>

			<!-- Calendar -->
			<div class="grid grid-cols-7 gap-y-3">
				<div
					v-for="day in DAYS"
					class="flex justify-center text-gray-600 text-sm font-medium leading-6"
				>
					{{ day }}
				</div>
				<!-- end of the previous month, so the 1st falls under its weekday -->
				<div v-for="date in leadingDates" :key="date.format('YYYY-MM-DD')">
					<div class="h-8 w-8 flex rounded-full mx-auto">
						<span class="text-gray-300 text-sm font-medium m-auto">{{ date.date() }}</span>
					</div>
				</div>
				<div v-for="index in firstOfMonth.endOf('M').get('D')">
					<div
						class="h-8 w-8 flex rounded-full mx-auto"
						:class="getEventOnDate(index) && colorMap[getEventOnDate(index)]"
					>
						<span class="text-gray-800 text-sm font-medium m-auto">
							{{ index }}
						</span>
					</div>
				</div>
				<!-- start of the next month, completing the last week -->
				<div v-for="date in trailingDates" :key="date.format('YYYY-MM-DD')">
					<div class="h-8 w-8 flex rounded-full mx-auto">
						<span class="text-gray-300 text-sm font-medium m-auto">{{ date.date() }}</span>
					</div>
				</div>
			</div>

			<hr />

			<!-- Summary -->
			<div class="grid grid-cols-4 mx-2">
				<div v-for="status in summaryStatuses" class="flex flex-col gap-1">
					<div class="flex flex-row gap-1 items-center">
						<span class="rounded full h-3 w-3" :class="colorMap[status]" />
						<span class="text-gray-600 text-sm font-medium leading-5"> {{ __(status) }} </span>
					</div>
					<span class="text-gray-800 text-base font-semibold leading-6 mx-auto">
						{{ summary[status] || 0 }}
					</span>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, inject, ref, watch } from "vue"
import { createResource } from "frappe-ui"

const dayjs = inject("$dayjs")
const __ = inject("$translate")
const firstOfMonth = ref(dayjs().date(1).startOf("D"))

const colorMap = {
	Present: "bg-green-300",
	"Work From Home": "bg-green-300",
	"Half Day": "bg-yellow-200",
	Absent: "bg-red-200",
	"On Leave": "bg-blue-300",
	Holiday: "bg-gray-300",
}

// __("Present"), __("Half Day"), __("Absent"), __("On Leave"), __("Work From Home")
const summaryStatuses = ["Present", "Half Day", "Absent", "On Leave"]

const summary = computed(() => {
	const summary = {}

	for (const status of Object.values(calendarEvents.data)) {
		let updatedStatus = status === "Work From Home" ? "Present" : status
		if (updatedStatus in summary) {
			summary[updatedStatus] += 1
		} else {
			summary[updatedStatus] = 1
		}
	}

	return summary
})

// weeks start on Monday
const leadingDates = computed(() => {
	const count = (firstOfMonth.value.day() + 6) % 7
	return Array.from({ length: count }, (_, i) => firstOfMonth.value.subtract(count - i, "day"))
})

const trailingDates = computed(() => {
	const daysInMonth = firstOfMonth.value.daysInMonth()
	const count = (7 - ((leadingDates.value.length + daysInMonth) % 7)) % 7
	const nextMonth = firstOfMonth.value.add(1, "M")
	return Array.from({ length: count }, (_, i) => nextMonth.add(i, "day"))
})

// working days exclude holidays and weekly offs; a half day counts as half a present day
const workingDays = computed(() => {
	const holidays = Object.values(calendarEvents.data || {}).filter((status) => status === "Holiday").length
	return firstOfMonth.value.daysInMonth() - holidays
})

const presentDays = computed(() => {
	const value = { Present: 1, "Work From Home": 1, "Half Day": 0.5 }
	return Object.values(calendarEvents.data || {}).reduce((total, status) => total + (value[status] || 0), 0)
})

watch(
	() => firstOfMonth.value,
	() => {
		calendarEvents.fetch()
	}
)

const getEventOnDate = (date) => {
	return calendarEvents.data[firstOfMonth.value.date(date).format("YYYY-MM-DD")]
}

const getFirstLetter = (s) => Array.from(s.trim())[0] // Unicode

const DAYS = [
	getFirstLetter(__("Monday")),
	getFirstLetter(__("Tuesday")),
	getFirstLetter(__("Wednesday")),
	getFirstLetter(__("Thursday")),
	getFirstLetter(__("Friday")),
	getFirstLetter(__("Saturday")),
	getFirstLetter(__("Sunday")),
]

//resources
const calendarEvents = createResource({
	url: "hrms.api.get_attendance_calendar_events",
	auto: true,
	cache: "hrms:attendance_calendar_events",
	makeParams() {
		return {
			from_date: firstOfMonth.value.format("YYYY-MM-DD"),
			to_date: firstOfMonth.value.endOf("M").format("YYYY-MM-DD"),
		}
	},
})
</script>
