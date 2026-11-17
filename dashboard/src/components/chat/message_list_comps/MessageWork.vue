<template>
  <div v-if="processBlocks.length" class="message-work">
    <button
      type="button"
      class="process-toggle"
      :aria-expanded="expanded"
      @click="
        expanded = !expanded;
        visited = true;
      "
    >
      <ThinkingIndicator v-if="isStreaming">{{ title }}</ThinkingIndicator>
      <span v-else>{{ title }}</span>
      <ChevronRight
        :size="18"
        :stroke-width="1.75"
        class="process-chevron"
        :class="{ 'is-expanded': expanded }"
        aria-hidden="true"
      />
    </button>
    <div
      class="process-collapse"
      :class="{ 'is-expanded': expanded }"
      :aria-hidden="!expanded"
      :inert="expanded ? undefined : ''"
    >
      <div class="process-collapse-inner">
        <div v-if="visited" class="message-work-content">
          <slot :blocks="processBlocks" :offset="0" />
        </div>
      </div>
    </div>
  </div>
  <slot :blocks="finalBlocks" :offset="processBlocks.length" />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ChevronRight } from "@lucide/vue";
import ThinkingIndicator from "@/components/chat/ThinkingIndicator.vue";
import type { MessageDisplayBlock } from "@/composables/useMessages";
import { useModuleI18n } from "@/i18n/composables";
import "@/components/chat/message_list_comps/processCollapse.css";

const props = defineProps<{
  blocks: MessageDisplayBlock[];
  isUser: boolean;
  isStreaming: boolean;
  stats?: Record<string, unknown>;
  createdAt?: string;
}>();
const { tm } = useModuleI18n("features/chat");
const expanded = ref(false);
const visited = ref(false);
const now = ref(Date.now());
const liveStart = ref<number | null>(null);
const liveEnd = ref<number | null>(null);
let timer: ReturnType<typeof setInterval> | undefined;

// Only a trailing content block can be the final response. Earlier replies stay in order.
const processBlocks = computed(() =>
  props.isUser
    ? []
    : props.blocks.slice(
        0,
        props.blocks[props.blocks.length - 1]?.kind === "content"
          ? -1
          : undefined,
      ),
);
const finalBlocks = computed(() =>
  props.blocks.slice(processBlocks.value.length),
);

watch(
  () => props.isStreaming,
  (streaming) => {
    clearInterval(timer);
    if (streaming) {
      expanded.value = true;
      visited.value = true;
      now.value = Date.now();
      const created = Date.parse(props.createdAt || "");
      liveStart.value = Number.isFinite(created) ? created : now.value;
      liveEnd.value = null;
      timer = setInterval(() => {
        now.value = Date.now();
      }, 1000);
    } else if (liveStart.value !== null) {
      expanded.value = false;
      liveEnd.value = Date.now();
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => clearInterval(timer));

const title = computed(() => {
  const stats = props.isStreaming ? undefined : props.stats;
  let duration: number | null = null;
  for (const key of ["duration", "total_duration"]) {
    const value = stats?.[key];
    if (value != null && Number.isFinite(Number(value)) && Number(value) >= 0) {
      duration = Number(value);
      break;
    }
  }
  if (
    duration === null &&
    stats?.start_time != null &&
    stats?.end_time != null
  ) {
    const elapsed = Number(stats.end_time) - Number(stats.start_time);
    if (Number.isFinite(elapsed) && elapsed >= 0) duration = elapsed;
  }
  if (duration === null && liveStart.value !== null) {
    duration = ((liveEnd.value ?? now.value) - liveStart.value) / 1000;
  }
  // Older history may have no timing metadata; do not invent a duration for it.
  if (duration === null) return tm("reasoning.workCompleted");
  const total = Math.max(0, Math.floor(duration));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  const time =
    hours > 0
      ? tm("reasoning.durationHours", { hours, minutes, seconds })
      : minutes > 0
      ? tm("reasoning.durationMinutes", { minutes, seconds })
      : tm("reasoning.durationSeconds", { seconds });
  return tm(props.isStreaming ? "reasoning.working" : "reasoning.worked", {
    duration: time,
  });
});
</script>

<style scoped>
.message-work {
  margin: 6px 0 12px;
}
.message-work-content {
  padding: 0 0 4px;
  margin-top: 2px;
}
.message-work-content > :deep(*) + :deep(*) {
  margin-top: 12px;
}
</style>
