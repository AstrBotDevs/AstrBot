// Date: 2026-07-04
//
// Bug 3 fix: deterministic trigger for "已忽略".
//
// When the user types a chat-input message while an ask_user_choice
// prompt is pending, the prompt must be marked ignored before the new
// user_msg lands in `props.messages`. Driving the "已忽略" state from
// this explicit event — rather than from a runtime reverse-walk of
// `props.messages` (the previous `recomputeIgnored` watcher in
// `ChatMessageList.vue`) — is what prevents a follow-up Q2 from being
// mis-classified as ignored when the LLM emits it in the same bot
// record as the response text to the typed input.
//
// The ask_user_choice protocol itself treats a typed message as an
// implicit "abandon the prompt" signal, so this matches the semantic
// the user has already opted into by typing.
//
// Kept in a separate module (no `@/api` imports) so it can be unit-
// tested via the raw `node --test` runner that the rest of the
// interactive_choice regression suite uses.

import { useInteractiveChoiceStore } from "../stores/interactiveChoice.ts";

/**
 * Mark every currently-active ask_user_choice prompt under `umo` as
 * ignored. No-op when `umo` is empty or no choice is active.
 *
 * Args:
 *   umo: The unified-message-origin key (e.g. webchat session id).
 */
export function abandonPendingInteractiveChoices(umo: string): void {
  if (!umo) return;
  const store = useInteractiveChoiceStore();
  const activeIds = Object.keys(store.activeChoices[umo] ?? {});
  if (activeIds.length === 0) return;
  store.markIgnored(umo, activeIds);
}
