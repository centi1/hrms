<template>
	<div class="flex flex-col bg-white rounded w-full py-6 px-4 border-none">
		<h2 class="text-lg font-bold text-gray-900">
			{{ __("Hey, {0} 👋", [employee?.data?.first_name]) }}
		</h2>

		<template v-if="settings.data?.allow_employee_checkin_from_mobile_app">
			<div class="font-medium text-sm text-gray-500 mt-1.5" v-if="lastLog?.time">
				<span>{{ __("Last {0} was at {1}", [__(lastLogType), formatTimestamp(lastLog.time)]) }}</span>
				<span class="whitespace-pre"> &middot; </span>
				<router-link :to="{ name: 'EmployeeCheckinListView' }" v-slot="{ navigate }">
					<span @click="navigate" class="underline">{{ __("View List") }}</span>
				</router-link>
			</div>
			<Button
				class="mt-4 mb-1 drop-shadow-sm py-5 text-base"
				id="open-checkin-modal"
				:loading="checkins.list.loading"
				@click="handleEmployeeCheckin"
			>
				<template #prefix>
					<FeatherIcon
						:name="nextAction.action === 'IN' ? 'arrow-right-circle' : 'arrow-left-circle'"
						class="w-4"
					/>
				</template>
				{{ nextAction.label }}
			</Button>
		</template>

		<div v-else class="font-medium text-sm text-gray-500 mt-1.5">
			{{ dayjs().format("ddd, D MMMM, YYYY") }}
		</div>
	</div>

	<ion-modal
		v-if="settings.data?.allow_employee_checkin_from_mobile_app"
		ref="modal"
		trigger="open-checkin-modal"
		:initial-breakpoint="1"
		:breakpoints="[0, 1]"
		@didPresent="onModalPresent"
		@didDismiss="onModalDismiss"
	>
		<div
			class="w-full flex flex-col items-center justify-center gap-5 p-4 mb-5"
			:class="photoRequired ? 'h-full overflow-y-auto' : 'h-120'"
		>
			<div class="flex flex-col gap-1.5 mt-2 items-center justify-center">
				<template v-if="checkinTimestamp">
					<div class="font-bold text-xl">
						{{ dayjs(checkinTimestamp).format("hh:mm:ss a") }}
					</div>
					<div class="font-medium text-gray-500 text-sm">
						{{ dayjs(checkinTimestamp).format("D MMM, YYYY") }}
					</div>
				</template>
				<div v-else class="font-medium text-gray-500 text-sm">{{ __("Fetching time...") }}</div>
			</div>

			<template v-if="settings.data?.allow_geolocation_tracking">
				<span v-if="locationStatus" class="font-medium text-gray-500 text-sm">
					{{ locationStatus }}
				</span>

				<div class="rounded border-4 translate-z-0 block overflow-hidden w-full h-170">
					<iframe
						width="100%"
						height="170"
						frameborder="0"
						scrolling="no"
						marginheight="0"
						marginwidth="0"
						style="border: 0"
						:src="`https://maps.google.com/maps?q=${latitude},${longitude}&hl=en&z=15&amp;output=embed`"
					>
					</iframe>
				</div>
			</template>

			<template v-if="photoRequired">
				<div
					class="relative rounded border-4 overflow-hidden w-full h-64 bg-gray-900 flex items-center justify-center"
				>
					<img v-if="photo" :src="photo" class="h-full w-full object-cover" />
					<video
						v-else
						ref="video"
						autoplay
						playsinline
						muted
						class="h-full w-full object-cover -scale-x-100"
					></video>
					<span v-if="cameraStatus" class="absolute px-4 text-center text-sm text-white">
						{{ cameraStatus }}
					</span>
				</div>
				<Button v-if="photo" class="w-full py-5 text-sm" @click="startCamera">
					<template #prefix><FeatherIcon name="refresh-cw" class="w-4" /></template>
					{{ __("Retake Photo") }}
				</Button>
				<Button v-else class="w-full py-5 text-sm" :disabled="!cameraReady" @click="capturePhoto">
					<template #prefix><FeatherIcon name="camera" class="w-4" /></template>
					{{ __("Take Photo") }}
				</Button>
			</template>

			<Button
				:loading="checkinRequest.loading"
				:disabled="!canSubmit"
				variant="solid"
				class="w-full py-5 text-sm disabled:bg-gray-700"
				@click="submitLog(nextAction.action)"
			>
				{{ __("Confirm {0}", [nextAction.label]) }}
			</Button>
		</div>
	</ion-modal>
</template>

<script setup>
import { createListResource, createResource, toast, FeatherIcon } from "frappe-ui"
import { computed, inject, nextTick, ref, onMounted, onBeforeUnmount } from "vue"
import { IonModal, modalController } from "@ionic/vue"

import { formatTimestamp } from "@/utils/formatters"
import { settings } from "@/data/settings"

const DOCTYPE = "Employee Checkin"
const PHOTO_MAX_WIDTH = 640

const socket = inject("$socket")
const employee = inject("$employee")
const dayjs = inject("$dayjs")
const __ = inject("$translate")
const checkinTimestamp = ref(null)
const latitude = ref(0)
const longitude = ref(0)
const locationStatus = ref("")

const video = ref(null)
const photo = ref(null)
const cameraReady = ref(false)
const cameraStatus = ref("")
let cameraStream = null

const photoRequired = computed(() => Boolean(settings.data?.require_photo_for_mobile_checkin))

