// Author: elecvoid243
// Date: 2026-07-17
// Spec: docs/superpowers/specs/2026-07-17-commit-message-ai-generate-design.md §Testing
// + Revision 2026-07-17 (structured JSON reply with few-shot examples)
//
// Verifies the bilingual commit-message prompt builder and the reply
// parser. Imports the .ts source directly; Node v24 strips types at
// import time.

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCommitMessagePrompt,
  parseCommitMessageReply,
  DIFF_CHAR_BUDGET,
} from "../src/composables/commitMessagePrompt.ts";

const files = [
  { path: "src/auth.py", status: "M", additions: 42, deletions: 7 },
  { path: "tests/test_x.py", status: "A", additions: 18, deletions: 0 },
];

// ── prompt builder ────────────────────────────────────────────────

test("zh prompt: JSON contract, few-shot examples, stats and diff", () => {
  const p = buildCommitMessagePrompt({
    language: "zh",
    files,
    rawDiff: "diff --git a/src/auth.py b/src/auth.py\n+line",
  });
  assert.match(p, /Conventional Commits/);
  assert.match(p, /72/);
  // JSON contract + few-shot examples (revision 2026-07-17).
  assert.ok(p.includes('{"subject"'));
  assert.ok(p.includes('"body"'));
  assert.ok(p.includes("输出示例"));
  assert.ok(p.includes("Markdown 代码块"));
  assert.ok(p.includes("src/auth.py (M, +42/-7)"));
  assert.ok(p.includes("tests/test_x.py (A, +18/-0)"));
  assert.ok(p.includes("diff --git a/src/auth.py"));
  assert.ok(!p.includes("(diff 已截断)"));
});

test("en prompt: JSON contract, few-shot examples, stats and diff", () => {
  const p = buildCommitMessagePrompt({
    language: "en",
    files,
    rawDiff: "diff --git a/src/auth.py b/src/auth.py\n+line",
  });
  assert.match(p, /Conventional Commits/);
  assert.match(p, /at most 72 characters/);
  assert.match(p, /Write the message in English/);
  assert.ok(p.includes('{"subject"'));
  assert.ok(p.includes('"body"'));
  assert.ok(p.includes("Output examples"));
  assert.ok(p.includes("no Markdown code fences"));
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

// ── reply parser ──────────────────────────────────────────────────

test("parser: clean JSON with body joins subject and body", () => {
  const reply =
    '{"subject": "feat(auth): 新增登录限制", "body": "- 连续失败 5 次锁定\\n- 新增 RetryLimiter"}';
  assert.equal(
    parseCommitMessageReply(reply),
    "feat(auth): 新增登录限制\n\n- 连续失败 5 次锁定\n- 新增 RetryLimiter",
  );
});

test("parser: empty body yields subject only", () => {
  assert.equal(
    parseCommitMessageReply('{"subject": "fix: 修复启动崩溃", "body": ""}'),
    "fix: 修复启动崩溃",
  );
});

test("parser: strips markdown code fences", () => {
  const reply = '```json\n{"subject": "docs: update readme", "body": ""}\n```';
  assert.equal(parseCommitMessageReply(reply), "docs: update readme");
});

test("parser: extracts JSON buried in prose", () => {
  const reply =
    '好的,根据改动我为你生成:\n{"subject": "feat: add retry", "body": ""}\n希望对你有帮助!';
  assert.equal(parseCommitMessageReply(reply), "feat: add retry");
});

test("parser: missing/empty/non-string subject returns null", () => {
  assert.equal(parseCommitMessageReply('{"body": "x"}'), null);
  assert.equal(parseCommitMessageReply('{"subject": "  ", "body": ""}'), null);
  assert.equal(parseCommitMessageReply('{"subject": 42, "body": ""}'), null);
  assert.equal(parseCommitMessageReply('["feat: x"]'), null);
});

test("parser: invalid JSON returns null", () => {
  assert.equal(parseCommitMessageReply("feat: add retry (no json at all)"), null);
  assert.equal(parseCommitMessageReply('{"subject": "broken'), null);
});

test("parser: non-string body is ignored", () => {
  assert.equal(
    parseCommitMessageReply('{"subject": "feat: x", "body": 123}'),
    "feat: x",
  );
});

// ── robustness against chatty / reasoning-model replies ──────────

test("parser: chatty reply with json fence and trailing prose", () => {
  // Real-world shape: conversational analysis, then a fenced json
  // block, then more prose containing brace fragments like
  // {"subject","body"} that must NOT poison the extraction.
  const reply = [
    "这正是组装出的完整 prompt（顺带解开了之前的谜团）。",
    "按该 prompt 的契约，合规的输出应为：",
    "```json",
    '{"subject": "feat(dashboard): AI 生成改用结构化 JSON", "body": "- prompt 附 few-shot 示例\\n- 超时放宽至 120s"}',
    "```",
    "经解析后填入 textarea 的效果：",
    "```",
    'feat(dashboard): ... prompt 要求输出 {"subject","body"} 并附示例',
    "```",
    "如果你想用这条 message 提交，告诉我即可。",
  ].join("\n");
  assert.equal(
    parseCommitMessageReply(reply),
    "feat(dashboard): AI 生成改用结构化 JSON\n\n- prompt 附 few-shot 示例\n- 超时放宽至 120s",
  );
});

test("parser: <think> reasoning block is stripped before parsing", () => {
  const reply =
    '<think>用户在等一条 commit message。先看看 diff……这里有 {"subject":"不相关","body":""} 的草稿。</think>{"subject": "fix: 修复登录重试", "body": ""}';
  assert.equal(parseCommitMessageReply(reply), "fix: 修复登录重试");
});

test("parser: invalid brace fragments in prose are skipped", () => {
  const reply =
    '输出格式是 {"subject","body"} 这样的 JSON,例如:\n{"subject": "docs: 更新说明", "body": ""}';
  assert.equal(parseCommitMessageReply(reply), "docs: 更新说明");
});

test("parser: json-labeled fence wins over an earlier plain fence", () => {
  const reply = [
    "```",
    '{"subject": "not: the real answer", "body": ""}',
    "```",
    "最终结果:",
    "```json",
    '{"subject": "feat: the real answer", "body": ""}',
    "```",
  ].join("\n");
  assert.equal(parseCommitMessageReply(reply), "feat: the real answer");
});
