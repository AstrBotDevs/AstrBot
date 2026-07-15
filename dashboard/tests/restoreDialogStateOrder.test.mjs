// Author: 2026-07-15 restore-dialog-flicker
//
// Regression test for the "old dialog stacking on top of new dialog"
// flicker. The original implementation used a manually-set ref
// (`confirmTargetIsNew`) inside `onFileRestore`, which could open the
// dialog with the *previous* file's isNew flag for one frame. The
// fix:
//   1. Makes `confirmTargetIsNew` a `computed` derived from
//      `confirmTargetPath` — a single source of truth.
//   2. Pins a `:key="confirmTargetPath"` on <v-card> so the v-card
//      re-mounts on every path change, eliminating in-place text
//      swap and the resulting layout shift.
//
// These assertions lock both invariants in source.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SIDEBAR = resolve(
  __dirname,
  "../src/components/chat/GitDiffSidebar.vue",
);
const src = readFileSync(SIDEBAR, "utf-8");

function bodyOf(name) {
  const startRe = new RegExp(`(async\\s+)?function\\s+${name}\\s*\\(`, "g");
  const m = startRe.exec(src);
  assert.ok(m, `could not find function ${name} in GitDiffSidebar.vue`);
  const open = src.indexOf("{", m.index);
  let depth = 0;
  for (let i = open; i < src.length; i++) {
    const ch = src[i];
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return src.slice(open, i + 1);
    }
  }
  throw new Error(`unterminated function body for ${name}`);
}

test("onFileRestore sets the path BEFORE opening the dialog", () => {
  // Critical: opening the dialog before setting the path lets Vue
  // render one frame with the previous file's content. Reverse the
  // order and you reintroduce the "stacking" flicker.
  const body = bodyOf("onFileRestore");
  const idxPath = body.indexOf("confirmTargetPath.value = path");
  const idxOpen = body.indexOf("confirmDialogOpen.value = true");
  assert.ok(idxPath !== -1, "onFileRestore must set confirmTargetPath");
  assert.ok(idxOpen !== -1, "onFileRestore must open the dialog");
  assert.ok(
    idxPath < idxOpen,
    "confirmTargetPath must be set BEFORE confirmDialogOpen=true, " +
      "otherwise the dialog opens with the previous file's content for one frame",
  );
});

test("onFileRestore does not manually set confirmTargetIsNew", () => {
  // The isNew flag must be derived from the path, not hand-set.
  // A manual `confirmTargetIsNew.value = ...` is exactly the bug.
  const body = bodyOf("onFileRestore");
  assert.ok(
    !/confirmTargetIsNew\.value\s*=/.test(body),
    "onFileRestore must not assign to confirmTargetIsNew — it is a " +
      "computed derived from confirmTargetPath. Reintroducing a " +
      "manual set would re-open the stacking flicker.",
  );
});

test("onCancelRestore and onConfirmRestore do not manually reset isNew", () => {
  // Same reasoning: the computed flips to false automatically when
  // confirmTargetPath is nulled.
  for (const name of ["onCancelRestore", "onConfirmRestore"]) {
    const body = bodyOf(name);
    assert.ok(
      !/confirmTargetIsNew\.value\s*=/.test(body),
      `${name} must not assign to confirmTargetIsNew (computed — " +
        "nulling the path flips it automatically)`,
    );
  }
});

test("confirmTargetIsNew is declared as computed, not ref", () => {
  // Source-level check. Find the declaration line.
  const declRe = /const\s+confirmTargetIsNew\s*=\s*([^;]+);/;
  const m = src.match(declRe);
  assert.ok(m, "could not find confirmTargetIsNew declaration");
  const rhs = m[1].trim();
  assert.ok(
    rhs.startsWith("computed"),
    `confirmTargetIsNew must be declared as a computed, got: ${rhs}`,
  );
  assert.ok(
    !rhs.startsWith("ref"),
    "confirmTargetIsNew must NOT be a ref (re-introduces the race)",
  );
  // And the computed must read from confirmTargetPath so it tracks
  // the same source as the dialog content.
  assert.ok(
    rhs.includes("confirmTargetPath"),
    "confirmTargetIsNew must read from confirmTargetPath",
  );
  assert.ok(
    rhs.includes("newFilePaths"),
    "confirmTargetIsNew must read from newFilePaths",
  );
});

