<template>
  <div
    class="input-area fade-in"
    :class="{ 'is-dark': isDark }"
    @dragover.prevent="handleDragOver"
    @dragleave.prevent="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <div
      class="input-container"
      :style="{
        width: '85%',
        maxWidth: '900px',
        margin: '0 auto',
        border: isDark ? 'none' : '1px solid #e0e0e0',
        borderRadius: '24px',
        boxShadow: isDark ? 'none' : '0px 2px 2px rgba(0, 0, 0, 0.1)',
        backgroundColor: isDark ? '#2d2d2d' : 'transparent',
        position: 'relative',
        transition: 'min-height 0.2s ease, padding 0.2s ease',
      }"
    >
      <!-- 拖拽上传遮罩 -->
      <transition name="fade">
        <div v-if="isDragging" class="drop-overlay">
          <div class="drop-overlay-content">
            <v-icon size="48" color="primary">mdi-cloud-upload</v-icon>
            <span class="drop-text">{{ tm("input.dropToUpload") }}</span>
          </div>
        </div>
      </transition>
      <!-- 引用预览区 -->
      <transition name="slideReply" @after-leave="handleReplyAfterLeave">
        <div class="reply-preview" v-if="props.replyTo && !isReplyClosing">
          <div class="reply-content">
            <v-icon size="small" class="reply-icon">mdi-reply</v-icon>
            "<span class="reply-text">{{ props.replyTo.selectedText }}</span
            >"
          </div>
          <v-btn
            @click="handleClearReply"
            class="remove-reply-btn"
            icon="mdi-close"
            size="x-small"
            color="grey"
            variant="text"
          />
        </div>
      </transition>

      <transition name="attachments">
        <div class="attachments-preview" v-if="hasStagedAttachments">
          <div
            v-for="(img, index) in stagedImagesUrl"
            :key="'img-' + index"
            class="attachment-card image-preview"
          >
            <img :src="img" class="preview-image" alt="attachment preview" />
            <v-btn
              @click="$emit('removeImage', index)"
              class="remove-attachment-btn"
              icon="mdi-close"
              size="x-small"
              color="error"
              variant="tonal"
            />
          </div>

          <div v-if="stagedAudioUrl" class="attachment-card audio-preview">
            <div class="attachment-icon attachment-icon--audio">
              <v-icon icon="mdi-microphone" size="24"></v-icon>
            </div>
            <span class="attachment-name">{{ tm("voice.recording") }}</span>
            <v-btn
              @click="$emit('removeAudio')"
              class="remove-attachment-btn"
              icon="mdi-close"
              size="x-small"
              color="error"
              variant="tonal"
            />
          </div>

          <div
            v-for="(file, index) in stagedFiles"
            :key="'file-' + index"
            class="attachment-card file-preview"
          >
            <div
              class="attachment-icon"
              :style="{ color: filePresentation(file).color }"
            >
              <v-icon :icon="filePresentation(file).icon" size="24"></v-icon>
              <span class="attachment-ext">{{
                filePresentation(file).label
              }}</span>
            </div>
            <span class="attachment-name">{{ file.original_name }}</span>
            <v-btn
              @click="$emit('removeFile', index)"
              class="remove-attachment-btn"
              icon="mdi-close"
              size="x-small"
              color="error"
              variant="tonal"
            />
          </div>
        </div>
      </transition>

      <div class="textarea-shell">
        <div
          ref="highlightLayer"
          class="textarea-highlight"
          :class="{ 'is-composing': isComposing }"
          aria-hidden="true"
        >
          <template v-for="(segment, index) in highlightedPrompt" :key="index">
            <span :class="{ 'textarea-mention': segment.mention }">{{
              segment.text
            }}</span>
          </template>
        </div>
        <textarea
          ref="inputField"
          v-model="localPrompt"
          :class="{ 'is-composing': isComposing }"
          @input="handlePromptInput"
          @scroll="syncHighlightScroll"
          @keydown="handleKeyDown"
          @compositionstart="isComposing = true"
          @compositionend="handleCompositionEnd"
          :disabled="disabled"
          placeholder="Ask AstrBot..."
          class="chat-textarea"
          autocomplete="off"
          autocorrect="off"
          autocapitalize="sentences"
          spellcheck="false"
        ></textarea>
      </div>
      <div v-if="mentionMenuOpen" class="mention-menu">
        <button
          v-for="(bot, index) in filteredMentionBots"
          :key="bot.bot_id"
          class="mention-option"
          :class="{ active: index === activeMentionIndex }"
          type="button"
          @mousedown.prevent="selectMentionBot(bot)"
        >
          <v-avatar size="24" rounded="lg">
            <img v-if="bot.avatar" :src="bot.avatar" alt="" />
            <span v-else>{{ bot.name.slice(0, 1).toUpperCase() }}</span>
          </v-avatar>
          <span class="mention-option-name">{{ bot.name }}</span>
          <v-chip size="x-small" variant="tonal">Bot</v-chip>
        </button>
      </div>
      <div
        style="
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 6px 14px;
        "
      >
        <div
          style="
            display: flex;
            justify-content: flex-start;
            margin-top: 4px;
            align-items: center;
            gap: 8px;
            min-width: 0;
            flex: 1;
            overflow: hidden;
          "
        >
          <!-- Settings Menu -->
          <StyledMenu
            offset="8"
            location="top start"
            :close-on-content-click="false"
          >
            <template v-slot:activator="{ props: activatorProps }">
              <v-btn
                v-bind="activatorProps"
                icon="mdi-plus"
                variant="outlined"
                class="input-neutral-btn input-outline-control"
              />
            </template>

            <!-- Upload Files -->
            <v-list-item
              class="styled-menu-item"
              rounded="md"
              @click="triggerImageInput"
            >
              <template v-slot:prepend>
                <v-icon icon="mdi-file-upload" size="small"></v-icon>
              </template>
              <v-list-item-title>
                {{ tm("input.upload") }}
              </v-list-item-title>
            </v-list-item>

            <!-- Config Selector in Menu -->
            <ConfigSelector
              :session-id="sessionId || null"
              :platform-id="sessionPlatformId"
              :is-group="sessionIsGroup"
              :initial-config-id="props.configId"
              @config-changed="handleConfigChange"
            />

            <!-- Streaming Toggle in Menu -->
            <v-list-item
              class="styled-menu-item"
              rounded="md"
              @click="$emit('toggleStreaming')"
            >
              <template v-slot:prepend>
                <v-icon icon="mdi-lightning-bolt" size="small"></v-icon>
              </template>
              <v-list-item-title>
                {{
                  enableStreaming
                    ? tm("streaming.enabled")
                    : tm("streaming.disabled")
                }}
              </v-list-item-title>
            </v-list-item>
          </StyledMenu>

          <!-- Provider/Model Selector Menu -->
          <ProviderModelMenu
            v-if="showProviderSelector && !sessionIsGroup"
            ref="providerModelMenuRef"
          />
        </div>
        <div
          style="
            display: flex;
            justify-content: flex-end;
            margin-top: 8px;
            align-items: center;
            flex-shrink: 0;
          "
        >
          <input
            type="file"
            ref="imageInputRef"
            @change="handleFileSelect"
            style="display: none"
            multiple
          />
          <v-progress-circular
            v-if="disabled && !mobile"
            indeterminate
            size="16"
            class="mr-1"
            width="1.5"
          />
          <!-- <v-btn @click="$emit('openLiveMode')"
                        icon
                        variant="text"
                        color="purple" 
                        size="small"
                    >
                        <v-icon icon="mdi-phone-in-talk" variant="text" plain></v-icon>
                        <v-tooltip activator="parent" location="top">
                            {{ tm('voice.liveMode') }}
                        </v-tooltip>
                    </v-btn> -->
          <v-btn
            @click="handleRecordClick"
            icon
            variant="text"
            class="record-btn input-icon-btn"
          >
            <v-icon
              :icon="isRecording ? 'mdi-stop-circle' : 'mdi-microphone'"
              variant="text"
              plain
            ></v-icon>
            <v-tooltip activator="parent" location="top">
              {{
                isRecording ? tm("voice.speaking") : tm("voice.startRecording")
              }}
            </v-tooltip>
          </v-btn>
          <v-btn
            icon
            v-if="showStopButton"
            @click="$emit('stop')"
            variant="tonal"
            class="send-btn input-action-btn"
          >
            <v-icon icon="mdi-stop" variant="text" plain></v-icon>
            <v-tooltip activator="parent" location="top">
              {{ tm("input.stopGenerating") }}
            </v-tooltip>
          </v-btn>
          <v-btn
            v-else
            @click="$emit('send')"
            icon="mdi-arrow-up"
            variant="tonal"
            :disabled="!canSend"
            class="send-btn input-action-btn"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ref,
  computed,
  watch,
  nextTick,
  onMounted,
  onBeforeUnmount,
} from "vue";
import { useDisplay } from "vuetify";
import { useModuleI18n } from "@/i18n/composables";
import { useCustomizerStore } from "@/stores/customizer";
import ConfigSelector from "./ConfigSelector.vue";
import ProviderModelMenu from "./ProviderModelMenu.vue";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import type { Session } from "@/composables/useSessions";

