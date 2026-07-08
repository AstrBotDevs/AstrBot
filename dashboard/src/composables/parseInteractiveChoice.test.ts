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
  assert.equal(
    isInteractiveChoicePayload({ type: "interactive_choice" }),
    true,
  );
});

test("isInteractiveChoicePayload rejects null", () => {
  assert.equal(isInteractiveChoicePayload(null), false);
});

test("validateInteractiveChoice accepts request_id", () => {
  const valid = {
    type: "interactive_choice",
    request_id: "r1",
    prompt: "test",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
  };
  assert.equal(validateInteractiveChoice(valid), true);
});

test("validateInteractiveChoice rejects missing request_id", () => {
  const invalid = {
    type: "interactive_choice",
    prompt: "test",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
  };
  assert.equal(validateInteractiveChoice(invalid), false);
});

test("validateInteractiveChoice rejects empty request_id", () => {
  const invalid = {
    type: "interactive_choice",
    request_id: "  ",
    prompt: "test",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
  };
  assert.equal(validateInteractiveChoice(invalid), false);
});

test("validateInteractiveChoice rejects duplicate option ids", () => {
  const invalid = {
    type: "interactive_choice",
    request_id: "r1",
    prompt: "test",
    options: [
      { id: "A", label: "a" },
      { id: "A", label: "b" },
    ],
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
  assert.equal(
    tryRecoverInteractiveChoiceFromPlainText(null as unknown as string),
    null,
  );
  assert.equal(
    tryRecoverInteractiveChoiceFromPlainText(undefined as unknown as string),
    null,
  );
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

// ── v1.1: extra_content 字段契约 ────────────────────────────────────
//
// 后端 v1.1 在 spec 里多了一个可选 `extra_content` 字段(≤5000 字符 Markdown),
// 用于在候选框里展示 LLM 推荐的"理由 / 注意事项"等。前端必须:
//   1. 接受它(`validateInteractiveChoice` 不应拒绝含 extra_content 的 part)
//   2. 截断超长内容(>5000 字符)作为防御性兜底
//   3. 缺省时为 undefined(不是 null,不是 "")
//   4. 未触顶时原样返回(同一对象引用,避免无谓重渲染)

test("validateInteractiveChoice accepts extra_content (v1.1)", () => {
  // LLM 写了完整 prose——validateInteractiveChoice 不应因此拒绝
  const withExtra = {
    type: "interactive_choice",
    request_id: "r-extra",
    prompt: "选一个部署方案?",
    options: [
      { id: "A", label: "蓝绿" },
      { id: "B", label: "灰度" },
    ],
    extra_content: "**推荐 B**。\n\n理由:\n- 兼顾成本与风险\n- LB 已就绪",
  };
  assert.equal(validateInteractiveChoice(withExtra), true);
});

test("validateInteractiveChoice accepts extra_content='' (v1.1)", () => {
  // 后端可能 strip 后传空串,前端不能因为空串就拒绝整个 part
  const emptyExtra = {
    type: "interactive_choice",
    request_id: "r-empty",
    prompt: "选一个部署方案?",
    options: [
      { id: "A", label: "蓝绿" },
      { id: "B", label: "灰度" },
    ],
    extra_content: "",
  };
  assert.equal(validateInteractiveChoice(emptyExtra), true);
});

test("truncateInteractiveChoice: extra_content > 5000 chars is truncated (v1.1)", () => {
  const longExtra = "x".repeat(6000);
  const input = {
    type: "interactive_choice" as const,
    request_id: "r1",
    prompt: "p",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
    extra_content: longExtra,
  };
  const out = truncateInteractiveChoice(input);
  assert.equal(out.extra_content?.length, 5000);
  // 返回的是新对象(因为 mutated)
  assert.notEqual(out, input);
});

test("truncateInteractiveChoice: extra_content within limit is untouched (v1.1)", () => {
  // ≤ 5000 字符不应触发 mutated——返回**同一对象引用**,
  // 让 Vue 的响应式系统能跳过不必要的下游重渲染。
  const input = {
    type: "interactive_choice" as const,
    request_id: "r1",
    prompt: "p",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
    extra_content: "**推荐 A**",
  };
  const out = truncateInteractiveChoice(input);
  assert.equal(out.extra_content, "**推荐 A**");
  // mutate 字段未变 → 应当返回原 part 引用
  assert.equal(out, input);
});

test("truncateInteractiveChoice: missing extra_content stays undefined (v1.1)", () => {
  // v1.0 旧数据没有 extra_content 字段,truncate 后仍为 undefined,
  // 不应被凭空补成 ""。
  const input = {
    type: "interactive_choice" as const,
    request_id: "r1",
    prompt: "p",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
  };
  const out = truncateInteractiveChoice(input);
  assert.equal(out.extra_content, undefined);
  assert.equal(out, input);
});

test("truncateInteractiveChoice: extra_content of wrong type is preserved as-is (v1.1)", () => {
  // 后端如果误传了非 string(例如 boolean),不应让它崩,也不应误改。
  const input = {
    type: "interactive_choice" as const,
    request_id: "r1",
    prompt: "p",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
    extra_content: true as unknown as string,
  };
  const out = truncateInteractiveChoice(input);
  assert.equal(out.extra_content, true);
});
