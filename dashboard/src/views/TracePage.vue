<script setup>
import TraceDisplayer from '@/components/shared/TraceDisplayer.vue';
import { useModuleI18n } from '@/i18n/composables';
import { ref, onMounted } from 'vue';
import axios from 'axios';

const { tm } = useModuleI18n('features/trace');

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
  <div style="height: 100%; display: flex; flex-direction: column;">
    <div class="trace-header">
      <div class="trace-info">
        <v-icon size="small" color="info" class="mr-2">mdi-information-outline</v-icon>
        <span class="trace-hint">当前仅记录部分 AstrBot 主 Agent 的模型调用路径，后续会不断完善。</span>
      </div>
      <div class="trace-controls">
        <v-switch
          v-model="traceEnabled"
          :loading="loading"
          :disabled="loading"
          color="primary"
          hide-details
          density="compact"
          @update:model-value="updateTraceSettings"
        >
          <template #label>
            <span class="switch-label">{{ traceEnabled ? '记录中' : '已暂停' }}</span>
          </template>
        </v-switch>
      </div>
    </div>
    <div style="flex: 1; min-height: 0;">
      <TraceDisplayer :key="traceDisplayerKey" />
    </div>
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
.trace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: rgba(59, 130, 246, 0.05);
  border-bottom: 1px solid rgba(59, 130, 246, 0.1);
  border-radius: 8px 8px 0 0;
  margin-bottom: 8px;
}

.trace-info {
  display: flex;
  align-items: center;
}

.trace-hint {
  font-size: 13px;
  color: #6b7280;
}

.trace-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.switch-label {
  font-size: 13px;
  color: #4b5563;
  white-space: nowrap;
}
</style>
