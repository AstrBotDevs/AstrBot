// Author: elecvoid243
// Date: 2026-06-24
// Spec: docs/superpowers/specs/2026-06-24-chatui-git-workflow-controls-design.md §9.2
//
// Verifies the 4 endpoint parsers + the classifyReason(reason, endpoint)
// function. Mirrors tests/parseSpcodeFileRestore.test.mjs style — import
// directly from the .ts source; Node v24 strips types at import time.

import assert from "node:assert/strict";
import test from "node:test";

import {
  parseSpcodeGitStage,
  parseSpcodeGitUnstage,
  parseSpcodeGitCommit,
  parseSpcodeGitLog,
  classifyReason,
  GIT_WORKFLOW_REASON_CODES,
  ALLOWED_REASONS,
} from "../src/composables/parseSpcodeGitWorkflow.ts";

const stageBaseData = {
  success: true,
  reason: null,
  stderr: "",
  elapsed_ms: 8,
  umo: "webchat-1",
  worktree: "C:/repo",
  directory: "C:/repo",
  staged: true,
  files: ["src/main.py"],
  staged_count: 1,
};

test("parseSpcodeGitStage: success envelope", () => {
  const r = parseSpcodeGitStage({ status: "ok", data: { ...stageBaseData } });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.staged, true);
  assert.equal(r.snapshot.files.length, 1);
  assert.equal(r.snapshot.files[0], "src/main.py");
  assert.equal(r.snapshot.stagedCount, 1);
  assert.equal(r.snapshot.worktree, "C:/repo");
});

test("parseSpcodeGitStage: failure (path_unsafe)", () => {
  const r = parseSpcodeGitStage({
    status: "ok",
    data: {
      ...stageBaseData,
      success: false,
      reason: "path_unsafe",
      stderr: "fatal: ...",
      staged: false,
      files: [],
      staged_count: 0,
    },
  });
  // 业务失败仍 parse 成功(沿用 useSpcodeGitDiff 约定)
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.success, false);
  assert.equal(r.snapshot.reason, "path_unsafe");
  assert.equal(r.snapshot.stderr, "fatal: ...");
});

test("parseSpcodeGitUnstage: mirrors stage (reuses parser)", () => {
  const r = parseSpcodeGitUnstage({
    status: "ok",
    data: {
      ...stageBaseData,
      staged: false,
      unstaged: true,
      files: [],
      staged_count: 0,
    },
  });
  assert.equal(r.snapshot.unstaged, true);
  assert.equal(r.snapshot.staged, false);
});

