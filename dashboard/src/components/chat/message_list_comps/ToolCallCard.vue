<template>
  <div class="tool-call-card" :class="{ expanded: isExpanded }">
    <button class="tool-call-header" type="button" @click="toggleExpanded">
      <v-icon size="16" class="tool-call-icon">{{ toolCallIcon }}</v-icon>
      <span class="tool-call-title">
        {{ tm("actions.toolCallUsed", { name: displayToolName }) }}
      </span>
      <span class="tool-call-duration">{{ toolCallDuration }}</span>
      <v-icon
        size="22"
        class="tool-call-expand-icon"
        :class="{ expanded: isExpanded }"
      >
        mdi-chevron-right
      </v-icon>
    </button>

    <div v-if="isExpanded" class="tool-call-details">
      <div v-if="toolCall.id" class="tool-call-detail-row">
        <span class="detail-label">ID:</span>
        <code class="detail-value">
          {{ toolCall.id }}
        </code>
      </div>

      <div class="tool-call-detail-row">
        <span class="detail-label">Args:</span>
        <pre class="detail-value detail-json">{{
          JSON.stringify(toolCall.args, null, 2)
        }}</pre>
      </div>

      <div v-if="toolCall.result" class="tool-call-detail-row">
        <span class="detail-label">Result:</span>
        <pre class="detail-value detail-json detail-result">{{
          formattedResult
        }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps({
  toolCall: {
    type: Object,
    required: true,
  },
  isDark: {
    type: Boolean,
    default: false,
  },
  initialExpanded: {
    type: Boolean,
    default: false,
  },
});

const { tm } = useModuleI18n("features/chat");
const isExpanded = ref(props.initialExpanded);
const currentTime = ref(Date.now() / 1000);
let timer = null;

const elapsedTime = computed(() => {
  if (props.toolCall.finished_ts) return "";
  const startTime = Number(props.toolCall.ts);
  if (!Number.isFinite(startTime) || startTime <= 0) return "";
  return formatDuration(currentTime.value - startTime);
});

const displayToolName = computed(() => props.toolCall.name || "tool");

const toolCallIcon = computed(() => {
  const name = String(props.toolCall.name || "");
  if (name === "astrbot_execute_ipython" || name === "astrbot_execute_python") {
    return "mdi-code-json";
  }
  if (name.includes("web_search") || name.includes("tavily")) {
    return "mdi-web";
  }
  if (name === "astrbot_execute_shell") {
    return "mdi-console-line";
  }
  return "mdi-wrench";
});

const toolCallDuration = computed(() => {
  const startTime = Number(props.toolCall.ts);
  if (!Number.isFinite(startTime) || startTime <= 0) return "";
  if (props.toolCall.finished_ts) {
    return formatDuration(Number(props.toolCall.finished_ts) - startTime);
  }
  return elapsedTime.value;
});

const formattedResult = computed(() => {
  if (!props.toolCall.result) return "";
  try {
    const parsed = JSON.parse(props.toolCall.result);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return props.toolCall.result;
  }
});

const formatDuration = (seconds) => {
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  if (seconds < 1) {
    return `${Math.round(seconds * 1000)}ms`;
  } else if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  } else {
    const minutes = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${minutes}m ${secs}s`;
  }
};

const toggleExpanded = () => {
  isExpanded.value = !isExpanded.value;
};

const updateTime = () => {
  currentTime.value = Date.now() / 1000;
};

onMounted(() => {
  if (!props.toolCall.finished_ts) {
    timer = setInterval(updateTime, 100);
  }
});

onUnmounted(() => {
  if (timer) {
    clearInterval(timer);
  }
});
</script>

<style scoped>
.tool-call-card {
  margin: 6px 0;
  max-width: 100%;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: inherit;
  line-height: inherit;
}

.tool-call-card.expanded {
  width: 100%;
}

.tool-call-header {
  max-width: 100%;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  user-select: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font: inherit;
  text-align: left;
}

.tool-call-header:hover {
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.tool-call-expand-icon {
  color: currentcolor;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.tool-call-expand-icon.expanded {
  transform: rotate(90deg);
}

.tool-call-icon {
  color: currentcolor;
  flex-shrink: 0;
}

.tool-call-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-call-duration {
  flex-shrink: 0;
  color: rgba(var(--v-theme-on-surface), 0.48);
}

.tool-call-details {
  margin-top: 8px;
  padding-left: 26px;
  animation: fadeIn 0.2s ease-in-out;
}

.tool-call-detail-row {
  display: flex;
  flex-direction: column;
  margin-bottom: 8px;
}

.tool-call-detail-row:last-child {
  margin-bottom: 0;
}

.detail-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.55);
  text-transform: uppercase;
  margin-bottom: 4px;
}

.detail-value {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.8);
  background-color: transparent;
  padding: 0;
  border-radius: 4px;
  word-break: break-all;
}

.detail-json {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.detail-result {
  max-height: 300px;
  background-color: transparent;
}

.animate-fade-in {
  animation: fadeIn 0.2s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}
</style>
