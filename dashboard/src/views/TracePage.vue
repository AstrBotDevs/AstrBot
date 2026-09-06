<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Waypoints } from "@lucide/vue";
import { useTheme } from "vuetify";
import TraceDisplayer from "@/components/shared/TraceDisplayer.vue";
import { traceApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/trace");
const theme = useTheme();

const isDark = computed(() => theme.global.current.value.dark);
const traceEnabled = ref(true);
const loading = ref(false);
const traceDisplayerKey = ref(0);

async function fetchTraceSettings() {
  try {
    const response = await traceApi.getSettings();
    if (response.data?.status === "ok") {
      const enabled = response.data.data?.trace_enable;
      traceEnabled.value = typeof enabled === "boolean" ? enabled : true;
    }
  } catch (error) {
    console.error("Failed to fetch trace settings:", error);
  }
}

async function updateTraceSettings() {
  loading.value = true;
  try {
    await traceApi.updateSettings({ trace_enable: traceEnabled.value });
    traceDisplayerKey.value += 1;
  } catch (error) {
    console.error("Failed to update trace settings:", error);
  } finally {
    loading.value = false;
  }
}

onMounted(fetchTraceSettings);
</script>

<template>
  <div class="trace-page" :class="{ 'is-dark': isDark }">
    <section class="trace-card">
      <div class="trace-toolbar">
        <div class="trace-hint">
          <Waypoints :size="16" :stroke-width="1.8" aria-hidden="true" />
          <span>{{ tm("hint") }}</span>
        </div>
        <v-switch
          v-model="traceEnabled"
          :loading="loading"
          :disabled="loading"
          :aria-label="tm('toggleLabel')"
          color="primary"
          hide-details
          density="compact"
          inset
          @update:model-value="updateTraceSettings"
        >
          <template #label>
            <span class="switch-label">
              {{ traceEnabled ? tm("recording") : tm("paused") }}
            </span>
          </template>
        </v-switch>
      </div>
      <div class="trace-body">
        <TraceDisplayer :key="traceDisplayerKey" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.trace-page {
  --trace-card: rgba(var(--v-theme-surface), 0.78);
  --trace-card-bg: rgba(var(--v-theme-surface), 0.94);
  --trace-record-bg: rgba(var(--v-theme-primary), 0.035);
  --trace-empty-surface: rgba(var(--v-theme-surface), 0.9);
  --trace-empty-icon-bg: rgba(var(--v-theme-primary), 0.12);
  --trace-text: rgba(var(--v-theme-on-surface), 0.92);
  --trace-title: rgb(var(--v-theme-on-surface));
  --trace-muted: rgba(var(--v-theme-on-surface), 0.72);
  --trace-subtle: rgba(var(--v-theme-on-surface), 0.56);
  --trace-primary: rgb(var(--v-theme-primary));
  --trace-primary-soft: rgba(var(--v-theme-primary), 0.1);
  --trace-border: rgba(var(--v-theme-borderLight), 0.46);
  --trace-border-strong: rgba(var(--v-theme-primary), 0.22);
  --trace-border-active: rgba(var(--v-theme-primary), 0.38);
  --trace-track: rgba(var(--v-theme-borderLight), 0.5);
  --trace-track-active: rgba(var(--v-theme-primary), 0.3);
  --trace-shadow: 0 10px 24px rgba(var(--v-theme-primary), 0.08);

  height: calc(100dvh - 112px);
  margin: 0 auto;
  max-width: 1560px;
  min-height: 0;
  padding: 0 12px 8px;
  width: 100%;
}

.trace-page.is-dark {
  --trace-card: rgba(var(--v-theme-on-surface), 0.06);
}

.trace-card {
  background: var(--trace-card);
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  padding: 12px;
}

.trace-toolbar {
  align-items: center;
  display: flex;
  flex: 0 0 auto;
  gap: 20px;
  justify-content: space-between;
  min-height: 42px;
  padding: 0 2px 10px;
}

.trace-hint {
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.58);
  display: flex;
  font-size: 0.75rem;
  gap: 7px;
  line-height: 1.45;
  min-width: 0;
}

.trace-hint svg {
  flex: 0 0 auto;
}

.switch-label {
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 0.75rem;
  white-space: nowrap;
}

.trace-toolbar :deep(.v-switch .v-selection-control) {
  min-height: 34px;
}

.trace-body {
  flex: 1 1 auto;
  min-height: 0;
}

@media (max-width: 800px) {
  .trace-page {
    padding: 0 4px 6px;
  }

  .trace-card {
    border-radius: 14px;
    padding: 10px;
  }

  .trace-toolbar {
    align-items: flex-start;
    gap: 8px;
    padding: 0 0 8px;
  }

  .trace-hint {
    padding-top: 7px;
  }
}

@media (max-width: 520px) {
  .trace-toolbar {
    justify-content: flex-end;
  }

  .trace-hint {
    display: none;
  }
}
</style>
