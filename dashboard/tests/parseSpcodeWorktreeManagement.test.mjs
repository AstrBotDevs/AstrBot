// Author: elecvoid243
// Date: 2026-06-27
// Spec: docs/superpowers/specs/2026-06-27-git-worktree-frontend-management-design.md §8

import assert from "node:assert/strict";
import test from "node:test";

import {
  parseSpcodeWorktreeAdd,
  parseSpcodeWorktreeRemove,
  parseSpcodeWorktreeLock,
  parseSpcodeWorktreeUnlock,
  classifyWorktreeReason,
  WORKTREE_MGMT_REASON_CODES,
  ALLOWED_WORKTREE_REASONS,
} from "../src/composables/parseSpcodeWorktreeManagement.ts";

const baseData = {
  loaded: true,
  directory: "C:/repo",
  umo: "webchat-1",
  worktree: "C:/repo/.worktrees/feat",
  worktrees: [
    {
      path: "C:/repo",
      head_sha: "abc1234",
      branch: "main",
      is_main: true,
      prunable: false,
      locked: null,
    },
  ],
  reason: null,
  stderr: "",
  elapsed_ms: 50,
};

test("parseSpcodeWorktreeAdd: success returns snapshot with branch", () => {
  const r = parseSpcodeWorktreeAdd({
    status: "ok",
    data: { ...baseData, branch: "feat" },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.branch, "feat");
  assert.equal(r.snapshot.worktree, "C:/repo/.worktrees/feat");
  assert.equal(r.snapshot.worktrees.length, 1);
});

test("parseSpcodeWorktreeRemove: success returns snapshot with removedPath", () => {
  const r = parseSpcodeWorktreeRemove({
    status: "ok",
    data: { ...baseData, removed_path: "C:/repo/.worktrees/feat" },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.removedPath, "C:/repo/.worktrees/feat");
  assert.equal(r.snapshot.worktree, "C:/repo/.worktrees/feat");
});

test("parseSpcodeWorktreeLock: success returns snapshot with locked=true + reason", () => {
  const r = parseSpcodeWorktreeLock({
    status: "ok",
    data: {
      ...baseData,
      locked: true,
      lock_reason: "WIP until PR #123 merged",
    },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.locked, true);
  assert.equal(r.snapshot.lockReason, "WIP until PR #123 merged");
});

test("parseSpcodeWorktreeUnlock: success returns snapshot with locked=false", () => {
  const r = parseSpcodeWorktreeUnlock({
    status: "ok",
    data: { ...baseData, locked: false },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.locked, false);
  assert.equal(r.snapshot.lockReason, null);
});

test("failure envelope (cannot_remove_main) still parses", () => {
  const r = parseSpcodeWorktreeRemove({
    status: "ok",
    data: { ...baseData, reason: "cannot_remove_main", stderr: "fatal: ..." },
  });
  // Business failure still parses (mirrors useSpcodeGitDiff convention).
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.meta.reason, "cannot_remove_main");
  assert.equal(r.snapshot.meta.stderr, "fatal: ...");
});

test("classifyWorktreeReason: known reason returns meta", () => {
  const meta = classifyWorktreeReason("worktree_locked", "remove");
  assert.equal(meta.i18nKey, "error.reason.worktree_locked");
  assert.equal(meta.color, "warning");
});

test("classifyWorktreeReason: withStderr for git_error", () => {
  const meta = classifyWorktreeReason("git_error", "remove");
  assert.equal(meta.withStderr, true);
  assert.equal(meta.color, "error");
});

test("classifyWorktreeReason: unknown endpoint-mismatched reason returns unknown", () => {
  // hook_rejected is a commit-only reason; classify on 'remove' should be unknown
  const meta = classifyWorktreeReason("hook_rejected", "remove");
  assert.equal(meta.i18nKey, "error.reason.unknown");
});

test("classifyWorktreeReason: null/undefined returns unknown", () => {
  assert.equal(classifyWorktreeReason(null, "add").i18nKey, "error.reason.unknown");
  assert.equal(classifyWorktreeReason(undefined, "lock").i18nKey, "error.reason.unknown");
});

test("classifyWorktreeReason: network always returns network", () => {
  const meta = classifyWorktreeReason("network", "add");
  assert.equal(meta.i18nKey, "error.reason.network");
});

test("ALLOWED_WORKTREE_REASONS covers all 4 endpoints", () => {
  for (const ep of ["add", "remove", "lock", "unlock"]) {
    assert.ok(Array.isArray(ALLOWED_WORKTREE_REASONS[ep]), `${ep} should be array`);
    assert.ok(ALLOWED_WORKTREE_REASONS[ep].length > 0, `${ep} should have reasons`);
  }
});
