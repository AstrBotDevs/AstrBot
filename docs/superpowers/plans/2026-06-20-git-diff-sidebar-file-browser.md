# GitDiffSidebar File Browser Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Files view to the existing `GitDiffSidebar` that lets users browse the current spcode project's directory tree and preview files (Shiki-highlighted) using the new `GET /spcode/file-browser` endpoint. Files view binds to the active worktree; 4 UI states (viewMode, selectedWorktree, selectedScope, currentPath) persist to localStorage.

**Architecture:** Side-effect-free `parseSpcodeFileBrowser` raw-response → reactive `useSpcodeFileBrowser` state machine (no polling, on-demand fetch + AbortController) → four new Vue components (`FileBrowserView` shell + 3 sub-components: `FileBrowserBreadcrumb`, `FileBrowserEntryList`, `FileBrowserFilePreview`). `GitDiffSidebar` gets a view-mode tab pill (Files / Diff), worktree tabs lifted to top (visible in both views), and a 4-state localStorage persistence layer. Mirrors existing `useSpcodeGitDiff` lifecycle pattern (per-instance composable, `dispose()`, `isMounted` flag).

**Tech Stack:** Vue 3 Composition API (`<script setup>`), Vuetify 3 (`v-btn` / `v-icon` / `v-progress-circular`), TypeScript strict mode, i18next (`useModuleI18n` composable + dot-path keys), Shiki (`ensureShikiLanguages` + `renderShikiCode` from `dashboard/src/utils/shiki.js`), `pluginExtensionApi.get` (axios) for the `/spcode/file-browser` HTTP call.

**Spec:** `docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md`

**Sister specs (depends-on):**
- `docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md` — `GitDiffSidebar` base; we extend it
- `docs/superpowers/specs/2026-06-18-git-worktree-switcher-design.md` — `useSpcodeWorktrees` composable; we consume it
- `docs/superpowers/specs/2026-06-20-git-diff-scope-switcher-design.md` — `selectedScope` persistence; we add it
- `astrbot_plugin_spcode_toolkit/docs/superpowers/specs/2026-06-20-file-browser-endpoint-design.md` — backend contract; this plan consumes it

**Out-of-scope reminders (from spec §1.3):**
- ❌ No write operations, no recursive directory, no file search/filter, no multi-tab preview, no drag-upload/download
- ❌ No spcode plugin changes (endpoint is stable)
- ❌ No `DiffPreview.vue` / `shiki.js` / `useSpcodeProjectStatus.ts` / `useSpcodeWorktrees.ts` changes (only consume)
- ❌ No cross-tab storage event sync
- ❌ No Vitest (per spec §1.3; verified by `pnpm typecheck` + `pnpm lint` + manual E2E)

**Verification convention:** No Vitest. Each task verifies with `pnpm typecheck` (TypeScript compile) + `pnpm lint` (ESLint) inside `dashboard/`. End-of-plan: full spec §9 E2E checklist (90+ items) run manually in dev server.

---

## File Structure

### New files (6)

| File | Responsibility | Lines (est.) |
|---|---|---|
| `dashboard/src/composables/parseSpcodeFileBrowser.ts` | Pure function: raw `SpcodeFileBrowserRawResponse` → `SpcodeFileBrowserSnapshot`. Handles 3-state discrimination (directory / file / symlink), field normalization, sorting. Throws `FileBrowserParseError` when `data.type === null`. | ~150 |
| `dashboard/src/composables/useSpcodeFileBrowser.ts` | Composable: HTTP fetch + state machine (`idle / loading / directory / file / symlink / error`) + AbortController + `dispose()`. Auto-refreshes on `pathRef` change. Returns reactive `state`, `refresh`, `dispose`. **No polling** (on-demand only). | ~120 |
| `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue` | Main Files-view component. Layout shell (breadcrumb + two-pane). Owns `useSpcodeFileBrowser` instance. Forwards `navigate-target` and `retry` events from children. Renders placeholder when project not loaded. | ~130 |
| `dashboard/src/components/chat/message_list_comps/FileBrowserEntryList.vue` | Left pane: directory entries list (directory / file / symlink types with icons + size + mtime). Click navigates; dangling symlinks disabled. Renders `truncated` warning at top. | ~140 |
| `dashboard/src/components/chat/message_list_comps/FileBrowserBreadcrumb.vue` | Top breadcrumb: splits currentPath into clickable segments (root + intermediate + current). | ~80 |
| `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue` | Right pane: Shiki-highlighted file content + meta (path, size, mtime) + copy button. Handles 4 sub-states: loading / error (with retry) / directory (info-only) / symlink (target + "Go to target" button) / file (with binary/too-large fallbacks). | ~280 |

### Modified files (4)

| File | Change scope |
|---|---|
| `dashboard/src/components/chat/GitDiffSidebar.vue` | (a) Add view-mode tab pill (Files / Diff) at top. (b) Lift worktree tabs to a level visible in both views. (c) Conditionally render `<FileBrowserView>` vs `<GitDiffBodyContent>` based on `viewMode`. (d) Add 4-state localStorage persistence (`viewMode` / `selectedWorktree` / `selectedScope` / `fileBrowserCurrentPath`). (e) Validate persisted values on load. (f) Dispose `useSpcodeFileBrowser` in `onBeforeUnmount`. |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | Add 30 keys under `spcodeProjectLoad.fileBrowser.*` (per spec §7). |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | Same 30 keys, English values. |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | Same 30 keys, Russian values. |

### File ordering rationale
1. i18n keys first (other code references them; adding first means `pnpm typecheck` succeeds for the rest)
2. Pure parser next (no dependencies, self-contained)
3. Composable next (depends on parser types)
4. 3 leaf UI components (Breadcrumb → EntryList → FilePreview; no inter-dependency among them)
5. Main view (`FileBrowserView`; depends on the 3 leaves)
6. `GitDiffSidebar` integration (depends on main view + composable + localStorage)
7. Final lint + typecheck + manual E2E

### Conventional commit sequence (per sister spec §7.3 + spec advisory R9)
1. `feat(spcode-i18n): add fileBrowser keys to all 3 locales` — i18n keys
2. `feat(spcode-filebrowser): add parseSpcodeFileBrowser parser` — pure parser
3. `feat(spcode-filebrowser): add useSpcodeFileBrowser composable` — composable
4. `feat(spcode-filebrowser): add FileBrowserBreadcrumb component` — leaf
5. `feat(spcode-filebrowser): add FileBrowserEntryList component` — leaf
6. `feat(spcode-filebrowser): add FileBrowserFilePreview component` — leaf (Shiki integration)
7. `feat(spcode-filebrowser): add FileBrowserView container` — main view
8. `feat(spcode-sidebar): integrate Files view with view-mode tab + persistence` — GitDiffSidebar wiring
9. `chore(spcode-sidebar): verify lint + typecheck + manual E2E` — no code change

---

## Chunk 1: Data Layer (i18n keys + parser + composable)

### Task 1: Add 30 i18n keys to all three locales

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

**Context:**
- The 30 keys are listed in Steps 1.2 / 1.3 / 1.4. Copy the values verbatim into the existing `spcodeProjectLoad` object in each JSON, immediately after `spcodeProjectLoad.indicator` (or at end of `spcodeProjectLoad` if no `indicator`).
- Each locale JSON follows the existing flat dot-path convention. Use 2-space indentation, no trailing commas, ensure JSON is valid.
- The three locales must contain **the same set of keys** to avoid `tm()` falling back to key name at runtime.

- [ ] **Step 1.1: Locate the `spcodeProjectLoad` object** in each of the 3 JSON files

Run:
```bash
cd F:\github\Astrbot\dashboard
type src\i18n\locales\zh-CN\features\chat.json | findstr /n "spcodeProjectLoad"
type src\i18n\locales\en-US\features\chat.json | findstr /n "spcodeProjectLoad"
type src\i18n\locales\ru-RU\features\chat.json | findstr /n "spcodeProjectLoad"
```

Expected: each file shows the existing `spcodeProjectLoad` block with `menuItem`, `dialog.*`, `indicator.*` keys.

- [ ] **Step 1.2: Add 30 keys to `zh-CN/features/chat.json`**

Insert immediately after `spcodeProjectLoad.indicator`'s closing brace (or at end of `spcodeProjectLoad`):

```json
"fileBrowser": {
  "title": "工作区浏览",
  "viewMode": {
    "files": "工作区",
    "diff": "Git Diff"
  },
  "breadcrumbRoot": "项目根",
  "loading": "加载中…",
  "empty": "空目录",
  "placeholder": "请先加载项目",
  "truncated": "⚠ 列表已截断,仅显示前 1000 项",
  "entryType": {
    "directory": "文件夹",
    "file": "文件",
    "symlink": "符号链接",
    "dangling": "悬空链接"
  },
  "preview": {
    "selectFromLeft": "从左侧选择文件以预览",
    "binary": "二进制文件,无法预览",
    "tooLarge": "文件过大 ({size}),无法预览",
    "copy": "复制",
    "copySuccess": "已复制",
    "goToTarget": "前往目标"
  },
  "error": {
    "loadFailedTitle": "无法加载",
    "pathNotFound": "路径不存在",
    "permissionDenied": "权限不足",
    "specialFile": "特殊文件类型,无法预览",
    "network": "网络连接失败",
    "unknown": "加载失败 ({reason})",
    "retry": "重试"
  }
}
```