test("parseSpcodeGitCommit: success returns 40-char SHA", () => {
  const r = parseSpcodeGitCommit({
    status: "ok",
    data: {
      success: true,
      reason: null,
      stderr: "",
      elapsed_ms: 47,
      umo: "x",
      worktree: "C:/repo",
      directory: "C:/repo",
      committed: true,
      sha: "418bb365a7c8a1b7c5b1b2d2e7b3a4f5a6b7c8d9",
      files: ["src/main.py"],
      committed_count: 1,
      staged_count: 0,
    },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.sha.length, 40);
  assert.equal(r.snapshot.committed, true);
  assert.equal(r.snapshot.stagedCount, 0);
});

test("parseSpcodeGitCommit: hook_rejected (failure keeps staged)", () => {
  const r = parseSpcodeGitCommit({
    status: "ok",
    data: {
      success: false,
      reason: "hook_rejected",
      stderr: "ruff ...",
      elapsed_ms: 1200,
      umo: "x",
      worktree: "C:/repo",
      directory: "C:/repo",
      committed: false,
      sha: "",
      files: ["src/main.py", "tests/foo.py"],
      committed_count: 0,
      staged_count: 2,
    },
  });
  // 关键不变量:失败后 staged 不丢(spec §3.4 决策 #9 + API doc §7.2)
  assert.equal(r.snapshot.stagedCount, 2);
  assert.equal(r.snapshot.committed, false);
  assert.equal(r.snapshot.sha, "");
  assert.equal(r.snapshot.reason, "hook_rejected");
});

test("parseSpcodeGitCommit: failure returns empty SHA", () => {
  // nothing_to_commit:失败时 sha 必为空
  const r = parseSpcodeGitCommit({
    status: "ok",
    data: {
      success: false,
      reason: "nothing_to_commit",
      stderr: "",
      elapsed_ms: 5,
      umo: "x",
      worktree: "C:/repo",
      directory: "C:/repo",
      committed: false,
      sha: "",
      files: [],
      committed_count: 0,
      staged_count: 0,
    },
  });
  assert.equal(r.snapshot.sha, "");
  assert.equal(r.snapshot.committed, false);
});

test("parseSpcodeGitStage: missing staged field defaults to false (backward compat)", () => {
  // v3.7 之前 plugin 可能不返回 staged 字段
  const d = { ...stageBaseData };
  delete d.staged;
  const r = parseSpcodeGitStage({ status: "ok", data: d });
  assert.equal(r.snapshot.staged, false);
  assert.equal(r.snapshot.stagedCount, 1);
});

test("parseSpcodeGitLog: empty repository", () => {
  const r = parseSpcodeGitLog({
    status: "ok",
    data: {
      success: false,
      reason: "empty_repository",
      loaded: false,
      elapsed_ms: 5,
      umo: "x",
      worktree: "C:/repo",
      directory: "C:/repo",
      ref: "HEAD",
      count: 0,
      has_more: false,
      truncated: false,
      max_bytes: 1048576,
      commits: [],
    },
  });
  assert.equal(r.snapshot.commits.length, 0);
  assert.equal(r.snapshot.reason, "empty_repository");
  assert.equal(r.snapshot.loaded, false);
});

test("parseSpcodeGitLog: parses commits array", () => {
  const r = parseSpcodeGitLog({
    status: "ok",
    data: {
      success: true,
      reason: null,
      loaded: true,
      elapsed_ms: 23,
      umo: "x",
      worktree: "C:/repo",
      directory: "C:/repo",
      ref: "HEAD",
      count: 1,
      has_more: false,
      truncated: false,
      max_bytes: 1048576,
      commits: [
        {
          sha: "418bb365a7c8a1b7c5b1b2d2e7b3a4f5a6b7c8d9",
          sha_short: "418bb36",
          author: { name: "elecvoid243", email: "elecvoid243@example.com" },
          committer: { name: "elecvoid243", email: "elecvoid243@example.com" },
          date: "2026-06-24T10:15:32+08:00",
          subject: "feat: add git-stage endpoint",
          body: "long description",
          parents: ["abc1234"],
          shortstat: { files: 3, additions: 142, deletions: 27 },
        },
      ],
    },
  });
  assert.equal(r.snapshot.commits.length, 1);
  assert.equal(r.snapshot.commits[0].shaShort, "418bb36");
  assert.equal(r.snapshot.commits[0].author.name, "elecvoid243");
  assert.equal(r.snapshot.commits[0].shortstat.additions, 142);
});

test("parseSpcodeGitLog: root commit (empty parents array)", () => {
  const r = parseSpcodeGitLog({
    status: "ok",
    data: {
      success: true,
      reason: null,
      loaded: true,
      elapsed_ms: 5,
      umo: "x",
      worktree: "C:/repo",
      directory: "C:/repo",
      ref: "HEAD",
      count: 1,
      has_more: false,
      truncated: false,
      max_bytes: 1048576,
      commits: [
        {
          sha: "0000000000000000000000000000000000000000",
          sha_short: "0000000",
          author: { name: "root", email: "root@example.com" },
          committer: { name: "root", email: "root@example.com" },
          date: "2026-01-01T00:00:00+00:00",
          subject: "Initial commit",
          body: null,
          parents: [],
          shortstat: { files: 1, additions: 1, deletions: 0 },
        },
      ],
    },
  });
  assert.equal(r.snapshot.commits[0].parents.length, 0);
  assert.equal(r.snapshot.commits[0].body, null);
});

test("parseSpcodeGitLog: truncated output flagged", () => {
  const r = parseSpcodeGitLog({
    status: "ok",
    data: {
      success: true,
      reason: null,
      loaded: true,
      elapsed_ms: 50,
      umo: "x",
      worktree: "C:/repo",
      directory: "C:/repo",
      ref: "HEAD",
      count: 200,
      has_more: true,
      truncated: true,
      max_bytes: 1048576,
      commits: [],
    },
  });
  assert.equal(r.snapshot.truncated, true);
  assert.equal(r.snapshot.hasMore, true);
});

test("parseSpcodeGitLog: empty commits array (success, not empty_repository)", () => {
  // 区分:success=true + commits=[] vs success=false + reason=empty_repository
  const r = parseSpcodeGitLog({
    status: "ok",
    data: {
      success: true,
      reason: null,
      loaded: true,
      elapsed_ms: 5,
      umo: "x",
      worktree: "C:/repo",
      directory: "C:/repo",
      ref: "HEAD",
      count: 0,
      has_more: false,
      truncated: false,
      max_bytes: 1048576,
      commits: [],
    },
  });
  assert.equal(r.snapshot.commits.length, 0);
  assert.equal(r.snapshot.reason, null);
  assert.equal(r.snapshot.success, true);
});

test("parseSpcodeGitLog: throws on missing data field", () => {
  assert.throws(() => parseSpcodeGitLog({ status: "ok" }), /missing data/i);
});

test("classifyReason: known reason for stage endpoint", () => {
  const m = classifyReason("path_unsafe", "stage");
  assert.equal(m.i18nKey, GIT_WORKFLOW_REASON_CODES.path_unsafe.i18nKey);
  assert.equal(m.color, "error");
});

test("classifyReason: endpoint mismatch (hook_rejected is commit-only)", () => {
  // hook_rejected 不在 stage / unstage / log 的允许集合中
  const mStage = classifyReason("hook_rejected", "stage");
  assert.equal(mStage.i18nKey, GIT_WORKFLOW_REASON_CODES.unknown.i18nKey);
  assert.equal(mStage.withReason, true);

  const mCommit = classifyReason("hook_rejected", "commit");
  assert.equal(mCommit.i18nKey, GIT_WORKFLOW_REASON_CODES.hook_rejected.i18nKey);
  assert.equal(mCommit.withStderr, true);
});

test("classifyReason: unknown reason always returns unknown", () => {
  assert.equal(classifyReason("foo_bar_baz", "stage").i18nKey, "error.reason.unknown");
  assert.equal(classifyReason(null, "stage").i18nKey, "error.reason.unknown");
  assert.equal(classifyReason(undefined, "commit").i18nKey, "error.reason.unknown");
  assert.equal(classifyReason("network", "log").i18nKey, "error.reason.network");
});

// P1-Critical regression guard: composables return the raw ReasonCode
// string in `result.reason`; the caller passes that string to
// `classifyReason` exactly once. If a future refactor accidentally
// feeds the i18nKey (e.g. "error.reason.path_unsafe") back into
// `classifyReason`, it must be classified as `unknown` (because the
// i18nKey is not in `ALLOWED_REASONS[endpoint]`). This test locks
// in that behavior so the double-classification bug from the
// 2026-06-24 review does not return.
test("classifyReason: i18nKey-shaped input is not a valid reason (defends against double-classification)", () => {
  const m = classifyReason("error.reason.path_unsafe", "stage");
  assert.equal(m.i18nKey, GIT_WORKFLOW_REASON_CODES.unknown.i18nKey);
  assert.equal(m.color, "error");
  // Most importantly: the user-facing flags must collapse to "generic
  // unknown error", not preserve the original reason's withStderr /
  // withReason semantics.
  assert.equal(m.withStderr, undefined);
});

test("ALLOWED_REASONS: log endpoint excludes empty_repository (空状态走模板分支)", () => {
  assert.equal(ALLOWED_REASONS.log.includes("empty_repository"), false);
  // 但 commit 也不在 log 集合中
  assert.equal(ALLOWED_REASONS.log.includes("hook_rejected"), false);
});
