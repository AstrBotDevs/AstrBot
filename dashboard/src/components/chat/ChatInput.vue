<template>
  <div class="input-area fade-in">
    <div
      class="input-container"
      :class="{
        'is-multiline': inputIsMultiline,
        'has-attachments': hasStagedAttachments,
      }"
    >
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
            color="secondary"
            aria-label="Clear reply"
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
              aria-label="Remove image attachment"
            />
          </div>

          <div v-if="stagedAudioUrl" class="attachment-card audio-preview">
            <div class="attachment-icon attachment-icon--audio">
              <v-icon icon="mdi-microphone" size="24"></v-icon>
            </div>
            <span class="attachment-name">{{ tm('voice.recording') }}</span>
            <v-btn
              @click="$emit('removeAudio')"
              class="remove-attachment-btn"
              icon="mdi-close"
              size="x-small"
              color="error"
              variant="tonal"
              aria-label="Remove audio attachment"
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
              aria-label="Remove file attachment"
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
            <template #activator="{ props: activatorProps }">
              <v-btn
                v-bind="activatorProps"
                icon="mdi-plus"
                variant="outlined"
                class="input-neutral-btn input-outline-control"
                :aria-label="tm('input.moreOptions')"
              />
            </template>

            <!-- Upload Files -->
            <v-list-item
              class="styled-menu-item"
              rounded="md"
              @click="triggerImageInput"
            >
              <template #prepend>
                <v-icon icon="mdi-file-upload" size="small"></v-icon>
              </template>
              <v-list-item-title>
                {{ tm('input.upload') }}
              </v-list-item-title>
            </v-list-item>

            <!-- Config Selector in Menu -->
            <ConfigSelector
              :session-id="sessionId || null"
              :platform-id="sessionPlatformId"
              :initial-config-id="props.configId"
              @config-changed="handleConfigChange"
            />

            <!-- Streaming Toggle in Menu -->
            <v-list-item
              class="styled-menu-item"
              rounded="md"
              @click="$emit('toggleStreaming')"
            >
              <template #prepend>
                <v-icon icon="mdi-lightning-bolt" size="small"></v-icon>
              </template>
              <v-list-item-title>
                {{
                  enableStreaming
                    ? tm('streaming.enabled')
                    : tm('streaming.disabled')
                }}
              </v-list-item-title>
            </v-list-item>

            <v-list-item
              class="styled-menu-item high-risk-tools-btn"
              rounded="md"
              :disabled="props.disabled"
              @click="$emit('toggleWebChatTools')"
            >
              <template #prepend>
                <v-icon
                  icon="mdi-shield-key-outline"
                  size="small"
                  :color="props.webChatToolsEnabled ? 'warning' : undefined"
                />
              </template>
              <v-list-item-title>
                {{
                  props.webChatToolsEnabled
                    ? tm('input.disableHighRiskTools')
                    : tm('input.enableHighRiskTools')
                }}
              </v-list-item-title>
            </v-list-item>
          </StyledMenu>
        </div>
        <div class="input-field-shell">
          <textarea
            ref="inputField"
            v-model="localPrompt"
            rows="1"
            @keydown="handleKeyDown"
            @input="handleInput"
            @compositionstart="handleCompositionStart"
            @compositionend="handleCompositionEnd"
            @compositioncancel="handleCompositionEnd"
            @blur="handleBlur"
            @paste="handlePaste"
            :disabled="disabled"
            :placeholder="props.placeholder ?? tm('input.placeholder')"
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
            class="file-input"
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
          <v-tooltip v-if="tokenUsageVisible" location="top" max-width="320">
            <template #activator="{ props: tokenTooltipProps }">
              <span v-bind="tokenTooltipProps" class="token-usage-indicator">
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
          <v-btn
            @click="handleRecordClick"
            icon
            variant="text"
            class="record-btn input-icon-btn"
            :aria-label="
              isRecording ? tm('voice.speaking') : tm('voice.startRecording')
            "
          >
            <v-icon
              :icon="isRecording ? 'mdi-stop-circle' : 'mdi-microphone'"
              variant="text"
              plain
            ></v-icon>
            <v-tooltip activator="parent" location="top">
              {{
                isRecording ? tm('voice.speaking') : tm('voice.startRecording')
              }}
            </v-tooltip>
          </v-btn>
          <v-btn
            v-if="!isRunning"
            @click="$emit('send')"
            icon="mdi-arrow-up"
            variant="tonal"
            :disabled="!canSend"
            class="send-btn input-action-btn"
            :aria-label="tm('input.send')"
          />
          <v-btn
            v-if="isRunning"
            icon
            @click="$emit('stop')"
            variant="tonal"
            class="stop-btn input-action-btn"
            :aria-label="tm('input.stopGenerating')"
          >
            <v-icon icon="mdi-stop" variant="text" plain></v-icon>
            <v-tooltip activator="parent" location="top">
              {{ tm('input.stopGenerating') }}
            </v-tooltip>
          </v-btn>
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
} from 'vue';
import { useDisplay } from 'vuetify';
import { themeNames } from '@/design/theme';
import { useModuleI18n } from '@/i18n/composables';
import { useCustomizerStore } from '@/stores/customizer';
import { isComposingEnter } from '@/utils/imeInput';
import { commandApi } from '@/api/v1';
import type { CommandItem } from '@/domain/commands';
import ConfigSelector from './ConfigSelector.vue';
import ProviderModelMenu from './ProviderModelMenu.vue';
import StyledMenu from '@/components/shared/StyledMenu.vue';
import CommandSuggestion from './CommandSuggestion.vue';
import { attachmentPresentation } from './attachmentPresentation';
import type { Session } from '@/composables/useSessions';
import {
  buildSuggestionSignature,
  rankSuggestionCommands,
} from './commandSuggestion';
import type { SuggestionCommand } from './commandSuggestion';

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
  sendShortcut?: 'enter' | 'shift_enter';
  showProviderSelector?: boolean;
  tokenUsage?: TokenUsageInfo | null;
  placeholder?: string;
  webChatToolsEnabled?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  sessionId: null,
  currentSession: null,
  configId: null,
  stagedFiles: () => [],
  replyTo: null,
  sendShortcut: 'shift_enter',
  showProviderSelector: true,
  tokenUsage: null,
  webChatToolsEnabled: false,
});

