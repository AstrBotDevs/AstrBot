# ChatUI Git Diff Sidebar Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Git Diff sidebar to the dashboard chat UI that lists and previews the working-tree diff of the currently loaded spcode project, with 10s polling, mutual exclusion with other sidebars, and full i18n.

**Architecture:** Side-effect-free `parseSpcodeGitDiff` raw-response → reactive `useSpcodeGitDiff` state machine with 10s `setInterval` polling + AbortController → three-component UI tree (`GitDiffSidebar` shell, `GitDiffBodyContent` state-machine renderer, `GitDiffFileItem` row) plus a `GitDiffChip` outlined v-chip in `ChatInput`'s status row. Mirrors existing `ReasoningSidebar` / `openXxxPanel` patterns; no `DiffPreview.vue` changes; no spcode plugin changes.

**Tech Stack:** Vue 3 Composition API (`<script setup>`), Vuetify 3 (`v-chip` / `v-tooltip` / `v-alert` / `v-progress-circular` / `v-btn`), TypeScript strict mode, i18next (`useModuleI18n` composable + dot-path keys), `pluginExtensionApi.get` (axios) for the `/spcode/git-diff` HTTP call.

**Spec:** `docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md`

**Sister spec (depends-on):** `docs/superpowers/specs/2026-06-16-chatui-project-load-button-design.md`
- Defines `applyOptimistic` / `setUnloaded` consumed by §5.3
- Defines the existing `<SpcodeProjectIndicator/>` chip in `ChatInput.vue:status-row` that we sit next to

**Out-of-scope reminders (from spec §1.4 / §9):**
- ❌ No multi-project diff, no file search/filter, no commit history, no staged/unstaged toggle, no commit/revert, no Vitest (per §1.4 + sister spec §1.4).
- ❌ No spcode plugin changes.
- ❌ No `DiffPreview.vue` changes.
- ❌ No `useSpcodeProjectStatus.ts` changes.

**Verification convention (per spec §7.1):** No Vitest. Each task verifies with `pnpm typecheck` (TypeScript compile) + `pnpm lint` (ESLint). End-of-plan: full §7.2 E2E checklist (E1–E14) run manually in dev server.

---

## File Structure

### New files (6)

| File | Responsibility | Lines (est.) |
|---|---|---|
| `dashboard/src/composables/parseSpcodeGitDiff.ts` | Pure function: raw `SpcodeGitDiffRawResponse` → `SpcodeGitDiffSnapshot`. Handles slicing unified diff by `diff --git` headers, binary detection, path→slice mapping, reason/status fallback. | ~80 |
| `dashboard/src/composables/useSpcodeGitDiff.ts` | Composable: HTTP fetch + state machine (`idle/loading/ok/error`) + 10s polling + AbortController + `dispose()`. Returns reactive `state`, `refresh`, `startPolling`, `stopPolling`. | ~120 |
| `dashboard/src/components/chat/GitDiffChip.vue` | Outlined v-chip with `mdi-source-pull` icon + tooltip. Emits `open-diff-sidebar`. | ~30 |
| `dashboard/src/components/chat/GitDiffSidebar.vue` | Outer shell: drag resizer, slide-left transition, header (title + directory tooltip + refresh + close), truncation warning, mounts `<GitDiffBodyContent>`. Owns composable instance; manages polling lifecycle; auto-closes on `status.loaded=false`. | ~150 |
| `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue` | Pure state-machine renderer: loading spinner / error block / empty / file list / error banner. Takes `state`, `expanded`, `isDark` as props. | ~80 |
| `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue` | Single file row (status icon + path + +/- stats + chevron) + collapsible body (`<DiffPreview>` or `v-alert` binary placeholder). | ~60 |

### Modified files (5)

| File | Change scope |
|---|---|
| `dashboard/src/components/chat/ChatInput.vue` | (a) Add `'open-diff-sidebar'` to `defineEmits` block. (b) Wrap status row in `justify-content: space-between`. (c) Add `<GitDiffChip v-if="showSpcodeIndicator && spcodeStatus.status.value.loaded" @open-diff-sidebar="$emit('open-diff-sidebar')" />`. |
| `dashboard/src/components/chat/Chat.vue` | (a) Import `GitDiffSidebar`. (b) Add `gitDiffSidebarOpen` ref. (c) Add `openGitDiffSidebar()` that closes other sidebars. (d) Mount `<GitDiffSidebar v-model="gitDiffSidebarOpen" />` in template. (e) Add `watch(currSessionId, ...)` line to close on session change. |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | Add 19 keys under `spcodeProjectLoad.diffSidebar.*` (17 from spec §5.1.1 + `noContent` + `loadFailedTitle` from Chunk 2 advisory). |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | Same 19 keys, English values. |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | Same 19 keys, Russian values. |

### File ordering rationale
1. i18n keys first (other code references them; adding first means `pnpm typecheck` succeeds for the rest)
2. Pure parser next (no dependencies, self-contained)
3. Composable next (depends on parser types)
4. `GitDiffFileItem` (leaf, no deps on other new components)
5. `GitDiffBodyContent` (depends on `GitDiffFileItem`)
6. `GitDiffSidebar` (depends on `GitDiffBodyContent` + composable)
7. `GitDiffChip` (depends on i18n only)
8. `ChatInput` (depends on `GitDiffChip`)
9. `Chat.vue` (depends on `GitDiffSidebar`)
10. Lint + typecheck + CHANGELOG

---

## Chunk 1: Data Layer (i18n keys + parser + composable)

### Task 1: Add 17 i18n keys to all three locales

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

**Context:**
- The 17 keys are listed verbatim in spec §5.1.1. Copy the table values into the existing `spcodeProjectLoad` object in each JSON.
- Each locale JSON follows the existing flat dot-path convention. Use 2-space indentation, no trailing commas, ensure JSON is valid.
- The three locales must contain **the same set of keys** to avoid `tm()` falling back to key name at runtime.

