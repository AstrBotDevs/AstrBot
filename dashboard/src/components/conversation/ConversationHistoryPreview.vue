<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ChevronRight, Minus, Plus } from "@lucide/vue";
import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{ messages: unknown[] }>();
const { tm } = useModuleI18n("features/conversation");
const markdownEnabled = ref(true);
const fontSize = ref(13);
const settingsKey = "conversation.preview.reading";

try {
  const saved = JSON.parse(localStorage.getItem(settingsKey) || "null");
  if (typeof saved?.markdown === "boolean")
    markdownEnabled.value = saved.markdown;
  if (
    Number.isInteger(saved?.fontSize) &&
    saved.fontSize >= 12 &&
    saved.fontSize <= 18
  ) {
    fontSize.value = saved.fontSize;
  }
} catch {
  // Reading preferences are optional when storage is unavailable or invalid.
}

watch([markdownEnabled, fontSize], () => {
  try {
    localStorage.setItem(
      settingsKey,
      JSON.stringify({
        markdown: markdownEnabled.value,
        fontSize: fontSize.value,
      }),
    );
  } catch {
    // Keep the current preferences usable when storage is unavailable.
  }
});

const markdown = new MarkdownIt({ html: false, breaks: true, linkify: true });
const knownRoles = [
  "user",
  "assistant",
  "system",
  "developer",
  "tool",
  "function",
];
type PreviewPart = {
  kind: "text" | "image" | "data";
  text: string;
  html?: string;
  label?: string;
};

const records = computed(() =>
  props.messages
    .filter(
      (entry) =>
        !entry ||
        typeof entry !== "object" ||
        !("role" in entry) ||
        entry.role !== "_checkpoint",
    )
    .map((entry) => {
      const message =
        entry && typeof entry === "object" && !Array.isArray(entry)
          ? (entry as Record<string, unknown>)
          : { content: entry };
      const role = typeof message.role === "string" ? message.role : "unknown";
      const parts: PreviewPart[] = [];
      const content = Array.isArray(message.content)
        ? message.content
        : [message.content];

      // Preserve unsupported content as data instead of silently dropping it.
      for (const item of content) {
        if (item == null) continue;
        if (
          typeof item === "string" ||
          (item?.type === "text" && typeof item.text === "string")
        ) {
          const text = typeof item === "string" ? item : item.text;
          if (text.length) {
            parts.push({
              kind: "text",
              text,
              html: markdownEnabled.value
                ? DOMPurify.sanitize(markdown.render(text), {
                    USE_PROFILES: { html: true },
                  })
                : undefined,
            });
          }
        } else if (
          item?.type === "image_url" &&
          typeof item.image_url?.url === "string" &&
          /^(https?:\/\/|data:image\/(png|jpeg|jpg|gif|webp);base64,)/i.test(
            item.image_url.url,
          )
        ) {
          parts.push({ kind: "image", text: item.image_url.url });
        } else {
          parts.push({ kind: "data", text: JSON.stringify(item, null, 2) });
        }
      }

      if (
        typeof message.reasoning_content === "string" &&
        message.reasoning_content
      ) {
        parts.push({
          kind: "data",
          label: tm("workspace.preview.reasoning"),
          text: message.reasoning_content,
        });
      }

      if (Array.isArray(message.tool_calls)) {
        for (const call of message.tool_calls) {
          let data = call;
          const fn = call?.function;
          if (fn && typeof fn.arguments === "string") {
            try {
              data = {
                ...call,
                function: { ...fn, arguments: JSON.parse(fn.arguments) },
              };
            } catch {
              // Incomplete or non-JSON arguments remain visible exactly as recorded.
            }
          }
          parts.push({
            kind: "data",
            label: `${tm("workspace.preview.toolCall")}${
              typeof fn?.name === "string" ? ` · ${fn.name}` : ""
            }`,
            text: JSON.stringify(data, null, 2),
          });
        }
      }

      if (
        !parts.length &&
        !Object.prototype.hasOwnProperty.call(message, "content")
      ) {
        parts.push({ kind: "data", text: JSON.stringify(entry, null, 2) });
      }

      return {
        role,
        label: knownRoles.includes(role)
          ? tm(`workspace.preview.roles.${role}`)
          : role === "unknown"
          ? tm("status.unknown")
          : role,
        name: typeof message.name === "string" ? message.name : "",
        toolCallId:
          typeof message.tool_call_id === "string" ? message.tool_call_id : "",
        parts,
      };
    }),
);
</script>