interface StagedFileInfo {
  attachment_id: string;
  filename: string;
  original_name: string;
  url: string;
  type: string;
}

interface ReplyInfo {
  messageId: string | number;
  selectedText?: string;
}

interface MentionableBot {
  bot_id: string;
  name: string;
  avatar?: string;
  conf_id?: string;
}

interface Props {
  prompt: string;
  stagedImagesUrl: string[];
  stagedAudioUrl: string;
  stagedFiles?: StagedFileInfo[];
  disabled: boolean;
  enableStreaming: boolean;
  isRecording: boolean;
  isRunning: boolean;
  sessionId?: string | null;
  currentSession?: Session | null;
  configId?: string | null;
  replyTo?: ReplyInfo | null;
  sendShortcut?: "enter" | "shift_enter";
  mentionableBots?: MentionableBot[];
}

const props = withDefaults(defineProps<Props>(), {
  sessionId: null,
  currentSession: null,
  configId: null,
  stagedFiles: () => [],
  replyTo: null,
  sendShortcut: "shift_enter",
  mentionableBots: () => [],
});

const emit = defineEmits<{
  "update:prompt": [value: string];
  send: [];
  stop: [];
  toggleStreaming: [];
  removeImage: [index: number];
  removeAudio: [];
  removeFile: [index: number];
  startRecording: [];
  stopRecording: [];
  pasteImage: [event: ClipboardEvent];
  fileSelect: [files: FileList];
  clearReply: [];
  openLiveMode: [];
}>();

