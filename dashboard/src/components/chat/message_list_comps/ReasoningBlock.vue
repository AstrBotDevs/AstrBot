<template>
  <div class="reasoning-block" :class="{ 'reasoning-block--dark': isDark }">
    <button
      class="reasoning-header"
      :class="{ 'reasoning-header--trigger': openInSidebar }"
      type="button"
      @click="handlePrimaryAction"
    >
      <span class="reasoning-title">
        {{ tm("reasoning.thinking") }}
      </span>
      <v-icon
        size="small"
        class="reasoning-icon"
        :class="{ 'rotate-90': !openInSidebar && isExpanded }"
      >
        mdi-chevron-right
      </v-icon>
    </button>

    <div
      v-if="!openInSidebar && isExpanded"
      class="reasoning-content animate-fade-in"
    >
      <ReasoningTimeline
        :parts="renderParts"
        :reasoning="reasoning"
        :is-dark="isDark"
      />
    </div>

    <transition :name="previewTransitionName" mode="out-in">
      <div v-if="showStreamingPreview" :key="previewKey" class="reasoning-preview">
        {{ previewText }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import type { MessagePart } from "@/composables/useMessages";
import { useModuleI18n } from "@/i18n/composables";
import ReasoningTimeline from "@/components/chat/message_list_comps/ReasoningTimeline.vue";

const props = defineProps<{
  parts?: MessagePart[];
  reasoning?: string;
  isDark?: boolean;
  initialExpanded?: boolean;
  isStreaming?: boolean;
  hasNonReasoningContent?: boolean;
  openInSidebar?: boolean;
}>();

const emit = defineEmits<{
  open: [];
}>();

const { tm } = useModuleI18n("features/chat");
const isExpanded = ref(Boolean(props.initialExpanded));
const previewText = ref("");
const previewKey = ref(0);
let previewTimer: ReturnType<typeof setInterval> | null = null;
let previewStartTimer: ReturnType<typeof setTimeout> | null = null;

const renderParts = computed<MessagePart[]>(() => {
  if (props.parts?.length) return props.parts;
  if (props.reasoning) {
    return [{ type: "think", think: props.reasoning }];
  }
  return [];
});

const openInSidebar = computed(() => Boolean(props.openInSidebar));

const thinkingText = computed(() =>
  renderParts.value
    .filter((part) => part.type === "think")
    .map((part) => String(part.think || ""))
    .join(""),
);

const showStreamingPreview = computed(
  () =>
    props.isStreaming &&
    (openInSidebar.value || !isExpanded.value) &&
    !props.hasNonReasoningContent &&
    previewText.value,
);

const previewTransitionName = computed(() =>
  props.hasNonReasoningContent
    ? "reasoning-preview-collapse"
    : "reasoning-preview-fade",
);

function handlePrimaryAction() {
  if (openInSidebar.value) {
    emit("open");
    return;
  }
  isExpanded.value = !isExpanded.value;
}

function latestReasoningPreview() {
  const lines = thinkingText.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.slice(-3).join("\n");
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
    (openInSidebar.value || !isExpanded.value) &&
    !props.hasNonReasoningContent
  ) {
    if (!previewTimer && !previewStartTimer) {
      previewStartTimer = setTimeout(() => {
        previewStartTimer = null;
        if (
          props.isStreaming &&
          (openInSidebar.value || !isExpanded.value) &&
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
    previewText.value = "";
  }
}

watch(
  () => [
    props.isStreaming,
    isExpanded.value,
    props.hasNonReasoningContent,
    thinkingText.value,
    openInSidebar.value,
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
/* Reasoning 区块样式 */
.reasoning-container {
  margin-bottom: 12px;
  margin-top: 6px;
  border: 1px solid var(--v-theme-border);
  border-radius: 20px;
  overflow: hidden;
  width: fit-content;
}

.reasoning-header {
  display: inline-flex;
  align-items: center;
  padding: 8px 8px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s ease;
  border-radius: 20px;
}

.reasoning-header:hover {
  background-color: rgba(103, 58, 183, 0.08);
}

.reasoning-header.is-dark:hover {
  background-color: rgba(103, 58, 183, 0.15);
}

.reasoning-header--trigger {
  align-items: flex-start;
}

.reasoning-icon {
  margin-right: 6px;
  color: var(--v-theme-secondary);
  transition: transform 0.2s ease;
}

.reasoning-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--v-theme-secondary);
  letter-spacing: 0.3px;
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
