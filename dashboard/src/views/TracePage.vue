<script setup>
import TraceDisplayer from '@/components/shared/TraceDisplayer.vue';
import { useModuleI18n } from '@/i18n/composables';
import { computed, ref, onMounted } from 'vue';
import { useTheme } from 'vuetify';
import axios from 'axios';

const { tm } = useModuleI18n('features/trace');
const theme = useTheme();

const isDark = computed(() => theme.global.current.value.dark);
const traceEnabled = ref(true);
const loading = ref(false);
const traceDisplayerKey = ref(0);

const fetchTraceSettings = async () => {
  try {
    const res = await axios.get('/api/trace/settings');
    if (res.data?.status === 'ok') {
      traceEnabled.value = res.data.data?.trace_enable ?? true;
    }
  } catch (err) {
    console.error('Failed to fetch trace settings:', err);
  }
};

const updateTraceSettings = async () => {
  loading.value = true;
  try {
    await axios.post('/api/trace/settings', {
      trace_enable: traceEnabled.value
    });
    // Refresh the TraceDisplayer component to reconnect SSE
    traceDisplayerKey.value += 1;
  } catch (err) {
    console.error('Failed to update trace settings:', err);
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchTraceSettings();
});
</script>

<template>
  <div class="dashboard-page trace-page" :class="{ 'is-dark': isDark }">
    <v-container fluid class="dashboard-shell trace-shell pa-4 pa-md-6">
      <div class="dashboard-header trace-header">
        <div class="dashboard-header-main">
          <h1 class="dashboard-title">{{ tm('title') }}</h1>
          <p class="dashboard-subtitle">
            {{ tm('hint') }}
          </p>
        </div>
        <div class="dashboard-header-actions">
          <v-switch
            v-model="traceEnabled"
            :loading="loading"
            :disabled="loading"
            color="primary"
            hide-details
            density="compact"
            inset
            @update:model-value="updateTraceSettings"
          >
            <template #label>
              <span class="switch-label">{{ traceEnabled ? tm('recording') : tm('paused') }}</span>
            </template>
          </v-switch>
        </div>
      </div>
      <div class="trace-body">
        <TraceDisplayer :key="traceDisplayerKey" />
      </div>
    </v-container>
  </div>
</template>

<script>
export default {
  name: 'TracePage',
  components: {
    TraceDisplayer
  }
};
</script>

<style scoped>
@import '@/styles/dashboard-shell.css';

.trace-page,
.trace-shell {
  height: 100%;
}

.trace-shell {
  display: flex;
  flex-direction: column;
}

.trace-header {
  flex: 0 0 auto;
}

.trace-body {
  flex: 1 1 auto;
  min-height: 0;
}

.switch-label {
  color: var(--dashboard-muted);
  font-size: 13px;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .trace-header {
    align-items: flex-start;
  }
}
</style>
