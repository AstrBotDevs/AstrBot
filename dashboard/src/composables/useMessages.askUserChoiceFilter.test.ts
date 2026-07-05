// Author: elecvoid243
// Date: 2026-07-05
// Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md
// §2.4 Amendment F — frontend regression tests.
//
// Why this file exists (Bug 7, "phantom tool entry"):
//
//   After the `interactive_choice` part is persisted into a bot
//   message (the §2.2 fix), the same message also carries a
//   `tool_call` part for the underlying `ask_user_choice` tool call.
//   The two are rendered side-by-side as separate cards. The
//   `tool_call` part shows the raw "User Selected: ..." string in
//   its RESULT slot, the `interactive_choice` part shows "已选择:
//   <label>" via the Pinia-store-backed "I already chose" UI.
//
//   The post-fix frontend must drop the `tool_call` / `tool_call_result`
//   events for `ask_user_choice` so the dashboard never shows the
//   duplicate. We test the two pure helpers that drive the filter:
//
//     1. `isAskUserChoiceToolCall(parsed)`  — applied to the SSE
//        `tool_call` payload, where the `name` field is present.
//     2. `isAskUserChoiceToolCallResult(record, parsed, filteredIds)` —
//        applied to the SSE `tool_call_result` payload (no `name`).
//
//   The history-reload path (`normalizeMessageParts`) is also tested
//   here because the persisted data is what the bug actually surfaces
//   on a hard refresh.
//
// Run: cd dashboard && pnpm exec node --test src/composables/useMessages.askUserChoiceFilter.test.ts

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ASK_USER_CHOICE_TOOL_NAME,
  isAskUserChoiceToolCall,
  isAskUserChoiceToolCallResult,
} from "./askUserChoiceToolFilter.ts";
// `normalizeMessageParts` was extracted from `useMessages.ts` into
// the leaf module `normalizeMessageParts.ts` so this node-only
// test runner can exercise the ask_user_choice history-reload
// filter without pulling in `@/api` (Vite alias).
import { normalizeMessageParts } from "./normalizeMessageParts.ts";

function toolCallPart(toolCalls: Array<Record<string, unknown>>) {
  return { type: "tool_call", tool_calls: toolCalls };
}

function interactiveChoicePart(requestId: string) {
  return {
    type: "interactive_choice",
    request_id: requestId,
    prompt: "Pick one",
    options: [
      { id: "A", label: "alpha" },
      { id: "B", label: "beta" },
    ],
  };
}

test("isAskUserChoiceToolCall: true for the ask_user_choice name", () => {
  assert.equal(
    isAskUserChoiceToolCall({
      id: "call-x",
      name: ASK_USER_CHOICE_TOOL_NAME,
      args: { prompt: "Pick" },
    }),
    true,
  );
});

test("isAskUserChoiceToolCall: false for any other tool name", () => {
  assert.equal(
    isAskUserChoiceToolCall({ id: "call-x", name: "web_search" }),
    false,
  );
  assert.equal(
    isAskUserChoiceToolCall({ id: "call-x", name: "" }),
    false,
  );
  assert.equal(isAskUserChoiceToolCall({ id: "call-x" }), false);
});

test("isAskUserChoiceToolCall: false on non-objects", () => {
  assert.equal(isAskUserChoiceToolCall(null), false);
  assert.equal(isAskUserChoiceToolCall(undefined), false);
  assert.equal(isAskUserChoiceToolCall("ask_user_choice"), false);
  assert.equal(isAskUserChoiceToolCall(42), false);
});

test("isAskUserChoiceToolCallResult: true when id is in the filtered set (live SSE path)", () => {
  // Mirrors the live SSE handler: the `tool_call` was filtered, the
  // id is now remembered; the `tool_call_result` payload must drop.
  const record = { content: { message: [] } } as any;
  const filtered = new Set<string>(["call-abc"]);
  assert.equal(
    isAskUserChoiceToolCallResult(
      record,
      { id: "call-abc", ts: 1, result: "User selected: A (id=A)" },
      filtered,
    ),
    true,
  );
});