const { tm } = useModuleI18n("features/chat");
const isDark = computed(
  () => useCustomizerStore().uiTheme === "PurpleThemeDark",
);

const inputField = ref<HTMLTextAreaElement | null>(null);
const highlightLayer = ref<HTMLDivElement | null>(null);
const imageInputRef = ref<HTMLInputElement | null>(null);
const providerModelMenuRef = ref<InstanceType<typeof ProviderModelMenu> | null>(
  null,
);
const showProviderSelector = ref(true);
const isReplyClosing = ref(false);
const isDragging = ref(false);
const selectedMentions = ref<MentionableBot[]>([]);
const mentionMenuOpen = ref(false);
const mentionQuery = ref("");
const mentionStartIndex = ref(-1);
const activeMentionIndex = ref(0);
const isComposing = ref(false);
let dragLeaveTimeout: number | null = null;

const localPrompt = computed({
  get: () => props.prompt,
  set: (value) => emit("update:prompt", value),
});

const sessionPlatformId = computed(
  () => props.currentSession?.platform_id || "webchat",
);
const sessionIsGroup = computed(() => Boolean(props.currentSession?.is_group));

const canSend = computed(() => {
  return (
    (props.prompt && props.prompt.trim()) ||
    props.stagedImagesUrl.length > 0 ||
    props.stagedAudioUrl ||
    (props.stagedFiles && props.stagedFiles.length > 0)
  );
});