- [ ] **Step 1.3: Add 30 keys to `en-US/features/chat.json`**

```json
"fileBrowser": {
  "title": "Workspace Browser",
  "viewMode": {
    "files": "Files",
    "diff": "Git Diff"
  },
  "breadcrumbRoot": "Project root",
  "loading": "Loading…",
  "empty": "Empty directory",
  "placeholder": "Load a project first",
  "truncated": "⚠ Listing truncated, only the first 1000 items are shown",
  "entryType": {
    "directory": "Folder",
    "file": "File",
    "symlink": "Symbolic link",
    "dangling": "Dangling link"
  },
  "preview": {
    "selectFromLeft": "Select a file from the left to preview",
    "binary": "Binary file, preview unavailable",
    "tooLarge": "File too large ({size}), preview unavailable",
    "copy": "Copy",
    "copySuccess": "Copied",
    "goToTarget": "Go to target"
  },
  "error": {
    "loadFailedTitle": "Failed to load",
    "pathNotFound": "Path not found",
    "permissionDenied": "Permission denied",
    "specialFile": "Special file type, preview unavailable",
    "network": "Network error",
    "unknown": "Load failed ({reason})",
    "retry": "Retry"
  }
}
```

- [ ] **Step 1.4: Add 30 keys to `ru-RU/features/chat.json`**

```json
"fileBrowser": {
  "title": "Обзор рабочей области",
  "viewMode": {
    "files": "Файлы",
    "diff": "Git Diff"
  },
  "breadcrumbRoot": "Корень проекта",
  "loading": "Загрузка…",
  "empty": "Пустая директория",
  "placeholder": "Сначала загрузите проект",
  "truncated": "⚠ Список обрезан, показаны первые 1000 элементов",
  "entryType": {
    "directory": "Папка",
    "file": "Файл",
    "symlink": "Символическая ссылка",
    "dangling": "Битая ссылка"
  },
  "preview": {
    "selectFromLeft": "Выберите файл слева для предпросмотра",
    "binary": "Двоичный файл, предпросмотр недоступен",
    "tooLarge": "Файл слишком большой ({size}), предпросмотр недоступен",
    "copy": "Копировать",
    "copySuccess": "Скопировано",
    "goToTarget": "Перейти к цели"
  },
  "error": {
    "loadFailedTitle": "Не удалось загрузить",
    "pathNotFound": "Путь не найден",
    "permissionDenied": "Доступ запрещён",
    "specialFile": "Специальный тип файла, предпросмотр недоступен",
    "network": "Ошибка сети",
    "unknown": "Ошибка загрузки ({reason})",
    "retry": "Повторить"
  }
}
```

- [ ] **Step 1.5: Verify JSON validity**

Run (note: use forward slashes in the JS string literals — backslashes would be interpreted as JS escape characters):
```bash
cd F:\github\Astrbot\dashboard
for %f in (src/i18n/locales/zh-CN/features/chat.json src/i18n/locales/en-US/features/chat.json src/i18n/locales/ru-RU/features/chat.json) do node -e "JSON.parse(require('fs').readFileSync('%f', 'utf8')); console.log('%f OK');"
```

Expected: 3 lines, each ending in `OK`.

- [ ] **Step 1.6: Verify key parity**

Run:
```bash
cd F:\github\Astrbot\dashboard
node -e "const fs=require('fs');const get=(o,p)=>p.split('.').reduce((a,k)=>a&&a[k],o);for(const l of ['zh-CN','en-US','ru-RU']){const o=JSON.parse(fs.readFileSync('src/i18n/locales/'+l+'/features/chat.json','utf8'));const fb=get(o,'spcodeProjectLoad.fileBrowser');if(!fb){console.error(l+': missing fileBrowser');process.exit(1);}const keys=Object.keys(fb);console.log(l,keys.length,'keys');}"
```

Expected: 3 lines, each showing 10 top-level keys (`title`, `viewMode`, `breadcrumbRoot`, `loading`, `empty`, `placeholder`, `truncated`, `entryType`, `preview`, `error`).

- [ ] **Step 1.7: Commit i18n**

```bash
cd F:\github\Astrbot
git add dashboard/src/i18n/locales/zh-CN/features/chat.json dashboard/src/i18n/locales/en-US/features/chat.json dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "feat(spcode-i18n): add fileBrowser keys to all 3 locales"
```

---

### Task 2: Create `parseSpcodeFileBrowser.ts`

**Files:**
- Create: `dashboard/src/composables/parseSpcodeFileBrowser.ts`

**Context:** Pure function module. No Vue, no HTTP. Takes raw API response (`SpcodeFileBrowserRawResponse`) and returns discriminated union (`SpcodeFileBrowserSnapshot`). Throws `FileBrowserParseError` when `data.type === null` (true backend error). The composable (Task 3) catches this and converts to error state.

Reference the existing `parseSpcodeGitDiff.ts` for module style (TypeScript strict, exported types, exported function, JSDoc on top).

- [ ] **Step 2.1: Create the file with full type definitions + parser**

Create `dashboard/src/composables/parseSpcodeFileBrowser.ts` with the content below. Author: `elecvoid243, 2026-06-20`.

```typescript
// Author: elecvoid243, 2026-06-20
// Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.1
// Mirrors the file-browser endpoint contract:
// astrbot_plugin_spcode_toolkit/docs/superpowers/specs/2026-06-20-file-browser-endpoint-design.md §3.5

/**
 * Single directory entry: directory / file / symlink, three-state.
 * For symlink targets, the backend does NOT follow them — type stays
 * "symlink" regardless of what the target resolves to.
 */
export interface SpcodeFileBrowserEntry {
  /** Absolute path of this entry (round-trip from backend) */
  path: string;
  /** Basename (unencoded) */
  name: string;
  /** "directory" / "file" / "symlink" — backend explicitly does not follow symlinks */
  type: "directory" | "file" | "symlink";
  /** Bytes (null for directories; for symlinks, lstat size of the link itself) */
  size: number | null;
  /** mtime in unix seconds; null if lstat failed */
  mtime: number | null;
  /** True when type === "symlink" */
  is_symlink: boolean;
  /** symlink only: raw target string */
  target?: string;
  /** symlink only: whether the target exists (for "dangling" UI) */
  target_exists?: boolean;
}

export interface SpcodeFileBrowserDirectorySnapshot {
  meta: {
    path: string;
    entryCount: number;
    truncated: boolean;
    maxEntries: number;
    reason: string | null;
    elapsedMs: number;
    fetchedAt: number;
  };
  /** Sorted: directories → files → symlinks */
  entries: SpcodeFileBrowserEntry[];
}

export interface SpcodeFileBrowserFileSnapshot {
  meta: {
    path: string;
    name: string;
    size: number;
    mtime: number | null;
    maxBytes: number;
    encoding: "utf-8" | null;
    isBinary: boolean | null;
    reason: string | null;
    elapsedMs: number;
    fetchedAt: number;
  };
  /** null when too large, binary, or read error */
  content: string | null;
}

export interface SpcodeFileBrowserSymlinkSnapshot {
  meta: {
    path: string;
    name: string;
    size: number;
    mtime: number | null;
    isSymlink: true;
    target: string;
    targetExists: boolean;
    elapsedMs: number;
    fetchedAt: number;
  };
}

/** Raw backend response (1:1 with the JSON schema). All fields optional except path/name/type. */
export interface SpcodeFileBrowserRawResponse {
  type: "file" | "directory" | "symlink" | null;
  path: string;
  name: string;
  size: number;
  mtime: number | null;
  is_symlink: boolean;
  // file
  encoding?: "utf-8" | null;
  is_binary?: boolean | null;
  content?: string | null;
  max_bytes?: number;
  // directory
  entry_count?: number;
  truncated?: boolean;
  max_entries?: number;
  entries?: Array<{
    path: string;
    name: string;
    type: "directory" | "file" | "symlink";
    size: number | null;
    mtime: number | null;
    is_symlink: boolean;
    target?: string;
    target_exists?: boolean;
  }>;
  // symlink (top-level, i.e. when the requested path itself is a symlink)
  target?: string;
  target_exists?: boolean;
  // error
  reason: string | null;
  elapsed_ms: number;
}

export type SpcodeFileBrowserSnapshot =
  | { kind: "directory"; snapshot: SpcodeFileBrowserDirectorySnapshot }
  | { kind: "file"; snapshot: SpcodeFileBrowserFileSnapshot }
  | { kind: "symlink"; snapshot: SpcodeFileBrowserSymlinkSnapshot };

/** Thrown when data.type === null (true backend error). */
export class FileBrowserParseError extends Error {
  public readonly reason: string;
  constructor(reason: string) {
    super(`file-browser parse error: ${reason}`);
    this.name = "FileBrowserParseError";
    this.reason = reason;
  }
}

function normalizeEntry(raw: NonNullable<SpcodeFileBrowserRawResponse["entries"]>[number]): SpcodeFileBrowserEntry {
  return {
    path: raw.path,
    name: raw.name,
    type: raw.type,
    size: raw.size,
    mtime: raw.mtime,
    is_symlink: raw.is_symlink,
    target: raw.target,
    target_exists: raw.target_exists,
  };
}

/**
 * Parse raw response into a typed snapshot.
 * @throws {FileBrowserParseError} when data.type is null (backend error).
 */
export function parseSpcodeFileBrowser(data: SpcodeFileBrowserRawResponse): SpcodeFileBrowserSnapshot {
  const fetchedAt = Date.now();
  if (data.type === null) {
    throw new FileBrowserParseError(data.reason ?? "unknown");
  }
  if (data.type === "directory") {
    return {
      kind: "directory",
      snapshot: {
        meta: {
          path: data.path,
          entryCount: data.entry_count ?? 0,
          truncated: data.truncated ?? false,
          maxEntries: data.max_entries ?? 1000,
          reason: data.reason ?? null,
          elapsedMs: data.elapsed_ms ?? 0,
          fetchedAt,
        },
        entries: Array.isArray(data.entries) ? data.entries.map(normalizeEntry) : [],
      },
    };
  }
  if (data.type === "file") {
    return {
      kind: "file",
      snapshot: {
        meta: {
          path: data.path,
          name: data.name,
          size: data.size ?? 0,
          mtime: data.mtime ?? null,
          maxBytes: data.max_bytes ?? 5 * 1024 * 1024,
          encoding: data.encoding ?? null,
          isBinary: data.is_binary ?? null,
          reason: data.reason ?? null,
          elapsedMs: data.elapsed_ms ?? 0,
          fetchedAt,
        },
        content: data.content ?? null,
      },
    };
  }
  // data.type === "symlink"
  return {
    kind: "symlink",
    snapshot: {
      meta: {
        path: data.path,
        name: data.name,
        size: data.size ?? 0,
        mtime: data.mtime ?? null,
        isSymlink: true,
        target: data.target ?? "",
        targetExists: data.target_exists ?? false,
        elapsedMs: data.elapsed_ms ?? 0,
        fetchedAt,
      },
    },
  };
}
```