- [ ] **Step 1.1: Locate the `spcodeProjectLoad` object** in each of the 3 JSON files

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
grep -n "spcodeProjectLoad" src/i18n/locales/zh-CN/features/chat.json
grep -n "spcodeProjectLoad" src/i18n/locales/en-US/features/chat.json
grep -n "spcodeProjectLoad" src/i18n/locales/ru-RU/features/chat.json
```

Expected: each file shows the existing `spcodeProjectLoad` block with `menuItem`, `dialog.*`, `indicator.*` keys.

- [ ] **Step 1.2: Add 19 keys to `zh-CN/features/chat.json`**

Insert a new sub-object `spcodeProjectLoad.diffSidebar` immediately after `spcodeProjectLoad.indicator` (or at end of `spcodeProjectLoad` if no `indicator`). The 19 keys (17 from spec §5.1.1 + 2 from Chunk 2 advisory, Chinese values):

```json
"diffSidebar": {
  "chip": "Git Diff",
  "chipTooltip": "查看 Git 改动",
  "title": "项目改动",
  "refreshTooltip": "刷新",
  "loading": "加载中…",
  "empty": "暂无文件改动",
  "truncated": "⚠ diff 已截断（仅显示前 {shown} / {max} 字节，可能不完整）",
  "binaryFile": "二进制文件改动（无文本预览）",
  "noContent": "内容已截断或不完整",
  "error": {
    "networkTitle": "网络连接失败",
    "loadFailedTitle": "无法获取改动",
    "retry": "重试",
    "reason": {
      "feature_disabled": "功能未启用（请检查 spcode 配置 agentsmd_enabled / codegraph_enabled）",
      "no_project_loaded": "项目未载入",
      "directory_missing": "已加载的目录不存在",
      "not_a_git_repo": "当前目录不是 Git 仓库",
      "git_unavailable": "未检测到 git 可执行文件",
      "git_error": "Git 执行失败（{reason}）",
      "generic": "获取改动失败（{reason}）"
    }
  }
}
```

- [ ] **Step 1.3: Add the same 19 keys to `en-US/features/chat.json`**

English values (from spec §5.1.1, plus 2 new keys from Chunk 2 advisory): `chip: "Git Diff"`, `chipTooltip: "View Git changes"`, `title: "Project changes"`, `refreshTooltip: "Refresh"`, `loading: "Loading…"`, `empty: "No file changes"`, `truncated: "⚠ diff truncated (showing first {shown} / {max} bytes, may be incomplete)"`, `binaryFile: "Binary file changed (no text preview)"`, `noContent: "Content truncated or incomplete"`, `error.networkTitle: "Network connection failed"`, `error.loadFailedTitle: "Failed to load changes"`, `error.retry: "Retry"`, `error.reason.feature_disabled: "Feature disabled (check spcode config agentsmd_enabled / codegraph_enabled)"`, `error.reason.no_project_loaded: "No project loaded"`, `error.reason.directory_missing: "Loaded directory no longer exists"`, `error.reason.not_a_git_repo: "Current directory is not a Git repository"`, `error.reason.git_unavailable: "Git executable not found"`, `error.reason.git_error: "Git execution failed ({reason})"`, `error.reason.generic: "Failed to fetch changes ({reason})"`. **Total: 19 keys.**

- [ ] **Step 1.4: Add the same 19 keys to `ru-RU/features/chat.json`**

Russian values (from spec §5.1.1, plus 2 new keys from Chunk 2 advisory): `chip: "Git Diff"`, `chipTooltip: "Просмотр изменений Git"`, `title: "Изменения проекта"`, `refreshTooltip: "Обновить"`, `loading: "Загрузка…"`, `empty: "Нет изменений файлов"`, `truncated: "⚠ diff обрезан (показано первые {shown} / {max} байт, возможно неполный)"`, `binaryFile: "Бинарный файл изменён (без предпросмотра)"`, `noContent: "Содержимое обрезано или неполное"`, `error.networkTitle: "Ошибка сетевого подключения"`, `error.loadFailedTitle: "Не удалось получить изменения"`, `error.retry: "Повторить"`, `error.reason.feature_disabled: "Функция отключена (проверьте spcode config agentsmd_enabled / codegraph_enabled)"`, `error.reason.no_project_loaded: "Проект не загружен"`, `error.reason.directory_missing: "Загруженный каталог больше не существует"`, `error.reason.not_a_git_repo: "Текущий каталог не является репозиторием Git"`, `error.reason.git_unavailable: "Исполняемый файл git не найден"`, `error.reason.git_error: "Ошибка выполнения Git ({reason})"`, `error.reason.generic: "Не удалось получить изменения ({reason})"`. **Total: 19 keys.**

- [ ] **Step 1.5: Verify all 3 files are valid JSON with the same key set**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
node -e "const fs=require('fs');for(const l of['zh-CN','en-US','ru-RU']){const j=JSON.parse(fs.readFileSync('src/i18n/locales/'+l+'/features/chat.json','utf8'));const ds=j.spcodeProjectLoad?.diffSidebar;const topLeaves=ds?Object.keys(ds).filter(k=>k!=='error'):[];const errLeaves=ds?.error?Object.keys(ds.error).filter(k=>k!=='reason'):[];const reasons=ds?.error?.reason?Object.keys(ds.error.reason):[];console.log(l,'top-level leaves:',topLeaves.length,'error leaves:',errLeaves.length,'reason leaves:',reasons.length,'total:',topLeaves.length+errLeaves.length+reasons.length);}"
```

Expected output: each locale reports `top-level leaves: 9`, `error leaves: 3`, `reason leaves: 7`, `total: 19`. The 9 top-level leaves are: `chip`, `chipTooltip`, `title`, `refreshTooltip`, `loading`, `empty`, `truncated`, `binaryFile`, `noContent`. The 3 error leaves are: `networkTitle`, `loadFailedTitle`, `retry`. The 7 reason leaves match the 7 spcode reason values. Originally 17 per spec §5.1.1; +2 from Chunk 2 advisory: `noContent`, `loadFailedTitle`.

- [ ] **Step 1.6: Run typecheck to confirm dot-path types resolve**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm typecheck
```

Expected: PASS, with no `MISSING:` warnings related to `spcodeProjectLoad.diffSidebar.*`.

- [ ] **Step 1.7: Commit**

```bash
cd F:\github\Astrbot-git-diff-sidebar
git add dashboard/src/i18n/locales/zh-CN/features/chat.json dashboard/src/i18n/locales/en-US/features/chat.json dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "feat(i18n): add spcodeProjectLoad.diffSidebar keys (zh-CN/en-US/ru-RU)"
```

---

### Task 2: `parseSpcodeGitDiff` pure function

**Files:**
- Create: `dashboard/src/composables/parseSpcodeGitDiff.ts`

**Context:**
- Pure function: no side effects, no Vue, no HTTP. Input = raw response from `/spcode/git-diff`; output = `SpcodeGitDiffSnapshot` for UI consumption.
- Types defined in spec §4.1.1.
- Slicing algorithm (spec §4.1.1): split `data.diff` by `^diff --git ` multi-line, extract path from `b/`, mark binary if slice contains "Binary files", mark `slice=null` if path not in `files_changed` (truncated boundary).
- Status code normalization: M/A/D/R/C/T + fallback `unknown`.
- No unit tests per spec §1.4 / §7.1 (no Vitest). Verification = `pnpm typecheck` + `pnpm lint`.

- [ ] **Step 2.1: Stub the module with type definitions**

Create `dashboard/src/composables/parseSpcodeGitDiff.ts` with all the type interfaces from spec §4.1.1, plus a stub `parseSpcodeGitDiff` that returns a minimal snapshot:

```typescript
// Author: elecvoid243
// Date: 2026-06-17
// Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.1.1

export interface SpcodeGitDiffRawResponse {
  loaded: boolean
  directory: string | null
  umo: string | null
  diff: string | null
  stat: string | null
  files_changed: Array<{
    path: string
    status: string
    additions: number
    deletions: number
  }>
  truncated: boolean
  truncated_at_bytes: number
  max_bytes: number
  elapsed_ms: number
  reason: string | null
}

export type FileStatus = 'M' | 'A' | 'D' | 'R' | 'C' | 'T' | 'unknown'

export interface SpcodeGitDiffFile {
  path: string
  status: FileStatus
  additions: number
  deletions: number
  slice: string | null
  isBinary: boolean
}

export interface SpcodeGitDiffMeta {
  directory: string | null
  umo: string | null
  loaded: boolean
  truncated: boolean
  truncatedAtBytes: number
  maxBytes: number
  reason: string | null
  elapsedMs: number
  fetchedAt: number
}

export interface SpcodeGitDiffSnapshot {
  meta: SpcodeGitDiffMeta
  files: SpcodeGitDiffFile[]
  rawDiff: string | null
}

const VALID_STATUSES: ReadonlySet<FileStatus> = new Set(['M', 'A', 'D', 'R', 'C', 'T'])

/** Normalize a raw git status code to the FileStatus union. */
function normalizeStatus(raw: string): FileStatus {
  const s = raw[0] as FileStatus
  return VALID_STATUSES.has(s) ? s : 'unknown'
}

export function parseSpcodeGitDiff(data: SpcodeGitDiffRawResponse): SpcodeGitDiffSnapshot {
  return {
    meta: {
      directory: data.directory,
      umo: data.umo,
      loaded: data.loaded,
      truncated: data.truncated,
      truncatedAtBytes: data.truncated_at_bytes,
      maxBytes: data.max_bytes,
      reason: data.reason,
      elapsedMs: data.elapsed_ms,
      fetchedAt: Date.now(),
    },
    files: [],
    rawDiff: data.diff,
  }
}
```

- [ ] **Step 2.2: Verify stub typechecks**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm typecheck
```

Expected: PASS. The stub has all required exports and signatures, but the slicing logic is incomplete (empty `files: []`).

- [ ] **Step 2.3: Implement the slicing algorithm**

Replace the stub's `files: []` with the full slicing logic. The algorithm:

1. If `data.diff === null || data.files_changed === undefined` → return `files: []`.
2. Build `Map<path, SpcodeGitDiffFile>` from `data.files_changed` with `slice=null, isBinary=false` initially.
3. Split `data.diff` by `/^diff --git /m` (preserving each segment as-is, including the `diff --git` line as the first line of each segment).
4. For each segment:
   - Extract path from `^diff --git a\/(\S+) b\/(\S+)/m` → use the `b/` path (rename/copy target).
   - If segment contains `Binary files ... differ` substring → set `isBinary=true, slice=null` in the map.
   - Otherwise → set `slice=<segment>` in the map (the entire segment including `diff --git` / `index` / `--- a/` / `+++ b/` / `@@` hunks).