const highlightedPrompt = computed(() => {
  const text = localPrompt.value;
  if (!text) return [];
  const mentionNames = props.mentionableBots
    .map((bot) => bot.name)
    .filter(Boolean)
    .sort((a, b) => b.length - a.length);
  if (!mentionNames.length) return [{ text, mention: false }];

  const pattern = new RegExp(
    `(^|\\s)@(${mentionNames.map(escapeRegExp).join("|")})(?=\\s|$)`,
    "gi",
  );
  const segments: Array<{ text: string; mention: boolean }> = [];
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    const prefix = match[1] || "";
    const mentionStart = index + prefix.length;
    if (mentionStart > cursor) {
      segments.push({ text: text.slice(cursor, mentionStart), mention: false });
    }
    segments.push({ text: `@${match[2]}`, mention: true });
    cursor = mentionStart + match[2].length + 1;
  }
  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), mention: false });
  }
  return segments;
});

const filteredMentionBots = computed(() => {
  const query = mentionQuery.value.toLowerCase();
  return props.mentionableBots
    .filter(
      (bot) =>
        !selectedMentions.value.some((item) => item.bot_id === bot.bot_id),
    )
    .filter((bot) => bot.name.toLowerCase().includes(query))
    .slice(0, 6);
});

const isGroupInput = computed(() => props.mentionableBots.length > 0);
const showStopButton = computed(
  () => props.isRunning && !canSend.value && !isGroupInput.value,
);

const hasStagedAttachments = computed(() => {
  return (
    props.stagedImagesUrl.length > 0 ||
    props.stagedAudioUrl ||
    (props.stagedFiles && props.stagedFiles.length > 0)
  );
});

const fileTypeStyles: Record<
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

function fileExtension(file: StagedFileInfo) {
  const name = file.original_name || file.filename || "";
  const extension = name.split(".").pop()?.toLowerCase() || "";
  return extension === name.toLowerCase() ? "" : extension;
}

function filePresentation(file: StagedFileInfo) {
  const extension = fileExtension(file);
  return (
    fileTypeStyles[extension] || {
      color: "#607d8b",
      icon: "mdi-file-document-outline",
      label: extension ? extension.slice(0, 4).toUpperCase() : "FILE",
    }
  );
}

// Ctrl+B 长按录音相关
const ctrlKeyDown = ref(false);
const ctrlKeyTimer = ref<number | null>(null);
const ctrlKeyLongPressThreshold = 300;

// 处理清除引用 - 触发关闭动画
function handleClearReply() {
  isReplyClosing.value = true;
}

// 动画完成后发送clearReply事件
function handleReplyAfterLeave() {
  emit("clearReply");
  isReplyClosing.value = false;
}

const { mobile } = useDisplay();

// Auto-resize textarea
function autoResize() {
  const el = inputField.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 200) + "px";
}

watch(localPrompt, () => {
  nextTick(autoResize);
});

watch(
  () => props.mentionableBots,
  (bots) => {
    if (!bots.length) {
      selectedMentions.value = [];
      closeMentionMenu();
      return;
    }
    const botIds = new Set(bots.map((bot) => bot.bot_id));
    selectedMentions.value = selectedMentions.value.filter((bot) =>
      botIds.has(bot.bot_id),
    );
  },
);