const canSubmit = computed(() => {
	if (photoRequired.value && !photo.value) return false
	if (settings.data?.allow_geolocation_tracking && !(latitude.value && longitude.value)) return false
	return true
})

const checkinRequest = createResource({ url: "hrms.api.create_employee_checkin" })
// the checkin is recorded at server time, so show that rather than the phone's clock
const serverTime = createResource({
	url: "hrms.api.get_server_time",
	onSuccess(data) {
		checkinTimestamp.value = data
	},
})

const checkins = createListResource({
	doctype: DOCTYPE,
	fields: ["name", "employee", "employee_name", "log_type", "time", "device_id"],
	filters: {
		employee: employee.data.name,
	},
	orderBy: "time desc",
})
checkins.reload()

const lastLog = computed(() => {
	if (!checkins.data?.length) return null
	return checkins.data[0]
})

const lastLogType = computed(() => {
	return lastLog?.value?.log_type === "IN" ? "check-in" : "check-out"
})

const nextAction = computed(() => {
	return lastLog?.value?.log_type === "IN"
		? { action: "OUT", label: __("Check Out") }
		: { action: "IN", label: __("Check In") }
})

function handleLocationSuccess(position) {
	latitude.value = position.coords.latitude
	longitude.value = position.coords.longitude

	locationStatus.value = [
		__("Latitude: {0}°", [Number(latitude.value).toFixed(5)]),
		__("Longitude: {0}°", [Number(longitude.value).toFixed(5)]),
	].join(", ")
}

function handleLocationError(error) {
	locationStatus.value = __("Unable to retrieve your location")
	if (error) locationStatus.value += `: ERROR(${error.code}): ${error.message}`
}

const fetchLocation = () => {
	if (!navigator.geolocation) {
		locationStatus.value = __("Geolocation is not supported by your current browser")
	} else {
		locationStatus.value = __("Locating...")
		navigator.geolocation.getCurrentPosition(handleLocationSuccess, handleLocationError)
	}
}

// live front camera only: the photo is taken now, never picked from the gallery
const startCamera = async () => {
	stopCamera()
	photo.value = null
	await nextTick()

	if (!navigator.mediaDevices?.getUserMedia) {
		cameraStatus.value = __("Camera is not available in this browser")
		return
	}

	cameraStatus.value = __("Starting camera...")
	try {
		cameraStream = await navigator.mediaDevices.getUserMedia({
			video: { facingMode: "user", width: { ideal: 1280 } },
			audio: false,
		})
		video.value.srcObject = cameraStream
		await video.value.play()
		cameraReady.value = true
		cameraStatus.value = ""
	} catch (error) {
		cameraStatus.value = __("Unable to access the camera: {0}", [error.message])
	}
}

const stopCamera = () => {
	cameraStream?.getTracks().forEach((track) => track.stop())
	cameraStream = null
	cameraReady.value = false
}

const capturePhoto = () => {
	const scale = Math.min(1, PHOTO_MAX_WIDTH / video.value.videoWidth)
	const canvas = document.createElement("canvas")
	canvas.width = Math.round(video.value.videoWidth * scale)
	canvas.height = Math.round(video.value.videoHeight * scale)
	canvas.getContext("2d").drawImage(video.value, 0, 0, canvas.width, canvas.height)
	photo.value = canvas.toDataURL("image/jpeg", 0.8)
	stopCamera()
}

const onModalPresent = () => {
	if (photoRequired.value) startCamera()
}

const onModalDismiss = () => {
	stopCamera()
	photo.value = null
	cameraStatus.value = ""
}

const handleEmployeeCheckin = () => {
	checkinTimestamp.value = null
	serverTime.fetch()

	if (settings.data?.allow_geolocation_tracking) {
		fetchLocation()
	}
}

const submitLog = (logType) => {
	const actionLabel = logType === "IN" ? __("Check-in") : __("Check-out")

	checkinRequest.submit(
		{
			log_type: logType,
			photo: photo.value,
			latitude: latitude.value,
			longitude: longitude.value,
		},
		{
			onSuccess(data) {
				if (!data?.name) {
					toast({
						title: __("Error"),
						text: __("{0} failed!", [actionLabel]),
						icon: "alert-circle",
						position: "bottom-center",
						iconClasses: "text-red-500",
					})
					return
				}

				checkins.reload()
				modalController.dismiss()
				toast({
					title: __("Success"),
					text: __("{0} successful at {1}", [actionLabel, dayjs(data.time).format("hh:mm:ss a")]),
					icon: "check-circle",
					position: "bottom-center",
					iconClasses: "text-green-500",
				})
			},
			onError(error) {
				let messages = error.messages?.length ? error.messages : [__("{0} failed!", [actionLabel])]

				for (const message of messages) {
					toast({
						title: __("Error"),
						text: message || __("{0} failed!", [actionLabel]),
						icon: "alert-circle",
						position: "bottom-center",
						iconClasses: "text-red-500",
					})
				}
			},
		}
	)
}

onMounted(() => {
	socket.emit("doctype_subscribe", DOCTYPE)
	socket.on("list_update", (data) => {
		if (data.doctype == DOCTYPE) {
			checkins.reload()
		}
	})
})

onBeforeUnmount(() => {
	stopCamera()
	socket.emit("doctype_unsubscribe", DOCTYPE)
	socket.off("list_update")
})
</script>
