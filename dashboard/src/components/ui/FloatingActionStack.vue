<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string;
  }>(),
  {
    label: 'Page actions',
  },
);
</script>

<template>
  <div class="floating-action-stack" :aria-label="label" role="group">
    <slot />
  </div>
</template>

<style scoped>
.floating-action-stack {
  position: fixed;
  right: max(16px, env(safe-area-inset-right));
  bottom: max(16px, env(safe-area-inset-bottom));
  z-index: 6;
  display: flex;
  flex-direction: column-reverse;
  gap: 12px;
}

.floating-action-stack :slotted(.v-btn) {
  box-shadow: 0 4px 12px rgb(24 33 43 / 18%);
}
</style>