function handleKeyDown(e: KeyboardEvent) {
  if (mentionMenuOpen.value) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeMentionIndex.value =
        (activeMentionIndex.value + 1) %
        Math.max(filteredMentionBots.value.length, 1);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      const length = Math.max(filteredMentionBots.value.length, 1);
      activeMentionIndex.value = (activeMentionIndex.value - 1 + length) % length;
      return;
    }
    if (e.key === "Enter" || e.key === "Tab") {
      const bot = filteredMentionBots.value[activeMentionIndex.value];
      if (bot) {
        e.preventDefault();
        selectMentionBot(bot);
        return;
      }
    }
    if (e.key === "Escape") {
      e.preventDefault();
      closeMentionMenu();
      return;
    }
  }

  const isEnter = e.key === "Enter";
  if (!isEnter) {
    // Ctrl+B 录音
    if (e.ctrlKey && e.keyCode === 66) {
      e.preventDefault();
      if (ctrlKeyDown.value) return;

      ctrlKeyDown.value = true;
      ctrlKeyTimer.value = window.setTimeout(() => {
        if (ctrlKeyDown.value && !props.isRecording) {
          emit("startRecording");
        }
      }, ctrlKeyLongPressThreshold);
    }
    return;
  }

  const isSendHotkey =
    e.ctrlKey ||
    e.metaKey ||
    (props.sendShortcut === "enter" ? !e.shiftKey : e.shiftKey);

  if (isSendHotkey) {
    e.preventDefault();
    if (localPrompt.value.trim() === "/astr_live_dev") {
      emit("openLiveMode");
      localPrompt.value = "";
      return;
    }
    if (canSend.value) {
      emit("send");
    }
    return;
  }
}

function handlePromptInput() {
  if (isComposing.value) return;
  syncSelectedMentionsFromText();
  updateMentionMenu();
}

function handleCompositionEnd() {
  isComposing.value = false;
  handlePromptInput();
}

function syncSelectedMentionsFromText() {
  const text = localPrompt.value;
  selectedMentions.value = selectedMentions.value.filter((bot) =>
    new RegExp(`(^|\\s)@${escapeRegExp(bot.name)}(?=\\s|$)`, "i").test(text),
  );
}

function updateMentionMenu() {
  const el = inputField.value;
  if (!el || !props.mentionableBots.length) {
    closeMentionMenu();
    return;
  }
  const caret = el.selectionStart ?? localPrompt.value.length;
  const beforeCaret = localPrompt.value.slice(0, caret);
  const match = /(^|\s)@([^\s@]*)$/.exec(beforeCaret);
  if (!match) {
    closeMentionMenu();
    return;
  }
  mentionStartIndex.value = beforeCaret.length - match[2].length - 1;
  mentionQuery.value = match[2];
  activeMentionIndex.value = 0;
  mentionMenuOpen.value = filteredMentionBots.value.length > 0;
}

function selectMentionBot(bot: MentionableBot) {
  if (!selectedMentions.value.some((item) => item.bot_id === bot.bot_id)) {
    selectedMentions.value.push(bot);
  }
  const el = inputField.value;
  const start = mentionStartIndex.value;
  if (el && start >= 0) {
    const caret = el.selectionStart ?? localPrompt.value.length;
    const before = localPrompt.value.slice(0, start);
    const after = localPrompt.value.slice(caret);
    const needsLeadingSpace = before.length > 0 && !/\s$/.test(before);
    const nextText = `${before}${needsLeadingSpace ? " " : ""}@${bot.name} ${after.replace(
      /^\s+/,
      "",
    )}`;
    localPrompt.value = nextText;
    nextTick(() => {
      const nextCaret =
        before.length + (needsLeadingSpace ? 1 : 0) + bot.name.length + 2;
      el.focus();
      el.setSelectionRange(nextCaret, nextCaret);
      autoResize();
      syncHighlightScroll();
    });
  }
  closeMentionMenu();
}

function closeMentionMenu() {
  mentionMenuOpen.value = false;
  mentionQuery.value = "";
  mentionStartIndex.value = -1;
  activeMentionIndex.value = 0;
}

function handleKeyUp(e: KeyboardEvent) {
  if (e.keyCode === 66) {
    ctrlKeyDown.value = false;

    if (ctrlKeyTimer.value) {
      clearTimeout(ctrlKeyTimer.value);
      ctrlKeyTimer.value = null;
    }

    if (props.isRecording) {
      emit("stopRecording");
    }
  }
}

