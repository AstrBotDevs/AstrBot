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
      traceEnabled.value = res.data?.data?.trace_enable ?? true;
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
    <div class="trace-topbar">
      <div class="topbar-left">
        <div class="topbar-title">{{ tm('title') || '追踪' }}</div>
        <div class="topbar-desc">{{ tm('hint') }}</div>
      </div>
      <div class="topbar-right">
        <div class="switch-wrap">
          <span class="switch-label">{{ traceEnabled ? tm('recording') : tm('paused') }}</span>
          <button
            class="switch-btn"
            :class="{ 'switch-btn-on': traceEnabled }"
            @click="updateTraceSettings"
            :disabled="loading"
          >
            <span class="switch-knob"></span>
          </button>
        </div>
      </div>
    </div>
    <div style="flex: 1; min-height: 0; overflow: hidden;">
      <TraceDisplayer :key="traceDisplayerKey" />
    </div>
  </div>
</template>

<script>
export default {
  name: 'TracePage',
  components: { TraceDisplayer }
};
</script>

<style scoped>
.trace-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 32px;
  background: #0a0a0f;
  border-bottom: 1px solid rgba(0, 242, 255, 0.1);
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.topbar-title {
  font-size: 16px;
  font-weight: 700;
  color: #00F2FF;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 1px;
}

.topbar-desc {
  font-size: 11px;
  color: #4b5563;
}

.topbar-right {
  display: flex;
  align-items: center;
}

.switch-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.switch-label {
  font-size: 12px;
  color: #9ca3af;
  font-family: 'JetBrains Mono', monospace;
}

.switch-btn {
  width: 40px;
  height: 22px;
  border-radius: 11px;
  background: #1e293b;
  border: 1px solid #334155;
  cursor: pointer;
  position: relative;
  transition: all 0.3s ease;
  padding: 0;
}

.switch-btn:hover {
  border-color: rgba(0, 242, 255, 0.3);
}

.switch-btn-on {
  background: rgba(0, 242, 255, 0.15);
  border-color: rgba(0, 242, 255, 0.4);
}

.switch-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #475569;
  transition: all 0.3s ease;
}

.switch-btn-on .switch-knob {
  left: 20px;
  background: #00F2FF;
  box-shadow: 0 0 8px rgba(0, 242, 255, 0.5);
}
</style>
