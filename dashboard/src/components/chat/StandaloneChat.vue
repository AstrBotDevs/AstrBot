<template>
  <div class="standalone-chat">
    <section class="standalone-messages">
      <div v-if="initializing" class="standalone-state">
        <v-progress-circular indeterminate size="28" width="3" />
      </div>

      <div v-else-if="!activeMessages.length" class="standalone-state">
        <div class="welcome-title">{{ tm("welcome.title") }}</div>
      </div>

      <MessageList
        v-if="!initializing && activeMessages.length"
        ref="messageListRef"
        :curr-session-id="currSessionId"
        :get-session="ensureSession"
        :messages="activeMessages"
        :is-dark="isDark"
        :is-loading-messages="initializing"
        :should-stick-to-bottom="shouldStickToBottom"
        :is-user-message="isUserMessage"
        :is-message-streaming="isMessageStreaming"
        :message-content="messageContent"
        @update:should-stick-to-bottom="shouldStickToBottom = $event"
      />
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
import RefNode from "@/components/chat/message_list_comps/RefNode.vue";
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
import MessageList from "@/components/chat/MessageList.vue";

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
const inputRef = ref<InstanceType<typeof ChatInput> | null>(null);
const messageListRef = ref<InstanceType<typeof MessageList> | null>(null);
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
  messageListRef.value?.scrollToBottom();
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