function syncHighlightScroll() {
  const input = inputField.value;
  const layer = highlightLayer.value;
  if (!input || !layer) return;
  layer.scrollTop = input.scrollTop;
  layer.scrollLeft = input.scrollLeft;
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function handlePaste(e: ClipboardEvent) {
  emit("pasteImage", e);
}

function handleDragOver(e: DragEvent) {
  // 清除之前的 leave timeout
  if (dragLeaveTimeout) {
    clearTimeout(dragLeaveTimeout);
    dragLeaveTimeout = null;
  }

  // 检查是否有文件
  if (e.dataTransfer?.types.includes("Files")) {
    isDragging.value = true;
  }
}

function handleDragLeave(e: DragEvent) {
  // 使用 timeout 避免在子元素间移动时闪烁
  dragLeaveTimeout = window.setTimeout(() => {
    isDragging.value = false;
  }, 50);
}

function handleDrop(e: DragEvent) {
  isDragging.value = false;

  const files = e.dataTransfer?.files;
  if (files && files.length > 0) {
    emit("fileSelect", files);
  }
}

function triggerImageInput() {
  imageInputRef.value?.click();
}

function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement;
  const files = target.files;
  if (files) {
    emit("fileSelect", files);
  }
  target.value = "";
}

function handleRecordClick() {
  if (props.isRecording) {
    emit("stopRecording");
  } else {
    emit("startRecording");
  }
}

function handleConfigChange(payload: {
  configId: string;
  agentRunnerType: string;
}) {
  const runnerType = (payload.agentRunnerType || "").toLowerCase();
  const isInternal = runnerType === "internal" || runnerType === "local";
  showProviderSelector.value = isInternal;
}

function getCurrentSelection() {
  if (!showProviderSelector.value) {
    return null;
  }
  return providerModelMenuRef.value?.getCurrentSelection();
}

function consumeMentions() {
  const mentions = mentionBotsFromText(localPrompt.value);
  selectedMentions.value = [];
  closeMentionMenu();
  return mentions;
}

function mentionBotsFromText(text: string) {
  const found = new Map<string, MentionableBot>();
  for (const bot of props.mentionableBots) {
    const pattern = new RegExp(
      `(^|\\s)@${escapeRegExp(bot.name)}(?=\\s|$)`,
      "gi",
    );
    if (pattern.test(text)) {
      found.set(bot.bot_id, bot);
    }
  }
  for (const bot of selectedMentions.value) {
    if (
      new RegExp(`(^|\\s)@${escapeRegExp(bot.name)}(?=\\s|$)`, "i").test(text)
    ) {
      found.set(bot.bot_id, bot);
    }
  }
  return Array.from(found.values());
}

function focusInput() {
  if (!inputField.value) return;
  inputField.value.focus();
}

onMounted(() => {
  if (inputField.value) {
    inputField.value.addEventListener("paste", handlePaste);
  }
  document.addEventListener("keyup", handleKeyUp);
});

onBeforeUnmount(() => {
  if (inputField.value) {
    inputField.value.removeEventListener("paste", handlePaste);
  }
  document.removeEventListener("keyup", handleKeyUp);
});

defineExpose({
  getCurrentSelection,
  consumeMentions,
  focusInput,
});
</script>

<style scoped>
.input-area {
  padding: 12px 16px 0;
  background-color: transparent;
  position: relative;
  border-top: 1px solid var(--v-theme-border);
  flex-shrink: 0;
}

.input-neutral-btn {
  color: #6f6f6f !important;
}

.input-neutral-btn:hover {
  background: #efefef;
}

.input-neutral-btn--tonal {
  background: #efefef;
  color: #4f4f4f !important;
}

.input-neutral-btn--tonal:hover {
  background: #e7e7e7;
}

.input-action-btn {
  background: #5594c6 !important;
  color: #fff !important;
}

.input-action-btn:hover {
  background: #4c86b3 !important;
}