- [ ] **Step 2.2: Verify the file type-checks standalone**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
```

Expected: 0 errors. (If the dashboard is in pnpm, this runs `vue-tsc` or similar; may take ~30s.)

- [ ] **Step 2.3: Commit parser**

```bash
cd F:\github\Astrbot
git add dashboard/src/composables/parseSpcodeFileBrowser.ts
git commit -m "feat(spcode-filebrowser): add parseSpcodeFileBrowser parser"
```

---

### Task 3: Create `useSpcodeFileBrowser.ts`

**Files:**
- Create: `dashboard/src/composables/useSpcodeFileBrowser.ts`

**Context:** Reactive composable for the file-browser endpoint. Mirrors `useSpcodeGitDiff.ts` lifecycle pattern:
- Per-instance (not singleton); consumer disposes in `onBeforeUnmount`
- `isMounted` flag prevents `state.value` writes after dispose
- AbortController aborts in-flight requests on refresh / dispose
- Auto-refreshes when `pathRef` changes (post-flush watcher)

**Differences from `useSpcodeGitDiff`:**
- No polling (files are loaded on demand, not on a schedule)
- `refresh(path?: string)` accepts optional path (uses `toValue(pathRef)` if omitted)
- Error state's `previousSnapshot` field kept for potential future use (currently dead per review advisory R1; can be removed in follow-up)

Reference: `dashboard/src/composables/useSpcodeGitDiff.ts:140-220` for the lifecycle pattern.

- [ ] **Step 3.1: Create the file**

Create `dashboard/src/composables/useSpcodeFileBrowser.ts`:

```typescript
// Author: elecvoid243, 2026-06-20
// Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.2
// Mirrors the lifecycle pattern of useSpcodeGitDiff.ts but does NOT poll
// (file-browser is on-demand: user navigates to a directory or clicks a file).

import { ref, watch, toValue, type Ref, type MaybeRef } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeFileBrowser,
  FileBrowserParseError,
  type SpcodeFileBrowserRawResponse,
  type SpcodeFileBrowserDirectorySnapshot,
  type SpcodeFileBrowserFileSnapshot,
  type SpcodeFileBrowserSymlinkSnapshot,
} from "./parseSpcodeFileBrowser";

export type FileBrowserFetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "directory"; snapshot: SpcodeFileBrowserDirectorySnapshot }
  | { kind: "file"; snapshot: SpcodeFileBrowserFileSnapshot }
  | { kind: "symlink"; snapshot: SpcodeFileBrowserSymlinkSnapshot }
  | {
      kind: "error";
      reason: string;
      previousSnapshot?:
        | SpcodeFileBrowserDirectorySnapshot
        | SpcodeFileBrowserFileSnapshot
        | SpcodeFileBrowserSymlinkSnapshot;
    };

export interface UseSpcodeFileBrowser {
  state: Ref<FileBrowserFetchState>;
  refresh: (path?: string) => Promise<void>;
  dispose: () => void;
}

/** Type guard for the three snapshot kinds (excludes idle/loading/error). */
function isSnapshotKind(
  kind: FileBrowserFetchState["kind"],
): kind is "directory" | "file" | "symlink" {
  return kind === "directory" || kind === "file" || kind === "symlink";
}

/** Classify an axios/network error into a reason code for the UI. */
function classifyError(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const anyErr = err as { code?: string; message?: string };
    if (anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")) {
      return "network";
    }
  }
  return "unknown";
}

/**
 * Composable for /spcode/file-browser.
 *
 * Per file-browser spec §3.5.1: this endpoint is stateless (no umo).
 * Unlike useSpcodeGitDiff, this composable does NOT poll — file
 * content is loaded on demand. Callers can invoke refresh(path)
 * explicitly; the composable also auto-refreshes when pathRef changes.
 *
 * Lifecycle: per-instance. Caller must invoke dispose() in
 * onBeforeUnmount to prevent state writes after unmount.
 */
export function useSpcodeFileBrowser(pathRef: MaybeRef<string>): UseSpcodeFileBrowser {
  const state = ref<FileBrowserFetchState>({ kind: "idle" });
  let abortController: AbortController | null = null;
  let isMounted = true;

  async function refresh(targetPath?: string): Promise<void> {
    if (!isMounted) return;
    const path = targetPath ?? toValue(pathRef);
    if (!path) {
      // Empty path → backend returns path_not_found. Short-circuit.
      const prev = isSnapshotKind(state.value.kind) ? state.value.snapshot : undefined;
      state.value = { kind: "error", reason: "path_not_found", previousSnapshot: prev };
      return;
    }
    abortController?.abort();
    abortController = new AbortController();
    const isFirst = !isSnapshotKind(state.value.kind);
    if (isFirst) state.value = { kind: "loading" };
    try {
      const resp = await pluginExtensionApi.get<SpcodeFileBrowserRawResponse>(
        "spcode/file-browser",
        { params: { path }, signal: abortController.signal },
      );
      if (!isMounted) return;
      const data = resp.data?.data;
      if (!data) throw new Error("empty response data");
      const snapshot = parseSpcodeFileBrowser(data);
      state.value = snapshot;
    } catch (err) {
      if (!isMounted) return;
      if ((err as { name?: string })?.name === "CanceledError") return;
      const prev = isSnapshotKind(state.value.kind) ? state.value.snapshot : undefined;
      if (err instanceof FileBrowserParseError) {
        state.value = { kind: "error", reason: err.reason, previousSnapshot: prev };
        return;
      }
      state.value = { kind: "error", reason: classifyError(err), previousSnapshot: prev };
    }
  }

  // Auto-refresh when pathRef changes (post-flush so initial assignment
  // doesn't trigger an extra fetch for the first navigation).
  watch(
    () => toValue(pathRef),
    () => { if (isMounted) void refresh(); },
    { flush: "post" },
  );

  function dispose(): void {
    isMounted = false;
    abortController?.abort();
    abortController = null;
  }

  return { state, refresh, dispose };
}
```

- [ ] **Step 3.2: Verify the file type-checks**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
```

Expected: 0 errors. If `pluginExtensionApi.get` type signature differs, check `dashboard/src/api/v1/index.ts` and adjust the generic.

- [ ] **Step 3.3: Commit composable**

```bash
cd F:\github\Astrbot
git add dashboard/src/composables/useSpcodeFileBrowser.ts
git commit -m "feat(spcode-filebrowser): add useSpcodeFileBrowser composable"
```

---

**End of Chunk 1.** Reviewer verification before proceeding to Chunk 2.

---

## Chunk 2: UI Components (4 Vue components)

### Task 4: Create `FileBrowserBreadcrumb.vue`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/FileBrowserBreadcrumb.vue`

**Context:** Pure presentational component. Splits `currentPath` into clickable segments (root + intermediate + current). Cross-platform (handles both `/` and `\` separators). No fetch state, no composables.

Reference for cross-platform path handling: `dashboard/src/utils/pathUtils.ts` if it exists, else handle inline (max 2 lines).

- [ ] **Step 4.1: Create the file**

Create `dashboard/src/components/chat/message_list_comps/FileBrowserBreadcrumb.vue`:

```vue
<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.6 -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  currentPath: string;
  /** Root path; null when project not loaded. */
  rootPath: string | null;
}>();
const emit = defineEmits<{ (e: "navigate", path: string): void }>();
const { tm } = useModuleI18n("features/chat");

interface Segment {
  name: string;
  path: string;
  isRoot: boolean;
}

