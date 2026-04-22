<template>
  <div
    ref="listRoot"
    class="chat-message-list"
    :class="[`variant-${variant}`, { 'is-dark': isDark }]"
  >
    <div class="messages-list">
      <div
        v-for="(msg, msgIndex) in messages"
        :key="msg.id || `${msgIndex}-${msg.created_at || ''}`"
        class="message-row"
        :class="isUserMessage(msg) ? 'from-user' : 'from-bot'"
      >
        <v-avatar v-if="!isUserMessage(msg)" class="bot-avatar" :size="avatarSize">
          <v-progress-circular
            v-if="isMessageStreaming(msg, msgIndex)"
            class="bot-streaming-spinner"
            indeterminate
            size="22"
            width="2"
          />
          <span v-else class="bot-avatar-symbol" aria-hidden="true">✦</span>
        </v-avatar>

        <div class="message-stack">
          <div
            v-if="isUserMessage(msg) && userAttachmentParts(msg).length"
            class="sent-attachments"
            :class="{ 'images-only': hasImageOnlyAttachments(msg) }"
          >
            <template
              v-for="(part, attachmentIndex) in userAttachmentParts(msg)"
              :key="`${msgIndex}-attachment-${attachmentIndex}-${part.type}`"
            >
              <button
                v-if="part.type === 'image'"
                class="sent-attachment-card sent-image-card"
                type="button"
                @click="openImage(partUrl(part))"
              >
                <img :src="partUrl(part)" :alt="part.filename || 'image'" />
              </button>

              <div v-else class="sent-attachment-card sent-file-card">
                <div
                  class="sent-attachment-icon"
                  :style="{ color: attachmentPresentation(part).color }"
                >
                  <v-icon :icon="attachmentPresentation(part).icon" size="24" />
                  <span class="sent-attachment-ext">
                    {{ attachmentPresentation(part).label }}
                  </span>
                </div>
                <span class="sent-attachment-name">
                  {{ attachmentName(part) }}
                </span>
                <v-btn
                  v-if="part.type === 'file'"
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
            </template>
          </div>

          <div
            v-if="shouldShowMessageBubble(msg)"
            class="message-bubble"
            :class="{ user: isUserMessage(msg), bot: !isUserMessage(msg) }"
            @mouseup="handleMouseUp($event, msg)"
          >
            <div v-if="messageContent(msg).isLoading" class="loading-message">
              <span>{{ tm("message.loading") }}</span>
            </div>

            <template v-else-if="isEditingMessage(msg)">
              <div class="inline-message-editor">
                <textarea
                  :value="editDraft"
                  class="inline-message-editor-input"
                  rows="2"
                  autofocus
                  @input="
                    emit(
                      'update:editDraft',
                      ($event.target as HTMLTextAreaElement).value,
                    )
                  "
                  @keydown.esc="emit('cancelEdit')"
                ></textarea>
                <div class="inline-message-editor-actions">
                  <v-btn
                    class="inline-message-editor-action"
                    size="small"
                    variant="text"
                    @click="emit('cancelEdit')"
                  >
                    {{ t("core.common.cancel") }}
                  </v-btn>
                  <v-btn
                    class="inline-message-editor-action"
                    size="small"
                    color="primary"
                    variant="tonal"
                    :loading="savingEdit"
                    @click="emit('saveEdit')"
                  >
                    {{ t("core.common.save") }}
                  </v-btn>
                </div>
              </div>
            </template>

            <template v-else>
              <ReasoningBlock
                v-if="messageContent(msg).reasoning"
                :reasoning="messageContent(msg).reasoning || ''"
                :is-dark="isDark"
                :initial-expanded="false"
                :is-streaming="isMessageStreaming(msg, msgIndex)"
                :has-non-reasoning-content="hasNonReasoningContent(msg)"
              />

              <template
                v-for="(part, partIndex) in bubbleParts(msg)"
                :key="`${msgIndex}-${partIndex}-${part.type}`"
              >
                <button
                  v-if="part.type === 'reply'"
                  class="reply-quote"
                  type="button"
                  @click="scrollToMessage(part.message_id)"
                >
                  <v-icon size="15">mdi-reply</v-icon>
                  <span>{{ replyPreview(part.message_id, part.selected_text) }}</span>
                </button>

                <div
                  v-else-if="part.type === 'plain' && isUserMessage(msg)"
                  class="plain-content"
                >
                  {{ part.text || "" }}
                </div>

                <div
                  v-else-if="part.type === 'plain' && messageThreads(msg).length"
                  class="threaded-message-content"
                >
                  <ThreadedMarkdownMessagePart
                    :text="part.text || ''"
                    :threads="messageThreads(msg)"
                    :refs="resolvedMessageRefs(msg)"
                    :is-dark="isDark"
                    :custom-html-tags="customMarkdownTags"
                    @open-thread="emit('openThread', $event)"
                  />
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

                <div v-else-if="part.type === 'tool_call'" class="tool-call-block">
                  <template v-for="tool in part.tool_calls || []" :key="tool.id || tool.name">
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

                <div v-else class="unknown-part">
                  {{ formatJson(part) }}
                </div>
              </template>
            </template>
          </div>

          <div v-if="showMessageMeta(msg, msgIndex)" class="message-meta">
            <span v-if="msg.created_at">{{ formatTime(msg.created_at) }}</span>
            <v-btn
              v-if="canEditMessage(msg, msgIndex)"
              icon="mdi-pencil-outline"
              size="x-small"
              variant="text"
              @click="emit('openEdit', msg)"
            />
            <RegenerateMenu
              v-if="canRegenerateMessage(msg, msgIndex)"
              @retry="emit('regenerate', msg)"
              @retry-with-model="emit('regenerateWithModel', msg, $event)"
            />
            <v-btn
              v-if="enableCopy && !isUserMessage(msg)"
              icon="mdi-content-copy"
              size="x-small"
              variant="text"
              @click="copyMessage(msg)"
            />
            <v-menu
              v-if="messageContent(msg).agentStats"
              location="bottom"
              transition="none"
            >
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
                  <strong>{{ inputTokens(messageContent(msg).agentStats) }}</strong>
                </div>
                <div class="stats-row">
                  <span>{{ tm("stats.outputTokens") }}</span>
                  <strong>{{ outputTokens(messageContent(msg).agentStats) }}</strong>
                </div>
                <div v-if="agentTtft(messageContent(msg).agentStats)" class="stats-row">
                  <span>{{ tm("stats.ttft") }}</span>
                  <strong>{{ agentTtft(messageContent(msg).agentStats) }}</strong>
                </div>
                <div class="stats-row">
                  <span>{{ tm("stats.duration") }}</span>
                  <strong>{{ agentDuration(messageContent(msg).agentStats) }}</strong>
                </div>
              </v-card>
            </v-menu>
            <StyledMenu
              v-if="messageThreads(msg).length"
              location="bottom"
              transition="none"
              no-border
            >
              <template #activator="{ props: threadMenuProps }">
                <button
                  v-bind="threadMenuProps"
                  class="message-thread-meta"
                  type="button"
                >
                  <v-icon size="14">mdi-source-branch</v-icon>
                  <span>{{ threadCountLabel(messageThreads(msg).length) }}</span>
                </button>
              </template>
              <v-list-item
                v-for="thread in messageThreads(msg)"
                :key="thread.thread_id"
                class="styled-menu-item thread-menu-item"
                rounded="md"
                @click="emit('openThread', thread)"
              >
                <template #prepend>
                  <v-icon size="16">mdi-source-branch</v-icon>
                </template>
                <v-list-item-title class="thread-menu-title">
                  {{ threadPreview(thread) }}
                </v-list-item-title>
              </v-list-item>
            </StyledMenu>
            <div v-if="messageRefs(msg).length" class="message-meta-refs">
              <ActionRef
                :refs="resolvedMessageRefs(msg)"
                @open-refs="handleOpenRefs"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <RefsSidebar
      v-if="manageRefsSidebar"
      v-model="refsSidebarOpen"
      :refs="selectedRefs"
    />

    <v-overlay
      v-model="imagePreview.visible"
      class="image-preview-overlay"
      scrim="rgba(0, 0, 0, 0.86)"
      @click="closeImage"
    >
      <img
        :src="imagePreview.url"
        class="preview-image"
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
import RegenerateMenu, {
  type RegenerateModelSelection,
} from "@/components/chat/RegenerateMenu.vue";
import ThreadedMarkdownMessagePart from "@/components/chat/ThreadedMarkdownMessagePart.vue";
import ReasoningBlock from "@/components/chat/message_list_comps/ReasoningBlock.vue";
import ToolCallCard from "@/components/chat/message_list_comps/ToolCallCard.vue";
import ToolCallItem from "@/components/chat/message_list_comps/ToolCallItem.vue";
import IPythonToolBlock from "@/components/chat/message_list_comps/IPythonToolBlock.vue";
import RefsSidebar from "@/components/chat/message_list_comps/RefsSidebar.vue";
import RefNode from "@/components/chat/message_list_comps/RefNode.vue";
import ThreadNode from "@/components/chat/message_list_comps/ThreadNode.vue";
import ActionRef from "@/components/chat/message_list_comps/ActionRef.vue";
import MarkdownMessagePart from "@/components/chat/message_list_comps/MarkdownMessagePart.vue";
import ThemeAwareMarkdownCodeBlock from "@/components/shared/ThemeAwareMarkdownCodeBlock.vue";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import type {
  ChatContent,
  ChatRecord,
  ChatThread,
  MessagePart,
} from "@/composables/useMessages";
import { useI18n, useModuleI18n } from "@/i18n/composables";

