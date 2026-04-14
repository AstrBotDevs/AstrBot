<template>
  <div
    ref="messageListRoot"
    class="message-list-root"
    :class="{ 'is-dark': isDark }"
  >
    <div v-if="isLoadingMessages" class="center-state">
      <v-progress-circular indeterminate size="32" width="3" />
    </div>

    <div v-else class="messages-list">
      <div
        v-for="(msg, msgIndex) in messages"
        :key="msg.id || `${msgIndex}-${msg.created_at || ''}`"
        class="message-row"
        :class="isUserMessage(msg) ? 'from-user' : 'from-bot'"
      >
        <v-avatar v-if="!isUserMessage(msg)" class="bot-avatar" size="48">
          <v-progress-circular
            v-if="isMessageStreaming(msgIndex)"
            indeterminate
            size="22"
            width="2"
          />
          <span v-else class="bot-avatar-symbol" aria-hidden="true">✦</span>
        </v-avatar>

        <div class="message-stack">
          <div
            class="message-bubble"
            :class="{ user: isUserMessage(msg), bot: !isUserMessage(msg) }"
          >
            <div v-if="messageContent(msg).isLoading" class="loading-message">
              <span>{{ tm("message.loading") }}</span>
            </div>

            <template v-else>
              <ReasoningBlock
                v-if="messageContent(msg).reasoning"
                :reasoning="messageContent(msg).reasoning || ''"
                :is-dark="isDark"
                :initial-expanded="false"
                :is-streaming="isMessageStreaming(msgIndex)"
                :has-non-reasoning-content="hasNonReasoningContent(msg)"
              />

              <template
                v-for="(part, partIndex) in messageParts(msg)"
                :key="`${msgIndex}-${partIndex}-${part.type}`"
              >
                <button
                  v-if="part.type === 'reply'"
                  class="reply-quote"
                  type="button"
                  @click="scrollToMessage(part.message_id)"
                >
                  <v-icon size="15">mdi-reply</v-icon>
                  <span>{{
                    replyPreview(part.message_id, part.selected_text)
                  }}</span>
                </button>

                <div
                  v-else-if="part.type === 'plain' && isUserMessage(msg)"
                  class="plain-content"
                >
                  {{ part.text || "" }}
                </div>

                <MarkdownMessagePart
                  v-else-if="part.type === 'plain'"
                  :content="part.text || ''"
                  :refs="resolvedMessageRefs(msg)"
                  :is-dark="isDark"
                  :custom-html-tags="customMarkdownTags"
                />

                <button
                  v-else-if="part.type === 'image'"
                  class="image-part"
                  type="button"
                  @click="openImage(partUrl(part))"
                >
                  <img :src="partUrl(part)" :alt="part.filename || 'image'" />
                </button>

                <audio
                  v-else-if="part.type === 'record'"
                  class="audio-part"
                  controls
                  :src="partUrl(part)"
                />

                <video
                  v-else-if="part.type === 'video'"
                  class="video-part"
                  controls
                  :src="partUrl(part)"
                />

                <div v-else-if="part.type === 'file'" class="file-part">
                  <v-icon size="20">mdi-file-document-outline</v-icon>
                  <span>{{ part.filename || "file" }}</span>
                  <v-btn
                    icon="mdi-download"
                    size="x-small"
                    variant="text"
                    :loading="
                      downloadingFiles.has(
                        part.attachment_id || part.filename || '',
                      )
                    "
                    @click="downloadPart(part)"
                  />
                </div>

                <div
                  v-else-if="part.type === 'tool_call'"
                  class="tool-call-block"
                >
                  <template
                    v-for="tool in part.tool_calls || []"
                    :key="tool.id || tool.name"
                  >
                    <ToolCallItem
                      v-if="isIPythonToolCall(tool)"
                      :is-dark="isDark"
                    >
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

                <div v-else class="unknown-part">
                  {{ formatJson(part) }}
                </div>
              </template>
            </template>
          </div>

          <div v-if="showMessageMeta(msg, msgIndex)" class="message-meta">
            <span v-if="msg.created_at">{{ formatTime(msg.created_at) }}</span>
            <v-btn
              v-if="!isUserMessage(msg)"
              icon="mdi-content-copy"
              size="x-small"
              variant="text"
              @click="copyMessage(msg)"
            />
            <v-menu v-if="messageContent(msg).agentStats" location="bottom">
              <template #activator="{ props: statsProps }">
                <v-btn
                  v-bind="statsProps"
                  icon="mdi-information-outline"
                  size="x-small"
                  variant="text"
                />
              </template>
              <v-card class="stats-card" elevation="4">
                <div class="stats-row">
                  <span>{{ tm("stats.inputTokens") }}</span>
                  <strong>{{
                    inputTokens(messageContent(msg).agentStats)
                  }}</strong>
                </div>
                <div class="stats-row">
                  <span>{{ tm("stats.outputTokens") }}</span>
                  <strong>{{
                    outputTokens(messageContent(msg).agentStats)
                  }}</strong>
                </div>
                <div
                  v-if="agentTtft(messageContent(msg).agentStats)"
                  class="stats-row"
                >
                  <span>{{ tm("stats.ttft") }}</span>
                  <strong>{{
                    agentTtft(messageContent(msg).agentStats)
                  }}</strong>
                </div>
                <div class="stats-row">
                  <span>{{ tm("stats.duration") }}</span>
                  <strong>{{
                    agentDuration(messageContent(msg).agentStats)
                  }}</strong>
                </div>
              </v-card>
            </v-menu>
            <div v-if="messageRefs(msg).length" class="message-meta-refs">
              <ActionRef
                :refs="resolvedMessageRefs(msg)"
                @open-refs="openRefsSidebar"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <RefsSidebar v-model="refsSidebarOpen" :refs="selectedRefs" />

    <v-overlay
      v-model="imagePreview.visible"
      class="image-preview-overlay"
      scrim="rgba(0, 0, 0, 0.86)"
      @click="closeImage"
    >
      <img
        class="preview-image"
        :src="imagePreview.url"
        alt="preview"
        @click.stop
      />
    </v-overlay>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref } from "vue";
