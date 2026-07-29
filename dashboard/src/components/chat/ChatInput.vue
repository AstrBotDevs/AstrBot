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
      :class="{
        'is-multiline': inputIsMultiline,
        'has-attachments': hasStagedAttachments,
      }"
      :style="{
        width: 'var(--chat-content-width, 76%)',
        maxWidth: 'var(--chat-content-max-width, 760px)',
        margin: '0 auto',
        border: isDark ? 'none' : '1px solid #e0e0e0',
        borderRadius: '24px',
        boxShadow: isDark ? 'none' : '0px 2px 2px rgba(0, 0, 0, 0.1)',
        backgroundColor: isDark ? '#2d2d2d' : '#fff',
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
              :style="{ '--attachment-color': filePresentation(file).color }"
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

      <CommandSuggestion
        :visible="showCommandSuggestion"
        :commands="filteredCommands"
        :selected-index="selectedCommandIndex"
        :is-dark="isDark"
        @select="handleCommandSelect"
        @update-selected-index="selectedCommandIndex = $event"
      />

      <div class="composer-row">
        <div class="input-left-actions">
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

        </div>
        <div class="input-field-shell">
          <input
            v-if="!inputIsMultiline"
            ref="inputField"
            v-model="localPrompt"
            @keydown="handleKeyDown"
            @input="handleInput"
            @compositionstart="handleCompositionStart"
            @compositionend="handleCompositionEnd"
            @compositioncancel="handleCompositionEnd"
            @blur="handleBlur"
            @paste="handlePaste"
            :disabled="disabled"
            :placeholder="tm('input.placeholder')"
            class="chat-text-input"
            autocomplete="off"
            autocorrect="off"
            autocapitalize="sentences"
            spellcheck="false"
            type="text"
          />
          <textarea
            v-else
            ref="inputField"
            v-model="localPrompt"
            @keydown="handleKeyDown"
            @input="handleInput"
            @compositionstart="handleCompositionStart"
            @compositionend="handleCompositionEnd"
            @compositioncancel="handleCompositionEnd"
            @blur="handleBlur"
            @paste="handlePaste"
            :disabled="disabled"
            :placeholder="tm('input.placeholder')"
            class="chat-textarea"
            autocomplete="off"
            autocorrect="off"
            autocapitalize="sentences"
            spellcheck="false"
          ></textarea>
        </div>
        <div class="input-right-actions">
          <input
            type="file"
            ref="imageInputRef"
            @change="handleFileSelect"
            style="display: none"
            multiple
          />
          <!-- Provider/Model Selector Menu -->
          <ProviderModelMenu
            v-if="props.showProviderSelector && providerSelectorAvailable"
            ref="providerModelMenuRef"
          />
          <v-progress-circular
            v-if="disabled && !mobile"
            indeterminate
            size="16"
            class="mr-1"
            width="1.5"
          />
          <v-tooltip
            v-if="tokenUsageVisible"
            location="top"
            max-width="320"
          >
            <template #activator="{ props: tokenTooltipProps }">
              <span
                v-bind="tokenTooltipProps"
                class="token-usage-indicator"
                :style="{ '--token-usage-color': tokenUsageColor }"
              >
                <v-progress-circular
                  :model-value="tokenUsagePercent"
                  size="24"
                  width="2.5"
                  class="token-usage-progress"
                />
              </span>
            </template>
            <span>{{ props.tokenUsage?.tooltip }}</span>
          </v-tooltip>
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
            v-if="isRunning && !canSend"
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
import { isComposingEnter } from "@/utils/imeInput.mjs";
import { commandApi } from "@/api/v1";
import type { CommandItem } from "@/components/extension/componentPanel/types";
import ConfigSelector from "./ConfigSelector.vue";
import ProviderModelMenu from "./ProviderModelMenu.vue";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import CommandSuggestion from "./CommandSuggestion.vue";
import { attachmentPresentation } from "./attachmentPresentation";
import type { Session } from "@/composables/useSessions";
import type { SuggestionCommand } from "./CommandSuggestion.vue";

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

interface TokenUsageInfo {
  used: number;
  limit: number;
  percent: number;
  tooltip: string;
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
  showProviderSelector?: boolean;
  tokenUsage?: TokenUsageInfo | null;
}