const props = withDefaults(
  defineProps<{
    messages: ChatRecord[];
    isDark?: boolean;
    isStreaming?: boolean;
    variant?: "main" | "thread";
    enableEdit?: boolean;
    enableRegenerate?: boolean;
    enableThreadSelection?: boolean;
    enableCopy?: boolean;
    manageRefsSidebar?: boolean;
    editingMessageId?: string | number | null;
    editDraft?: string;
    savingEdit?: boolean;
  }>(),
  {
    isDark: false,
    isStreaming: false,
    variant: "main",
    enableEdit: false,
    enableRegenerate: false,
    enableThreadSelection: false,
    enableCopy: true,
    manageRefsSidebar: true,
    editingMessageId: null,
    editDraft: "",
    savingEdit: false,
  },
);

const emit = defineEmits<{
  "update:editDraft": [value: string];
  openEdit: [message: ChatRecord];
  cancelEdit: [];
  saveEdit: [];
  regenerate: [message: ChatRecord];
  regenerateWithModel: [
    message: ChatRecord,
    selection: RegenerateModelSelection,
  ];
  selectBotText: [event: MouseEvent, message: ChatRecord];
  openThread: [thread: ChatThread];
  openRefs: [refs: unknown];
}>();

setCustomComponents("chat-message", {
  ref: RefNode,
  thread: ThreadNode,
  code_block: ThemeAwareMarkdownCodeBlock,
});

