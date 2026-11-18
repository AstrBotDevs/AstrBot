<template>
  <div class="reasoning-block" :class="{ 'reasoning-block--dark': isDark }">
    <button
      class="reasoning-header process-toggle"
      :aria-expanded="isExpanded"
      type="button"
      @click="
        isExpanded = !isExpanded;
        visited = true;
      "
    >
      <span class="reasoning-title">
        <ThinkingIndicator v-if="isStreaming && !hasNonReasoningContent">
          {{ reasoningTitle }}
        </ThinkingIndicator>
        <template v-else>{{ reasoningTitle }}</template>
      </span>
      <ChevronRight
        :size="20"
        :stroke-width="1.75"
        aria-hidden="true"
        class="reasoning-icon process-chevron"
        :class="{
          'is-expanded': isExpanded,
        }"
      />
    </button>

    <div
      class="process-collapse"
      :class="{ 'is-expanded': isExpanded }"
      :aria-hidden="!isExpanded"
      :inert="isExpanded ? undefined : ''"
    >
      <div class="process-collapse-inner">
        <div v-if="visited" class="reasoning-content">
          <ReasoningTimeline
            :parts="renderParts"
            :reasoning="reasoning"
            :is-dark="isDark"
            :is-streaming="isStreaming"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import "@/components/chat/message_list_comps/processCollapse.css";
import { computed, ref, watch } from "vue";
import { ChevronRight } from "@lucide/vue";
import {
  reasoningActivityCounts,
  reasoningActivityTitle,
  type MessagePart,
} from "@/composables/useMessages";
import { useModuleI18n } from "@/i18n/composables";
import ThinkingIndicator from "@/components/chat/ThinkingIndicator.vue";
import ReasoningTimeline from "@/components/chat/message_list_comps/ReasoningTimeline.vue";

const props = defineProps<{
  parts?: MessagePart[];
  reasoning?: string;
  isDark?: boolean;
  initialExpanded?: boolean;
  isStreaming?: boolean;
  hasNonReasoningContent?: boolean;
}>();

const { tm } = useModuleI18n("features/chat");
const isExpanded = ref(Boolean(props.initialExpanded));
const visited = ref(isExpanded.value);

watch(
  () => Boolean(props.isStreaming && !props.hasNonReasoningContent),
  (active, wasActive) => {
    if (active) {
      isExpanded.value = true;
      visited.value = true;
    } else if (wasActive) {
      isExpanded.value = false;
    }
  },
  { immediate: true },
);

const renderParts = computed<MessagePart[]>(() => {
  if (props.parts?.length) return props.parts;
  if (props.reasoning) {
    return [{ type: "think", think: props.reasoning }];
  }
  return [];
});

const activityCounts = computed(() =>
  reasoningActivityCounts(renderParts.value, props.reasoning || ""),
);

const reasoningTitle = computed(() =>
  reasoningActivityTitle(activityCounts.value, tm),
);
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
  width: fit-content;
  max-width: 100%;
  border: 0;
  padding: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 8px;
  font: inherit;
  font-size: 1rem;
  line-height: 1.7;
  text-align: left;
}

@media (min-width: 761px) {
  .reasoning-header {
    font-size: 0.9375rem;
    line-height: 1.75;
  }
}

.reasoning-header:hover {
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.reasoning-icon {
  color: currentcolor;
  flex-shrink: 0;
  align-self: center;
}

.reasoning-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reasoning-content {
  margin-top: 6px;
  padding: 0;
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-style: normal;
}
</style>
