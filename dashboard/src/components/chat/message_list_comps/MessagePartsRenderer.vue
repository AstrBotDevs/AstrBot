<template>
  <template
    v-for="(renderPart, renderIndex) in getRenderParts(parts)"
    :key="renderPart.key"
  >
    <!-- Grouped Tool Calls (consecutive tool_call parts) -->
    <div v-if="renderPart.type === 'tool_group'" class="tool-call-compact">
      <transition-group name="tool-call-item" tag="div" class="tool-call-items">
        <ToolCallItem
          v-for="(toolCall, tcIndex) in renderPart.toolCalls"
          :key="toolCall.id"
          :is-dark="isDark"
        >
          <template #label="{ expanded }">
            <v-icon
              v-if="
                toolCall.name?.includes('web_search') ||
                toolCall.name?.includes('tavily')
              "
              size="x-small"
            >
              mdi-web
            </v-icon>
            <v-icon
              v-else-if="toolCall.name === 'astrbot_execute_shell'"
              size="x-small"
            >
              mdi-console-line
            </v-icon>
            <v-icon v-else size="x-small"> mdi-wrench </v-icon>
            {{ tm("actions.toolCallUsed", { name: toolCall.name ?? "" }) }}
            <span style="opacity: 0.6">{{
              toolCall.finished_ts
                ? formatDuration(
                    (toolCall.finished_ts ?? 0) - (toolCall.ts ?? 0),
                  )
                : getElapsedTime(toolCall.ts ?? 0)
            }}</span>
            <v-icon
              size="x-small"
              class="tool-call-chevron"
              :class="{ rotated: expanded }"
            >
              mdi-chevron-right
            </v-icon>
          </template>
          <template #details>
            <div class="tool-call-detail-row">
              <span class="detail-label">ID:</span>
              <code class="detail-value">{{ toolCall.id }}</code>
            </div>
            <div class="tool-call-detail-row">
              <span class="detail-label">Args:</span>
              <pre class="detail-value detail-json">{{
                formatToolArgs(toolCall.args)
              }}</pre>
            </div>
            <div v-if="toolCall.result" class="tool-call-detail-row">
              <span class="detail-label">Result:</span>
              <pre class="detail-value detail-json detail-result">{{
                formatToolResult(toolCall.result)
              }}</pre>
            </div>
          </template>
        </ToolCallItem>
      </transition-group>
    </div>

    <!-- Text (Markdown) -->
    <div
      v-else-if="
        renderPart.type === 'part' &&
        renderPart.part?.type === 'plain' &&
        renderPart.part?.text?.trim()
      "
      :key="`${renderPart.key}-${isDark ? 'dark' : 'light'}`"
      class="markdown-content"
    >
      <MarkdownRender
        custom-id="message-list"
        :custom-html-tags="['ref']"
        :content="normalizeMarkdownContent(renderPart.part?.text)"
        :typewriter="false"
        :is-dark="isDark"
        :monaco-options="{ theme: isDark ? 'vs-dark' : 'vs-light' }"
      />
    </div>

    <!-- Image -->
    <div
      v-else-if="
        renderPart.type === 'part' &&
        renderPart.part?.type === 'image' &&
        renderPart.part?.embedded_url
      "
      class="embedded-images"
    >
      <div class="embedded-image">
        <img
          :src="renderPart.part?.embedded_url"
          class="bot-embedded-image"
          @click="emitOpenImage(renderPart.part?.embedded_url)"
        />
      </div>
    </div>

    <!-- Audio -->
    <div
      v-else-if="
        renderPart.type === 'part' &&
        renderPart.part?.type === 'record' &&
        renderPart.part?.embedded_url
      "
      class="embedded-audio"
    >
      <audio controls class="audio-player">
        <source :src="renderPart.part?.embedded_url" type="audio/wav" />
        {{ t("messages.errors.browser.audioNotSupported") }}
      </audio>
    </div>

    <!-- Files -->
    <div
      v-else-if="
        renderPart.type === 'part' &&
        renderPart.part?.type === 'file' &&
        renderPart.part?.embedded_file
      "
      class="embedded-files"
    >
      <div class="embedded-file">
        <a
          v-if="renderPart.part?.embedded_file?.url"
          :href="renderPart.part?.embedded_file?.url"
          :download="renderPart.part?.embedded_file?.filename"
          class="file-link"
          :class="{ 'is-dark': isDark }"
          :style="
            isDark
              ? {
                  backgroundColor: 'rgba(255, 255, 255, 0.05)',
                  borderColor: 'rgba(255, 255, 255, 0.1)',
                  color: 'var(--v-theme-secondary)',
                }
              : {}
          "
        >
          <v-icon
            size="small"
            class="file-icon"
            :style="isDark ? { color: 'var(--v-theme-secondary)' } : {}"
            >mdi-file-document-outline</v-icon
          >
          <span class="file-name">{{
            renderPart.part?.embedded_file?.filename
          }}</span>
        </a>
        <a
          v-else
          class="file-link file-link-download"
          :class="{ 'is-dark': isDark }"
          :style="
            isDark
              ? {
                  backgroundColor: 'rgba(255, 255, 255, 0.05)',
                  borderColor: 'rgba(255, 255, 255, 0.1)',
                  color: 'var(--v-theme-secondary)',
                }
              : {}
          "
          @click="emitDownloadFile(renderPart.part?.embedded_file)"
        >
          <v-icon
            size="small"
            class="file-icon"
            :style="isDark ? { color: 'var(--v-theme-secondary)' } : {}"
            >mdi-file-document-outline</v-icon
          >
          <span class="file-name">{{
            renderPart.part?.embedded_file?.filename
          }}</span>
          <v-icon
            v-if="isFileDownloading(renderPart)"
            size="small"
            class="download-icon"
            >mdi-loading mdi-spin</v-icon
          >
          <v-icon v-else size="small" class="download-icon"
            >mdi-download</v-icon
          >
        </a>
      </div>
    </div>
  </template>
