<template>
  <div v-if="timelineEntries.length" class="reasoning-timeline">
    <div
      v-for="entry in timelineEntries"
      :key="entry.key"
      class="reasoning-timeline-item"
    >
      <div class="reasoning-step">
        <div v-if="entry.kind === 'think'" class="thought-item">
          <MessageCircleMore
            :size="16"
            class="thought-icon"
            aria-hidden="true"
          />
          <div
            class="thought-copy"
            :class="{ 'is-expanded': expandedThoughts[entry.key] }"
          >
            <button
              type="button"
              class="thought-first-line-toggle"
              :aria-label="entry.preview"
              :aria-expanded="Boolean(expandedThoughts[entry.key])"
              @click="
                expandedThoughts[entry.key] = !expandedThoughts[entry.key]
              "
            ></button>
            <div class="thought-clip">
              <MarkdownRender
                :content="entry.think"
                class="chat-markdown reasoning-text markdown-content"
                :aria-hidden="!expandedThoughts[entry.key]"
                :inert="expandedThoughts[entry.key] ? undefined : ''"
                :final="!isStreaming"
                :smooth-streaming="isStreaming ? 'auto' : false"
                :fade="false"
                :typewriter="false"
                :is-dark="isDark"
                :node-virtual="false"
                :max-live-nodes="
                  isStreaming ? MARKDOWN_RENDER_MAX_LIVE_NODES : 0
                "
                :style="{
                  ...CHAT_MARKDOWN_HEADING_STYLE,
                  '--ms-text-body': '13.5px',
                  '--ms-leading-body': '22px',
                }"
              />
            </div>
          </div>
          <button
            type="button"
            class="thought-toggle"
            :aria-label="tm('reasoning.think')"
            :aria-expanded="Boolean(expandedThoughts[entry.key])"
            @click="expandedThoughts[entry.key] = !expandedThoughts[entry.key]"
          >
            <ChevronRight
              :size="22"
              class="process-chevron"
              :class="{ 'is-expanded': expandedThoughts[entry.key] }"
              aria-hidden="true"
            />
          </button>
        </div>

        <div v-else-if="entry.tool" class="reasoning-tool-call-block">
          <ToolCallItem v-if="isIPythonToolCall(entry.tool)" :is-dark="isDark">
            <template #label>
              <CodeXml :size="16" aria-hidden="true" />
              <span>{{ entry.tool.name || "python" }}</span>
              <span class="tool-call-inline-status">
                {{ toolCallStatusText(entry.tool) }}
              </span>
            </template>
            <template #details>
              <IPythonToolBlock
                :tool-call="entry.tool"
                :is-dark="isDark"
                :show-header="false"
                :force-expanded="true"
              />
            </template>
          </ToolCallItem>
          <ToolCallCard v-else :tool-call="entry.tool" :is-dark="isDark" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive } from "vue";
import { MessageCircleMore, ChevronRight, CodeXml } from "@lucide/vue";
import "@/components/chat/message_list_comps/processCollapse.css";
import { MarkdownRender } from "markstream-vue";
import {
  CHAT_MARKDOWN_HEADING_STYLE,
  MARKDOWN_RENDER_MAX_LIVE_NODES,
} from "@/components/chat/markdownRenderConfig";
import IPythonToolBlock from "@/components/chat/message_list_comps/IPythonToolBlock.vue";
import ToolCallCard from "@/components/chat/message_list_comps/ToolCallCard.vue";
import ToolCallItem from "@/components/chat/message_list_comps/ToolCallItem.vue";
import type { MessagePart } from "@/composables/useMessages";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  parts?: MessagePart[];
  reasoning?: string;
  isDark?: boolean;
  isStreaming?: boolean;
}>();

const { tm } = useModuleI18n("features/chat");
const expandedThoughts = reactive<Record<string, boolean>>({});

type NormalizedToolCall = Record<string, unknown>;

type TimelineEntry =
  | {
      key: string;
      kind: "think";
      preview: string;
      think: string;
    }
  | {
      key: string;
      kind: "tool_call";
      tool: NormalizedToolCall;
    };

const renderParts = computed<MessagePart[]>(() => {
  if (props.parts?.length) return props.parts;
  if (props.reasoning) {
    return [{ type: "think", think: props.reasoning }];
  }
  return [];
});

