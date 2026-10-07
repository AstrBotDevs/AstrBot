import assert from "node:assert/strict";
import test from "node:test";

import {
  isConfigValueEmpty,
  conditionRuleMatches,
  evaluateCondition,
} from "../src/utils/configCondition.mjs";

// ---- 向后兼容：原始值严格相等 ----

test("原始值按严格相等判定（向后兼容）", () => {
  assert.equal(conditionRuleMatches("a", "a"), true);
  assert.equal(conditionRuleMatches("a", "b"), false);
  assert.equal(conditionRuleMatches(true, true), true);
  assert.equal(conditionRuleMatches(false, true), false);
  assert.equal(conditionRuleMatches(0, 0), true);
  // 缺路径时 getValueBySelector 返回 undefined
  assert.equal(conditionRuleMatches(undefined, true), false);
  assert.equal(conditionRuleMatches(undefined, undefined), true);
});

// ---- empty 运算符 ----

test("empty: true 仅当值为空时成立", () => {
  assert.equal(conditionRuleMatches(undefined, { empty: true }), true);
  assert.equal(conditionRuleMatches(null, { empty: true }), true);
  assert.equal(conditionRuleMatches("", { empty: true }), true);
  assert.equal(conditionRuleMatches([], { empty: true }), true);
  assert.equal(conditionRuleMatches({}, { empty: true }), true);
  // 非空情形
  assert.equal(conditionRuleMatches("x", { empty: true }), false);
  assert.equal(conditionRuleMatches(0, { empty: true }), false);
  assert.equal(conditionRuleMatches(false, { empty: true }), false);
  assert.equal(conditionRuleMatches([1], { empty: true }), false);
});

test("empty: false 等价于 notEmpty: true", () => {
  assert.equal(conditionRuleMatches("", { empty: false }), false);
  assert.equal(conditionRuleMatches("x", { empty: false }), true);
  assert.equal(conditionRuleMatches([], { empty: false }), false);
  assert.equal(conditionRuleMatches([1], { empty: false }), true);
});

// ---- notEmpty 运算符 ----

test("notEmpty: true 仅当值非空时成立", () => {
  assert.equal(conditionRuleMatches("x", { notEmpty: true }), true);
  assert.equal(conditionRuleMatches([1], { notEmpty: true }), true);
  assert.equal(conditionRuleMatches("", { notEmpty: true }), false);
  assert.equal(conditionRuleMatches([], { notEmpty: true }), false);
  assert.equal(conditionRuleMatches({}, { notEmpty: true }), false);
  assert.equal(conditionRuleMatches(undefined, { notEmpty: true }), false);
});

test("notEmpty: false 等价于 empty: true", () => {
  assert.equal(conditionRuleMatches("", { notEmpty: false }), true);
  assert.equal(conditionRuleMatches("x", { notEmpty: false }), false);
});

// ---- 未知运算符对象退回深度相等 ----

test("未知运算符对象退回深度相等，避免误显/误隐", () => {
  assert.equal(conditionRuleMatches({ a: 1 }, { a: 1 }), true);
  assert.equal(conditionRuleMatches({ a: 1 }, { a: 2 }), false);
  assert.equal(conditionRuleMatches("x", {}), false);
});

// ---- isConfigValueEmpty ----

test("isConfigValueEmpty 的边界", () => {
  assert.equal(isConfigValueEmpty(""), true);
  assert.equal(isConfigValueEmpty(undefined), true);
  assert.equal(isConfigValueEmpty(null), true);
  assert.equal(isConfigValueEmpty([]), true);
  assert.equal(isConfigValueEmpty({}), true);
  assert.equal(isConfigValueEmpty(0), false);
  assert.equal(isConfigValueEmpty(false), false);
  assert.equal(isConfigValueEmpty(" "), false);
});

// ---- evaluateCondition：多键 AND + 解析回调 ----

test("evaluateCondition 多键全满足才显示，并按键解析实际值", () => {
  const iterable = {
    enabled: true,
    background: "",
    nested: { on: false },
  };
  const resolve = (key) => {
    const keys = key.split(".");
    let cur = iterable;
    for (const k of keys) {
      if (cur && typeof cur === "object" && k in cur) cur = cur[k];
      else return undefined;
    }
    return cur;
  };

  // 旧语义 + 新语义混合，多键 AND
  assert.equal(
    evaluateCondition({ enabled: true, background: { notEmpty: true } }, resolve),
    false,
  );
  assert.equal(
    evaluateCondition({ enabled: true, background: { empty: true } }, resolve),
    true,
  );
  // 嵌套键解析
  assert.equal(
    evaluateCondition({ "nested.on": false }, resolve),
    true,
  );
  // 缺条件直接通过
  assert.equal(evaluateCondition(undefined, resolve), true);
  assert.equal(evaluateCondition(null, resolve), true);
});

// ---- 插件真实场景：背景图留空时隐藏 opacity / blur ----

test("插件场景：page_background 为空时 notEmpty 条件隐藏依赖项", () => {
  const resolve = (key) => (key === "page_background" ? "" : undefined);
  assert.equal(
    evaluateCondition({ page_background: { notEmpty: true } }, resolve),
    false,
  );

  const resolveSet = (key) => (key === "page_background" ? "bg.png" : undefined);
  assert.equal(
    evaluateCondition({ page_background: { notEmpty: true } }, resolveSet),
    true,
  );
});
