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
                <template
                  v-for="(block, blockIndex) in renderBlocks(msg)"
                  :key="`${msgIndex}-block-${blockIndex}-${block.kind}`"
                >
                  <ReasoningBlock
                    v-if="block.kind === 'thinking'"
                    :parts="block.parts"
                    :is-dark="isDark"
                    :initial-expanded="false"
                    :is-streaming="isMessageStreaming(msg, msgIndex)"
                    :has-non-reasoning-content="
                      hasFollowingContentBlock(msg, blockIndex)
                    "
                  />

                  <template v-else>
                    <template
                      v-for="(part, partIndex) in block.parts"
                      :key="`${msgIndex}-${blockIndex}-${partIndex}-${part.type}`"
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
                </template>
              </template>
            </div>
            <p class="text-caption text-medium-emphasis mt-2">
              测试配置: {{ configId || "default" }}
            </p>
          </div>

          <!-- 输入区域 -->
          <ChatInput
            ref="chatInputRef"
            v-model:prompt="prompt"
            :staged-images-url="stagedImagesUrl"
            :staged-audio-url="stagedAudioUrl"
            :disabled="isStreaming"
            :is-running="isStreaming || isConvRunning"
            :enable-streaming="enableStreaming"
            :is-recording="isRecording"
            :session-id="currSessionId || null"
            :current-session="getCurrentSession"
            :config-id="configId"
            @send="handleSendMessage"
            @stop="handleStopMessage"
            @toggleStreaming="toggleStreaming"
            @removeImage="removeImage"
            @removeAudio="removeAudio"
            @startRecording="handleStartRecording"
            @stopRecording="handleStopRecording"
            @pasteImage="handlePaste"
            @fileSelect="handleFileSelect"
          />
        </div>
      </div>
    </v-card-text>
  </v-card>

  <!-- 图片预览对话框 -->
  <v-dialog v-model="imagePreviewDialog" max-width="90vw" max-height="90vh">
    <v-card class="image-preview-card" elevation="8">
      <v-card-title class="d-flex justify-space-between align-center pa-4">
        <span>{{ t("core.common.imagePreview") }}</span>
        <v-btn
          icon="mdi-close"
          variant="text"
          @click="imagePreviewDialog = false"
        />
      </v-card-title>
      <v-card-text class="text-center pa-4">
        <img :src="previewImageUrl" class="preview-image-large" />
      </v-card-text>
    </v-card>
  </v-dialog>
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
  displayParts as displayMessageParts,
  messageBlocks as buildMessageBlocks,
  type MessageDisplayBlock,
  useMessages,
  type ChatRecord,
  type MessagePart,
  type TransportMode,
} from "@/composables/useMessages";
import type { Session } from "@/composables/useSessions";
import { useModuleI18n } from "@/i18n/composables";
import { useCustomizerStore } from "@/stores/customizer";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import MessageList from "@/components/chat/MessageList.vue";
import ChatInput from "@/components/chat/ChatInput.vue";
import { useMessages } from "@/composables/useMessages";
import { useMediaHandling } from "@/composables/useMediaHandling";
import { useRecording } from "@/composables/useRecording";
import { useToast } from "@/utils/toast";
import { buildWebchatUmoDetails } from "@/utils/chatConfigBinding";

interface Props {
  configId?: string | null;
}

const props = withDefaults(defineProps<Props>(), {
  configId: null,
});

const { t } = useI18n();
const { error: showError } = useToast();

// UI 状态
const imagePreviewDialog = ref(false);
const previewImageUrl = ref("");

// 会话管理（不使用 useSessions 避免路由跳转）
const currSessionId = ref("");
const getCurrentSession = computed(() => null); // 独立测试模式不需要会话信息

async function bindConfigToSession(sessionId: string) {
  const confId = (props.configId || "").trim();
  if (!confId || confId === "default") {
    return;
  }

  const umoDetails = buildWebchatUmoDetails(sessionId, false);

  await axios.post("/api/config/umo_abconf_route/update", {
    umo: umoDetails.umo,
    conf_id: confId,
  });
}

async function newSession() {
  try {
    const response = await axios.get("/api/chat/new_session");
    const sessionId = response.data.data.session_id;

    try {
      await bindConfigToSession(sessionId);
    } catch (err) {
      console.error("Failed to bind config to session", err);
    }

    currSessionId.value = sessionId;

    return sessionId;
  } catch (err) {
    console.error(err);
    throw err;
  }
}

function updateSessionTitle(sessionId: string, title: string) {
  // 独立模式不需要更新会话标题
}

function getSessions() {
  // 独立模式不需要加载会话列表
}