<template>
  <div
    class="history-preview"
    :style="{ '--preview-font-size': `${fontSize}px` }"
  >
    <div class="reading-toolbar">
      <span class="record-count">{{
        tm("workspace.preview.messageCount", { count: records.length })
      }}</span>
      <div class="reading-controls">
        <button
          type="button"
          class="markdown-toggle"
          :class="{ 'markdown-toggle--active': markdownEnabled }"
          :aria-pressed="markdownEnabled"
          :aria-label="tm('workspace.preview.markdown')"
          :title="tm('workspace.preview.markdown')"
          @click="markdownEnabled = !markdownEnabled"
        >
          <span class="toggle-indicator" aria-hidden="true" />
          Markdown
        </button>
        <div
          class="font-controls"
          role="group"
          :aria-label="tm('workspace.preview.fontSize')"
        >
          <button
            type="button"
            :disabled="fontSize <= 12"
            :aria-label="tm('workspace.preview.smallerText')"
            :title="tm('workspace.preview.smallerText')"
            @click="fontSize--"
          >
            <Minus :size="13" aria-hidden="true" />
          </button>
          <output
            :aria-label="tm('workspace.preview.fontSize')"
            aria-live="polite"
            >{{ fontSize }}px</output
          >
          <button
            type="button"
            :disabled="fontSize >= 18"
            :aria-label="tm('workspace.preview.largerText')"
            :title="tm('workspace.preview.largerText')"
            @click="fontSize++"
          >
            <Plus :size="13" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>

    <div
      class="history-records"
      tabindex="0"
      role="region"
      :aria-label="tm('workspace.preview.title')"
    >
      <div v-if="!records.length" class="history-empty">
        {{ tm("workspace.preview.empty") }}
      </div>
      <article
        v-for="(record, index) in records"
        :key="index"
        class="history-record"
        :class="{ 'history-record--user': record.role === 'user' }"
      >
        <header class="record-header">
          <span class="record-index">{{
            String(index + 1).padStart(2, "0")
          }}</span>
          <span
            class="record-role"
            :class="{ 'record-role--assistant': record.role === 'assistant' }"
            >{{ record.label }}</span
          >
          <span v-if="record.name" class="record-name">{{ record.name }}</span>
          <span
            v-if="record.toolCallId"
            class="record-call-id"
            :title="record.toolCallId"
            >{{ record.toolCallId }}</span
          >
        </header>
        <div class="record-body">
          <span v-if="!record.parts.length" class="empty-content">{{
            tm("status.emptyContent")
          }}</span>
          <template v-for="(part, partIndex) in record.parts" :key="partIndex">
            <div
              v-if="part.kind === 'text' && markdownEnabled"
              class="record-markdown"
              v-html="part.html"
            />
            <pre v-else-if="part.kind === 'text'" class="record-text">{{
              part.text
            }}</pre>
            <img
              v-else-if="part.kind === 'image'"
              class="record-image"
              :src="part.text"
              :alt="tm('workspace.preview.image')"
              loading="lazy"
              referrerpolicy="no-referrer"
            />
            <details v-else class="record-data">
              <summary>
                <ChevronRight :size="13" aria-hidden="true" />{{
                  part.label || tm("workspace.preview.structuredData")
                }}
              </summary>
              <pre>{{ part.text }}</pre>
            </details>
          </template>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.history-preview {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  color: rgb(var(--v-theme-on-surface));
}

.reading-toolbar,
.reading-controls,
.font-controls,
.markdown-toggle,
.record-header {
  display: flex;
  align-items: center;
}

.reading-toolbar {
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 16px;
  border-block: 1px solid rgba(var(--v-theme-on-surface), 0.07);
  font-size: 11px;
}