5. Return `files: Array.from(map.values())` preserving the order of `data.files_changed`.

Replace the body of `parseSpcodeGitDiff` accordingly. The complete function body (append after the meta assignment):

```typescript
    files: (() => {
      if (!data.diff || !Array.isArray(data.files_changed)) return []
      const byPath = new Map<string, SpcodeGitDiffFile>()
      for (const f of data.files_changed) {
        byPath.set(f.path, {
          path: f.path,
          status: normalizeStatus(f.status),
          additions: f.additions ?? 0,
          deletions: f.deletions ?? 0,
          slice: null,
          isBinary: false,
        })
      }
      const segments = data.diff.split(/^diff --git /m)
      for (let i = 1; i < segments.length; i++) {
        const seg = 'diff --git ' + segments[i]
        const m = seg.match(/^diff --git a\/\S+ b\/(\S+)/m)
        if (!m) continue
        const path = m[1]
        if (seg.includes('Binary files')) {
          const existing = byPath.get(path)
          if (existing) existing.isBinary = true
        } else {
          const existing = byPath.get(path)
          if (existing) existing.slice = seg
        }
      }
      return data.files_changed.map((f) => byPath.get(f.path)!)
    })(),
```

- [ ] **Step 2.4: Run typecheck + lint**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm typecheck && pnpm lint
```

Expected: both PASS. Lint may flag the `!` non-null assertion on `byPath.get(f.path)!`; if so, replace with `byPath.get(f.path) ?? { path: f.path, status: normalizeStatus(f.status), additions: f.additions ?? 0, deletions: f.deletions ?? 0, slice: null, isBinary: false }` to satisfy strict lint.

- [ ] **Step 2.5: Manual smoke test via dev-server console**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm dev
```

Then in the dashboard's HMR-patched module graph, add a temporary ad-hoc test in any existing `<script setup>` (e.g., ChatInput.vue's `onMounted`) and watch the browser console for assertions. Or use `pnpm vite-node` for a one-off script:

Create `dashboard/scripts/smoke-parse-git-diff.ts` (temp file, deleted after):

```typescript
import { parseSpcodeGitDiff } from '@/composables/parseSpcodeGitDiff'
const raw = {
  loaded: true, directory: '/tmp/repo', umo: 'aiocqhttp:group_message:123',
  diff: 'diff --git a/README.md b/README.md\nindex abc..def 100644\n--- a/README.md\n+++ b/README.md\n@@ -1,3 +1,3 @@\n line1\n-old\n+new\n line3\n',
  stat: ' README.md | 2 +-\n 1 file changed, 1 insertion(+), 1 deletion(-)\n',
  files_changed: [{ path: 'README.md', status: 'M', additions: 1, deletions: 1 }],
  truncated: false, truncated_at_bytes: 0, max_bytes: 1048576,
  elapsed_ms: 47, reason: null,
}
const snap = parseSpcodeGitDiff(raw)
console.assert(snap.files.length === 1, 'expected 1 file')
console.assert(snap.files[0].path === 'README.md', 'path mismatch')
console.assert(snap.files[0].isBinary === false, 'should not be binary')
console.assert(snap.files[0].slice?.includes('@@ -1,3 +1,3') === true, 'hunk missing')
console.log('smoke ok:', snap.files[0])
```

Run with: `pnpm tsx dashboard/scripts/smoke-parse-git-diff.ts` (or `pnpm vite-node`).
Expected console output: `smoke ok: { path: 'README.md', status: 'M', additions: 1, deletions: 1, slice: '...', isBinary: false }` and zero `Assertion failed` messages. Delete the script after the smoke test.

- [ ] **Step 2.6: Commit**

```bash
cd F:\github\Astrbot-git-diff-sidebar
git add dashboard/src/composables/parseSpcodeGitDiff.ts
git commit -m "feat(chatui): add parseSpcodeGitDiff pure function"
```

---

### Task 3: `useSpcodeGitDiff` composable

**Files:**
- Create: `dashboard/src/composables/useSpcodeGitDiff.ts`

**Context:**
- Reactive state machine + HTTP fetch + 10s polling.
- Pattern: composable is **per-instance** (NOT a singleton). Each `<GitDiffSidebar/>` mount creates a fresh instance via `useSpcodeGitDiff()`. The composable does NOT export the instance as a singleton.
- State types: `idle | loading | ok | error` (see spec §4.1.2).
- `refresh()` creates a new `AbortController`, aborts the previous, calls `pluginExtensionApi.get('spcode/git-diff', { params: { umo } })`, parses via `parseSpcodeGitDiff`.
- `startPolling(ms)` is idempotent (multiple calls keep one timer); `stopPolling()` clears it.
- `dispose()` sets `isMounted=false`, calls `stopPolling()`, aborts in-flight request.
- Manual `refresh()` (header button) shares the same fetch path as the polling tick (per spec §4.1.2).
- The `umo` is read from `useSpcodeProjectStatus().status.value.umo` at fetch time.

- [ ] **Step 3.1: Define the composable interface and stub**

Create `dashboard/src/composables/useSpcodeGitDiff.ts`:

```typescript
// Author: elecvoid243
// Date: 2026-06-17
// Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.1.2

import { ref, type Ref } from 'vue'
import { pluginExtensionApi } from '@/api/v1'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'
import {
  parseSpcodeGitDiff,
  type SpcodeGitDiffSnapshot,
  type SpcodeGitDiffRawResponse,
} from '@/composables/parseSpcodeGitDiff'

export type GitDiffFetchState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ok'; snapshot: SpcodeGitDiffSnapshot }
  | { kind: 'error'; reason: string; previousSnapshot?: SpcodeGitDiffSnapshot }

export interface UseSpcodeGitDiff {
  state: Ref<GitDiffFetchState>
  refresh: () => Promise<void>
  startPolling: (intervalMs?: number) => void
  stopPolling: () => void
  dispose: () => void
}

interface ApiEnvelope {
  status: string
  data?: SpcodeGitDiffRawResponse
  message?: string
}

const DEFAULT_POLL_MS = 10_000

export function useSpcodeGitDiff(): UseSpcodeGitDiff {
  const state = ref<GitDiffFetchState>({ kind: 'idle' })
  const spcodeStatus = useSpcodeProjectStatus()
  let abortController: AbortController | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let isMounted = true

  async function refresh(): Promise<void> {
    if (!isMounted) return
    // Per-instance contract: each useSpcodeGitDiff() call owns its own closure
    // (isMounted, abortController, pollTimer). The Chunk 2 GitDiffSidebar
    // instantiates this once per <mount> and calls dispose() in onBeforeUnmount.
    // Do NOT export a module-level singleton; the composable is per-component.
    const umo = spcodeStatus.status.value.umo
    if (!umo) {
      // Note: spec §4.1.2 originally listed 'not_loaded', but i18n key list
      // (spec §5.1.1) only has 'no_project_loaded'. Use the i18n-covered
      // value to keep the UI renderable.
      const prev = state.value.kind === 'ok' ? state.value.snapshot : undefined
      state.value = { kind: 'error', reason: 'no_project_loaded', previousSnapshot: prev }
      return
    }
    abortController?.abort()
    abortController = new AbortController()
    const isFirst = state.value.kind !== 'ok'
    if (isFirst) state.value = { kind: 'loading' }
    try {
      const resp = await pluginExtensionApi.get<ApiEnvelope>('spcode/git-diff', {
        params: { umo },
        signal: abortController.signal,
      })
      if (!isMounted) return
      const data = resp.data?.data
      if (!data) throw new Error('empty response data')
      state.value = { kind: 'ok', snapshot: parseSpcodeGitDiff(data) }
    } catch (err) {
      if (!isMounted) return
      if ((err as { name?: string })?.name === 'CanceledError') return
      const prev = state.value.kind === 'ok' ? state.value.snapshot : undefined
      state.value = {
        kind: 'error',
        reason: classifyError(err),
        previousSnapshot: prev,
      }
    }
  }

  function startPolling(intervalMs: number = DEFAULT_POLL_MS): void {
    if (pollTimer) return
    pollTimer = setInterval(() => {
      void refresh()
    }, intervalMs)
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function dispose(): void {
    isMounted = false
    stopPolling()
    abortController?.abort()
    abortController = null
  }

  return { state, refresh, startPolling, stopPolling, dispose }
}

function classifyError(err: unknown): string {
  if (typeof err === 'object' && err !== null) {
    const anyErr = err as { code?: string; message?: string }
    if (anyErr.code === 'ERR_NETWORK' || /network/i.test(anyErr.message ?? '')) {
      return 'network'
    }
  }
  return 'unknown'
}
```