import axios from "axios";
import { setCustomComponents } from "markstream-vue";
import "markstream-vue/index.css";
import IPythonToolBlock from "@/components/chat/message_list_comps/IPythonToolBlock.vue";
import MarkdownMessagePart from "@/components/chat/message_list_comps/MarkdownMessagePart.vue";
import ReasoningBlock from "@/components/chat/message_list_comps/ReasoningBlock.vue";
import RefNode from "@/components/chat/message_list_comps/RefNode.vue";
import RefsSidebar from "@/components/chat/message_list_comps/RefsSidebar.vue";
import ToolCallCard from "@/components/chat/message_list_comps/ToolCallCard.vue";
import ToolCallItem from "@/components/chat/message_list_comps/ToolCallItem.vue";
import ActionRef from "@/components/chat/message_list_comps/ActionRef.vue";
import ThemeAwareMarkdownCodeBlock from "@/components/shared/ThemeAwareMarkdownCodeBlock.vue";
import type {
  ChatContent,
  ChatRecord,
  MessagePart,
} from "@/composables/useMessages";
import { useModuleI18n } from "@/i18n/composables";

const props = withDefaults(
  defineProps<{
    messages: ChatRecord[];
    isDark?: boolean;
    isStreaming?: boolean;
    isLoadingMessages?: boolean;
  }>(),
  {
    isDark: false,
    isStreaming: false,
    isLoadingMessages: false,
  },
);

setCustomComponents("chat-message", {
  ref: RefNode,
  code_block: ThemeAwareMarkdownCodeBlock,
});

const { tm } = useModuleI18n("features/chat");
const customMarkdownTags = ["ref"];
const downloadingFiles = ref(new Set<string>());
const messageListRoot = ref<HTMLElement | null>(null);
const imagePreview = reactive({ visible: false, url: "" });
const refsSidebarOpen = ref(false);
const selectedRefs = ref<Record<string, unknown> | null>(null);

const messages = computed(() => props.messages || []);

function isUserMessage(message: ChatRecord) {
  return messageContent(message).type === "user";
}

function messageContent(message: ChatRecord): ChatContent {
  return message.content || { type: "bot", message: [] };
}

function messageParts(message: ChatRecord): MessagePart[] {
  const parts = messageContent(message).message;
  if (Array.isArray(parts)) return parts;
  if (typeof parts === "string") return [{ type: "plain", text: parts }];
  return [];
}

function isMessageStreaming(messageIndex: number) {
  return props.isStreaming && messageIndex === messages.value.length - 1;
}