const props = withDefaults(defineProps<Props>(), {
  sessionId: null,
  currentSession: null,
  configId: null,
  stagedFiles: () => [],
  replyTo: null,
  sendShortcut: "shift_enter",
  showProviderSelector: true,
  tokenUsage: null,
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

const inputField = ref<HTMLInputElement | HTMLTextAreaElement | null>(null);
const imageInputRef = ref<HTMLInputElement | null>(null);
const providerModelMenuRef = ref<InstanceType<typeof ProviderModelMenu> | null>(
  null,
);
const providerSelectorAvailable = ref(true);
const isReplyClosing = ref(false);
const isDragging = ref(false);
const isComposing = ref(false);
const inputIsMultiline = ref(false);
const lastCompositionEndAt = ref<number | null>(null);
let dragLeaveTimeout: number | null = null;

// 命令提示相关状态
const allCommands = ref<CommandItem[]>([]);
const showCommandSuggestion = ref(false);
const selectedCommandIndex = ref(0);
const commandSuggestionLoading = ref(false);
const wakePrefixes = ref<string[]>(["/"]);
const currentConfigId = ref((props.configId as string) || "default");

/** 检查文本是否以任意一个唤醒词前缀开头 */
function hasWakePrefix(text: string): boolean {
  return wakePrefixes.value.some((p) => text.startsWith(p));
}

/** 去掉文本开头匹配的任意唤醒词前缀，返回剥离后的文本 */
function stripWakePrefix(text: string): string {
  let result = text;
  for (const p of wakePrefixes.value) {
    if (result.startsWith(p)) {
      result = result.slice(p.length);
      break; // 只剥离第一个匹配的前缀
    }
  }
  return result;
}

function normalizeCommandSearchText(value: string) {
  return stripWakePrefix(value.trim()).toLowerCase();
}

/** 从所有指令中展平获取启用的普通指令和子指令 */
const enabledCommands = computed(() => {
  const result: SuggestionCommand[] = [];
  const seen = new Set<string>();
  // 使用第一个唤醒词前缀作为指令的展示前缀
  const displayPrefix = wakePrefixes.value[0] || "/";

  function addCommand(cmd: CommandItem) {
    if (!cmd.enabled) return;
    if (cmd.type === "group") {
      // 指令组本身不加入，但其子指令加入
      cmd.sub_commands?.forEach(addCommand);
      return;
    }
    // 统一添加唤醒词前缀（子命令的 effective_command 如 "music play" 需要变成 "/music play"）
    const displayCmd = hasWakePrefix(cmd.effective_command)
      ? cmd.effective_command
      : `${displayPrefix}${cmd.effective_command}`;
    if (!seen.has(displayCmd)) {
      seen.add(displayCmd);
      result.push({
        handler_full_name: cmd.handler_full_name,
        effective_command: displayCmd,
        description: cmd.description,
        plugin_display_name: cmd.plugin_display_name,
        enabled: cmd.enabled,
        reserved: cmd.reserved,
      });
    }
    // 同时加入别名（别名也需要加上唤醒词前缀）
    cmd.aliases?.forEach((alias) => {
      const aliasBase = cmd.parent_signature
        ? `${cmd.parent_signature} ${alias}`
        : alias;
      const aliasKey = hasWakePrefix(aliasBase)
        ? aliasBase
        : `${displayPrefix}${aliasBase}`;
      if (!seen.has(aliasKey)) {
        seen.add(aliasKey);
        result.push({
          handler_full_name: cmd.handler_full_name,
          effective_command: aliasKey,
          description: cmd.description,
          plugin_display_name: cmd.plugin_display_name,
          enabled: cmd.enabled,
          reserved: cmd.reserved,
        });
      }
    });
  }

  allCommands.value.forEach(addCommand);
  return result;
});

function sortSystemPluginCommandsFirst(commands: SuggestionCommand[]) {
  return [...commands].sort((a, b) => Number(b.reserved) - Number(a.reserved));
}

/** 根据当前输入过滤候选指令 */
const filteredCommands = computed(() => {
  const text = props.prompt;
  if (!text || !hasWakePrefix(text)) return [];

  const query = normalizeCommandSearchText(text);
  if (!query) return sortSystemPluginCommandsFirst(enabledCommands.value);

  const startsWithMatches: SuggestionCommand[] = [];
  const containsMatches: SuggestionCommand[] = [];

  for (const cmd of enabledCommands.value) {
    const commandText = normalizeCommandSearchText(cmd.effective_command);
    const pluginText = normalizeCommandSearchText(cmd.plugin_display_name || "");
    const descriptionText = normalizeCommandSearchText(cmd.description || "");
    const matchesCommand = commandText.includes(query);
    const matchesMetadata =
      pluginText.includes(query) || descriptionText.includes(query);

    if (commandText.startsWith(query)) {
      startsWithMatches.push(cmd);
    } else if (matchesCommand || matchesMetadata) {
      containsMatches.push(cmd);
    }
  }

  return [
    ...sortSystemPluginCommandsFirst(startsWithMatches),
    ...sortSystemPluginCommandsFirst(containsMatches),
  ];
});

const localPrompt = computed({
  get: () => props.prompt,
  set: (value) => {
    // Suppress v-model sync during IME composition to avoid a reactive
    // feedback loop. Vue's :value binding overwrites the native textarea
    // DOM state mid-composition, which interferes with IME insertion at
    // non-terminal cursor positions (alternating character loss).
    // The final value is synced manually in handleCompositionEnd.
    if (!isComposing.value) emit("update:prompt", value);
  },
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

const hasStagedAttachments = computed(() => {
  return (
    props.stagedImagesUrl.length > 0 ||
    props.stagedAudioUrl ||
    (props.stagedFiles && props.stagedFiles.length > 0)
  );
});

function filePresentation(file: StagedFileInfo) {
  return attachmentPresentation(file);
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

const tokenUsageVisible = computed(() => {
  const usage = props.tokenUsage;
  return Boolean(
    usage &&
      Number.isFinite(usage.used) &&
      Number.isFinite(usage.limit) &&
      usage.used > 0 &&
      usage.limit > 0,
  );
});

const tokenUsagePercent = computed(() => {
  const percent = props.tokenUsage?.percent || 0;
  if (!Number.isFinite(percent)) return 0;
  return Math.min(100, Math.max(0, percent));
});

const tokenUsageColor = computed(() =>
  isDark.value
    ? "rgba(var(--v-theme-on-surface), 0.82)"
    : "rgba(var(--v-theme-on-surface), 0.72)",
);

// Auto-resize textarea
function autoResize() {
  const el = inputField.value;
  if (!el) return;
  if (!(el instanceof HTMLTextAreaElement)) {
    const shouldExpand =
      localPrompt.value.includes("\n") ||
      (el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 4);
    if (shouldExpand) {
      const cursor = el.selectionStart ?? localPrompt.value.length;
      inputIsMultiline.value = true;
      nextTick(() => {
        inputField.value?.focus();
        inputField.value?.setSelectionRange(cursor, cursor);
        autoResize();
      });
    }
    return;
  }
  const isMobileViewport =
    typeof window !== "undefined" &&
    window.matchMedia("(max-width: 768px)").matches;
  const viewportHeight =
    typeof window !== "undefined" ? window.innerHeight : 900;
  const minHeight = isMobileViewport ? 56 : 52;
  const maxHeight = isMobileViewport
    ? Math.min(220, Math.round(viewportHeight * 0.42))
    : Math.min(420, Math.round(viewportHeight * 0.48));
  if (!localPrompt.value) {
    inputIsMultiline.value = false;
    el.style.height = minHeight + "px";
    return;
  }
  el.style.height = "auto";
  el.style.setProperty("min-height", "0", "important");
  const measuredHeight = el.scrollHeight;
  el.style.removeProperty("min-height");
  const computed = getComputedStyle(el);
  let lineHeight = parseFloat(computed.lineHeight);
  if (!Number.isFinite(lineHeight)) {
    lineHeight = parseFloat(computed.fontSize) * 1.2;
  }
  const paddingVertical =
    parseFloat(computed.paddingTop) + parseFloat(computed.paddingBottom);
  const shouldUseMultiline =
    localPrompt.value.includes("\n") ||
    measuredHeight > lineHeight + paddingVertical + 0.5;
  if (inputIsMultiline.value !== shouldUseMultiline) {
    const cursor = el.selectionStart ?? localPrompt.value.length;
    inputIsMultiline.value = shouldUseMultiline;
    nextTick(() => {
      inputField.value?.focus();
      inputField.value?.setSelectionRange(cursor, cursor);
      autoResize();
    });
    return;
  }
  el.style.height = shouldUseMultiline
    ? Math.min(Math.max(measuredHeight, minHeight), maxHeight) + "px"
    : minHeight + "px";
}

watch(
  () => props.prompt,
  (value) => {
    if (!value) {
      inputIsMultiline.value = false;
    }
    nextTick(autoResize);
  },
);

watch(inputIsMultiline, () => {
  nextTick(autoResize);
});

function handleKeyDown(e: KeyboardEvent) {
  // 命令提示激活时，拦截方向键和 Enter/Esc
  if (showCommandSuggestion.value && filteredCommands.value.length > 0) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      selectedCommandIndex.value =
        (selectedCommandIndex.value + 1) % filteredCommands.value.length;
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      selectedCommandIndex.value =
        (selectedCommandIndex.value - 1 + filteredCommands.value.length) %
        filteredCommands.value.length;
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const cmd = filteredCommands.value[selectedCommandIndex.value];
      if (cmd) {
        handleCommandSelect(cmd);
      }
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      showCommandSuggestion.value = false;
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

  if (isComposingEnter(e, isComposing.value, lastCompositionEndAt.value)) {
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

  if (!inputIsMultiline.value) {
    e.preventDefault();
    const target = e.target as HTMLInputElement;
    const start = target.selectionStart ?? localPrompt.value.length;
    const end = target.selectionEnd ?? start;
    localPrompt.value =
      localPrompt.value.slice(0, start) + "\n" + localPrompt.value.slice(end);
    inputIsMultiline.value = true;
    nextTick(() => {
      inputField.value?.focus();
      inputField.value?.setSelectionRange(start + 1, start + 1);
      autoResize();
    });
  }
}

/** 处理输入变化，控制命令提示显示 */
function handleInput() {
  const text = props.prompt;
  if (text && hasWakePrefix(text) && !isComposing.value) {
    showCommandSuggestion.value = filteredCommands.value.length > 0;
    selectedCommandIndex.value = 0;
  } else {
    showCommandSuggestion.value = false;
  }
}

/** 处理 blur 事件，延迟关闭命令提示以允许点击 */
function handleBlur() {
  clearCompositionState();
  // 延迟关闭，避免点击候选项时面板已消失
  setTimeout(() => {
    showCommandSuggestion.value = false;
  }, 200);
}

/** 选择命令，填入输入框 */
function handleCommandSelect(cmd: SuggestionCommand) {
  localPrompt.value = cmd.effective_command + " ";
  showCommandSuggestion.value = false;
  nextTick(() => {
    inputField.value?.focus();
    autoResize();
  });
}

/** 获取指令列表 */
async function fetchCommands() {
  if (commandSuggestionLoading.value) return;
  commandSuggestionLoading.value = true;
  try {
    const cid = currentConfigId.value;
    const res = await commandApi.list(cid && cid !== "default" ? cid : undefined);
    if (res.data.status === "ok") {
      allCommands.value = res.data.data.items || [];
      // 读取当前配置的唤醒词列表，用于指令候选的触发前缀
      const prefixes: string[] = res.data.data.wake_prefix || [];
      if (prefixes && prefixes.length > 0) {
        wakePrefixes.value = prefixes;
      }
    }
  } catch (err) {
    // 静默失败，不影响聊天功能
    console.warn("Failed to fetch commands for suggestion:", err);
  } finally {
    commandSuggestionLoading.value = false;
  }
}

function handleCompositionStart() {
  isComposing.value = true;
  lastCompositionEndAt.value = null;
}

function handleCompositionEnd(e: CompositionEvent) {
  lastCompositionEndAt.value = e.timeStamp;
  clearCompositionState({ keepLastEndAt: true });

  // Manually sync the final composited text to the parent component
  // after the IME commits. The v-model setter is suppressed during
  // composition (see localPrompt computed), so we must explicitly
  // propagate the DOM value once composition ends.
  //
  // Capture the DOM value at compositionend to guard against a race
  // where props.prompt is externally updated between now and nextTick.
  const endValue = inputField.value?.value;

  nextTick(() => {
    const el = inputField.value;
    // Only sync if the DOM hasn't been changed externally in the meantime.
    if (el && el.value === endValue && el.value !== props.prompt) {
      emit("update:prompt", el.value);
      // Re-evaluate command suggestions that were suppressed during IME
      // composition (handleInput checks isComposing). Only needed when
      // the value actually changed. Runs in a nested nextTick so
      // props.prompt reflects the emit above.
      nextTick(() => {
        handleInput();
      });
    }
  });
}

function clearCompositionState({ keepLastEndAt = false } = {}) {
  isComposing.value = false;
  if (!keepLastEndAt) {
    lastCompositionEndAt.value = null;
  }
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

function handlePaste(e: ClipboardEvent) {
  const pastedText = e.clipboardData?.getData("text/plain") || "";
  if (!inputIsMultiline.value && pastedText.includes("\n")) {
    e.preventDefault();
    const target = e.target as HTMLInputElement;
    const start = target.selectionStart ?? localPrompt.value.length;
    const end = target.selectionEnd ?? start;
    localPrompt.value =
      localPrompt.value.slice(0, start) +
      pastedText +
      localPrompt.value.slice(end);
    inputIsMultiline.value = true;
    nextTick(() => {
      inputField.value?.focus();
      const cursor = start + pastedText.length;
      inputField.value?.setSelectionRange(cursor, cursor);
      autoResize();
    });
  }
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
  providerSelectorAvailable.value = isInternal;
  // 配置切换后重新获取指令列表和唤醒词
  if (payload.configId && payload.configId !== currentConfigId.value) {
    currentConfigId.value = payload.configId;
    fetchCommands();
  }
}

function getCurrentSelection() {
  if (!props.showProviderSelector || !providerSelectorAvailable.value) {
    return null;
  }
  return providerModelMenuRef.value?.getCurrentSelection();
}

function focusInput() {
  if (!inputField.value) return;
  inputField.value.focus();
}

onMounted(() => {
  document.addEventListener("keyup", handleKeyUp);
  // 预加载指令列表
  fetchCommands();
  nextTick(autoResize);
});

onBeforeUnmount(() => {
  clearCompositionState();
  document.removeEventListener("keyup", handleKeyUp);
});

defineExpose({
  getCurrentSelection,
  focusInput,
});
</script>

<style scoped>
.input-area {
  padding: 0 16px;
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

.token-usage-indicator {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 24px;
  border-radius: 50%;
  color: var(--token-usage-color);
}

.token-usage-progress {
  color: currentColor;
}

.token-usage-progress :deep(.v-progress-circular__underlay) {
  color: rgba(var(--v-theme-on-surface), 0.18);
  stroke: currentColor;
  opacity: 0.24;
}

.token-usage-progress :deep(.v-progress-circular__overlay) {
  stroke: currentColor;
}

.input-outline-control {
  width: 36px !important;
  height: 36px !important;
  min-width: 36px !important;
  border: 0 !important;
  border-color: transparent !important;
  background: transparent !important;
  box-shadow: none !important;
}

.input-outline-control:hover,
.input-outline-control:focus-visible {
  border-color: transparent !important;
  background: rgba(var(--v-theme-on-surface), 0.04) !important;
}

.input-area.is-dark .input-neutral-btn {
  color: rgba(255, 255, 255, 0.78) !important;
}

.input-area.is-dark .input-neutral-btn:hover,
.input-area.is-dark .input-neutral-btn--tonal {
  background: rgba(255, 255, 255, 0.1);
}

.input-area.is-dark .input-outline-control {
  border-color: transparent !important;
  background: transparent !important;
}

.input-area.is-dark .input-outline-control:hover,
.input-area.is-dark .input-outline-control:focus-visible {
  border-color: transparent !important;
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

.input-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 64px;
  padding: 6px 12px 6px 14px !important;
  border-color: #f0f0f0 !important;
  border-radius: 999px !important;
  background: #fff !important;
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.08) !important;
}

.input-container.is-multiline {
  justify-content: flex-start;
  padding: 16px 20px 14px !important;
  border-radius: 34px !important;
}

.input-container.has-attachments {
  justify-content: flex-start;
  min-height: 130px;
  padding: 14px 18px 10px !important;
  border-radius: 30px !important;
}

.input-area.is-dark .input-container {
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  background: #2d2d2d !important;
  box-shadow: none !important;
}

.reply-preview,
.attachments-preview {
  width: 100%;
  flex: 0 0 auto;
}

.composer-row {
  width: 100%;
  min-height: 52px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  grid-template-areas: "left field right";
  align-items: center;
  column-gap: 10px;
}

.input-container.is-multiline .composer-row {
  grid-template-areas:
    "field field field"
    "left . right";
  row-gap: 10px;
  align-items: end;
}

.input-field-shell {
  grid-area: field;
  min-width: 0;
  min-height: 52px;
  display: flex;
  align-items: center;
}

.input-container.is-multiline .input-field-shell {
  min-height: auto;
  align-items: flex-start;
}

.chat-text-input,
.chat-textarea {
  display: block;
  width: 100%;
  box-sizing: border-box;
  min-width: 0;
  min-height: 52px !important;
  max-height: 72px !important;
  margin: 0;
  padding: 0 !important;
  border: 0 !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  resize: none;
  outline: none;
  font-family: inherit;
  font-size: 18px !important;
}

.chat-text-input {
  height: 52px !important;
  padding: 0 !important;
  line-height: normal !important;
  overflow: hidden;
}

.chat-textarea {
  max-height: min(48vh, 420px) !important;
  padding: 12px 0 !important;
  overflow-y: auto;
  overflow-wrap: break-word;
  line-height: 28px !important;
  transition: height 0.16s ease;
}

.chat-text-input::placeholder,
.chat-textarea::placeholder {
  color: rgba(var(--v-theme-on-surface), 0.56);
  opacity: 1;
}

.input-left-actions {
  grid-area: left;
  display: flex;
  align-items: center;
  flex: 0 0 auto !important;
  justify-content: center !important;
  gap: 0 !important;
  min-width: auto !important;
  margin-top: 0 !important;
  overflow: visible !important;
}

.input-right-actions {
  grid-area: right;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
  gap: 10px;
  margin-top: 0 !important;
}

.input-outline-control {
  width: 34px !important;
  height: 34px !important;
  min-width: 34px !important;
  border: 0 !important;
  border-color: transparent !important;
  border-radius: 50% !important;
  box-shadow: none !important;
}

.input-icon-btn {
  width: 42px !important;
  height: 42px !important;
  min-width: 42px !important;
  margin-right: 0;
}

.input-right-actions :deep(.provider-chip) {
  height: 40px !important;
  min-height: 40px !important;
  border-radius: 999px !important;
}

.input-area:not(.is-dark) .input-action-btn {
  width: 46px !important;
  height: 46px !important;
  min-width: 46px !important;
  background: #8fcfb4 !important;
  color: #fff !important;
}

.input-area:not(.is-dark) .input-action-btn:hover {
  background: #7fc4a8 !important;
}

.input-area:not(.is-dark) .input-action-btn:disabled {
  background: #f2f5f3 !important;
  color: rgba(0, 0, 0, 0.18) !important;
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

.input-container.has-attachments .attachments-preview {
  margin: 0 0 8px;
  padding: 0;
}

.attachment-card {
  --attachment-color: #607d8b;
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  width: 210px;
  height: 54px;
  flex: 0 0 auto;
  min-width: 0;
  padding: 7px 32px 7px 10px;
  overflow: hidden;
  color: rgb(var(--v-theme-on-surface));
  background: rgba(var(--v-theme-on-surface), 0.055);
  border: 0;
  border-radius: 8px;
}

.file-preview {
  background: rgba(var(--v-theme-on-surface), 0.055);
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--attachment-color) 14%, transparent),
    rgba(var(--v-theme-on-surface), 0.055) 62%
  );
}

.image-preview {
  width: 54px;
  flex-basis: 54px;
  padding: 0;
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.preview-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 8px;
}

.attachment-icon {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  flex-shrink: 0;
  min-width: 34px;
  color: var(--attachment-color);
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
  color: var(--attachment-color);
}

.attachment-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  line-height: 17px;
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
    padding: 8px 0 0 !important;
    border-top: 0;
  }

  .input-container {
    display: flex !important;
    flex-direction: column;
    justify-content: center;
    width: calc(100% - 20px) !important;
    max-width: 100% !important;
    min-height: 64px;
    margin: 0 10px calc(8px + env(safe-area-inset-bottom)) !important;
    padding: 6px 8px 6px 10px !important;
    overflow: hidden;
    border: 1px solid rgba(var(--v-theme-on-surface), 0.14) !important;
    border-radius: 999px !important;
    background: #fff !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08) !important;
  }

  .input-container.is-multiline {
    justify-content: flex-start;
    min-height: 128px;
    padding: 10px !important;
    border-radius: 26px !important;
  }

  .input-container.has-attachments {
    justify-content: flex-start;
    min-height: 124px;
    padding: 10px !important;
    border-radius: 26px !important;
  }

  .input-area.is-dark .input-container {
    border-color: rgba(255, 255, 255, 0.16) !important;
    background: #2d2d2d !important;
    box-shadow: none !important;
  }

  .composer-row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas: "left field right";
    min-height: 52px;
    row-gap: 0;
    column-gap: 8px;
    align-items: center;
  }

  .input-container.is-multiline .composer-row {
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas:
      "field field field"
      "left . right";
    min-height: auto;
    row-gap: 4px;
  }

  .input-field-shell {
    min-height: 52px;
    align-items: center;
  }

  .input-container.is-multiline .input-field-shell {
    min-height: 56px;
    align-items: flex-start;
  }

  .input-left-actions,
  .input-right-actions {
    margin-top: 0 !important;
    align-items: center !important;
  }

  .input-right-actions {
    gap: 6px;
  }

  .input-outline-control {
    width: 38px !important;
    height: 38px !important;
    min-width: 38px !important;
    border: 0 !important;
    border-color: transparent !important;
    border-radius: 50% !important;
  }

  .chat-text-input,
  .chat-textarea {
    min-height: 52px !important;
    max-height: 132px !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    font-size: 18px !important;
  }

  .chat-text-input {
    height: 52px !important;
    padding: 0 2px !important;
    line-height: normal !important;
    overflow: hidden;
  }

  .chat-textarea {
    max-height: min(42vh, 220px) !important;
    padding: 4px 10px 2px !important;
    line-height: 24px !important;
    overflow-y: auto;
  }

  .chat-text-input::placeholder,
  .chat-textarea::placeholder {
    color: rgba(var(--v-theme-on-surface), 0.56);
    opacity: 1;
  }

  .input-icon-btn {
    width: 38px !important;
    height: 38px !important;
    min-width: 38px !important;
    margin-right: 0;
  }

  .input-action-btn {
    width: 42px !important;
    height: 42px !important;
    min-width: 42px !important;
    border-radius: 50% !important;
  }

  .input-action-btn:not(:disabled) {
    background: rgb(var(--v-theme-on-surface)) !important;
    color: rgb(var(--v-theme-surface)) !important;
  }

  .input-action-btn:disabled {
    background: rgba(var(--v-theme-on-surface), 0.04) !important;
    color: rgba(var(--v-theme-on-surface), 0.18) !important;
  }

  :deep(.provider-chip) {
    height: 38px !important;
    min-height: 38px !important;
    border-radius: 999px !important;
    padding: 0 12px !important;
    font-size: 14px !important;
    border-color: rgba(var(--v-theme-on-surface), 0.18) !important;
    background: transparent !important;
  }

  .attachments-preview {
    margin: 8px 16px 0;
    gap: 8px;
  }

  .input-container.has-attachments .attachments-preview {
    margin: 0 0 8px;
  }

  .attachment-card {
    width: min(220px, calc(100vw - 28px));
    height: 54px;
  }

  .image-preview {
    width: 54px;
    flex-basis: 54px;
  }
}
</style>
