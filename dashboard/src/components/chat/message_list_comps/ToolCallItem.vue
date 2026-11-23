<template>
  <div class="tool-call-item">
    <button
      class="tool-call-line"
      type="button"
      :aria-expanded="isExpanded"
      @click="toggleExpanded"
    >
      <slot name="label" :expanded="isExpanded" />
      <ChevronRight
        :size="22"
        class="process-chevron"
        :class="{ 'is-expanded': isExpanded }"
        aria-hidden="true"
      />
    </button>
    <transition name="tool-call-fade">
      <div
        v-if="isExpanded"
        class="tool-call-inline-details"
        :class="{ 'is-dark': isDark }"
      >
        <slot name="details" />
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ChevronRight } from "@lucide/vue";
import { ref } from "vue";
import "@/components/chat/message_list_comps/processCollapse.css";

const props = withDefaults(
  defineProps<{
    isDark?: boolean;
  }>(),
  {
    isDark: false,
  },
);

const isExpanded = ref(false);

const toggleExpanded = () => {
  isExpanded.value = !isExpanded.value;
};
</script>

<style scoped>
.tool-call-line {
  border: 0;
  padding: 0;
  background: transparent;
  font: inherit;
  line-height: inherit;
  color: rgba(var(--v-theme-on-surface), 0.7);
  cursor: pointer;
  user-select: none;
  transition:
    color 0.2s ease,
    opacity 0.2s ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.tool-call-line:hover {
  color: rgba(var(--v-theme-on-surface), 0.88);
  opacity: 1;
}

.tool-call-inline-details {
  margin-top: 6px;
  padding: 8px 10px;
  border-left: 2px solid var(--v-theme-border);
  border-radius: 6px;
  background-color: rgba(0, 0, 0, 0.02);
  font-size: inherit;
  line-height: inherit;
}

.tool-call-inline-details.is-dark {
  background-color: rgba(255, 255, 255, 0.04);
  border-left-color: rgba(255, 255, 255, 0.15);
}

.tool-call-fade-enter-active,
.tool-call-fade-leave-active {
  transition: opacity 0.1s ease;
}

.tool-call-fade-enter-from,
.tool-call-fade-leave-to {
  opacity: 0;
}
</style>
