# Document Manager Sub-tab — Design Spec (Frontend, Spec A)

| Field | Value |
| --- | --- |
| Spec author | elecvoid243 |
| Created at | 2026-07-11 20:09 (CST) |
| Status | Draft — pending user review |
| Scope | Frontend-only (Astrbot dashboard). Backend endpoints listed are **consumed** by this spec but **defined** in spec B. |

> Companion spec (to be authored separately): `2026-07-11-document-manager-backend-design.md`
> in repository `F:\github\astrbot_plugin_spcode_toolkit`. It defines the new
> endpoints `GET /spcode/git-file`, `POST /spcode/docs`, `PATCH /spcode/docs/<path>`,
> `DELETE /spcode/docs/<path>`, and adds a `?path=` filter to `GET /spcode/git-log`.

---

## 1. Goal

Add a new "文档管理 (Documents)" sub-tab inside `GitDiffSidebar.vue`, peer to the
existing "工作区 (Files)" / "Git Diff" / "历史 (History)" tabs.

The sub-tab is for reading and editing **project documentation** — primarily
spec / plan Markdown files living in a configurable docs root folder. It must:

1. Display the docs directory tree; click a `.md` file to preview.
2. Render Markdown in two modes — raw text and rendered HTML — via the same
   pipeline that `ReadmeDialog.vue` already implements.
3. Show per-file commit history. The user can pick **any past revision** and
   (a) view that revision's full Markdown rendered, and (b) view a unified
   diff between that revision and the current working-tree file.
4. Allow CRUD on docs files: create / save / delete. Rename ships as UI only
   in this spec (stubbed endpoint in spec B).

### Non-goals (out of scope)

- Authoring Markdown in the chat message surface (read-only docs view only).
- Real-time collaboration / multi-cursor editing.
- Auto-`git add` on save. Spec A writes **to working tree only**; user commits
  via the Git Diff tab.
- YAML frontmatter parsing, splitting, or special rendering.
- TOC sidebar, full-text search across docs, mermaid / KaTeX extensions.
- Editable Markdown inside the historical-revision view (read-only there).
- Backend endpoints — covered by spec B.

---