.input-action-btn:disabled {
  background: rgba(85, 148, 198, 0.24) !important;
  color: rgba(255, 255, 255, 0.72) !important;
}

.input-icon-btn {
  background: transparent !important;
  color: rgb(var(--v-theme-on-surface)) !important;
  margin-right: 8px;
}

.input-icon-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.04) !important;
}

.input-outline-control {
  width: 36px !important;
  height: 36px !important;
  min-width: 36px !important;
  border-color: rgba(var(--v-theme-on-surface), 0.18) !important;
  background: transparent !important;
}

.input-outline-control:hover {
  border-color: rgba(var(--v-theme-on-surface), 0.34) !important;
  background: rgba(var(--v-theme-on-surface), 0.04) !important;
}

.textarea-shell {
  position: relative;
  width: 100%;
  border: 1px solid var(--v-theme-border);
  border-radius: 12px;
  background-color: var(--v-theme-surface);
}

.chat-textarea,
.textarea-highlight {
  box-sizing: border-box;
  width: 100%;
  min-height: 34px;
  max-height: 200px;
  padding: 12px 18px;
  border: 0;
  border-radius: 12px;
  font-family: inherit;
  font-size: 16px;
  line-height: normal;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.chat-textarea {
  position: relative;
  z-index: 1;
  display: block;
  resize: none;
  outline: none;
  overflow-y: auto;
  background: transparent;
  color: transparent;
  caret-color: rgb(var(--v-theme-on-surface));
  transition: height 0.16s ease;
}

.chat-textarea::placeholder {
  color: rgba(var(--v-theme-on-surface), 0.42);
  opacity: 1;
}

.chat-textarea.is-composing {
  color: rgb(var(--v-theme-on-surface));
}

.textarea-highlight {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
  color: rgb(var(--v-theme-on-surface));
}

.textarea-highlight.is-composing {
  opacity: 0;
}

.textarea-mention {
  color: rgb(var(--v-theme-primary));
  font-weight: 500;
}

.mention-menu {
  position: absolute;
  left: 18px;
  bottom: calc(100% - 8px);
  z-index: 12;
  display: grid;
  gap: 4px;
  width: min(280px, calc(100% - 36px));
  max-height: 220px;
  padding: 6px;
  overflow-y: auto;
  border: 1px solid rgba(var(--v-border-color), 0.16);
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
}

.mention-option {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 38px;
  padding: 7px 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  text-align: left;
}

.mention-option:hover,
.mention-option.active {
  background: rgba(var(--v-theme-primary), 0.1);
}

.mention-option img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.mention-option-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
}

.input-area.is-dark .input-neutral-btn {
  color: rgba(255, 255, 255, 0.78) !important;
}

.input-area.is-dark .input-neutral-btn:hover,
.input-area.is-dark .input-neutral-btn--tonal {
  background: rgba(255, 255, 255, 0.1);
}

.input-area.is-dark .input-outline-control {
  border-color: rgba(255, 255, 255, 0.22) !important;
  background: transparent !important;
}

.input-area.is-dark .input-outline-control:hover {
  border-color: rgba(255, 255, 255, 0.42) !important;
  background: rgba(255, 255, 255, 0.06) !important;
}

.input-area.is-dark .input-action-btn {
  background: rgb(var(--v-theme-on-surface)) !important;
  color: rgb(var(--v-theme-surface)) !important;
}

.input-area.is-dark .input-action-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.86) !important;
}

.input-area.is-dark .input-action-btn:disabled {
  background: rgba(var(--v-theme-on-surface), 0.14) !important;
  color: rgba(var(--v-theme-on-surface), 0.4) !important;
}

/* 拖拽上传遮罩 */
.drop-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(var(--v-theme-primary), 0.12);
  border: 2px dashed rgba(var(--v-theme-primary), 0.45);
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  pointer-events: none;
}

.drop-overlay-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.drop-text {
  font-size: 16px;
  font-weight: 500;
  color: rgb(var(--v-theme-primary));
}