const { t } = useI18n();
const { tm } = useModuleI18n("features/chat");
const customMarkdownTags = ["ref"];
const downloadingFiles = ref(new Set<string>());
const imagePreview = reactive({ visible: false, url: "" });
const refsSidebarOpen = ref(false);
const selectedRefs = ref<Record<string, unknown> | null>(null);
const listRoot = ref<HTMLElement | null>(null);
const avatarSize = computed(() => (props.variant === "thread" ? 36 : 56));

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

function isAttachmentPart(part: MessagePart) {
  return ["image", "record", "video", "file"].includes(part.type);
}

function userAttachmentParts(message: ChatRecord) {
  if (!isUserMessage(message)) return [];
  return messageParts(message).filter(isAttachmentPart);
}

function hasImageOnlyAttachments(message: ChatRecord) {
  const attachments = userAttachmentParts(message);
  return (
    attachments.length > 0 &&
    attachments.every((part) => part.type === "image")
  );
}

function bubbleParts(message: ChatRecord) {
  if (!isUserMessage(message)) return messageParts(message);
  return messageParts(message).filter((part) => !isAttachmentPart(part));
}

function shouldShowMessageBubble(message: ChatRecord) {
  return (
    !isUserMessage(message) ||
    isEditingMessage(message) ||
    messageContent(message).isLoading ||
    bubbleParts(message).length > 0
  );
}