// Split currentPath into clickable segments. root segment is special
// (label = "Project root" / "项目根" / "Корень проекта").
const segments = computed<Segment[]>(() => {
  if (!props.currentPath || !props.rootPath) return [];
  const sep = props.currentPath.includes("\\") ? "\\" : "/";
  const normCurrent = props.currentPath.replace(/\\/g, "/");
  const normRoot = props.rootPath.replace(/\\/g, "/").replace(/\/$/, "");

  // Compute relative path from root
  let relative: string;
  if (normCurrent === normRoot) {
    relative = "";
  } else if (normCurrent.startsWith(normRoot + "/")) {
    relative = normCurrent.slice(normRoot.length + 1);
  } else {
    return [];  // currentPath is outside root; render nothing
  }

  const parts = relative.split("/").filter(Boolean);
  const result: Segment[] = [
    { name: tm("spcodeProjectLoad.fileBrowser.breadcrumbRoot"), path: normRoot, isRoot: true },
  ];
  let acc = normRoot;
  for (const p of parts) {
    acc += "/" + p;
    result.push({ name: p, path: acc, isRoot: false });
  }
  return result;
});
</script>

<template>
  <nav v-if="segments.length > 0" class="file-browser-breadcrumb">
    <template v-for="(seg, i) in segments" :key="seg.path">
      <button
        type="button"
        class="breadcrumb-segment"
        :class="{ 'is-current': i === segments.length - 1 }"
        :title="seg.path"
        @click="emit('navigate', seg.path)"
      >
        {{ seg.name }}
      </button>
      <span v-if="i < segments.length - 1" class="breadcrumb-sep">/</span>
    </template>
  </nav>
</template>

<style scoped>
.file-browser-breadcrumb {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  padding: 8px 14px;
  font-size: 12px;
  font-family: ui-monospace, monospace;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.4);
}
.breadcrumb-segment {
  background: none;
  border: none;
  padding: 2px 6px;
  border-radius: 4px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-family: inherit;
  font-size: inherit;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.breadcrumb-segment:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), 0.9);
}
.breadcrumb-segment.is-current {
  color: rgba(var(--v-theme-on-surface), 0.95);
  font-weight: 500;
  cursor: default;
}
.breadcrumb-sep {
  color: rgba(var(--v-theme-on-surface), 0.3);
  user-select: none;
}
</style>
```

- [ ] **Step 4.2: Verify type-check**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
```

Expected: 0 errors.

- [ ] **Step 4.3: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/FileBrowserBreadcrumb.vue
git commit -m "feat(spcode-filebrowser): add FileBrowserBreadcrumb component"
```

---

### Task 5: Create `FileBrowserEntryList.vue`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/FileBrowserEntryList.vue`

**Context:** Left pane of the Files view. Renders directory entries. Three entry types with distinct icons:
- `directory`: `mdi-folder-outline` (info color)
- `file`: `mdi-file-document-outline` (grey)
- `symlink`: `mdi-link-variant` (info color); dangling → red border

Click handlers:
- Dangling symlink: no-op
- Regular entry: emits `navigate(entry.path)`
- (Symlink "Go to target" is handled in the right pane, not the list)

Renders `truncated` warning banner at top when `state.kind === "directory" && snapshot.meta.truncated === true`.

- [ ] **Step 5.1: Create the file**

Create `dashboard/src/components/chat/message_list_comps/FileBrowserEntryList.vue`:

```vue
<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.4 -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { FileBrowserFetchState } from "@/composables/useSpcodeFileBrowser";
import type { SpcodeFileBrowserEntry } from "@/composables/parseSpcodeFileBrowser";

const props = defineProps<{
  state: FileBrowserFetchState;
}>();
const emit = defineEmits<{ (e: "navigate", path: string): void }>();
const { tm } = useModuleI18n("features/chat");

const TYPE_ICONS: Record<SpcodeFileBrowserEntry["type"], { icon: string; color: string }> = {
  directory: { icon: "mdi-folder-outline", color: "info" },
  file: { icon: "mdi-file-document-outline", color: "grey" },
  symlink: { icon: "mdi-link-variant", color: "info" },
};

const entries = computed<SpcodeFileBrowserEntry[]>(() => {
  if (props.state.kind === "directory") return props.state.snapshot.entries;
  return [];
});

const truncated = computed<boolean>(() => {
  return props.state.kind === "directory" && props.state.snapshot.meta.truncated;
});

function handleClick(entry: SpcodeFileBrowserEntry): void {
  // Dangling symlink: click does nothing
  if (entry.type === "symlink" && entry.target_exists === false) return;
  emit("navigate", entry.path);
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}
</script>

<template>
  <div class="file-browser-entry-list">
    <div v-if="truncated" class="entry-list-warning">
      {{ tm("spcodeProjectLoad.fileBrowser.truncated") }}
    </div>

    <div v-if="entries.length === 0 && state.kind === 'directory'" class="file-browser-empty-dir">
      <v-icon size="24" color="grey">mdi-folder-open-outline</v-icon>
      <span>{{ tm("spcodeProjectLoad.fileBrowser.empty") }}</span>
    </div>

    <ul v-else class="file-browser-entries">
      <li
        v-for="entry in entries"
        :key="entry.path"
        class="file-browser-entry"
        :class="{
          'is-symlink': entry.type === 'symlink',
          'is-dangling': entry.type === 'symlink' && entry.target_exists === false,
        }"
        @click="handleClick(entry)"
      >
        <v-icon
          :icon="TYPE_ICONS[entry.type].icon"
          :color="TYPE_ICONS[entry.type].color"
          size="16"
        />
        <span class="entry-name">{{ entry.name }}</span>
        <span v-if="entry.type === 'symlink' && entry.target" class="entry-symlink-target">
          → {{ entry.target }}
        </span>
        <span class="entry-size">{{ formatSize(entry.size) }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.file-browser-entry-list {
  flex: 0 0 40%;
  min-width: 140px;
  overflow-y: auto;
  overflow-x: hidden;
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  display: flex;
  flex-direction: column;
}
.entry-list-warning {
  padding: 8px 14px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-warning), 1);
  background: rgba(var(--v-theme-warning), 0.08);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.file-browser-empty-dir {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 13px;
}
.file-browser-entries {
  list-style: none;
  margin: 0;
  padding: 4px 0;
}
.file-browser-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 14px;
  cursor: pointer;
  font-size: 12.5px;
  transition: background 0.1s;
}
.file-browser-entry:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.file-browser-entry.is-dangling {
  opacity: 0.5;
  cursor: not-allowed;
}
.entry-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: ui-monospace, monospace;
}
.entry-symlink-target {
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 10.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}
.entry-size {
  color: rgba(var(--v-theme-on-surface), 0.4);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
</style>
```

- [ ] **Step 5.2: Verify type-check**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
```

Expected: 0 errors.

- [ ] **Step 5.3: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/FileBrowserEntryList.vue
git commit -m "feat(spcode-filebrowser): add FileBrowserEntryList component"
```

---

### Task 6: Create `FileBrowserFilePreview.vue`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`

**Context:** Right pane of the Files view. The most complex component — handles 5 sub-states:
- `idle` / `loading`: spinner
- `error`: icon + reason + retry button (emits `retry`)
- `directory`: small "select from left" hint (left pane already shows the list)
- `symlink`: target label + dangling warning + "Go to target" button (emits `navigate-target`)
- `file`: Shiki-highlighted content + meta (path, size, mtime) + copy button

**Shiki integration:** uses `ensureShikiLanguages` + `renderShikiCode` from `dashboard/src/utils/shiki.js`. The `detectLanguage` function is a mirror of the one in `dashboard/src/components/chat/message_list_comps/ToolResultView.vue:160-165`. We re-declare it locally to avoid a cross-file import (the existing helper is file-local).

Reference: `dashboard/src/components/chat/message_list_comps/ToolResultView.vue` for the Shiki usage pattern.

- [ ] **Step 6.1: Create the file**

Create `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`:

