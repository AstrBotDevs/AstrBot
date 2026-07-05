// Author: elecvoid243 (task12_impl)
// Date: 2026-07-03
// Spec: docs/superpowers/specs/2026-07-02-blocking-interactive-choice-design.md §5.1
//
// Test runner: node --test (Node v24 strips TS from .ts imports automatically).
// Run: cd dashboard && pnpm exec node --test --import tsx src/composables/parseInteractiveChoice.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  isInteractiveChoicePayload,
  validateInteractiveChoice,
  truncateInteractiveChoice,
  getOptionSubmitText,
  tryRecoverInteractiveChoiceFromPlainText,
} from "./parseInteractiveChoice.ts";

test("isInteractiveChoicePayload accepts valid type", () => {
  assert.equal(isInteractiveChoicePayload({ type: "interactive_choice" }), true);
});

test("isInteractiveChoicePayload rejects null", () => {
  assert.equal(isInteractiveChoicePayload(null), false);
});

test("validateInteractiveChoice accepts request_id", () => {
  const valid = {
    type: "interactive_choice",
    request_id: "r1",
    prompt: "test",
    options: [{ id: "A", label: "a" }, { id: "B", label: "b" }],
  };
  assert.equal(validateInteractiveChoice(valid), true);
});

test("validateInteractiveChoice rejects missing request_id", () => {
  const invalid = {
    type: "interactive_choice",
    prompt: "test",
    options: [{ id: "A", label: "a" }, { id: "B", label: "b" }],
  };
  assert.equal(validateInteractiveChoice(invalid), false);
});

test("validateInteractiveChoice rejects empty request_id", () => {
  const invalid = {
    type: "interactive_choice",
    request_id: "  ",
    prompt: "test",
    options: [{ id: "A", label: "a" }, { id: "B", label: "b" }],
  };
  assert.equal(validateInteractiveChoice(invalid), false);
});

test("validateInteractiveChoice rejects duplicate option ids", () => {
  const invalid = {
    type: "interactive_choice",
    request_id: "r1",
    prompt: "test",
    options: [{ id: "A", label: "a" }, { id: "A", label: "b" }],
  };
  assert.equal(validateInteractiveChoice(invalid), false);
});

test("truncateInteractiveChoice preserves request_id", () => {
  const input = {
    type: "interactive_choice" as const,
    request_id: "r1",
    prompt: "x".repeat(300),
    options: [{ id: "A", label: "a" }],
  };
  const out = truncateInteractiveChoice(input);
  assert.equal(out.request_id, "r1");
  assert.equal(out.prompt.length, 200);
});

test("getOptionSubmitText returns id+label when no value", () => {
  const opt = { id: "A", label: "alpha" };
  assert.equal(getOptionSubmitText(opt), "A. alpha");
});

// ── Round-2 migration: tryRecoverInteractiveChoiceFromPlainText ──────────
//
// Conversations persisted by the pre-fix `BotMessageAccumulator` have
// the OLD wire-format JSON string dumped into a plain-text part. This
// helper turns that back into a structured `InteractiveChoicePart` so
// the box renders at the original chronological position (instead of
// the page tail via orphan-injection).

const OLD_WIRE_JSON = JSON.stringify({
  request_id: "uuid-abc",
  spec: {
    type: "interactive_choice",
    prompt: "今晚打算做什么？",
    options: [
      { id: "A", label: "学习/写代码", description: "升级插件或新特性" },
      { id: "B", label: "追番/看剧" },
    ],
    input_placeholder: "或者输入你自己的想法",
  },
  expires_at: 1700000000,
  umo: "webchat:webchat!astrbot!30a3002e-d4b1-4dd9-b8bd-5a481c8c148b",
});

test("tryRecoverInteractiveChoiceFromPlainText: bare JSON string", () => {
  const recovered = tryRecoverInteractiveChoiceFromPlainText(OLD_WIRE_JSON);
  assert.ok(recovered);
  assert.equal(recovered!.type, "interactive_choice");
  assert.equal(recovered!.request_id, "uuid-abc");
  assert.equal(recovered!.prompt, "今晚打算做什么？");
  assert.equal(recovered!.options.length, 2);
  assert.equal(recovered!.options[0].id, "A");
  assert.equal(recovered!.options[1].label, "追番/看剧");
  assert.equal(recovered!.expires_at, 1700000000);
  assert.equal(recovered!.input_placeholder, "或者输入你自己的想法");
});

