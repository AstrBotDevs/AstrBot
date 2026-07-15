// Author: 2026-07-15 restore-refresh-status
//
// Regression test: every successful restore branch in GitDiffSidebar
// must refresh BOTH git-diff and git-status. Without the git-status
// refresh, restoring an untracked file leaves the newFilePaths set
// stale (it comes from git-status's `new` scope) and the row lingers
// in the UI for one polling tick (10s) after the file is unlinked.
//
// We don't mount the component — we grep the source for the expected
// pair of calls inside the two relevant functions. Cheap, drift-free,
// and fails fast if someone copy-pastes a restore handler that only
// calls `composable.refresh()`.

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

/** Slice the source from `start` (inclusive) to the matching closing
 *  brace of the first top-level `{` after `start`. We only use this on
 *  functions whose body is delimited by a single block — good enough
 *  for the two restore handlers in GitDiffSidebar. */
function bodyOf(name) {
  // Match `function <name>(` optionally preceded by `async `.
  const startRe = new RegExp(
    `(async\\s+)?function\\s+${name}\\s*\\(`,
    "g",
  );
  const m = startRe.exec(src);
  assert.ok(m, `could not find function ${name} in GitDiffSidebar.vue`);
  const open = src.indexOf("{", m.index);
  assert.ok(open !== -1, `could not find opening brace for ${name}`);
  // Walk to matching close — naive brace counter, fine for our
  // no-nested-function-in-function code style.
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

for (const name of ["onConfirmRestore", "onConfirmRestorePaths"]) {
  test(`${name} refreshes git-status on success`, () => {
    // Each success branch must go through the refreshDiffAndStatus
    // helper (not a bare composable.refresh()) so git-status is
    // re-fetched in parallel — otherwise the newFilePaths set /
    // stagedCount counter lag by up to 10s (one polling tick).
    const body = bodyOf(name);
    assert.ok(
      body.includes("refreshDiffAndStatus()"),
      `${name} must call refreshDiffAndStatus() helper on success. ` +
        `A bare composable.refresh() leaves git-status stale.`,
    );
  });
}

test("refreshDiffAndStatus helper touches BOTH diff and status", () => {
  // Helper-level contract: it must re-fetch both endpoints. The two
  // restore handlers above only assert that they call the helper;
  // this test guards the helper itself.
  const helperBody = bodyOf("refreshDiffAndStatus");
  assert.ok(
    helperBody.includes("composable.refresh()"),
    "refreshDiffAndStatus must call composable.refresh() (diff endpoint)",
  );
  assert.ok(
    helperBody.includes("gitStatus.refresh()"),
    "refreshDiffAndStatus must call gitStatus.refresh() (status endpoint)",
  );
  assert.ok(
    /Promise\.all\s*\(\s*\[\s*composable\.refresh\(\)\s*,\s*gitStatus\.refresh\(\)\s*\]\s*\)/.test(
      helperBody,
    ),
    "refreshDiffAndStatus must run both refreshes in parallel via Promise.all",
  );
});

test("useSpcodeGitDiff is decoupled from git-status fetch", () => {
  // Sanity check: useSpcodeGitDiff must NOT trigger git-status fetch
  // internally. If it ever does, we'd double-refresh on every restore
  // (and the helper above would mask the bug).
  const path = resolve(
    __dirname,
    "../src/composables/useSpcodeGitDiff.ts",
  );
  const diff = readFileSync(path, "utf-8");
  assert.ok(
    !/gitStatus|git-status|\/spcode\/git-status/.test(diff),
    "useSpcodeGitDiff must remain decoupled from git-status fetch",
  );
});