```vue
<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.5 -->
<script setup lang="ts">
import { computed, ref, onMounted, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { ensureShikiLanguages, renderShikiCode, escapeHtml } from "@/utils/shiki";
import type { FileBrowserFetchState } from "@/composables/useSpcodeFileBrowser";

const props = defineProps<{
  state: FileBrowserFetchState;
  isDark: boolean;
}>();
const emit = defineEmits<{
  (e: "navigate-target", resolvedPath: string): void;
  (e: "retry"): void;
}>();
const { tm } = useModuleI18n("features/chat");

/**
 * Resolve a symlink target string (which may be relative) against the
 * symlink's parent directory. Mirrors POSIX symlink semantics:
 * - Absolute target: use as-is
 * - Relative target: join with parent dir of the symlink
 *
 * The backend does NOT resolve symlinks (per file-browser spec §3.5.4);
 * if the user wants to view the resolved content, we manually re-issue
 * the request with the resolved path so the backend re-classifies it.
 */
function resolveTargetPath(symlinkPath: string, target: string): string {
  const isWindows = symlinkPath.includes("\\");
  const sep = isWindows ? "\\" : "/";
  if (target.startsWith("/") || /^[a-zA-Z]:[\\/]/.test(target)) {
    return target;  // Absolute path
  }
  const lastSep = Math.max(symlinkPath.lastIndexOf("/"), symlinkPath.lastIndexOf("\\"));
  const parentDir = lastSep >= 0 ? symlinkPath.slice(0, lastSep) : symlinkPath;
  return parentDir + sep + target;
}

// Mirror of detectLanguage in ToolResultView.vue (line 160-165) to ensure
// consistent language detection between the tool result view and this preview.
const EXT_TO_LANG: Record<string, string> = {
  ".py": "python",
  ".js": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".ts": "typescript",
  ".tsx": "tsx",
  ".jsx": "jsx",
  ".vue": "vue",
  ".json": "json",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".sh": "bash",
  ".bash": "bash",
  ".zsh": "bash",
  ".css": "css",
  ".html": "html",
  ".htm": "html",
  ".xml": "xml",
  ".svg": "xml",
  ".md": "markdown",
  ".sql": "sql",
  ".java": "java",
  ".ini": "ini",
  ".diff": "diff",
  ".patch": "diff",
  ".ps1": "powershell",
  ".dockerfile": "dockerfile",
  ".txt": "text",
  ".c": "c",
  ".h": "c",
  ".cpp": "cpp",
  ".cc": "cpp",
  ".cxx": "cpp",
  ".hpp": "cpp",
  ".c++": "cpp",
  ".go": "go",
  ".rs": "rust",
};

function detectLanguage(filePath: string): string {
  const m = filePath.match(/\.([\w]+)$/i);
  if (!m) return "text";
  const key = "." + m[1].toLowerCase();
  return EXT_TO_LANG[key] || "text";
}

const shikiHighlighter = ref<any>(null);
const shikiReady = ref(false);

onMounted(async () => {
  // Pattern mirrored verbatim from ToolResultView.vue:289 — do NOT
  // pass an array arg to ensureShikiLanguages (it takes zero args
  // and silently ignores any). Assign the returned highlighter so
  // the !shikiHighlighter.value guard in highlightedHtml is satisfied.
  try {
    shikiHighlighter.value = await ensureShikiLanguages();
    shikiReady.value = true;
  } catch (err) {
    console.error("Shiki init failed:", err);
  }
});

const highlightedHtml = computed(() => {
  if (props.state.kind !== "file") return "";
  const snapshot = props.state.snapshot;
  if (snapshot.content === null) return "";
  if (!shikiReady.value || !shikiHighlighter.value) {
    return `<pre><code>${escapeHtml(snapshot.content)}</code></pre>`;
  }
  try {
    // renderShikiCode signature: (highlighter, code, language, colorMode)
    // colorMode="auto" enables dual-theme (light/dark) auto-switching.
    return renderShikiCode(
      shikiHighlighter.value,
      snapshot.content,
      detectLanguage(snapshot.meta.path),
      "auto",
    );
  } catch (err) {
    console.error("Shiki render failed:", err);
    return `<pre><code>${escapeHtml(snapshot.content)}</code></pre>`;
  }
});

const copyButtonText = ref<string>("");
watch(highlightedHtml, () => {
  copyButtonText.value = tm("spcodeProjectLoad.fileBrowser.preview.copy");
});

async function copyContent(): Promise<void> {
  if (props.state.kind !== "file" || !props.state.snapshot.content) return;
  if (!navigator.clipboard) return;  // HTTP insecure context fallback
  try {
    await navigator.clipboard.writeText(props.state.snapshot.content);
    copyButtonText.value = tm("spcodeProjectLoad.fileBrowser.preview.copySuccess");
    setTimeout(() => {
      copyButtonText.value = tm("spcodeProjectLoad.fileBrowser.preview.copy");
    }, 2000);
  } catch {
    // Silent: user can manually select
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}
function formatMtime(mtime: number | null): string {
  if (!mtime) return "—";
  return new Date(mtime * 1000).toLocaleString();
}

// Map the composable's reason codes to localized messages.
const REASON_I18N_KEYS: Record<string, string> = {
  path_not_found: "spcodeProjectLoad.fileBrowser.error.pathNotFound",
  permission_denied: "spcodeProjectLoad.fileBrowser.error.permissionDenied",
  special_file: "spcodeProjectLoad.fileBrowser.error.specialFile",
};

function localizedReason(reason: string): string {
  const key = REASON_I18N_KEYS[reason];
  if (key) return tm(key);
  if (reason === "network") {
    return tm("spcodeProjectLoad.fileBrowser.error.network");
  }
  return tm("spcodeProjectLoad.fileBrowser.error.unknown", { reason });
}
</script>

<template>
  <div class="file-browser-preview">
    <!-- 加载中 -->
    <div v-if="state.kind === 'idle' || state.kind === 'loading'" class="preview-center">
      <v-progress-circular indeterminate color="primary" :size="32" />
      <span>{{ tm("spcodeProjectLoad.fileBrowser.loading") }}</span>
    </div>

    <!-- 错误(真错误:path_not_found / permission_denied / special_file / network / unknown) -->
    <div v-else-if="state.kind === 'error'" class="preview-center">
      <v-icon size="32" color="error">mdi-alert-circle-outline</v-icon>
      <div class="preview-error-title">{{ tm("spcodeProjectLoad.fileBrowser.error.loadFailedTitle") }}</div>
      <div class="preview-error-detail">{{ localizedReason(state.reason) }}</div>
      <v-btn
        size="small"
        color="primary"
        variant="tonal"
        prepend-icon="mdi-refresh"
        @click="emit('retry')"
      >
        {{ tm("spcodeProjectLoad.fileBrowser.error.retry") }}
      </v-btn>
    </div>

    <!-- 目录状态:左栏已经显示列表,右栏只显示提示 -->
    <div v-else-if="state.kind === 'directory'" class="preview-center">
      <v-icon size="32" color="grey">mdi-folder-open-outline</v-icon>
      <span class="preview-hint">{{ tm("spcodeProjectLoad.fileBrowser.preview.selectFromLeft") }}</span>
    </div>

    <!-- symlink 状态 -->
    <div v-else-if="state.kind === 'symlink'" class="preview-center">
      <v-icon size="32" color="info">mdi-link-variant</v-icon>
      <div class="preview-symlink-info">
        <div class="preview-symlink-target-label">→ {{ state.snapshot.meta.target }}</div>
        <div v-if="!state.snapshot.meta.targetExists" class="preview-symlink-dangling">
          {{ tm("spcodeProjectLoad.fileBrowser.entryType.dangling") }}
        </div>
      </div>
      <v-btn
        v-if="state.snapshot.meta.targetExists"
        size="small"
        variant="tonal"
        prepend-icon="mdi-arrow-right"
        @click="emit('navigate-target', resolveTargetPath(state.snapshot.meta.path, state.snapshot.meta.target))"
      >
        {{ tm("spcodeProjectLoad.fileBrowser.preview.goToTarget") }}
      </v-btn>
    </div>

    <!-- 文件 -->
    <div v-else-if="state.kind === 'file'" class="preview-file">
      <!-- 元信息头 -->
      <div class="preview-file-meta">
        <span class="preview-file-path" :title="state.snapshot.meta.path">{{ state.snapshot.meta.name }}</span>
        <span class="preview-file-size">{{ formatBytes(state.snapshot.meta.size) }}</span>
        <span class="preview-file-mtime">{{ formatMtime(state.snapshot.meta.mtime) }}</span>
        <v-btn
          v-if="state.snapshot.content"
          size="x-small"
          variant="text"
          prepend-icon="mdi-content-copy"
          @click="copyContent"
        >
          {{ copyButtonText }}
        </v-btn>
      </div>

      <!-- 二进制文件 -->
      <div v-if="state.snapshot.meta.isBinary === true" class="preview-binary">
        <v-icon size="32" color="grey">mdi-file-question-outline</v-icon>
        <span>{{ tm("spcodeProjectLoad.fileBrowser.preview.binary") }}</span>
      </div>

      <!-- 过大文件 -->
      <div v-else-if="state.snapshot.content === null" class="preview-binary">
        <v-icon size="32" color="grey">mdi-file-alert-outline</v-icon>
        <span>{{ tm("spcodeProjectLoad.fileBrowser.preview.tooLarge", { size: formatBytes(state.snapshot.meta.size) }) }}</span>
      </div>

      <!-- 文本内容(Shiki 高亮) -->
      <pre v-else class="preview-file-content" v-html="highlightedHtml" />
    </div>
  </div>
</template>

<style scoped>
.file-browser-preview {
  flex: 1 1 60%;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: transparent;
}
.preview-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 100%;
  padding: 32px 16px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 13px;
  text-align: center;
}
.preview-hint { color: rgba(var(--v-theme-on-surface), 0.5); font-size: 12.5px; }
.preview-error-title { color: rgba(var(--v-theme-error), 1); font-weight: 500; font-size: 14px; }
.preview-error-detail { color: rgba(var(--v-theme-on-surface), 0.7); font-size: 12.5px; max-width: 320px; }

.preview-file {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.preview-file-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 14px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.4);
}
.preview-file-path {
  flex: 1;
  font-family: ui-monospace, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-file-size, .preview-file-mtime {
  font-variant-numeric: tabular-nums;
  color: rgba(var(--v-theme-on-surface), 0.4);
}
.preview-file-content {
  flex: 1;
  margin: 0;
  padding: 12px 14px;
  overflow: auto;
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
  line-height: 1.55;
  background: transparent !important;
}
.preview-binary {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 16px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 13px;
}
.preview-symlink-info {
  font-family: ui-monospace, monospace;
  font-size: 13px;
  text-align: center;
}
.preview-symlink-target-label { color: rgb(var(--v-theme-info)); }
.preview-symlink-dangling {
  color: rgb(248, 81, 73);
  font-size: 12px;
  margin-top: 6px;
}
</style>
```

