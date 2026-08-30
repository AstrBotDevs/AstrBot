<template>
  <div class="reasoning-block" :class="{ 'reasoning-block--dark': isDark }">
    <div class="reasoning-header-row">
      <button
        class="reasoning-header"
        type="button"
        :disabled="sidebarActive"
        :aria-expanded="showInlineContent"
        :aria-label="
          sidebarActive ? tm('reasoning.sidebarActive') : reasoningTitle
        "
        :title="sidebarActive ? tm('reasoning.sidebarActive') : undefined"
        @click="toggleExpanded"
      >
        <span class="reasoning-title">
          {{ reasoningTitle }}
        </span>
        <v-icon
          size="22"
          class="reasoning-icon"
          :class="{ 'rotate-90': showInlineContent }"
        >
          mdi-chevron-right
        </v-icon>
      </button>
      <v-btn
        v-if="showSidebarAction"
        class="reasoning-sidebar-btn"
        icon="mdi-open-in-new"
        size="x-small"
        variant="text"
        :aria-label="tm('reasoning.openInSidebar')"
        @click.stop="openSidebar"
      />
    </div>

    <div v-if="showInlineContent" class="reasoning-content animate-fade-in">
      <ReasoningTimeline
        :parts="renderParts"
        :reasoning="reasoning"
        :is-dark="isDark"
        :is-streaming="isStreaming"
      />
    </div>

    <transition :name="previewTransitionName" mode="out-in">
      <div
        v-if="showStreamingPreview"
        :key="previewKey"
        class="reasoning-preview"
      >
        {{ previewText }}
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import {
  reasoningActivityCounts,
  reasoningActivityTitle,
} from '@/composables/useMessages';
import type { MessagePart } from '@/domain/chat';
import { useModuleI18n } from '@/i18n/composables';
import ReasoningTimeline from '@/components/chat/message_list_comps/ReasoningTimeline.vue';

const props = defineProps<{
  parts?: MessagePart[];
  reasoning?: string;
  isDark?: boolean;
  initialExpanded?: boolean;
  isStreaming?: boolean;
  hasNonReasoningContent?: boolean;
  showSidebarAction?: boolean;
  sidebarActive?: boolean;
}>();

const emit = defineEmits<{
  open: [];
}>();

const { tm } = useModuleI18n('features/chat');
const isExpanded = ref(Boolean(props.initialExpanded));
const previewText = ref('');
const previewKey = ref(0);
let previewTimer: ReturnType<typeof setInterval> | null = null;
let previewStartTimer: ReturnType<typeof setTimeout> | null = null;

const renderParts = computed<MessagePart[]>(() => {
  if (props.parts?.length) return props.parts;
  if (props.reasoning) {
    return [{ type: 'think', think: props.reasoning }];
  }
  return [];
});

const showSidebarAction = computed(() => Boolean(props.showSidebarAction));
const sidebarActive = computed(() => Boolean(props.sidebarActive));
const showInlineContent = computed(
  () => isExpanded.value && !sidebarActive.value,
);

const activityCounts = computed(() =>
  reasoningActivityCounts(renderParts.value, props.reasoning || ''),
);

const reasoningTitle = computed(() =>
  reasoningActivityTitle(activityCounts.value, tm),
);

const thinkingText = computed(() =>
  renderParts.value
    .filter((part) => part.type === 'think')
    .map((part) => String(part.think || ''))
    .join(''),
);

const showStreamingPreview = computed(
  () =>
    props.isStreaming &&
    !showInlineContent.value &&
    !props.hasNonReasoningContent &&
    previewText.value,
);

const previewTransitionName = computed(() =>
  props.hasNonReasoningContent
    ? 'reasoning-preview-collapse'
    : 'reasoning-preview-fade',
);

function toggleExpanded() {
  isExpanded.value = !isExpanded.value;
}

function openSidebar() {
  isExpanded.value = false;
  emit('open');
}

function latestReasoningPreview() {
  const lines = thinkingText.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.slice(-3).join('\n');
}