- [ ] **Step 3.2: Verify imports resolve and typecheck passes**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm typecheck
```

Expected: PASS. If `pluginExtensionApi` import path differs, check `dashboard/src/api/v1.ts` for the exact named export (used in sister spec; may be a function or an object with `.get`).

- [ ] **Step 3.3: Run lint**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm lint
```

Expected: PASS. If lint flags the unused `ApiEnvelope.message` field or any `any` cast, tighten the types (e.g., remove `message` from the type or use `unknown`).

- [ ] **Step 3.4: Commit**

```bash
cd F:\github\Astrbot-git-diff-sidebar
git add dashboard/src/composables/useSpcodeGitDiff.ts
git commit -m "feat(chatui): add useSpcodeGitDiff composable"
```

---

## Chunk 2: Components (FileItem → BodyContent → Sidebar)

### Task 4: `GitDiffFileItem` — single file row + collapsible body

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue`

**Context:**
- Leaf component, no dependencies on other new components.
- Props: `file: SpcodeGitDiffFile`, `expanded: boolean`, `isDark: boolean`.
- Emits: `toggle: []` (no payload — parent's `expanded` set is keyed by path).
- Three body branches (per spec §4.2.4):
  - `isBinary` → `<v-alert>` with `binaryFile` i18n key
  - `slice` non-null → `<DiffPreview :content="file.slice" :file-path="file.path" :collapsible="false" :is-dark="isDark" />` (pass `false` so DiffPreview doesn't render its own collapsible header — outer row owns path + chevron)
  - `slice=null && !isBinary` → "无内容" placeholder using `diffSidebar.noContent` i18n key
- Status icon/color mapping (spec §4.2.5): M / A / D / R / C / T / unknown.
- Emits `toggle` on row click. Chevron rotates on `expanded`.

- [ ] **Step 4.1: Stub the component**

Create `dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue`:

```vue
<!-- Author: elecvoid243, 2026-06-17 -->
<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.4 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { SpcodeGitDiffFile, FileStatus } from '@/composables/parseSpcodeGitDiff'
import { useModuleI18n } from '@/i18n/composables'
import DiffPreview from '@/components/chat/message_list_comps/DiffPreview.vue'

const { tm } = useModuleI18n('features/chat')

const props = defineProps<{
  file: SpcodeGitDiffFile
  expanded: boolean
  isDark: boolean
}>()
const emit = defineEmits<{ (e: 'toggle'): void }>()

const ICON_MAP: Record<FileStatus, { icon: string; color: string }> = {
  M: { icon: 'mdi-pencil', color: 'primary' },
  A: { icon: 'mdi-plus-circle', color: 'success' },
  D: { icon: 'mdi-minus-circle', color: 'error' },
  R: { icon: 'mdi-rename-box', color: 'warning' },
  C: { icon: 'mdi-content-copy', color: 'info' },
  T: { icon: 'mdi-swap-horizontal', color: 'info' },
  unknown: { icon: 'mdi-file-document-edit-outline', color: 'grey' },
}
const iconInfo = computed(() => ICON_MAP[props.file.status])
</script>

