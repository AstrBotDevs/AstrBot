<script setup>
import TraceDisplayer from "@/components/shared/TraceDisplayer.vue";
import { useModuleI18n } from "@/i18n/composables";
import { ref, onMounted } from "vue";
import axios from "axios";

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

const updateTraceSettings = async () => {
  loading.value = true;
  try {
    await axios.post("/api/trace/settings", {
      trace_enable: traceEnabled.value,
    });
    traceDisplayerKey.value += 1;
  } catch (err) {
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
        <div class="topbar-title">{{ tm("title") || "追踪" }}</div>
        <div class="topbar-desc">{{ tm("hint") }}</div>
      </div>
      <div class="topbar-right">
        <div class="switch-wrap">
          <span class="switch-label">{{
            traceEnabled ? tm("recording") : tm("paused")
          }}</span>
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
  --trace-page-bg: linear-gradient(180deg, #06141d 0%, #04070b 100%);
  --trace-panel-bg: rgba(8, 14, 20, 0.94);
  --trace-card-bg: rgba(10, 18, 25, 0.94);
  --trace-record-bg: rgba(3, 10, 16, 0.52);
  --trace-empty-surface: rgba(7, 16, 24, 0.8);
  --trace-primary: #00f2ff;
  --trace-primary-soft: rgba(0, 242, 255, 0.1);
  --trace-primary-soft-strong: rgba(0, 242, 255, 0.16);
  --trace-border: rgba(83, 104, 120, 0.3);
  --trace-border-strong: rgba(0, 242, 255, 0.18);
  --trace-border-active: rgba(0, 242, 255, 0.38);
  --trace-track: rgba(71, 85, 105, 0.42);
  --trace-track-active: rgba(0, 242, 255, 0.3);
  --trace-title: #f4feff;
  --trace-text: rgba(226, 232, 240, 0.92);
  --trace-muted: rgba(203, 213, 225, 0.76);
  --trace-subtle: rgba(148, 163, 184, 0.76);
  --trace-empty-icon-bg: rgba(0, 242, 255, 0.12);
  --trace-shadow: 0 18px 48px rgba(0, 0, 0, 0.28);
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

:global(.v-theme--bluebusinesstheme) .trace-page {
  --trace-page-bg: linear-gradient(180deg, #f7fbff 0%, #eef4fa 100%);
  --trace-panel-bg: rgba(255, 255, 255, 0.94);
  --trace-card-bg: rgba(255, 255, 255, 0.97);
  --trace-record-bg: rgba(243, 247, 251, 0.94);
  --trace-empty-surface: rgba(248, 250, 252, 0.98);
  --trace-primary: #003153;
  --trace-primary-soft: rgba(0, 49, 83, 0.08);
  --trace-primary-soft-strong: rgba(0, 49, 83, 0.14);
  --trace-border: rgba(15, 23, 42, 0.1);
  --trace-border-strong: rgba(0, 49, 83, 0.14);
  --trace-border-active: rgba(0, 49, 83, 0.26);
  --trace-track: rgba(148, 163, 184, 0.42);
  --trace-track-active: rgba(0, 49, 83, 0.22);
  --trace-title: #10243d;
  --trace-text: rgba(15, 23, 42, 0.88);
  --trace-muted: rgba(51, 65, 85, 0.84);
  --trace-subtle: rgba(71, 85, 105, 0.74);
  --trace-empty-icon-bg: rgba(0, 49, 83, 0.08);
  --trace-shadow: 0 16px 36px rgba(15, 23, 42, 0.08);
}

.trace-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 32px;
  background: var(--trace-panel-bg);
  border-bottom: 1px solid var(--trace-border-strong);
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
  color: var(--trace-primary);
  font-family:
    "JetBrains Mono", "Fira Code", "PingFang SC", "Microsoft YaHei", monospace;
  letter-spacing: 1px;
}

.topbar-desc {
  font-size: 11px;
  color: var(--trace-muted);
  max-width: 64ch;
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
  color: var(--trace-text);
  font-family:
    "JetBrains Mono", "Fira Code", "PingFang SC", "Microsoft YaHei", monospace;
}

.switch-btn {
  width: 40px;
  height: 22px;
  border-radius: 11px;
  background: var(--trace-primary-soft);
  border: 1px solid var(--trace-border);
  cursor: pointer;
  position: relative;
  transition: all 0.3s ease;
  padding: 0;
}

.switch-btn:hover {
  border-color: var(--trace-border-active);
}

.switch-btn-on {
  background: var(--trace-primary-soft-strong);
  border-color: var(--trace-border-active);
}

.switch-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--trace-subtle);
  transition: all 0.3s ease;
}

.switch-btn-on .switch-knob {
  left: 20px;
  background: var(--trace-primary);
  box-shadow: 0 0 8px rgba(0, 242, 255, 0.5);
}

.trace-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

@media (max-width: 700px) {
  .trace-topbar {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
    padding: 16px;
  }

  .topbar-desc {
    max-width: none;
  }
}
</style>