function updatePreviewLine() {
  const nextText = latestReasoningPreview();
  if (!nextText || nextText === previewText.value) return;
  previewText.value = nextText;
  previewKey.value += 1;
}

function stopPreviewTimer() {
  if (!previewTimer) return;
  clearInterval(previewTimer);
  previewTimer = null;
}

function stopPreviewStartTimer() {
  if (!previewStartTimer) return;
  clearTimeout(previewStartTimer);
  previewStartTimer = null;
}

function startPreviewTimer() {
  updatePreviewLine();
  if (!previewTimer) {
    previewTimer = setInterval(updatePreviewLine, 2000);
  }
}

function syncPreviewTimer() {
  if (
    props.isStreaming &&
    !showInlineContent.value &&
    !props.hasNonReasoningContent
  ) {
    if (!previewTimer && !previewStartTimer) {
      previewStartTimer = setTimeout(() => {
        previewStartTimer = null;
        if (
          props.isStreaming &&
          !showInlineContent.value &&
          !props.hasNonReasoningContent
        ) {
          startPreviewTimer();
        }
      }, 2000);
    }
    return;
  }

  stopPreviewStartTimer();
  stopPreviewTimer();
  if (!props.isStreaming) {
    previewText.value = '';
  }
}

watch(sidebarActive, (active) => {
  if (active) {
    isExpanded.value = false;
  }
});

watch(
  () => [
    props.isStreaming,
    isExpanded.value,
    props.hasNonReasoningContent,
    thinkingText.value,
    sidebarActive.value,
  ],
  syncPreviewTimer,
  {
    immediate: true,
  },
);

onBeforeUnmount(() => {
  stopPreviewStartTimer();
  stopPreviewTimer();
});
</script>

<style scoped>
.reasoning-block {
  margin: 6px 0;
  max-width: 100%;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: inherit;
  line-height: inherit;
}

.reasoning-header-row {
  display: flex;
  max-width: 100%;
  align-items: center;
  gap: 2px;
}

.reasoning-header {
  min-width: 0;
  max-width: 100%;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  user-select: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font: inherit;
  text-align: left;
}

.reasoning-header:hover {
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.reasoning-header:disabled {
  cursor: default;
  opacity: 0.72;
}

.reasoning-header:disabled:hover {
  color: inherit;
}

.reasoning-icon {
  color: currentcolor;
  transition: transform 0.2s ease;
  flex-shrink: 0;
  align-self: center;
}

.reasoning-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reasoning-sidebar-btn {
  flex: 0 0 auto;
  color: inherit;
  opacity: 0.72;
}

.reasoning-sidebar-btn:hover {
  opacity: 1;
}

.reasoning-content {
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 18px;
  background: rgb(var(--v-theme-surface));
  color: rgba(var(--v-theme-on-surface), 0.72);
  animation: fadeIn 0.2s ease-in-out;
  font-style: normal;
}

.reasoning-preview {
  max-width: 100%;
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.52);
  overflow: hidden;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  white-space: pre-line;
  font: inherit;
  font-size: 14.5px;
  line-height: 1.62;
  font-style: normal;
}

.animate-fade-in {
  animation: fadeIn 0.2s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

.rotate-90 {
  transform: rotate(90deg);
}

.reasoning-preview-fade-enter-active {
  transition: opacity 0.25s ease;
}

.reasoning-preview-fade-leave-active {
  transition: opacity 0.25s ease;
}

.reasoning-preview-fade-enter-from,
.reasoning-preview-fade-leave-to {
  opacity: 0;
}

.reasoning-preview-collapse-enter-active {
  transition: opacity 0.25s ease;
}

.reasoning-preview-collapse-leave-active {
  transition:
    opacity 0.18s ease,
    max-height 0.18s ease,
    margin-top 0.18s ease;
  overflow: hidden;
}

.reasoning-preview-collapse-enter-from {
  opacity: 0;
}

.reasoning-preview-collapse-leave-from {
  opacity: 1;
  max-height: 6.5em;
  margin-top: 4px;
}

.reasoning-preview-collapse-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
}
</style>
