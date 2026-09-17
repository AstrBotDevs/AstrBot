<template>
  <div class="message-content-transition">
    <Transition name="message-crossfade">
      <div v-if="loading" key="loading" class="message-content-layer">
        <ThinkingIndicator class="loading-message" />
      </div>
      <div v-else key="content" class="message-content-layer">
        <slot />
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import ThinkingIndicator from "@/components/chat/ThinkingIndicator.vue";

defineProps<{ loading?: boolean }>();
</script>

<style scoped>
.message-content-transition {
  display: grid;
}

.message-content-layer {
  grid-area: 1 / 1;
  align-self: start;
  min-width: 0;
  display: flow-root;
}

.loading-message {
  margin: 6px 0;
}

.message-crossfade-enter-active,
.message-crossfade-leave-active {
  transition: opacity 240ms ease;
}

.message-crossfade-leave-active {
  pointer-events: none;
}

.message-crossfade-enter-from,
.message-crossfade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .message-crossfade-enter-active,
  .message-crossfade-leave-active {
    transition: none;
  }
}
</style>
