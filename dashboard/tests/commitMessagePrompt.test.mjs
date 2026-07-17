// Author: elecvoid243
// Date: 2026-07-17
// Spec: docs/superpowers/specs/2026-07-17-commit-message-ai-generate-design.md §Testing
//
// Verifies the bilingual commit-message prompt builder. Imports the
// .ts source directly; Node v24 strips types at import time.

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCommitMessagePrompt,
  DIFF_CHAR_BUDGET,
} from "../src/composables/commitMessagePrompt.ts";

const files = [
  { path: "src/auth.py", status: "M", additions: 42, deletions: 7 },
  { path: "tests/test_x.py", status: "A", additions: 18, deletions: 0 },
];

test("zh prompt: instruction, stats and diff sections", () => {
  const p = buildCommitMessagePrompt({
    language: "zh",
    files,
    rawDiff: "diff --git a/src/auth.py b/src/auth.py\n+line",
  });
  assert.match(p, /Conventional Commits/);
  assert.match(p, /72/);
  assert.match(p, /只返回 commit message 文本本身/);
  assert.ok(p.includes("src/auth.py (M, +42/-7)"));
  assert.ok(p.includes("tests/test_x.py (A, +18/-0)"));
  assert.ok(p.includes("diff --git a/src/auth.py"));
  assert.ok(!p.includes("(diff 已截断)"));
});

test("en prompt: instruction, stats and diff sections", () => {
  const p = buildCommitMessagePrompt({
    language: "en",
    files,
    rawDiff: "diff --git a/src/auth.py b/src/auth.py\n+line",
  });
  assert.match(p, /Conventional Commits/);
  assert.match(p, /at most 72 characters/);
  assert.match(p, /Write the message in English/);
  assert.match(p, /no Markdown code fences/);
  assert.ok(p.includes("src/auth.py (M, +42/-7)"));
  assert.ok(p.includes("diff --git a/src/auth.py"));
  assert.ok(!p.includes("(diff truncated)"));
});

test("diff longer than DIFF_CHAR_BUDGET is cut with marker", () => {
  const long = "x".repeat(DIFF_CHAR_BUDGET + 500);
  const zh = buildCommitMessagePrompt({ language: "zh", files, rawDiff: long });
  assert.ok(zh.includes("(diff 已截断)"));
  assert.ok(zh.includes("x".repeat(DIFF_CHAR_BUDGET)));
  assert.ok(!zh.includes("x".repeat(DIFF_CHAR_BUDGET + 1)));
  const en = buildCommitMessagePrompt({ language: "en", files, rawDiff: long });
  assert.ok(en.includes("(diff truncated)"));
});

test("null/empty diff: section omitted, stats-only note present", () => {
  const zh = buildCommitMessagePrompt({ language: "zh", files, rawDiff: null });
  assert.ok(!zh.includes("diff 内容:"));
  assert.ok(zh.includes("请仅根据文件统计推断改动意图"));
  const en = buildCommitMessagePrompt({ language: "en", files, rawDiff: "" });
  assert.ok(!en.includes("Diff:"));
  assert.ok(en.includes("infer the intent from the file stats only"));
});
