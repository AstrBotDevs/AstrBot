// Author: elecvoid243
// Date: 2026-06-22
// Spec: docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md §4-5
//
// NOTE: TS-only syntax (`type` import keyword, type annotations) stripped
// from the plan's verbatim draft because Node v24.7.0 does not strip TS
// syntax in .mjs files even with --experimental-transform-types. The
// source module is still .ts; Node v24 strips types from .ts automatically
// at import time. See commit message for full rationale.
import assert from "node:assert/strict";
import test from "node:test";

import {
  parseSpcodeFileRestore,
  classifyReason,
  RESTORE_REASON_CODES,
} from "../src/composables/parseSpcodeFileRestore.ts";

const baseData = {
  restored: true,
  reason: null,
  file: "main.py",
  umo: "qq:1",
  worktree: "F:\\repo",
  directory: "F:\\repo",
  scope: "unstaged",
  elapsed_ms: 23,
  stderr: "",
};

test("parses success envelope", () => {
  const r = parseSpcodeFileRestore({ status: "ok", data: { ...baseData } });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.restored, true);
  assert.equal(r.snapshot.reason, null);
  assert.equal(r.snapshot.file, "main.py");
  assert.equal(r.snapshot.elapsedMs, 23);
  assert.equal(r.snapshot.scope, "unstaged");
});

test("parses success envelope with staged scope (v3.6)", () => {
  // Plugin v3.6+ auto-detects scope via git status and echoes it back.
  const r = parseSpcodeFileRestore({
    status: "ok",
    data: { ...baseData, scope: "staged" },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.restored, true);
  assert.equal(r.snapshot.scope, "staged");
});

test("defaults missing/invalid scope to unstaged (forward-compat)", () => {
  // Older plugin versions (<v3.6) always returned scope="unstaged".
  // Unknown future values should fall back to "unstaged" rather than
  // crashing the success toast.
  const r = parseSpcodeFileRestore({
    status: "ok",
    data: { ...baseData, scope: "bogus-scope" },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.scope, "unstaged");
});

test("parses failure envelope with reason", () => {
  const r = parseSpcodeFileRestore({
    status: "ok",
    data: { ...baseData, restored: false, reason: "untracked_file", stderr: "?? new.py" },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.restored, false);
  assert.equal(r.snapshot.reason, "untracked_file");
  assert.equal(r.snapshot.stderr, "?? new.py");
});

test("parses git_error with stderr", () => {
  const r = parseSpcodeFileRestore({
    status: "ok",
    data: { ...baseData, restored: false, reason: "git_error", stderr: "fatal: ..." },
  });
  assert.equal(r.snapshot.reason, "git_error");
  assert.equal(r.snapshot.stderr, "fatal: ...");
});

test("throws on missing data field", () => {
  assert.throws(
    () => parseSpcodeFileRestore({ status: "ok" }),
    /missing data/i,
  );
});

test("throws on wrong status", () => {
  assert.throws(
    () => parseSpcodeFileRestore({ status: "error" }),
    /status/i,
  );
});

test("classifyReason returns known reason unchanged", () => {
  for (const code of RESTORE_REASON_CODES) {
    assert.equal(classifyReason(code), code);
  }
});

test("classifyReason maps unknown to 'unknown'", () => {
  assert.equal(classifyReason("not_a_real_code"), "unknown");
});

test("classifyReason maps null/undefined to 'unknown'", () => {
  assert.equal(classifyReason(null), "unknown");
  assert.equal(classifyReason(undefined), "unknown");
});