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

      <!-- ── Args: key-value table ──────────────────────────── -->
      <div v-if="argEntries.length" class="tool-call-detail-row">
        <span class="detail-label">Args:</span>
        <div class="args-table">
          <div
            v-for="(entry, i) in displayedArgEntries"
            :key="i"
            class="args-row"
            :class="{ clickable: entry.long }"
            @click="entry.long && toggleArgExpand(i)"
          >
            <span class="args-key">{{ entry.icon }}{{ entry.key }}</span>
            <span class="args-value">{{ entry.display }}</span>
            <span v-if="entry.long && !expandedArgs[i]" class="args-expand-hint">…</span>
          </div>
          <div
            v-if="argEntries.length > maxVisibleArgs"
            class="args-row args-more"
            @click="showAllArgs = !showAllArgs"
          >
            <span class="args-key"></span>
            <span class="args-value args-more-text">
              {{ showAllArgs
                ? 'Show fewer'
                : `+${argEntries.length - maxVisibleArgs} more` }}
            </span>
          </div>
        </div>
      </div>

      <!-- ── Result ────────────────────────────────────────── -->
      <div
        v-if="isEditTool && editToolDiff"
        class="tool-call-detail-row"
      >
        <span class="detail-label">Result:</span>
        <DiffPreview
          :content="editToolDiff"
          :file-path="editToolFilePath"
          :summary="editToolSummary"
          :is-dark="isDark"
          :max-lines="25"
          :collapsible="false"
        />
        <div v-if="editToolNotice" class="edit-tool-notice">{{ editToolNotice }}</div>
      </div>

      <div
        v-else-if="toolCall.result"
        class="tool-call-detail-row"
      >
        <span class="detail-label">Result:</span>
        <ToolResultView
          :tool-name="toolCall.name ?? ''"
          :result="toolCall.result ?? ''"
          :tool-args="toolCall.args"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { findSystemNoticeIndex } from "@/utils/systemNotice";
import DiffPreview from "./DiffPreview.vue";
import ToolResultView from "./ToolResultView.vue";
import { SPCODE_ICONS } from "./spcode_tools/icons";

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

// ── Icons ─────────────────────────────────────────────────────

const toolCallIcon = computed(() => {
  const name = String(props.toolCall.name || "");
  if (name === "astrbot_file_read_tool") return "mdi-file-document-outline";
  if (name === "astrbot_file_write_tool") return "mdi-content-save-outline";
  if (name === "astrbot_file_edit_tool") return "mdi-file-document-edit-outline";
  if (name === "astrbot_grep_tool") return "mdi-magnify";
  if (name === "astrbot_execute_shell") return "mdi-console-line";
  if (name === "astrbot_execute_python" || name === "astrbot_execute_ipython") return "mdi-language-python";
  if (name === "astrbot_inta_shell_start") return "mdi-play-circle-outline";
  if (name === "astrbot_inta_shell_send") return "mdi-keyboard-outline";
  if (name === "astrbot_inta_shell_read") return "mdi-eye-outline";
  if (name === "astrbot_inta_shell_stop") return "mdi-stop-circle-outline";
  if (name === "astrbot_inta_shell_list") return "mdi-format-list-bulleted";
  if (name === "astrbot_upload_file") return "mdi-upload-outline";
  if (name === "astrbot_download_file") return "mdi-download-outline";
  if (name.includes("web_search") || name.includes("tavily")) return "mdi-web";
  if (SPCODE_ICONS[name]) return SPCODE_ICONS[name];
  return "mdi-wrench";
});

// ── Args display ──────────────────────────────────────────────

const maxVisibleArgs = 5;
const showAllArgs = ref(false);
const expandedArgs = reactive({});

const argEntries = computed(() => {
  const args = props.toolCall.args;
  if (!args || typeof args !== "object") return [];
  return Object.entries(args).map(([key, value], index) => {
    const raw = value === null || value === undefined ? "—" : String(value);
    const long = raw.length > 60;
    const isExpanded = !!expandedArgs[index];
    return {
      key,
      raw,
      long,
      icon: argIcon(key),
      display: long && !isExpanded ? raw.slice(0, 60) : raw,
    };
  });
});

const displayedArgEntries = computed(() => {
  const entries = argEntries.value;
  if (showAllArgs.value) return entries;
  return entries.slice(0, maxVisibleArgs);
});

