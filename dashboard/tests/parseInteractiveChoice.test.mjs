// Author: elecvoid243
// Date: 2026-06-28
// Spec: docs/superpowers/specs/2026-06-28-dynamic-choice-box-rendering-design.md §2.3 / §3.2 / §7
//
// 测试 parseInteractiveChoice.ts 的纯函数:解包(unwrap) + 校验(validate) + 截断(truncate)。
// 覆盖 spec §3.2 字段约束、§7 错误处理。
import assert from "node:assert/strict";
import test from "node:test";

import {
  isInteractiveChoicePayload,
  unwrapInteractiveChoice,
  validateInteractiveChoice,
  truncateInteractiveChoice,
} from "../src/composables/parseInteractiveChoice.ts";

// ─── 公共 fixture ─────────────────────────────────────────────
const validOption = { id: "a", label: "GPT-4", description: "更强但更慢", value: "gpt-4" };
const validPart = {
  type: "interactive_choice",
  prompt: "请选择下一步使用的模型:",
  options: [validOption, { id: "b", label: "GPT-4 mini", value: "gpt-4-mini" }],
};

// ─── isInteractiveChoicePayload ──────────────────────────────
test("isInteractiveChoicePayload: 合法 InteractiveChoicePart 返回 true", () => {
  assert.equal(isInteractiveChoicePayload(validPart), true);
});

test("isInteractiveChoicePayload: 缺 type 字段返回 false", () => {
  assert.equal(isInteractiveChoicePayload({ prompt: "x", options: [validOption] }), false);
});

test("isInteractiveChoicePayload: type 不是 interactive_choice 返回 false", () => {
  assert.equal(isInteractiveChoicePayload({ type: "plain", text: "hi" }), false);
  assert.equal(isInteractiveChoicePayload({ type: "tool_call" }), false);
});

test("isInteractiveChoicePayload: 非对象(null / string / array)返回 false", () => {
  assert.equal(isInteractiveChoicePayload(null), false);
  assert.equal(isInteractiveChoicePayload("string"), false);
  assert.equal(isInteractiveChoicePayload([1, 2]), false);
});

// ─── unwrapInteractiveChoice ──────────────────────────────────
test("unwrapInteractiveChoice: plain + JSON 字符串前缀 { 解包为 InteractiveChoicePart", () => {
  const part = { type: "plain", text: JSON.stringify(validPart) };
  const result = unwrapInteractiveChoice(part);
  assert.deepEqual(result, validPart);
});

test("unwrapInteractiveChoice: 原生 interactive_choice part 透传", () => {
  const result = unwrapInteractiveChoice(validPart);
  assert.deepEqual(result, validPart);
});

test("unwrapInteractiveChoice: 普通 plain 文本不改动", () => {
  const part = { type: "plain", text: "hello world" };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: plain 但 JSON.parse 失败保留原 part(见 spec §7)", () => {
  const part = { type: "plain", text: '{ "type": "interactive_choice", "broken' };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: plain 但解析后 type 不是 interactive_choice 保留原 part", () => {
  const part = { type: "plain", text: '{"type":"other","foo":1}' };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: plain 但 text 不以 { 开头保留原 part", () => {
  const part = { type: "plain", text: "not json" };
  assert.deepEqual(unwrapInteractiveChoice(part), part);
});

test("unwrapInteractiveChoice: 非 plain / 非 interactive_choice 原样返回(图片等不重写)", () => {
  const imagePart = { type: "image", url: "http://x" };
  assert.deepEqual(unwrapInteractiveChoice(imagePart), imagePart);
});

// ─── validateInteractiveChoice ────────────────────────────────
test("validateInteractiveChoice: 合法 part 返回 true", () => {
  assert.equal(validateInteractiveChoice(validPart), true);
});

test("validateInteractiveChoice: 缺 prompt 返回 false", () => {
  assert.equal(validateInteractiveChoice({ type: "interactive_choice", options: [validOption] }), false);
});

test("validateInteractiveChoice: prompt 为空字符串返回 false", () => {
  assert.equal(validateInteractiveChoice({ type: "interactive_choice", prompt: "", options: [validOption] }), false);
});

test("validateInteractiveChoice: 缺 options 返回 false", () => {
  assert.equal(validateInteractiveChoice({ type: "interactive_choice", prompt: "x" }), false);
});

test("validateInteractiveChoice: options 只有一个元素返回 false(spec §3.2 至少 2 个)", () => {
  assert.equal(
    validateInteractiveChoice({ type: "interactive_choice", prompt: "x", options: [validOption] }),
    false,
  );
});

test("validateInteractiveChoice: options 元素缺 id 返回 false", () => {
  const bad = { type: "interactive_choice", prompt: "x", options: [{ label: "x", value: "y" }] };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: options 元素缺 label 返回 false", () => {
  const bad = { type: "interactive_choice", prompt: "x", options: [{ id: "a", value: "y" }] };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: options 元素缺 value 返回 false", () => {
  const bad = { type: "interactive_choice", prompt: "x", options: [{ id: "a", label: "y" }] };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: id 重复返回 false(spec §3.2)", () => {
  const bad = {
    type: "interactive_choice",
    prompt: "x",
    options: [
      { id: "a", label: "A", value: "1" },
      { id: "a", label: "B", value: "2" },
    ],
  };
  assert.equal(validateInteractiveChoice(bad), false);
});

test("validateInteractiveChoice: id 为空字符串返回 false", () => {
  const bad = {
    type: "interactive_choice",
    prompt: "x",
    options: [
      { id: "", label: "A", value: "1" },
      { id: "b", label: "B", value: "2" },
    ],
  };
  assert.equal(validateInteractiveChoice(bad), false);
});

// ─── truncateInteractiveChoice ───────────────────────────────
test("truncateInteractiveChoice: prompt 超 200 字截断", () => {
  const long = "a".repeat(300);
  const result = truncateInteractiveChoice({ type: "interactive_choice", prompt: long, options: [validOption] });
  assert.equal(result.prompt.length, 200);
});

test("truncateInteractiveChoice: title 超 30 字截断", () => {
  const result = truncateInteractiveChoice({ ...validPart, title: "a".repeat(50) });
  assert.equal(result.title.length, 30);
});

test("truncateInteractiveChoice: option.label 超 30 字截断", () => {
  const opt = { ...validOption, label: "a".repeat(60) };
  const result = truncateInteractiveChoice({ ...validPart, options: [opt] });
  assert.equal(result.options[0].label.length, 30);
});

test("truncateInteractiveChoice: option.description 超 200 字截断", () => {
  const opt = { ...validOption, description: "a".repeat(300) };
  const result = truncateInteractiveChoice({ ...validPart, options: [opt] });
  assert.equal(result.options[0].description.length, 200);
});

test("truncateInteractiveChoice: input_placeholder 超 60 字截断", () => {
  const result = truncateInteractiveChoice({ ...validPart, input_placeholder: "a".repeat(100) });
  assert.equal(result.input_placeholder.length, 60);
});

test("truncateInteractiveChoice: value 不截断", () => {
  const longValue = "a".repeat(1000);
  const result = truncateInteractiveChoice({
    ...validPart,
    options: [{ ...validOption, value: longValue }],
  });
  assert.equal(result.options[0].value.length, 1000);
});

test("truncateInteractiveChoice: 短字段不动", () => {
  const result = truncateInteractiveChoice(validPart);
  assert.equal(result, validPart);  // 不可变:如果未截断,返回原对象
});