const {
  stagedImagesUrl,
  stagedAudioUrl,
  stagedFiles,
  getMediaFile,
  processAndUploadImage,
  handlePaste,
  removeImage,
  removeAudio,
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

const {
  messages,
  isStreaming,
  isConvRunning,
  enableStreaming,
  getSessionMessages: getSessionMsg,
  sendMessage: sendMsg,
  stopMessage: stopMsg,
  toggleStreaming,
} = useMessages(currSessionId, getMediaFile, updateSessionTitle, getSessions);

// 组件引用
const messageList = ref<InstanceType<typeof MessageList> | null>(null);
const chatInputRef = ref<InstanceType<typeof ChatInput> | null>(null);

// 输入状态
const prompt = ref("");

const isDark = computed(() => useCustomizerStore().isDarkTheme);

function openImagePreview(imageUrl: string) {
  previewImageUrl.value = imageUrl;
  imagePreviewDialog.value = true;
}

async function handleStartRecording() {
  await startRec();
}

async function handleStopRecording() {
  const audioFilename = await stopRec();
  stagedAudioUrl.value = audioFilename;
}

async function handleFileSelect(files: FileList) {
  for (const file of Array.from(files)) {
    await processAndUploadImage(file);
  }
}

async function handleSendMessage() {
  if (
    !prompt.value.trim() &&
    stagedFiles.value.length === 0 &&
    !stagedAudioUrl.value
  ) {
    return;
  }

  try {
    if (!currSessionId.value) {
      await newSession();
    }

    const promptToSend = prompt.value.trim();
    const audioNameToSend = stagedAudioUrl.value;
    const filesToSend = stagedFiles.value.map((f) => ({
      attachment_id: f.attachment_id,
      url: f.url,
      original_name: f.original_name,
      type: f.type,
    }));

    // 清空输入和附件
    prompt.value = "";
    clearStaged();

    // 获取选择的提供商和模型
    const selection = chatInputRef.value?.getCurrentSelection();
    const selectedProviderId = selection?.providerId || "";
    const selectedModelName = selection?.modelName || "";

    await sendMsg(
      promptToSend,
      filesToSend,
      audioNameToSend,
      selectedProviderId,
      selectedModelName,
    );

    // 滚动到底部
    nextTick(() => {
      messageList.value?.scrollToBottom();
    });
  } catch (err) {
    console.error("Failed to send message:", err);
    showError(t("features.chat.errors.sendMessageFailed"));
    // 恢复输入内容，让用户可以重试
    // 注意：附件已经上传到服务器，所以不恢复附件
  }
}

async function handleStopMessage() {
  await stopMsg();
}

onMounted(async () => {
  // 独立模式在挂载时创建新会话
  try {
    await newSession();
  } catch (err) {
    console.error("Failed to create initial session:", err);
    showError(t("features.chat.errors.createSessionFailed"));
  }
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
  clearStaged({ revokeUrls: false });
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
  return renderBlocks(message).some((block) => block.kind === "content");
}

function bubbleParts(message: ChatRecord) {
  return displayMessageParts(messageContent(message));
}

function renderBlocks(message: ChatRecord): MessageDisplayBlock[] {
  if (isUserMessage(message)) {
    const parts = bubbleParts(message);
    return parts.length ? [{ kind: "content", parts }] : [];
  }
  return buildMessageBlocks(messageContent(message));
}

function hasFollowingContentBlock(message: ChatRecord, blockIndex: number) {
  return renderBlocks(message)
    .slice(blockIndex + 1)
    .some((block) => block.kind === "content");
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
/* 基础动画 */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.standalone-chat-card {
  width: 100%;
  height: 100%;
  max-height: 100%;
  overflow: hidden;
}

.standalone-chat-container {
  width: 100%;
  height: 100%;
  max-height: 100%;
  padding: 0;
  overflow: hidden;
}

.chat-layout {
  height: 100%;
  max-height: 100%;
  display: flex;
  overflow: hidden;
}

.chat-content-panel {
  height: 100%;
  max-height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.conversation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  padding-left: 16px;
  border-bottom: 1px solid var(--v-theme-border);
  width: 100%;
  padding-right: 32px;
  flex-shrink: 0;
}

.conversation-header-info h4 {
  margin: 0;
  font-weight: 500;
}

.conversation-header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.welcome-container {
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: column;
}

.welcome-title {
  font-size: 28px;
  margin-bottom: 8px;
}

.bot-name {
  font-weight: 700;
  margin-left: 8px;
  color: var(--v-theme-secondary);
}

.fade-in {
  animation: fadeIn 0.3s ease-in-out;
}

.preview-image-large {
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
}
</style>
