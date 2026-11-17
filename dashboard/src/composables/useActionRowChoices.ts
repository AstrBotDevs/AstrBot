import { ref } from "vue";
import type { ChatRecord, MessagePart } from "@/composables/useMessages";

// Single-use button choices, shared by every rendering of the same row (the
// message list and the approval card docked on the input box). They are
// remembered in the browser because the message list is rebuilt from
// history after a reply ends and would forget them.
const CHOSEN_STORAGE_KEY = "chat.chosenButtonCallbacks";
const CHOSEN_STORAGE_LIMIT = 200;
// Browsers overflow timeouts longer than ~24.8 days, so the clock wakes at
// least once a day and re-arms for the rest.
const MAX_CLOCK_DELAY_MS = 24 * 60 * 60 * 1000;

function readChosenCallbacks(): string[] {
  try {
    const stored = JSON.parse(localStorage.getItem(CHOSEN_STORAGE_KEY) || "[]");
    return Array.isArray(stored)
      ? stored.filter((item) => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

export const chosenCallbacks = ref<string[]>(readChosenCallbacks());

export function rememberChosenCallback(callbackData: string) {
  const next = chosenCallbacks.value.filter((item) => item !== callbackData);
  next.push(callbackData);
  chosenCallbacks.value = next.slice(-CHOSEN_STORAGE_LIMIT);
  try {
    localStorage.setItem(
      CHOSEN_STORAGE_KEY,
      JSON.stringify(chosenCallbacks.value),
    );
  } catch {
    // Storage may be unavailable; the choice then lasts until a reload.
  }
}

/** Unlock a card again, e.g. when its callback could not be delivered. */
export function forgetChosenCallback(callbackData: string) {
  chosenCallbacks.value = chosenCallbacks.value.filter(
    (item) => item !== callbackData,
  );
  try {
    localStorage.setItem(
      CHOSEN_STORAGE_KEY,
      JSON.stringify(chosenCallbacks.value),
    );
  } catch {
    // Retrying stays possible even when storage is unavailable.
  }
}

// The one clock every approval card (and the dock) reads its expiry from.
// It only ticks at the next deadline a card asked for.
export const approvalNow = ref(Date.now());
let clockTimer: ReturnType<typeof setTimeout> | undefined;
let clockWakesAt = Infinity;

/**
 * Wake the shared approval clock at a deadline, unless it wakes earlier.
 *
 * @param deadlineMs Local epoch milliseconds; past or invalid values are ignored.
 */
export function wakeApprovalClockAt(deadlineMs: number) {
  const delay = deadlineMs - Date.now();
  if (!(delay > 0) || deadlineMs >= clockWakesAt) return;
  clearTimeout(clockTimer);
  const wait = Math.min(delay, MAX_CLOCK_DELAY_MS);
  clockWakesAt = Date.now() + wait;
  clockTimer = setTimeout(() => {
    clockWakesAt = Infinity;
    approvalNow.value = Date.now();
  }, wait + 50);
}

/** The first callback of a row: its identity across copies of the part. */
export function approvalCardKey(part: MessagePart | undefined): string {
  const buttons = Array.isArray(part?.buttons) ? part?.buttons : [];
  const button = buttons?.find(
    (item: any) => item?.action?.type === "callback",
  ) as any;
  return button?.action.callback_data || "";
}

/**
 * State of an action row, from the shared choices and clock.
 *
 * `expires_at` is in local epoch seconds: a streamed `expires_in` is anchored
 * on arrival (see normalizeMessageParts).
 *
 * @param part The actionrow part.
 * @returns The chosen callback, whether it expired, the backend outcome,
 *   whether its buttons are locked, and whether it is an open approval card.
 */
export function approvalCardState(part: MessagePart) {
  const singleUse = part.single_use === true;
  const buttons = Array.isArray(part.buttons) ? part.buttons : [];
  const chosen = singleUse
    ? (
        buttons.find(
          (button: any) =>
            button?.action?.type === "callback" &&
            chosenCallbacks.value.includes(button.action.callback_data),
        ) as any
      )?.action.callback_data || ""
    : "";
  const expiresAt = Number(part.expires_at);
  const expired =
    Number.isFinite(expiresAt) && approvalNow.value >= expiresAt * 1000;
  const outcome = typeof part.outcome === "string" ? part.outcome : "";
  const locked = Boolean(outcome) || expired || Boolean(chosen);
  return {
    chosen: chosen as string,
    expired,
    outcome,
    locked,
    open:
      part.type === "actionrow" &&
      singleUse &&
      typeof part.title === "string" &&
      Boolean(part.title) &&
      !locked,
  };
}

/** The newest open approval card of a conversation, docked on the input. */
export function latestOpenApproval(messages: ChatRecord[]) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    const parts = message.content?.message || [];
    for (let j = parts.length - 1; j >= 0; j--) {
      if (approvalCardState(parts[j]).open) return { message, part: parts[j] };
    }
  }
  return null;
}
