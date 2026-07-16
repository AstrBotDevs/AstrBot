# GitDiffSidebar: Non-Git-Project Init Prompt Design

**Date:** 2026-07-16
**Status:** Draft (pending user review)
**Author:** elecvoid243
**Related:** `docs/api/v2.17.0-endpoints-frontend.md` §1 `POST /spcode/git-init` and §2 `GET /spcode/git-branches` (latter used as the probe endpoint)

## Goal

When a user has loaded a project that is **not** a Git repository (i.e. the loaded directory has no `.git/`), opening `GitDiffSidebar` must surface a clear, full-width prompt that asks the user whether they want to initialize a Git repository right there. If the user confirms, the dashboard calls `POST /spcode/git-init` on the loaded directory and the sidebar re-renders as a freshly-initialized, empty Git repository (with the default branch as the "current" branch). If the user cancels, the sidebar stays usable in a degraded mode: the **Files** view remains functional (file browsing does not require Git), while **Diff / History / Worktree** are visibly disabled and explained.

## Background

The spcode plugin's `GET /spcode/git-branches` endpoint has a preflight check that returns `reason: "not_a_git_repo"` when the loaded directory is not a Git repository. The same endpoint is intended to feed a future branch-management UI. This spec uses it as a **probe**: the response's `reason` field is the single source of truth for "is this a Git repository right now?".

The plugin also exposes `POST /spcode/git-init`, which initializes a new repository on the supplied path and returns the chosen default branch. It is the only write endpoint in v2.17.0 that is exempted from the "must be a Git repository" preflight (because "no Git repository" is exactly the state in which initialization is wanted).

Branch management itself (create / switch / delete branches) is **out of scope** for this spec: per the user's request, the user runs `git branch` themselves, and `Worktree` (already supported in `GitDiffSidebar`) is the supported way to isolate work for an agentic workflow.

## Scope

The feature applies when a project is loaded in the spcode plugin and the user opens `GitDiffSidebar`:

- If the loaded directory is a Git repository → no visible change. Sidebar renders as today.
- If the loaded directory is **not** a Git repository:
  - The sidebar body shows a full-width `GitRepoInitPrompt` instead of the regular Files / Diff / History / Docs body.
  - The view-mode tab strip (Files / Diff / History / Docs) and the worktree tab strip are hidden, because they have nothing useful to show on a non-Git directory.
  - The user can either confirm the initialization or cancel.
- After a successful initialization, the sidebar transitions to a normal empty-Git-repo state, the prompt disappears, and the default branch becomes the current branch.
- After a cancelled prompt (Q4c option C2), the sidebar shows a small "not a Git project" chip at the top and the Files view is selectable; Diff / History / Worktree / Docs remain visually disabled with an explanatory tooltip.
- The Files view's data fetching is **unchanged** — it does not need Git. The Diff and History views already have empty-state copy and continue to use it once the repo is initialized but has no commits.
- The chip is **not persisted**; reopening the sidebar or reloading the page re-presents the prompt.

The feature must:

- probe the Git status of the currently-loaded directory via `GET /spcode/git-branches` whenever the sidebar opens, whenever the loaded project changes (`umo` or `directory`), and on a 30 s polling cadence;
- respect `ETag` / `304` from the probe endpoint, with `localStorage`-backed cache keys, exactly as described in `v2.17.0-endpoints-frontend.md` §9;
- on a successful `POST /spcode/git-init`, force-invalidate the probe ETag, re-run the probe, and update the sidebar state to reflect the freshly-initialized repository;
- on a failed `POST /spcode/git-init`, keep the prompt visible, surface the server's `stderr` to the user, and leave the probe state unchanged;
- never block the Files view from rendering once the user has cancelled the prompt.

The feature must **not**:

- implement any branch-management UI (create / switch / delete branches) — this is out of scope per the user's request;
- add `is_git_repo` to `useSpcodeProjectStatus` (the project-status composable remains unchanged);
- introduce any new backend endpoint or modify any existing one;
- persist any "dismissed" state for the prompt;
- affect any code path that is not on the `GitDiffSidebar` route;
- alter the existing `GitCommitBar`, `GitCommitDialog`, `GitLogView`, `GitDiffBodyContent`, or `WorktreeCreateDialog` components.

## Architecture

Three new frontend files plus one modification:

1. `dashboard/src/composables/parseSpcodeGitRepoProbe.ts` — type definitions and a single envelope-parser that recognizes the `ok` and `not_a_git_repo` reasons on the probe endpoint.
2. `dashboard/src/composables/useSpcodeGitRepoProbe.ts` — Vue composable that holds the probe state machine, owns the `ETag`/`localStorage` cache, and exposes the `gitInit` mutation.
3. `dashboard/src/components/chat/message_list_comps/GitRepoInitPrompt.vue` — the full-width prompt component.
4. `dashboard/src/components/chat/GitDiffSidebar.vue` — wire the new composable into the orchestrator, add the `v-if`-gated prompt slot, hide the view-mode and worktree tabs when the repo is not a Git repository, and add a dismissed-state chip.
5. `dashboard/src/i18n/locales/{en-US,zh-CN,ru-RU}/features/chat.json` — new keys under `spcodeProjectLoad.diffSidebar.repoInit.*`.

The composable follows the same single-instance-per-`GitDiffSidebar` lifecycle pattern as `useSpcodeWorktrees` and `useSpcodeGitStatus`: one instance is created in `script setup`, polling is started in `onMounted`, and `dispose()` is invoked in `onBeforeUnmount`. Unlike those composables, it owns no data derived from the probe response other than the `ok` / `not_a_git_repo` boolean and the default branch name (used to label the new branch after init); the full branch list will be owned by a future branch-management composable, not by this one.

### Module Dependency Diagram

```
GitDiffSidebar.vue
  ├─ import: useSpcodeGitRepoProbe
  │     └─ import: parseSpcodeGitRepoProbe
  ├─ import: GitRepoInitPrompt (no further deps)
  └─ import: useSpcodeProjectStatus (unchanged)

useSpcodeGitRepoProbe
  ├─ import: pluginExtensionApi (@/api/v1)
  ├─ import: useSpcodeProjectStatus
  └─ import: parseSpcodeGitRepoProbe (for shape validation)

parseSpcodeGitRepoProbe
  └─ (no internal deps)
```

## State Machine

```ts
type GitRepoProbeState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; defaultBranch: string | null }
  | { kind: 'not_a_git_repo'; directory: string }
  | { kind: 'error'; reason: string; stderr?: string }
```

The ETag string is held in a closure-level variable inside the composable (not in `state`), because the UI does not need to react to ETag changes — only to the parsed `ok` / `not_a_git_repo` outcome.

State transitions:

- `idle` → `loading` on `refresh()` and on `gitInit()` start.
- `loading` → `ok` when the probe response is `success: true` and the envelope's `reason` is `null`. `defaultBranch` is read from `data.default` (e.g. `"main"`).
- `loading` → `not_a_git_repo` when the probe response is `success: false` and `reason === 'not_a_git_repo'`. `directory` is the loaded `projectRoot`.
- `loading` → `error` for any other failure reason (`git_unavailable`, `network`, `unknown`, …) or for an unparseable response. `stderr` is propagated verbatim when present.
- `ok` → `loading` on a subsequent `refresh()`; the previous `ok` snapshot is preserved on the loading state so the UI does not flicker.
- `not_a_git_repo` → `loading` on a subsequent `refresh()` (typically called immediately after `gitInit()` succeeds).
- `error` → `loading` on a subsequent `refresh()`; `error` does not carry a `previousSnapshot` (errors are not sticky).

When the loaded project changes (new `umo` or new `directory`), the composable resets to `idle` and the next `refresh()` is the authoritative one.

## Probe Endpoint and Caching

The probe reuses `GET /spcode/git-branches?umo=<umo>&worktree=<worktree>`. The response envelope (`ResponseEnvelope<GitBranchesResponse>`) is parsed only for two fields:

- `reason === null` ⇒ the directory is a Git repository. Read `data.default` for the default branch name.
- `reason === 'not_a_git_repo'` ⇒ the directory is not a Git repository. Read `data.directory` (it should equal the loaded `projectRoot`).
- Any other `reason` ⇒ the probe failed for an unrelated reason; surface it as an `error` state and let the user retry.

`ETag`/`304` is implemented exactly as in `v2.17.0-endpoints-frontend.md` §9:

- Two `localStorage` keys are used per `(umo, worktree)` pair:
  - `astrbot.spcode.gitRepoProbe.etag.<umo>.<worktree>` — the ETag string.
  - `astrbot.spcode.gitRepoProbe.snapshot.<umo>.<worktree>` — the last-known `ok` snapshot as JSON.