const timelineEntries = computed<TimelineEntry[]>(() => {
  const entries: TimelineEntry[] = [];

  renderParts.value.forEach((part, partIndex) => {
    if (part.type === "think") {
      const think = String(part.think || "");
      if (!think.trim()) return;
      entries.push({
        key: `think-${partIndex}`,
        kind: "think",
        preview: think.trim().split(/\r?\n/, 1)[0],
        think,
      });
      return;
    }

    if (part.type !== "tool_call" || !Array.isArray(part.tool_calls)) return;

    part.tool_calls.forEach((tool, toolIndex) => {
      const normalizedTool = normalizeToolCall(tool);
      entries.push({
        key: `tool-${String(
          tool.id || tool.name || `${partIndex}-${toolIndex}`,
        )}`,
        kind: "tool_call",
        tool: normalizedTool,
      });
    });
  });

  return entries;
});

function normalizeToolCall(tool: Record<string, unknown>) {
  const normalized = { ...tool };
  normalized.args = parseJsonSafe(
    normalized.args ?? normalized.arguments ?? {},
  );
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
  // The turn ended before this call returned (see ToolCallCard).
  if (tool.phase === "unknown") return tm("toolStatus.interrupted");
  if (tool.finished_ts) return tm("toolStatus.done");
  // Waiting for the user to answer a tool approval card.
  if (tool.phase === "awaiting_approval") {
    return tm("toolStatus.awaitingApproval");
  }
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
</script>

<style scoped>
.reasoning-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-top: 0;
}

.reasoning-timeline-item {
  padding-bottom: 2px;
}

.reasoning-timeline-item:last-child {
  padding-bottom: 0;
}

.reasoning-step {
  min-width: 0;
  font-size: 14.5px;
  line-height: 1.62;
}

.thought-item {
  display: grid;
  width: fit-content;
  max-width: 100%;
  grid-template-columns: 16px minmax(0, 1fr) 22px;
  align-items: start;
  column-gap: 8px;
  margin: 2px 0;
  font-size: 13.5px;
  line-height: 1.56;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.thought-icon {
  margin-top: 3px;
}

.thought-copy {
  position: relative;
  min-width: 0;
  display: grid;
  grid-template-rows: minmax(22px, 0fr);
  transition: grid-template-rows 360ms cubic-bezier(0.22, 1, 0.36, 1);
}

.thought-copy.is-expanded {
  grid-template-rows: minmax(22px, 1fr);
}

.thought-first-line-toggle {
  position: absolute;
  inset: 0 0 auto;
  z-index: 1;
  height: 22px;
  border: 0;
  padding: 0;
  background: transparent;
  cursor: pointer;
}

.thought-clip {
  min-height: 0;
  overflow: hidden;
}

.thought-toggle {
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.thought-toggle {
  display: flex;
}

.thought-first-line-toggle:focus-visible,
.thought-toggle:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.reasoning-tool-call-block {
  font-style: normal;
}

.reasoning-text {
  font-size: inherit;
  line-height: inherit;
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-style: normal;
}

/* Remove Markdown's leading paragraph margin so the first line centers on the icons. */
.reasoning-text :deep(.node-slot:first-child > .node-content > :first-child) {
  margin-top: 0;
}

.reasoning-step :deep(.tool-call-card) {
  margin: 2px 0;
}

.reasoning-step :deep(.tool-call-card),
.reasoning-step :deep(.tool-call-item),
.reasoning-step :deep(.ipython-tool-block) {
  font-size: 13.5px;
  line-height: 1.56;
}

.reasoning-step :deep(.tool-call-card .detail-label) {
  font-size: 11.5px;
}

.reasoning-step :deep(.tool-call-card .detail-value),
.reasoning-step :deep(.ipython-tool-block .code-highlighted),
.reasoning-step :deep(.ipython-tool-block .code-fallback),
.reasoning-step :deep(.ipython-tool-block .result-label),
.reasoning-step :deep(.ipython-tool-block .result-content) {
  font-size: 12.5px;
}

.tool-call-inline-status {
  margin-left: 4px;
  color: rgba(var(--v-theme-on-surface), 0.48);
}
/* Align details with the label text to the right of each leading icon. */
.reasoning-step :deep(.tool-call-details),
.reasoning-step :deep(.tool-call-inline-details) {
  padding-left: 24px;
  padding-right: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}
.reasoning-step :deep(.tool-call-inline-details) {
  padding-left: 24px;
}
@media (prefers-reduced-motion: reduce) {
  .thought-copy {
    position: relative;
    transition: none;
  }
}
</style>
