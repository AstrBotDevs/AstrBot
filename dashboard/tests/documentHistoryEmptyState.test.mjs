// Author: 2026-07-15 document-history-empty
//
// Regression test for the document-manager's right-side history panel
// empty state. Two bugs that the test pins down:
//
//  1. When no file is selected, the history panel showed the *tree*
//     empty-state key ("该目录下没有 .md 文件") — misleading because
//     the user is not looking at a directory listing, they simply
//     haven't picked a file. The panel should use a dedicated
//     `documentManager.history.noSelection` key, translated as
//     "未选中文件" / "No file selected" / "Файл не выбран".
//
//  2. The history panel defaulted to expanded even when no file was
//     selected, so the misleading wording was actually visible. The
//     `isHistoryCollapsed` ref must default to `true` whenever the
//     initial `selectedDoc` is null (i.e. on first visit). Once the
//     user manually toggles it, that decision wins (no forced sync).

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "../src");

const HISTORY_PANEL = resolve(
  ROOT,
  "components/chat/message_list_comps/DocumentHistoryPanel.vue",
);
const DOC_MGR = resolve(
  ROOT,
  "components/chat/message_list_comps/DocumentManager.vue",
);

const LOCALES = [
  { id: "zh-CN", file: resolve(ROOT, "i18n/locales/zh-CN/features/chat.json") },
  { id: "en-US", file: resolve(ROOT, "i18n/locales/en-US/features/chat.json") },
  { id: "ru-RU", file: resolve(ROOT, "i18n/locales/ru-RU/features/chat.json") },
];

for (const { id, file } of LOCALES) {
  test(`chat.json [${id}] exposes documentManager.history.noSelection`, () => {
    const json = JSON.parse(readFileSync(file, "utf-8"));
    const v = json?.spcodeProjectLoad?.documentManager?.history?.noSelection;
    assert.ok(
      typeof v === "string" && v.length > 0,
      `documentManager.history.noSelection must exist in ${id} chat.json ` +
        `(replaces the misused tree.empty key on the right panel)`,
    );
  });
}

test("DocumentHistoryPanel uses history.noSelection (not tree.empty) when no file", () => {
  const src = readFileSync(HISTORY_PANEL, "utf-8");
  // The empty branch (v-if="!fileRelative") must reference the
  // history.noSelection key. tree.empty must NOT be used here —
  // that's the LEFT-pane tree's empty wording.
  const emptyBranch = src.match(/v-if="!fileRelative"[\s\S]*?<\/div>/);
  assert.ok(emptyBranch, "expected an !fileRelative branch in DocumentHistoryPanel");
  assert.ok(
    /documentManager\.history\.noSelection/.test(emptyBranch[0]),
    "DocumentHistoryPanel's !fileRelative branch must use " +
      "documentManager.history.noSelection, not tree.empty",
  );
  assert.ok(
    !/documentManager\.tree\.empty/.test(emptyBranch[0]),
    "DocumentHistoryPanel's !fileRelative branch must NOT use " +
      "documentManager.tree.empty (that's the left pane's wording)",
  );
});

test("DocumentManager: isHistoryCollapsed default follows selectedDoc", () => {
  // The history pane should start collapsed when no file is selected
  // (so the misleading "no .md files" text never appears), and
  // expanded when a file is already selected on mount. Source-level
  // check: the ref initializer must depend on `selectedDoc.value`.
  const src = readFileSync(DOC_MGR, "utf-8");
  const m = src.match(/const\s+isHistoryCollapsed\s*=\s*ref<boolean>\s*\(\s*([^)]+)\)/);
  assert.ok(m, "could not find isHistoryCollapsed ref initializer");
  const arg = m[1].trim();
  assert.ok(
    /!selectedDoc/.test(arg),
    `isHistoryCollapsed must default to !selectedDoc.value so the pane ` +
      `starts collapsed on first visit (no selectedDoc). Got: ${arg}`,
  );
});

test("DocumentManager: pane-left uses v-show keyed only on collapse state", () => {
  // 2026-07-15 fullscreen-layout-parity: fullscreen shares the same
  // layout as the normal mode. pane-left is mounted in BOTH modes and
  // gated ONLY by `!isLeftPaneCollapsed`. Adding any isFullscreen branch
  // reintroduces the fullscreen-only layout divergence (and the
  // floating collapse button regression).
  const src = readFileSync(DOC_MGR, "utf-8");
  const idx = src.indexOf('class="document-manager__pane-left"');
  assert.ok(idx !== -1, "pane-left div not found in DocumentManager");
  const head = src.slice(Math.max(0, idx - 200), idx);
  assert.ok(
    /v-show\s*=\s*"!isLeftPaneCollapsed"\s*(?:$|\s+class)/.test(head),
    'pane-left must use v-show="!isLeftPaneCollapsed" — fullscreen ' +
      "shares the normal layout, so the gate should NOT branch on " +
      "isFullscreen",
  );
  assert.ok(
    !/!isFullscreen/.test(head),
    "pane-left must NOT include isFullscreen — fullscreen reuses " +
      "the normal layout so any isFullscreen branch recreates the " +
      "layout divergence bug",
  );
});