function isMessageStreaming(message: ChatRecord, messageIndex: number) {
  return (
    props.isStreaming &&
    !isUserMessage(message) &&
    messageIndex === props.messages.length - 1
  );
}

function isEditingMessage(message: ChatRecord) {
  return (
    props.editingMessageId != null &&
    message.id != null &&
    String(props.editingMessageId) === String(message.id)
  );
}

function canEditMessage(message: ChatRecord, messageIndex: number) {
  return (
    props.enableEdit &&
    isUserMessage(message) &&
    messageIndex === latestEditableUserIndex() &&
    message.id != null &&
    !String(message.id).startsWith("local-")
  );
}

function latestEditableUserIndex() {
  for (let index = props.messages.length - 1; index >= 0; index -= 1) {
    const message = props.messages[index];
    if (
      isUserMessage(message) &&
      message.id != null &&
      !String(message.id).startsWith("local-")
    ) {
      return index;
    }
  }
  return -1;
}

function canRegenerateMessage(message: ChatRecord, messageIndex: number) {
  return (
    props.enableRegenerate &&
    !isUserMessage(message) &&
    messageIndex === props.messages.length - 1 &&
    !isMessageStreaming(message, messageIndex) &&
    Boolean(message.llm_checkpoint_id)
  );
}

function showMessageMeta(message: ChatRecord, messageIndex: number) {
  return (
    !messageContent(message).isLoading &&
    !isMessageStreaming(message, messageIndex)
  );
}

function hasNonReasoningContent(message: ChatRecord) {
  return messageParts(message).some((part) => {
    if (part.type === "reply") return false;
    if (part.type === "plain") return Boolean(String(part.text || "").trim());
    return true;
  });
}

const attachmentTypeStyles: Record<
  string,
  { color: string; icon: string; label: string }
