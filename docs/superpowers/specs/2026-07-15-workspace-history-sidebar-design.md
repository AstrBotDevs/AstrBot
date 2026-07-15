# Workspace History Sidebar Design

**Date:** 2026-07-15
**Status:** Approved (pending implementation)

## Goal

Make the workspace page's "查看文件历史" affordance behave the same way as the file-manager page's history sidebar: a per-file commit list where each commit offers "view this revision" and "compare with current", with a banner showing the active SHA and a "back to current" control.

The workspace page currently routes the button to a standalone Git History tab that only renders a commit list. The change upgrades that tab into a two-column workspace (commit list + revision preview) so the user can read a file's content at any historical commit and diff it against the working tree, in one click.

## Scope

The feature applies to:

- the workspace page (`GitDiffSidebar.vue`, `viewMode === "history"` only);
- text files selected from the file browser (`FileBrowserView` → `FileBrowserFilePreview`);
- binary files selected from the file browser: the "查看文件历史" button is **hidden** (text-only affordance), because revision preview cannot meaningfully render binary blobs without extending the preview pipeline beyond the current FileBrowserFilePreview scope.

The feature does not apply to:

- the document manager's history sidebar (already feature-complete; `DocumentManager.vue` and `DocumentHistoryPanel.vue` stay as the reference implementation);
- the Git Diff page (`viewMode === "diff"`), the Git Changes page itself, or the File Browser tab (`viewMode === "files"`).

The feature does not change file-browser data fetching, search, the existing Git History tab's filter form, the worktree tab, the path-filter persistence, or any other sidebar control outside the History tab.

## Behavior

When the user clicks the **查看文件历史** button on a selected text file:

- `viewMode` switches to `"history"`.
- The History tab's filter form is pre-filled with the file's path (current `setLogPathFilter` behavior, unchanged).
- `historyFilePath` is set to that path.
- `selectedRevision` is cleared; `historyPreviewMode` is reset to `"raw"`; `diffPatch` is cleared.
- The History tab now renders two columns side-by-side:
  - left: a per-file commit list with working-tree pseudo-row and per-commit actions (see below);
  - right: an empty preview that shows the banner placeholder ("no revision selected") until the user picks one.

When the user clicks the **eye** action on a commit:

- `selectedRevision` is set to that commit's SHA.
- `historyPreviewMode` is set to `"raw"`.
- The right column fetches the historical blob via `useSpcodeGitFile.fetchRef(path, sha)` and renders it with the existing text-preview pipeline (`FileBrowserCodeView` for code, `MarkdownView` for `.md`).
- The banner at the top of the right column reads "正在查看历史版本 {sha7}" with a "回到当前" button on the right.

When the user clicks the **compare** action on a commit:

- `selectedRevision` is set to that commit's SHA.
- `historyPreviewMode` is set to `"diff"`.
- The right column fetches the unified diff (`git diff <sha>..HEAD -- <path>`) and renders it with the existing unified-diff renderer (same component used by the Git Changes page for non-selected diffs).

When the user clicks **回到当前**:

- `selectedRevision` is cleared.
- `historyPreviewMode` is reset to `"raw"`; `diffPatch` is cleared.
- The right column reverts to the empty placeholder.

When the user toggles the History tab's path filter away from the currently selected file (e.g. clears the path field and clicks Apply):

- `historyFilePath` becomes empty (or matches a different file).
- `selectedRevision` is cleared; banner disappears.
- The commit list re-fetches against the new filter.

When the user switches off the History tab to any other view mode:

- `selectedRevision` is preserved across short switches but the right column is hidden because the History tab is not rendered. Re-entering the History tab restores the previously selected revision and mode (same session, no persistence).

When the user closes the sidebar (sets `modelValue` to `false`):

- All session state is cleared by the existing unmount lifecycle (`selectedRevision = null`, `diffPatch = null`, `historyPreviewMode = "raw"`).

## Component Layout

