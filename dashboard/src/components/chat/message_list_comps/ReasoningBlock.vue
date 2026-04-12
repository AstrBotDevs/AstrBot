<template>
  <div class="reasoning-block" :class="{ 'reasoning-block--dark': isDark }">
    <button class="reasoning-header" type="button" @click="toggleExpanded">
      <span class="reasoning-title">
        {{ tm("reasoning.thinking") }}
      </span>
      <v-icon
        size="22"
        class="reasoning-icon"
        :class="{ 'rotate-90': isExpanded }"
      >
        mdi-chevron-right
      </v-icon>
    </button>
    <div v-if="isExpanded" class="reasoning-content animate-fade-in">
      <MarkdownRender
        :key="`reasoning-${isDark ? 'dark' : 'light'}`"
        :content="reasoning"
        class="reasoning-text markdown-content"
        :typewriter="false"
        :is-dark="isDark"
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

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { MarkdownRender } from "markstream-vue";

const props = defineProps({
  reasoning: {
    type: String,
    required: true,
  },
  isDark: {
    type: Boolean,
    default: false,
  },
  initialExpanded: {
    type: Boolean,
    default: false,
  },
  isStreaming: {
    type: Boolean,
    default: false,
  },
  hasNonReasoningContent: {
    type: Boolean,
    default: false,
  },
});

const { tm } = useModuleI18n("features/chat");
const isExpanded = ref(props.initialExpanded);
const previewText = ref("");
const previewKey = ref(0);
let previewTimer = null;
let previewStartTimer = null;

const showStreamingPreview = computed(
  () =>
    props.isStreaming &&
    !isExpanded.value &&
    !props.hasNonReasoningContent &&
    previewText.value,
);
const previewTransitionName = computed(() =>
  props.hasNonReasoningContent
    ? "reasoning-preview-collapse"
    : "reasoning-preview-fade",
);

const toggleExpanded = () => {
  isExpanded.value = !isExpanded.value;
};

const latestReasoningPreview = () => {
  const lines = props.reasoning
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.slice(-3).join("\n");
};

const updatePreviewLine = () => {
  const nextText = latestReasoningPreview();
  if (!nextText || nextText === previewText.value) return;
  previewText.value = nextText;
  previewKey.value += 1;
};

const stopPreviewTimer = () => {
  if (!previewTimer) return;
  clearInterval(previewTimer);
  previewTimer = null;
};

const stopPreviewStartTimer = () => {
  if (!previewStartTimer) return;
  clearTimeout(previewStartTimer);
  previewStartTimer = null;
};

const startPreviewTimer = () => {
  updatePreviewLine();
  if (!previewTimer) {
    previewTimer = setInterval(updatePreviewLine, 2000);
  }
};

const syncPreviewTimer = () => {
  if (props.isStreaming && !isExpanded.value && !props.hasNonReasoningContent) {
    if (!previewTimer && !previewStartTimer) {
      previewStartTimer = setTimeout(() => {
        previewStartTimer = null;
        if (
          props.isStreaming &&
          !isExpanded.value &&
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
};

watch(
  () => [props.isStreaming, isExpanded.value, props.hasNonReasoningContent],
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

.reasoning-header {
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

.reasoning-icon {
  color: currentcolor;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.reasoning-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reasoning-content {
  margin-top: 8px;
  padding: 0;
  color: rgba(var(--v-theme-on-surface), 0.7);
  animation: fadeIn 0.2s ease-in-out;
  font-style: italic;
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
  font-style: italic;
}

.reasoning-text {
  font-size: inherit;
  line-height: inherit;
  color: inherit;
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
  overflow: hidden;
  transition:
    max-height 0.45s cubic-bezier(0.55, 0, 1, 0.45),
    margin-top 0.45s cubic-bezier(0.55, 0, 1, 0.45),
    opacity 0.35s ease-in,
    transform 0.45s cubic-bezier(0.55, 0, 1, 0.45);
}

.reasoning-preview-collapse-enter-from {
  opacity: 0;
}

.reasoning-preview-collapse-leave-from {
  max-height: 5rem;
  opacity: 1;
  transform: translateY(0);
}

.reasoning-preview-collapse-leave-to {
  max-height: 0;
  margin-top: 0;
  opacity: 0;
  transform: translateY(-8px);
}
</style>