> = {
  pdf: { color: "#d32f2f", icon: "mdi-file-pdf-box", label: "PDF" },
  txt: { color: "#1976d2", icon: "mdi-file-document-outline", label: "TXT" },
  md: { color: "#1976d2", icon: "mdi-language-markdown-outline", label: "MD" },
  markdown: {
    color: "#1976d2",
    icon: "mdi-language-markdown-outline",
    label: "MD",
  },
  doc: { color: "#2b579a", icon: "mdi-file-word-box", label: "DOC" },
  docx: { color: "#2b579a", icon: "mdi-file-word-box", label: "DOCX" },
  xls: { color: "#217346", icon: "mdi-file-excel-box", label: "XLS" },
  xlsx: { color: "#217346", icon: "mdi-file-excel-box", label: "XLSX" },
  csv: { color: "#217346", icon: "mdi-file-delimited-outline", label: "CSV" },
  ppt: { color: "#d24726", icon: "mdi-file-powerpoint-box", label: "PPT" },
  pptx: { color: "#d24726", icon: "mdi-file-powerpoint-box", label: "PPTX" },
  zip: { color: "#7b5e00", icon: "mdi-folder-zip-outline", label: "ZIP" },
  rar: { color: "#7b5e00", icon: "mdi-folder-zip-outline", label: "RAR" },
  "7z": { color: "#7b5e00", icon: "mdi-folder-zip-outline", label: "7Z" },
  tar: { color: "#7b5e00", icon: "mdi-folder-zip-outline", label: "TAR" },
  gz: { color: "#7b5e00", icon: "mdi-folder-zip-outline", label: "GZ" },
  json: { color: "#6a1b9a", icon: "mdi-code-json", label: "JSON" },
  yaml: { color: "#6a1b9a", icon: "mdi-code-braces", label: "YAML" },
  yml: { color: "#6a1b9a", icon: "mdi-code-braces", label: "YML" },
  js: { color: "#b8860b", icon: "mdi-language-javascript", label: "JS" },
  ts: { color: "#3178c6", icon: "mdi-language-typescript", label: "TS" },
  html: { color: "#e34c26", icon: "mdi-language-html5", label: "HTML" },
  css: { color: "#264de4", icon: "mdi-language-css3", label: "CSS" },
  py: { color: "#3776ab", icon: "mdi-language-python", label: "PY" },
  java: { color: "#b07219", icon: "mdi-language-java", label: "JAVA" },
  mp3: { color: "#00897b", icon: "mdi-file-music-outline", label: "MP3" },
  wav: { color: "#00897b", icon: "mdi-file-music-outline", label: "WAV" },
  flac: { color: "#00897b", icon: "mdi-file-music-outline", label: "FLAC" },
  mp4: { color: "#5e35b1", icon: "mdi-file-video-outline", label: "MP4" },
  mov: { color: "#5e35b1", icon: "mdi-file-video-outline", label: "MOV" },
  webm: { color: "#5e35b1", icon: "mdi-file-video-outline", label: "WEBM" },
};

function attachmentName(part: MessagePart) {
  return part.embedded_file?.filename || part.filename || part.type || "file";
}

function attachmentExtension(part: MessagePart) {
  const name = attachmentName(part);
  const extension = name.split(".").pop()?.toLowerCase() || "";
  return extension === name.toLowerCase() ? "" : extension;
}

function attachmentPresentation(part: MessagePart) {
  if (part.type === "record") {
    return { color: "#00897b", icon: "mdi-microphone", label: "AUDIO" };
  }
  if (part.type === "video") {
    return { color: "#5e35b1", icon: "mdi-file-video-outline", label: "VIDEO" };
  }
  const extension = attachmentExtension(part);
  return (
    attachmentTypeStyles[extension] || {
      color: "#607d8b",
      icon: "mdi-file-document-outline",
      label: extension ? extension.slice(0, 4).toUpperCase() : "FILE",
    }
  );
}

function handleMouseUp(event: MouseEvent, message: ChatRecord) {
  if (props.enableThreadSelection && !isUserMessage(message)) {
    emit("selectBotText", event, message);
  }
}

function messageThreads(message: ChatRecord) {
  return message.threads || [];
}

function threadCountLabel(count: number) {
  return tm("thread.count", { count });
}

