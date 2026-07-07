// Author: elecvoid243
// Date: 2026-07-07
// Spec: docs/superpowers/specs/2026-07-07-hunk-discard-design.md §5.4
//
// Test runner: node --test (Node v24 strips TS from .ts imports automatically).
// Run: cd dashboard && pnpm exec node --test --import tsx src/utils/diffHunkPatch.test.ts
//
// Locks the `git apply --reverse` consumer contract for buildHunkPatchText():
// the reconstructed patch must end with a single trailing `\n`. The fix
// landed on 2026-07-07 to unbreak hunk discard in production (the previous
// `lines.join("\n")` left the last body line unterminated, which `git apply`
// rejects as "error: corrupt patch at line N" → backend reason
// `patch_malformed`, discard silently failed).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  buildHunkPatchText,
  extractDiffContent,
  parseUnifiedDiff,
} from "./diffHunkPatch.ts";

// Minimal fixture: 4-line hunk showing the exact regression case from
// production — a one-line modification reverted via hunk discard.
const SAMPLE_DIFF = [
  "diff --git a/astrbot/core/provider/__init__.py b/astrbot/core/provider/__init__.py",
  "--- a/astrbot/core/provider/__init__.py",
  "+++ b/astrbot/core/provider/__init__.py",
  "@@ -1,4 +1,4 @@",
  " from .entities import ProviderMetaData",
  " from .provider import Provider, STTProvider",
  " ",
  "-__all__ = [\"Provider\", \"ProviderMetaData\", \"STTProvider\"]",
  "+__all__ = [\"Provider\", \"ProviderMetaData\", \"STTProvider\"]# test mod",
].join("\n");

test("buildHunkPatchText output ends with a single trailing newline", () => {
  const out = buildHunkPatchText(SAMPLE_DIFF, "astrbot/core/provider/__init__.py", 0);
  assert.ok(out.endsWith("\n"), `missing trailing \\n: ...${JSON.stringify(out.slice(-20))}`);
  // Exactly ONE trailing newline — joining-then-append would otherwise
  // emit "\n\n" if any source line already ended with \n (it shouldn't,
  // but we lock the invariant tightly so a future refactor can't double
  // up).
  assert.equal(out.endsWith("\n\n"), false, "double trailing newline detected");
});

test("buildHunkPatchText output is structurally a git apply patch", () => {
  const out = buildHunkPatchText(SAMPLE_DIFF, "astrbot/core/provider/__init__.py", 0);
  const lines = out.split("\n");
  // Headers + hunk header + 5 body lines + final empty after trailing \n.
  // (Note: split("\n") on a string ending in \n yields a trailing "" entry.)
  assert.equal(lines[0], "diff --git a/astrbot/core/provider/__init__.py b/astrbot/core/provider/__init__.py");
  assert.equal(lines[1], "--- a/astrbot/core/provider/__init__.py");
  assert.equal(lines[2], "+++ b/astrbot/core/provider/__init__.py");
  assert.equal(lines[3], "@@ -1,4 +1,4 @@");
  // Body lines must use ASCII '-' / '+' / ' ' prefixes (NOT U+2212 visual
  // minus from the display parser) — git apply rejects the unicode form.
  assert.match(lines[4], /^ from \.entities/);
  assert.match(lines[5], /^ from \.provider/);
  assert.equal(lines[6], " ", "empty context line must be a single space char + newline");
  assert.equal(lines[7], "-__all__ = [\"Provider\", \"ProviderMetaData\", \"STTProvider\"]");
  assert.equal(lines[8], "+__all__ = [\"Provider\", \"ProviderMetaData\", \"STTProvider\"]# test mod");
});

test("buildHunkPatchText returns empty for empty filePath", () => {
  assert.equal(buildHunkPatchText(SAMPLE_DIFF, "", 0), "");
});

test("buildHunkPatchText returns empty when hunkIndex is out of range", () => {
  assert.equal(buildHunkPatchText(SAMPLE_DIFF, "foo.py", 99), "");
});