test("isAskUserChoiceToolCallResult: true when matching part carries the ask_user_choice name", () => {
  // Defensive branch: even if the filter-set was lost (e.g. the SSE
  // connection was re-established without replay), if there is a
  // `tool_call` part on the record with the same id and the name
  // `ask_user_choice`, we still drop the result.
  const record = {
    content: {
      message: [
        toolCallPart([{ id: "call-abc", name: ASK_USER_CHOICE_TOOL_NAME }]),
      ],
    },
  } as any;
  const filtered = new Set<string>();
  assert.equal(
    isAskUserChoiceToolCallResult(
      record,
      { id: "call-abc", ts: 1, result: "x" },
      filtered,
    ),
    true,
  );
});

test("isAskUserChoiceToolCallResult: false for unrelated tool calls", () => {
  const record = {
    content: {
      message: [
        toolCallPart([{ id: "call-xyz", name: "web_search" }]),
      ],
    },
  } as any;
  const filtered = new Set<string>();
  assert.equal(
    isAskUserChoiceToolCallResult(
      record,
      { id: "call-xyz", ts: 1, result: "x" },
      filtered,
    ),
    false,
  );
});

test("isAskUserChoiceToolCallResult: false for non-objects / missing id", () => {
  const record = { content: { message: [] } } as any;
  const filtered = new Set<string>();
  assert.equal(isAskUserChoiceToolCallResult(record, null, filtered), false);
  assert.equal(isAskUserChoiceToolCallResult(record, "string", filtered), false);
  assert.equal(
    isAskUserChoiceToolCallResult(record, { ts: 1, result: "x" }, filtered),
    false,
  );
});

// ---------------------------------------------------------------------------
// History reload path: `normalizeMessageParts` must strip
// ask_user_choice tool_call parts when an interactive_choice part is
// present in the same message. This handles data persisted BEFORE
// the backend filter was deployed.
// ---------------------------------------------------------------------------

test("normalizeMessageParts drops ask_user_choice tool_call part when interactive_choice is present", () => {
  const parts = [
    toolCallPart([
      {
        id: "call-abc",
        name: ASK_USER_CHOICE_TOOL_NAME,
        args: { prompt: "Pick" },
      },
    ]),
    interactiveChoicePart("req-1"),
  ];
  const normalized = normalizeMessageParts(parts);
  // The tool_call part should be dropped, the interactive_choice
  // part kept.
  assert.equal(normalized.length, 1);
  assert.equal(normalized[0].type, "interactive_choice");
});

test("normalizeMessageParts keeps ask_user_choice tool_call part when no interactive_choice is present", () => {
  // If the bot message only contains the tool_call (no
  // interactive_choice), we cannot infer that it is the ask_user_choice
  // duplicate — keep the part. This avoids accidentally dropping a
  // generic tool call that happens to be named ask_user_choice in a
  // future where the plugin may reuse the name.
  const parts = [
    toolCallPart([
      {
        id: "call-abc",
        name: ASK_USER_CHOICE_TOOL_NAME,
        args: { prompt: "Pick" },
      },
    ]),
  ];
  const normalized = normalizeMessageParts(parts);
  assert.equal(normalized.length, 1);
  assert.equal(normalized[0].type, "tool_call");
});

test("normalizeMessageParts strips ask_user_choice sibling inside a mixed tool_call part", () => {
  // A tool_call part may carry multiple tool calls (one per LLM
  // decision); only the ask_user_choice one is a duplicate, the
  // sibling should stay.
  const parts = [
    toolCallPart([
      { id: "call-abc", name: ASK_USER_CHOICE_TOOL_NAME, args: {} },
      { id: "call-xyz", name: "web_search", args: {} },
    ]),
    interactiveChoicePart("req-1"),
  ];
  const normalized = normalizeMessageParts(parts);
  assert.equal(normalized.length, 2);
  const [tcPart, icPart] = normalized;
  assert.equal(icPart.type, "interactive_choice");
  assert.equal(tcPart.type, "tool_call");
  const toolCalls = (tcPart as { tool_calls?: unknown[] }).tool_calls ?? [];
  assert.equal(toolCalls.length, 1);
  assert.equal((toolCalls[0] as { name: string }).name, "web_search");
});

test("normalizeMessageParts does not touch non-ask_user_choice tool_call parts", () => {
  const parts = [
    toolCallPart([{ id: "call-xyz", name: "web_search" }]),
  ];
  const normalized = normalizeMessageParts(parts);
  assert.equal(normalized.length, 1);
  assert.equal(normalized[0].type, "tool_call");
});