function threadPreview(thread: ChatThread) {
  return truncate(thread.selected_text || tm("thread.title"), 48);
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

function plainTextFromMessage(message: ChatRecord) {
  return messageParts(message)
    .filter((part) => part.type === "plain" && part.text)
    .map((part) => part.text)
    .join("\n");
}

function replyPreview(messageId?: string | number, fallback?: string) {
  if (fallback) return truncate(fallback, 80);
  const found = props.messages.find(
    (message) => String(message.id) === String(messageId),
  );
  const text = found ? plainTextFromMessage(found) : "";
  return text ? truncate(text, 80) : tm("reply.replyTo");
}

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max)}...` : value;
}

function scrollToMessage(messageId?: string | number) {
  if (!messageId) return;
  const index = props.messages.findIndex(
    (message) => String(message.id) === String(messageId),
  );
  if (index < 0) return;
  nextTick(() => {
    listRoot.value
      ?.querySelectorAll(".message-row")
      [index]?.scrollIntoView({ behavior: "smooth", block: "center" });
  });
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

function parseJsonSafe(value: unknown) {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function messageRefs(message: ChatRecord) {
  return resolvedMessageRefs(message).used;
}

function resolvedMessageRefs(message: ChatRecord) {
  return normalizeRefs(messageContent(message).refs);
}

function normalizeRefs(refs: unknown) {
  if (!refs) return { used: [] as Array<Record<string, unknown>> };
  const used = Array.isArray((refs as any)?.used)
    ? (refs as any).used
    : Array.isArray(refs)
      ? refs
      : [];
  return { used: normalizeRefItems(used) };
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

function handleOpenRefs(refs: unknown) {
  if (!props.manageRefsSidebar) {
    emit("openRefs", refs);
    return;
  }
  selectedRefs.value =
    refs && typeof refs === "object" ? (refs as Record<string, unknown>) : null;
  refsSidebarOpen.value = true;
}

function normalizeToolCall(tool: Record<string, unknown>) {
  const normalized = { ...tool };
  normalized.args = normalized.args ?? normalized.arguments ?? {};
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
.chat-message-list {
  --chat-border: rgba(var(--v-border-color), 0.16);
  --chat-muted: rgba(var(--v-theme-on-surface), 0.62);
  width: 100%;
  color: rgb(var(--v-theme-on-surface));
}

.chat-message-list.is-dark {
  --chat-border: rgba(255, 255, 255, 0.1);
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
  display: flex;
  flex-direction: column;
  max-width: min(760px, 82%);
}

.from-user .message-stack {
  align-items: flex-end;
  max-width: 60%;
}

.sent-attachments {
  display: flex;
  max-width: 100%;
  gap: 10px;
  margin-bottom: 8px;
  padding: 2px 2px 4px;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
}

.sent-attachment-card {
  position: relative;
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  height: 64px;
  overflow: hidden;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  color: rgb(var(--v-theme-on-surface));
}

.sent-image-card {
  width: 64px;
  padding: 0;
  border: 0;
  cursor: zoom-in;
}

.sent-image-card img {
  width: 100%;
  height: 100%;
  border-radius: 11px;
  object-fit: cover;
}

.sent-attachments.images-only {
  max-width: min(420px, 100%);
}

.sent-attachments.images-only .sent-image-card {
  width: 180px;
  height: 180px;
}

.sent-attachments.images-only .sent-image-card img {
  object-fit: cover;
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.sent-file-card {
  width: 220px;
  padding: 8px 10px;
}

.sent-attachment-icon {
  display: inline-flex;
  flex-shrink: 0;
  min-width: 34px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
}

.sent-attachment-ext {
  max-width: 58px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  font-weight: 700;
  line-height: 12px;
}

.sent-attachment-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  line-height: 18px;
}

.bot-avatar {
  margin-top: 2px;
  color: rgb(var(--v-theme-primary));
  user-select: none;
}

.bot-streaming-spinner {
  margin-top: -4px;
}

.bot-avatar-symbol {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  margin-top: -2px;
  line-height: 0;
  pointer-events: none;
  user-select: none;
}

.message-bubble {
  border-radius: 8px;
  padding: 10px 14px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.message-bubble.user {
  color: var(--v-theme-primaryText);
  padding: 12px 18px;
  font-size: 15px;
  max-width: 100%;
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

.inline-message-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: min(420px, 72vw);
}

.inline-message-editor-input {
  width: 100%;
  min-height: 0;
  max-height: 220px;
  padding: 0;
  border: 0;
  outline: 0;
  resize: vertical;
  background: transparent;
  color: inherit;
  font: inherit;
  line-height: 1.65;
  white-space: pre-wrap;
}

.inline-message-editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 2px;
}

.inline-message-editor-action {
  min-height: 34px;
  padding: 0 14px;
  border-radius: 14px;
}

.loading-message {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  color: var(--chat-muted);
}

.chat-message-list :deep(.markdown-content p) {
  margin: 0.25rem 0;
}

.unknown-part {
  max-width: 100%;
  overflow-x: auto;
  border-radius: 8px;
  padding: 10px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  font-size: 13px;
  line-height: 1.5;
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

.message-bubble.bot
  > .tool-call-block:first-child
  :deep(.tool-call-card:first-child) {
  margin-top: 0;
}

.tool-call-inline-status {
  color: var(--chat-muted);
  font-size: 12px;
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

.message-thread-meta {
  min-height: 24px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 0;
  border-radius: 8px;
  padding: 0 6px;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 12px;
  line-height: 24px;
  cursor: pointer;
}

.message-thread-meta:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.thread-menu-item {
  max-width: min(320px, 72vw);
}

.thread-menu-title {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
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
  margin-bottom: 4px;
  padding: 2px 0;
  font-size: 13px;
  line-height: 1.35;
}

.stats-row span {
  color: var(--chat-muted);
}

.stats-row strong {
  font-size: 12px;
  font-weight: 600;
}

.threaded-message-content {
  color: inherit;
}

.image-preview-overlay {
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-image {
  max-width: min(92vw, 1200px);
  max-height: 90vh;
  object-fit: contain;
  cursor: zoom-out;
}

.variant-thread .messages-list {
  gap: 14px;
}

.variant-thread .message-stack {
  max-width: min(300px, 86%);
}

.variant-thread .from-user .message-stack {
  max-width: 78%;
}

.variant-thread .bot-avatar-symbol {
  font-size: 24px;
}

.variant-thread .from-bot .bot-avatar {
  display: none;
}

.variant-thread .from-bot .message-stack {
  max-width: 100%;
}

.variant-thread .message-bubble {
  padding: 9px 12px;
  border-radius: 18px;
  font-size: 14px;
}

.variant-thread .message-bubble.user {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgb(var(--v-theme-on-surface));
  color: rgb(var(--v-theme-surface));
}

.variant-thread .message-bubble.bot {
  border: 0;
  background: transparent;
  padding-left: 12px;
}

@media (max-width: 760px) {
  .messages-list {
    gap: 18px;
  }

  .message-row.from-bot {
    flex-direction: column;
    gap: 2px;
  }

  .message-row.from-bot .bot-avatar {
    display: none;
  }

  .message-row.from-bot .message-stack {
    max-width: 100%;
  }

  .message-stack {
    max-width: 88%;
  }

  .from-user .message-stack {
    max-width: 82%;
  }

  .sent-file-card {
    width: min(220px, calc(100vw - 28px));
    height: 58px;
  }

  .sent-image-card {
    width: 58px;
    height: 58px;
  }

  .sent-attachments.images-only .sent-image-card {
    width: min(180px, calc(100vw - 52px));
    height: min(180px, calc(100vw - 52px));
  }

  .message-bubble {
    padding: 9px 12px;
  }

  .message-bubble.user {
    padding: 10px 14px;
  }

  .inline-message-editor {
    min-width: min(100%, calc(100vw - 36px));
  }

  .image-part img {
    max-width: min(100%, calc(100vw - 36px));
    max-height: 300px;
  }

  .video-part {
    max-height: 300px;
  }

  .variant-thread .messages-list {
    gap: 12px;
  }

  .variant-thread .message-stack,
  .variant-thread .from-bot .message-stack {
    max-width: 100%;
  }

  .variant-thread .from-user .message-stack {
    max-width: 82%;
  }

  .variant-thread .message-bubble.bot {
    padding-left: 0;
  }
}
</style>