- [ ] **Step 6.2: Verify type-check**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
```

Expected: 0 errors. If `ensureShikiLanguages` / `renderShikiCode` / `escapeHtml` exports differ, check `dashboard/src/utils/shiki.js` and adjust.

- [ ] **Step 6.3: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue
git commit -m "feat(spcode-filebrowser): add FileBrowserFilePreview component"
```

---

### Task 7: Create `FileBrowserView.vue` (main container)

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue`

**Context:** Main Files-view component. Owns the `useSpcodeFileBrowser` composable instance. Layout shell: breadcrumb on top, two-pane (entry list + preview) below. Renders placeholder when project not loaded.

**Props received from parent `GitDiffSidebar`:**
- `currentPath: string` (state lifted to parent)
- `isDark: boolean`
- `rootPath: string | null` (computed by parent: `selectedWorktree ?? mainWorktreePath`)

**No `useSpcodeWorktrees` instance here** — worktree data is passed as props (per spec §4.3 decision; avoids duplicate composable instances).

- [ ] **Step 7.1: Create the file**

Create `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue`:

```vue
<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.3 -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeFileBrowser } from "@/composables/useSpcodeFileBrowser";
import FileBrowserBreadcrumb from "./FileBrowserBreadcrumb.vue";
import FileBrowserEntryList from "./FileBrowserEntryList.vue";
import FileBrowserFilePreview from "./FileBrowserFilePreview.vue";

const props = defineProps<{
  currentPath: string;
  isDark?: boolean;
  /** Current worktree root (parent computes: selectedWorktree ?? mainWorktreePath). null = project not loaded. */
  rootPath: string | null;
}>();
const emit = defineEmits<{ (e: "navigate", path: string): void }>();

const { tm } = useModuleI18n("features/chat");
const spcodeStatus = useSpcodeProjectStatus();

const fileBrowserComposable = useSpcodeFileBrowser(
  computed(() => props.currentPath),
);
</script>

<template>
  <div class="file-browser-view">
    <div v-if="!spcodeStatus.status.value.loaded" class="file-browser-empty">
      <v-icon size="36" color="grey">mdi-folder-open-outline</v-icon>
      <span class="empty-text">{{ tm("spcodeProjectLoad.fileBrowser.placeholder") }}</span>
    </div>

    <template v-else>
      <FileBrowserBreadcrumb
        :current-path="currentPath"
        :root-path="rootPath"
        @navigate="(p) => emit('navigate', p)"
      />

      <div class="file-browser-body">
        <FileBrowserEntryList
          :state="fileBrowserComposable.state.value"
          @navigate="(p) => emit('navigate', p)"
        />

        <div class="file-browser-divider" />

        <FileBrowserFilePreview
          :state="fileBrowserComposable.state.value"
          :is-dark="!!isDark"
          @navigate-target="(p) => emit('navigate', p)"
          @retry="() => fileBrowserComposable.refresh()"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.file-browser-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.file-browser-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.file-browser-divider {
  width: 1px;
  background: rgba(var(--v-theme-on-surface), 0.1);
  flex-shrink: 0;
}
.file-browser-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px 16px;
  min-height: 200px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.empty-text { font-size: 14px; }

/* Mobile: stack the two panes vertically. */
@media (max-width: 760px) {
  .file-browser-body {
    flex-direction: column;
  }
  .file-browser-divider {
    width: auto;
    height: 1px;
  }
  :deep(.file-browser-entry-list) {
    flex: 0 0 auto;
    max-height: 40vh;
    min-width: 0;
  }
  :deep(.file-browser-preview) {
    flex: 1 1 auto;
  }
}
</style>
```

- [ ] **Step 7.2: Verify type-check**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
```

Expected: 0 errors.

- [ ] **Step 7.3: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/FileBrowserView.vue
git commit -m "feat(spcode-filebrowser): add FileBrowserView container"
```

---

**End of Chunk 2.**

---

## Chunk 3: GitDiffSidebar Integration (view-mode tab + persistence + final E2E)

### Task 8: Modify `GitDiffSidebar.vue` to add Files view

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

**Context:** This is the largest single-file change in the plan — `GitDiffSidebar.vue` grows from ~600 lines to ~750 lines. The modifications are:

1. **Add view-mode state + localStorage persistence** (4 keys: `viewMode`, `selectedWorktree`, `selectedScope`, `fileBrowserCurrentPath`).
2. **Add `FileBrowserView` import** + `fileBrowserCurrentPath` ref.
3. **Lift worktree tabs** to a level visible in both views (currently they sit *below* the scope bar, which is Diff-only).
4. **Add view-mode tab pill** (Files / Diff) at the top — same component family as the scope pills.
5. **Conditionally render** `<FileBrowserView>` vs `<GitDiffBodyContent>` based on `viewMode`.
6. **Dispose `useSpcodeFileBrowser`** in `onBeforeUnmount` (if we instantiate the composable here directly). We do NOT need a `useSpcodeFileBrowser` instance here — `FileBrowserView` owns its own.

Reference for the existing structure: `dashboard/src/components/chat/GitDiffSidebar.vue:1-100` (script setup header), `GitDiffSidebar.vue:300-420` (template + worktree tabs), `GitDiffSidebar.vue:420-500` (body).

**localStorage keys** (per spec §6.2):
- `astrbot.spcode.gitDiffSidebar.viewMode` — `"files" | "diff"` (default `"files"`)
- `astrbot.spcode.gitDiffSidebar.fileBrowserCurrentPath` — string (default: `mainWorktreePath` once loaded, else `""`)
- `astrbot.spcode.gitDiffSidebar.selectedWorktree` — string | null (already in use as ref; we just add persistence)
- `astrbot.spcode.gitDiffSidebar.selectedScope` — string (already in use as ref; we just add persistence)

> **Why the `gitDiffSidebar.` prefix and not `sidebar.`:** spec §6.2 mandates `astrbot.spcode.gitDiffSidebar.*`. Using a different prefix would silently lose state for users who already have the old keys.

**Validation rules** (per spec §6.3):
- `viewMode`: must be `"files"` or `"diff"`; else default `"files"` (per spec §2 decision #10).
- `selectedScope`: must be one of `"unstaged" | "staged" | "all"`; else default `DEFAULT_SCOPE` (`"unstaged"`).
- `selectedWorktree`: must match an entry in `worktreeList` or be `null`; else reset to `null`.
- `fileBrowserCurrentPath`: must be a non-empty string AND be inside the current root (cross-root check via `validateCurrentPath`); else reset to `mainWorktreePath` (or the active worktree's root).

- [ ] **Step 8.1: Add localStorage helper constants + types**

Open `dashboard/src/components/chat/GitDiffSidebar.vue`. After the existing imports block, add a section:

```typescript
// ── localStorage persistence (spec 2026-06-20 §5.1 + §6) ────────────
// Persists 4 view-state keys across page reloads. Values are loaded
// once at component creation and saved on every change (most are
// flush:"post" watchers; currentPath uses a 300ms debounce per spec
// §2 decision #9 to avoid thrashing during fast navigation).
//
// Validation rules: invalid persisted values are silently replaced
// with the spec-defined default. We never throw — localStorage may
// be disabled (private browsing) or the value may have been written
// by an older app version.
const STORAGE_KEYS = {
  viewMode: "astrbot.spcode.gitDiffSidebar.viewMode",
  fileBrowserCurrentPath: "astrbot.spcode.gitDiffSidebar.fileBrowserCurrentPath",
  selectedWorktree: "astrbot.spcode.gitDiffSidebar.selectedWorktree",
  selectedScope: "astrbot.spcode.gitDiffSidebar.selectedScope",
} as const;

function safeGetItem(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function safeSetItem(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* no-op */ }
}

function loadViewMode(): "files" | "diff" {
  const v = safeGetItem(STORAGE_KEYS.viewMode);
  return v === "files" || v === "diff" ? v : "files";
}
function loadFileBrowserCurrentPath(): string {
  return safeGetItem(STORAGE_KEYS.fileBrowserCurrentPath) ?? "";
}
function loadSelectedScope(): GitDiffScope {
  const v = safeGetItem(STORAGE_KEYS.selectedScope);
  if (v === "unstaged" || v === "staged" || v === "all") return v;
  return DEFAULT_SCOPE;
}

// Debounced writer for currentPath (spec §5.1 lines 1273-1280).
// Avoids localStorage thrashing when the user clicks through
// directories rapidly.
let persistCurrentPathTimer: ReturnType<typeof setTimeout> | null = null;
function persistCurrentPath(path: string): void {
  if (persistCurrentPathTimer) clearTimeout(persistCurrentPathTimer);
  persistCurrentPathTimer = setTimeout(() => {
    safeSetItem(STORAGE_KEYS.fileBrowserCurrentPath, path);
  }, 300);
}

