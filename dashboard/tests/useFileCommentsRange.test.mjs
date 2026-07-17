// Author: elecvoid243, 2026-07-17
// Spec: docs/superpowers/specs/2026-07-17-selection-comment-design.md §5-6
//
// Unit tests for the pure helpers extracted from useFileComments
// for selection-comment support. The composable's LLM-format
// renderer (renderWindow) is intrinsically entangled with the
// per-file grouping logic and is smoke-tested manually per the
// repo's composable-testing norm (see
// tests/useSpcodeDocs.test.mjs note).

import assert from "node:assert/strict";
import test from "node:test";

const mod = await import(
  "../src/composables/useFileComments.ts"
);

test("commentCoversLine: single line covers only that line", () => {
  // Single-line comment is identified by `line` alone (endLine
  // absent). Coverage must be [line, line] inclusive.
  const c = { line: 5 };
  assert.equal(mod.commentCoversLine(c, 4), false);
  assert.equal(mod.commentCoversLine(c, 5), true);
  assert.equal(mod.commentCoversLine(c, 6), false);
});

test("commentCoversLine: range covers inclusive span", () => {
  // Range comment covers [line, endLine] inclusive on both ends.
  const c = { line: 5, endLine: 8 };
  assert.equal(mod.commentCoversLine(c, 4), false);
  assert.equal(mod.commentCoversLine(c, 5), true);
  assert.equal(mod.commentCoversLine(c, 7), true);
  assert.equal(mod.commentCoversLine(c, 8), true);
  assert.equal(mod.commentCoversLine(c, 9), false);
});

test("extractRangeLineContext: mid-file — lineContent from selection's first line, context from file", () => {
  // The selection's first line is the fingerprint; surrounding
  // context comes from the live file content (one line before
  // startLine, one line after endLine).
  const content = "L1\nL2\nL3\nL4\nL5\nL6\nL7\n";
  const got = mod.extractRangeLineContext(
    content,
    /*startLine*/ 3,
    /*endLine*/ 5,
    /*selection*/ "L3 picked\nL4 picked\nL5 picked",
  );
  assert.equal(got.lineContent, "L3 picked");
  assert.equal(got.contextBefore, "L2");
  assert.equal(got.contextAfter, "L6");
});

test("extractRangeLineContext: file boundaries yield null context", () => {
  // When startLine is line 1 there is no "before"; when endLine
  // is the last line there is no "after". Both must be null (NOT
  // "" or undefined) so the editor can distinguish "boundary"
  // from "empty content".
  const got = mod.extractRangeLineContext(
    "L1\nL2\nL3\n",
    /*startLine*/ 1,
    /*endLine*/ 2,
    /*selection*/ "L1\nL2",
  );
  assert.equal(got.contextBefore, null);
  assert.equal(got.contextAfter, "L3");
});
