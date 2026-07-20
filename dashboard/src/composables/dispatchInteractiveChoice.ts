// Author: elecvoid243
// Date: 2026-07-03
// Spec: docs/superpowers/specs/2026-07-02-blocking-interactive-choice-design.md §5.1
//
// Dispatcher for the SSE `interactive_choice` event emitted by the
// backend's `ask_user_choice` plugin (via `_push_to_webchat_back_queue`).
//
// Why this lives in its own module (rather than inlined inside
// `useMessages.ts`'s `processStreamPayload`):
//
//   1. `useMessages.ts` imports `@/api/http`, which is a Vue alias that
//      node's `--test` runner cannot resolve. Pulling the SSE-handler
//      out keeps it unit-testable in plain node.
//   2. The contract is small and self-contained: parse the wire payload,
//      push the part into the bot record so `ChatMessageList.vue` can
//      render `<InteractiveChoiceBox>`, and mirror it into the Pinia
//      store so hydrate / reconcile / tab-switch can recover it.
//
// The two surface mutations are **both required**:
//   - `botRecord.content.message.push(part)` powers the immediate render
//     (`<InteractiveChoiceBox v-else-if="part.type === 'interactive_choice'">`).
//   - `useInteractiveChoiceStore().addChoice(part)` keeps the store in
//     sync for `localStorage` persistence and `reconcile(umo)` on session
//     re-entry. Without it, a tab-switch or hard refresh would drop the box.

import { useInteractiveChoiceStore } from "../stores/interactiveChoice.ts";

import {
  interactiveChoicePartFromSsePayload,
  type InteractiveChoicePart,
} from "./parseInteractiveChoice.ts";

/**
 * Minimal bot-record shape this dispatcher mutates. Declared structurally
 * (rather than reusing `ChatRecord`) so the dispatcher has no dependency
 * on the larger `useMessages` module — keeping it unit-testable in plain
 * node without Vue aliases. The `message` array is typed as a structural
 * superset of `MessagePart` (and of `InteractiveChoicePart`) so the
 * dispatcher can be called from `useMessages.ts` (which holds the
 * `ChatRecord`/`MessagePart` discriminated union) without casts.
 */
export interface BotMessageLike {
  content: {
    message: Array<
      InteractiveChoicePart | (Record<string, unknown> & { type: string })
    >;
    isLoading?: boolean;
  };
}

/**
 * Apply a backend-emitted SSE `interactive_choice` payload to the client.
 *
 * Behaviour:
 *   - Returns silently when the payload fails validation.
 *   - On a valid part, appends it to `botRecord.content.message` and
 *     clears `isLoading`.
 *   - Mirrors the part into `useInteractiveChoiceStore().activeChoices`
 *     keyed by `request_id` (store dedups by id internally).
 *
 * The `umo` argument scopes the write to a single session's bucket.
 * It is **required** (Bug Y1 fix — see `stores/interactiveChoice.ts`
 * header). Callers must have the live UMO handy; the SSE pipeline in
 * `useMessages.ts` already passes `sessionId`, which is the same
 * value as `props.currentUmo` on the message list side.
 */
export function applyInteractiveChoiceSse(
  umo: string,
  botRecord: BotMessageLike,
  payload: unknown,
): void {
  if (!umo) {
    throw new Error(
      "applyInteractiveChoiceSse: missing required 'umo' (Bug Y1 fix)",
    );
  }
  const part = interactiveChoicePartFromSsePayload(payload);
  if (!part) return;
  botRecord.content.message.push(part);
  botRecord.content.isLoading = false;
  useInteractiveChoiceStore().addChoice(umo, part);
}

/**
 * Apply a backend-emitted SSE `interactive_choice_resolved` payload to
 * the client. Used to record server-driven terminal events (timeout
 * or `asyncio.CancelledError`) so the box can flip into the
 * non-interactive `cancelled` state.
 *
 * Behaviour:
 *   - Returns silently on malformed payload (wrong type, missing
 *     `data.request_id`, empty after trim).
 *   - **Filters on `data.reason === "cancelled"`**: events with any
 *     other reason (notably the v1.0 success-path `reason:
 *     "submitted"`, and any future reason values such as `"expired"`,
 *     `"error"`) are silently dropped. Without this filter, the
 *     success path would also write to `cancelledStates` and flip a
 *     just-submitted box into the cancelled visual. Reviewer flag
 *     from F3.
 *   - On a valid payload, writes the request_id into
 *     `useInteractiveChoiceStore().cancelledStates[umo]` via
 *     `markCancelled`.
 *   - Does **not** mutate any bot record `content.message` — the
 *     resolved event carries no `spec`, only the bookkeeping id.
 *
 * The `umo` argument scopes the write to a single session's bucket.
 * Throws when missing, matching the `applyInteractiveChoiceSse`
 * contract (Bug Y1 fix).
 */
export function applyInteractiveChoiceResolved(
  umo: string,
  payload: unknown,
): void {
  if (!umo) {
    throw new Error(
      "applyInteractiveChoiceResolved: missing required 'umo' (Bug Y1 fix)",
    );
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return;
  }
  const root = payload as Record<string, unknown>;
  if (root.type !== "interactive_choice_resolved") {
    return;
  }
  const data = root.data as Record<string, unknown> | undefined;
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return;
  }
  const requestId =
    typeof data.request_id === "string" ? data.request_id.trim() : "";
  if (!requestId) {
    return;
  }
  // Only the server-cancel / timeout path writes to cancelledStates.
  // Other reasons (notably v1.0's success-path `reason: "submitted"`)
  // are dropped here so a successful submission never flips the box
  // to the cancelled visual. Filter runs AFTER request_id validation
  // so malformed payloads still fail fast on the id check.
  const reason = typeof data.reason === "string" ? data.reason : "";
  if (reason !== "cancelled") {
    return;
  }
  // v1.2.1 fix: the `umo` param passed by the SSE pipeline
  // (`connection.sessionId`) is the raw conversation UUID, but the
  // InteractiveChoiceBox component reads from the store using the
  // full unified_msg_origin (e.g. "webchat:FriendMessage:webchat!u!cid").
  // Prefer the `data.umo` field set by the backend plugin (which has
  // access to the real UMO), falling back to the passed-in value for
  // backward compatibility with plugin versions that don't include it.
  const resolvedUmo =
    typeof data.umo === "string" && data.umo.trim()
      ? data.umo.trim()
      : umo;
  useInteractiveChoiceStore().markCancelled(resolvedUmo, requestId);
}