test("tryRecoverInteractiveChoiceFromPlainText: LLM narrative + JSON tail", () => {
  // Matches the bug screenshot exactly:
  // "好的，再次调用 ask_user_choice 工具：{...JSON...}"
  const text = `好的，再次调用 ask_user_choice 工具：${OLD_WIRE_JSON}`;
  const recovered = tryRecoverInteractiveChoiceFromPlainText(text);
  assert.ok(recovered);
  assert.equal(recovered!.request_id, "uuid-abc");
  assert.equal(recovered!.prompt, "今晚打算做什么？");
});

test("tryRecoverInteractiveChoiceFromPlainText: LLM narrative + JSON mid", () => {
  // Trailing footer noise (e.g. bot's "工具调用、结果回传链路正常")
  // must not confuse the brace-walk.
  const text = `好的，再次调用 ask_user_choice 工具：${OLD_WIRE_JSON}\n工具调用、结果回传链路正常。`;
  const recovered = tryRecoverInteractiveChoiceFromPlainText(text);
  assert.ok(recovered);
  assert.equal(recovered!.request_id, "uuid-abc");
  assert.equal(recovered!.prompt, "今晚打算做什么？");
});

test("tryRecoverInteractiveChoiceFromPlainText: returns null on narrative-only", () => {
  const text = "好的,今晚打算做点什么呢？我想想,先看个番吧。";
  assert.equal(tryRecoverInteractiveChoiceFromPlainText(text), null);
});

test("tryRecoverInteractiveChoiceFromPlainText: returns null on non-string input", () => {
  assert.equal(tryRecoverInteractiveChoiceFromPlainText(""), null);
  assert.equal(tryRecoverInteractiveChoiceFromPlainText(null as unknown as string), null);
  assert.equal(tryRecoverInteractiveChoiceFromPlainText(undefined as unknown as string), null);
});

test("tryRecoverInteractiveChoiceFromPlainText: returns null when spec fails validation", () => {
  // spec.options has only 1 entry — `validateInteractiveChoice` rejects
  const bad = JSON.stringify({
    request_id: "uuid-bad",
    spec: {
      type: "interactive_choice",
      prompt: "x",
      options: [{ id: "A", label: "only" }],
    },
  });
  assert.equal(tryRecoverInteractiveChoiceFromPlainText(bad), null);
});

test("tryRecoverInteractiveChoiceFromPlainText: returns null when request_id missing", () => {
  const bad = JSON.stringify({
    spec: {
      type: "interactive_choice",
      prompt: "x",
      options: [
        { id: "A", label: "a" },
        { id: "B", label: "b" },
      ],
    },
  });
  assert.equal(tryRecoverInteractiveChoiceFromPlainText(bad), null);
});

test("tryRecoverInteractiveChoiceFromPlainText: tolerates JSON truncated mid-brace-walk", () => {
  // Take a prefix of OLD_WIRE_JSON that does NOT close every brace
  // (last 30 chars chopped). The brace-walk should bail out cleanly
  // and return null instead of throwing.
  const truncated = OLD_WIRE_JSON.slice(0, OLD_WIRE_JSON.length - 30);
  assert.equal(tryRecoverInteractiveChoiceFromPlainText(truncated), null);
});

test("tryRecoverInteractiveChoiceFromPlainText: drops expires_at when not a number", () => {
  const noExpiry = JSON.stringify({
    request_id: "uuid-x",
    spec: {
      type: "interactive_choice",
      prompt: "x",
      options: [
        { id: "A", label: "a" },
        { id: "B", label: "b" },
      ],
    },
  });
  const recovered = tryRecoverInteractiveChoiceFromPlainText(noExpiry);
  assert.ok(recovered);
  assert.equal(recovered!.expires_at, undefined);
});
