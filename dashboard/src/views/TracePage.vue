<script setup>
import TraceDisplayer from "@/components/shared/TraceDisplayer.vue";
import { useModuleI18n } from "@/i18n/composables";
import axios from "@/utils/request";
import { ref, onMounted } from "vue";

const { tm } = useModuleI18n("features/trace");

const traceEnabled = ref(true);
const loading = ref(false);
const traceDisplayerKey = ref(0);

const fetchTraceSettings = async () => {
  try {
    const res = await axios.get("/api/trace/settings");
    if (res.data?.status === "ok") {
      traceEnabled.value = res.data?.data?.trace_enable ?? true;
    }
  } catch (err) {
    console.error("Failed to fetch trace settings:", err);
  }
};

const updateTraceSettings = async (nextValue = !traceEnabled.value) => {
  const previousValue = traceEnabled.value;
  traceEnabled.value = nextValue;
  loading.value = true;
  try {
    await axios.post("/api/trace/settings", {
      trace_enable: nextValue,
    });
    traceDisplayerKey.value += 1;
  } catch (err) {
    traceEnabled.value = previousValue;
    console.error("Failed to update trace settings:", err);
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchTraceSettings();
});
</script>

<template>
  <div class="trace-page">
    <div class="trace-topbar">
      <div class="topbar-left">
        <div
          class="topbar-title"
          style="
            color: var(--trace-primary) !important;
            -webkit-text-fill-color: var(--trace-primary) !important;
            opacity: 1 !important;
            visibility: visible !important;
          "
        >
          {{ tm("title") || "追踪" }}
        </div>
        <div
          class="topbar-desc"
          style="
            color: var(--trace-muted) !important;
            -webkit-text-fill-color: var(--trace-muted) !important;
            opacity: 1 !important;
            visibility: visible !important;
          "
        >
          {{ tm("hint") }}
        </div>
      </div>
      <div class="topbar-right">
        <v-switch
          :model-value="traceEnabled"
          :label="traceEnabled ? tm('recording') : tm('paused')"
          class="trace-switch"
          color="primary"
          hide-details
          density="compact"
          inset
          :disabled="loading"
          @update:model-value="updateTraceSettings"
        />
      </div>
    </div>
    <div class="trace-content">
      <TraceDisplayer :key="traceDisplayerKey" />
    </div>
  </div>
</template>

<script>
export default {
  name: "TracePage",
  components: { TraceDisplayer },
};
</script>

<style scoped>
.trace-page {
  --trace-page-bg: transparent;
  --trace-panel-bg: rgba(var(--v-theme-surface), 0.78);
  --trace-card-bg: rgba(var(--v-theme-surface), 0.9);
  --trace-record-bg: rgba(var(--v-theme-surface-variant), 0.38);
  --trace-empty-surface: rgba(var(--v-theme-surface), 0.68);
  --trace-primary: rgb(var(--v-theme-primary));
  --trace-primary-soft: rgba(var(--v-theme-primary), 0.08);
  --trace-primary-soft-strong: rgba(var(--v-theme-primary), 0.14);
  --trace-border: rgba(var(--v-theme-borderLight), 0.22);
  --trace-border-strong: rgba(var(--v-theme-borderLight), 0.4);
  --trace-border-active: rgba(var(--v-theme-primary), 0.24);
  --trace-track: rgba(var(--v-theme-borderLight), 0.78);
  --trace-track-active: rgba(var(--v-theme-primary), 0.22);
  --trace-title: rgb(var(--v-theme-on-surface));
  --trace-text: rgba(var(--v-theme-on-surface), 0.92);
  --trace-muted: rgba(var(--v-theme-on-surface), 0.7);
  --trace-subtle: rgba(var(--v-theme-on-surface), 0.54);
  --trace-empty-icon-bg: rgba(var(--v-theme-primary), 0.1);
  --trace-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  position: relative;
  z-index: 1;
  isolation: isolate;
  gap: 16px;
  padding: 16px;
}

:global(.v-theme--bluebusinessdarktheme) .trace-page {
  --trace-panel-bg: rgba(var(--v-theme-surface), 0.72);
  --trace-card-bg: rgba(var(--v-theme-surface-variant), 0.74);
  --trace-record-bg: rgba(var(--v-theme-surface), 0.52);
  --trace-empty-surface: rgba(var(--v-theme-surface-variant), 0.56);
  --trace-border: rgba(var(--v-theme-borderLight), 0.46);
  --trace-border-strong: rgba(var(--v-theme-borderLight), 0.66);
  --trace-track: rgba(var(--v-theme-borderLight), 0.9);
  --trace-shadow: none;
}

.trace-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: var(--trace-panel-bg);
  border: 1px solid var(--trace-border);
  border-radius: 12px;
  backdrop-filter: blur(16px);
  box-shadow: var(--trace-shadow);
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.topbar-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--trace-primary) !important;
  -webkit-text-fill-color: var(--trace-primary);
  letter-spacing: 0.01em;
}

.topbar-desc {
  font-size: 13px;
  color: var(--trace-muted) !important;
  -webkit-text-fill-color: var(--trace-muted);
  line-height: 1.5;
  max-width: 60ch;
}

.topbar-right {
  display: flex;
  align-items: center;
}

:deep(.trace-switch .v-label) {
  color: var(--trace-text) !important;
  -webkit-text-fill-color: var(--trace-text);
  font-size: 13px;
}

.trace-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
  z-index: 1;
  background: var(--trace-panel-bg);
  border: 1px solid var(--trace-border);
  border-radius: 12px;
  backdrop-filter: blur(16px);
  box-shadow: var(--trace-shadow);
}

@media (max-width: 700px) {
  .trace-topbar {
    flex-direction: column;
    align-items: flex-start;
    padding: 16px;
  }

  .topbar-right {
    width: 100%;
  }

  .topbar-desc {
    max-width: none;
  }

  .trace-page {
    gap: 12px;
    padding: 12px;
  }
}
</style>
