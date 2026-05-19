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

if (props.widgetModel) {
  currSessionId.value = props.apiPackageData?.session_id ?? '';
}

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

const transportMode = computed<TransportMode>(() =>
  (localStorage.getItem("chat.transportMode") as TransportMode) === "websocket"
    ? "websocket"
    : "sse",
);

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
