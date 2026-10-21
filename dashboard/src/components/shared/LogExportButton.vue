<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { logApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import { useToast } from "@/utils/toast";

const { tm } = useModuleI18n("features/console");
const toast = useToast();
const exporting = ref(false);
const exportHint = ref<"stillExporting" | "largeExport" | null>(null);
let exportTimers: ReturnType<typeof setTimeout>[] = [];
onBeforeUnmount(() => {
  for (const timer of exportTimers) clearTimeout(timer);
  exportTimers = [];
});
const dialog = ref(false);
const redact = ref(true);
const timeRange = ref<number | "custom">(86400);
const timeRangeItems = computed(() => [
  { title: tm("exportLogs.lastHour"), value: 3600 },
  { title: tm("exportLogs.last12Hours"), value: 43200 },
  { title: tm("exportLogs.lastDay"), value: 86400 },
  { title: tm("exportLogs.last3Days"), value: 259200 },
  { title: tm("exportLogs.customRange"), value: "custom" },
]);
const startTime = ref("");
const endTime = ref("");
const timeRangeError = computed(() => {
  if (timeRange.value !== "custom") return "";
  const start = new Date(startTime.value).getTime();
  const end = new Date(endTime.value).getTime();
  return Number.isFinite(start) && Number.isFinite(end) && start <= end
    ? ""
    : tm("exportLogs.invalidTimeRange");
});
const attachTarget = ref<Element>();

function openDialog() {
  redact.value = true;
  timeRange.value = 86400;
  const now = Math.floor(Date.now() / 1000) * 1000;
  [startTime.value, endTime.value] = [now - 24 * 60 * 60 * 1000, now].map(
    (timestamp) => {
      const date = new Date(timestamp);
      return new Date(timestamp - date.getTimezoneOffset() * 60 * 1000)
        .toISOString()
        .slice(0, 19);
    },
  );
  attachTarget.value = document.fullscreenElement || undefined;
  dialog.value = true;
}

async function exportLogs() {
  if (timeRangeError.value || exporting.value) return;
  exporting.value = true;
  exportHint.value = null;
  exportTimers = [
    setTimeout(() => { exportHint.value = "stillExporting"; }, 5000),
    setTimeout(() => { exportHint.value = "largeExport"; }, 10000),
  ];
  try {
    const range = timeRange.value;
    const end =
      range === "custom"
        ? Math.floor(new Date(endTime.value).getTime() / 1000)
        : Math.floor(Date.now() / 1000);
    const start =
      range === "custom"
        ? Math.floor(new Date(startTime.value).getTime() / 1000)
        : end - range;
    const response = await logApi.exportArchive(
      redact.value,
      start,
      end,
    );
    const disposition = String(response.headers["content-disposition"] || "");
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download =
      disposition.match(/filename="?([^";]+)"?/)?.[1] ||
      "astrbot-diagnostics.zip";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    dialog.value = false;
  } catch {
    toast.error(tm("exportLogs.failed"));
  } finally {
    for (const timer of exportTimers) clearTimeout(timer);
    exportTimers = [];
    exportHint.value = null;
    exporting.value = false;
  }
}
</script>

<template>
  <v-tooltip :text="tm('exportLogs.hint')" location="bottom" max-width="320">
    <template #activator="{ props }">
      <v-btn
        v-bind="props"
        size="small"
        variant="tonal"
        prepend-icon="mdi-download"
        :loading="exporting"
        @click="openDialog"
      >
        {{ tm("exportLogs.button") }}
      </v-btn>
    </template>
  </v-tooltip>
  <v-dialog
    v-model="dialog"
    :attach="attachTarget"
    :persistent="exporting"
    width="500"
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{
        tm("exportLogs.button")
      }}</v-card-title>
      <v-card-text class="pa-6 pb-2">
        <p>{{ tm("exportLogs.contents") }}</p>
        <v-select
          v-model="timeRange"
          :items="timeRangeItems"
          :label="tm('exportLogs.timeRange')"
          :disabled="exporting"
          variant="outlined"
          density="comfortable"
          hide-details
          class="mt-4"
        />
        <template v-if="timeRange === 'custom'">
          <v-text-field
            v-model="startTime"
            type="datetime-local"
            :label="tm('exportLogs.startTime')"
            :max="endTime"
            :disabled="exporting"
            variant="outlined"
            density="comfortable"
            step="1"
            hide-details
            class="mt-3"
          />
          <v-text-field
            v-model="endTime"
            type="datetime-local"
            :label="tm('exportLogs.endTime')"
            :min="startTime"
            :disabled="exporting"
            :error-messages="timeRangeError"
            :hint="tm('exportLogs.timeRangeHint')"
            variant="outlined"
            density="comfortable"
            persistent-hint
            step="1"
            class="mt-3"
          />
        </template>
        <v-checkbox
          v-model="redact"
          :label="tm('exportLogs.redact')"
          :disabled="exporting"
          color="primary"
          hide-details
          class="mt-2"
        />
        <v-alert :type="redact ? 'info' : 'warning'" variant="tonal" class="mt-2">{{
          tm(redact ? "exportLogs.privacy" : "exportLogs.rawPrivacy")
        }}</v-alert>
        <small
          v-if="exporting && exportHint"
          class="d-block mt-3 text-medium-emphasis"
          role="status"
          aria-live="polite"
        >{{ tm(`exportLogs.${exportHint}`) }}</small>
      </v-card-text>
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" :disabled="exporting" @click="dialog = false">{{
          tm("exportLogs.cancel")
        }}</v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          :loading="exporting"
          :disabled="Boolean(timeRangeError)"
          @click="exportLogs"
          >{{ tm("exportLogs.download") }}</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
