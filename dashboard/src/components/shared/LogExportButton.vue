<script setup lang="ts">
import { ref } from "vue";
import { logApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import { useToast } from "@/utils/toast";

const { tm } = useModuleI18n("features/console");
const toast = useToast();
const exporting = ref(false);

async function exportLogs() {
  exporting.value = true;
  try {
    const response = await logApi.exportArchive();
    const disposition = String(response.headers["content-disposition"] || "");
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download =
      disposition.match(/filename="?([^";]+)"?/)?.[1] || "astrbot-logs.zip";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
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
        @click="exportLogs"
      >
        {{ tm("exportLogs.button") }}
      </v-btn>
    </template>
  </v-tooltip>
</template>
