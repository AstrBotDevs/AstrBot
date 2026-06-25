// Author: elecvoid243
// Date: 2026-06-25
// Spec: docs/superpowers/specs/2026-06-25-git-show-design.md §9.2
//
// Verifies the git-show envelope parser. Mirrors
// tests/parseSpcodeGitWorkflow.test.mjs style — import directly from
// the .ts source; Node v24 strips types at import time.

import assert from "node:assert/strict";
import test from "node:test";

import { parseSpcodeGitShow } from "../src/composables/parseSpcodeGitShow.ts";

const baseData = {
  success: true,
  reason: null,
  loaded: true,
  stderr: "",
  elapsed_ms: 18,
  umo: "webchat-1",
  worktree: "C:/repo",
  directory: "C:/repo",
  ref: "HEAD",
  resolved_sha: "418bb3650b2ed2178ebd636178b226d1a5fee76ff",
  parents: ["82cbc23f8d4bfc917465d4c3f772a7eae85d31d2"],
  author: { name: "elecvoid243", email: "elecvoid243@example.com" },
  date: "2026-06-25T08:00:00+08:00",
  subject: "feat: add git-show endpoint",
  body: "Returns commit metadata + modified files list\nfor given ref.",
  files: [
    {
      path: "src/auth.py",
      status: "M",
      additions: 42,
      deletions: 7,
    },
    {
      path: "tests/test_x.py",
      status: "A",
      additions: 18,
      deletions: 0,
    },
  ],
  count: 2,
  truncated: false,
  max_files: 500,
};

test("parseSpcodeGitShow: success envelope", () => {
  const r = parseSpcodeGitShow({ status: "ok", data: { ...baseData } });
  assert.equal(r.kind, "ok");
  const s = r.snapshot;
  assert.equal(s.success, true);
  assert.equal(s.reason, null);
  assert.equal(s.commit.ref, "HEAD");
  assert.equal(s.commit.resolvedSha, baseData.resolved_sha);
  assert.equal(s.commit.subject, baseData.subject);
  assert.equal(s.commit.body, baseData.body);
  assert.equal(s.commit.author.name, "elecvoid243");
  assert.equal(s.files.length, 2);
  assert.equal(s.files[0].path, "src/auth.py");
  assert.equal(s.files[0].status, "M");
  assert.equal(s.files[0].additions, 42);
  assert.equal(s.files[0].deletions, 7);
  assert.equal(s.files[0].oldPath, null); // M has no oldPath
  assert.equal(s.files[1].path, "tests/test_x.py");
  assert.equal(s.files[1].status, "A");
  assert.equal(s.count, 2);
  assert.equal(s.truncated, false);
  assert.equal(s.maxFiles, 500);
});

test("parseSpcodeGitShow: rename file (R) carries oldPath + similarity", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      files: [
        {
          path: "new_name.py",
          old_path: "old_name.py",
          status: "R",
          similarity: 95,
          additions: 0,
          deletions: 0,
        },
      ],
      count: 1,
    },
  });
  assert.equal(r.kind, "ok");
  const f = r.snapshot.files[0];
  assert.equal(f.status, "R");
  assert.equal(f.oldPath, "old_name.py");
  assert.equal(f.similarity, 95);
});

test("parseSpcodeGitShow: copy file (C) carries oldPath + similarity", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      files: [
        {
          path: "src/copy.py",
          old_path: "src/original.py",
          status: "C",
          similarity: 80,
          additions: 10,
          deletions: 0,
        },
      ],
      count: 1,
    },
  });
  assert.equal(r.kind, "ok");
  const f = r.snapshot.files[0];
  assert.equal(f.status, "C");
  assert.equal(f.oldPath, "src/original.py");
  assert.equal(f.similarity, 80);
});

test("parseSpcodeGitShow: M status should NOT have oldPath even if provided", () => {
  // Defensive: the backend should not include old_path for non-R/C
  // statuses, but if it does, the parser should clear it (per spec
  // §3.3: R/C exclusive). This guards against backend drift.
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      files: [
        {
          path: "src/main.py",
          old_path: "should_be_ignored.py",
          similarity: 100,
          status: "M",
          additions: 5,
          deletions: 1,
        },
      ],
      count: 1,
    },
  });
  assert.equal(r.kind, "ok");
  const f = r.snapshot.files[0];
  assert.equal(f.status, "M");
  assert.equal(f.oldPath, null);
  assert.equal(f.similarity, null);
});

test("parseSpcodeGitShow: failure envelope (ref_not_found)", () => {
  // The success path is `data.reason === null`; failure is encoded
  // as a non-null reason. The parser still returns `kind: "ok"`
  // with a populated snapshot, and the caller (useSpcodeGitShow)
  // inspects `snapshot.success` to dispatch the error path.
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      success: false,
      reason: "ref_not_found",
      files: [],
      count: 0,
    },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.success, false);
  assert.equal(r.snapshot.reason, "ref_not_found");
  assert.equal(r.snapshot.files.length, 0);
  assert.equal(r.snapshot.count, 0);
});

test("parseSpcodeGitShow: failure envelope (commit_too_large)", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      success: false,
      reason: "commit_too_large",
      files: [],
      count: 0,
    },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.success, false);
  assert.equal(r.snapshot.reason, "commit_too_large");
});