// Cross-root validator (spec §5.1 lines 1300-1310). Returns the input
// if it's inside the root, else the root. Used to reset stale paths
// after project / worktree switches.
function validateCurrentPath(persisted: string | null, root: string | null): string {
  if (!root) return "";
  if (!persisted) return root;
  const normPersisted = persisted.replace(/\\/g, "/");
  const normRoot = root.replace(/\\/g, "/").replace(/\/$/, "");
  if (normPersisted === normRoot || normPersisted.startsWith(normRoot + "/")) {
    return persisted;
  }
  return root;
}

// selectedWorktree: validated after worktree list loads (Step 8.3 below).
```

- [ ] **Step 8.2: Add the new refs**

After the existing `selectedWorktree` / `selectedScope` / `pendingScope` block, add:

```typescript
// ── View-mode tab (spec 2026-06-20 §5.1 + §5.2) ─────────────────────
// "files" shows <FileBrowserView>; "diff" shows <GitDiffBodyContent>.
// Default: "files" per spec §2 decision #10 (the more general view;
// first-time users likely want to "see what's in the project").
const viewMode = ref<"files" | "diff">(loadViewMode());
const fileBrowserCurrentPath = ref<string>(loadFileBrowserCurrentPath());
```

Also add the import for `FileBrowserView` at the top of the file, next to the `GitDiffBodyContent` import:

```typescript
import FileBrowserView from "@/components/chat/message_list_comps/FileBrowserView.vue";
```

- [ ] **Step 8.3: Persist the 4 refs + validate `selectedWorktree` after worktree list loads**

Add this block right after the `viewMode` ref declarations (or anywhere after `worktreeList` / `mainWorktreePath` are defined):

```typescript
// Persist viewMode / selectedScope / selectedWorktree on every change.
// fileBrowserCurrentPath uses persistCurrentPath (300ms debounce).
watch(viewMode, (v) => safeSetItem(STORAGE_KEYS.viewMode, v), { flush: "post" });
watch(
  selectedScope,
  (v) => safeSetItem(STORAGE_KEYS.selectedScope, v),
  { flush: "post" },
);

// selectedScope: load persisted value, fall back to DEFAULT_SCOPE.
const persistedScope = loadSelectedScope();
if (persistedScope !== DEFAULT_SCOPE) selectedScope.value = persistedScope;

// selectedWorktree: load raw value first, then validate after
// worktree list arrives. We store the literal string "null" for null.
const persistedWorktree = safeGetItem(STORAGE_KEYS.selectedWorktree);
if (persistedWorktree !== null && persistedWorktree !== "null") {
  selectedWorktree.value = persistedWorktree;
}
watch(
  selectedWorktree,
  (v) => safeSetItem(
    STORAGE_KEYS.selectedWorktree,
    v === null ? "null" : v,
  ),
  { flush: "post" },
);

// When the worktree list first loads, validate the persisted worktree
// AND cross-validate the persisted currentPath against the new root.
// This is the only place where fileBrowserCurrentPath is overwritten
// during initial hydration; thereafter the user is in control.
watch(
  () => worktreesComposable.state.value,
  (s) => {
    if (s.kind !== "ok") return;
    const wtList = s.snapshot.worktrees;
    // Validate selectedWorktree
    if (selectedWorktree.value && !wtList.some((w) => w.path === selectedWorktree.value)) {
      selectedWorktree.value = null;
    }
    // Validate currentPath against the (possibly new) root
    const root = selectedWorktree.value
      ?? wtList.find((w) => w.isMain)?.path
      ?? null;
    const validated = validateCurrentPath(fileBrowserCurrentPath.value, root);
    if (fileBrowserCurrentPath.value !== validated) {
      fileBrowserCurrentPath.value = validated;
    }
  },
  { immediate: true },
);

// When selectedWorktree changes, reset currentPath to the new root.
// This fires for BOTH manual worktree switches and project switches
// (which reset selectedWorktree to null via the existing directory
// watcher at line 137-143 of the current GitDiffSidebar.vue).
// Per spec §5.1: "reset currentPath regardless of current viewMode"
// — we don't want stale paths leaking into a different worktree.
watch(
  selectedWorktree,
  (newVal) => {
    const root = newVal ?? mainWorktreePath.value;
    if (root && fileBrowserCurrentPath.value !== root) {
      fileBrowserCurrentPath.value = root;
      persistCurrentPath(root);
    }
  },
);

// Persist currentPath (debounced 300ms, spec §5.1 line 1357-1361).
// Empty path is skipped — we don't want to overwrite a valid persisted
// value with an empty string during the brief interval before the
// worktree-list watcher fires.
watch(
  fileBrowserCurrentPath,
  (newPath) => { if (newPath) persistCurrentPath(newPath); },
);
```

> **Note on `selectedWorktree` persistence:** we write the literal string `"null"` when null, and read it back. The check `persistedWorktree !== null` then distinguishes "no persisted value" from "persisted null". This is a small workaround for the fact that `localStorage.getItem` returns `null` for both "missing" and "stored null".

- [ ] **Step 8.4: Add a `currentRoot` computed for `FileBrowserView`**

Add after the existing `directoryPath` / `isTruncated` / `truncatedShown` / `truncatedMax` computeds:

```typescript
// Root path for FileBrowserView: the active worktree (or main if none).
// We pass this to FileBrowserView so it can render the breadcrumb.
const currentRoot = computed<string | null>(() => {
  return selectedWorktree.value ?? mainWorktreePath.value;
});
```

- [ ] **Step 8.5: Add the `onFileBrowserNavigate` handler**

Add after the existing `onWorktreeChange` / `onScopeChange` functions:

```typescript
// Spec 2026-06-20 §4.3: user clicked a breadcrumb or entry → update
// currentPath. The composable inside FileBrowserView re-fetches
// automatically when this ref changes.
function onFileBrowserNavigate(path: string): void {
  fileBrowserCurrentPath.value = path;
}
```

- [ ] **Step 8.6: Lift worktree tabs + add view-mode tab in the template**

The current template order is:
```
header → scope bar → worktree tabs → truncated warning → body
```

The new order for the **Files** view is:
```
header → view-mode tab → worktree tabs → (body = FileBrowserView)
```

The new order for the **Diff** view is:
```
header → view-mode tab → worktree tabs → scope bar → truncated warning → (body = GitDiffBodyContent)
```

So the view-mode tab and worktree tabs move up to right after the header. The scope bar and warning stay Diff-only.

**Replace the entire `<template>` block** with the version below. The change set is:

- (a) Lift the worktree tabs `<div v-if="hasMultipleWorktrees" class="git-diff-sidebar-tabs">` to right after the header.
- (b) Add a new view-mode tab `<div class="git-diff-sidebar-view-tabs">` between header and worktree tabs.
- (c) Conditionally render the scope bar and warning inside a `<template v-if="viewMode === 'diff'">` block.
- (d) Conditionally render `<FileBrowserView>` vs `<GitDiffBodyContent>` in the body.

New template (full replacement):

```vue
<template>
  <transition name="slide-left">
    <aside
      v-if="modelValue"
      ref="sidebarRef"
      class="git-diff-sidebar"
      :class="{ resizing: isResizing }"
      :style="{ width: sidebarWidth + 'px' }"
    >
      <div class="git-diff-sidebar-resizer" @mousedown="startResize" />
      <div class="git-diff-sidebar-header">
        <div class="git-diff-sidebar-title-wrap">
          <span class="git-diff-sidebar-title">
            {{ viewMode === "files"
              ? tm("spcodeProjectLoad.fileBrowser.title")
              : tm("spcodeProjectLoad.diffSidebar.title") }}
          </span>
          <v-tooltip
            v-if="viewMode === 'diff' && directoryPath"
            location="bottom"
            :open-delay="200"
          >
            <template #activator="{ props: tipProps }">
              <v-icon
                v-bind="tipProps"
                size="14"
                class="git-diff-sidebar-dir-icon"
                >mdi-folder-outline</v-icon
              >
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
              {{ tm("spcodeProjectLoad.diffSidebar.refreshTooltip") }}
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

      <!-- View-mode tab (spec 2026-06-20 §5.2): Files / Diff.
           aria-label is hardcoded (per advisory R2) to avoid adding
           a 31st i18n key — the visible button text already conveys
           the purpose for sighted users. -->
      <div
        class="git-diff-sidebar-view-tabs"
        role="tablist"
        aria-label="Switch view"
      >
        <button
          type="button"
          role="tab"
          :aria-selected="viewMode === 'files'"
          :class="[
            'git-diff-sidebar-view-tab',
            { 'is-active': viewMode === 'files' },
          ]"
          @click="viewMode = 'files'"
        >
          <v-icon size="14">mdi-folder-outline</v-icon>
          <span>{{ tm("spcodeProjectLoad.fileBrowser.viewMode.files") }}</span>
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="viewMode === 'diff'"
          :class="[
            'git-diff-sidebar-view-tab',
            { 'is-active': viewMode === 'diff' },
          ]"
          @click="viewMode = 'diff'"
        >
          <v-icon size="14">mdi-source-pull</v-icon>
          <span>{{ tm("spcodeProjectLoad.fileBrowser.viewMode.diff") }}</span>
        </button>
      </div>

      <!-- Worktree tabs (visible in BOTH views, spec 2026-06-20 §5.3) -->
      <div
        v-if="hasMultipleWorktrees"
        class="git-diff-sidebar-tabs"
        role="tablist"
        :aria-label="tm('spcodeProjectLoad.diffSidebar.worktreeTabs.ariaLabel')"
      >
        <button
          v-for="wt in worktreeList"
          :key="wt.path"
          type="button"
          role="tab"
          :aria-selected="(selectedWorktree ?? mainWorktreePath) === wt.path"
          :class="[
            'git-diff-sidebar-tab',
            {
              'git-diff-sidebar-tab--active':
                (selectedWorktree ?? mainWorktreePath) === wt.path,
            },
          ]"
          :title="wt.path"
          @click="onWorktreeChange(wt.isMain ? null : wt.path)"
        >
          <v-icon v-if="wt.isMain" size="12" class="git-diff-sidebar-tab-icon"
            >mdi-home</v-icon
          >
          <span class="git-diff-sidebar-tab-label">
            {{
              wt.branch ??
              (wt.isMain
                ? tm("spcodeProjectLoad.diffSidebar.worktreeTabs.mainBadge")
                : wt.headSha.slice(0, 7))
            }}
          </span>
          <span v-if="!wt.branch" class="git-diff-sidebar-tab-badge">{{
            tm("spcodeProjectLoad.diffSidebar.worktreeTabs.detachedBadge")
          }}</span>
        </button>
      </div>

      <!-- Diff-only sub-UI: scope bar + truncation warning -->
      <template v-if="viewMode === 'diff'">
        <div
          class="git-diff-sidebar-scope"
          role="tablist"
          :aria-label="tm('spcodeProjectLoad.diffSidebar.scopeBar.ariaLabel')"
        >
          <div class="git-diff-sidebar-scope-pills">
            <button
              v-for="opt in SCOPE_OPTIONS"
              :key="opt.value"
              type="button"
              role="tab"
              :aria-selected="selectedScope === opt.value"
              :aria-label="tm(opt.labelKey)"
              :class="[
                'git-diff-sidebar-scope-pill',
                `is-${opt.value}`,
                { 'is-active': selectedScope === opt.value },
              ]"
              :disabled="
                !isProjectLoaded || (isScopeLoading && pendingScope !== opt.value)
              "
              @click="onScopeChange(opt.value)"
            >
              <v-icon size="14" class="git-diff-sidebar-scope-pill-icon">
                {{ opt.icon }}
              </v-icon>
              <span class="git-diff-sidebar-scope-pill-text">
                {{ tm(opt.labelKey) }}
              </span>
              <v-progress-circular
                v-if="isScopeLoading && pendingScope === opt.value"
                indeterminate
                :size="12"
                :width="2"
                class="git-diff-sidebar-scope-pill-spinner"
              />
            </button>
          </div>
        </div>
        <div v-if="isTruncated" class="git-diff-sidebar-warning">
          {{
            tm("spcodeProjectLoad.diffSidebar.truncated", {
              shown: truncatedShown,
              max: truncatedMax,
            })
          }}
        </div>
      </template>

      <!-- Body: Files view OR Diff view -->
      <div class="git-diff-sidebar-body">
        <FileBrowserView
          v-if="viewMode === 'files'"
          :current-path="fileBrowserCurrentPath"
          :is-dark="!!isDark"
          :root-path="currentRoot"
          @navigate="onFileBrowserNavigate"
        />
        <GitDiffBodyContent
          v-else
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
```

- [ ] **Step 8.7: Add CSS for the new view-mode tab**

Append to the existing `<style scoped>` block, after the `.git-diff-sidebar-actions` block (or any other appropriate location — verify by reading the file's CSS structure):

```css
/* ── View-mode tab (spec 2026-06-20 §5.2) ──────────────────── */

