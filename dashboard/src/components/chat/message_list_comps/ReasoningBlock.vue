<template>
  <div class="reasoning-block" :class="{ 'reasoning-block--dark': isDark }">
    <button class="reasoning-header" type="button" @click="toggleExpanded">
      <span class="reasoning-title">
        {{ tm("reasoning.thinking") }}
      </span>
      <v-icon
        size="22"
        class="reasoning-icon"
        :class="{ 'rotate-90': isExpanded }"
      >
        mdi-chevron-right
      </v-icon>
    </button>

    <div v-if="isExpanded" class="reasoning-content animate-fade-in">
      <template v-for="(part, partIndex) in renderParts" :key="reasoningPartKey(part, partIndex)">
        <MarkdownRender
          v-if="part.type === 'think'"
          :key="`reasoning-${partIndex}-${isDark ? 'dark' : 'light'}`"
          :content="String(part.think || '')"
          class="reasoning-text markdown-content"
          :typewriter="false"
          :is-dark="isDark"
        />

        <div v-else-if="part.type === 'tool_call'" class="reasoning-tool-call-block">
          <template
            v-for="tool in part.tool_calls || []"
            :key="String(tool.id || tool.name || partIndex)"
          >
            <ToolCallItem v-if="isIPythonToolCall(tool)" :is-dark="isDark">
              <template #label>
                <v-icon size="16">mdi-code-json</v-icon>
                <span>{{ tool.name || "python" }}</span>
                <span class="tool-call-inline-status">
                  {{ toolCallStatusText(tool) }}
                </span>
              </template>
              <template #details>
                <IPythonToolBlock
                  :tool-call="normalizeToolCall(tool)"
                  :is-dark="isDark"
                  :show-header="false"
                  :force-expanded="true"
                />
              </template>
            </ToolCallItem>
            <ToolCallCard
              v-else
              :tool-call="normalizeToolCall(tool)"
              :is-dark="isDark"
            />
          </template>
        </div>
      </template>
    </div>

    <transition :name="previewTransitionName" mode="out-in">
      <div v-if="showStreamingPreview" :key="previewKey" class="reasoning-preview">
        {{ previewText }}
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { MarkdownRender } from "markstream-vue";
import IPythonToolBlock from "@/components/chat/message_list_comps/IPythonToolBlock.vue";
import ToolCallCard from "@/components/chat/message_list_comps/ToolCallCard.vue";
import ToolCallItem from "@/components/chat/message_list_comps/ToolCallItem.vue";
import type { MessagePart } from "@/composables/useMessages";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  parts?: MessagePart[];
  reasoning?: string;
  isDark?: boolean;
  initialExpanded?: boolean;
  isStreaming?: boolean;
  hasNonReasoningContent?: boolean;
}>();

const { tm } = useModuleI18n("features/chat");
const isExpanded = ref(Boolean(props.initialExpanded));
const previewText = ref("");
const previewKey = ref(0);
let previewTimer: ReturnType<typeof setInterval> | null = null;
let previewStartTimer: ReturnType<typeof setTimeout> | null = null;

const renderParts = computed<MessagePart[]>(() => {
  if (props.parts?.length) return props.parts;
  if (props.reasoning) {
    return [{ type: "think", think: props.reasoning }];
  }
  return [];
});

const thinkingText = computed(() =>
  renderParts.value
    .filter((part) => part.type === "think")
    .map((part) => String(part.think || ""))
    .join(""),
);

const showStreamingPreview = computed(
  () =>
    props.isStreaming &&
    !isExpanded.value &&
    !props.hasNonReasoningContent &&
    previewText.value,
);

const previewTransitionName = computed(() =>
  props.hasNonReasoningContent
    ? "reasoning-preview-collapse"
    : "reasoning-preview-fade",
);

function toggleExpanded() {
  isExpanded.value = !isExpanded.value;
}

function reasoningPartKey(part: MessagePart, index: number) {
  if (part.type === "tool_call") {
    const tool = Array.isArray(part.tool_calls) ? part.tool_calls[0] : null;
    return `${part.type}-${tool?.id || tool?.name || index}`;
  }
  return `${part.type}-${index}`;
}

function latestReasoningPreview() {
  const lines = thinkingText.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.slice(-3).join("\n");
}