</template>

<script setup lang="ts">
import type { PropType } from "vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { MarkdownRender } from "markstream-vue";
import IPythonToolBlock from "./IPythonToolBlock.vue";
import ToolCallItem from "./ToolCallItem.vue";
import type { MessagePart } from "@/composables/useMessages";

const props = defineProps({
  parts: {
    type: Array as PropType<MessagePart[]>,
    required: true,
  },
  isDark: {
    type: Boolean,
    default: false,
  },
  currentTime: {
    type: Number,
    default: 0,
  },
  downloadingFiles: {
    type: Object as PropType<Set<string>>,
    default: () => new Set<string>(),
  },
});

const emit = defineEmits(["open-image-preview", "download-file"]);
const { t } = useI18n();
const { tm } = useModuleI18n("features/chat");

const emitOpenImage = (url: string): void => {
  emit("open-image-preview", url);
};

const emitDownloadFile = (file: unknown): void => {
  emit("download-file", file);
};

const isMarkdownCodeFence = (text: string): boolean =>
  /^(```|~~~)/.test(text.trim());

const looksLikeStandaloneHtml = (text: string): boolean => {
  const normalized = text.trim();
  if (!normalized) return false;
  if (!/(<!doctype\s+html|<html\b|<head\b|<body\b)/i.test(normalized))
    return false;
  return /(<\/html>|<\/body>|<\/head>|<form\b|<input\b|<button\b)/i.test(
    normalized,
  );
};

const normalizeMarkdownContent = (text: string): string => {
  if (typeof text !== "string") return text;
  if (isMarkdownCodeFence(text) || !looksLikeStandaloneHtml(text)) return text;
  return `\`\`\`\`html\n${text}\n\`\`\`\``;
};