.git-diff-sidebar-view-tabs {
  display: flex;
  gap: 0;
  padding: 0 14px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.git-diff-sidebar-view-tab {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
  margin-bottom: -1px;
  transition:
    color 0.12s ease,
    border-color 0.12s ease;
}
.git-diff-sidebar-view-tab:hover {
  color: rgba(var(--v-theme-on-surface), 0.85);
}
.git-diff-sidebar-view-tab.is-active {
  color: rgb(var(--v-theme-primary));
  border-bottom-color: rgb(var(--v-theme-primary));
}
```

- [ ] **Step 8.8: Verify type-check + lint**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
pnpm lint
```

Expected: 0 errors. If the new `viewModeLabel` i18n key is missing, add it to all 3 locales (see Step 8.9 below).

- [ ] **Step 8.9: Confirm `viewModeLabel` i18n key is NOT needed**

The template (Step 8.6) uses a hardcoded `aria-label="Switch view"` (per advisory R2 from the plan review) — no extra i18n key is required. Skip this step.

> **If you prefer the named-key approach:** add `"viewModeLabel": "Switch view"` (or locale equivalents) to all 3 locales and change the template binding back to `:aria-label="tm('spcodeProjectLoad.fileBrowser.viewModeLabel')"`. This adds 1 key per locale, for a total of 31 keys (vs 30 in spec §7). The hardcoded approach is preferred for simplicity and consistency with the other sidebars (which also use English-hardcoded `aria-label` strings).

- [ ] **Step 8.10: Commit GitDiffSidebar integration**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/GitDiffSidebar.vue dashboard/src/i18n/locales/zh-CN/features/chat.json dashboard/src/i18n/locales/en-US/features/chat.json dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "feat(spcode-sidebar): integrate Files view with view-mode tab + persistence"
```

---

### Task 9: End-to-end manual verification (per spec §9 E1–E14)

**Files:** none modified. This is a verification + commit chore.

**Context:** Per spec §1.3, no Vitest. Verification = `pnpm typecheck` + `pnpm lint` + manual E2E. This task walks the executing agent through the full E1–E14 checklist. The dev server must be running (`pnpm dev` on port 3000) and the spcode plugin loaded with at least one project (use the `chatui-spcode-folder-picker` flow if needed).

- [ ] **Step 9.1: Confirm the static checks are clean**

Run:
```bash
cd F:\github\Astrbot\dashboard
pnpm typecheck
pnpm lint
```

Expected: 0 errors. If not, fix before proceeding.

- [ ] **Step 9.2: Start the dev server**

```bash
cd F:\github\Astrbot\dashboard
pnpm dev
```

Expected: server starts on `http://localhost:3000`. Open the URL in a browser.

- [ ] **Step 9.3: Walk the E1–E14 checklist from spec §9**

> **Note on scope (advisory R3):** spec §9 actually enumerates 34 individual bullets across 7 categories (§9.1 mount-and-load, §9.2 view-mode tab, §9.3 breadcrumb, §9.4 entries, §9.5 preview, §9.6 persistence, §9.7 error-edges). The 14 items below are a **critical-path condensation** that covers every category; the executing agent should also do a quick walkthrough of the full §9.1-§9.7 list after E1-E14 all pass.

For each of the 14 E2E scenarios in spec §9, run the test and record the result. Use a manual checklist:

| # | Scenario | Pass? | Notes |
|---|----------|-------|-------|
| E1 | Files view renders breadcrumb + placeholder when no project loaded | ☐ | |
| E2 | Loading a project populates breadcrumb with project root + intermediate segments | ☐ | |
| E3 | Clicking a directory entry navigates and fetches new content | ☐ | |
| E4 | Clicking a file entry shows Shiki-highlighted content (not plain `<pre>`) | ☐ | |
| E5 | Symlink entries render with `mdi-link-variant` icon; dangling links are visually distinct | ☐ | |
| E6 | Binary file renders `mdi-file-question-outline` placeholder; too-large renders `mdi-file-alert-outline` | ☐ | |
| E7 | Copy button copies content; tooltip changes to "Copied" for 2s | ☐ | |
| E8 | Truncation warning renders when directory has >1000 entries | ☐ | |
| E9 | viewMode tab switches between Files and Diff; both views' data is preserved | ☐ | |
| E10 | Reloading the page restores viewMode + selectedWorktree + selectedScope + currentPath | ☐ | |
| E11 | Switching to a non-existent worktree tab shows error in Files view but doesn't crash | ☐ | |
| E12 | Closing the sidebar + reopening preserves the last viewMode | ☐ | |
| E13 | Mobile width (≤760px) stacks the two panes vertically | ☐ | |
| E14 | All i18n keys are translated (no `tm()` returning key names in zh-CN / en-US / ru-RU) | ☐ | |

- [ ] **Step 9.4: Address any failed E1–E14 items**

For any `☐` that's now `✗`, document the failure, fix the underlying issue (likely in Chunk 2 components), and re-run the failed scenarios. Do not commit a "verification chore" commit if any item is failing.

- [ ] **Step 9.5: Final chore commit (no code changes)**

If `pnpm typecheck` and `pnpm lint` were both clean and all E1–E14 items pass:

```bash
cd F:\github\Astrbot
git status
```

Expected: clean working tree (no modifications). If clean, no commit is needed — the plan is complete.

If there are formatting-only changes from `pnpm lint --fix`, commit them:

```bash
cd F:\github\Astrbot
git add dashboard/
git commit -m "chore(spcode-sidebar): apply lint auto-fixes after E2E"
```

---

**End of Chunk 3.** Plan complete.

