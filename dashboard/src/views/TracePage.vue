<script setup lang="ts">
import { onMounted, ref } from "vue";
import TraceDisplayer from "@/components/shared/TraceDisplayer.vue";
import { traceApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import { useToast } from "@/utils/toast";

const { tm } = useModuleI18n("features/trace");
const toast = useToast();
const traceEnabled = ref(true);
const loading = ref(true);

async function fetchTraceSettings() {
  try {
    const response = await traceApi.getSettings();
    if (response.data?.status !== "ok")
      throw new Error("Trace settings are unavailable");
    const enabled = response.data.data?.trace_enable;
    traceEnabled.value = typeof enabled === "boolean" ? enabled : true;
  } catch (error) {
    console.error("Failed to fetch trace settings:", error);
    toast.error(tm("controls.loadFailed"));
  } finally {
    loading.value = false;
  }
}

async function updateTraceSettings() {
  if (loading.value) return;
  const nextEnabled = !traceEnabled.value;
  loading.value = true;
  try {
    const response = await traceApi.updateSettings({
      trace_enable: nextEnabled,
    });
    if (response.data?.status !== "ok")
      throw new Error("Trace settings update failed");
    traceEnabled.value = nextEnabled;
  } catch (error) {
    console.error("Failed to update trace settings:", error);
    toast.error(tm("controls.updateFailed"));
  } finally {
    loading.value = false;
  }
}

onMounted(fetchTraceSettings);
</script>

<template>
  <div class="trace-page">
    <div class="trace-body">
      <TraceDisplayer
        :recording-enabled="traceEnabled"
        :recording-busy="loading"
        @toggle-recording="updateTraceSettings"
      />
    </div>
  </div>
</template>

<style scoped>
.trace-page {
  display: flex;
  flex-direction: column;
  height: calc(100dvh - 112px);
  margin: 0 auto;
  max-width: 1560px;
  min-height: 0;
  overflow: hidden;
  padding: 0 12px max(8px, env(safe-area-inset-bottom));
  width: 100%;
}

.trace-body {
  flex: 1 1 auto;
  min-height: 0;
}

@media (max-width: 800px) {
  .trace-page {
    padding: 0 4px max(6px, env(safe-area-inset-bottom));
  }
}
</style>