## 2. Design Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | **Sub-tab ordering** | `[Files · Documents · Git Diff · History]` | "Documents" sits next to "Files" because they share the most visual / conceptual overlap. The other two stay where they are. |
| 2 | **Default viewMode** | Unchanged — `"files"` still the default | Spec 2026-06-24 §2 decision #10 is preserved. New tab is opt-in via the existing pill row. |
| 3 | **Route / persistence** | Reuses `VIEW_MODE_STORAGE_KEY`; `loadViewMode()` validates against the 4-value enum and falls back to `"files"` on stale values | No new localStorage keys for viewMode. Path-bar state has its own key (see §3.4). |
| 4 | **Layout** | Two-pane resizable split (30% left, can be dragged 15–70%) — identical to `FileBrowserView` | Users already know the gesture. The resize logic itself is reused via a new shared composable (see §3.6). |
| 5 | **Path storage** | localStorage only, keyed by **UMO** (project identity), independent of worktree | Same path is used across all worktrees of the same project. Spec A does **not** call the backend to persist path; missing path falls back to `"docs"`. See §3.4. |
| 6 | **Markdown rendering** | Extract `MarkdownDialog`'s pipeline into `MarkdownPipeline.ts` + `MarkdownView.vue`; reuse for both `ReadmeDialog` and `DocumentManager` | The pipeline already supports shiki + DOMPurify + heading slugs + copy-code buttons. Extracting prevents duplication and unblocks future markdown surfaces (chat preview, tooltips). |
| 7 | **History "rendered" view** | New backend endpoint `GET /spcode/git-file?ref=<sha>&path=<rel>` returns **the full blob** at that ref | The existing `/spcode/git-show?path=` returns `patch: string` (unified diff), not the full file. We cannot reuse it for the "view historical version" requirement (#3a) — see §5.1. |
| 8 | **History "diff vs current" view** | Reuses existing `useSpcodeGitShow.fetchFile(sha, path)` — that gives us `patch: string` which is exactly a unified diff vs parent | We additionally render `patch` as a side-by-side or unified diff using existing DiffPreview component. |
| 9 | **`git-log` per-file filter** | Backend adds `?path=<rel>` to `GET /spcode/git-log`; frontend reuses `useSpcodeGitLog(...)` instance | Lets the existing composable's ETag + pagination + error handling carry over. One new query param, no new composable. |
| 10 | **Editor implementation** | CodeMirror 6 (`@codemirror/state` + `@codemirror/view` + `@codemirror/lang-markdown`); fall back to plain `<textarea>` if CodeMirror fails to load | CodeMirror 6 is ~200KB gzip vs Monaco's ~3MB; markdown language pack is sufficient for spec/plan docs. Fallback ensures the page is never broken. |
| 11 | **Rename** | UI renders a button but it is **disabled with a tooltip** "not available yet" | Spec B does not have a PATCH endpoint; we ship the UI in this spec so the visual flow is final, but the action is a no-op toast. |
| 12 | **Save semantics** | Save = **write to working tree only** (no auto `git add`); user commits via the Git Diff tab | Keeps the document manager decoupled from git workflow. Spec B confirms the endpoint behavior. |
| 13 | **Optimistic updates** | New file = optimistic (set selectedDoc first); Delete = pessimistic (wait for backend); Save = pessimistic (refresh after success) | Avoids the "I thought I deleted it but it's still there" foot-gun. New file rarely conflicts so optimism is fine. |
| 14 | **Sub-pane persistence** | `docsRoot` and `selectedDoc` are component-local state; they reset when the tab is unmounted (switching to another tab and back) | Matches existing `FileBrowserView` behavior. Users who want sticky recently-opened docs is a future enhancement. |

---

## 3. Architecture

### 3.1 New files

```
dashboard/
├── src/
│   ├── components/
│   │   ├── chat/
│   │   │   ├── GitDiffSidebar.vue                (modify: viewMode + new tab + new component mount)
│   │   │   └── message_list_comps/
│   │   │       ├── DocumentManager.vue           (NEW: page container)
│   │   │       ├── DocumentTreePanel.vue         (NEW: left pane)
│   │   │       ├── DocumentPathBar.vue           (NEW: top path editor)
│   │   │       ├── DocumentViewModeTab.vue       (NEW: top-right tab strip)
│   │   │       ├── DocumentHistoryPanel.vue      (NEW: bottom-right history list)
│   │   │       ├── DocumentEditor.vue            (NEW: codemirror 6 host + save/cancel/delete)
│   │   │       ├── CodemirrorHost.vue            (NEW: thin CodeMirror mount/unmount wrapper)
│   │   │       └── FileTreeList.vue              (NEW: extracted from FileBrowserView, reused by both)
│   │   └── shared/
│   │       ├── MarkdownView.vue                  (NEW: Vue wrapper around MarkdownPipeline)
│   │       └── MarkdownPipeline.ts               (NEW: createMarkdownRenderer() factory)
│   ├── composables/
│   │   ├── useSpcodeGitFile.ts                   (NEW: fetchRef for full file content at any ref)
│   │   └── useResizableSplit.ts                  (NEW: shared 15–70% drag handler)
│   ├── i18n/
│   │   └── locales/{en-US,zh-CN,ru-RU}/features/chat.json
│   │                                            (modify: + documentManager.* keys)
│   └── …
└── tests/
    ├── MarkdownPipeline.test.ts                   (NEW: node-only, no Vue)
    ├── useSpcodeGitFile.test.ts                   (NEW: composable, axios mocked)
    ├── useResizableSplit.test.ts                  (NEW: JSDOM + mocked mousemove/mouseup)
    ├── DocumentPathBar.test.ts                    (NEW: mounted, isValidDocsRoot coverage)
    ├── DocumentHistoryPanel.test.ts               (NEW: emits + empty state)
    ├── DocumentEditor.test.ts                     (NEW: dirty tracking, delete confirm, fallback)
    ├── DocumentTreePanel.test.ts                  (NEW: mock useSpcodeFileBrowser)
    └── DocumentManager.integration.test.ts        (NEW: light e2e, @vue/test-utils)
```

### 3.2 Module responsibilities (single-purpose)

| Module | Does | Does NOT |
|--------|------|----------|
| `DocumentManager.vue` | Wires up all sub-components; owns `docsRoot / selectedDoc / viewMode / historyOpen / selectedRevision / editMode / editBuffer`; orchestrates CRUD HTTP calls | Render Markdown, fetch git data directly, or manage low-level cache |
| `DocumentTreePanel.vue` | Render the docs directory tree (left pane); emit `navigate` / `select` | Show file preview, manage file content cache, do editing |
| `DocumentPathBar.vue` | Show / edit the docs root path; write localStorage on commit | Talk to the backend, fetch anything |
| `DocumentViewModeTab.vue` | Top-right tab strip UI; emit `update:modelValue` | Hold any data |
| `DocumentHistoryPanel.vue` | Show commit list (with path filter); emit `select-revision` / `compare-current` | Fetch file blobs or rendered HTML |
| `DocumentEditor.vue` | `<textarea>` (or CodeMirror 6) with save / cancel / copy / delete / rename (stub) buttons | Render Markdown, talk HTTP directly |
| `MarkdownView.vue` | Take raw Markdown → render HTML; expose copy-code button + heading anchors | Fetch data, manage editing state |
| `MarkdownPipeline.ts` | Pure factory: `createMarkdownRenderer()` returns a renderer with `render(source, opts)` and `dispose()` | Depend on Vue |
| `useSpcodeGitFile.ts` | Cache + ETag + dedup for `GET /spcode/git-file?ref=&path=`; key = `<path>|<ref>` | Render anything, fetch listing / history |
| `useResizableSplit.ts` | Mouse-drag state machine for pane resizing; emits numeric percent | Know about any specific pane content |

### 3.3 `viewMode` extension

```ts
// GitDiffSidebar.vue
type ViewMode = "files" | "diff" | "history" | "docs";

const viewMode = ref<ViewMode>(loadViewMode()); // already exists

function loadViewMode(): ViewMode {
  const v = safeGetItem(VIEW_MODE_STORAGE_KEY);
  if (v === "files" || v === "diff" || v === "history" || v === "docs") return v;
  return "files";
}
```

New tab pill inserted between "Files" and "Git Diff":

```vue
<button
  type="button"
  role="tab"
  :aria-selected="viewMode === 'docs'"
  :aria-label="tm('spcodeProjectLoad.gitDiffSidebar.tabs.docs')"
  :class="[/* ... */]"
  @click="setViewMode('docs')"
>
  <v-icon size="14">mdi-file-document-multiple-outline</v-icon>
</button>
```

`setViewMode` already exists; we just widen its argument type.

### 3.4 `docsRoot` localStorage

```
KEY:    "astrbot.spcode.documentManager.docsPathByUmo"
VALUE:  { "<umo>": "<relative path>", ... }
FORMAT: JSON.stringify
```

**Write** triggers (both in `DocumentPathBar`):
- User blurs the input.
- User presses `Enter`.
- User clicks the reset (↺) button (writes the literal `"docs"`).

**Read** triggers (in `DocumentManager.onMounted` and `watch(() => props.umo)`):
- If the key is missing OR `umo` is not in the map OR the value is the empty string → fall back to `"docs"`.
- If `localStorage` access itself throws (private mode, quota) → mark `storageOK = false`, never write back; UI shows a small `mdi-alert-circle-outline` icon next to the reset button.

**Validation** at write time (`DocumentPathBar.commit()`):
- Relative path only (no leading `/`, no `\`-only, no drive letter, no UNC `\\…`, no `..` segments, non-empty).
- On failure → red inline error, no localStorage write, no `path-change` emit.

```ts
function isValidDocsRoot(p: string): boolean {
  if (!p) return false;
  if (path.isAbsolute(p)) return false;
  if (/^[a-zA-Z]:/.test(p)) return false;     // Windows drive
  if (p.includes("..")) return false;
  if (/^\\\\/.test(p)) return false;          // UNC
  if (p.startsWith("/") || p.startsWith("\\")) return false;
  return true;
}
```

Path coercion at commit: `trim()`; `\\` → `/`; strip trailing `/`. Mid-path slashes preserved so `specs/plans` is valid.

### 3.5 Composables

#### `useSpcodeGitFile.ts`

```ts
type FileRevisionState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: { sha: string; path: string; content: string; isBinary: boolean } }
  | { kind: "error"; reason: string };

export interface UseSpcodeGitFile {
  /** Idempotent fetch. Dedupes by `${path}|${ref}`. Sets state to "loading" then ok/error. */
  fetchRef(path: string, ref: string): Promise<void>;
  getData(path: string, ref: string): GitFileData | null;     // sync, for templates
  getState(path: string, ref: string): FileRevisionState;    // sync, for templates
  invalidateAll(): void;
  dispose(): void;                                           // abort in-flight, drop cache
}
```

Implementation mirrors `useSpcodeGitShow.ts` (already uses `${sha}|${path}` as cache key):
- `inflight: Map<string, AbortController>` for dedup.
- `etagMap: Map<string, string>` per `(umo, worktree, path, ref)`.
- `dataMap: Map<string, GitFileData>` and `stateMap: Map<string, FileRevisionState>` reactive.
- Response shape: `{ content: string; is_binary: boolean; sha: string; path: string; reason: string | null; success: boolean }`.
- `fetchRef` returns early if state is already `ok`, or if the key is in `inflight`.
- `fetchRef` is a no-op when `!spcodeStatus.status.value.umo` and sets `error.reason = "no_project_loaded"`.

#### `useResizableSplit.ts`

```ts
export interface UseResizableSplitOptions {
  initialPercent?: number;       // default 30
  minPercent?: number;           // default 15
  maxPercent?: number;           // default 70
  onPercentChange?: (pct: number) => void;
}

export interface UseResizableSplit {
  percent: Ref<number>;
  isResizing: Ref<boolean>;
  startResize(event: MouseEvent): void;
}
```

Used identically by `FileBrowserView` and `DocumentManager`. Implementation is a copy of `FileBrowserView.startResize / onMouseMove / onMouseUp` lifted into module scope.

### 3.6 Backend endpoints (consumed, defined in spec B)

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/spcode/git-file` | Full content of a file at a given ref. Params: `umo`, `worktree?`, `ref`, `path`. Returns `{ success, reason, content, is_binary, sha, path, elapsed_ms }`. |
| `GET`  | `/spcode/git-log` | **Existing**, now accepts `?path=<rel>` to filter commits by touched path. |
| `POST` | `/spcode/docs` | Create OR **upsert** a docs file at the given relative path. Body: `{ path: string; content: string }`. Returns `{ success, reason, path, sha? }`. |
| `DELETE` | `/spcode/docs` | Delete a docs file at the given relative path. Query/path encodes the path. |
| `PATCH` | `/spcode/docs` | **Stub** in spec A. UI renders the button; click shows a toast "rename not available yet". spec B will add the endpoint in a follow-up. |

All endpoints must repeat the **`isValidDocsRoot` invariants** server-side. Frontend validation is defense-in-depth, not the source of truth.

---

## 4. File-by-file detail

### 4.1 `DocumentManager.vue` — page container

```vue
<script setup lang="ts">
const props = defineProps<{
  worktreePath: string | null;
  umo: string | null;
  projectRoot: string | null;
  isDark?: boolean;
}>();

// Local state (all refs, none emit):
//   docsRoot: Ref<string>           // relative path; default "docs"
//   selectedDoc: Ref<string | null> // relative .md path
//   viewMode: Ref<"raw" | "rendered" | "diff">
//   historyOpen: Ref<boolean>
//   selectedRevision: Ref<string | null>  // null = working tree
//   editMode: Ref<boolean>
//   editBuffer: Ref<string>
//   storageOK: Ref<boolean>
//   pathMissingNotice: Ref<string | null>

// Computed:
//   leftPercent = useResizableSplit({ initialPercent: 30, minPercent: 15, maxPercent: 70 })
//   resolvedRootPath = joinFs(props.projectRoot, docsRoot)  // for useSpcodeFileBrowser

// Initialize docsRoot from localStorage on mount / umo change.
// On pathMissingNotice (backend returns path_not_found): set a 5s countdown
// then emit path-change to "docs".

// Watch:
//   watch(props.umo, () => read docsRoot from localStorage)
//   watch(docsRoot, async (p) => {
//     if (!isValidDocsRoot(p)) return;
//     // Probe by listing the directory; if kind === "error" && reason === "path_not_found"
//     // then set pathMissingNotice.value = p and start 5s countdown.
//   })
//   watch(selectedDoc, () => { editMode = false; selectedRevision = null; editBuffer = "" })

// Methods:
//   onPathChange(newPath: string)  -> write localStorage + docsRoot.value = newPath
//   onTreeNavigate(dirRel)         -> docsRoot = dirRel; selectedDoc = null
//   onTreeSelect(fileRel)          -> selectedDoc = fileRel (only if !editMode || !dirty)
//   onStartEdit()                  -> editMode = true; editBuffer = snapshot
//   onSave(content)                -> POST /spcode/docs; on success close editMode + refresh tree
//   onDelete()                     -> DELETE; on success selectedDoc = null + refresh
//   onRename()                     -> toast "rename not available yet" (stub)
//   onSelectRevision(sha)          -> selectedRevision = sha; viewMode = "rendered"
//   onCompareCurrent(sha)          -> selectedRevision = sha; viewMode = "diff"
//
// Beforeunload guard: if editMode && dirty, show native confirm.
</script>

<template>
  <div class="document-manager">
    <header class="document-manager__header">
      <DocumentPathBar
        :current-path="docsRoot"
        :storage-ok="storageOK"
        default-path="docs"
        @path-change="onPathChange"
      />
      <v-spacer />
      <v-btn v-if="selectedDoc && !editMode" size="small" variant="text" @click="onStartEdit">
        <v-icon size="14">mdi-pencil-outline</v-icon>
        {{ tm("documentManager.editor.edit") }}
      </v-btn>
      <v-btn v-if="selectedDoc && editMode" size="small" variant="text" disabled>
        <v-icon size="14">mdi-rename-outline</v-icon>
        {{ tm("documentManager.editor.rename") }}
      </v-btn>
      <v-btn v-if="selectedDoc" size="small" variant="text" color="error" @click="onDelete">
        <v-icon size="14">mdi-delete-outline</v-icon>
      </v-btn>
      <v-spacer />
      <DocumentViewModeTab
        v-if="selectedDoc"
        v-model="viewMode"
        :has-revision="!!selectedRevision"
        @update:modelValue="viewMode = $event"
      />
    </header>

    <div v-if="pathMissingNotice" class="document-manager__notice document-manager__notice--warn">
      {{ tm("documentManager.tree.pathMissing", { path: docsRoot }) }}
    </div>

    <div class="document-manager__body" :style="{ gridTemplateColumns: `${leftPercent.percent.value}% 4px 1fr` }">
      <DocumentTreePanel
        class="document-manager__left"
        :current-dir="docsRoot"
        :root-path="resolvedRootPath"
        @navigate="onTreeNavigate"
        @select="onTreeSelect"
      />
      <div class="document-manager__splitter" @mousedown="leftPercent.startResize" />
      <section class="document-manager__right">
        <template v-if="!selectedDoc">
          <p class="document-manager__empty">{{ tm("documentManager.noFileSelected") }}</p>
        </template>
        <template v-else-if="editMode">
          <DocumentEditor
            :initial-content="editBuffer"
            :file-relative="selectedDoc"
            :is-saving="isSaving"
            @save="onSave"
            @cancel="onCancelEdit"
            @delete="onDelete"
            @rename="onRename"
          />
        </template>
        <template v-else>
          <div v-if="selectedRevision" class="document-manager__revision-banner">
            {{ tm("documentManager.viewMode.viewingRevision", { sha: selectedRevision.slice(0, 7) }) }}
            <button class="document-manager__revision-back" @click="selectedRevision = null">
              {{ tm("documentManager.viewMode.backToCurrent") }}
            </button>
          </div>
          <DocumentViewModeTab v-if="!selectedRevision" v-model="viewMode" ... />
          <MarkdownView v-if="viewMode === 'rendered'" :source="fileContent" :is-dark="props.isDark" />
          <pre v-else-if="viewMode === 'raw'" class="document-manager__raw">{{ fileContent }}</pre>
          <DiffPreview v-else-if="viewMode === 'diff'" :patch="revisionPatch" :is-dark="props.isDark" />
        </template>
      </section>
    </div>

    <DocumentHistoryPanel
      v-if="selectedDoc && !editMode"
      class="document-manager__history"
      :worktree-path="props.worktreePath"
      :umo="props.umo"
      :file-relative="selectedDoc"
      :current-revision="selectedRevision"
      @select-revision="onSelectRevision"
      @compare-current="onCompareCurrent"
    />
  </div>
</template>
```

### 4.2 `DocumentPathBar.vue` — top path editor

See design §4.2 of the brainstorming notes. Behavior recap:
- Click the displayed text to start editing; `Enter` / `blur` commits, `Esc` cancels.
- Validation runs on commit; failure shows red error inline.
- Reset (↺) button writes `"docs"` directly.
- `storageOK` shows an `mdi-alert-circle-outline` icon with tooltip when localStorage is unavailable; writes silently swallowed.

### 4.3 `DocumentTreePanel.vue` — left pane

```vue
<script setup lang="ts">
const props = defineProps<{
  currentDir: string;
  rootPath: string;
}>();

const emit = defineEmits<{
  (e: "navigate", dirRelative: string): void;
  (e: "select", fileRelative: string): void;
}>();

// Directly composes the existing FileTreeList (extracted from FileBrowserView)
// passing the directory + callbacks. FileTreeList already supports:
//   - breadcrumb click → navigate
//   - directory click  → navigate
//   - .md file click   → select
//   - non-.md files    → visible but not interactive
//
// Pre-breadcrumb for the root: link back to (parent of currentDir). For
// currentDir === "docs" itself, the breadcrumb is just "docs/".
</script>
```

States (rendered by FileTreeList):
- loading → skeleton rows.
- error → "Cannot load directory tree: {reason}" + previous snapshot retained.
- empty → "No `.md` files in this directory."

### 4.4 `DocumentViewModeTab.vue` — three-segment control

```vue
<script setup lang="ts">
const props = defineProps<{
  modelValue: "raw" | "rendered" | "diff";
  hasRevision?: boolean;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: "raw" | "rendered" | "diff"): void;
}>();
// Three buttons: 原文 (raw) | 渲染 (rendered) | 与当前对比 (diff vs current)
// `diff` is disabled when !hasRevision (no historical revision selected).
// Style mirrors the existing scope-pill row (git-diff sidebar) for consistency.
</script>
```

### 4.5 `DocumentHistoryPanel.vue` — commit list

```vue
<script setup lang="ts">
const props = defineProps<{
  worktreePath: string | null;
  umo: string | null;
  fileRelative: string | null;
  currentRevision: string | null;       // null = working tree (highlight placeholder)
}>();
const emit = defineEmits<{
  (e: "select-revision", sha: string): void;
  (e: "compare-current", sha: string): void;
}>();

// Uses the parent's existing useSpcodeGitLog instance.
// watch(() => props.fileRelative, (p) => {
//   if (p) await gitLog.refresh({ ref: "HEAD", n: 50, path: p });
// });

// List rows:
//   - "当前工作树" pseudo row (highlighted when currentRevision === null)
//   - One row per commit: short sha / relative time / author / subject
//   - Each row has two action buttons: [查看此版本] [与当前对比]

// Empty / error states:
//   fileRelative === null   → "Select a document first"
//   commits.length === 0    → "No commits yet for this document"
//   error.reason            → "Cannot read history: <reason>"
</script>
```

### 4.6 `DocumentEditor.vue` — edit area

```vue
<script setup lang="ts">
const props = defineProps<{
  initialContent: string;
  fileRelative: string;
  isSaving: boolean;
  useSimpleTextarea?: boolean;          // optional fallback flag
}>();
const emit = defineEmits<{
  (e: "save", newContent: string): void;
  (e: "cancel"): void;
  (e: "delete"): void;
  (e: "rename", newRelativePath: string): void;
}>();

// buffer = ref(initialContent); dirty = computed(buffer !== initialContent)
// Watch fileRelative: reset buffer (parent should prevent switching while dirty).
// Save button: disabled while !dirty or isSaving.
// Cancel: if dirty, native confirm before discarding.
// Delete: two-step inline confirm (matches the existing file-restore dialog pattern).
// Copy raw button: copyToClipboard(buffer); ephemeral toast.
</script>
```

`CodemirrorHost.vue` (peer file):
```vue
<script setup lang="ts">
const props = defineProps<{ modelValue: string; language?: "markdown" }>();
const emit = defineEmits<{ (e: "update:modelValue", v: string): void }>();

// Lazy-import CodeMirror 6 modules. On failure → set internal `errored = true`
// and DocumentEditor falls back to a <textarea> at the parent level via the
// `:use-simple-textarea="true"` prop wired from a global Pinia / provide.
</script>
```

### 4.7 `MarkdownPipeline.ts` — pure renderer factory

```ts
export interface MarkdownRenderResult {
  /** Sanitized HTML; safe for v-html. */
  html: string;
  /** Highlighted code blocks preserved separately for post-processing
   *  (currently: copy-code button injection). */
  highlightedBlocks: ReadonlyArray<{ index: number; html: string }>;
}

export interface MarkdownRenderOptions {
  highlighter: Highlighter | null;       // null = fence fallback
  theme: "light" | "dark";
  sanitize?: boolean;                    // default true
}

export interface MarkdownRenderer {
  /** Render markdown source → HTML + highlighted blocks. */
  render(source: string, opts: MarkdownRenderOptions): MarkdownRenderResult;
  /** Lazy helper for callers that need to enumerate fence languages
   *  before initializing Shiki. */
  parseSource(source: string): Token[];
  /** Release highlighter resources. */
  dispose(): void;
}

export function createMarkdownRenderer(): MarkdownRenderer;
```

Internals (pulled from `ReadmeDialog.vue`):
1. Single shared `MarkdownIt` instance with `{ html: true, linkify: true, typographer: true, breaks: false }`, `enable(["table", "strikethrough"])`, `table_open/_close` wrapped in `.table-container`.
2. `render(source, opts)`:
   - Parse tokens via `md.parse(source)`.
   - For each `fence` token, eagerly substitute placeholder `<div data-code-block-index="${i}"></div>` + collect highlighted HTML.
   - Run `md.renderer.render(tokens, md.options, env)` to produce raw HTML.
   - `DOMPurify.sanitize(rawHtml, MARKDOWN_SANITIZE_OPTIONS)`.
   - Post-process: heading slug ids, external link `target=_blank rel=noopener noreferrer`.
   - Walk placeholders back in, replacing each with its highlighted block (passed through `CODE_BLOCK_SANITIZE_OPTIONS`).
3. No Vue imports — testable with `node --test`.

#### `MarkdownView.vue`

```vue
<script setup lang="ts">
const props = defineProps<{
  source: string;
  isDark?: boolean;
  containerClass?: string;
}>();

const renderer = ref<MarkdownRenderer | null>(null);
const highlighter = ref<Highlighter | null>(null);
const renderedHtml = ref("");
const lastRenderId = ref(0);

onMounted(async () => {
  const r = createMarkdownRenderer();
  renderer.value = r;
  const tokens = r.parseSource(props.source ?? "");
  const langs = tokens
    .filter((t) => t.type === "fence")
    .map((t) => normalizeShikiLanguage(t.info));
  try {
    highlighter.value = await ensureShikiLanguages(langs);
  } catch (err) {
    console.error("MarkdownView: Shiki init failed", err);
    highlighter.value = null; // fence fallback
  }
  reRender();
});
onBeforeUnmount(() => renderer.value?.dispose());

watch(
  [() => props.source, () => props.isDark],
  reRender,
  { flush: "post" },
);

function reRender() {
  if (!renderer.value) return;
  const renderId = ++lastRenderId.value;
  const out = renderer.value.render(props.source ?? "", {
    highlighter: highlighter.value,
    theme: props.isDark ? "dark" : "light",
  });
  if (renderId === lastRenderId.value) renderedHtml.value = out.html;
}
</script>

<template>
  <div
    class="markdown-body"
    :class="props.containerClass"
    v-html="renderedHtml"
    @click="handleClick"
  />
</template>
```

`handleClick` is the same logic as `ReadmeDialog`: copy-code button click → `copyToClipboard` + 2s success/error icon; `a[href^="#"]` click → `scrollIntoView` of the target id.

Styling: copy the `:deep(.markdown-body)` CSS block verbatim from `ReadmeDialog` so the visual is identical.

### 4.8 i18n additions (`features/chat.json`, three locales)

```jsonc
{
  "spcodeProjectLoad": {
    "gitDiffSidebar": {
      "tabs": {
        "docs": "文档管理"
      }
    },
    "documentManager": {
      "pathBar": {
        "label": "文档目录",
        "editHint": "点击修改路径",
        "resetTitle": "恢复为默认 docs/",
        "invalidPath": "路径无效:必须是项目内的相对路径",
        "storageWarning": "浏览器存储不可用,本次会话结束后保存将失效"
      },
      "tree": {
        "empty": "该目录下没有 .md 文件",
        "noHistory": "此文档还未被提交过任何历史",
        "loadError": "无法加载目录树:{reason}",
        "pathMissing": "路径 '{path}' 不存在,5 秒后回到默认"
      },
      "viewMode": {
        "raw": "原文",
        "rendered": "渲染",
        "diff": "与当前对比",
        "viewingRevision": "正在查看历史版本 {sha}",
        "backToCurrent": "回到当前"
      },
      "history": {
        "title": "历史",
        "currentPlaceholder": "当前工作树",
        "viewThisRevision": "查看此版本",
        "compareWithCurrent": "与当前对比",
        "loadFail": "无法读取历史版本"
      },
      "editor": {
        "newFile": "新建 .md",
        "createFilePlaceholder": "文件名,如 plan.md",
        "filenameInvalid": "文件名必须以 .md 结尾,只允许字母/数字/_/-/空格/. ",
        "filenameExists": "同名文件已存在",
        "edit": "修改",
        "save": "保存",
        "saving": "保存中",
        "cancel": "取消",
        "cancelDirty": "有未保存修改,确定放弃?",
        "delete": "删除",
        "rename": "重命名",
        "renameUnavailable": "重命名功能在后续版本提供",
        "deleteConfirmTitle": "确认删除文档?",
        "deleteConfirmBody": "将删除 {path},不可撤销",
        "saveError": "保存失败",
        "deleteError": "删除失败"
      },
      "newFile": "选择 .md 文件或新建",
      "noFileSelected": "请先选择一个文档"
    }
  }
}
```

`en-US` / `ru-RU` follow the same shape; this spec only contracts the keys; translation may be done by i18n tooling or a follow-up.

---

## 5. Data flow

### 5.1 Read flow — clicking a `.md` file

```
User clicks .md in DocumentTreePanel
  → emit("select", fileRel)
  → DocumentManager.onTreeSelect(fileRel)
      ├─ selectedDoc = fileRel
      ├─ viewMode = "rendered"            // first time
      ├─ selectedRevision = null         // reset
      └─ useSpcodeFileBrowser(fileRel)    // already in tree panel; reuse cached
                                          // for raw "原文" view

User toggles viewMode → raw / rendered / diff (if hasRevision)
  → MarkdownView re-renders (internal watch)
  → or <pre> shows raw text
  → or DiffPreview shows patch (revision vs current)
```

### 5.2 History flow — picking a past revision

```
User clicks [查看此版本] on a row
  → emit("select-revision", sha)
  → DocumentManager.onSelectRevision(sha)
      ├─ selectedRevision = sha
      ├─ viewMode = "rendered" (unless already a non-default mode)
      └─ useSpcodeGitFile.fetchRef(fileRel, sha) → content
                                                     // then MarkdownView

User clicks [与当前对比]
  → emit("compare-current", sha)
  → DocumentManager.onCompareCurrent(sha)
      ├─ selectedRevision = sha
      ├─ viewMode = "diff"
      └─ useSpcodeGitShow.fetchFile(sha, fileRel) → patch (already supported)

User clicks "回到当前" banner link
  → selectedRevision = null
  → useSpcodeFileBrowser (working-tree content) takes over
```

### 5.3 Write flow — editing + saving

```
User clicks [✏️ 修改]
  → onStartEdit()
      ├─ editMode = true
      ├─ editBuffer = useSpcodeFileBrowser data (current raw content)
      └─ beforeunload guard attached (native confirm if dirty)

User types in DocumentEditor
  → buffer mutates locally; isDirty = true

User clicks [保存]
  → emit("save", buffer)
  → DocumentManager.onSave(content)
      ├─ POST /spcode/docs { path, content }
      │    ├─ success → exit editMode; useSpcodeFileBrowser.refresh(); snackbar
      │    └─ error   → keep editMode; red banner + toast
      └─ while in flight: isSaving = true (disables Save button + shows spinner)

User clicks [取消] while dirty
  → emit("cancel")
  → DocumentManager.onCancelEdit()
      ├─ native confirm("有未保存修改,确定放弃?")
      └─ on confirm → editMode = false

User clicks [删除]
  → two-step inline confirm (matches GitDiffSidebar's restore dialog pattern)
  → emit("delete")
  → DocumentManager.onDelete()
      ├─ DELETE /spcode/docs/<encoded path>
      │    ├─ success → selectedDoc = null; refresh tree; snackbar
      │    └─ error   → keep selection; toast "删除失败"
      └─ snackbar duration: 4s
```

### 5.4 Tree navigation

```
User clicks a directory or breadcrumb segment
  → emit("navigate", dirRel)
  → DocumentManager.onTreeNavigate(dirRel)
      ├─ docsRoot = dirRel
      ├─ selectedDoc = null             // leaving any doc means edit mode ends
      └─ if editMode && dirty: native confirm first

User changes path via DocumentPathBar
  → emit("path-change", newPath)
  → DocumentManager.onPathChange(newPath)
      ├─ localStorage write
      ├─ docsRoot = newPath
      └─ selectedDoc = null             // path change → file selection invalid
```

### 5.5 Worktree / project switch

```
Sidebar's worktree or umo changes
  → DocumentManager re-evaluates resolvedRootPath
  → DocumentTreePanel re-queries useSpcodeFileBrowser(newRootPath)
  → FileBrowserLocal state reset (selectedDoc / revision / edit / buffer all dropped)

If editMode && dirty at this moment → native beforeunload confirm (browser-native).
Then proceed to the new project/worktree as if from a fresh open.
```

### 5.6 Component unmount

```
DocumentManager unmount
  → useSpcodeGitFile.dispose() (clears cache + aborts in-flight)
  → MarkdownView's renderer.dispose() (automatic via its own onBeforeUnmount)
  → useResizableSplit removes its document mousemove/mouseup listeners
```

---

## 6. Error handling

| Scenario | Visible behavior | Auto-recovery |
|----------|------------------|---------------|
| Project not loaded (`umo === null`) | Page body shows "请选择项目" placeholder. No fetches issued. | Once UMO is set, hooks fire and data loads. |
| `projectRoot === null` | Same placeholder as above. | Once project root resolves, page loads. |
| `localStorage` unavailable | `mdi-alert-circle-outline` next to reset button + tooltip. Writes silently skipped. | Per-session. |
| `docsRoot` invalid (e.g. user typed `../foo`) | Red inline error in `DocumentPathBar`. No write. | User edits again. |
| `docsRoot` does not exist on disk | Top notice "路径 '{path}' 不存在,5 秒后回到默认", auto-reset to `"docs"` after 5s. | Automatic; user can override. |
| `docsRoot` empty after listing | Tree shows "该目录下没有 .md 文件". Editor button disabled. | User creates a file or changes path. |
| Git history fails (`/spcode/git-log`) | History list shows "无法读取历史: <reason>"; other panes unaffected. | User re-selects file or refreshes. |
| Git historical blob fails | `DocumentHistoryPanel` row shows inline error icon, rest of rows unaffected. | User picks another revision. |
| CodeMirror 6 fails to load | Editor falls back to `<textarea>` (monospace). | Permanent (until page reload). |
| MarkdownView Shiki fails | Whole page still renders; fences use `<pre><code>` fallback. | Permanent. |
| Save returns 4xx | Top red banner "保存失败: <reason>". Editor stays open. | User edits + retries. |
| Save returns 5xx | Same as 4xx + snackbar "保存失败,稍后重试". | User retries. |
| Save success + refresh fails | Snackbar "目录树刷新失败"; content pane shows new value (we just wrote it). | User clicks tree refresh. |
| New file name conflict | Red text "同名文件已存在"; request not sent. | User renames. |
| New file post fails | Optimistic selectedDoc is dropped; toast "新建失败". User can try again. | User retries. |
| Delete fails | Snackbar "删除失败: <reason>"; selectedDoc unchanged. | User retries. |
| Switch worktree/project while `editMode && dirty` | Browser-native `beforeunload` confirm. | User choice. |
| Browser quits while `editMode && dirty` | Same `beforeunload` confirm. | OS behavior. |

---

## 7. Testing matrix

### 7.1 Layer 1 — unit (no DOM, pure TS)

```
tests/MarkdownPipeline.test.ts
  ✓ createMarkdownRenderer() idempotent (returns same instance per call)
  ✓ render("", ...) → empty string HTML, no throw
  ✓ render("# Hello\n\n```ts\nconst a = 1;\n```") → contains <h1> and <pre class="shiki">
  ✓ render("<script>alert(1)</script>") → no <script> in output
  ✓ render("[x](javascript:alert(1))") → href stripped or replaced with about:blank
  ✓ table wrapped in <div class="table-container"><table>
  ✓ http(s):// links get target=_blank rel="noopener noreferrer"
  ✓ highlighter=null → fences render as <pre class="shiki shiki-fallback"><code>
  ✓ race: 2 parallel render() calls, only the last renderId output survives
  ✓ dispose() releases highlighter (no exception on dispose twice)

tests/useSpcodeGitFile.test.ts
  ✓ fetchRef(path, ref) caches result; second call is a no-op
  ✓ Different refs do not collide in cache
  ✓ Aborted fetch leaves state untouched
  ✓ 304 ETag hit keeps previous data; no state change
  ✓ Backend reason="ref_not_found" surfaces as error state
  ✓ dispose() drops all entries and aborts inflight
```

### 7.2 Layer 2 — composables / mounted components

```
tests/useResizableSplit.test.ts (JSDOM)
  ✓ startResize sets isResizing=true and registers document listeners
  ✓ Simulated mousemove updates percent
  ✓ min/max clamping: values outside [min,max] snap to bound
  ✓ Simulated mouseup clears listeners and isResizing=false

tests/DocumentPathBar.test.ts (vue test-utils)
  ✓ "docs" → isValidDocsRoot true
  ✓ "../foo" → invalid → error message shows, no emit
  ✓ Enter commits, Esc reverts
  ✓ Reset (↺) → draft === "docs"
  ✓ StorageOK=false hides reset button's storage write attempts
  ✓ storageOK=true → after Enter, localStorage is updated
```

### 7.3 Layer 3 — components with state

```
tests/DocumentHistoryPanel.test.ts
  ✓ fileRelative=null → empty-state shown
  ✓ commits.length=0 (but fileRelative set) → noHistory shown
  ✓ Clicking a row's [查看此版本] emit("select-revision", sha)
  ✓ Clicking a row's [与当前对比] emit("compare-current", sha)
  ✓ "当前工作树" pseudo row reflects currentRevision === null → highlighted

tests/DocumentEditor.test.ts
  ✓ dirty=false → Save button disabled
  ✓ Cancel while dirty requires confirm
  ✓ Delete two-step inline confirm
  ✓ useSimpleTextarea=true → renders <textarea>, no CodeMirror import attempted
  ✓ Watch on fileRelative resets buffer
  ✓ Copy-raw button calls clipboard API and shows ephemeral feedback

tests/DocumentTreePanel.test.ts (mock useSpcodeFileBrowser)
  ✓ Directory click emit("navigate", dirRel)
  ✓ .md click emit("select", fileRel)
  ✓ Non-.md is visible but not interactive
  ✓ loading → skeleton
  ✓ error → error message + previous snapshot retained
  ✓ empty → empty message
```

### 7.4 Layer 4 — integration (light)

```
tests/DocumentManager.integration.test.ts (@vue/test-utils + happy-dom)
  ✓ Selecting a file sets selectedDoc and switches to "rendered" by default
  ✓ [与当前对比] switches to "diff" mode and emits fetchFile
  ✓ [查看此版本] switches to "rendered" and triggers fetchRef
  ✓ [回到当前] banner link clears selectedRevision
  ✓ Path-bar Enter updates docsRoot and clears selectedDoc
  ✓ Save POST → on success, editMode closes; tree refresh fires
  ✓ Delete DELETE → on success, selectedDoc cleared and tree refresh fires
  ✓ editMode active + tree click on a different file triggers native confirm
```

---

## 8. Out of scope (deferred)

- **Mermaid diagram rendering** (` ```mermaid ` blocks): not in spec A. Could be added later by extending `MarkdownPipeline` with a fence renderer plugin. Comments in this spec encourage future-proofing the renderer hooks.
- **Full-text search across docs**: separate sub-tab feature; the existing `FileBrowserView` already has `SearchPanel` over the working tree, which can be lifted to docs in a later spec.
- **YAML frontmatter parsing / collapsing**: not implemented. Markdown renders frontmatter as a code fence by default; this is acceptable for spec/plan docs.
- **Multi-doc concurrent editing**: spec A is single-buffer (current file). The 4-layer test matrix covers this.
- **Right-pane sticky-scroll position across viewMode toggles**: not preserved by spec A.
- **Templates / scaffolds for new docs**: future spec.
- **Rename endpoint and UI**: spec B will deliver the endpoint; spec A renders the button as disabled stub.

---

## 9. Open questions to confirm before writing-plans

1. **CodeMirror 6 dependencies weight** — accepted at ~200KB gzip. Plan stage re-evaluates if bundle budget tightens; fallback is plain `<textarea>` + soft-wrap + line-number sidebar. **Confirm acceptance.**
2. **Editor rename button as disabled stub** — confirmed in §4.1 and §4.6. **Confirm.**
3. **Save = working tree only** — confirmed in §2 decision 12 and §5.3. **Confirm.**
4. **`docsRoot` default = literal `"docs"`** — confirmed in §3.4. The path is never persisted server-side. **Confirm.**
5. **i18n: only zh-CN filled in for spec A; en-US / ru-RU placeholder strings to be supplied by i18n tooling or follow-up PR** — **Confirm.**
6. **`FileTreeList` is shared between `FileBrowserView` and `DocumentTreePanel`** — confirmed in §3.1 + §4.3. The visual tree-rendering code lives in one file from now on. **Confirm.**

---

## 10. Acceptance criteria

This spec is complete when:

- [ ] All 8 new Vue components, 1 new shared composable, 1 new shared pipeline exist and are referenced by `GitDiffSidebar.vue`.
- [ ] Sub-tab pill clickable; selecting "Documents" shows the panel with path bar, left tree, and empty-state right pane.
- [ ] Changing the path persists across page reload for the same `umo`.
- [ ] Clicking any `.md` in the tree shows the file in "rendered" by default with a view-mode tab strip.
- [ ] "rendered" view uses the same HTML output that `ReadmeDialog` produces for the same Markdown source (visual regression acceptable manually; no diff required).
- [ ] "raw" view shows the file's raw text in a `<pre>`.
- [ ] "diff" view is reachable only after picking a historical revision; shows a DiffPreview with the patch.
- [ ] Picking a historical revision: shows banner with sha + "回到当前" link.
- [ ] Per-file commit list filters to commits that touched this file (backend `?path=`).
- [ ] Clicking "修改" enters edit mode with CodeMirror (textarea fallback path works).
- [ ] Clicking "保存" writes only to working tree (no auto `git add`); the change appears in the Git Diff tab as an unstaged modification.
- [ ] Clicking "删除" requires a two-step inline confirm; success clears selection and refreshes tree.
- [ ] Clicking "重命名" shows a "not available yet" toast (button disabled).
- [ ] Refresh and reload behaviors correctly snapshot/restore localStorage path by UMO.
- [ ] All 4 test layers pass in CI (`pnpm test`).
- [ ] `pnpm lint` and `pnpm typecheck` clean for the new code paths.
- [ ] All i18n keys for `documentManager.*` exist in `zh-CN`; placeholders for the other locales are either translated (preferred) or noted in the PR.
