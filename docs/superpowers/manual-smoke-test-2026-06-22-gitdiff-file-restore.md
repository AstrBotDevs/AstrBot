# Manual Smoke Test — GitDiff file-restore button

> **Status: DEFERRED — no live backend available in CI / subagent context.**
> This file is the executable checklist a human must run against a live
> dashboard (`pnpm dev` + loaded spcode project) before merging.
> All 9 scenarios come from the plan's Task 11
> (`docs/superpowers/plans/2026-06-22-chatui-git-diff-file-restore.md`).
> Expected results match spec §9.3.

**Branch under test:** `feat/gitdiff-file-restore`
**Spec:** `docs/superpowers/specs/2026-06-22-chatui-git-diff-file-restore-design.md`
**Plan:** `docs/superpowers/plans/2026-06-22-chatui-git-diff-file-restore.md`

## Prerequisites

1. `pnpm dev` running against a backend that has the
   `astrbot_plugin_spcode_toolkit` v3.5+ plugin loaded.
2. A spcode project loaded into the dashboard (a worktree with at
   least one file modified relative to `index`).
3. Three browser locales available (`zh-CN`, `en-US`, `ru-RU`) — toggle
   via the dashboard's language switcher.
4. DevTools Network panel open (for scenario 8).

## Pre-flight: automated checks (run before manual scenarios)

```bash
cd dashboard
pnpm typecheck                                  # expect 0 errors
node --test tests/parseSpcodeFileRestore.test.mjs   # expect 8 pass
```

Both must be green before proceeding.

> `pnpm lint` is intentionally **not** run here — the project-wide lint
> config is broken with 288 parsing errors (pre-existing, unrelated to
> this change). See Chunk 4 concerns.

---

## Scenario 1 — Modified file appears in diff list

**Goal:** verify the existing `useSpcodeGitDiff` plumbing still surfaces
modified files after our changes (regression check).

**Steps:**
1. In the loaded worktree, modify any file (e.g. `echo "x" >> README.md`).
2. Wait for the polling refresh (~10s) or click the ↻ refresh button.
3. Open the GitDiff sidebar in the dashboard.

**Expected result:**
- The sidebar lists the modified file as one row.
- Hovering the row reveals a ↩ restore button at the right edge of the
  path.
- **Code exercised:**
  - `dashboard/src/composables/useSpcodeGitDiff.ts` (existing,
    unchanged in this PR)
  - `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue:86-100`
    (restore button render)

---

## Scenario 2 — Cancel confirmation leaves list intact

**Goal:** verify the cancel path of `<v-dialog>` reverts state without
firing any HTTP request or toast.

**Steps:**
1. From scenario 1, click the ↩ button on the modified file.
2. In the confirm dialog, click "取消" / "Cancel" / "Отмена".

**Expected result:**
- Dialog closes.
- File row is **still present** in the list.
- No snackbar / toast appears.
- No `POST .../file-restore` request in DevTools Network panel.
- **Code exercised:**
  - `dashboard/src/components/chat/GitDiffSidebar.vue:457-460`
    (`onCancelRestore`)
  - `dashboard/src/components/chat/GitDiffSidebar.vue:837`
    (cancel `<v-btn>` in dialog)

---

## Scenario 3 — Happy path: confirm → success → row disappears

**Goal:** verify the full success path including the post-success
`composable.refresh()` that drops the row.

**Steps:**
1. Click ↩ on the modified file.
2. In the confirm dialog, click "恢复" / "Restore" / "Восстановить".
3. Wait for the request to complete (typically <500ms for a small file).

**Expected result:**
- Confirm button shows a spinner while the request is in flight.
- A green success snackbar appears bottom-right: "已恢复 README.md" /
  "Restored README.md" / "Восстановлено: README.md".
- The file row **disappears** from the list within 1s.
- DevTools Network panel shows one `POST .../file-restore` request with
  `status: 200` and a JSON body containing `"restored": true`.
- **Code exercised:**
  - `dashboard/src/components/chat/GitDiffSidebar.vue:462-490`
    (`onConfirmRestore` — success branch)
  - `dashboard/src/components/chat/GitDiffSidebar.vue:824-848`
    (dialog, confirm button with `:loading="restoringFile !== null"`)
  - `dashboard/src/composables/useSpcodeFileRestore.ts:38-79`
    (request + `parseSpcodeFileRestore`)

---

## Scenario 4 — Untracked file → warning toast with reason

**Goal:** verify the failure-toast path with a specific `reason` from
`RESTORE_REASON_CODES`.

**Steps:**
1. Create a new untracked file: `touch new.py` (no `git add`).
2. Wait for the sidebar to refresh.
3. Click ↩ on `new.py`.
4. Confirm the dialog.

**Expected result:**
- Spinner shows briefly, then a warning / error snackbar appears with
  the localized "未跟踪的文件无法恢复（请用 git rm --cached 或 git add）"
  / "Cannot restore an untracked file (use git rm --cached or git add)"
  / "Невозможно восстановить неотслеживаемый файл..." message.
- The `new.py` row **stays** in the list (restore was rejected).
- DevTools Network panel shows the request returning `"restored": false`
  with `"reason": "untracked_file"`.
- **Code exercised:**
  - `dashboard/src/components/chat/GitDiffSidebar.vue:485-490`
    (failure branch + i18n mapping via `RESTORE_REASON_I18N_KEYS`)
  - `dashboard/src/composables/useSpcodeFileRestore.ts:70-74`
    (failure return shape `{ ok: false, reason, stderr }`)
  - `dashboard/src/i18n/locales/*/features/chat.json` —
    `spcodeProjectLoad.diffSidebar.restore.error.reason.untracked_file`

