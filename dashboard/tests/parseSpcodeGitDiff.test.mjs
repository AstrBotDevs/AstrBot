// Author: elecvoid243
// Date: 2026-06-30
// Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.1.1
//      + docs/superpowers/specs/2026-06-20-git-diff-scope-switcher-design.md §4.2
//
// Verifies the git-diff envelope parser. Mirrors
// tests/parseSpcodeGitShow.test.mjs style — import directly from
// the .ts source; Node v24 strips types at import time.
//
// Bug fix coverage (2026-06-30): when the backend returns an empty
// `diff` payload (e.g. scope=unstaged for an empty worktree, or a
// truncation that dropped the patch text) but a populated
// `files_changed` array, the parser MUST preserve the file metadata
// list. The previous implementation short-circuited on `!data.diff`
// and returned [], silently dropping every entry of files_changed.
//
// Note: this file is .mjs (not .ts) so it runs under `node --test`
// without a build step. We use untyped fixtures; the parser
// coerces everything to the canonical shape at runtime.

import assert from "node:assert/strict";
import test from "node:test";

import { parseSpcodeGitDiff } from "../src/composables/parseSpcodeGitDiff.ts";

/** Minimal base data with one modified file + a single-hunk diff. */
const baseData = {
  loaded: true,
  directory: "C:/repo",
  umo: "webchat-1",
  scope: "unstaged",
  diff: [
    "diff --git a/src/auth.py b/src/auth.py",
    "index 1234..5678 100644",
    "--- a/src/auth.py",
    "+++ b/src/auth.py",
    "@@ -1,3 +1,4 @@",
    " def login(user):",
    "+    assert user",
    "     return user.token",
    "",
  ].join("\n"),
  stat: " src/auth.py | 1 +",
  files_changed: [
    { path: "src/auth.py", status: "M", additions: 1, deletions: 0 },
  ],
  truncated: false,
  truncated_at_bytes: 0,
  max_bytes: 262144,
  elapsed_ms: 18,
  reason: null,
};

test("parseSpcodeGitDiff: success envelope populates files + meta", () => {
  const r = parseSpcodeGitDiff(baseData);
  assert.equal(r.files.length, 1);
  const f = r.files[0];
  assert.equal(f.path, "src/auth.py");
  assert.equal(f.status, "M");
  assert.equal(f.additions, 1);
  assert.equal(f.deletions, 0);
  assert.equal(f.isBinary, false);
  // Slice is the patch segment (1-indexed, leading "diff --git "
  // is preserved by the segmenter).
  assert.ok(f.slice && f.slice.startsWith("diff --git "));
  assert.equal(r.meta.scope, "unstaged");
  assert.equal(r.meta.truncated, false);
  assert.equal(r.meta.reason, null);
  assert.equal(r.meta.elapsedMs, 18);
  assert.equal(r.meta.directory, "C:/repo");
  assert.equal(r.meta.umo, "webchat-1");
  assert.equal(r.meta.loaded, true);
  assert.equal(r.rawDiff, baseData.diff);
});

test("parseSpcodeGitDiff: empty diff + populated files_changed preserves files (regression for data-loss bug)", () => {
  // Bug scenario: backend returns files_changed with metadata but
  // an empty/null diff payload. This is plausible when:
  //   - The diff command output is empty (clean worktree) but the
  //     status-derived list still includes untracked entries.
  //   - A truncation that dropped the patch text but kept metadata.
  // The parser MUST keep the file entries (slice=null) so the
  // sidebar can still render the file list.
  const data = {
    ...baseData,
    diff: "",
    files_changed: [
      { path: "src/auth.py", status: "M", additions: 0, deletions: 0 },
      { path: "new_file.ts", status: "A", additions: 0, deletions: 0 },
    ],
  };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.files.length, 2);
  assert.deepEqual(
    r.files.map((f) => f.path),
    ["src/auth.py", "new_file.ts"],
  );
  // Without a diff payload, slice is null and isBinary stays false.
  for (const f of r.files) {
    assert.equal(f.slice, null);
    assert.equal(f.isBinary, false);
  }
  // rawDiff preserves what the backend sent verbatim.
  assert.equal(r.rawDiff, "");
});

test("parseSpcodeGitDiff: null diff + populated files_changed preserves files", () => {
  // Same regression coverage but with the explicit null variant.
  const data = {
    ...baseData,
    diff: null,
    files_changed: [
      { path: "only.ts", status: "M", additions: 3, deletions: 1 },
    ],
  };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.files.length, 1);
  assert.equal(r.files[0].path, "only.ts");
  assert.equal(r.files[0].additions, 3);
  assert.equal(r.files[0].deletions, 1);
  assert.equal(r.files[0].slice, null);
});

test("parseSpcodeGitDiff: diff with only whitespace but files_changed populated", () => {
  // The backend may emit a status-only response where the diff
  // body is whitespace/empty but the files_changed carries the
  // entries. This is the failure mode the user reported in the
  // sidebar: "unstaged / staged list is empty" while the
  // "all (vs HEAD)" tab is populated.
  const data = {
    ...baseData,
    diff: "\n",
    files_changed: [
      { path: "untracked_1.ts", status: "??", additions: 0, deletions: 0 },
      { path: "untracked_2.ts", status: "??", additions: 0, deletions: 0 },
    ],
  };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.files.length, 2);
  // "??" is not a valid FileStatus; defensive normalization
  // narrows it to "unknown" so the UI can still render the row.
  assert.equal(r.files[0].status, "unknown");
  assert.equal(r.files[1].status, "unknown");
});

