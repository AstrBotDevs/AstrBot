<template>
  <div class="standalone-chat">
    <section ref="messagesContainer" class="standalone-messages">
      <div v-if="initializing" class="standalone-state">
        <v-progress-circular indeterminate size="28" width="3" />
      </div>

      <div v-else-if="!activeMessages.length" class="standalone-state">
        <div class="welcome-title">{{ tm("welcome.title") }}</div>
      </div>

      <div v-else class="message-list">
        <div
          v-for="(msg, msgIndex) in activeMessages"
          :key="msg.id || `${msgIndex}-${msg.created_at || ''}`"
          class="message-row"
          :class="isUserMessage(msg) ? 'from-user' : 'from-bot'"
        >
          <div class="message-stack">
            <div
              class="message-bubble"
              :class="{ user: isUserMessage(msg), bot: !isUserMessage(msg) }"
            >
              <div v-if="messageContent(msg).isLoading" class="loading-message">
                {{ tm("message.loading") }}
              </div>

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
                  v-for="(part, partIndex) in messageParts(msg)"
                  :key="`${msgIndex}-${partIndex}-${part.type}`"
                >
                  <div
                    v-if="part.type === 'plain' && isUserMessage(msg)"
                    class="plain-content"
                  >
                    {{ part.text || "" }}
                  </div>

                  <MarkdownMessagePart
                    v-else-if="part.type === 'plain'"
                    :content="part.text || ''"
                    :refs="messageRefs(msg)"
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

                  <pre v-else class="unknown-part">{{ formatJson(part) }}</pre>
                </template>
              </template>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="standalone-composer">
      <ChatInput
        ref="inputRef"
        v-model:prompt="draft"
        :staged-images-url="stagedImagesUrl"
        :staged-audio-url="stagedAudioUrl"
        :staged-files="stagedNonImageFiles"
        :disabled="sending || initializing"
        :enable-streaming="enableStreaming"
        :is-recording="false"
        :is-running="Boolean(currSessionId && isSessionRunning(currSessionId))"
        :session-id="currSessionId || null"
        :current-session="currentSession"
        :config-id="configId || 'default'"
        send-shortcut="enter"
        @send="sendCurrentMessage"
        @stop="stopCurrentSession"
        @toggle-streaming="enableStreaming = !enableStreaming"
        @remove-image="removeImage"
        @remove-audio="removeAudio"
        @remove-file="removeFile"
        @paste-image="handlePaste"
        @file-select="handleFilesSelected"
      />
    </section>

    <v-overlay
      v-model="imagePreview.visible"
      class="image-preview-overlay"
      scrim="rgba(0, 0, 0, 0.86)"
      @click="closeImage"
    >
      <img class="preview-image" :src="imagePreview.url" alt="preview" />
    </v-overlay>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
} from "vue";
import axios from "axios";
import { setCustomComponents } from "markstream-vue";
import "markstream-vue/index.css";
import ChatInput from "@/components/chat/ChatInput.vue";
import IPythonToolBlock from "@/components/chat/message_list_comps/IPythonToolBlock.vue";
import MarkdownMessagePart from "@/components/chat/message_list_comps/MarkdownMessagePart.vue";
import ReasoningBlock from "@/components/chat/message_list_comps/ReasoningBlock.vue";
import RefNode from "@/components/chat/message_list_comps/RefNode.vue";
import ToolCallCard from "@/components/chat/message_list_comps/ToolCallCard.vue";
import ToolCallItem from "@/components/chat/message_list_comps/ToolCallItem.vue";
import ThemeAwareMarkdownCodeBlock from "@/components/shared/ThemeAwareMarkdownCodeBlock.vue";
import { useMediaHandling } from "@/composables/useMediaHandling";
import {
  useMessages,
  type ChatRecord,
  type MessagePart,
  type TransportMode,
} from "@/composables/useMessages";
import type { Session } from "@/composables/useSessions";
import { useModuleI18n } from "@/i18n/composables";
import { useCustomizerStore } from "@/stores/customizer";
import { buildWebchatUmoDetails } from "@/utils/chatConfigBinding";