test("v-card inside the single-file dialog has :key bound to confirmTargetPath", () => {
  // Pin the v-card :key. Without it, v-card-text content is swapped
  // in place and triggers a one-frame layout shift on path change.
  const dialogBlock = src.match(
    /<v-dialog\s+v-model="confirmDialogOpen"[\s\S]*?<\/v-dialog>/,
  );
  assert.ok(dialogBlock, "single-file v-dialog block not found");
  const block = dialogBlock[0];
  assert.ok(
    /<v-card\s[^>]*:key="confirmTargetPath/.test(block) ||
      /<v-card\s[^>]*:key=\{\{?confirmTargetPath/.test(block) ||
      /<v-card\s[^>]*:key=['"`]confirmTargetPath/.test(block) ||
      /:key="confirmTargetPath\s*\?\?\s*'empty'"/.test(block),
    "v-card must have :key bound to confirmTargetPath so it re-mounts " +
      "on path change (prevents in-place text swap flicker)",
  );
});

test("v-card inside the single-file dialog has v-if bound to confirmDialogOpen", () => {
  // Pin the v-if guard. Without it, v-card lives across the dialog
  // close transition, allowing v-card-text to re-render the wrong
  // wording in place — the "old message flash" on close.
  const dialogBlock = src.match(
    /<v-dialog\s+v-model="confirmDialogOpen"[\s\S]*?<\/v-dialog>/,
  );
  assert.ok(dialogBlock, "single-file v-dialog block not found");
  const block = dialogBlock[0];
  // v-card is multiline in current source — match either single-line
  // or multi-line attribute layout.
  assert.ok(
    /<v-card\s[^>]*v-if="confirmDialogOpen"/.test(block) ||
      /<v-card[\s\S]*?v-if="confirmDialogOpen"[\s\S]*?>/.test(block),
    "v-card must have v-if bound to confirmDialogOpen so it unmounts " +
      "synchronously when the dialog starts to close (prevents the " +
      "old-wording flash on close transition)",
  );
});

test("onCancelRestore closes dialog BEFORE clearing confirmTargetPath", () => {
  // Order matters on close: if we null the path first, the computed
  // isNew flips to false and the still-mounted v-card (during the
  // close transition) re-renders with the OLD wording for a few
  // frames. Closing the dialog first lets v-if unmount the v-card
  // synchronously.
  const body = bodyOf("onCancelRestore");
  const idxClose = body.indexOf("confirmDialogOpen.value = false");
  const idxPath = body.indexOf("confirmTargetPath.value = null");
  assert.ok(idxClose !== -1, "onCancelRestore must close the dialog");
  assert.ok(
    idxPath !== -1,
    "onCancelRestore must clear confirmTargetPath (deferred to nextTick is fine)",
  );
  assert.ok(
    idxClose < idxPath,
    "onCancelRestore must set confirmDialogOpen=false BEFORE " +
      "confirmTargetPath=null, otherwise v-card-text flashes the " +
      "old message during the close transition",
  );
});

test("onConfirmRestore closes dialog BEFORE clearing confirmTargetPath", () => {
  // Same reasoning as onCancelRestore.
  const body = bodyOf("onConfirmRestore");
  // Find the FIRST occurrence of "confirmDialogOpen.value = false" —
  // the close step (later in the function we may have awaits, but the
  // first close is the one that matters for state order).
  const idxClose = body.indexOf("confirmDialogOpen.value = false");
  const idxPath = body.indexOf("confirmTargetPath.value = null");
  assert.ok(idxClose !== -1, "onConfirmRestore must close the dialog");
  assert.ok(
    idxPath !== -1,
    "onConfirmRestore must clear confirmTargetPath (deferred is fine)",
  );
  assert.ok(
    idxClose < idxPath,
    "onConfirmRestore must set confirmDialogOpen=false BEFORE " +
      "confirmTargetPath=null, otherwise the user sees the OLD " +
      "message text for a few frames during the close transition",
  );
});