test("parseSpcodeGitDiff: empty files_changed returns empty list", () => {
  // Defensive: no files → empty files. Still tolerate any diff
  // value (including null) since the absence of files is the
  // single source of truth.
  const data = {
    ...baseData,
    diff: null,
    files_changed: [],
  };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.files.length, 0);
});

test("parseSpcodeGitDiff: missing files_changed returns empty list", () => {
  // Defensive: malformed envelope with files_changed absent.
  const data = { ...baseData };
  delete data.files_changed;
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.files.length, 0);
});

test("parseSpcodeGitDiff: files_changed is not an array returns empty list", () => {
  // Defensive: backend occasionally returns null instead of [].
  // Do not crash, do not leak the raw value into the snapshot.
  const data = { ...baseData, files_changed: null };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.files.length, 0);
});

test("parseSpcodeGitDiff: binary file flagged via diff text", () => {
  // Binary files: the slice has no textual hunks, only the
  // "Binary files ... differ" marker. The parser should set
  // isBinary=true and leave slice null.
  const data = {
    ...baseData,
    diff: [
      "diff --git a/asset.bin b/asset.bin",
      "index 1234..5678 100644",
      "Binary files a/asset.bin and b/asset.bin differ",
      "",
    ].join("\n"),
    files_changed: [
      { path: "asset.bin", status: "M", additions: 0, deletions: 0 },
    ],
  };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.files.length, 1);
  assert.equal(r.files[0].path, "asset.bin");
  assert.equal(r.files[0].isBinary, true);
  assert.equal(r.files[0].slice, null);
});

test("parseSpcodeGitDiff: multiple files preserves backend order + attaches slices", () => {
  const data = {
    ...baseData,
    diff: [
      "diff --git a/a.ts b/a.ts",
      "@@ -1 +1 @@",
      "-old",
      "+new",
      "diff --git a/b.ts b/b.ts",
      "@@ -1 +1 @@",
      "-old",
      "+new",
    ].join("\n"),
    files_changed: [
      { path: "a.ts", status: "M", additions: 1, deletions: 1 },
      { path: "b.ts", status: "M", additions: 1, deletions: 1 },
    ],
  };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.files.length, 2);
  // Order MUST mirror the backend (spec §4.1.1: backend is the
  // source of truth for file ordering in the sidebar).
  assert.deepEqual(
    r.files.map((f) => f.path),
    ["a.ts", "b.ts"],
  );
  assert.ok(r.files[0].slice && r.files[0].slice.includes("a/a.ts"));
  assert.ok(r.files[1].slice && r.files[1].slice.includes("b/b.ts"));
});

test("parseSpcodeGitDiff: unknown scope echo is normalized to null", () => {
  const data = { ...baseData, scope: "bogus" };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.meta.scope, null);
});

test("parseSpcodeGitDiff: missing scope is normalized to null", () => {
  // Pre-scope spcode plugin (v3.0) returns no scope field. The
  // parser must not leak the undefined into the typed Meta.
  const data = { ...baseData };
  delete data.scope;
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.meta.scope, null);
});

test("parseSpcodeGitDiff: malformed file status defaults to 'unknown'", () => {
  const data = {
    ...baseData,
    files_changed: [
      { path: "weird.bin", status: "Z", additions: 0, deletions: 0 },
    ],
  };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.files[0].status, "unknown");
});

test("parseSpcodeGitDiff: meta mirrors truncated + max_bytes for warning banner", () => {
  const data = {
    ...baseData,
    truncated: true,
    truncated_at_bytes: 102400,
    max_bytes: 102400,
  };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.meta.truncated, true);
  assert.equal(r.meta.truncatedAtBytes, 102400);
  assert.equal(r.meta.maxBytes, 102400);
});

test("parseSpcodeGitDiff: missing additions/deletions default to 0", () => {
  // Defensive: backend may omit additions/deletions for binary
  // or rename entries.
  const data = {
    ...baseData,
    files_changed: [{ path: "x.ts", status: "R" }],
  };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.files[0].additions, 0);
  assert.equal(r.files[0].deletions, 0);
});

test("parseSpcodeGitDiff: file missing in diff segments gets null slice but still appears", () => {
  // Edge case: files_changed lists a path but the diff payload
  // does not contain a matching "diff --git" segment (could happen
  // if the backend truncates the patch early). The file must
  // still be in the result with slice=null.
  const data = {
    ...baseData,
    diff: "", // intentionally empty
    files_changed: [
      { path: "no_segment.ts", status: "M", additions: 5, deletions: 2 },
    ],
  };
  const r = parseSpcodeGitDiff(data);
  assert.equal(r.files.length, 1);
  assert.equal(r.files[0].path, "no_segment.ts");
  assert.equal(r.files[0].slice, null);
  assert.equal(r.files[0].isBinary, false);
});
