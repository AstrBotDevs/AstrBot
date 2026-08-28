<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useTheme } from 'vuetify';
import { traceApi } from '@/api/v1';
import TraceDisplayer from '@/components/shared/TraceDisplayer.vue';
import { useModuleI18n } from '@/i18n/composables';

defineOptions({ name: 'TracePage' });

const { tm } = useModuleI18n('features/trace');
const theme = useTheme();

const isDark = computed(() => theme.global.current.value.dark);
const traceEnabled = ref(true);
const confirmedTraceEnabled = ref(true);
const loading = ref(false);
const updateError = ref('');
const traceDisplayerKey = ref(0);

const fetchTraceSettings = async () => {
  try {
    const res = await traceApi.getSettings();
    if (res.data?.status === 'ok') {
      const enabled = res.data.data?.enabled ?? true;
      traceEnabled.value = enabled;
      confirmedTraceEnabled.value = enabled;
    }
  } catch {
    console.error('Failed to fetch trace settings');
  }
};

const updateTraceSettings = async () => {
  loading.value = true;
  updateError.value = '';
  try {
    const response = await traceApi.updateSettings({
      enabled: traceEnabled.value,
    });
    if (response.data?.status !== 'ok') {
      throw new Error('Trace settings update was rejected');
    }
    confirmedTraceEnabled.value = traceEnabled.value;
    traceDisplayerKey.value += 1;
  } catch {
    console.error('Failed to update trace settings');
    traceEnabled.value = confirmedTraceEnabled.value;
    updateError.value = tm('errors.updateFailed');
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  void fetchTraceSettings();
});
</script>

<template>
  <div class="trace-page" :class="{ 'is-dark': isDark }">
    <section class="trace-card">
      <div class="trace-toolbar">
        <div class="trace-hint">
          <v-icon size="16" aria-hidden="true"
            >mdi-timeline-text-outline</v-icon
          >
          <span>{{ tm('hint') }}</span>
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
              {{ traceEnabled ? tm('recording') : tm('paused') }}
            </span>
          </template>
        </v-switch>
      </div>
      <div class="trace-body">
        <v-alert v-if="updateError" type="error" variant="tonal" class="mb-4">
          {{ updateError }}
        </v-alert>
        <TraceDisplayer :key="traceDisplayerKey" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.trace-page {
  --trace-card: #f5f6f7;
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
  flex-wrap: wrap;
  gap: 8px 16px;
  justify-content: space-between;
  min-height: 42px;
  padding: 0 2px 10px;
}

.trace-hint {
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.58);
  display: inline-flex;
  font-size: 0.78rem;
  gap: 8px;
  line-height: 1.45;
  min-width: 0;
}

.trace-body {
  flex: 1 1 auto;
  min-height: 0;
}

.switch-label {
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 13px;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .trace-page {
    padding: 0 4px 6px;
  }

  .trace-toolbar {
    align-items: flex-start;
  }
}
</style>