function hasNonReasoningContent(message: ChatRecord) {
  return messageParts(message).some((part) => {
    if (part.type === "reply") return false;
    if (part.type === "plain") return Boolean(String(part.text || "").trim());
    return true;
  });
}

function partUrl(part: MessagePart) {
  if (part.embedded_url) return part.embedded_url;
  if (part.embedded_file?.url) return part.embedded_file.url;
  if (part.attachment_id) {
    return `/api/chat/get_attachment?attachment_id=${encodeURIComponent(
      part.attachment_id,
    )}`;
  }
  if (part.filename) {
    return `/api/chat/get_file?filename=${encodeURIComponent(part.filename)}`;
  }
  return "";
}

function formatJson(value: unknown) {
  if (typeof value === "string") {
    const parsed = parseJsonSafe(value);
    if (parsed !== value) return JSON.stringify(parsed, null, 2);
    return value;
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "");
  }
}

function replyPreview(messageId?: string | number, fallback?: string) {
  if (fallback) return truncate(fallback, 80);
  const found = messages.value.find(
    (message) => String(message.id) === String(messageId),
  );
  const text = found ? plainTextFromMessage(found) : "";
  return text ? truncate(text, 80) : tm("reply.replyTo");
}

function plainTextFromMessage(message: ChatRecord) {
  return messageParts(message)
    .filter((part) => part.type === "plain" && part.text)
    .map((part) => part.text)
    .join("\n");
}

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max)}...` : value;
}

function scrollToMessage(messageId?: string | number) {
  if (!messageId) return;
  const index = messages.value.findIndex(
    (message) => String(message.id) === String(messageId),
  );
  if (index < 0) return;
  nextTick(() => {
    const rows = messageListRoot.value?.querySelectorAll(".message-row");
    rows?.[index]?.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

function showMessageMeta(message: ChatRecord, msgIndex: number) {
  return !messageContent(message).isLoading && !isMessageStreaming(msgIndex);
}

function messageRefs(message: ChatRecord) {
  return resolvedMessageRefs(message).used;
}

function resolvedMessageRefs(message: ChatRecord) {
  return normalizeRefs(messageContent(message).refs);
}

function normalizeRefs(refs: unknown) {
  if (!refs) return { used: [] as Array<Record<string, unknown>> };
  const refsValue = refs as { used?: unknown };
  const used = Array.isArray(refsValue.used)
    ? refsValue.used
    : Array.isArray(refs)
    ? refs
    : [];

  return {
    used: normalizeRefItems(used),
  };
}

function normalizeRefItems(items: unknown[]) {
  return items
    .map((item: any) => ({
      index: item?.index,
      title: item?.title || item?.url || tm("refs.title"),
      url: item?.url,
      snippet: item?.snippet,
      favicon: item?.favicon,
    }))
    .filter((item) => item.url);
}

function openRefsSidebar(refs: unknown) {
  selectedRefs.value =
    refs && typeof refs === "object" ? (refs as Record<string, unknown>) : null;
  refsSidebarOpen.value = true;
}

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

async function copyMessage(message: ChatRecord) {
  const text = plainTextFromMessage(message);
  if (!text) return;
  await navigator.clipboard?.writeText(text);
}

async function downloadPart(part: MessagePart) {
  const key = part.attachment_id || part.filename || "";
  if (!key) return;
  downloadingFiles.value = new Set(downloadingFiles.value).add(key);
  try {
    const response = await axios.get(partUrl(part), { responseType: "blob" });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = part.filename || "file";
    anchor.click();
    URL.revokeObjectURL(url);
  } finally {
    const next = new Set(downloadingFiles.value);
    next.delete(key);
    downloadingFiles.value = next;
  }
}

function openImage(url: string) {
  if (!url) return;
  imagePreview.url = url;
  imagePreview.visible = true;
}

function closeImage() {
  imagePreview.visible = false;
  imagePreview.url = "";
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function inputTokens(stats: any) {
  const usage = stats?.token_usage || {};
  return (usage.input_other || 0) + (usage.input_cached || 0);
}

function outputTokens(stats: any) {
  return stats?.token_usage?.output || 0;
}

function agentDuration(stats: any) {
  const directDuration = readPositiveNumber(stats, [
    "duration",
    "total_duration",
  ]);
  if (directDuration !== null) return formatDuration(directDuration);

  const startTime = readPositiveNumber(stats, ["start_time"]);
  const endTime = readPositiveNumber(stats, ["end_time"]);
  if (startTime === null || endTime === null || endTime < startTime) return "-";
  return formatDuration(endTime - startTime);
}

function agentTtft(stats: any) {
  const ttft = readPositiveNumber(stats, [
    "time_to_first_token",
    "ttft",
    "first_token_latency",
  ]);
  if (ttft === null) return "";
  return formatDuration(ttft);
}

function readPositiveNumber(source: any, keys: string[]) {
  for (const key of keys) {
    const value = Number(source?.[key]);
    if (Number.isFinite(value) && value > 0) return value;
  }
  return null;
}

function formatDuration(seconds: number) {
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const restSeconds = Math.round(seconds % 60);
  return `${minutes}m ${restSeconds}s`;
}
</script>

<style scoped>
.message-list-root {
  --chat-border: rgba(var(--v-border-color), 0.16);
  --chat-muted: rgba(var(--v-theme-on-surface), 0.62);
  width: 100%;
  min-height: 0;
  color: rgb(var(--v-theme-on-surface));
}

.message-list-root.is-dark {
  --chat-border: rgba(255, 255, 255, 0.1);
}

.center-state {
  display: flex;
  min-height: 160px;
  align-items: center;
  justify-content: center;
}

.messages-list {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.message-row {
  display: flex;
  gap: 10px;
  max-width: 100%;
}

.message-row.from-user {
  justify-content: flex-end;
}

.message-stack {
  max-width: min(760px, 82%);
}

.from-user .message-stack {
  align-items: flex-end;
  max-width: 60%;
}

.bot-avatar {
  margin-top: 2px;
  color: rgb(var(--v-theme-primary));
  user-select: none;
}

.bot-avatar-symbol {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  line-height: 0;
  margin-top: -2px;
  pointer-events: none;
  user-select: none;
}

.message-bubble {
  max-width: 100%;
  border-radius: 8px;
  padding: 10px 14px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.message-bubble.user {
  color: var(--v-theme-primaryText);
  padding: 12px 18px;
  font-size: 15px;
  border-radius: 1.5rem;
  background: rgba(var(--v-theme-primary), 0.12);
}

.message-bubble.bot {
  background: transparent;
  padding-left: 0;
}

.plain-content {
  white-space: pre-wrap;
}

.loading-message {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  color: var(--chat-muted);
}

.reply-quote {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  border: 0;
  border-left: 3px solid rgb(var(--v-theme-primary));
  border-radius: 6px;
  padding: 7px 9px;
  margin-bottom: 8px;
  background: rgba(var(--v-theme-primary), 0.08);
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.image-part {
  display: block;
  border: 0;
  padding: 0;
  margin-top: 8px;
  background: transparent;
  cursor: zoom-in;
}

.image-part img {
  max-width: min(420px, 100%);
  max-height: 360px;
  border-radius: 8px;
  object-fit: contain;
}

.audio-part,
.video-part {
  display: block;
  max-width: 100%;
  margin-top: 8px;
}

.video-part {
  max-height: 360px;
  border-radius: 8px;
}

.file-part {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 8px 10px;
  border: 1px solid var(--chat-border);
  border-radius: 8px;
}

.file-part span {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-call-block {
  margin: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tool-call-inline-status {
  color: var(--chat-muted);
  font-size: 12px;
}

.unknown-part {
  max-width: 100%;
  overflow-x: auto;
  border-radius: 8px;
  padding: 10px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 2px;
  min-height: 24px;
  color: var(--chat-muted);
  font-size: 12px;
}

.message-meta-refs {
  display: flex;
  align-items: center;
}

.from-user .message-meta {
  justify-content: flex-end;
}

.stats-card {
  min-width: 150px;
  padding: 8px 10px;
}

.stats-row {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 2px 0;
  font-size: 12px;
  line-height: 1.35;
}

.stats-row span {
  color: var(--chat-muted);
}

.stats-row strong {
  font-size: 12px;
  font-weight: 600;
}

.image-preview-overlay {
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-image {
  max-width: min(92vw, 1200px);
  max-height: 88vh;
  border-radius: 8px;
  object-fit: contain;
}

@media (max-width: 760px) {
  .message-stack,
  .from-user .message-stack {
    max-width: 88%;
  }

  .message-row.from-bot {
    flex-direction: column;
    gap: 2px;
  }

  .message-row.from-bot .message-stack {
    max-width: 100%;
  }

  .message-row.from-bot .bot-avatar {
    display: none;
  }
}
</style>
