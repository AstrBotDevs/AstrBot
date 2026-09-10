<template>
  <span class="thinking-indicator" role="status">
    <slot>{{ tm(`message.loadingVariants.${loadingVariant}`) }}</slot>
  </span>
</template>

<script setup lang="ts">
import { useModuleI18n } from "@/i18n/composables";

const { tm } = useModuleI18n("features/chat");
const loadingVariant = Math.floor(Math.random() * 10);
</script>

<style scoped>
.thinking-indicator {
  display: block;
  width: fit-content;
  font-size: 1rem;
  line-height: 1.7;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

@media (min-width: 761px) {
  .thinking-indicator {
    font-size: 0.9375rem;
    line-height: 1.75;
  }
}

@supports ((background-clip: text) or (-webkit-background-clip: text)) {
  .thinking-indicator {
    background-image: linear-gradient(
      110deg,
      rgba(var(--v-theme-on-surface), 0.45) 40%,
      rgba(var(--v-theme-on-surface), 0.95) 50%,
      rgba(var(--v-theme-on-surface), 0.45) 60%
    );
    background-size: 250% 100%;
    background-position: 100% 0;
    background-clip: text;
    -webkit-background-clip: text;
    color: transparent;
    animation: thinking-sweep 2.8s ease-in-out infinite;
  }
}

@keyframes thinking-sweep {
  0%,
  15% {
    background-position: 100% 0;
  }
  85%,
  100% {
    background-position: 0% 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .thinking-indicator {
    animation: none;
    background: none;
    color: rgba(var(--v-theme-on-surface), 0.6);
  }
}

@media (forced-colors: active) {
  .thinking-indicator {
    animation: none;
    background: none;
    color: CanvasText;
  }
}
</style>
