<template>
  <div
    v-if="!hiddenForDock"
    :class="
      title
        ? [
            'action-card',
            { 'is-trace': locked && !docked, 'is-docked': docked },
          ]
        : 'button-action-row'
    "
    :role="title ? undefined : 'group'"
    :aria-live="docked ? 'polite' : undefined"
    :aria-atomic="docked ? true : undefined"
  >
    <template v-if="title">
      <div class="action-card-header">
        <span class="action-card-title">{{ title }}</span>
        <span v-if="stateLabel" class="action-card-state">{{
          stateLabel
        }}</span>
      </div>
      <button
        v-if="detail"
        class="action-card-toggle"
        type="button"
        :aria-expanded="showDetail"
        @click="showDetail = !showDetail"
      >
        <span>{{
          showDetail
            ? tm("actionCard.hideDetails")
            : tm("actionCard.showDetails")
        }}</span>
        <v-icon
          size="18"
          class="action-card-chevron"
          :class="{ expanded: showDetail }"
          >mdi-chevron-right</v-icon
        >
      </button>
      <pre v-if="detail && showDetail" class="action-card-detail">{{
        detail
      }}</pre>
      <!-- The app's own buttons, the decision last. -->
      <div v-if="!locked" class="action-card-actions">
        <v-btn
          v-for="button in cardButtons"
          :key="button.id + button.style"
          size="small"
          rounded="xl"
          class="action-card-btn"
          :variant="CARD_VARIANTS[button.style]"
          :color="button.style === 'danger' ? undefined : 'primary'"
          @click="choose(button)"
        >
          {{ button.label }}
        </v-btn>
      </div>
    </template>
    <template v-for="button in buttons" v-else :key="button.id">
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
        :class="[
          `style-${button.style}`,
          {
            'is-chosen': chosen === button.action.callback_data,
            'is-locked': locked && chosen !== button.action.callback_data,
          },
        ]"
        type="button"
        :disabled="locked"
        :aria-pressed="chosen === button.action.callback_data"
        @click="choose(button)"
      >
        <v-icon v-if="chosen === button.action.callback_data" size="14"
          >mdi-check</v-icon
        >
        {{ button.label }}
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref, watchEffect, type Ref } from "vue";
import {
  approvalCardKey,
  approvalCardState,
  rememberChosenCallback,
  wakeApprovalClockAt,
} from "@/composables/useActionRowChoices";
import type { MessagePart } from "@/composables/useMessages";
import { useModuleI18n } from "@/i18n/composables";

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

// `docked`: rendered on the input box as the pending approval (see Chat.vue).
const props = defineProps<{ part: MessagePart; docked?: boolean }>();
const emit = defineEmits<{ callback: [callbackData: string] }>();
const { tm } = useModuleI18n("features/chat");

const cardState = computed(() => approvalCardState(props.part));
const chosen = computed(() => cardState.value.chosen);
const locked = computed(() => cardState.value.locked);
// Let the shared clock lock this card when its callbacks stop working.
watchEffect(() => {
  if (!locked.value) wakeApprovalClockAt(Number(props.part.expires_at) * 1000);
});

// Chat.vue provides the key of the card it docks (the message list renders
// copies of the parts); the list leaves that card out until it is answered
// and keeps a one-line trace afterwards.
const dockedKey = inject<Ref<string> | null>("approvalDockKey", null);
const hiddenForDock = computed(
  () =>
    !props.docked &&
    !locked.value &&
    Boolean(dockedKey?.value) &&
    approvalCardKey(props.part) === dockedKey?.value,
);

// Rows that carry a title are drawn as a card with the detail folded away.
const title = computed(() =>
  typeof props.part.title === "string" ? props.part.title : "",
);
const detail = computed(() =>
  typeof props.part.detail === "string" ? props.part.detail : "",
);
const showDetail = ref(false);
const stateLabel = computed(() => {
  const { outcome, expired } = cardState.value;
  if (outcome === "rejected") return tm("actionCard.rejected");
  if (outcome === "expired") return tm("actionCard.expired");
  const button = buttons.value.find(
    (item) =>
      item.action.type === "callback" &&
      item.action.callback_data === chosen.value,
  );
  if (chosen.value && button) {
    return tm("actionCard.chosen", { label: button.label });
  }
  if (outcome === "approved") return tm("actionCard.approved");
  return expired ? tm("actionCard.expired") : "";
});

