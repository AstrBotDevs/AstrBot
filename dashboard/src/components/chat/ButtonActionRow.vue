<template>
  <div class="button-action-row" role="group">
    <template v-for="button in buttons" :key="button.id">
      <a
        v-if="button.action.type === 'url'"
        class="message-button"
        :class="`style-${button.style}`"
        :href="button.action.url"
        target="_blank"
        rel="noopener noreferrer"
      >
        <span>{{ button.label }}</span>
        <v-icon size="13">mdi-open-in-new</v-icon>
      </a>
      <button
        v-else
        class="message-button"
        :class="`style-${button.style}`"
        type="button"
        @click="emit('callback', button.action.callback_data)"
      >
        {{ button.label }}
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { MessagePart } from "@/composables/useMessages";

type ButtonStyle = "default" | "primary" | "success" | "danger";

interface CallbackButtonAction {
  type: "callback";
  callback_data: string;
}

interface UrlButtonAction {
  type: "url";
  url: string;
}

interface MessageButton {
  id: string;
  label: string;
  style: ButtonStyle;
  action: CallbackButtonAction | UrlButtonAction;
}

const props = defineProps<{ part: MessagePart }>();
const emit = defineEmits<{ callback: [callbackData: string] }>();

const buttons = computed<MessageButton[]>(() => {
  if (!Array.isArray(props.part.buttons)) return [];
  const result: MessageButton[] = [];
  for (const candidate of props.part.buttons) {
    if (!candidate || typeof candidate !== "object") continue;
    const button = candidate as Record<string, unknown>;
    const action = button.action as Record<string, unknown> | undefined;
    const id = typeof button.id === "string" ? button.id : "";
    const label = typeof button.label === "string" ? button.label : "";
    const style = ["primary", "success", "danger"].includes(
      String(button.style),
    )
      ? (button.style as ButtonStyle)
      : "default";

    if (!id || !label || !action) continue;
    if (action.type === "url" && typeof action.url === "string") {
      try {
        const url = new URL(action.url);
        if (url.protocol === "http:" || url.protocol === "https:") {
          result.push({
            id,
            label,
            style,
            action: { type: "url", url: url.toString() },
          });
        }
      } catch {
        // Ignore malformed or relative links from untrusted message content.
      }
      continue;
    }
    if (
      action.type === "callback" &&
      typeof action.callback_data === "string"
    ) {
      result.push({
        id,
        label,
        style,
        action: {
          type: "callback",
          callback_data: action.callback_data,
        },
      });
    }
  }
  return result;
});
</script>

<style scoped>
.button-action-row {
  display: flex;
  width: 100%;
  gap: 4px;
  margin: 5px 0 1px;
}

.message-button {
  display: inline-flex;
  min-width: 0;
  min-height: 34px;
  flex: 1 1 0;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px 10px;
  border: 1px solid rgba(var(--v-theme-primary), 0.16);
  border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.09);
  color: rgb(var(--v-theme-primary));
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  line-height: 1.2;
  text-align: center;
  text-decoration: none;
  cursor: pointer;
  transition:
    background-color 120ms ease,
    border-color 120ms ease,
    transform 120ms ease;
}

.message-button:hover {
  border-color: rgba(var(--v-theme-primary), 0.3);
  background: rgba(var(--v-theme-primary), 0.15);
}

.message-button:active {
  transform: translateY(1px);
}

.message-button:focus-visible {
  outline: 2px solid rgba(var(--v-theme-primary), 0.45);
  outline-offset: 1px;
}

.message-button.style-success {
  border-color: rgba(34, 197, 94, 0.2);
  background: rgba(34, 197, 94, 0.11);
  color: rgb(22, 163, 74);
}

.message-button.style-danger {
  border-color: rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.1);
  color: rgb(220, 38, 38);
}

.message-button.style-primary {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}

@media (max-width: 520px) {
  .message-button {
    padding-inline: 7px;
    font-size: 0.78rem;
  }
}
</style>