const props = withDefaults(defineProps<{ configId?: string | null }>(), {
  configId: "default",
});

setCustomComponents("chat-message", {
  ref: RefNode,
  code_block: ThemeAwareMarkdownCodeBlock,
});

const { tm } = useModuleI18n("features/chat");
const customizer = useCustomizerStore();
const currSessionId = ref("");
const currentSession = ref<Session | null>(null);
const draft = ref("");
const initializing = ref(false);
const enableStreaming = ref(true);
const shouldStickToBottom = ref(true);
const messagesContainer = ref<HTMLElement | null>(null);
const inputRef = ref<InstanceType<typeof ChatInput> | null>(null);
const imagePreview = reactive({ visible: false, url: "" });

const isDark = computed(() => customizer.uiTheme === "PurpleThemeDark");
const customMarkdownTags = ["ref"];

const {
  stagedFiles,
  stagedImagesUrl,
  stagedAudioUrl,
  stagedNonImageFiles,
  processAndUploadImage,
  processAndUploadFile,
  handlePaste,
  removeImage,
  removeAudio,
  removeFile,
  clearStaged,
  cleanupMediaCache,
} = useMediaHandling();

const {
  sending,
  activeMessages,
  isSessionRunning,
  isMessageStreaming,
  isUserMessage,
  messageContent,
  messageParts,
  createLocalExchange,
  sendMessageStream,
  stopSession,
} = useMessages({
  currentSessionId: currSessionId,
  onStreamUpdate: () => {
    if (shouldStickToBottom.value) {
      scrollToBottom();
    }
  },
});

const transportMode = computed<TransportMode>(() =>
  (localStorage.getItem("chat.transportMode") as TransportMode) === "websocket"
    ? "websocket"
    : "sse",
);

onMounted(async () => {
  await ensureSession();
  inputRef.value?.focusInput();
});

onBeforeUnmount(() => {
  cleanupMediaCache();
});

async function ensureSession() {
  if (currSessionId.value) return currSessionId.value;
  initializing.value = true;
  try {
    const response = await axios.get("/api/chat/new_session");
    const session = response.data?.data as Session;
    currSessionId.value = session.session_id;
    currentSession.value = session;
    await bindConfigToSession(session.session_id);
    return session.session_id;
  } finally {
    initializing.value = false;
  }
}

async function bindConfigToSession(sessionId: string) {
  const confId = props.configId || "default";
  const umo = buildWebchatUmoDetails(sessionId, false).umo;
  await axios.post("/api/config/umo_abconf_route/update", {
    umo,
    conf_id: confId,
  });
}

async function sendCurrentMessage() {
  if (!draft.value.trim() && !stagedFiles.value.length) return;
  const sessionId = await ensureSession();
  const text = draft.value.trim();
  const parts = buildOutgoingParts(text);
  const messageId = crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  const selection = inputRef.value?.getCurrentSelection();
  const { botRecord } = createLocalExchange({ sessionId, messageId, parts });

  draft.value = "";
  clearStaged();
  scrollToBottom();

  sendMessageStream({
    sessionId,
    messageId,
    parts,
    transport: transportMode.value,
    enableStreaming: enableStreaming.value,
    selectedProvider: selection?.providerId || "",
    selectedModel: selection?.modelName || "",
    botRecord,
  });
}

function buildOutgoingParts(text: string): MessagePart[] {
  const parts: MessagePart[] = [];
  if (text) {
    parts.push({ type: "plain", text });
  }
  stagedFiles.value.forEach((file) => {
    parts.push({
      type: file.type,
      attachment_id: file.attachment_id,
      filename: file.filename,
      embedded_url: file.url,
    });
  });
  return parts;
}