// "Don't ask again in this conversation" also switches the provided
// permission mode (the conversation's in Chat.vue, the thread's own in
// ThreadPanel.vue), like the backend: workspace stays confined.
const ALLOW_CONVERSATION_ACTION_ID = "astrbot_tool_approval_conversation";
const permissionMode = inject<Ref<string> | null>(
  "approvalPermissionMode",
  null,
);

function choose(button: MessageButton) {
  if (locked.value || button.action.type !== "callback") return;
  const callbackData = button.action.callback_data;
  // Emit first: the docked card's handler reads the card it was given, and
  // remembering the choice closes the dock.
  emit("callback", callbackData);
  if (button.id === ALLOW_CONVERSATION_ACTION_ID && permissionMode) {
    permissionMode.value = permissionMode.value.startsWith("workspace")
      ? "workspace_no_ask"
      : "full";
  }
  if (props.part.single_use === true) rememberChosenCallback(callbackData);
}

// Card buttons: reject quietly, allow-for-conversation tonal, allow filled.
const CARD_VARIANTS = {
  danger: "text",
  default: "text",
  primary: "tonal",
  success: "flat",
} as const;
const CARD_ORDER = { danger: 0, default: 1, primary: 2, success: 3 };
const cardButtons = computed(() =>
  buttons.value
    .filter((button) => button.action.type === "callback")
    .sort((a, b) => CARD_ORDER[a.style] - CARD_ORDER[b.style]),
);

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
.action-card {
  max-width: 560px;
  margin: 6px 0;
  padding: 10px 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.03);
}

.action-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.action-card-title {
  min-width: 0;
  flex: 1 1 auto;
  font-size: 0.9rem;
  font-weight: 500;
  overflow-wrap: anywhere;
}

.action-card-state {
  flex-shrink: 0;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 0.85em;
}

.action-card-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin: 4px 0 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font: inherit;
  font-size: 0.85em;
  cursor: pointer;
  user-select: none;
}

.action-card-toggle:hover {
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.action-card-chevron {
  color: currentcolor;
  transition: transform 0.2s ease;
}

.action-card-chevron.expanded {
  transform: rotate(90deg);
}

.action-card-detail {
  max-height: 240px;
  margin: 6px 0 0;
  padding: 8px 10px;
  overflow: auto;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.05);
  color: rgba(var(--v-theme-on-surface), 0.78);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8em;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.action-card-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 8px;
}

.action-card-btn {
  letter-spacing: 0;
  text-transform: none;
}

/* Answered approval: a quiet one-line record under the reply. */
.action-card.is-trace {
  padding: 2px 0;
  border: 0;
  background: transparent;
  font-size: 0.8rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.action-card.is-trace .action-card-header {
  gap: 6px;
}

.action-card.is-trace .action-card-toggle {
  font-size: 0.75rem;
}

.action-card.is-trace .action-card-title {
  flex: 0 1 auto;
  font-size: inherit;
  font-weight: 400;
}

.action-card.is-trace .action-card-state::before {
  content: "· ";
}

/* Docked on the input box, which draws the frame: title and details on the
   left, the decision on the right. */
.action-card.is-docked {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  column-gap: 12px;
  max-width: none;
  margin: 0 0 8px;
  padding: 2px 0 10px;
  border: 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 0;
  background: transparent;
}

.action-card.is-docked .action-card-header {
  grid-column: 1;
  grid-row: 1;
}

.action-card.is-docked .action-card-toggle {
  grid-column: 1;
  grid-row: 2;
  justify-self: start;
}

.action-card.is-docked .action-card-detail {
  grid-column: 1 / -1;
  grid-row: 3;
}

.action-card.is-docked .action-card-actions {
  grid-column: 2;
  grid-row: 1 / span 2;
  margin-top: 0;
}

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

/* A single-use row after its choice: the chosen button stays, others fade. */
.message-button.is-chosen {
  border-color: currentColor;
  cursor: default;
}

.message-button.is-locked {
  cursor: default;
  opacity: 0.38;
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
  .action-card.is-docked .action-card-actions {
    grid-column: 1 / -1;
    grid-row: 4;
    margin-top: 8px;
  }

  .message-button {
    padding-inline: 7px;
    font-size: 0.78rem;
  }
}
</style>