test("parseSpcodeGitShow: missing envelope throws", () => {
  // Missing `status` should be a parse error, not a graceful "ok".
  assert.throws(() => parseSpcodeGitShow({ data: baseData }));
  assert.throws(() => parseSpcodeGitShow({ status: "error", data: baseData }));
  assert.throws(() => parseSpcodeGitShow(null));
  assert.throws(() => parseSpcodeGitShow("nope"));
});

test("parseSpcodeGitShow: empty file list (merge commit / no-op commit)", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      files: [],
      count: 0,
    },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.files.length, 0);
  assert.equal(r.snapshot.count, 0);
});

test("parseSpcodeGitShow: body null is preserved", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      body: null,
    },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.commit.body, null);
});

test("parseSpcodeGitShow: root commit (no parents)", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      parents: [],
    },
  });
  assert.equal(r.kind, "ok");
  assert.deepEqual(r.snapshot.commit.parents, []);
});

test("parseSpcodeGitShow: merge commit (two parents)", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      parents: [
        "82cbc23f8d4bfc917465d4c3f772a7eae85d31d2",
        "f4e3d2c1b0a9876543210fedcba9876543210abc",
      ],
    },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.commit.parents.length, 2);
});

test("parseSpcodeGitShow: malformed status defaults to 'unknown'", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      files: [
        { path: "weird.bin", status: "Z", additions: 0, deletions: 0 },
      ],
      count: 1,
    },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.files[0].status, "unknown");
});

test("parseSpcodeGitShow: missing required field falls back to defaults", () => {
  // Defensive: backend occasionally omits optional fields. The
  // parser should not throw, just substitute defaults.
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      success: true,
      reason: null,
      loaded: true,
      umo: "u",
      worktree: "w",
      directory: "d",
      ref: "HEAD",
      resolved_sha: "abc",
      parents: [],
      author: { name: "", email: "" },
      date: "",
      subject: "s",
      body: null,
      files: [],
      count: 0,
      truncated: false,
      max_files: 500,
    },
  });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.elapsedMs, 0);
  assert.equal(r.snapshot.stderr, "");
  assert.equal(r.snapshot.commit.author.name, "");
  assert.deepEqual(r.snapshot.commit.parents, []);
  assert.equal(r.snapshot.maxFiles, 500);
});

// ── v3.9 (2026-06-25): optional ``data.file`` single-file patch view ──
// Backend only writes ``data.file`` when ?path= is supplied; in the
// default commit list view the field is absent. The parser must
// normalise "absent" to ``null`` and surface the parsed view otherwise.
test("parseSpcodeGitShow v3.9: file field is null when absent", () => {
  const r = parseSpcodeGitShow({ status: "ok", data: { ...baseData } });
  assert.equal(r.kind, "ok");
  assert.equal(r.snapshot.file, null);
});

test("parseSpcodeGitShow v3.9: file field parses modified (M) text patch", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      file: {
        path: "src/auth.py",
        old_path: null,
        status: "M",
        additions: 3,
        deletions: 1,
        is_binary: false,
        patch: "diff --git a/src/auth.py b/src/auth.py\n@@ -1,3 +1,4 @@\n+x\n",
      },
    },
  });
  assert.equal(r.kind, "ok");
  const f = r.snapshot.file;
  assert.ok(f, "file view should be present");
  assert.equal(f.path, "src/auth.py");
  assert.equal(f.status, "M");
  assert.equal(f.additions, 3);
  assert.equal(f.deletions, 1);
  assert.equal(f.isBinary, false);
  assert.equal(f.oldPath, null);
  assert.match(f.patch, /^diff --git/);
});

test("parseSpcodeGitShow v3.9: file field parses binary (patch=null)", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      file: {
        path: "assets/logo.png",
        old_path: null,
        status: "A",
        additions: 0,
        deletions: 0,
        is_binary: true,
        patch: null,
      },
    },
  });
  assert.equal(r.kind, "ok");
  const f = r.snapshot.file;
  assert.ok(f);
  assert.equal(f.isBinary, true);
  assert.equal(f.patch, null);
});

test("parseSpcodeGitShow v3.9: rename file view surfaces oldPath", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      file: {
        path: "src/new_name.py",
        old_path: "src/old_name.py",
        status: "R",
        additions: 1,
        deletions: 1,
        is_binary: false,
        patch: "diff --git a/src/old_name.py b/src/new_name.py\n",
      },
    },
  });
  assert.equal(r.kind, "ok");
  const f = r.snapshot.file;
  assert.ok(f);
  assert.equal(f.status, "R");
  assert.equal(f.oldPath, "src/old_name.py");
});

test("parseSpcodeGitShow v3.9: unknown status (path not in commit)", () => {
  const r = parseSpcodeGitShow({
    status: "ok",
    data: {
      ...baseData,
      file: {
        path: "nope.txt",
        old_path: null,
        status: "unknown",
        additions: 0,
        deletions: 0,
        is_binary: false,
        patch: null,
      },
    },
  });
  assert.equal(r.kind, "ok");
  const f = r.snapshot.file;
  assert.ok(f);
  assert.equal(f.status, "unknown");
  assert.equal(f.patch, null);
});
