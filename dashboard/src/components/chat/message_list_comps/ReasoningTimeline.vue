<template>
  <div v-if="timelineEntries.length" class="reasoning-timeline">
    <div
      v-for="(entry, entryIndex) in timelineEntries"
      :key="entry.key"
      class="reasoning-timeline-item"
    >
      <div class="reasoning-timeline-rail" aria-hidden="true">
        <span class="reasoning-timeline-dot"></span>
        <span
          v-if="entryIndex < timelineEntries.length - 1"
          class="reasoning-timeline-line"
        ></span>
      </div>

      <div class="reasoning-step">
        <div class="reasoning-step-meta">
          <span class="reasoning-step-title">{{ entry.title }}</span>
        </div>

        <MarkdownRender
          v-if="entry.kind === 'think'"
          :content="entry.think || ''"
          class="reasoning-text markdown-content"
          :typewriter="false"
          :is-dark="isDark"
        />

        <div v-else-if="entry.tool" class="reasoning-tool-call-block">
          <ToolCallItem v-if="isIPythonToolCall(entry.tool)" :is-dark="isDark">
            <template #label>
              <v-icon size="16">mdi-code-json</v-icon>
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
          <ToolCallCard
            v-else
            :tool-call="entry.tool"
            :is-dark="isDark"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
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
}>();

const { tm } = useModuleI18n("features/chat");

type NormalizedToolCall = Record<string, unknown>;

type TimelineEntry =
  | {
      key: string;
      kind: "think";
      title: string;
      think: string;
    }
  | {
      key: string;
      kind: "tool_call";
      title: string;
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
        title: tm("reasoning.think"),
        think,
      });
      return;
    }

    if (part.type !== "tool_call" || !Array.isArray(part.tool_calls)) return;

    part.tool_calls.forEach((tool, toolIndex) => {
      const normalizedTool = normalizeToolCall(tool);
      entries.push({
        key: `tool-${String(tool.id || tool.name || `${partIndex}-${toolIndex}`)}`,
        kind: "tool_call",
        title: tm("reasoning.toolUsed"),
        tool: normalizedTool,
      });
    });
  });

  return entries;
});

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
</script>

<style scoped>
.reasoning-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-top: 4px;
}

.reasoning-timeline-item {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr);
  column-gap: 10px;
  align-items: flex-start;
  padding-bottom: 10px;
}

.reasoning-timeline-item:last-child {
  padding-bottom: 0;
}

.reasoning-timeline-rail {
  position: relative;
  display: flex;
  justify-content: center;
  min-height: 100%;
  padding-top: 6px;
}

.reasoning-timeline-dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.18);
}

.reasoning-timeline-line {
  position: absolute;
  top: 15px;
  bottom: -10px;
  left: 50%;
  width: 1px;
  transform: translateX(-50%);
  background: rgba(var(--v-theme-on-surface), 0.12);
}

.reasoning-step {
  min-width: 0;
  font-size: 14.5px;
  line-height: 1.62;
}

.reasoning-step-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 12px;
  line-height: 1.35;
}

.reasoning-step-title {
  color: rgba(var(--v-theme-on-surface), 0.76);
  font-weight: 600;
  font-size: 12px;
}

.reasoning-tool-call-block {
  margin-top: 4px;
  font-style: normal;
}

.reasoning-text {
  font-size: inherit;
  line-height: inherit;
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-style: normal;
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
</style>