function hasNonReasoningContent(message: ChatRecord) {
  return messageParts(message).some((part) => {
    if (part.type === "reply") return false;
    if (part.type === "plain") return Boolean(String(part.text || "").trim());
    return true;
  });
}

async function stopCurrentSession() {
  if (!currSessionId.value) return;
  await stopSession(currSessionId.value);
}

async function handleFilesSelected(files: FileList) {
  const selectedFiles = Array.from(files || []);
  for (const file of selectedFiles) {
    if (file.type.startsWith("image/")) {
      await processAndUploadImage(file);
    } else {
      await processAndUploadFile(file);
    }
  }
}

function scrollToBottom() {
  nextTick(() => {
    const container = messagesContainer.value;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
    shouldStickToBottom.value = true;
  });
}

function messageRefs(message: ChatRecord) {
  const refs = messageContent(message).refs;
  if (refs && typeof refs === "object" && Array.isArray(refs.used)) {
    return refs as { used?: Array<Record<string, unknown>> };
  }
  return null;
}

function partUrl(part: MessagePart) {
  if (part.embedded_url) return part.embedded_url;
  if (part.embedded_file?.url) return part.embedded_file.url;
  if (part.attachment_id)
    return `/api/chat/get_attachment?attachment_id=${encodeURIComponent(
      part.attachment_id,
    )}`;
  if (part.filename)
    return `/api/chat/get_file?filename=${encodeURIComponent(part.filename)}`;
  return "";
}

function normalizeToolCall(tool: Record<string, unknown>) {
  const normalized = { ...tool };
  normalized.args = parseJsonSafe(normalized.args || normalized.arguments);
  normalized.result = parseJsonSafe(normalized.result);
  if (!normalized.ts) normalized.ts = Date.now() / 1000;
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

function formatJson(value: unknown) {
  if (typeof value === "string") return value;
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

function openImage(url: string) {
  imagePreview.url = url;
  imagePreview.visible = true;
}

function closeImage() {
  imagePreview.visible = false;
  imagePreview.url = "";
}
</script>

<style scoped>
.standalone-chat {
  --standalone-muted: rgba(var(--v-theme-on-surface), 0.62);
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: rgb(var(--v-theme-background));
}

.standalone-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 22px 14px;
}

.standalone-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.welcome-title {
  font-size: 24px;
  font-weight: 700;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.message-row {
  display: flex;
}

.message-row.from-user {
  justify-content: flex-end;
}

.message-stack {
  max-width: 88%;
}

.from-user .message-stack {
  max-width: 70%;
}

.message-bubble {
  border-radius: 8px;
  padding: 10px 14px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.message-bubble.user {
  padding: 12px 18px;
  border-radius: 1.5rem;
  background: rgba(var(--v-theme-primary), 0.12);
}

.message-bubble.bot {
  padding-left: 0;
  background: transparent;
}

.plain-content {
  white-space: pre-wrap;
}

.loading-message,
.tool-call-inline-status {
  color: var(--standalone-muted);
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
  max-width: min(360px, 100%);
  max-height: 320px;
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
  max-height: 320px;
  border-radius: 8px;
}

.file-part {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
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

.unknown-part {
  max-width: 100%;
  overflow-x: auto;
  border-radius: 8px;
  padding: 10px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  font-size: 13px;
  line-height: 1.5;
}

.standalone-composer {
  position: relative;
  z-index: 1;
  padding-bottom: 10px;
  background: rgb(var(--v-theme-background));
}

.standalone-composer::before {
  content: "";
  position: absolute;
  z-index: -1;
  left: 0;
  right: 0;
  top: -32px;
  height: 32px;
  pointer-events: none;
  background: linear-gradient(
    to bottom,
    rgba(var(--v-theme-background), 0),
    rgb(var(--v-theme-background))
  );
}

.standalone-composer :deep(.input-area) {
  border-top: 0;
}

.image-preview-overlay {
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-image {
  max-width: min(92vw, 1000px);
  max-height: 88vh;
  border-radius: 8px;
  object-fit: contain;
}
</style>
