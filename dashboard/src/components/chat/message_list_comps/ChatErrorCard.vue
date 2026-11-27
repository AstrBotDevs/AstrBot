<template>
  <div
    class="chat-error-card"
    :class="{ 'is-warning': configurationError }"
    role="status"
  >
    <component
      :is="configurationError ? TriangleAlert : CircleAlert"
      :size="19"
      class="error-icon"
      aria-hidden="true"
    />
    <div class="error-content">
      <div class="error-title">
        {{ tm(`executionError.${category}.title`) }}
      </div>
      <p class="error-description">
        {{ tm(`executionError.${category}.description`) }}
      </p>
      <v-btn
        v-if="configurationError"
        class="configure-button"
        size="small"
        variant="tonal"
        @click="emit('configureModels')"
      >
        {{ tm("executionError.configureModels") }}
      </v-btn>
      <details v-if="message" class="error-details">
        <summary>{{ tm("executionError.details") }}</summary>
        <pre>{{ message }}</pre>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { CircleAlert, TriangleAlert } from "@lucide/vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{ code?: string; message?: string }>();
const emit = defineEmits<{ configureModels: [] }>();
const { tm } = useModuleI18n("features/chat");

const category = computed(() => {
  if (props.code === "noProvider") return "noModel";
  if (
    [
      "providerNotFound",
      "invalidProviderType",
      "invalidSessionProviderType",
      "blockedProvider",
    ].includes(props.code || "")
  ) {
    return "modelConfiguration";
  }
  if (props.code === "connection_error") return "connection";
  if (props.code === "ffmpegNotFound") return "ffmpegNotFound";
  return "generic";
});
const configurationError = computed(() =>
  ["noModel", "modelConfiguration"].includes(category.value),
);
</script>

<style scoped>
.chat-error-card {
  --error-accent: var(--v-theme-error);
  display: flex;
  gap: 12px;
  width: 100%;
  max-width: 520px;
  margin: 8px 0;
  padding: 16px;
  border: 1px solid rgba(var(--error-accent), 0.18);
  border-radius: 12px;
  background: rgba(var(--error-accent), 0.045);
  color: rgb(var(--v-theme-on-surface));
}
.is-warning {
  --error-accent: var(--v-theme-warning);
}
.error-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: rgb(var(--error-accent));
}
.error-content {
  flex: 1;
  min-width: 0;
}
.error-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.5;
}
.error-description {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.configure-button {
  margin-top: 12px;
  text-transform: none;
}
.error-details {
  margin-top: 12px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.65);
}
.error-details summary {
  cursor: pointer;
  width: fit-content;
}
.error-details pre {
  margin: 8px 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: monospace;
  font-size: 12px;
  line-height: 1.6;
}
</style>