const emit = defineEmits<{
  'update:prompt': [value: string];
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
  toggleWebChatTools: [];
  'config-changed': [payload: { configId: string; agentRunnerType: string }];
}>();

const { tm } = useModuleI18n('features/chat');
const isDark = computed(() => useCustomizerStore().uiTheme === themeNames.dark);

const inputField = ref<HTMLTextAreaElement | null>(null);
const imageInputRef = ref<HTMLInputElement | null>(null);
const providerModelMenuRef = ref<InstanceType<typeof ProviderModelMenu> | null>(
  null,
);
const providerSelectorAvailable = ref(true);
const isReplyClosing = ref(false);
const isComposing = ref(false);
const inputIsMultiline = ref(false);
const lastCompositionEndAt = ref<number | null>(null);

// 命令提示相关状态
const allCommands = ref<CommandItem[]>([]);
const showCommandSuggestion = ref(false);
const selectedCommandIndex = ref(0);
const commandSuggestionLoading = ref(false);
const wakePrefixes = ref<string[]>(['/']);
const currentConfigId = ref((props.configId as string) || 'default');

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
  const displayPrefix = wakePrefixes.value[0] || '/';

  function addCommand(cmd: CommandItem) {
    if (!cmd.enabled) return;
    if (cmd.type === 'group') {
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
        display_signature: buildSuggestionSignature(
          displayCmd,
          cmd.signature,
          cmd.effective_command,
        ),
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
          display_signature: buildSuggestionSignature(
            aliasKey,
            cmd.signature,
            cmd.effective_command,
          ),
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

/** 根据当前输入过滤候选指令 */
const filteredCommands = computed(() => {
  const text = props.prompt;
  if (!text || !hasWakePrefix(text)) return [];

  const query = normalizeCommandSearchText(text);

  return rankSuggestionCommands(
    enabledCommands.value,
    query,
    normalizeCommandSearchText,
  );
});

const localPrompt = computed({
  get: () => props.prompt,
  set: (value) => {
    // Suppress v-model sync during IME composition to avoid a reactive
    // feedback loop. Vue's :value binding overwrites the native textarea
    // DOM state mid-composition, which interferes with IME insertion at
    // non-terminal cursor positions (alternating character loss).
    // The final value is synced manually in handleCompositionEnd.
    if (!isComposing.value) emit('update:prompt', value);
  },
});

const sessionPlatformId = computed(
  () => props.currentSession?.platform_id || 'webchat',
);

const canSend = computed(() => {
  return (
    Boolean(props.prompt?.trim()) ||
    props.stagedImagesUrl.length > 0 ||
    Boolean(props.stagedAudioUrl) ||
    Boolean(props.stagedFiles?.length)
  );
});

const hasStagedAttachments = computed(() => {
  return (
    props.stagedImagesUrl.length > 0 ||
    Boolean(props.stagedAudioUrl) ||
    Boolean(props.stagedFiles?.length)
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
  emit('clearReply');
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

// Auto-resize textarea
function autoResize() {
  const el = inputField.value;
  if (!(el instanceof HTMLTextAreaElement)) return;
  const isMobileViewport =
    typeof window !== 'undefined' &&
    window.matchMedia('(max-width: 768px)').matches;
  const viewportHeight =
    typeof window !== 'undefined' ? window.innerHeight : 900;
  const minHeight = 52;
  const maxHeight = isMobileViewport
    ? Math.min(220, Math.round(viewportHeight * 0.42))
    : Math.min(420, Math.round(viewportHeight * 0.48));
  if (!localPrompt.value) {
    inputIsMultiline.value = false;
    el.style.height = `${minHeight}px`;
    return;
  }

  const previousTransition = el.style.transition;
  el.style.transition = 'none';
  el.style.height = 'auto';
  el.style.setProperty('min-height', '0', 'important');
  const measuredHeight = el.scrollHeight;
  el.style.removeProperty('min-height');
  el.style.height = `${Math.min(
    Math.max(measuredHeight, minHeight),
    maxHeight,
  )}px`;
  el.style.transition = previousTransition;

  // Keep the expanded layout until the prompt is cleared. The single-line
  // layout is narrower, so shrinking based on textarea height can oscillate.
  if (localPrompt.value.includes('\n') || measuredHeight > minHeight + 4) {
    inputIsMultiline.value = true;
  }
}

watch(
  () => props.prompt,
  (value) => {
    if (!value) {
      inputIsMultiline.value = false;
    }
    void nextTick(autoResize);
  },
);

function handleKeyDown(e: KeyboardEvent) {
  // 命令提示激活时，拦截方向键和 Enter/Esc
  if (showCommandSuggestion.value && filteredCommands.value.length > 0) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      selectedCommandIndex.value =
        (selectedCommandIndex.value + 1) % filteredCommands.value.length;
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      selectedCommandIndex.value =
        (selectedCommandIndex.value - 1 + filteredCommands.value.length) %
        filteredCommands.value.length;
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      const cmd = filteredCommands.value[selectedCommandIndex.value];
      if (cmd) {
        handleCommandSelect(cmd);
      }
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      showCommandSuggestion.value = false;
      return;
    }
  }

  const isEnter = e.key === 'Enter';
  if (!isEnter) {
    // Ctrl+B 录音
    if (e.ctrlKey && e.keyCode === 66) {
      e.preventDefault();
      if (ctrlKeyDown.value) return;

      ctrlKeyDown.value = true;
      ctrlKeyTimer.value = window.setTimeout(() => {
        if (ctrlKeyDown.value && !props.isRecording) {
          emit('startRecording');
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
    (props.sendShortcut === 'enter' ? !e.shiftKey : e.shiftKey);

  if (isSendHotkey) {
    e.preventDefault();
    if (canSend.value) {
      emit('send');
    }
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
  window.setTimeout(() => {
    showCommandSuggestion.value = false;
  }, 200);
}

/** 选择命令，填入输入框 */
function handleCommandSelect(cmd: SuggestionCommand) {
  localPrompt.value = `${cmd.effective_command} `;
  showCommandSuggestion.value = false;
  void nextTick(() => {
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
    const res = await commandApi.list(
      cid && cid !== 'default' ? cid : undefined,
    );
    if (res.data.status === 'ok') {
      allCommands.value = res.data.data.items || [];
      // 读取当前配置的唤醒词列表，用于指令候选的触发前缀
      const commandPrefixes: string[] = res.data.data.command_prefixes || [];
      const llmPrefixes: string[] = res.data.data.llm_access?.prefixes || [];
      const prefixes = [...commandPrefixes, ...llmPrefixes].filter(Boolean);
      if (prefixes.length > 0) {
        wakePrefixes.value = [...new Set(prefixes)];
      }
    }
  } catch (err) {
    // 静默失败，不影响聊天功能
    console.warn('Failed to fetch commands for suggestion:', err);
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

  void nextTick(() => {
    const el = inputField.value;
    // Only sync if the DOM hasn't been changed externally in the meantime.
    if (el && el.value === endValue && el.value !== props.prompt) {
      emit('update:prompt', el.value);
      // Re-evaluate command suggestions that were suppressed during IME
      // composition (handleInput checks isComposing). Only needed when
      // the value actually changed. Runs in a nested nextTick so
      // props.prompt reflects the emit above.
      void nextTick(() => {
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
      emit('stopRecording');
    }
  }
}

function handlePaste(e: ClipboardEvent) {
  emit('pasteImage', e);
}

function triggerImageInput() {
  imageInputRef.value?.click();
}

function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement;
  const files = target.files;
  if (files) {
    emit('fileSelect', files);
  }
  target.value = '';
}

function handleRecordClick() {
  if (props.isRecording) {
    emit('stopRecording');
  } else {
    emit('startRecording');
  }
}

function handleConfigChange(payload: {
  configId: string;
  agentRunnerType: string;
}) {
  const runnerType = (payload.agentRunnerType || '').toLowerCase();
  const isInternal = runnerType === 'internal' || runnerType === 'local';
  providerSelectorAvailable.value = isInternal;
  // 配置切换后重新获取指令列表和唤醒词
  if (payload.configId && payload.configId !== currentConfigId.value) {
    currentConfigId.value = payload.configId;
    void fetchCommands();
  }
  emit('config-changed', payload);
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
  document.addEventListener('keyup', handleKeyUp);
  // 预加载指令列表
  void fetchCommands();
  void nextTick(autoResize);
});

onBeforeUnmount(() => {
  clearCompositionState();
  document.removeEventListener('keyup', handleKeyUp);
});

defineExpose({
  getCurrentSelection,
  focusInput,
});
</script>

<style scoped>
.input-area {
  padding: 12px 16px 0;
  background-color: transparent;
  position: relative;
  border-top: 1px solid rgb(var(--v-theme-outline-variant));
  flex-shrink: 0;
}

.input-neutral-btn {
  color: rgb(var(--v-theme-on-surface-variant));
}

.input-neutral-btn:hover {
  background: rgb(var(--v-theme-surface-variant));
}

.input-neutral-btn--tonal {
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-on-surface));
}

.input-neutral-btn--tonal:hover {
  background: rgb(var(--v-theme-surface-variant));
}

.input-action-btn {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}

.input-action-btn:hover {
  background: rgb(var(--v-theme-primary));
  filter: brightness(0.92);
}

.input-action-btn:disabled {
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-on-surface-variant));
}

.input-icon-btn {
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  margin-right: 8px;
}

.input-icon-btn:hover {
  background: rgb(var(--v-theme-surface-variant));
}

.token-usage-indicator {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 24px;
  border-radius: 50%;
  color: rgb(var(--v-theme-on-surface-variant));
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
  width: 40px;
  height: 40px;
  min-width: 40px;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.input-outline-control:hover,
.input-outline-control:focus-visible {
  background: rgb(var(--v-theme-surface-variant));
}

.input-container {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: var(--chat-content-width, 76%);
  max-width: var(--chat-content-max-width, 760px);
  min-height: 64px;
  margin: 0 auto;
  padding: 8px 12px;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 2px 4px rgb(24 33 43 / 10%);
  transition:
    min-height 0.2s ease,
    padding 0.2s ease;
}

.input-container.is-multiline {
  justify-content: flex-start;
  padding: 16px;
  border-radius: 8px;
}

.input-container.has-attachments {
  justify-content: flex-start;
  min-height: 130px;
  padding: 12px;
  border-radius: 8px;
}

:global(.dashboard-appearance-active .input-container) {
  background: var(--dashboard-wallpaper-surface);
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
  grid-template-areas: 'left field right';
  align-items: center;
  column-gap: 10px;
}

.input-container.is-multiline .composer-row {
  grid-template-areas:
    'field field field'
    'left . right';
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

.chat-textarea {
  display: block;
  width: 100%;
  box-sizing: border-box;
  min-width: 0;
  min-height: 52px;
  max-height: min(48vh, 420px);
  height: 52px;
  margin: 0;
  padding: 12px 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  resize: none;
  outline: none;
  overflow-y: hidden;
  overflow-wrap: break-word;
  font-family: inherit;
  font-size: 18px;
  line-height: 28px;
  transition: height 0.16s ease;
}

.input-container.is-multiline .chat-textarea {
  overflow-y: auto;
}

.chat-textarea::placeholder {
  color: rgba(var(--v-theme-on-surface), 0.56);
  opacity: 1;
}

.input-left-actions {
  grid-area: left;
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  justify-content: center;
  gap: 0;
  min-width: auto;
  margin-top: 0;
  overflow: visible;
}

.input-right-actions {
  grid-area: right;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
  gap: 10px;
  margin-top: 0;
}

.input-outline-control {
  border-radius: 8px;
}

.input-icon-btn {
  width: 40px;
  height: 40px;
  min-width: 40px;
  margin-right: 0;
}

.input-right-actions :deep(.provider-chip) {
  height: 40px;
  min-height: 40px;
  border-radius: 8px;
}

.input-action-btn {
  width: 40px;
  height: 40px;
  min-width: 40px;
}

.reply-preview {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  margin: 8px 8px 0 8px;
  background-color: rgba(var(--v-theme-primary), 0.06);
  border-radius: 8px;
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
  color: rgb(var(--v-theme-secondary));
  flex-shrink: 0;
}

.reply-text {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
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
  --attachment-color: rgb(var(--v-theme-secondary));
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
  color: rgb(var(--v-theme-success));
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
  width: 24px;
  height: 24px;
  min-width: 24px;
  opacity: 0.8;
  transition: opacity 0.2s;
}

.remove-attachment-btn:hover {
  opacity: 1;
}

.fade-in {
  animation: fadeIn 0.3s ease-in-out;
}

.file-input {
  display: none;
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
    padding: 8px 0 0;
    border-top: 0;
  }

  .input-container {
    display: flex;
    flex-direction: column;
    justify-content: center;
    width: calc(100% - 16px);
    max-width: 100%;
    min-height: 64px;
    margin: 0 8px calc(8px + env(safe-area-inset-bottom));
    padding: 8px;
    overflow: hidden;
    border: 1px solid rgb(var(--v-theme-outline-variant));
    border-radius: 8px;
    box-shadow: 0 2px 4px rgb(24 33 43 / 10%);
  }

  .input-container.is-multiline {
    justify-content: flex-start;
    min-height: 128px;
    padding: 12px;
    border-radius: 8px;
  }

  .input-container.has-attachments {
    justify-content: flex-start;
    min-height: 124px;
    padding: 12px;
    border-radius: 8px;
  }

  .composer-row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas: 'left field right';
    min-height: 52px;
    row-gap: 0;
    column-gap: 8px;
    align-items: center;
  }

  .input-container.is-multiline .composer-row {
    grid-template-columns: auto minmax(0, 1fr) auto;
    grid-template-areas:
      'field field field'
      'left . right';
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
    margin-top: 0;
    align-items: center;
  }

  .input-right-actions {
    gap: 6px;
  }

  .input-outline-control {
    width: 40px;
    height: 40px;
    min-width: 40px;
    border: 0;
    border-radius: 8px;
  }

  .chat-textarea {
    min-height: 52px;
    max-height: min(42vh, 220px);
    height: 52px;
    padding: 4px 8px;
    border: 0;
    border-radius: 0;
    background: transparent;
    box-shadow: none;
    overflow-y: hidden;
    font-size: 18px;
    line-height: 24px;
  }

  .input-container.is-multiline .chat-textarea {
    overflow-y: auto;
  }

  .chat-textarea::placeholder {
    color: rgba(var(--v-theme-on-surface), 0.56);
    opacity: 1;
  }

  .input-icon-btn {
    width: 40px;
    height: 40px;
    min-width: 40px;
    margin-right: 0;
  }

  .input-action-btn {
    width: 40px;
    height: 40px;
    min-width: 40px;
    border-radius: 8px;
  }

  :deep(.provider-chip) {
    height: 40px;
    min-height: 40px;
    border-radius: 8px;
    padding: 0 12px;
    font-size: 14px;
    border-color: rgb(var(--v-theme-outline-variant));
    background: transparent;
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
