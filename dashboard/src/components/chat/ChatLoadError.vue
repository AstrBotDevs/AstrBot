<template>
  <div class="chat-load-error" role="alert">
    <CircleAlert class="chat-load-error-icon" :size="16" aria-hidden="true" />
    <span class="chat-load-error-message">{{ message }}</span>
    <v-btn
      class="chat-load-error-retry"
      size="small"
      variant="text"
      rounded="pill"
      :loading="loading"
      @click="emit('retry')"
    >
      <RotateCw :size="14" aria-hidden="true" />
      {{ tm("actions.retry") }}
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import { CircleAlert, RotateCw } from "@lucide/vue";
import { useModuleI18n } from "@/i18n/composables";

defineProps<{ message: string; loading?: boolean }>();
const emit = defineEmits<{ retry: [] }>();
const { tm } = useModuleI18n("features/chat");
</script>

<style scoped>
.chat-load-error {
  display: flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  max-width: 100%;
  padding: 1px 0;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.8125rem;
  line-height: 1.5;
  text-align: start;
}

.chat-load-error-icon {
  flex-shrink: 0;
  color: rgba(var(--v-theme-on-surface), 0.45);
}

.chat-load-error-message {
  min-width: 0;
  overflow-wrap: anywhere;
}

.chat-load-error-retry {
  flex-shrink: 0;
  color: rgba(var(--v-theme-on-surface), 0.82);
  font: inherit;
  letter-spacing: normal;
}

.chat-load-error-retry :deep(.v-btn__content) {
  gap: 6px;
}
</style>