test("buildHunkPatchText returns empty for empty diffContent", () => {
  // Defensive: an empty content should produce no patch, not a half-built
  // header-only string (which would also fail the trailing-\n invariant).
  assert.equal(buildHunkPatchText("", "foo.py", 0), "");
});

test("reconstructed patch survives git apply --check --reverse (end-to-end)", () => {
  // Skipped silently if git isn't on PATH (CI boxes without git would
  // otherwise break unrelated runs).
  const gitProbe = spawnSync("git", ["--version"], { encoding: "utf-8" });
  if (gitProbe.status !== 0) return;

  // Need a working tree that matches the file the patch reverses INTO,
  // i.e. the file currently has the "+__all__ = [...]# test mod" form,
  // and --reverse applies the patch to drop the modification.
  const dir = mkdtempSync(join(tmpdir(), "hunk-discard-test-"));
  try {
    spawnSync("git", ["init", "-q"], { cwd: dir, encoding: "utf-8" });
    spawnSync("git", ["config", "user.email", "test@test"], { cwd: dir, encoding: "utf-8" });
    spawnSync("git", ["config", "user.name", "Test"], { cwd: dir, encoding: "utf-8" });
    writeFileSync(
      join(dir, "foo.py"),
      'from .entities import ProviderMetaData\n'
      + 'from .provider import Provider, STTProvider\n'
      + '\n'
      + '__all__ = ["Provider", "ProviderMetaData", "STTProvider"]# test mod\n',
    );
    spawnSync("git", ["add", "foo.py"], { cwd: dir, encoding: "utf-8" });
    spawnSync("git", ["commit", "-q", "-m", "init"], { cwd: dir, encoding: "utf-8" });

    // The exact payload the frontend would build for this hunk.
    const diffFixture = [
      "diff --git a/foo.py b/foo.py",
      "--- a/foo.py",
      "+++ b/foo.py",
      "@@ -1,4 +1,4 @@",
      " from .entities import ProviderMetaData",
      " from .provider import Provider, STTProvider",
      " ",
      "-__all__ = [\"Provider\", \"ProviderMetaData\", \"STTProvider\"]",
      "+__all__ = [\"Provider\", \"ProviderMetaData\", \"STTProvider\"]# test mod",
    ].join("\n");
    const patch = buildHunkPatchText(diffFixture, "foo.py", 0);

    // --check (dry-run) + --reverse + feed patch via stdin (mirrors how
    // the backend pipes `patch_text` into `git apply`).
    const res = spawnSync(
      "git",
      ["apply", "--check", "--reverse", "--whitespace=error", "--no-unsafe-paths"],
      { cwd: dir, input: patch, encoding: "utf-8" },
    );
    assert.equal(
      res.status,
      0,
      `git apply --check --reverse rejected the patch: stderr=${JSON.stringify(res.stderr)}`,
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// ── Minimal sanity coverage for the two other exports ─────────────
// We don't re-test the SFC-wide behavior — these pin the contracts the
// SFC relies on so a parser refactor can't silently change hunk indices
// or content extraction.

test("parseUnifiedDiff assigns hunkIndex based on parse order", () => {
  const hunks = parseUnifiedDiff(SAMPLE_DIFF, Infinity);
  assert.equal(hunks.length, 1);
  assert.equal(hunks[0].hunkIndex, 0);
});

test("extractDiffContent unwraps ```diff fences", () => {
  const fenced = "Some preamble\n```diff\n@@ -1 +1 @@\n-x\n+y\n```\nSome trailer";
  const out = extractDiffContent(fenced);
  assert.ok(out.startsWith("@@"), `expected @@ start, got: ${out.slice(0, 30)!}`);
  assert.ok(out.includes("-x"), "expected -x inside extracted body");
});

test("extractDiffContent strips leading preamble when @@ is present", () => {
  const out = extractDiffContent("Edited file foo.py:\n@@ -1 +1 @@\n-x\n+y");
  assert.ok(out.startsWith("@@"));
});