<template>
  <div class="git-diff-file-item" :class="{ expanded: expanded }">
    <button type="button" class="git-diff-file-row" @click="emit('toggle')">
      <v-icon :size="16" :color="iconInfo.color">{{ iconInfo.icon }}</v-icon>
      <span class="git-diff-file-path">{{ file.path }}</span>
      <span class="git-diff-file-stats">
        <span class="git-diff-add">+{{ file.additions }}</span>
        <span class="git-diff-del">−{{ file.deletions }}</span>
      </span>
      <v-icon
        :size="16"
        class="git-diff-file-chevron"
        :class="{ expanded: expanded }"
      >mdi-chevron-down</v-icon>
    </button>
    <div v-if="expanded" class="git-diff-file-body">
      <v-alert v-if="file.isBinary" type="info" density="compact" variant="tonal">
        {{ tm('spcodeProjectLoad.diffSidebar.binaryFile') }}
      </v-alert>
      <DiffPreview
        v-else-if="file.slice"
        :content="file.slice"
        :file-path="file.path"
        :collapsible="false"
        :is-dark="isDark"
      />
      <div v-else class="git-diff-file-no-content">
        {{ tm('spcodeProjectLoad.diffSidebar.noContent') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.git-diff-file-item { border-bottom: 1px solid rgba(0, 0, 0, 0.08); }
.git-diff-file-row {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 8px 12px;
  background: transparent; border: none; cursor: pointer; text-align: left;
}
.git-diff-file-row:hover { background: rgba(0, 0, 0, 0.04); }
.git-diff-file-path {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-family: monospace; font-size: 13px;
}
.git-diff-file-stats { display: flex; gap: 6px; font-family: monospace; font-size: 12px; }
.git-diff-add { color: rgb(46, 160, 67); }
.git-diff-del { color: rgb(248, 81, 73); }
.git-diff-file-chevron { transition: transform 0.15s; }
.git-diff-file-chevron.expanded { transform: rotate(180deg); }
.git-diff-file-body { padding: 0 12px 12px; }
.git-diff-file-no-content {
  padding: 12px; text-align: center; color: rgba(0, 0, 0, 0.45); font-size: 12px;
}
</style>
```

- [ ] **Step 4.2: Verify typecheck and lint**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm typecheck && pnpm lint
```

Expected: PASS. If lint complains about the `mdi-pencil` etc. icon string literals, ensure the project's ESLint config allows vuetify icon names.

- [ ] **Step 4.3: Commit**

```bash
cd F:\github\Astrbot-git-diff-sidebar
git add dashboard/src/components/chat/message_list_comps/GitDiffFileItem.vue
git commit -m "feat(chatui): add GitDiffFileItem component"
```

---

### Task 5: `GitDiffBodyContent` — state-machine renderer

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue`

**Context:**
- Pure renderer, no state, no HTTP. Takes `state` from the composable + `expanded` Set of paths + `isDark` flag.
- Renders one of 5 branches (spec §4.2.3):
  1. `state.kind === 'loading'` → centered spinner + `loading` i18n
  2. `state.kind === 'error' && !previousSnapshot` → centered error block + retry button
  3. `state.kind === 'ok' && files.length === 0` → centered empty state
  4. `state.kind === 'ok' && files.length > 0` → list of `<GitDiffFileItem>` + (if `error` with `previousSnapshot`) bottom error banner
  5. Branch 2 and 4 logic should combine correctly (see template below)
- Emits: `toggle: [path: string]`, `retry: []`.

- [ ] **Step 5.1: Stub the component**

Create `dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue`:

```vue
<!-- Author: elecvoid243, 2026-06-17 -->
<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.3 -->
<script setup lang="ts">
import { computed } from 'vue'
import type { GitDiffFetchState } from '@/composables/useSpcodeGitDiff'
import { useModuleI18n } from '@/i18n/composables'
import GitDiffFileItem from '@/components/chat/message_list_comps/GitDiffFileItem.vue'

const { tm } = useModuleI18n('features/chat')

const props = defineProps<{
  state: GitDiffFetchState
  expanded: Set<string>
  isDark: boolean
}>()
const emit = defineEmits<{
  (e: 'toggle', path: string): void
  (e: 'retry'): void
}>()

const REASON_I18N_KEYS: Record<string, string> = {
  feature_disabled: 'spcodeProjectLoad.diffSidebar.error.reason.feature_disabled',
  no_project_loaded: 'spcodeProjectLoad.diffSidebar.error.reason.no_project_loaded',
  directory_missing: 'spcodeProjectLoad.diffSidebar.error.reason.directory_missing',
  not_a_git_repo: 'spcodeProjectLoad.diffSidebar.error.reason.not_a_git_repo',
  git_unavailable: 'spcodeProjectLoad.diffSidebar.error.reason.git_unavailable',
  git_error: 'spcodeProjectLoad.diffSidebar.error.reason.git_error',
}

function localizedReason(reason: string): string {
  const key = REASON_I18N_KEYS[reason]
  if (key) return tm(key)
  if (reason === 'network') return tm('spcodeProjectLoad.diffSidebar.error.networkTitle')
  return tm('spcodeProjectLoad.diffSidebar.error.reason.generic', { reason })
}

const errorInfo = computed(() => {
  if (props.state.kind !== 'error') return null
  return { reason: props.state.reason, hasPrevious: !!props.state.previousSnapshot }
})

const files = computed(() =>
  props.state.kind === 'ok' || (props.state.kind === 'error' && props.state.previousSnapshot)
    ? (props.state.kind === 'ok' ? props.state.snapshot.files : props.state.previousSnapshot!.files)
    : []
)
</script>

<template>
  <!-- Branch 1: loading -->
  <div v-if="state.kind === 'loading'" class="git-diff-center">
    <v-progress-circular indeterminate :size="32" />
    <span class="git-diff-center-text">{{ tm('spcodeProjectLoad.diffSidebar.loading') }}</span>
  </div>

  <!-- Branch 2: error with no previous -->
  <div
    v-else-if="state.kind === 'error' && !state.previousSnapshot && errorInfo"
    class="git-diff-center"
  >
    <v-icon size="36" color="error">mdi-alert-circle-outline</v-icon>
    <div class="git-diff-error-title">{{ tm('spcodeProjectLoad.diffSidebar.error.loadFailedTitle') }}</div>
    <div class="git-diff-error-detail">{{ localizedReason(errorInfo.reason) }}</div>
    <v-btn size="small" color="primary" @click="emit('retry')">
      {{ tm('spcodeProjectLoad.diffSidebar.error.retry') }}
    </v-btn>
  </div>

  <!-- Branch 3 & 4: success (or success with stale error) -->
  <template v-else-if="state.kind === 'ok' || (state.kind === 'error' && state.previousSnapshot)">
    <div v-if="files.length === 0" class="git-diff-center">
      <v-icon size="36" color="grey">mdi-check-circle-outline</v-icon>
      <span class="git-diff-center-text">{{ tm('spcodeProjectLoad.diffSidebar.empty') }}</span>
    </div>
    <GitDiffFileItem
      v-for="f in files"
      :key="f.path + ':' + f.status"
      :file="f"
      :expanded="expanded.has(f.path)"
      :is-dark="isDark"
      @toggle="emit('toggle', f.path)"
    />
    <div v-if="state.kind === 'error' && errorInfo" class="git-diff-banner-error">
      <span>{{ localizedReason(errorInfo.reason) }}</span>
      <button class="git-diff-banner-retry" @click="emit('retry')">
        {{ tm('spcodeProjectLoad.diffSidebar.error.retry') }}
      </button>
    </div>
  </template>

  <!-- Branch 5: idle (initial state, no fetch yet) -->
  <div v-else class="git-diff-center">
    <span class="git-diff-center-text">{{ tm('spcodeProjectLoad.diffSidebar.loading') }}</span>
  </div>
</template>

<style scoped>
.git-diff-center {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 12px; padding: 32px 16px; min-height: 200px;
}
.git-diff-center-text { color: rgba(0, 0, 0, 0.6); font-size: 14px; }
.git-diff-error-title { font-weight: 600; font-size: 15px; }
.git-diff-error-detail { color: rgba(0, 0, 0, 0.6); font-size: 13px; text-align: center; }
.git-diff-banner-error {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 8px 12px; margin: 8px 12px;
  background: rgba(248, 81, 73, 0.1); border-radius: 4px;
  font-size: 12px; color: rgb(248, 81, 73);
}
.git-diff-banner-retry {
  background: transparent; border: 1px solid currentColor;
  border-radius: 4px; padding: 2px 8px; cursor: pointer; color: inherit;
}
</style>
```

- [ ] **Step 5.2: Verify typecheck and lint**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm typecheck && pnpm lint
```

Expected: PASS. The `state.previousSnapshot!` non-null assertion is already guarded by the v-else-if `state.previousSnapshot` check, so it's safe; lint may still flag — replace with explicit guard if so.

- [ ] **Step 5.3: Commit**

```bash
cd F:\github\Astrbot-git-diff-sidebar
git add dashboard/src/components/chat/message_list_comps/GitDiffBodyContent.vue
git commit -m "feat(chatui): add GitDiffBodyContent component"
```

---

### Task 6: `GitDiffSidebar` — outer shell with polling lifecycle

**Files:**
- Create: `dashboard/src/components/chat/GitDiffSidebar.vue`

**Context:**
- Mirrors `ReasoningSidebar.vue` structure: slide-left transition, drag resizer, header, body.
- Owns the `useSpcodeGitDiff()` composable instance. Mounts it once per component instance; disposes on unmount.
- Watches `props.modelValue` (v-model):
  - `false → true`: call `refresh()` then `startPolling(10_000)`.
  - `true → false`: call `stopPolling()`.
- Watches `useSpcodeProjectStatus().status.value.loaded`:
  - `true → false`: emit `update:modelValue false` (auto-close on unload).
- Default width 420, MIN 320, MAX 1200. Mobile <760px: full-screen overlay (use existing media query pattern from `ReasoningSidebar`).
- Truncation warning: shown when `state.snapshot.meta.truncated === true`.
- Refresh button in header: calls `composable.refresh()`; shows loading state via `state.kind === 'loading' || (state.kind === 'ok' && Date.now() - state.snapshot.meta.fetchedAt < 200)` — but simplest: tie loading indicator to whether the most recent refresh is in-flight. Per spec §4.2.2, header refresh button uses `v-btn :loading` and `:disabled` while a fetch is running. To keep state minimal, use a separate local `Ref<boolean>` for `isFetching`.

- [ ] **Step 6.1: Implement the shell (slide transition, drag resizer, header, body, truncation warning, mobile overlay)**

Create `dashboard/src/components/chat/GitDiffSidebar.vue` with the template, script setup, and styles. The structure follows `ReasoningSidebar.vue` exactly. Width 420 default, MIN 320, MAX 1200.

```vue
<!-- Author: elecvoid243, 2026-06-17 -->
<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.2 -->
<script setup lang="ts">
import { ref, watch, onBeforeUnmount, computed } from 'vue'
import { useSpcodeGitDiff } from '@/composables/useSpcodeGitDiff'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'
import { useModuleI18n } from '@/i18n/composables'
import GitDiffBodyContent from '@/components/chat/message_list_comps/GitDiffBodyContent.vue'

const { tm } = useModuleI18n('features/chat')
const props = defineProps<{
  modelValue: boolean
  isDark?: boolean
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const composable = useSpcodeGitDiff()
const spcodeStatus = useSpcodeProjectStatus()
const expandedSet = ref<Set<string>>(new Set())

const isFetching = ref(false)
async function onManualRefresh(): Promise<void> {
  if (isFetching.value) return
  isFetching.value = true
  try { await composable.refresh() } finally { isFetching.value = false }
}

watch(() => props.modelValue, async (open) => {
  if (open) {
    isFetching.value = true
    try { await composable.refresh() } finally { isFetching.value = false }
    composable.startPolling(10_000)
  } else {
    composable.stopPolling()
  }
}, { immediate: true })

watch(() => spcodeStatus.status.value.loaded, (loaded) => {
  if (!loaded) emit('update:modelValue', false)
})

onBeforeUnmount(() => composable.dispose())

function toggleFile(path: string): void {
  const next = new Set(expandedSet.value)
  if (next.has(path)) next.delete(path); else next.add(path)
  expandedSet.value = next
}

const MIN_WIDTH = 320
const MAX_WIDTH = 1200
const DEFAULT_WIDTH = 420
const sidebarWidth = ref(DEFAULT_WIDTH)
const isResizing = ref(false)

function startResize(e: MouseEvent): void {
  isResizing.value = true
  const startX = e.clientX
  const startW = sidebarWidth.value
  const onMove = (ev: MouseEvent): void => {
    const next = startW + (ev.clientX - startX)
    sidebarWidth.value = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, next))
  }
  const onUp = (): void => {
    isResizing.value = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

const directoryPath = computed(() => {
  const s = composable.state.value
  if (s.kind === 'ok') return s.snapshot.meta.directory
  if (s.kind === 'error' && s.previousSnapshot) return s.previousSnapshot.meta.directory
  return null
})

const isTruncated = computed(() => {
  const s = composable.state.value
  if (s.kind === 'ok') return s.snapshot.meta.truncated
  if (s.kind === 'error' && s.previousSnapshot) return s.previousSnapshot.meta.truncated
  return false
})

const truncatedShown = computed(() => {
  const s = composable.state.value
  if (s.kind === 'ok') return s.snapshot.meta.truncatedAtBytes
  if (s.kind === 'error' && s.previousSnapshot) return s.previousSnapshot.meta.truncatedAtBytes
  return 0
})

const truncatedMax = computed(() => {
  const s = composable.state.value
  if (s.kind === 'ok') return s.snapshot.meta.maxBytes
  if (s.kind === 'error' && s.previousSnapshot) return s.previousSnapshot.meta.maxBytes
  return 0
})
</script>

<template>
  <transition name="slide-left">
    <aside
      v-if="modelValue"
      class="git-diff-sidebar"
      :class="{ resizing: isResizing }"
      :style="{ width: sidebarWidth + 'px' }"
    >
      <div class="git-diff-sidebar-resizer" @mousedown.prevent="startResize" />
      <div class="git-diff-sidebar-header">
        <div class="git-diff-sidebar-title-wrap">
          <span class="git-diff-sidebar-title">
            {{ tm('spcodeProjectLoad.diffSidebar.title') }}
          </span>
          <v-tooltip v-if="directoryPath" location="bottom" :open-delay="200">
            <template #activator="{ props: tipProps }">
              <v-icon
                v-bind="tipProps"
                size="14"
                class="git-diff-sidebar-dir-icon"
              >mdi-folder-outline</v-icon>
            </template>
            <span class="git-diff-sidebar-dir">{{ directoryPath }}</span>
          </v-tooltip>
        </div>
        <div class="git-diff-sidebar-actions">
          <v-btn
            icon="mdi-refresh"
            size="small"
            variant="text"
            :loading="isFetching"
            @click="onManualRefresh"
          >
            <v-tooltip activator="parent" location="bottom" :open-delay="200">
              {{ tm('spcodeProjectLoad.diffSidebar.refreshTooltip') }}
            </v-tooltip>
          </v-btn>
          <v-btn
            icon="mdi-close"
            size="small"
            variant="text"
            @click="emit('update:modelValue', false)"
          />
        </div>
      </div>
      <div v-if="isTruncated" class="git-diff-sidebar-warning">
        {{ tm('spcodeProjectLoad.diffSidebar.truncated', { shown: truncatedShown, max: truncatedMax }) }}
      </div>
      <div class="git-diff-sidebar-body">
        <GitDiffBodyContent
          :state="composable.state.value"
          :expanded="expandedSet"
          :is-dark="!!isDark"
          @toggle="toggleFile"
          @retry="onManualRefresh"
        />
      </div>
    </aside>
  </transition>
</template>

<style scoped>
.git-diff-sidebar {
  position: fixed; top: 0; right: 0; bottom: 0;
  background: var(--v-theme-surface);
  border-left: 1px solid rgba(0, 0, 0, 0.12);
  display: flex; flex-direction: column; z-index: 1000;
}
.git-diff-sidebar.resizing { transition: none; user-select: none; }
.git-diff-sidebar-resizer {
  position: absolute; top: 0; left: -3px; width: 6px; height: 100%;
  cursor: col-resize; z-index: 1;
}
.git-diff-sidebar-resizer:hover { background: rgba(0, 0, 0, 0.04); }
.git-diff-sidebar-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 12px 12px 16px; border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
}
.git-diff-sidebar-title-wrap { display: flex; align-items: center; gap: 6px; }
.git-diff-sidebar-title { font-weight: 600; font-size: 15px; }
.git-diff-sidebar-dir-icon { color: rgba(0, 0, 0, 0.45); }
.git-diff-sidebar-dir { font-family: monospace; font-size: 12px; }
.git-diff-sidebar-actions { display: flex; gap: 4px; }
.git-diff-sidebar-warning {
  padding: 8px 16px; background: rgba(255, 193, 7, 0.12);
  color: rgb(255, 152, 0); font-size: 12px; border-bottom: 1px solid rgba(255, 193, 7, 0.3);
}
.git-diff-sidebar-body { flex: 1; overflow-y: auto; }
.slide-left-enter-active, .slide-left-leave-active { transition: transform 0.2s; }
.slide-left-enter-from, .slide-left-leave-to { transform: translateX(100%); }

@media (max-width: 760px) {
  .git-diff-sidebar {
    position: fixed; inset: 0; width: 100vw !important;
    border-left: 0; z-index: 1300;
  }
  .git-diff-sidebar-resizer { display: none; }
  .git-diff-sidebar-header { padding-top: calc(12px + env(safe-area-inset-top)); }
  .git-diff-sidebar-body { padding-bottom: env(safe-area-inset-bottom); }
}
</style>
```

- [ ] **Step 6.2: Verify typecheck and lint**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm typecheck && pnpm lint
```

Expected: PASS. If lint complains about the `ev` parameter shadowing `e` in the resize handler, rename to `ev`.

- [ ] **Step 6.3: Commit**

```bash
cd F:\github\Astrbot-git-diff-sidebar
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(chatui): add GitDiffSidebar shell with polling lifecycle"
```

---

## Chunk 3: Integration (Chip → ChatInput → Chat.vue → final)

### Task 7: `GitDiffChip` outlined v-chip

**Files:**
- Create: `dashboard/src/components/chat/GitDiffChip.vue`

**Context:**
- Outlined v-chip with `mdi-source-pull` icon and tooltip. Emits `open-diff-sidebar`.
- ~30 lines. Leaf component, no deps on other new code.
- Visibility is **NOT** owned by this component — it is gated in `ChatInput.vue` (per spec §4.2.1).

- [ ] **Step 7.1: Create the component**

Create `dashboard/src/components/chat/GitDiffChip.vue`:

```vue
<!-- Author: elecvoid243, 2026-06-17 -->
<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.1 -->
<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables'
const { tm } = useModuleI18n('features/chat')
const emit = defineEmits<{ (e: 'open-diff-sidebar'): void }>()
function open(): void { emit('open-diff-sidebar') }
</script>

<template>
  <v-tooltip location="bottom" :open-delay="200">
    <template #activator="{ props: tipProps }">
      <v-chip
        v-bind="tipProps"
        variant="outlined"
        size="small"
        density="comfortable"
        prepend-icon="mdi-source-pull"
        class="git-diff-chip"
        @click="open"
      >
        {{ tm('spcodeProjectLoad.diffSidebar.chip') }}
      </v-chip>
    </template>
    <span>{{ tm('spcodeProjectLoad.diffSidebar.chipTooltip') }}</span>
  </v-tooltip>
</template>

<style scoped>
.git-diff-chip { cursor: pointer; }
</style>
```

- [ ] **Step 7.2: Verify typecheck and lint**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm typecheck && pnpm lint
```

Expected: PASS.

- [ ] **Step 7.3: Commit**

```bash
cd F:\github\Astrbot-git-diff-sidebar
git add dashboard/src/components/chat/GitDiffChip.vue
git commit -m "feat(chatui): add GitDiffChip outlined chip"
```

---

### Task 8: Wire `GitDiffChip` into `ChatInput.vue` status row

**Files:**
- Modify: `dashboard/src/components/chat/ChatInput.vue`

**Context:**
- `ChatInput.vue` already has a status-row that renders `<SpcodeProjectIndicator/>`. The new chip goes **next to** it (right-aligned via `justify-content: space-between`).
- `ChatInput.vue` already imports `useSpcodeProjectStatus()` (line 1064 per spec §4.2.1). The chip's `v-if` reads `spcodeStatus.status.value.loaded`.
- Need to add `'open-diff-sidebar'` to the `defineEmits` block (currently lines 408-422).
- Need to import `GitDiffChip.vue`.

- [ ] **Step 8.1: Add `'open-diff-sidebar'` to the defineEmits block**

Open `dashboard/src/components/chat/ChatInput.vue` and locate the `defineEmits<{...}>()` block. Add a new entry: `(e: 'open-diff-sidebar'): void`.

Find the existing `defineEmits<{` block (search for `open-load-dialog` or `update:prompt` to locate it). The file uses Vue 3.3+ object syntax (`{ "event-name": [argType] }`); preserve that style. Add a new key:

```typescript
const emit = defineEmits<{
  // ... existing entries ...
  'open-load-dialog': []
  'open-diff-sidebar': []   // <-- new
}>()
```

If the file uses the older tuple syntax (`(e: 'x'): void`), add a new tuple line: `(e: 'open-diff-sidebar'): void`. Match the file's actual style.

- [ ] **Step 8.2: Import `GitDiffChip`**

Add at the top of `<script setup>` (near other component imports):
```typescript
import GitDiffChip from '@/components/chat/GitDiffChip.vue'
```

- [ ] **Step 8.3: Update the status-row markup**

Find the existing status-row element (search for `<SpcodeProjectIndicator` or `input-area__status-row`). Change the wrapping element's CSS class to add `space-between` and append the new chip:

```vue
<div class="input-area__status-row">
  <SpcodeProjectIndicator
    v-if="showSpcodeIndicator"
    @open-load-dialog="openLoadDialog"
  />
  <GitDiffChip
    v-if="showSpcodeIndicator && spcodeStatus.status.value.loaded"
    @open-diff-sidebar="emit('open-diff-sidebar')"
  />
</div>
```

If the existing CSS for `.input-area__status-row` is `display: flex; gap: ...` (no justify), update it to add `justify-content: space-between;` either in the same file or in the scoped style. The minimal change is to add the property to the existing rule. Alternatively, add a one-off style: `style="justify-content: space-between"`.

- [ ] **Step 8.4: Verify typecheck and lint**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm typecheck && pnpm lint
```

Expected: PASS. If `tsc` reports `spcodeStatus is not defined`, check that the import is already present (it is per spec §4.2.1 + sister spec).

- [ ] **Step 8.5: Manual visual check via dev server**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm dev
```

Open the dashboard in a browser, load any spcode project (e.g., via `/project load <path>`), and confirm the new `Git Diff` chip appears in the status row, right of the existing project indicator. Click the chip — nothing visible happens yet because `GitDiffSidebar` is not mounted (Task 9).

- [ ] **Step 8.6: Commit**

```bash
cd F:\github\Astrbot-git-diff-sidebar
git add dashboard/src/components/chat/ChatInput.vue
git commit -m "feat(chatui): wire GitDiffChip into ChatInput status row"
```

---

### Task 9: Mount `GitDiffSidebar` in `Chat.vue` with mutual exclusion

**Files:**
- Modify: `dashboard/src/components/chat/Chat.vue`

**Context:**
- `Chat.vue` already has patterns for `ReasoningSidebar`, `RefsSidebar`, `TodoSidebar` (per spec §3.4). Add `GitDiffSidebar` to the same pattern.
- Need: import, ref, openGitDiffSidebar() helper, template mount, currSessionId watcher line.
- Mutual exclusion: openGitDiffSidebar closes all other sidebars.

- [ ] **Step 9.1: Import `GitDiffSidebar`**

Add to the existing import block (near other sidebar imports):
```typescript
import GitDiffSidebar from '@/components/chat/GitDiffSidebar.vue'
```

- [ ] **Step 9.2: Add `gitDiffSidebarOpen` ref**

Find the existing sidebar ref declarations (e.g., `const reasoningPanelOpen = ref(false)`, `const refsSidebarOpen = ref(false)`, `const todoSidebarOpen = ref(false)`). Add:
```typescript
const gitDiffSidebarOpen = ref(false)
```

- [ ] **Step 9.3: Add `openGitDiffSidebar()` helper**

Find the existing `openXxxPanel()` helpers (e.g., `openReasoningPanel`, `openRefsSidebar`). Add an analogous function:

```typescript
function openGitDiffSidebar(): void {
  threadPanelOpen.value = false
  activeThread.value = null
  reasoningPanelOpen.value = false
  activeReasoningTarget.value = null
  refsSidebarOpen.value = false
  selectedRefs.value = null
  todoSidebarOpen.value = false
  gitDiffSidebarOpen.value = true
}
```

(Adjust ref names to match the actual file. The `threadPanelOpen` / `activeThread` / `activeReasoningTarget` / `selectedRefs` / `todoSidebarOpen` references are based on the existing pattern from `Chat.vue`. Verify with `grep "ref<" Chat.vue`.)

- [ ] **Step 9.4: Mount `<GitDiffSidebar>` in the template**

Find the existing sidebar mounts (e.g., `<ReasoningSidebar v-model="reasoningPanelOpen" />`, `<RefsSidebar v-model="refsSidebarOpen" />`, `<TodoSidebar v-model="todoSidebarOpen" />`). Add:
```vue
<GitDiffSidebar v-model="gitDiffSidebarOpen" />
```

Adjust props: if `isDark` is passed to other sidebars, also pass it. Check `ReasoningSidebar` usage in `Chat.vue` template for the prop list.

- [ ] **Step 9.5: Hook up the chip's `open-diff-sidebar` event**

Find the `<ChatInput>` usage in `Chat.vue` template and ensure its emits include `open-diff-sidebar` (or that there's a generic event listener). Add `@open-diff-sidebar="openGitDiffSidebar"` to the `<ChatInput>` element. If `ChatInput` doesn't currently emit `open-diff-sidebar` (it's added in Task 8), the listener just won't fire — the chip will appear but clicking it does nothing. This step ensures the listener is in place.

- [ ] **Step 9.6: Add `currSessionId` watcher for auto-close**

Find the existing `watch(currSessionId, ...)` (line 1066-1074 per spec §3.3) and add a `gitDiffSidebarOpen.value = false` line inside it. Be careful not to duplicate logic; the minimal addition is one line:

```typescript
watch(currSessionId, () => {
  // ... existing logic ...
  gitDiffSidebarOpen.value = false  // <-- new
})
```

> **E13 accuracy note:** Per reviewer's direct inspection of `Chat.vue:1063-1074`, the existing `currSessionId` watcher only calls `spcodeStatus.refresh()` and does **not** close `threadPanelOpen` / `reasoningPanelOpen` / `refsSidebarOpen` / `todoSidebarOpen`. So our new `gitDiffSidebarOpen.value = false` line is the **only** sidebar that closes on session switch. The spec's E13 wording "随其它 sidebar 一起关闭" is inaccurate — only the new git-diff sidebar will close. This is acceptable behavior for v1 (avoids touching unrelated panel-closing logic) but a future refactor could centralize it.

- [ ] **Step 9.7: Verify typecheck and lint**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm typecheck && pnpm lint
```

Expected: PASS. If TypeScript complains about the `selectedRefs` / `activeThread` / `activeReasoningTarget` names, adjust to match the actual file.

- [ ] **Step 9.8: Manual E2E smoke test**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm dev
```

Walk through spec §7.2 E1-E14 (at minimum E1, E2, E3, E6, E7, E8, E12, E13):

- E1: spcode plugin not enabled → no `Git Diff` chip
- E2: spcode enabled but no project loaded → no `Git Diff` chip
- E3: `/project load <git-repo-path>` → chip appears, click → sidebar opens, file list rendered
- E6: open sidebar, click reasoning button → sidebar closes (mutual exclusion)
- E7: `/project unload` → sidebar auto-closes, chip disappears
- E8: load non-git directory → chip visible, click → error reason shown
- E12: resize window to <760px → sidebar goes full-screen
- E13: switch to another session → sidebar closes

Capture any deviation and fix before continuing.

- [ ] **Step 9.9: Commit**

```bash
cd F:\github\Astrbot-git-diff-sidebar
git add dashboard/src/components/chat/Chat.vue
git commit -m "feat(chatui): mount GitDiffSidebar in Chat.vue with mutual exclusion"
```

---

### Task 10: Final lint + typecheck + CHANGELOG

**Files:**
- Create: `astrbot/changelogs/2026-06-17-chatui-git-diff-sidebar.md` (or whatever the project convention is — check `astrbot/changelogs/` for examples)

**Context:**
- The spec lists 10 commits in §7.3. Tasks 1-9 produced 9 commits (1-9). Task 10 is the cleanup / final commit.
- `pnpm lint` and `pnpm typecheck` should already pass after each task. This task confirms end-to-end.
- CHANGELOG entry summarizes the user-facing change.

- [ ] **Step 10.1: Full project typecheck and lint**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar
pnpm typecheck
cd dashboard && pnpm lint
```

Expected: BOTH PASS with no warnings or errors. If either fails, fix the issues and re-run.

- [ ] **Step 10.2: Run dashboard build to catch any production-build issues**

Run:
```bash
cd F:\github\Astrbot-git-diff-sidebar\dashboard
pnpm build
```

Expected: BUILD SUCCESS. Check the output for any tree-shaking warnings or dead-code paths related to the new composable / components.

- [ ] **Step 10.3: Add CHANGELOG entry**

**Project convention** (per direct repo check): `astrbot/changelogs/vX.Y.Z.md` (e.g., `v4.13.0.md`), headers in Chinese (`## What's Changed` / `### 新功能` / `### 修复` / `### 优化`). Determine the current dev version (run `cd astrbot && cat pyproject.toml | grep version` or check the most recent `changelogs/v*.md`) and use that exact version number. The filename **must** be `vX.Y.Z.md` — do not use date-based names.

Find an example to mirror format:
```bash
ls astrbot/changelogs/*.md | tail -5
cat astrbot/changelogs/$(ls astrbot/changelogs/ | sort -V | tail -1)
```

Append a new section in the same style. Use this skeleton (adapt headers to the file's existing format):

```markdown
### 新功能
- ChatUI：新增「Git Diff」侧边栏，列出当前已加载 spcode 项目的未暂存改动（文件状态图标、+/- 统计、可展开 unified diff、二进制文件占位、截断警告）。10s 静默轮询，卸载项目时自动关闭，移动端 <760px 全屏覆盖。
- ChatUI：新增 19 个 i18n 键（`spcodeProjectLoad.diffSidebar.*`）覆盖 zh-CN / en-US / ru-RU。

### 实现细节
- 新增组件：`GitDiffChip.vue`、`GitDiffSidebar.vue`、`GitDiffBodyContent.vue`、`GitDiffFileItem.vue`（4 个）。
- 新增 composable：`useSpcodeGitDiff`（状态机 + AbortController + 10s 轮询 + dispose）。
- 新增纯函数模块：`parseSpcodeGitDiff`（raw response → snapshot，diff 字符串切片、二进制检测、reason/status 兜底）。
- 复用现有 `DiffPreview.vue`、`useSpcodeProjectStatus.ts`、spcode `GET /spcode/git-diff` 端点（已存在于 spcode `main.py:1130-1135`）。
```

If a `vX.Y.Z.md` for the current dev version does **not** exist yet (pre-release), create it. If it exists, append a new section.

- [ ] **Step 10.4: Commit CHANGELOG**

```bash
cd F:\github\Astrbot-git-diff-sidebar
git add astrbot/changelogs/v<VERSION>.md   # replace <VERSION> with actual version
git commit -m "chore(changelog): chatui git diff sidebar"
```

- [ ] **Step 10.5: Commit this implementation plan to the feature branch (CRITICAL — do not skip)**

**Why:** The plan file at `F:\github\Astrbot-git-diff-sidebar\docs/superpowers/plans/2026-06-17-chatui-git-diff-sidebar.md` is currently uncommitted. If you later `git worktree remove` the worktree (e.g., during rollback), the plan file is **lost** — only the implementation code (merged to `all`) survives. Commit the plan so the feature branch carries the full history.

```bash
cd F:\github\Astrbot-git-diff-sidebar
git add docs/superpowers/plans/2026-06-17-chatui-git-diff-sidebar.md
git commit -m "docs(plan): include implementation plan for chatui git diff sidebar"
```

- [ ] **Step 10.6: Final typecheck + lint + build (re-run with deps installed)**

First-time build precondition (skip if already done in earlier tasks):

```bash
cd F:\github\Astrbot-git-diff-sidebar
pnpm install --frozen-lockfile   # only if node_modules is missing/stale
cd dashboard
pnpm install --frozen-lockfile   # only if dashboard/node_modules is missing/stale
```

Then:
```bash
pnpm typecheck && pnpm lint && pnpm build
```

Expected: ALL PASS. Fix any errors before continuing.

---

## Final Verification (after all tasks complete)

**All §7.2 E2E cases (E1-E14) must pass:**

| # | Scenario | Expected |
|---|---|---|
| E1 | spcode plugin not enabled | chip not shown |
| E2 | spcode enabled, no project loaded | chip not shown |
| E3 | `/project load <git-repo>` | chip appears, click → sidebar shows file list with directory tooltip |
| E4 | edit file in repo, wait 10s | list updates automatically |
| E5 | click header refresh button | immediate fetch, button briefly loading |
| E6 | sidebar open + click reasoning button | sidebar closes, reasoning opens |
| E7 | `/project unload` | sidebar auto-closes, chip disappears |
| E8 | load non-git directory | error reason displayed, retry button works |
| E9 | diff > 1MB | truncation warning at top of sidebar |
| E10 | modify a binary file | file row shows v-alert binary placeholder when expanded |
| E11 | disconnect network for 5s | no immediate error; after 10s tick, error banner at bottom; on reconnect, retry succeeds |
| E12 | window < 760px | sidebar full-screen overlay, resizer hidden |
| E13 | switch session | new git-diff sidebar closes (other sidebars retain current behavior; see Task 9 Step 9.6 E13 accuracy note) |
| E14 | switch to en-US / ru-RU | all 19 new keys render in correct language |

**All git commits (11 total, conventional commit format):**

> **Note:** Spec §7.3 lists 10 commits but bundles "add GitDiffChip + wire to ChatInput" into a single commit 7. The plan splits this into commits 7+8 for atomicity (each commit is independently revertable and reviewable). A separate commit 11 is added to include the plan file on the feature branch (preserves it through worktree removal).

1. `feat(i18n): add spcodeProjectLoad.diffSidebar keys (zh-CN/en-US/ru-RU)`
2. `feat(chatui): add parseSpcodeGitDiff pure function`
3. `feat(chatui): add useSpcodeGitDiff composable`
4. `feat(chatui): add GitDiffFileItem component`
5. `feat(chatui): add GitDiffBodyContent component`
6. `feat(chatui): add GitDiffSidebar shell with polling lifecycle`
7. `feat(chatui): add GitDiffChip outlined chip`
8. `feat(chatui): wire GitDiffChip into ChatInput status row`
9. `feat(chatui): mount GitDiffSidebar in Chat.vue with mutual exclusion`
10. `chore(changelog): chatui git diff sidebar`
11. `docs(plan): include implementation plan for chatui git diff sidebar`

**Push the branch:**
```bash
cd F:\github\Astrbot-git-diff-sidebar
git push origin feat/chatui-git-diff-sidebar
```

**Open a PR:**
- Title: `feat(chatui): add Git Diff sidebar for spcode project changes`
- Body: link to spec (`docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md`) + summary of 19-key i18n (17 from spec + 2 advisory: `noContent` + `loadFailedTitle`) + 4 new components + 1 composable + 1 parser. Note: spcode plugin unchanged, `DiffPreview.vue` unchanged, `useSpcodeProjectStatus.ts` unchanged. Note: E13 in spec wording ("其它 sidebar 一起关闭") is fiction — only the new git-diff sidebar closes on session switch; the other sidebars retain their current behavior.

---

## Rollback / Recovery

If any task in Chunks 1-3 fails irreversibly:
- Each commit is self-contained and revertable: `git revert <commit-hash>`
- The branch `feat/chatui-git-diff-sidebar` is isolated from `all` (the development branch). Reverting the entire branch is just deleting the worktree + branch: `git worktree remove F:\github\Astrbot-git-diff-sidebar && git branch -D feat/chatui-git-diff-sidebar`
- **Before `git worktree remove`**, ensure:
  1. The 11 commits have been merged to `all` (or pushed to `origin/feat/chatui-git-diff-sidebar` and a backup is made)
  2. Any working artifacts you want to keep (the plan markdown, WIP notes) have been copied out
  3. The plan markdown is committed (Step 10.5)
- i18n keys are additive (no existing keys modified); revert is safe.
- The 4 new components are all in the `chat/` subdir; no modifications to `DiffPreview.vue` / `useSpcodeProjectStatus.ts` / spcode plugin.
- If only a partial implementation is needed, revert the offending commits and push the rest. The plan's per-task structure means any subset is a valid stopping point.
