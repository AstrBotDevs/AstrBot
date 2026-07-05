// Author: elecvoid243
// Date: 2026-07-05
// Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
// §2.4 Amendment F — pure helpers for the ask_user_choice filter.
//
// Why this file is its own module:
//   The dashboard's `useMessages.ts` pulls in `@/api` (Vite alias),
//   which makes it un-importable from a node-only test runner. By
//   keeping these two predicates in a leaf module, the live SSE
//   handler (`processStreamPayload`) and the history reload path
//   (`normalizeMessageParts`) share the same source of truth AND
//   the test file can exercise them in isolation (see
//   `useMessages.askUserChoiceFilter.test.ts`).
//
// The constants and predicates here are intentionally tiny — no
// Pinia, no Vue, no `@/api` — so they can be reused by either path
// without pulling in unrelated dependencies.

export const ASK_USER_CHOICE_TOOL_NAME = "ask_user_choice";

/** Predicate for the SSE `tool_call` payload (carries `name`). */
export function isAskUserChoiceToolCall(value: unknown): boolean {
  return (
    !!value &&
    typeof value === "object" &&
    (value as { name?: unknown }).name === ASK_USER_CHOICE_TOOL_NAME
  );
}

/**
 * Structural shape of a `ChatRecord` for the result predicate. Kept
 * inline so this module stays free of any `useMessages` import.
 */
interface ToolCallPartLike {
  type?: unknown;
  tool_calls?: unknown;
}

/**
 * Structural shape of a `ChatRecord` we walk over to find a
 * previously-inserted `tool_call` part.
 */
interface RecordLike {
  content: { message: ToolCallPartLike[] };
}

/**
 * Predicate for the SSE `tool_call_result` payload (does NOT carry
 * `name`; the call id must be matched against remembered state).
 *
 * The caller passes a closure-scoped `Set` of call ids whose
 * matching `tool_call` was filtered live. We also walk the
 * in-memory record as a defensive second check, in case the
 * filter-set was lost across remounts (e.g. a hot reload) but a
 * `tool_call` part with the ask_user_choice name was still
 * committed to the message.
 */
export function isAskUserChoiceToolCallResult(
  record: RecordLike,
  result: unknown,
  filteredToolCallIds: ReadonlySet<string>,
): boolean {
  if (!result || typeof result !== "object") return false;
  const callId = (result as { id?: unknown }).id;
  if (typeof callId !== "string" && typeof callId !== "number") return false;
  if (filteredToolCallIds.has(String(callId))) return true;
  for (const part of record.content.message) {
    if (!part || part.type !== "tool_call" || !Array.isArray(part.tool_calls))
      continue;
    for (const tc of part.tool_calls) {
      if (tc && (tc as { id?: unknown }).id === callId) {
        return (
          (tc as { name?: unknown }).name === ASK_USER_CHOICE_TOOL_NAME
        );
      }
    }
  }
  return false;
}