function argIcon(key) {
  const k = key.toLowerCase();
  if (k.includes("path") || k === "file" || k.includes("dir")) return "📁 ";
  if (k.includes("content") || k === "old" || k === "new" || k === "text") return "📝 ";
  if (k.includes("pattern") || k.includes("query") || k.includes("search")) return "🔍 ";
  if (k.includes("command") || k.includes("cmd")) return "⚡ ";
  if (k.includes("code") || k.includes("python")) return "🐍 ";
  if (k.includes("replace_all")) return "🔄 ";
  if (k.includes("offset") || k.includes("limit") || k.includes("result_limit")) return "#⃣ ";
  return "";
}

function toggleArgExpand(index) {
  expandedArgs[index] = !expandedArgs[index];
}

// ── file_edit_tool diff rendering ─────────────────────────────

const isEditTool = computed(
  () => props.toolCall.name === "astrbot_file_edit_tool",
);

// Strip [SYSTEM NOTICE] suffix from the raw result for all edit tool computed properties.
// Uses the shared findSystemNoticeIndex() to correctly distinguish genuine system
// notices from "[SYSTEM NOTICE]" text that may appear inside the edited file's diff content.
const editToolCleanResult = computed(() => {
  const raw = props.toolCall.result ?? "";
  const idx = findSystemNoticeIndex(raw);
  return idx < 0 ? raw : raw.slice(0, idx).trim();
});

const editToolNotice = computed(() => {
  const raw = props.toolCall.result ?? "";
  const idx = findSystemNoticeIndex(raw);
  return idx < 0 ? null : raw.slice(idx).trim();
});

const editToolDiff = computed(() => {
  if (!isEditTool.value) return "";
  const raw = editToolCleanResult.value;
  const match = raw.match(/```diff\s*\n?([\s\S]*?)```/);
  return match ? match[1] : raw;
});

const editToolFilePath = computed(() => {
  if (!isEditTool.value) return "";
  const raw = editToolCleanResult.value;
  const match = raw.match(/^Edited\s+(.+?)\./m);
  return match ? match[1] : "";
});

const editToolSummary = computed(() => {
  if (!isEditTool.value) return "";
  const raw = editToolCleanResult.value;
  const lines = raw.split("\n");
  const statusParts = [];
  for (const line of lines) {
    if (line.startsWith("Diff:") || line.startsWith("```")) break;
    if (line.trim()) statusParts.push(line.trim());
  }
  return statusParts.join("\n");
});

// ── Duration ──────────────────────────────────────────────────

const toolCallDuration = computed(() => {
  const startTime = Number(props.toolCall.ts);
  if (!Number.isFinite(startTime) || startTime <= 0) return "";
  if (props.toolCall.finished_ts) {
    return formatDuration(Number(props.toolCall.finished_ts) - startTime);
  }
  return elapsedTime.value;
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

.edit-tool-notice {
  margin-top: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), 0.55);
  white-space: pre-wrap;
  word-break: break-word;
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
  word-break: break-all;
}

/* ── Args table ─────────────────────────────────────────────── */

.args-table {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 4px;
  overflow: hidden;
}

.args-row {
  display: flex;
  align-items: baseline;
  padding: 3px 8px;
  font-size: 11.5px;
  line-height: 1.55;
}

.args-row + .args-row {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.05);
}

.args-row.clickable {
  cursor: pointer;
}

.args-row.clickable:hover {
  background: rgba(var(--v-theme-on-surface), 0.03);
}

.args-key {
  flex-shrink: 0;
  width: 110px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 8px;
}

.args-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.8);
  white-space: pre-wrap;
  word-break: break-all;
  min-width: 0;
}

.args-expand-hint {
  color: rgba(var(--v-theme-on-surface), 0.35);
  font-style: italic;
  margin-left: 4px;
}

.args-more {
  cursor: pointer;
  background: rgba(var(--v-theme-on-surface), 0.02);
}

.args-more:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.args-more-text {
  color: rgba(var(--v-theme-on-surface), 0.45) !important;
  font-style: italic;
}

/* ── Legacy detail rows ─────────────────────────────────────── */

.detail-json {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.animate-fade-in {
  animation: fadeIn 0.2s ease-in-out;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