---

## Scenario 5 — Keyboard activation via Enter

**Goal:** verify the focusable restore button is reachable and activatable
via keyboard per spec §6.2 (a11y requirement).

**Steps:**
1. Tab to the file row; Tab again to the ↩ button (visible focus ring).
2. Press `Enter`.

**Expected result:**
- The confirm dialog opens identically to a mouse click.
- **Code exercised:**
  - `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue:70-72`
    (outer row `<div role="button" tabindex="0">` keyboard handling)
  - `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue:86-92`
    (restore `<button>` — native keyboard activation)

---

## Scenario 6 — Worktree switch flows into POST body

**Goal:** verify the `worktree` field in the request body tracks the
currently-selected worktree.

**Steps:**
1. From a worktree with at least 2 worktrees available, modify a file.
2. In the sidebar's worktree tabs, switch to the **other** worktree.
3. Click ↩ on the modified file and confirm.

**Expected result:**
- DevTools Network panel shows the request body contains
  `"worktree": "<path of the OTHER worktree>"`.
- **Code exercised:**
  - `dashboard/src/components/chat/GitDiffSidebar.vue:468-470`
    (passes `selectedWorktree.value` to `fileRestore.restore()`)
  - `dashboard/src/composables/useSpcodeFileRestore.ts:46-51`
    (request body assembly)

---

## Scenario 7 — Unloading project hides the ↩ button

**Goal:** verify the button is hidden when no spcode project is loaded
(spec §6.2 conditional render).

**Steps:**
1. With a project loaded, confirm ↩ buttons are visible.
2. Unload the project (via the spcode plugin unload control).

**Expected result:**
- All ↩ buttons disappear from the sidebar.
- `useSpcodeGitDiff` reports `state.kind === "error"` with reason
  `no_project_loaded`.
- **Code exercised:**
  - `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue:19-23, 44-46`
    (conditional render of button when `props.onRestore` provided)

---

## Scenario 8 — Network request shape verification

**Goal:** verify the request URL, method, and body shape match the
backend contract (`POST /plugins/extensions/spcode/file-restore`).

**Steps:**
1. Open DevTools Network panel and filter by `file-restore`.
2. Trigger any restore (success or failure).
3. Inspect the captured request.

**Expected result:**
- **Method:** `POST`
- **URL:** ends with `/plugins/extensions/spcode/file-restore` (exact
  prefix depends on the reverse-proxy / extension mount path; the
  fragment `spcode/file-restore` must be present).
- **Request body (JSON):**
  ```json
  {
    "file": "<file path string>",
    "worktree": "<absolute worktree path or omitted>",
    "umo": "<UMO string or omitted>"
  }
  ```
- **Response status:** `200` (both success and business-failure paths).
- **Code exercised:**
  - `dashboard/src/composables/useSpcodeFileRestore.ts:46-54`
    (`pluginExtensionApi.post("spcode/file-restore", { ... })`)

---

## Scenario 9 — Three-locale UI text

**Goal:** verify all user-facing strings (button, dialog, snackbar) flip
correctly when the dashboard language is switched.

**Steps:**
1. Set dashboard language to `zh-CN`, then perform scenario 3 (success
   path) and capture the button / confirm dialog / toast text.
2. Switch to `en-US`, repeat.
3. Switch to `ru-RU`, repeat.

**Expected (zh-CN):**
- Button title: "恢复" — tooltip: "恢复文件 README.md"
- Dialog title: "恢复文件？" — body: `将丢弃 "README.md" 相对于 index 的所有改动，该操作不可撤销。`
- Actions: "取消" / "恢复"
- Success toast: "已恢复 README.md"
- Untracked failure toast: "未跟踪的文件无法恢复（请用 git rm --cached 或 git add）"

**Expected (en-US):**
- Button: "Restore" — tooltip: "Restore file README.md"
- Dialog: "Restore file?" — body: `This will discard all uncommitted changes to "README.md". This cannot be undone.`
- Actions: "Cancel" / "Restore"
- Success toast: "Restored README.md"
- Untracked failure: "Cannot restore an untracked file (use git rm --cached or git add)"

**Expected (ru-RU):**
- Button: "Восстановить" — tooltip: "Восстановить файл README.md"
- Dialog: "Восстановить файл?" — body: `Это отменит все незафиксированные изменения в "README.md". Действие необратимо.`
- Actions: "Отмена" / "Восстановить"
- Success toast: "Восстановлено: README.md"
- Untracked failure: "Невозможно восстановить неотслеживаемый файл (используйте git rm --cached или git add)"

**Code exercised:**
- `dashboard/src/i18n/locales/zh-CN/features/chat.json` —
  `spcodeProjectLoad.diffSidebar.restore.*`
- `dashboard/src/i18n/locales/en-US/features/chat.json` — same path
- `dashboard/src/i18n/locales/ru-RU/features/chat.json` — same path
- `dashboard/src/components/chat/GitDiffSidebar.vue:828, 832, 837, 840`
  (i18n key references in dialog markup)
- `dashboard/src/components/chat/GitDiffSidebar.vue:475` (success toast)
- `dashboard/src/components/chat/GitDiffSidebar.vue:486-489`
  (failure toast, branching on `git_error` to substitute `{stderr}`)

---

## Sign-off

When all 9 scenarios pass, mark the PR description's "Manual smoke
test" checkbox. If any scenario fails, do not merge; record the
failure in the PR comments with the scenario number, observed vs.
expected, and DevTools Network screenshot if relevant.