```
┌────────────────────────────────────────────────────────────────────┐
│ History tab filter form (path / ref / author / since / until / n) │
├────────────────────────────────────────────────────────────────────┤
│ [GitHistorySidebar]  │ resize │ [GitRevisionPreview]                │
│  - 文件路径徽标       │ divider│  - banner: "查看历史 {sha7}" + 回到 │
│  - working tree 伪行  │        │  - tabs: raw | diff                │
│  - commit 列表        │        │  - raw: text/code markdown preview  │
│  - 每行 eye/compare   │        │  - diff: unified diff              │
│  - 折叠按钮           │        │                                    │
└────────────────────────────────────────────────────────────────────┘
```

- Divider uses the existing `useResizableSplit` composable; initial 35% / 65%, min 25%, max 60%. Width is persisted per worktree in `localStorage` (same key scheme as the document manager's `historySplit`).
- When the sidebar is collapsed (`isHistoryCollapsed === true`), only a thin chevron handle appears on the right edge; clicking it re-expands to the persisted width.
- Banner is hidden when `selectedRevision === null`. The right column falls back to a centered placeholder text ("选择左侧 commit 查看历史版本").
- Binary files do not reach this state because the entry button is hidden for them on `FileBrowserFilePreview`.

## Recommended Architecture

Implement in three new files plus targeted edits in two existing files.

### New files

1. `dashboard/src/components/chat/message_list_comps/GitHistorySidebar.vue`
   - Mirror of `DocumentHistoryPanel.vue`: same per-file commit list, same working-tree pseudo-row, same per-commit eye/compare actions, same collapse button.
   - Props: `gitLog: UseSpcodeGitLog`, `fileRelative: string | null`, `currentRevision: string | null`, `isLoading: boolean`.
   - Emits: `select-revision(sha)`, `compare-current(sha)`, `collapse`.
   - Watches `fileRelative` and calls `gitLog.refresh({ ref: "HEAD", n: 50, path })` (identical to `DocumentHistoryPanel`).
   - i18n: reuses `spcodeProjectLoad.documentManager.history.*` keys (banner, viewThisRevision, compareWithCurrent, currentPlaceholder, noSelection, loadFail).
   - Styling: copy from `DocumentHistoryPanel.vue`; rename BEM root to `git-history-sidebar__*` so the two panels do not collide.

2. `dashboard/src/components/chat/message_list_comps/GitRevisionPreview.vue`
   - Props: `fileRelative: string | null`, `selectedRevision: string | null`, `previewMode: "raw" | "diff"`, `gitFile: UseSpcodeGitFile`, `diffPatch: string | null`, `diffLoading: boolean`.
   - Emits: `back-to-current`, `update:previewMode`.
   - Banner: visible only when `selectedRevision !== null`; shows truncated SHA and the back button.
   - Tabs: `raw` is disabled if `gitFile` reports `isBinary`; `diff` is always available when a revision is selected.
   - Raw content: read `gitFile.getData(path, sha)?.content`; route to `FileBrowserCodeView` for non-`.md` text and `MarkdownView` for `.md`.
   - Binary fallback: when `isBinary` is true in raw mode, render the same "binary file" placeholder that `FileBrowserFilePreview` already uses.
   - Diff content: render `diffPatch` via the existing unified-diff component used by the Git Changes page.
   - Loading / error states mirror `DocumentManager.vue`'s view region: progress indicator while fetching, red error text when the fetch fails.

3. `dashboard/src/composables/useSpcodeGitFileDiff.ts` (or an inline helper if simple)
   - One-shot fetcher: `fetchDiff(path: string, sha: string, base?: string = "HEAD"): Promise<string | null>`.
   - Calls the same backend endpoint that already powers `git-show` diff output, or a new `?path=&sha=&base=` query on the existing endpoint if the backend already supports `format=diff` (to be confirmed in implementation).
   - ETag-aware; reuses the existing ETag key shape from `useSpcodeGitFile`.

### Edits

1. `dashboard/src/components/chat/GitDiffSidebar.vue`
   - Add refs: `historySplit`, `historyFilePath`, `selectedRevision`, `historyPreviewMode`, `diffPatch`, `diffLoading`, `isHistoryCollapsed`.
   - Add a second `useSpcodeGitFile` instance scoped to the History tab (call it `historyGitFile`); share the existing `useSpcodeGitLog` instance via the new `<GitHistorySidebar>` props.
   - Replace the existing `<GitLogView v-else-if="viewMode === 'history'" ... />` block with a new container that renders `<GitHistorySidebar>` + divider + `<GitRevisionPreview>`.
   - Update `setLogPathFilter` to also reset `selectedRevision`, `historyPreviewMode`, `diffPatch`, `diffLoading`, and to set `historyFilePath`. The existing path-prefill on the filter form stays.
   - Watch `[historyFilePath, selectedRevision, historyPreviewMode]` to drive fetches (mirror `DocumentManager.vue`'s watch block at lines ~224–248).
   - On unmount, clear all session state.

2. `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`
   - Hide the "查看文件历史" button when the file is detected as binary.
   - Pass the file path to `setLogPathFilter` as today (no API change).
   - If the binary-detection logic is local, extract it to `dashboard/src/utils/detectBinary.ts` so both `FileBrowserFilePreview` and `GitRevisionPreview` can share it.

### Backend assumptions (verify during implementation)

- `GET /spcode/git-show?path=<file>&sha=<sha>` returns raw text content for any text file. Already used by `DocumentManager.vue` for markdown; same call works for code/text.
- `GET /spcode/git-show?path=<file>&sha=<sha>&base=<ref>` (or a sibling endpoint) returns the unified diff between `sha` and `base` for that path. If this does not exist yet, a one-endpoint backend addition is acceptable as part of this task — keep the parameter shape consistent with the existing toolkit conventions (see `plugins/astrbot_plugin_spcode_toolkit/tools/webapi/git_log.py` for the pattern).
- `useSpcodeGitFile.fetchRef` already handles 304 + caching + ETag. The new diff fetcher follows the same shape.

## State Summary

| State | Owner | Persisted? | Reset on |
|---|---|---|---|
| `historySplit.percent` | `GitDiffSidebar` | localStorage | worktree change |
| `historyFilePath` | `GitDiffSidebar` | no (driven by path-filter form) | tab switch |
| `selectedRevision` | `GitDiffSidebar` | no | file change / tab switch |
| `historyPreviewMode` | `GitDiffSidebar` | no | tab switch / file change |
| `diffPatch` | `GitDiffSidebar` | no | revision change / unmount |
| `isHistoryCollapsed` | `GitDiffSidebar` | no | never (resets on close) |

## Error Handling

- GitLog load failure: existing `<GitHistorySidebar>` error branch shows "无法读取历史版本: {reason}" (reuses DocumentManager copy).
- GitFile (raw blob) load failure: `<GitRevisionPreview>` shows a red error line in the preview region with the reason; the banner stays so the user knows which revision failed.
- Diff load failure: same toast pattern as DocumentManager's diff error; preview region shows the reason inline.
- Empty state (no commits for the file): working-tree pseudo-row is the only row; preview shows the empty placeholder.

## i18n

Reuse the existing `spcodeProjectLoad.documentManager.history.*` keys for `viewThisRevision`, `compareWithCurrent`, `currentPlaceholder`, `loadFail`, `noSelection`, `title`, `collapseHistory`, `expandHistory`. Add new keys under `spcodeProjectLoad.gitHistory.*` only for strings that do not exist in the document manager namespace:

- `banner.viewing` — "正在查看历史版本 {sha}"
- `banner.backToCurrent` — "回到当前"
- `preview.tab.raw` — "原文"
- `preview.tab.diff` — "本次改动"
- `preview.placeholder.empty` — "选择左侧 commit 查看历史版本"
- `preview.binaryUnsupported` — "二进制文件不支持历史版本预览"
- `preview.diffLoadFail` — "无法加载 diff: {reason}"

Add matching entries in `dashboard/src/i18n/locales/en-US/features/chat.json` for the new keys.

## Out of Scope

- Drawing a two-column preview directly inside the file browser's Files tab (no layout change there).
- Editor / write-back of historical revisions (this is read-only by design, matching `DocumentManager`'s current model).
- Persisting `selectedRevision` across page reloads (defer until product asks).
- A new "compare with previous commit" affordance (the user already gets this via the unified-diff against HEAD; further granularity is YAGNI).