const formatDuration = (seconds: number): string => {
  if (seconds < 1) {
    return `${Math.round(seconds * 1000)}ms`;
  }
  if (seconds < 60) {
    return `${seconds.toFixed(1)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${minutes}m ${secs}s`;
};

const getElapsedTime = (startTs: number): string => {
  const elapsed = props.currentTime - startTs;
  return formatDuration(elapsed);
};

const formatToolResult = (result: unknown): string => {
  if (!result) return "";
  if (typeof result === "string") {
    try {
      const parsed = JSON.parse(result);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return result;
    }
  }
  return JSON.stringify(result, null, 2);
};

const formatToolArgs = (args: unknown): string => {
  if (!args) return "";
  if (typeof args === "string") {
    try {
      const parsed = JSON.parse(args);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return args;
    }
  }
  return JSON.stringify(args, null, 2);
};

const isIPythonTool = (toolCall: { name?: string }): boolean => {
  return (
    toolCall.name === "astrbot_execute_ipython" ||
    toolCall.name === "astrbot_execute_python"
  );
};

interface PendingToolCall {
  name?: string;
  finished_ts?: number;
  ts?: number;
  id?: string;
  args?: unknown;
  result?: unknown;
  [key: string]: unknown;
}

const isFileDownloading = (renderPart: {
  type: string;
  part?: { embedded_file?: { attachment_id?: string } };
}): boolean => {
  const downloadSet = props.downloadingFiles;
  if (!downloadSet) return false;
  const attachmentId = renderPart?.part?.embedded_file?.attachment_id;
  if (!attachmentId) return false;
  return downloadSet.has(attachmentId);
};

const getRenderParts = (
  messageParts: MessagePart[],
): Array<{
  type: string;
  toolCalls?: PendingToolCall[];
  toolCall?: PendingToolCall;
  part?: MessagePart;
  key?: string;
}> => {
  if (!Array.isArray(messageParts)) return [];
  const rendered: Array<{
    type: string;
    toolCalls?: PendingToolCall[];
    toolCall?: PendingToolCall;
    part?: MessagePart;
    key?: string;
  }> = [];
  let pendingToolCalls: PendingToolCall[] = [];
  let groupIndex = 0;

  const flushPending = (endIndex: number): void => {
    if (!pendingToolCalls.length) return;
    rendered.push({
      type: "tool_group",
      toolCalls: pendingToolCalls,
      key: `tool-group-${groupIndex}-${endIndex}`,
    });
    pendingToolCalls = [];
    groupIndex += 1;
  };

  messageParts.forEach((part, idx) => {
    if (
      part?.type === "tool_call" &&
      Array.isArray(part.tool_calls) &&
      part.tool_calls.length
    ) {
      part.tool_calls.forEach((toolCall, tcIndex) => {
        if (isIPythonTool(toolCall)) {
          flushPending(idx - 1);
          rendered.push({
            type: "ipython",
            toolCall,
            key: `ipython-${idx}-${tcIndex}`,
          });
          return;
        }

        pendingToolCalls.push(toolCall);
      });
      return;
    }

    flushPending(idx - 1);
    if (!part) return;
    rendered.push({
      type: "part",
      part,
      key: `part-${idx}`,
    });
  });

  flushPending(messageParts.length - 1);
  return rendered;
};
</script>

<style scoped>
.tool-call-compact {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 8px 0 4px;
}

.tool-call-group-title {
  font-size: 13px;
  color: var(--v-theme-secondaryText);
  opacity: 0.7;
}

.tool-call-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-call-detail-row {
  display: flex;
  flex-direction: column;
  margin-bottom: 6px;
}

.tool-call-detail-row:last-child {
  margin-bottom: 0;
}

.detail-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--v-theme-secondaryText);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.detail-value {
  font-size: 12px;
  color: var(--v-theme-primaryText);
  background-color: transparent;
  padding: 2px 6px;
  border-radius: 4px;
  word-break: break-word;
}

.detail-json {
  font-family: "Fira Code", "Consolas", monospace;
  white-space: pre-wrap;
  max-height: 220px;
  overflow-y: auto;
  margin: 0;
}

.detail-result {
  max-height: 320px;
  background-color: transparent;
}

.tool-call-item-enter-active,
.tool-call-item-leave-active {
  transition: all 0.2s ease;
}

.tool-call-item-enter-from,
.tool-call-item-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.ipython-icon,
.tool-call-chevron {
  margin-left: 6px;
  transition: transform 0.2s ease;
}

.ipython-icon.rotated {
  transform: rotate(90deg);
}

.tool-call-chevron.rotated {
  transform: rotate(90deg);
}

.embedded-images {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.embedded-image {
  display: flex;
  justify-content: flex-start;
}

.bot-embedded-image {
  max-width: 55%;
  width: auto;
  height: auto;
  border-radius: 4px;
  cursor: pointer;
  transition: transform 0.2s ease;
}

.embedded-audio {
  width: 300px;
  margin-top: 8px;
}

.embedded-audio .audio-player {
  width: 100%;
  max-width: 300px;
}

/* 文件附件样式 */
.file-attachments,
.embedded-files {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.file-attachment,
.embedded-file {
  display: flex;
  align-items: center;
}

/* 文件附件样式 */
.file-attachments,
.embedded-files {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.file-attachment,
.embedded-file {
  display: flex;
  align-items: center;
}

.file-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background-color: rgba(var(--v-theme-primary), 0.08);
  border: 1px solid rgba(var(--v-theme-primary), 0.2);
  border-radius: 8px;
  text-decoration: none;
  font-size: 13px;
  transition: all 0.2s ease;
  max-width: 320px;
}

.file-link-download {
  cursor: pointer;
}
</style>