- On `refresh()`:
  - If a cached ETag exists, send `If-None-Match`.
  - On `304`: restore the cached snapshot (state becomes `ok`); do **not** issue a network round-trip.
  - On `200`: store the new ETag and snapshot.
- On `gitInit()` success: **delete both keys** for the current `(umo, worktree)` and call `refresh()` once to re-probe the now-Git directory.

The cache key includes the `worktree` because each worktree has its own `.git` resolution (linked worktrees use a `.git` file pointing at the main worktree's `worktrees/<name>` directory). Polling uses the same `worktree` value the sidebar already passes to `useSpcodeGitStatus` and `useSpcodeGitLog` — i.e. `selectedWorktree.value ?? mainWorktreePath.value`.

## gitInit Mutation

`useSpcodeGitRepoProbe.gitInit(params: { path: string })` performs the following:

1. Set state to `loading`.
2. POST `POST /spcode/git-init` with body `{ path: params.path, initial_branch: 'main', bare: false }`. (The `initial_branch` and `bare` fields are hard-coded for v1 — see the *Non-Goals* section.)
3. On `success: true`: delete the cached ETag and snapshot, call `refresh()` once, and return `{ ok: true, defaultBranch: response.data.initial_branch }`. After `refresh()` resolves, the state will be `ok` (assuming the init succeeded) and the prompt will hide automatically.
4. On `success: false` with a known reason: return `{ ok: false, reason, stderr? }` and set the state back to `not_a_git_repo` (preserving the `directory`). The prompt remains visible and renders the `stderr` if present.
5. On network / parse errors: same as step 4, but with `reason: 'unknown'` (or `'network'` if `ERR_NETWORK`).

A single-flight guard mirrors `useSpcodeWorktrees`: a second `gitInit()` call before the first resolves aborts the first.

## Component: GitRepoInitPrompt

```vue
<script setup lang="ts">
defineProps<{
  /** Absolute path of the directory that needs initialization. */
  directory: string;
  /** True while a POST /spcode/git-init request is in flight. */
  isSubmitting: boolean;
  /**
   * Most recent stderr from a failed init, if any. When present, the
   * prompt renders an inline error block above the buttons. Cleared
   * by the parent on every new submission attempt.
   */
  lastError?: { reason: string; stderr?: string } | null;
}>();
defineEmits<{
  (e: 'confirm'): void;
  (e: 'cancel'): void;
}>();
</script>
```

Visual layout (full-width, padded, no tab strip above):

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│         ℹ  这不是一个 Git 项目                       │
│                                                     │
│   当前文件夹 D:\Users\dev\projects\myapp            │
│   下未检测到 .git/ 目录。                            │
│                                                     │
│   初始化为新的 Git 仓库后将自动创建默认分支(main)。  │
│                                                     │
│   [ 取消 ]   [ 初始化 Git 仓库 ]                     │
│                                                     │
│   ── lastError 存在时: ──                           │
│   ⚠ git: 'D:/.../myapp' already exists             │
│     (reason: directory_not_empty)                   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

Behavior:

- The `confirm` button shows an inline spinner and is disabled while `isSubmitting` is `true`. The `cancel` button is also disabled during submission.
- The `lastError` block is rendered only when `lastError` is non-null. Its text is `${reason} — ${stderr}` (or just `reason` if `stderr` is empty).
- Pressing `Escape` while the prompt is focused emits `cancel` (the same handler as the button).

## GitDiffSidebar Integration

### Imports

Add to the existing import block near the top of `<script setup>`:

```ts
import GitRepoInitPrompt from '@/components/chat/message_list_comps/GitRepoInitPrompt.vue';
import { useSpcodeGitRepoProbe } from '@/composables/useSpcodeGitRepoProbe';
```

### Composable instance and derived state

Add immediately after the existing `useSpcodeWorktrees()` line:

```ts
const gitRepoProbe = useSpcodeGitRepoProbe();

const isGitRepo = computed(
  () => gitRepoProbe.state.value.kind === 'ok',
);
const isRepoInitSubmitting = ref(false);
const repoInitLastError = ref<{ reason: string; stderr?: string } | null>(null);
const repoPromptDismissed = ref(false);   // session-only, Q4c option C2
const showRepoInitPrompt = computed(
  () =>
    isProjectLoaded.value
    && gitRepoProbe.state.value.kind === 'not_a_git_repo'
    && !repoPromptDismissed.value,
);
const showNotGitRepoChip = computed(
  () =>
    isProjectLoaded.value
    && gitRepoProbe.state.value.kind === 'not_a_git_repo'
    && repoPromptDismissed.value,
);
const disableGitViews = computed(
  () => !isGitRepo.value && !showNotGitRepoChip.value,
);
```

### Lifecycle

In `onMounted`, after the existing `worktreesComposable.refresh()` call:

```ts
void gitRepoProbe.refresh();
gitRepoProbe.startPolling(30_000);
```

In `onBeforeUnmount`, after the existing `worktreesComposable.stopPolling()` call:

```ts
gitRepoProbe.stopPolling();
gitRepoProbe.dispose();
```

### Project-switch / worktree-switch watchers

The composable internally watches `umo` and `directory` and re-probes on change (matching the pattern in `useSpcodeWorktrees` and `useSpcodeGitStatus`). No additional orchestrator code is required for project switches. On worktree switches, the existing `onWorktreeChange()` handler must also reset the dismissed flag:

```ts
function onWorktreeChange(path: string | null): void {
  // ... existing logic ...
  repoPromptDismissed.value = false;
}
```

This is so a user who cancels the prompt on one worktree and then switches to a different worktree (where the directory is also not a Git repository) is re-presented the prompt.

### Handlers

Add two new handlers near the existing `onInitSubmit`:

```ts
async function onRepoInitConfirm(): Promise<void> {
  if (!projectRoot.value) return;
  repoInitLastError.value = null;
  isRepoInitSubmitting.value = true;
  const result = await gitRepoProbe.gitInit({ path: projectRoot.value });
  isRepoInitSubmitting.value = false;
  if (result.ok) {
    repoPromptDismissed.value = false;
    return;
  }
  repoInitLastError.value = {
    reason: result.reason,
    stderr: result.stderr,
  };
}

function onRepoInitCancel(): void {
  repoPromptDismissed.value = true;
  repoInitLastError.value = null;
}
```

### Template changes

Three modifications, all in the body of `<aside class="git-diff-sidebar">`:

1. Replace the existing view-mode tab strip block (the `<div class="git-diff-sidebar-view-tabs">` near the bottom of the header) with a version gated on `isGitRepo || showNotGitRepoChip`:

   ```vue
   <div
     v-if="isGitRepo || showNotGitRepoChip"
     class="git-diff-sidebar-view-tabs"
     role="tablist"
     aria-label="Switch view"
   >
     <!-- unchanged children -->
   </div>
   ```

2. Add a `v-if` to the existing worktree tabs block:

   ```vue
   <div
     v-if="hasMultipleWorktrees && (isGitRepo || showNotGitRepoChip)"
     class="git-diff-sidebar-tabs"
     ...
   >
     <!-- unchanged children -->
   </div>
   ```

3. Insert the prompt and the chip directly above the existing `<div class="git-diff-sidebar-body">`:

   ```vue
   <GitRepoInitPrompt
     v-if="showRepoInitPrompt"
     :directory="gitRepoProbe.state.value.kind === 'not_a_git_repo'
                 ? gitRepoProbe.state.value.directory
                 : ''"
     :is-submitting="isRepoInitSubmitting"
     :last-error="repoInitLastError"
     @confirm="onRepoInitConfirm"
     @cancel="onRepoInitCancel"
   />
   <div
     v-else-if="showNotGitRepoChip"
     class="git-diff-sidebar-repo-chip"
     role="status"
   >
     <v-icon size="14">mdi-information-outline</v-icon>
     <span>{{ tm('spcodeProjectLoad.diffSidebar.repoInit.dismissedChip') }}</span>
     <button
       type="button"
       class="git-diff-sidebar-repo-chip-action"
       @click="repoPromptDismissed = false"
     >
      {{ tm('spcodeProjectLoad.diffSidebar.repoInit.reopenPrompt') }}
     </button>
   </div>
   ```

The body itself (`<div class="git-diff-sidebar-body">`) needs no change: it already renders the Files / Diff / History / Docs views, and the `Files` view continues to work when Git is absent. The `Diff` and `History` views will hit the existing `not_a_git_repo` error path on the backend and surface the standard error toast.

### Scoped CSS

Add a small block to the existing `<style scoped>` for the chip:

```css
.git-diff-sidebar-repo-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--v-theme-surface-variant, rgba(0, 0, 0, 0.04));
  border-bottom: 1px solid var(--v-border-color, rgba(0, 0, 0, 0.08));
  font-size: 12px;
}
.git-diff-sidebar-repo-chip-action {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--v-theme-primary, #1976d2);
  cursor: pointer;
  font: inherit;
  padding: 0;
}
```

The `GitRepoInitPrompt` component ships its own scoped styles; it does not depend on `GitDiffSidebar` selectors.

## i18n

Add the following keys to `spcodeProjectLoad.diffSidebar.repoInit.*` in all three locale files (`en-US`, `zh-CN`, `ru-RU`):

| Key | English | 简体中文 | Русский |
|---|---|---|---|
| `title` | This is not a Git project | 这不是一个 Git 项目 | Это не Git-проект |
| `body` | The current folder `{directory}` does not contain a `.git/` directory. | 当前文件夹 {directory} 下未检测到 .git/ 目录。 | В текущей папке {directory} не найден каталог .git/. |
| `hint` | Initializing a new Git repository here will create the default branch ({defaultBranch}). | 在此初始化新的 Git 仓库后将自动创建默认分支({defaultBranch})。 | Инициализация нового Git-репозитория создаст ветку по умолчанию ({defaultBranch}). |
| `confirm` | Initialize Git repository | 初始化 Git 仓库 | Инициализировать Git-репозиторий |
| `cancel` | Cancel | 取消 | Отмена |
| `dismissedChip` | This is not a Git project. | 当前目录不是 Git 项目,部分功能受限。 | Это не Git-проект, часть функций недоступна. |
| `reopenPrompt` | Initialize now | 立即初始化 | Инициализировать сейчас |
| `submitting` | Initializing… | 正在初始化… | Инициализация… |
| `errors.directory_not_empty` | The directory is not empty. Please clean it up first, or use a bare repository. | 目录非空,请先清理或使用 bare 仓库。 | Каталог не пуст. Сначала очистите его или используйте bare-репозиторий. |
| `errors.path_not_directory` | The path does not exist or is not a directory. | 路径不存在或不是目录。 | Путь не существует или не является каталогом. |
| `errors.already_a_git_repo` | This directory is already a Git repository. | 该目录已是 Git 仓库,无需初始化。 | Этот каталог уже является Git-репозиторием. |
| `errors.worktree_blacklisted` | The path is protected by configuration. | 该路径受配置保护。 | Путь защищён конфигурацией. |
| `errors.path_unsafe` | The path is not allowed. | 路径不合法。 | Путь недопустим. |
| `errors.init_failed` | Git initialization failed: {stderr} | 初始化失败:{stderr} | Ошибка инициализации: {stderr} |
| `errors.unknown` | An unexpected error occurred. | 发生意外错误。 | Произошла непредвиденная ошибка. |

The `body` and `hint` keys use placeholder substitution with `{directory}` and `{defaultBranch}` respectively, matching the existing i18n usage pattern in the same file.

## Error Handling Summary

| Backend `reason` | UX behavior |
|---|---|
| `not_a_git_repo` (from probe) | Full-width prompt is shown. |
| `git_unavailable` (from probe) | Sidebar shows a top-of-sidebar error chip with the same styling as the dismissed chip but with a different message. Files view is still rendered. |
| `network` / `unknown` (from probe) | Same as `git_unavailable`, but the chip copy says "Could not reach the spcode plugin. Retry?". A retry button calls `gitRepoProbe.refresh()`. |
| `directory_not_empty` (from init) | `lastError` is set, prompt remains, button re-enables. |
| `path_not_directory` (from init) | Same as above. |
| `already_a_git_repo` (from init) | Rare race; the prompt disappears automatically because the next probe returns `ok`. |
| `worktree_blacklisted` / `path_unsafe` (from init) | `lastError` is set, prompt remains. |
| `init_failed` (from init) | `lastError` is set with the `stderr`, prompt remains. |

All non-`not_a_git_repo` probe errors are non-fatal: the Files view continues to render and the user can still navigate. The chip is the only indicator.

## Testing

Three test files, no E2E (see the *Non-Goals* section):

1. `dashboard/src/composables/parseSpcodeGitRepoProbe.spec.ts` — unit tests for the parser. Cases:
   - `success: true, reason: null` → `{ kind: 'ok', defaultBranch: 'main' }`.
   - `success: false, reason: 'not_a_git_repo'` → `{ kind: 'not_a_git_repo', directory: '...' }`.
   - `success: false, reason: 'git_unavailable'` → `{ kind: 'error', reason: 'git_unavailable' }`.
   - Missing `data` field → `{ kind: 'error', reason: 'unknown' }`.

2. `dashboard/src/composables/useSpcodeGitRepoProbe.spec.ts` — unit tests for the composable. Cases:
   - `refresh()` against a Git repo → state becomes `ok`, ETag is stored.
   - `refresh()` against a non-Git directory → state becomes `not_a_git_repo`.
   - `refresh()` with cached ETag + server returns `304` → state stays `ok` with the cached snapshot.
   - `gitInit()` success → ETag is invalidated, `refresh()` is called automatically, state becomes `ok`.
   - `gitInit()` with `directory_not_empty` → state goes back to `not_a_git_repo`, return value is `{ ok: false, reason: 'directory_not_empty', stderr: '...' }`.
   - `gitInit()` called twice rapidly → the first call is aborted (single-flight).

3. `dashboard/src/components/chat/message_list_comps/GitRepoInitPrompt.spec.ts` — component tests. Cases:
   - Renders `directory` in the body.
   - Emits `confirm` on the primary button.
   - Emits `cancel` on the secondary button.
   - Disables both buttons when `isSubmitting` is `true`.
   - Renders `lastError.stderr` when provided.
   - Does not render the `lastError` block when `lastError` is `null`.

All tests use Vitest with `@vue/test-utils` (matching existing component tests in the same directory).

## Non-Goals (YAGNI)

The following are explicitly **not** part of this spec and are deferred to future work:

- Branch-management UI: create / switch / delete branches. The user runs `git` themselves; `Worktree` is the supported isolation mechanism.
- Surface `is_git_repo` in `useSpcodeProjectStatus`. The probe is local to the sidebar.
- "Initialize as bare repository" option in the UI. `bare: false` is hard-coded.
- Custom `initial_branch` option in the UI. `initial_branch: 'main'` is hard-coded.
- "Initialize and add .gitignore template" workflow.
- Persistence of the dismissed state.
- Auto-reopening of the prompt after a successful init (it just hides).
- Linking the prompt to a chat / agent command (e.g. `/spcode init`) — the prompt is purely UI.
- E2E tests. The unit-test coverage above is sufficient given the small surface area.
- A separate confirmation dialog for `directory_not_empty` failures. The inline `lastError` block is the only surface.
- Any change to the `Files` view, the `Diff` view, the `History` view, the `Docs` view, the `Worktree` tab strip, the `GitCommitBar`, or the `GitCommitDialog`.

## Risks

1. **ETag race during init**: the `gitInit` mutation deletes the cache and re-probes. If the user switches worktrees in the brief window between `gitInit` resolving and the re-probe completing, the ETag might be re-populated with stale data. Mitigation: the orchestrator resets `repoPromptDismissed` and the composable's internal watchers re-probe on `umo` / `directory` change, which clears the cache key prefix for the new `(umo, worktree)` pair.
2. **Polling cost**: a 30 s cadence means a non-Git directory shows the prompt within 30 s of a directory becoming non-Git. The cost is one HTTP round-trip per polling cycle, identical to `useSpcodeWorktrees`. Acceptable.
3. **Agent interference**: if an external tool (e.g. a CLI session) runs `git init` while the sidebar is open, the probe will pick it up within 30 s. No special handling required.
4. **i18n drift**: the three locale files must stay in sync. The existing `validator.ts` CI check enforces this. No new keys are skipped.
5. **Empty-state semantics after init**: the user lands in an empty Git repository. The `Files` view works (file browsing), the `Diff` view shows "no changes" (the existing empty-state copy), and the `History` view shows "no commits yet". No special empty-repo copy is introduced by this spec.

## Open Questions

None at draft time. All clarifications were resolved in the brainstorming phase:

- Scope: probe + init prompt only. No branch management.
- Files-view on non-Git directories: allowed (Q4 option A1).
- Probe endpoint: `GET /spcode/git-branches` (option A, 0 backend changes).
- Cancel UX: dismissed chip, not sticky (Q4c option C2).
- Post-init default branch: shown in path strip (Q4a option A1 derivative).
- Init failure: in-prompt inline `lastError` (Q4b option B2 derivative).
