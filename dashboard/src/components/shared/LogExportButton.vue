<script setup lang="ts">
import { ref } from "vue";
import { logApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import { useToast } from "@/utils/toast";

const { tm } = useModuleI18n("features/console");
const toast = useToast();
const exporting = ref(false);
const dialog = ref(false);
const redact = ref(true);
const attachTarget = ref<Element>();

function openDialog() {
  redact.value = true;
  attachTarget.value = document.fullscreenElement || undefined;
  dialog.value = true;
}

async function exportLogs() {
  exporting.value = true;
  try {
    const response = await logApi.exportArchive(redact.value);
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
          @click="exportLogs"
          >{{ tm("exportLogs.download") }}</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