// 2026-07-15 fullscreen-layout-parity: fullscreen mode must use the
// same layout as the normal (in-sidebar) mode — just scaled to the
// viewport. The previous design overlaid a left-rail trigger button +
// drawer overlay in fullscreen, which (a) introduced the floating
// collapse button regression, (b) used a layout different from the
// normal mode. We removed the drawer entirely so fullscreen is just
// the same pane tree, with the manager teleported to <body> and
// position:fixed inset:0.

test("DocumentManager: pane-left is always mounted (no !isFullscreen gate)", () => {
  const src = readFileSync(DOC_MGR, "utf-8");
  const idx = src.indexOf('class="document-manager__pane-left"');
  assert.ok(idx !== -1, "pane-left div not found");
  const head = src.slice(Math.max(0, idx - 200), idx);
  // No condition should exclude fullscreen — the gate is purely
  // the user's collapse choice.
  assert.ok(
    /v-(?:if|show)\s*=\s*"!isLeftPaneCollapsed"\s*(?:$|\s+class)/.test(head),
    "pane-left must be visible in fullscreen too — fullscreen " +
      "reuses the normal layout. Gate should be only on collapse " +
      "state (e.g. v-show=\"!isLeftPaneCollapsed\").",
  );
  assert.ok(
    !/!isFullscreen/.test(head),
    "pane-left must NOT branch on isFullscreen anymore — the drawer " +
      "scheme is removed and fullscreen now mirrors normal layout",
  );
});

test("DocumentManager: drawer / left-rail / drawer-backdrop fully removed", () => {
  const src = readFileSync(DOC_MGR, "utf-8");
  const banned = [
    "leftDrawerOpen",
    "openLeftDrawer",
    "closeLeftDrawer",
    "document-manager__left-rail",
    "document-manager__left-drawer",
    "document-manager__drawer-backdrop",
  ];
  for (const id of banned) {
    assert.ok(
      !src.includes(id),
      `${id} must be removed from DocumentManager — fullscreen reuses ` +
        `the normal layout, so the offscreen drawer / trigger rail ` +
        `are obsolete`,
    );
  }
});

for (const { id, file } of LOCALES) {
  test(`chat.json [${id}] drops documentManager.fullscreen.openDrawer`, () => {
    // The key was only used by the removed left-rail button.
    // Keeping it would invite re-introducing the drawer.
    const json = JSON.parse(readFileSync(file, "utf-8"));
    const v = json?.spcodeProjectLoad?.documentManager?.fullscreen?.openDrawer;
    assert.ok(
      v === undefined,
      `${id} chat.json must remove documentManager.fullscreen.openDrawer ` +
        `(it was only used by the now-removed left-rail trigger)`,
    );
  });
}

// 2026-07-15 history-action-rename: clicking the action button on a
// history row, or activating the "diff" tab while a revision is
// selected, runs `gitShow.fetchFile(rev, doc)` which is
// `git show <rev>:<file>` — the patch THIS commit introduces
// (commit-to-parent), NOT a diff against the working tree.
// The old wording "与当前对比 / Diff vs current" suggested a
// working-tree diff and misled users. Both the tab label and the
// history-row hover title must describe the actual behaviour: the
// selected commit's own changes.

const FORBIDDEN_OLD = {
  "zh-CN": "与当前对比",
  "en-US": "Diff vs current",
  "ru-RU": "Сравнить с текущ",
};
const COMMIT_KEYWORD = {
  "zh-CN": /本次/,
  "en-US": /this commit/i,
  "ru-RU": /коммит/i,
};

for (const { id, file } of LOCALES) {
  test(`chat.json [${id}] viewMode.diff describes the commit's own changes`, () => {
    const json = JSON.parse(readFileSync(file, "utf-8"));
    const label = json?.spcodeProjectLoad?.documentManager?.viewMode?.diff;
    assert.ok(
      typeof label === "string" && label.length > 0,
      `${id} viewMode.diff must be a non-empty string`,
    );
    assert.ok(
      !label.includes(FORBIDDEN_OLD[id]),
      `${id} viewMode.diff must not say "${FORBIDDEN_OLD[id]}" — ` +
        "the diff is commit-to-parent, not vs the working tree",
    );
    assert.ok(
      COMMIT_KEYWORD[id].test(label),
      `${id} viewMode.diff should mention the commit itself (e.g. "本次" / "this commit" / "коммит")`,
    );
  });

  test(`chat.json [${id}] history.compareWithCurrent describes the commit's own changes`, () => {
    const json = JSON.parse(readFileSync(file, "utf-8"));
    const label =
      json?.spcodeProjectLoad?.documentManager?.history?.compareWithCurrent;
    assert.ok(
      typeof label === "string" && label.length > 0,
      `${id} history.compareWithCurrent must be a non-empty string`,
    );
    assert.ok(
      !label.includes(FORBIDDEN_OLD[id]),
      `${id} history.compareWithCurrent must not say "${FORBIDDEN_OLD[id]}" — ` +
        "the action shows the commit-to-parent patch, not a working-tree diff",
    );
    assert.ok(
      COMMIT_KEYWORD[id].test(label),
      `${id} history.compareWithCurrent should mention the commit itself`,
    );
  });
}