.record-count,
.record-index,
.record-call-id,
.empty-content,
.history-empty {
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.reading-controls {
  gap: 10px;
}

.markdown-toggle {
  gap: 6px;
  min-height: 30px;
  padding: 0 7px;
  border-radius: 6px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.markdown-toggle--active {
  color: rgb(var(--v-theme-primary));
}

.toggle-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.4;
}

.markdown-toggle--active .toggle-indicator {
  opacity: 1;
}

.font-controls {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 6px;
  overflow: hidden;
}

.font-controls button {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
}

.font-controls button:disabled {
  opacity: 0.3;
  cursor: default;
}
.font-controls output {
  min-width: 38px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.reading-controls button:hover:not(:disabled) {
  background: rgba(var(--v-theme-on-surface), 0.05);
}
.reading-controls button:focus-visible,
.record-data summary:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.history-records {
  flex: 1;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.history-empty {
  padding: 48px 16px;
  text-align: center;
  font-size: 13px;
}
.history-record {
  padding: 16px 18px;
}
.history-record--user {
  background: rgba(var(--v-theme-on-surface), 0.055);
}
.history-record + .history-record {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.07);
}
.record-header {
  gap: 8px;
  margin-bottom: 9px;
  font-size: 11px;
  min-width: 0;
}
.record-index {
  font-variant-numeric: tabular-nums;
  font-size: 10px;
}
.record-role {
  font-weight: 650;
  flex-shrink: 0;
}
.record-role--assistant {
  color: rgb(var(--v-theme-primary));
}
.record-name,
.record-call-id {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.record-call-id {
  margin-left: auto;
  font-family: monospace;
  font-size: 10px;
}
.record-body {
  font-size: var(--preview-font-size);
  line-height: 1.65;
  overflow-wrap: anywhere;
}
.record-body > * + * {
  margin-top: 10px;
}
.record-text {
  white-space: pre-wrap;
  font: inherit;
  margin: 0;
}
.record-image,
.record-markdown :deep(img) {
  display: inline-block;
  max-width: min(100%, 144px);
  max-height: 104px;
  margin: 4px 6px 4px 0;
  object-fit: contain;
  vertical-align: top;
  border-radius: 6px;
}

.record-data {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.09);
  border-radius: 7px;
  overflow: hidden;
}

.record-data summary {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 9px;
  background: rgba(var(--v-theme-on-surface), 0.025);
  cursor: pointer;
  font-size: 0.92em;
  list-style: none;
}

.record-data summary::-webkit-details-marker {
  display: none;
}
.record-data summary svg {
  flex-shrink: 0;
  transition: transform 0.15s;
}
.record-data[open] summary svg {
  transform: rotate(90deg);
}
.record-data pre {
  margin: 0;
  padding: 10px;
  overflow: auto;
  max-height: 360px;
  white-space: pre-wrap;
}
.record-data pre,
.record-markdown :deep(pre),
.record-markdown :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 0.92em;
}
.record-markdown {
  overflow: hidden;
}
.record-markdown :deep(p) {
  margin: 0 0 0.7em;
}
.record-markdown :deep(> :last-child) {
  margin-bottom: 0;
}
.record-markdown :deep(h1),
.record-markdown :deep(h2),
.record-markdown :deep(h3),
.record-markdown :deep(h4),
.record-markdown :deep(h5),
.record-markdown :deep(h6) {
  font-size: 1.08em;
  font-weight: 650;
  line-height: 1.5;
  margin: 1em 0 0.5em;
}
.record-markdown :deep(> :first-child) {
  margin-top: 0;
}
.record-markdown :deep(ul),
.record-markdown :deep(ol) {
  padding-left: 1.6em;
  margin-bottom: 0.7em;
}
.record-markdown :deep(li + li) {
  margin-top: 0.2em;
}
.record-markdown :deep(pre) {
  overflow-x: auto;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.045);
  margin-bottom: 0.7em;
}
.record-markdown :deep(code) {
  padding: 0.1em 0.3em;
  border-radius: 3px;
  background: rgba(var(--v-theme-on-surface), 0.055);
}
.record-markdown :deep(pre code) {
  padding: 0;
  background: none;
  font-size: inherit;
}
.record-markdown :deep(blockquote) {
  margin: 0 0 0.7em;
  padding: 2px 12px;
  border-left: 3px solid rgba(var(--v-theme-on-surface), 0.18);
  color: rgba(var(--v-theme-on-surface), 0.68);
}
.record-markdown :deep(table) {
  display: block;
  overflow-x: auto;
  border-collapse: collapse;
  margin-bottom: 0.7em;
}
.record-markdown :deep(th),
.record-markdown :deep(td) {
  padding: 5px 9px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.record-markdown :deep(th) {
  background: rgba(var(--v-theme-on-surface), 0.04);
  font-weight: 600;
}
.record-markdown :deep(a) {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
}
.record-markdown :deep(hr) {
  border: 0;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  margin: 1em 0;
}

@media (max-width: 600px) {
  .history-record {
    padding: 14px;
  }
  .reading-toolbar {
    padding-inline: 12px;
  }
}
</style>
