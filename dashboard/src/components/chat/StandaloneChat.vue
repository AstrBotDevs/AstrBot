<template>
  <div class="standalone-chat">
    <section ref="messagesContainer" class="standalone-messages">
      <div v-if="initializing" class="standalone-state">
        <v-progress-circular indeterminate size="28" width="3" />
      </div>

      <div v-else-if="!activeMessages.length" class="standalone-state">
        <div class="welcome-title">{{ welcomeTitle ? welcomeTitle : tm("welcome.title") }}</div>
      </div>

      <div v-else class="message-list">
        <ChatMessageList
          :messages="activeMessages"
          :is-dark="isDark"
          :is-streaming="
            Boolean(currSessionId && isSessionRunning(currSessionId))
          "
          :enable-edit="false"
          :enable-regenerate="false"
          :enable-copy="true"
          :manage-refs-sidebar="false"
        />
      </div>
    </v-card-text>
  </v-card>

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
        @paste-image="(e: ClipboardEvent) => handlePaste(e, currSessionId)"
        @file-select="handleFilesSelected"
        :uploadFilesDisabled="!attachmentEnabled"
        :providerModelMenuDisabled="widgetModel"
        :config-selector-disabled="widgetModel"
        :recordDisabled="!attachmentEnabled"
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
import RefNode from "@/components/chat/message_list_comps/RefNode.vue";
import ThemeAwareMarkdownCodeBlock from "@/components/shared/ThemeAwareMarkdownCodeBlock.vue";
import { useMediaHandling } from "@/composables/useMediaHandling";
import ChatMessageList from "@/components/chat/ChatMessageList.vue";
import {
  useMessages,
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

const props = withDefaults(
  defineProps<{
    configId?: string | null,
    widgetModel?: boolean,
    apiPackage?: Record<string, string> | null,
    apiPackageData?: Record<string, string> | null,
    attachmentEnabled?: boolean,
    welcomeTitle?: string,
  }>(),
  {
    configId: "default",
    widgetModel: false,
    apiPackage: null,
    apiPackageData: null,
    attachmentEnabled: true,
    welcomeTitle: '',
  }
);

const { t } = useI18n();
const { error: showError } = useToast();

// UI 状态
const imagePreviewDialog = ref(false);
const previewImageUrl = ref("");

// 会话管理（不使用 useSessions 避免路由跳转）
const currSessionId = ref("");
const getCurrentSession = computed(() => null); // 独立测试模式不需要会话信息

const isDark = computed(() => customizer.uiTheme === "PurpleThemeDark");

if (props.widgetModel) {
  currSessionId.value = props.apiPackageData?.session_id ?? '';
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
  chatWidgetSetApiPackage,
} = useMediaHandling();

const {
  sending,
  activeMessages,
  isSessionRunning,
  createLocalExchange,
  sendMessageStream,
  stopSession,
  widgetSetApiPackage,
  loadSessionMessages,
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
    clearStaged({ revokeUrls: false });

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
  await ensureSession();
  inputRef.value?.focusInput();
  if (props.widgetModel) {
    initializing.value = true;
    chatWidgetSetApiPackage(props.apiPackage ?? {});
    widgetSetApiPackage(props.apiPackage ?? {});
    loadSessionMessages(props.apiPackageData?.session_id ?? '')
    .then()
    .finally(() => {
      initializing.value = false
    });
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

  sendMessageStream({
    sessionId,
    messageId,
    parts,
    transport: props.widgetModel ? 'sse' : transportMode.value,
    enableStreaming: enableStreaming.value,
    selectedProvider: props.widgetModel ? '' : (selection?.providerId || ""),
    selectedModel: props.widgetModel ? '' : (selection?.modelName || ""),
    botRecord,
  });
  // 等半秒后再清理，有些浏览器清理太快会导致图片显示异常
  setTimeout(() => {
    draft.value = "";
    clearStaged({ revokeUrls: false });
    scrollToBottom();
  }, 500)
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

async function stopCurrentSession() {
  if (!currSessionId.value) return;
  await stopSession(currSessionId.value);
}

async function handleFilesSelected(files: FileList) {
  const selectedFiles = Array.from(files || []);
  for (const file of selectedFiles) {
    if (file.type.startsWith("image/")) {
      await processAndUploadImage(file, currSessionId.value);
    } else {
      await processAndUploadFile(file, currSessionId.value);
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

.image-part img {
  max-width: min(360px, 100%);
  max-height: 320px;
  border-radius: 8px;
  object-fit: contain;
}

.message-bubble.bot
  > .tool-call-block:first-child
  :deep(.tool-call-card:first-child) {
  margin-top: 0;
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
@media (max-width: 760px) {
  .standalone-composer {
    padding-bottom: 0;
  }
}
</style>