function updatePreviewLine() {
  const nextText = latestReasoningPreview();
  if (!nextText || nextText === previewText.value) return;
  previewText.value = nextText;
  previewKey.value += 1;
}

function stopPreviewTimer() {
  if (!previewTimer) return;
  clearInterval(previewTimer);
  previewTimer = null;
}

function stopPreviewStartTimer() {
  if (!previewStartTimer) return;
  clearTimeout(previewStartTimer);
  previewStartTimer = null;
}

function startPreviewTimer() {
  updatePreviewLine();
  if (!previewTimer) {
    previewTimer = setInterval(updatePreviewLine, 2000);
  }
}

function syncPreviewTimer() {
  if (props.isStreaming && !isExpanded.value && !props.hasNonReasoningContent) {
    if (!previewTimer && !previewStartTimer) {
      previewStartTimer = setTimeout(() => {
        previewStartTimer = null;
        if (props.isStreaming && !isExpanded.value && !props.hasNonReasoningContent) {
          startPreviewTimer();
        }
      }, 2000);
    }
    return;
  }

  stopPreviewStartTimer();
  stopPreviewTimer();
  if (!props.isStreaming) {
    previewText.value = "";
  }
}

function normalizeToolCall(tool: Record<string, unknown>) {
  const normalized = { ...tool };
  normalized.args = parseJsonSafe(normalized.args ?? normalized.arguments ?? {});
  normalized.result = parseJsonSafe(normalized.result);
  normalized.ts = normalized.ts ?? Date.now() / 1000;
  if (normalized.result && typeof normalized.result === "object") {
    normalized.result = JSON.stringify(normalized.result, null, 2);
  }
  return normalized;
}

function isIPythonToolCall(tool: Record<string, unknown>) {
  const name = String(tool.name || "").toLowerCase();
  return name.includes("python") || name.includes("ipython");
}

function toolCallStatusText(tool: Record<string, unknown>) {
  if (tool.finished_ts) return tm("toolStatus.done");
  return tm("toolStatus.running");
}

function parseJsonSafe(value: unknown) {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

watch(
  () => [props.isStreaming, isExpanded.value, props.hasNonReasoningContent, thinkingText.value],
  syncPreviewTimer,
  {
    immediate: true,
  },
);

onBeforeUnmount(() => {
  stopPreviewStartTimer();
  stopPreviewTimer();
});
</script>

<style scoped>
.reasoning-block {
  margin: 6px 0;
  max-width: 100%;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: inherit;
  line-height: inherit;
}

.reasoning-header {
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

.reasoning-header:hover {
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.reasoning-icon {
  color: currentcolor;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.reasoning-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reasoning-content {
  margin-top: 8px;
  padding: 0;
  color: rgba(var(--v-theme-on-surface), 0.7);
  animation: fadeIn 0.2s ease-in-out;
  font-style: italic;
}

.reasoning-tool-call-block {
  margin-top: 8px;
  font-style: normal;
}

.reasoning-preview {
  max-width: 100%;
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.52);
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  white-space: pre-line;
  font: inherit;
  font-style: italic;
}

.reasoning-text {
  font-size: inherit;
  line-height: inherit;
  color: inherit;
}

.tool-call-inline-status {
  margin-left: 4px;
  color: rgba(var(--v-theme-on-surface), 0.48);
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

.rotate-90 {
  transform: rotate(90deg);
}

.reasoning-preview-fade-enter-active {
  transition: opacity 0.25s ease;
}

.reasoning-preview-fade-leave-active {
  transition: opacity 0.25s ease;
}

.reasoning-preview-fade-enter-from,
.reasoning-preview-fade-leave-to {
  opacity: 0;
}

.reasoning-preview-collapse-enter-active {
  transition: opacity 0.25s ease;
}

.reasoning-preview-collapse-leave-active {
  transition:
    opacity 0.18s ease,
    max-height 0.18s ease,
    margin-top 0.18s ease;
  overflow: hidden;
}

.reasoning-preview-collapse-enter-from {
  opacity: 0;
}

.reasoning-preview-collapse-leave-from {
  opacity: 1;
  max-height: 6.5em;
  margin-top: 4px;
}

.reasoning-preview-collapse-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
}
</style>