/* Fade transition for drop overlay */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.reply-preview {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  margin: 8px 8px 0 8px;
  background-color: rgba(var(--v-theme-primary), 0.06);
  border-radius: 12px;
  gap: 8px;
  max-height: 500px;
  overflow: hidden;
}

/* Transition animations for reply preview */
.slideReply-enter-active {
  animation: slideDown 0.2s ease-out;
}

.slideReply-leave-active {
  animation: slideUp 0.2s ease-out;
}

@keyframes slideDown {
  from {
    max-height: 0;
    opacity: 0;
    margin-top: 0;
    padding-top: 0;
    padding-bottom: 0;
  }

  to {
    max-height: 500px;
    opacity: 1;
    margin-top: 8px;
    padding-top: 8px;
    padding-bottom: 8px;
  }
}

@keyframes slideUp {
  from {
    max-height: 500px;
    opacity: 1;
    margin-top: 8px;
    padding-top: 8px;
    padding-bottom: 8px;
  }

  to {
    max-height: 0;
    opacity: 0;
    margin-top: 0;
    padding-top: 0;
    padding-bottom: 0;
  }
}

.reply-content {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.reply-icon {
  color: var(--v-theme-secondary);
  flex-shrink: 0;
}

.reply-text {
  font-size: 13px;
  color: var(--v-theme-secondaryText);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.remove-reply-btn {
  flex-shrink: 0;
  opacity: 0.6;
}

.attachments-preview {
  display: flex;
  gap: 10px;
  margin: 10px 12px 0;
  padding: 2px 2px 4px;
  flex-wrap: nowrap;
  align-items: center;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
  max-height: 72px;
}

.attachment-card {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  width: 220px;
  height: 64px;
  flex: 0 0 auto;
  min-width: 0;
  padding: 8px 34px 8px 10px;
  overflow: hidden;
  color: rgb(var(--v-theme-on-surface));
  background: rgba(var(--v-theme-on-surface), 0.04);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 12px;
}

.image-preview {
  width: 64px;
  flex-basis: 64px;
  padding: 0;
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.preview-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 11px;
}

.attachment-icon {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  flex-shrink: 0;
  min-width: 34px;
}

.attachment-icon--audio {
  color: #00897b;
}

.attachment-ext {
  max-width: 58px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  font-weight: 700;
  line-height: 12px;
}

.attachment-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  line-height: 18px;
}

.remove-attachment-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px !important;
  height: 22px !important;
  min-width: 22px !important;
  opacity: 0.8;
  transition: opacity 0.2s;
}

.remove-attachment-btn:hover {
  opacity: 1;
}

.fade-in {
  animation: fadeIn 0.3s ease-in-out;
}

.attachments-enter-active,
.attachments-leave-active {
  overflow: hidden;
  transition:
    max-height 0.2s ease,
    margin 0.2s ease,
    padding 0.2s ease,
    opacity 0.16s ease,
    transform 0.2s ease;
}

.attachments-enter-from,
.attachments-leave-to {
  max-height: 0;
  margin-top: 0;
  padding-top: 0;
  padding-bottom: 0;
  opacity: 0;
  transform: translateY(6px);
}

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

@media (max-width: 768px) {
  .input-area {
    padding: 0 !important;
  }

  .input-container {
    width: 100% !important;
    max-width: 100% !important;
    border-bottom-left-radius: 0 !important;
    border-bottom-right-radius: 0 !important;
  }

  .input-outline-control {
    width: 32px !important;
    height: 32px !important;
    min-width: 32px !important;
  }

  .input-area textarea,
  .chat-textarea,
  .textarea-highlight {
    min-height: 28px !important;
    max-height: 140px !important;
    font-size: 16px !important;
    line-height: 20px !important;
    padding: 8px 14px 7px !important;
  }

  .attachments-preview {
    margin: 8px 10px 0;
    gap: 8px;
  }

  .attachment-card {
    width: min(220px, calc(100vw - 28px));
    height: 58px;
  }

  .image-preview {
    width: 58px;
    flex-basis: 58px;
  }
}
</style>
