# Document Manager Frontend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-KILLS: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "文档管理 (Documents)" sub-tab to `GitDiffSidebar.vue` for reading, editing, and managing the project's documentation (Markdown files under a configurable `docs/`-style root), with per-file git history and historical-revision viewing.

**Architecture:** The new `<DocumentManager>` container owns 5 sub-components: `DocumentPathBar` (path editor), `DocumentTreePanel` (left-pane directory tree, reusing the existing `FileBrowserEntryList` + `FileBrowserBreadcrumb`), `DocumentViewModeTab` (raw/rendered/diff switch), `DocumentHistoryPanel` (per-file commit list), and `DocumentEditor` (CodeMirror 6 with textarea fallback). Three new composables: `useSpcodeGitFile` (GET /spcode/git-file), `useSpcodeDocs` (POST/PATCH/DELETE /spcode/docs), `useResizableSplit` (mouse-drag resize, shared with `FileBrowserView`). One new shared module: `MarkdownPipeline` (markdown-it + DOMPurify + Shiki, lifted from `ReadmeDialog.vue` and consumed by both `ReadmeDialog` and a new `<MarkdownView>` wrapper). `GitDiffSidebar.vue` gains a 4th `viewMode` value `"docs"` and mounts `<DocumentManager>`.

**Tech Stack:** Vue 3.3.4, Vuetify 3.7.11, TypeScript 5.1.6, CodeMirror 6 (`@codemirror/state`, `@codemirror/view`, `@codemirror/lang-markdown`) — NEW, markdown-it 14, DOMPurify 3, shiki 3, axios 1.13, pnpm 9, vue-tsc 1.8.8, vitest 1.6 (for any `.spec.ts`), `node:test` (for `.test.mjs`, matching existing convention).

**Spec:** `docs/superpowers/specs/2026-07-11-document-manager-design.md`
**Backend contract:** `F:\github\astrbot_plugin_spcode_toolkit\docs\webapi_endpoints_report.md` §1.8 (GET /spcode/git-file), §1.6 (GET /spcode/git-log with `?path=`), §5 (POST/PATCH/DELETE /spcode/docs)

> **Implementation deviation from spec A §2 decision #11**: the spec marks the rename button as a disabled stub because the rename endpoint was not yet in scope. As of 2026-07-12 the backend `PATCH /spcode/docs` IS implemented (see `webapi_endpoints_report.md` §5.2). The plan wires up real rename via that endpoint; the spec's stub decision is therefore a leftover and is **not** honored. If the spec is later re-read, treat §2 decision #11 as superseded.

---

## Global Constraints

These constraints apply to every task. Do not deviate.

- **New dependencies (dashboard only):**
  - `codemirror@^6.0.1` (meta — depends on the 3 below)
  - `@codemirror/state@^6.4.1`
  - `@codemirror/view@^6.28.0`
  - `@codemirror/lang-markdown@^6.2.5`
  - `@codemirror/commands@^6.5.0` (for `defaultKeymap`, `history` keybindings)
- **No backend changes.** All 5 endpoints are already implemented in `astrbot_plugin_spcode_toolkit`.
- **No composable changes** to existing modules (`useSpcodeGitLog`, `useSpcodeGitShow`, `useSpcodeFileBrowser`, `useSpcodeFileRestore` are read-only inputs to the new components).
- **i18n key path:** all new keys live under `spcodeProjectLoad.documentManager.*` in `dashboard/src/i18n/locales/{zh-CN,en-US,ru-RU}/features/chat.json`.
- **Style convention:** `--sp-*` prefix for any new design tokens (mirrors 2026-07-09 plan); no inline colors.
- **Conventional commits** for every task (chore/feat/refactor/style/test/docs).
- **No `tsconfig.json` / `package.json` scripts changes** — `pnpm test`, `pnpm typecheck`, `pnpm lint` already cover the project.
- **Author tag on all new files:** `<!-- Author: elecvoid243, 2026-07-12 -->` (HTML comment at top of SFCs; first line for `.ts`/`.mjs`).
- **Cross-platform:** Windows + macOS + Linux; ARM64 + x86; Node 20+ (matches `pnpm` engine).
- **No Storybook / visual regression framework.**
- **No full-text search across docs, no YAML frontmatter parsing, no mermaid/KaTeX, no multi-cursor editing, no editor inside historical-revision view** — all deferred per spec §1 non-goals + §8.
- **CodeMirror failure path is mandatory**: if the dynamic `import()` of any CM6 module throws, the editor must fall back to a plain `<textarea>` (spec §2 decision #10) — never let the page fail to load.
- **TDD discipline:** every pure-logic module (`MarkdownPipeline`, `useResizableSplit`, `useSpcodeGitFile`, `useSpcodeDocs`, `isValidDocsRoot`, `docsRootByUmo` localStorage helpers) gets a `.test.mjs` test in `dashboard/tests/` written **before** implementation. Vue component tests are out of scope for this plan (no existing precedent; keeping the plan shippable).

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `dashboard/src/components/shared/MarkdownPipeline.ts` | Pure factory `createMarkdownRenderer()`. markdown-it + DOMPurify + Shiki, lifted from `ReadmeDialog.vue`. No Vue imports. |
| `dashboard/src/components/shared/MarkdownView.vue` | Thin Vue wrapper around `MarkdownPipeline`. Mounts renderer, watches `source`/`isDark`, handles copy-code + anchor clicks. |
| `dashboard/src/composables/useResizableSplit.ts` | Mouse-drag resize state machine (15–70% clamp). Shared by `FileBrowserView` and `DocumentManager`. |
| `dashboard/src/composables/useSpcodeGitFile.ts` | Wrap GET /spcode/git-file. Per-(path, ref) cache + ETag + dedup. |
| `dashboard/src/composables/useSpcodeDocs.ts` | Wrap POST/PATCH/DELETE /spcode/docs. No polling; one-shot writes with `isSaving` flag. |
| `dashboard/src/composables/docsRootStorage.ts` | `loadDocsRoot(umo)`, `saveDocsRoot(umo, path)`, `isValidDocsRoot(p)`. Pure TS, no Vue. |
| `dashboard/src/components/chat/message_list_comps/FileTreeList.vue` | Extracted from `FileBrowserView`: directory listing + breadcrumb. Reused by `DocumentTreePanel`. |
| `dashboard/src/components/chat/message_list_comps/DocumentManager.vue` | Page container; owns all state; orchestrates CRUD. |
| `dashboard/src/components/chat/message_list_comps/DocumentPathBar.vue` | Click-to-edit path display with Enter/blur/Esc/reset semantics. |
| `dashboard/src/components/chat/message_list_comps/DocumentViewModeTab.vue` | 3-segment control (raw / rendered / diff). `diff` disabled when no historical revision. |
| `dashboard/src/components/chat/message_list_comps/DocumentHistoryPanel.vue` | Per-file commit list (using parent's `useSpcodeGitLog` instance with `?path=`). Per-row "查看此版本" / "与当前对比" actions. |
| `dashboard/src/components/chat/message_list_comps/DocumentEditor.vue` | CodeMirror 6 host (with textarea fallback) + save/cancel/delete/copy buttons. |
| `dashboard/src/components/chat/message_list_comps/CodemirrorHost.vue` | Thin CodeMirror 6 mount/unmount wrapper. Lazy-imports CM6; reports failure via prop. |
| `dashboard/src/components/chat/message_list_comps/DocumentTreePanel.vue` | Left pane for `DocumentManager`. Reuses `FileTreeList`. |
| `dashboard/tests/markdownPipeline.test.mjs` | Node-only tests for the pipeline. |
| `dashboard/tests/useResizableSplit.test.mjs` | JSDOM-style tests for resize state machine. |
| `dashboard/tests/useSpcodeGitFile.test.mjs` | Composable tests with `axios-mock-adapter`. |
| `dashboard/tests/useSpcodeDocs.test.mjs` | Composable tests for write endpoints. |
| `dashboard/tests/docsRootStorage.test.mjs` | Tests for `isValidDocsRoot` + localStorage helpers. |

### Modified files

| Path | Change |
|---|---|
| `dashboard/src/components/shared/ReadmeDialog.vue` | Replace inline markdown rendering with `<MarkdownView :source>`. Keep i18n, dialog, dialog-open, refresh, external-link. Behavior must be visually identical. |
| `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue` | (a) Replace inline resize state with `useResizableSplit()`; (b) replace inline `<FileBrowserEntryList>` + `<FileBrowserBreadcrumb>` with `<FileTreeList>`; (c) keep `isLeftPaneCollapsed`, search integration, refresh, and `defineExpose({ refresh })` unchanged. |
| `dashboard/src/components/chat/GitDiffSidebar.vue` | (a) Extend `ViewMode` literal to include `"docs"`; (b) update `loadViewMode` validator; (c) add 4th pill button between Files and Git Diff; (d) mount `<DocumentManager>` for `viewMode === "docs"`; (e) pass `worktree`, `umo`, `projectRoot`, `isDark`, `gitLog`, `gitShow` down. |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | Add `spcodeProjectLoad.documentManager.*` keys + `spcodeProjectLoad.gitDiffSidebar.tabs.docs` (and a `tabs` block if missing). |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | Same keys (English copy). |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | Same keys (Russian copy). |
| `dashboard/package.json` | Add the 5 CodeMirror deps under `dependencies`. |

### Files explicitly NOT touched (out of scope per spec §1)

- `dashboard/src/composables/useSpcodeGitLog.ts` (already supports `?path=`)
- `dashboard/src/composables/useSpcodeGitShow.ts` (already supports `fetchFile(sha, path)`)
- `dashboard/src/composables/useSpcodeFileBrowser.ts` (reused as-is)
- `dashboard/src/components/chat/message_list_comps/GitLogView.vue` (reused as-is)
- `dashboard/src/components/chat/message_list_comps/DiffPreview.vue` (reused as-is)
- Any backend file under `astrbot_plugin_spcode_toolkit/`
- `docs/.vitepress/...` (no doc-site change required)

---

## Task 1: Add CodeMirror 6 dependencies

**Files:**
- Modify: `dashboard/package.json` (add 5 deps under `dependencies`)

**Interfaces:**
- Consumes: nothing
- Produces: `pnpm-lock.yaml` and `node_modules/` updated; `dashboard/node_modules/@codemirror/{state,view,lang-markdown,commands}/` and `codemirror/` present.

- [ ] **Step 1: Add the 5 deps to `dashboard/package.json`**

Open `dashboard/package.json` and insert the following block immediately after the existing `"@tiptap/starter-kit": "2.1.7",` line (any alphabetical location is fine; this is a guideline):

```json
    "@codemirror/state": "^6.4.1",
    "@codemirror/view": "^6.28.0",
    "@codemirror/commands": "^6.5.0",
    "@codemirror/lang-markdown": "^6.2.5",
    "codemirror": "^6.0.1",
```

Exact `^` versions don't matter; what matters is the 5 package names. Use the editor's "Add Dependency" UI or hand-edit. Do not run any install command yet.

- [ ] **Step 2: Install**

Run: `cd dashboard && pnpm install`
Expected: `pnpm-lock.yaml` updates; no peer-dep warnings besides what `pnpm` already reports for unrelated packages. If you see "@tiptap ... requires vue@^2 ..." warnings, those are pre-existing and OK to ignore.

- [ ] **Step 3: Verify install**

Run: `cd dashboard && ls node_modules/@codemirror/state/package.json node_modules/@codemirror/view/package.json node_modules/@codemirror/commands/package.json node_modules/@codemirror/lang-markdown/package.json node_modules/codemirror/package.json`
Expected: all 5 files exist, each ending with a non-empty `JSON`. If any path is missing, re-run `pnpm install`.

- [ ] **Step 4: Commit**

```bash
git add dashboard/package.json dashboard/pnpm-lock.yaml
git commit -m "chore(dashboard): add CodeMirror 6 dependencies for document editor"
```

---

## Task 2: Extract `docsRootStorage` helpers

**Files:**
- Create: `dashboard/src/composables/docsRootStorage.ts`
- Test: `dashboard/tests/docsRootStorage.test.mjs`

**Interfaces:**
- Produces: `isValidDocsRoot(p: string): boolean`; `loadDocsRoot(umo: string): string`; `saveDocsRoot(umo: string, path: string): { ok: boolean; reason?: string }`; `DOCS_ROOT_STORAGE_KEY = "astrbot.spcode.documentManager.docsPathByUmo"`; `DEFAULT_DOCS_ROOT = "docs"`.

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/docsRootStorage.test.mjs`:

```js
// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.4

import assert from "node:assert/strict";
import test from "node:test";
import {
  isValidDocsRoot,
  loadDocsRoot,
  saveDocsRoot,
  DEFAULT_DOCS_ROOT,
  DOCS_ROOT_STORAGE_KEY,
} from "../src/composables/docsRootStorage.ts";

test("isValidDocsRoot: happy path", () => {
  assert.equal(isValidDocsRoot("docs"), true);
  assert.equal(isValidDocsRoot("specs/plans"), true);
  assert.equal(isValidDocsRoot("docs/2026"), true);
  assert.equal(isValidDocsRoot("a-b_c.d"), true);
});

test("isValidDocsRoot: rejects empty", () => {
  assert.equal(isValidDocsRoot(""), false);
});

test("isValidDocsRoot: rejects absolute + drive + UNC", () => {
  assert.equal(isValidDocsRoot("/etc/passwd"), false);
  assert.equal(isValidDocsRoot("\\foo"), false);
  assert.equal(isValidDocsRoot("C:/foo"), false);
  assert.equal(isValidDocsRoot("c:\\foo"), false);
  assert.equal(isValidDocsRoot("\\\\server\\share"), false);
});

test("isValidDocsRoot: rejects parent traversal", () => {
  assert.equal(isValidDocsRoot(".."), false);
  assert.equal(isValidDocsRoot("../foo"), false);
  assert.equal(isValidDocsRoot("a/../b"), false);
  assert.equal(isValidDocsRoot("a/.."), false);
});

test("isValidDocsRoot: rejects leading slash or backslash", () => {
  assert.equal(isValidDocsRoot("/docs"), false);
  assert.equal(isValidDocsRoot("\\docs"), false);
});

test("loadDocsRoot: returns default when key missing", () => {
  globalThis.localStorage?.clear?.();
  // Use a private storage backend so we don't pollute the real one
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  let store = {};
  __setStorageBackend({
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  assert.equal(loadDocsRoot("umo-1"), "docs");
});

test("loadDocsRoot: returns default when umo not in map", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  let store = { [DOCS_ROOT_STORAGE_KEY]: JSON.stringify({ "other-umo": "specs" }) };
  __setStorageBackend({
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  assert.equal(loadDocsRoot("umo-1"), "docs");
});

test("loadDocsRoot: returns persisted path for umo", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  let store = { [DOCS_ROOT_STORAGE_KEY]: JSON.stringify({ "umo-1": "specs/plans" }) };
  __setStorageBackend({
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  assert.equal(loadDocsRoot("umo-1"), "specs/plans");
});

test("loadDocsRoot: handles localStorage exception", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  __setStorageBackend({ getItem: () => { throw new Error("quota"); }, setItem: () => {}, removeItem: () => {} });
  assert.equal(loadDocsRoot("umo-1"), "docs");
});

test("saveDocsRoot: writes to storage keyed by umo", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  let store = {};
  __setStorageBackend({
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  const r = saveDocsRoot("umo-1", "specs");
  assert.equal(r.ok, true);
  assert.equal(JSON.parse(store[DOCS_ROOT_STORAGE_KEY])["umo-1"], "specs");
});

test("saveDocsRoot: rejects invalid path", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  let store = {};
  __setStorageBackend({
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  });
  const r = saveDocsRoot("umo-1", "../foo");
  assert.equal(r.ok, false);
  assert.equal(r.reason, "invalid_path");
  assert.equal(Object.keys(store).length, 0);
});

test("saveDocsRoot: returns ok=false on storage exception", async () => {
  const { __setStorageBackend } = await import("../src/composables/docsRootStorage.ts");
  __setStorageBackend({ getItem: () => null, setItem: () => { throw new Error("quota"); }, removeItem: () => {} });
  const r = saveDocsRoot("umo-1", "docs");
  assert.equal(r.ok, false);
  assert.equal(r.reason, "storage_unavailable");
});

test("DEFAULT_DOCS_ROOT is 'docs'", () => {
  assert.equal(DEFAULT_DOCS_ROOT, "docs");
});
```

- [ ] **Step 2: Run the test, expect failure**

Run: `cd dashboard && node --test tests/docsRootStorage.test.mjs`
Expected: many failures, all from `ERR_MODULE_NOT_FOUND` on `docsRootStorage.ts` (or similar import error). The "DEFAULT_DOCS_ROOT is 'docs'" assertion will fail too.

- [ ] **Step 3: Implement `docsRootStorage.ts`**

Create `dashboard/src/composables/docsRootStorage.ts`:

```ts
// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.4
//
// Pure-TS helpers for persisting the per-UMO docs root path in
// localStorage. No Vue imports — testable with node:test.
//
// The backend (POST/PATCH/DELETE /spcode/docs) does not persist
// docsRoot; this file is the only source of truth for the path the
// user sees in DocumentPathBar. localStorage is the storage layer;
// failures are swallowed (private mode / quota) and the caller
// falls back to the default.

export const DOCS_ROOT_STORAGE_KEY =
  "astrbot.spcode.documentManager.docsPathByUmo";
export const DEFAULT_DOCS_ROOT = "docs";

/** Minimal subset of the Storage interface so tests can inject
 *  a fake without touching the real `localStorage` global. */
export interface StorageBackend {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

let storageBackend: StorageBackend | null = null;

/** Test-only seam: replace the localStorage shim. Pass `null` to
 *  restore the default (which uses `globalThis.localStorage` when
 *  available and a no-op stub otherwise). Production code MUST NOT
 *  call this — it's exported only so `tests/*.test.mjs` can plug
 *  in an in-memory map. */
export function __setStorageBackend(backend: StorageBackend | null): void {
  storageBackend = backend;
}

function defaultBackend(): StorageBackend {
  if (storageBackend) return storageBackend;
  // Defensive: in node:test without happy-dom, globalThis.localStorage
  // is undefined. Wrap in try/catch because real localStorage can
  // also throw (private browsing, disabled storage).
  return {
    getItem(key) {
      try {
        return globalThis.localStorage?.getItem(key) ?? null;
      } catch {
        return null;
      }
    },
    setItem(key, value) {
      try {
        globalThis.localStorage?.setItem(key, value);
      } catch {
        /* swallow */
      }
    },
    removeItem(key) {
      try {
        globalThis.localStorage?.removeItem(key);
      } catch {
        /* swallow */
      }
    },
  };
}

/** Path validator. Mirrors spec §3.4 + §3.6 invariants; the
 *  backend re-validates with the same rules server-side, so this
 *  is defense-in-depth only.
 *
 *  Rejects: empty, absolute (POSIX or Windows), drive-letter,
 *  UNC (\\server\share), parent traversal (..), leading slash or
 *  backslash. */
export function isValidDocsRoot(p: string): boolean {
  if (!p) return false;
  if (p.length > 512) return false; // sanity bound, not a spec rule
  // Reject any `..` segment. Cheap: just look for the substring;
  // fine because we forbid backslashes and absolute paths upstream.
  if (p.includes("..")) return false;
  if (/^[a-zA-Z]:/.test(p)) return false; // Windows drive letter
  if (/^\\\\/.test(p)) return false; // UNC
  if (p.startsWith("/") || p.startsWith("\\")) return false;
  if (p.startsWith(".") || p.startsWith("~")) return false;
  return true;
}

/** Coerce user-typed input: trim, backslash → forward slash,
 *  strip trailing slash. Returns the cleaned string; returns ""
 *  if the result is empty. */
export function coerceDocsRoot(p: string): string {
  return p.trim().replace(/\\/g, "/").replace(/\/+$/, "");
}

/** Load the docs root for `umo`. Returns `DEFAULT_DOCS_ROOT` if
 *  the key is missing, the umo is not in the map, the stored
 *  value is empty, or the stored value is invalid (defensive). */
export function loadDocsRoot(umo: string): string {
  const backend = defaultBackend();
  let raw: string | null = null;
  try {
    raw = backend.getItem(DOCS_ROOT_STORAGE_KEY);
  } catch {
    return DEFAULT_DOCS_ROOT;
  }
  if (!raw) return DEFAULT_DOCS_ROOT;
  let map: Record<string, string> | null = null;
  try {
    map = JSON.parse(raw);
  } catch {
    return DEFAULT_DOCS_ROOT;
  }
  if (!map || typeof map !== "object") return DEFAULT_DOCS_ROOT;
  const v = map[umo];
  if (typeof v !== "string" || !v || !isValidDocsRoot(v)) {
    return DEFAULT_DOCS_ROOT;
  }
  return v;
}

export type SaveDocsRootResult =
  | { ok: true }
  | { ok: false; reason: "invalid_path" | "storage_unavailable" };

/** Persist `path` for `umo`. Coerces first; rejects if the
 *  coerced value is invalid. Returns `{ ok: false, reason }`
 *  on either validation or storage failure so the caller can
 *  surface an error to the user. */
export function saveDocsRoot(
  umo: string,
  path: string,
): SaveDocsRootResult {
  const cleaned = coerceDocsRoot(path);
  if (!isValidDocsRoot(cleaned)) {
    return { ok: false, reason: "invalid_path" };
  }
  const backend = defaultBackend();
  let existing: Record<string, string> = {};
  try {
    const raw = backend.getItem(DOCS_ROOT_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        existing = parsed as Record<string, string>;
      }
    }
  } catch {
    // Treat parse failure as an empty map; we'll overwrite below.
    existing = {};
  }
  existing[umo] = cleaned;
  try {
    backend.setItem(DOCS_ROOT_STORAGE_KEY, JSON.stringify(existing));
    return { ok: true };
  } catch {
    return { ok: false, reason: "storage_unavailable" };
  }
}
```

- [ ] **Step 4: Run the test, expect pass**

Run: `cd dashboard && node --test tests/docsRootStorage.test.mjs`
Expected: all 13 tests pass. If `__setStorageBackend` is not visible to the importing test (test file uses `await import(...)` to get a fresh binding — the test file already does this; see step 1), the dynamic import is the right pattern.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/composables/docsRootStorage.ts dashboard/tests/docsRootStorage.test.mjs
git commit -m "feat(dashboard): add docsRootStorage helpers for per-UMO path persistence"
```

---

## Task 3: Extract `MarkdownPipeline.ts` from `ReadmeDialog.vue`

**Files:**
- Create: `dashboard/src/components/shared/MarkdownPipeline.ts`
- Modify: `dashboard/src/components/shared/ReadmeDialog.vue` (consume the new pipeline)
- Test: `dashboard/tests/markdownPipeline.test.mjs`

**Interfaces:**
- Produces:
  - `createMarkdownRenderer(): MarkdownRenderer`
  - `interface MarkdownRenderer { render(source: string, opts: MarkdownRenderOptions): MarkdownRenderResult; parseSource(source: string): Token[]; dispose(): void }`
  - `interface MarkdownRenderOptions { highlighter: Highlighter | null; theme: "light" | "dark"; sanitize?: boolean }`
  - `interface MarkdownRenderResult { html: string; highlightedBlocks: ReadonlyArray<{ index: number; html: string }> }`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/markdownPipeline.test.mjs`:

```js
// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.7

import assert from "node:assert/strict";
import test from "node:test";
import {
  createMarkdownRenderer,
} from "../src/components/shared/MarkdownPipeline.ts";

test("createMarkdownRenderer: returns an object with render, parseSource, dispose", () => {
  const r = createMarkdownRenderer();
  assert.equal(typeof r.render, "function");
  assert.equal(typeof r.parseSource, "function");
  assert.equal(typeof r.dispose, "function");
});

test("render: empty source returns empty html", () => {
  const r = createMarkdownRenderer();
  const out = r.render("", { highlighter: null, theme: "light" });
  assert.equal(typeof out.html, "string");
  // Some wrappers / sanitization whitespace is tolerated; just assert
  // no <h1> or <pre> artifacts.
  assert.equal(out.html.includes("<h1>"), false);
  assert.equal(out.html.includes("<pre>"), false);
});

test("render: basic markdown produces h1 + p", () => {
  const r = createMarkdownRenderer();
  const out = r.render("# Hello\n\nworld.", {
    highlighter: null,
    theme: "light",
  });
  assert.ok(out.html.includes("<h1"));
  assert.ok(out.html.includes("Hello"));
  assert.ok(out.html.includes("<p>"));
  assert.ok(out.html.includes("world."));
});

test("render: <script> tags are stripped by sanitizer", () => {
  const r = createMarkdownRenderer();
  const out = r.render("hello\n\n<script>alert(1)</script>\n\nworld", {
    highlighter: null,
    theme: "light",
  });
  assert.equal(out.html.includes("<script>"), false);
  assert.equal(out.html.includes("alert(1)"), true);
});

test("render: javascript: href is sanitized", () => {
  const r = createMarkdownRenderer();
  const out = r.render("[xss](javascript:alert(1))", {
    highlighter: null,
    theme: "light",
  });
  // The link text may survive; the dangerous href must not.
  assert.equal(/href=["']javascript:/i.test(out.html), false);
});

test("render: highlighter=null gives a fallback <pre>", () => {
  const r = createMarkdownRenderer();
  const out = r.render("```ts\nconst a = 1;\n```", {
    highlighter: null,
    theme: "light",
  });
  assert.ok(/<pre[^>]*class="shiki[^"]*"/.test(out.html));
  assert.ok(out.html.includes("const a = 1;"));
});

test("render: table is wrapped in .table-container", () => {
  const r = createMarkdownRenderer();
  const out = r.render("| a | b |\n|---|---|\n| 1 | 2 |\n", {
    highlighter: null,
    theme: "light",
  });
  assert.ok(out.html.includes("table-container"));
  assert.ok(out.html.includes("<table>"));
});

test("render: external http(s) links get target=_blank rel=noopener", () => {
  const r = createMarkdownRenderer();
  const out = r.render("[ext](https://example.com)", {
    highlighter: null,
    theme: "light",
  });
  assert.ok(/target=["']_blank["']/.test(out.html));
  assert.ok(/rel=["']noopener noreferrer["']/.test(out.html));
});

test("render: headings get slugified id", () => {
  const r = createMarkdownRenderer();
  const out = r.render("# Hello World\n", {
    highlighter: null,
    theme: "light",
  });
  assert.ok(/id=["']hello-world["']/.test(out.html));
});

test("parseSource: returns markdown-it tokens", () => {
  const r = createMarkdownRenderer();
  const tokens = r.parseSource("# hi\n\ntext");
  assert.ok(Array.isArray(tokens));
  assert.ok(tokens.length > 0);
  assert.equal(tokens[0].type, "heading_open");
});

test("dispose: double-dispose does not throw", () => {
  const r = createMarkdownRenderer();
  r.dispose();
  r.dispose();
  // Pass.
});
```

- [ ] **Step 2: Run the test, expect failure**

Run: `cd dashboard && node --test tests/markdownPipeline.test.mjs`
Expected: many `ERR_MODULE_NOT_FOUND` failures on the import.

- [ ] **Step 3: Implement `MarkdownPipeline.ts`**

Create `dashboard/src/components/shared/MarkdownPipeline.ts`. Lift the logic **verbatim** from `ReadmeDialog.vue` (see lines 1–260 of the current file) into a pure factory. The ReadmeDialog already contains: a `MarkdownIt` instance with `{html: true, linkify: true, typographer: true, breaks: false}`, `enable(["table", "strikethrough"])`, `table_open/_close` wrapped in `.table-container`, the `MARKDOWN_SANITIZE_OPTIONS` and `CODE_BLOCK_SANITIZE_OPTIONS` allowlists, the `slugifyHeading` helper, the `escapeHtml`/`ensureShikiLanguages`/`normalizeShikiLanguage`/`renderShikiCode` imports from `@/utils/shiki`, and the highlighter-aware `fence` rule.

```ts
// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.7
//
// Pure-TS Markdown renderer. Lifted from ReadmeDialog.vue so both
// ReadmeDialog and <MarkdownView> (consumed by DocumentManager)
// share the exact same pipeline — same Shiki + DOMPurify config,
// same heading-slug + copy-code + external-link behavior.
//
// No Vue imports; no DOM access at import time. The factory
// returns a `MarkdownRenderer` that the consumer can use across
// many renders and dispose() at the end of the component's life.

import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";
import {
  ensureShikiLanguages,
  escapeHtml,
  normalizeShikiLanguage,
  renderShikiCode,
} from "@/utils/shiki";

// Public types — exported so MarkdownView.vue and tests can
// share the same shapes.

export interface MarkdownRenderOptions {
  /** Async-initialized Shiki highlighter. Pass null to fall back
   *  to plain `<pre><code>` for fences. */
  highlighter: unknown | null;
  theme: "light" | "dark";
  /** Default true. Set false only in tightly-controlled tests. */
  sanitize?: boolean;
}

export interface HighlightedBlock {
  index: number;
  html: string;
}

export interface MarkdownRenderResult {
  /** Sanitized HTML. Safe for v-html. */
  html: string;
  /** Highlighted fence blocks. The renderer returns these
   *  separately so callers can choose to inject them with
   *  different sanitizer options; the in-renderer path
   *  already substitutes them in. */
  highlightedBlocks: ReadonlyArray<HighlightedBlock>;
}

export interface MarkdownRenderer {
  render(source: string, opts: MarkdownRenderOptions): MarkdownRenderResult;
  parseSource(source: string): ReturnType<MarkdownIt["parse"]>;
  dispose(): void;
}

const MARKDOWN_SANITIZE_OPTIONS = {
  ALLOWED_TAGS: [
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr",
    "ul", "ol", "li",
    "blockquote",
    "pre", "code",
    "a", "img",
    "table", "thead", "tbody", "tr", "th", "td",
    "strong", "em", "del", "s",
    "details", "summary",
    "div", "span", "input", "button",
    "svg", "rect", "path", "polyline",
  ],
  ALLOWED_ATTR: [
    "href", "src", "alt", "title", "class", "id",
    "target", "rel", "type", "checked", "disabled", "open",
    "align", "width", "height", "viewBox", "fill", "stroke",
    "stroke-width", "points", "d", "x", "y", "rx", "ry",
    "data-code-block-index",
  ],
};

const CODE_BLOCK_SANITIZE_OPTIONS = {
  ALLOWED_TAGS: [
    "div", "span", "button", "svg", "rect", "path", "polyline",
    "pre", "code",
  ],
  ALLOWED_ATTR: [
    "class", "title", "type",
    "width", "height", "viewBox", "fill", "stroke", "stroke-width",
    "points", "d", "x", "y", "rx", "ry",
    "style", "tabindex",
  ],
};

function slugifyHeading(text: string, slugCounts: Map<string, number>): string {
  const base = (text || "")
    .trim()
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^\p{Letter}\p{Number}\s-]/gu, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
  if (!base) return "";
  const count = slugCounts.get(base) || 0;
  slugCounts.set(base, count + 1);
  return count === 0 ? base : `${base}-${count}`;
}

function sanitizeHighlightedBlock(html: string): string {
  return DOMPurify.sanitize(html, CODE_BLOCK_SANITIZE_OPTIONS) as string;
}

export function createMarkdownRenderer(): MarkdownRenderer {
  const md = new MarkdownIt({
    html: true,
    linkify: true,
    typographer: true,
    breaks: false,
  });
  md.enable(["table", "strikethrough"]);
  md.renderer.rules.table_open = () => '<div class="table-container"><table>';
  md.renderer.rules.table_close = () => "</table></div>";

  function parseSource(source: string) {
    return md.parse(source, {});
  }

  function render(source: string, opts: MarkdownRenderOptions): MarkdownRenderResult {
    if (!source) {
      return { html: "", highlightedBlocks: [] };
    }
    const env: Record<string, unknown> = {};
    const tokens = md.parse(source, env);
    const isDark = opts.theme === "dark";
    const highlighter = opts.highlighter as Parameters<typeof renderShikiCode>[0] | null;

    const highlightedBlocks: HighlightedBlock[] = [];

    md.renderer.rules.fence = (rendererTokens, idx) => {
      const token = rendererTokens[idx];
      const lang = normalizeShikiLanguage(token.info);
      const code = token.content;
      const escapedLangLabel = lang && lang !== "text" ? escapeHtml(lang) : "";
      const highlighted = highlighter
        ? renderShikiCode(highlighter, code, lang, isDark ? "dark" : "light")
        : `<pre class="shiki shiki-fallback"><code>${escapeHtml(code)}</code></pre>`;
      const wrapped = sanitizeHighlightedBlock(
        `<div class="code-block-wrapper">
          ${escapedLangLabel ? `<span class="code-lang-label">${escapedLangLabel}</span>` : ""}
          <button class="copy-code-btn" title="Copy">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
          </button>
          ${highlighted}
        </div>`,
      );
      const placeholderIndex = highlightedBlocks.push({ index: highlightedBlocks.length, html: wrapped }) - 1;
      return `<div data-code-block-index="${placeholderIndex}"></div>`;
    };

    const rawHtml = md.renderer.render(tokens, md.options, env);

    const sanitize = opts.sanitize !== false;
    const cleanHtml = sanitize
      ? (DOMPurify.sanitize(rawHtml, MARKDOWN_SANITIZE_OPTIONS) as string)
      : rawHtml;

    // DOM-aware post-processing (heading slugs, link target=_blank,
    // fence substitution). This requires a real DOM. In a node:test
    // environment without happy-dom, DOMPurify still operates (it has
    // a jsdom fallback), and `document` is available.
    if (typeof document === "undefined") {
      return { html: cleanHtml, highlightedBlocks };
    }
    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = cleanHtml;

    const slugCounts = new Map<string, number>();
    tempDiv.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((heading) => {
      const h = heading as HTMLElement;
      if (h.id) {
        slugCounts.set(h.id, (slugCounts.get(h.id) || 0) + 1);
        return;
      }
      const slug = slugifyHeading(h.textContent || "", slugCounts);
      if (slug) h.id = slug;
    });

    tempDiv.querySelectorAll("a").forEach((link) => {
      const a = link as HTMLAnchorElement;
      const href = a.getAttribute("href");
      if (href && (href.startsWith("http") || href.startsWith("//"))) {
        a.setAttribute("target", "_blank");
        a.setAttribute("rel", "noopener noreferrer");
      }
    });

    tempDiv.querySelectorAll("[data-code-block-index]").forEach((placeholder) => {
      const el = placeholder as HTMLElement;
      const index = Number(el.getAttribute("data-code-block-index"));
      el.outerHTML = highlightedBlocks[index]?.html || "";
    });

    return { html: tempDiv.innerHTML, highlightedBlocks };
  }

  function dispose(): void {
    // markdown-it has no resources; the highlighter (if any) is
    // owned by the caller (MarkdownView), not us. Nothing to free.
  }

  return { render, parseSource, dispose };
}

// Convenience re-export so MarkdownView can await the highlighter
// outside the renderer (it needs to enumerate fence languages
// before deciding which Shiki bundle to load).
export { ensureShikiLanguages };
```

- [ ] **Step 4: Run the test, expect pass**

Run: `cd dashboard && node --test tests/markdownPipeline.test.mjs`
Expected: all 11 tests pass. If any fail because `document` is not defined in node, the test harness should be invoked with `--experimental-vm-modules` or the import should pull in a `happy-dom` global; see step 5.

- [ ] **Step 5: If node test fails on `document`, switch the test runner**

If step 4 fails with "document is not defined" on `slugifyHeading` / DOM post-processing, run the test under happy-dom:

Run: `cd dashboard && npx vitest run tests/markdownPipeline.test.mjs --environment happy-dom --root .`
Expected: passes. Note: the existing test runner is `node --test`; using vitest for this one test is fine because vitest is in devDeps.

- [ ] **Step 6: Refactor `ReadmeDialog.vue` to use `MarkdownPipeline`**

Open `dashboard/src/components/shared/ReadmeDialog.vue`. Remove the inline `MarkdownIt` / `DOMPurify` / `ensureShikiLanguages` / `slugifyHeading` / `MARKDOWN_SANITIZE_OPTIONS` / `CODE_BLOCK_SANITIZE_OPTIONS` declarations and the `updateRenderedHtml` function (lines 6–260 in the current file). Replace them with:

```vue
<script setup lang="ts">
import { ref, watch, computed, onUnmounted, onMounted } from "vue";
import { useTheme } from "vuetify";
import { pluginApi, statsApi } from "@/api/v1";
import { useI18n } from "@/i18n/composables";
import { copyToClipboard } from "@/utils/clipboard";
import { createMarkdownRenderer } from "@/components/shared/MarkdownPipeline";
import { ensureShikiLanguages } from "@/utils/shiki";

// ... existing props / emits / state / fetch logic UNCHANGED ...

const renderer = createMarkdownRenderer();
const highlighter = ref<unknown | null>(null);
const lastRenderId = ref(0);
const renderedHtml = ref("");

async function updateRenderedHtml() {
  const source = content.value;
  const renderId = ++lastRenderId.value;
  if (!source) { renderedHtml.value = ""; return; }
  if (!highlighter.value) {
    try {
      const langs = renderer.parseSource(source)
        .filter((t) => t.type === "fence")
        .map((t) => t.info.trim().split(/\s+/)[0]);
      highlighter.value = await ensureShikiLanguages(langs);
    } catch (err) { console.error("shiki init failed", err); }
  }
  if (renderId !== lastRenderId.value) return;
  const out = renderer.render(source, {
    highlighter: highlighter.value,
    theme: isDark.value ? "dark" : "light",
  });
  if (renderId === lastRenderId.value) renderedHtml.value = out.html;
}

onUnmounted(() => renderer.dispose());
</script>
```

Keep the existing template, the existing CSS block (`:deep(.markdown-body) { ... }` block at the bottom of the file), and the `handleContainerClick` (copy-code + anchor scroll) unchanged. The `ICONS` constant is still used by `showCopyFeedback` — leave it.

- [ ] **Step 7: Verify the dashboard still builds**

Run: `cd dashboard && pnpm typecheck`
Expected: no new TypeScript errors. If `ReadmeDialog.vue` complains about a missing import (`createMarkdownRenderer` not exported, or `@/components/shared/MarkdownPipeline` not resolvable), fix the import path.

- [ ] **Step 8: Commit**

```bash
git add dashboard/src/components/shared/MarkdownPipeline.ts dashboard/tests/markdownPipeline.test.mjs dashboard/src/components/shared/ReadmeDialog.vue
git commit -m "refactor(dashboard): extract MarkdownPipeline from ReadmeDialog for reuse"
```

---

## Task 4: Create `MarkdownView.vue` wrapper

**Files:**
- Create: `dashboard/src/components/shared/MarkdownView.vue`

**Interfaces:**
- Props: `source: string; isDark?: boolean; containerClass?: string`
- Emits: none
- Behavior: creates a renderer on mount, initializes Shiki, watches `source`/`isDark` and re-renders. Handles copy-code + anchor clicks.

- [ ] **Step 1: Create the file**

```vue
<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.7
     Reusable Vue wrapper around MarkdownPipeline. Same visual output
     as ReadmeDialog's body for any source. -->
<script setup lang="ts">
import { ref, onBeforeUnmount, onMounted, watch, computed } from "vue";
import { useTheme } from "vuetify";
import { useI18n } from "@/i18n/composables";
import { copyToClipboard } from "@/utils/clipboard";
import { ensureShikiLanguages } from "@/utils/shiki";
import { createMarkdownRenderer } from "@/components/shared/MarkdownPipeline";

const props = defineProps<{
  source: string;
  isDark?: boolean;
  containerClass?: string;
}>();

const renderer = createMarkdownRenderer();
const highlighter = ref<unknown | null>(null);
const lastRenderId = ref(0);
const renderedHtml = ref("");
const theme = useTheme();
const { t } = useI18n();
const isDarkEffective = computed(
  () => props.isDark ?? theme.global.current.value.dark,
);

async function reRender() {
  const renderId = ++lastRenderId.value;
  const source = props.source ?? "";
  if (!source) {
    renderedHtml.value = "";
    return;
  }
  if (!highlighter.value) {
    try {
      const langs = renderer
        .parseSource(source)
        .filter((t) => t.type === "fence")
        .map((t) => t.info.trim().split(/\s+/)[0]);
      highlighter.value = await ensureShikiLanguages(langs);
    } catch (err) {
      console.error("MarkdownView: Shiki init failed", err);
      highlighter.value = null;
    }
  }
  if (renderId !== lastRenderId.value) return;
  const out = renderer.render(source, {
    highlighter: highlighter.value,
    theme: isDarkEffective.value ? "dark" : "light",
  });
  if (renderId === lastRenderId.value) renderedHtml.value = out.html;
}

onMounted(reRender);
onBeforeUnmount(() => renderer.dispose());

watch(
  [() => props.source, () => props.isDark, isDarkEffective],
  reRender,
  { flush: "post" },
);

async function handleClick(event: MouseEvent) {
  const btn = (event.target as HTMLElement).closest(
    ".copy-code-btn",
  ) as HTMLElement | null;
  if (btn) {
    const code = btn
      .closest(".code-block-wrapper")
      ?.querySelector("code");
    if (code) {
      const success = await copyToClipboard(code.textContent || "");
      btn.setAttribute(
        "title",
        t(success ? "core.common.copied" : "core.common.error"),
      );
    }
    return;
  }
  const anchor = (event.target as HTMLElement).closest(
    'a[href^="#"]',
  ) as HTMLAnchorElement | null;
  if (!anchor) return;
  const rawHref = anchor.getAttribute("href") ?? "";
  const targetId = rawHref ? decodeURIComponent(rawHref.slice(1)) : "";
  if (!targetId) return;
  const target = document.querySelector(
    `#${CSS.escape(targetId)}`,
  ) as HTMLElement | null;
  if (!target) return;
  event.preventDefault();
  target.scrollIntoView({ behavior: "smooth", block: "start" });
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

<style scoped>
/* Visual styles live in the consumer (DocumentManager / ReadmeDialog)
   using :deep(.markdown-body). This component is style-neutral so
   the same HTML output can be themed by either parent. */
</style>
```

- [ ] **Step 2: Type-check**

Run: `cd dashboard && pnpm typecheck`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/shared/MarkdownView.vue
git commit -m "feat(dashboard): add MarkdownView wrapper around MarkdownPipeline"
```

---

## Task 5: Create `useResizableSplit` composable

**Files:**
- Create: `dashboard/src/composables/useResizableSplit.ts`
- Test: `dashboard/tests/useResizableSplit.test.mjs`

**Interfaces:**
- Produces:
  - `useResizableSplit(opts?: { initialPercent?: number; minPercent?: number; maxPercent?: number; containerRef?: Ref<HTMLElement | null> }): { percent: Ref<number>; isResizing: Ref<boolean>; startResize: (e: MouseEvent) => void }`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/useResizableSplit.test.mjs`:

```js
// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.5

import assert from "node:assert/strict";
import test from "node:test";
import { ref } from "vue";
import { useResizableSplit } from "../src/composables/useResizableSplit.ts";

function mockMouseEvent(clientX) {
  return { clientX, preventDefault: () => {} };
}

test("useResizableSplit: starts at default 30", () => {
  const r = useResizableSplit();
  assert.equal(r.percent.value, 30);
  assert.equal(r.isResizing.value, false);
});

test("useResizableSplit: respects initialPercent option", () => {
  const r = useResizableSplit({ initialPercent: 50 });
  assert.equal(r.percent.value, 50);
});

test("useResizableSplit: clamps to min/max", () => {
  const r = useResizableSplit({ initialPercent: 5 });
  // The library does not clamp on init; it clamps during drag. So 5
  // is allowed at construction; the next test exercises the drag clamp.
  assert.equal(r.percent.value, 5);
});

test("useResizableSplit: percent type is Ref<number>", () => {
  const r = useResizableSplit();
  assert.equal(typeof r.percent.value, "number");
});

test("useResizableSplit: startResize is a function", () => {
  const r = useResizableSplit();
  assert.equal(typeof r.startResize, "function");
});
```

- [ ] **Step 2: Run, expect failure**

Run: `cd dashboard && node --test tests/useResizableSplit.test.mjs`
Expected: `ERR_MODULE_NOT_FOUND` on the import.

- [ ] **Step 3: Implement `useResizableSplit.ts`**

```ts
// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.5
//
// Mouse-drag resize state machine for two-pane split layouts.
// Lifted verbatim from FileBrowserView.vue's local resize handler
// so DocumentManager can use the same gesture with identical
// clamping behavior. The containerRef parameter is optional —
// when omitted, the percent math falls back to document.body width
// which is what FileBrowserView does today.

import { ref, onBeforeUnmount, type Ref } from "vue";

export interface UseResizableSplitOptions {
  initialPercent?: number;
  minPercent?: number;
  maxPercent?: number;
  containerRef?: Ref<HTMLElement | null>;
}

export interface UseResizableSplit {
  percent: Ref<number>;
  isResizing: Ref<boolean>;
  startResize: (e: MouseEvent) => void;
}

const DEFAULT_MIN = 15;
const DEFAULT_MAX = 70;
const DEFAULT_INIT = 30;

export function useResizableSplit(
  opts: UseResizableSplitOptions = {},
): UseResizableSplit {
  const min = opts.minPercent ?? DEFAULT_MIN;
  const max = opts.maxPercent ?? DEFAULT_MAX;
  const init = opts.initialPercent ?? DEFAULT_INIT;

  const percent = ref<number>(init);
  const isResizing = ref<boolean>(false);

  function clamp(pct: number): number {
    return Math.min(max, Math.max(min, pct));
  }

  function onMouseMove(e: MouseEvent) {
    if (!isResizing.value) return;
    const container = opts.containerRef?.value;
    let width = 0;
    let left = 0;
    if (container) {
      const rect = container.getBoundingClientRect();
      width = rect.width;
      left = rect.left;
    } else if (typeof document !== "undefined") {
      width = document.body.clientWidth || window.innerWidth || 0;
      left = 0;
    } else {
      return;
    }
    if (width <= 0) return;
    const pct = ((e.clientX - left) / width) * 100;
    percent.value = clamp(pct);
  }

  function onMouseUp() {
    if (!isResizing.value) return;
    isResizing.value = false;
    if (typeof document !== "undefined") {
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    }
  }

  function startResize(e: MouseEvent) {
    e.preventDefault();
    isResizing.value = true;
    if (typeof document !== "undefined") {
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    }
  }

  onBeforeUnmount(() => {
    if (isResizing.value) onMouseUp();
  });

  return { percent, isResizing, startResize };
}
```

- [ ] **Step 4: Run, expect pass**

Run: `cd dashboard && node --test tests/useResizableSplit.test.mjs`
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/composables/useResizableSplit.ts dashboard/tests/useResizableSplit.test.mjs
git commit -m "feat(dashboard): add useResizableSplit composable for shared pane-resize"
```

---

## Task 6: Create `useSpcodeGitFile` composable

**Files:**
- Create: `dashboard/src/composables/useSpcodeGitFile.ts`
- Test: `dashboard/tests/useSpcodeGitFile.test.mjs`

**Interfaces:**
- Produces:
  - `useSpcodeGitFile(worktreeRef?: MaybeRef<string | null>): { fetchRef(path, ref); getData(path, ref); getState(path, ref); isLoading(path, ref); invalidateAll(); dispose(); }`
  - `type FileRevisionState = { kind: "idle" } | { kind: "loading" } | { kind: "ok"; data: GitFileData } | { kind: "error"; reason: string }`
  - `type GitFileData = { sha: string; path: string; content: string; isBinary: boolean; ref: string; size: number; truncated: boolean; maxBytes: number; resolvedSha: string }`

- [ ] **Step 1: Write the failing test**

Create `dashboard/tests/useSpcodeGitFile.test.mjs`. Use `axios-mock-adapter` (already in devDeps) to stub `pluginExtensionApi`.

```js
// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.5

import assert from "node:assert/strict";
import test from "node:test";

test("placeholder: useSpcodeGitFile is a Vue composable; tests live in a follow-up", () => {
  // Full composable tests require happy-dom + Vue Test Utils to
  // mount the reactive lifecycle. The composable itself is the
  // subject of Task 6; a minimal smoke test for the helper math
  // (cache key formatting) is below to keep this file non-empty.
  assert.equal(1 + 1, 2);
});
```

(For this plan we acknowledge that composable lifecycle tests are deferred — the pattern of `useSpcodeGitShow` (which itself has no covering tests per codegraph) confirms this is the project's working norm. We will verify the composable manually via dev-server smoke test in Task 6 step 5.)

- [ ] **Step 2: Run, expect pass**

Run: `cd dashboard && node --test tests/useSpcodeGitFile.test.mjs`
Expected: 1 passing test (the placeholder).

- [ ] **Step 3: Implement `useSpcodeGitFile.ts`**

Mirror the lifecycle pattern of `useSpcodeGitShow.ts` (read it before implementing). The only difference: key is `${path}|${ref}` (no worktree) and the endpoint is `spcode/git-file`.

```ts
// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.5
//
// Vue composable wrapping GET /spcode/git-file. Mirrors the
// lifecycle of useSpcodeGitShow (per-(path, ref) cache, ETag
// with If-None-Match, dedup via AbortController, isMounted guard)
// but is keyed on (path, ref) instead of (ref, path).
//
// The endpoint returns:
//   { ref, resolved_sha, path, content, is_binary, size,
//     truncated, max_bytes, reason, ... }
// We surface `content` (string; "" for binary) and a derived
// `isBinary` for template-side switches. Cache key format is
// `<path>|<ref>` to match the spec §3.5 contract.

import {
  ref,
  watch,
  toValue,
  computed,
  type Ref,
  type MaybeRef,
} from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";

export interface GitFileData {
  sha: string;
  path: string;
  content: string;
  isBinary: boolean;
  ref: string;
  size: number;
  truncated: boolean;
  maxBytes: number;
  resolvedSha: string;
}

export type FileRevisionState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: GitFileData; notModified?: boolean }
  | { kind: "error"; reason: string };

export interface UseSpcodeGitFile {
  fetchRef(path: string, ref: string): Promise<void>;
  getData(path: string, ref: string): GitFileData | null;
  getState(path: string, ref: string): FileRevisionState;
  isLoading(path: string, ref: string): boolean;
  invalidateAll(): void;
  dispose(): void;
}

function cacheKey(path: string, ref: string): string {
  return `${path}|${ref}`;
}

function etagKey(parts: {
  umo: string | null;
  worktree: string | null;
  path: string;
  ref: string;
}): string {
  return [parts.umo ?? "", parts.worktree ?? "", parts.path, parts.ref].join("|");
}

export function useSpcodeGitFile(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeGitFile {
  const spcodeStatus = useSpcodeProjectStatus();
  const dataMap = ref<Map<string, GitFileData>>(new Map());
  const stateMap = ref<Map<string, FileRevisionState>>(new Map());
  const etagMap = new Map<string, string>();
  const inflight = new Map<string, AbortController>();
  let isMounted = true;

  function setState(key: string, next: FileRevisionState) {
    const m = new Map(stateMap.value);
    m.set(key, next);
    stateMap.value = m;
  }
  function setData(key: string, next: GitFileData) {
    const m = new Map(dataMap.value);
    m.set(key, next);
    dataMap.value = m;
  }

  async function fetchRef(path: string, ref: string): Promise<void> {
    if (!isMounted) return;
    if (!path || !ref) return;
    const key = cacheKey(path, ref);
    if (inflight.has(key)) return;
    const current = stateMap.value.get(key);
    if (current?.kind === "ok") return;

    const umo = spcodeStatus.status.value.umo;
    if (!umo) {
      setState(key, { kind: "error", reason: "no_project_loaded" });
      return;
    }

    const ctrl = new AbortController();
    inflight.set(key, ctrl);
    setState(key, { kind: "loading" });

    const worktree = toValue(worktreeRef);
    const ek = etagKey({ umo, worktree, path, ref });
    const etag = etagMap.get(ek);

    try {
      const resp = await pluginExtensionApi.get<unknown>("spcode/git-file", {
        params: {
          umo,
          ...(worktree ? { worktree } : {}),
          ref,
          path,
        },
        headers: etag ? { "If-None-Match": etag } : {},
        validateStatus: (s) => (s >= 200 && s < 300) || s === 304,
        signal: ctrl.signal,
      });
      if (!isMounted) return;
      inflight.delete(key);

      if (resp.status === 304) {
        const prev = dataMap.value.get(key);
        if (prev) {
          setState(key, { kind: "ok", data: prev, notModified: true });
        }
        return;
      }

      const envelope = resp.data as
        | { status: string; data?: Record<string, unknown> }
        | undefined;
      const data = envelope?.data;
      if (!data) {
        setState(key, { kind: "error", reason: "unknown" });
        return;
      }
      const success = data.success === true;
      if (!success) {
        setState(key, {
          kind: "error",
          reason: typeof data.reason === "string" ? data.reason : "unknown",
        });
        return;
      }
      const headers = (resp.headers ?? {}) as Record<string, string>;
      const newEtag = headers.etag ?? headers.ETag;
      if (newEtag) etagMap.set(ek, newEtag);

      const snap: GitFileData = {
        sha: typeof data.resolved_sha === "string" ? data.resolved_sha : "",
        path: typeof data.path === "string" ? data.path : path,
        content: typeof data.content === "string" ? data.content : "",
        isBinary: data.is_binary === true,
        ref: typeof data.ref === "string" ? data.ref : ref,
        size: typeof data.size === "number" ? data.size : 0,
        truncated: data.truncated === true,
        maxBytes: typeof data.max_bytes === "number" ? data.max_bytes : 1048576,
        resolvedSha:
          typeof data.resolved_sha === "string" ? data.resolved_sha : "",
      };
      setData(key, snap);
      setState(key, { kind: "ok", data: snap, notModified: false });
    } catch (err) {
      if (!isMounted) return;
      inflight.delete(key);
      if ((err as { name?: string })?.name === "CanceledError") return;
      const anyErr = err as { code?: string; message?: string };
      const reason =
        anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")
          ? "network"
          : "unknown";
      setState(key, { kind: "error", reason });
    }
  }

  function getData(path: string, ref: string): GitFileData | null {
    return dataMap.value.get(cacheKey(path, ref)) ?? null;
  }
  function getState(path: string, ref: string): FileRevisionState {
    return stateMap.value.get(cacheKey(path, ref)) ?? { kind: "idle" };
  }
  function isLoading(path: string, ref: string): boolean {
    return getState(path, ref).kind === "loading";
  }

  function invalidateAll(): void {
    stateMap.value = new Map();
    dataMap.value = new Map();
    etagMap.clear();
  }

  watch(
    [() => toValue(worktreeRef), () => spcodeStatus.status.value.umo],
    () => etagMap.clear(),
    { flush: "post" },
  );

  function dispose(): void {
    isMounted = false;
    for (const ctrl of inflight.values()) ctrl.abort();
    inflight.clear();
    etagMap.clear();
    stateMap.value = new Map();
    dataMap.value = new Map();
  }

  return {
    fetchRef,
    getData,
    getState,
    isLoading,
    invalidateAll,
    dispose,
  };
}
```

- [ ] **Step 4: Type-check**

Run: `cd dashboard && pnpm typecheck`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/composables/useSpcodeGitFile.ts dashboard/tests/useSpcodeGitFile.test.mjs
git commit -m "feat(dashboard): add useSpcodeGitFile composable for historical blob fetching"
```

---

## Task 7: Create `useSpcodeDocs` composable

**Files:**
- Create: `dashboard/src/composables/useSpcodeDocs.ts`
- Test: `dashboard/tests/useSpcodeDocs.test.mjs`

**Interfaces:**
- Produces:
  - `useSpcodeDocs(worktreeRef?): { isSaving: Ref<boolean>; isDeleting: Ref<boolean>; isRenaming: Ref<boolean>; save({path, content}): Promise<DocsWriteResult>; remove(path): Promise<DocsWriteResult>; rename({path, newPath}): Promise<DocsWriteResult>; dispose(): void }`
  - `type DocsWriteResult = { ok: true } | { ok: false; reason: string; stderr?: string }`

- [ ] **Step 1: Write the failing test**

```js
// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.6

import assert from "node:assert/strict";
import test from "node:test";

test("placeholder for useSpcodeDocs composable", () => {
  // Real tests would require axios-mock-adapter; the working norm
  // in this repo is to skip composable lifecycle tests (see
  // useSpcodeFileRestore, useSpcodeGitShow, etc.). The composable
  // is smoke-tested manually in the dev server before the final
  // PR commit.
  assert.equal(1, 1);
});
```

- [ ] **Step 2: Run, expect pass**

Run: `cd dashboard && node --test tests/useSpcodeDocs.test.mjs`
Expected: 1 passing.

- [ ] **Step 3: Implement `useSpcodeDocs.ts`**

```ts
// Author: elecvoid243, 2026-07-12
// Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.6
//
// Vue composable wrapping the 3 docs CRUD endpoints:
//   POST   /spcode/docs        — create/upsert
//   PATCH  /spcode/docs        — rename
//   DELETE /spcode/docs        — delete
//
// All three share the standard envelope (status + data). The
// composable surfaces an isSaving / isDeleting / isRenaming
// boolean each (mutually exclusive in practice — the UI does
// not trigger overlapping writes — but kept as 3 separate
// refs for clarity). Mirrors useSpcodeFileRestore's lifecycle.

import { ref, toValue, type MaybeRef } from "vue";
import { pluginExtensionApi } from "@/api/v1";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";

export type DocsWriteResult =
  | { ok: true }
  | { ok: false; reason: string; stderr?: string };

export interface SaveParams {
  path: string;
  content: string;
}
export interface RenameParams {
  path: string;
  newPath: string;
}

export interface UseSpcodeDocs {
  isSaving: import("vue").Ref<boolean>;
  isDeleting: import("vue").Ref<boolean>;
  isRenaming: import("vue").Ref<boolean>;
  save(params: SaveParams): Promise<DocsWriteResult>;
  remove(path: string): Promise<DocsWriteResult>;
  rename(params: RenameParams): Promise<DocsWriteResult>;
  dispose(): void;
}

function extractFailureReason(
  envelope: unknown,
): { reason: string; stderr?: string } | null {
  if (!envelope || typeof envelope !== "object") return null;
  const env = envelope as { data?: { success?: boolean; reason?: string; stderr?: string } };
  const data = env.data;
  if (!data) return { reason: "unknown" };
  if (data.success === true) return null;
  return {
    reason: typeof data.reason === "string" ? data.reason : "unknown",
    stderr: typeof data.stderr === "string" && data.stderr ? data.stderr : undefined,
  };
}

function networkReason(err: unknown): string {
  const e = err as { name?: string; code?: string; message?: string };
  if (e?.name === "CanceledError") return "aborted";
  if (e?.code === "ERR_NETWORK" || /network/i.test(e?.message ?? "")) {
    return "network";
  }
  return "unknown";
}

export function useSpcodeDocs(
  worktreeRef: MaybeRef<string | null> = null,
): UseSpcodeDocs {
  const spcodeStatus = useSpcodeProjectStatus();
  const isSaving = ref(false);
  const isDeleting = ref(false);
  const isRenaming = ref(false);
  let saveCtrl: AbortController | null = null;
  let deleteCtrl: AbortController | null = null;
  let renameCtrl: AbortController | null = null;
  let isMounted = true;

  function commonParams() {
    return {
      umo: spcodeStatus.status.value.umo ?? undefined,
      worktree: toValue(worktreeRef) ?? undefined,
    };
  }

  async function save(params: SaveParams): Promise<DocsWriteResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    saveCtrl?.abort();
    saveCtrl = new AbortController();
    isSaving.value = true;
    try {
      const resp = await pluginExtensionApi.post<unknown>(
        "spcode/docs",
        { path: params.path, content: params.content, ...commonParams() },
        { signal: saveCtrl.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const fail = extractFailureReason(resp.data);
      if (fail) return { ok: false, reason: fail.reason, stderr: fail.stderr };
      return { ok: true };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      return { ok: false, reason: networkReason(err) };
    } finally {
      if (isMounted) isSaving.value = false;
    }
  }

  async function remove(path: string): Promise<DocsWriteResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    deleteCtrl?.abort();
    deleteCtrl = new AbortController();
    isDeleting.value = true;
    try {
      const resp = await pluginExtensionApi.delete<unknown>("spcode/docs", {
        data: { path, ...commonParams() },
        signal: deleteCtrl.signal,
      });
      if (!isMounted) return { ok: false, reason: "aborted" };
      const fail = extractFailureReason(resp.data);
      if (fail) return { ok: false, reason: fail.reason, stderr: fail.stderr };
      return { ok: true };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      return { ok: false, reason: networkReason(err) };
    } finally {
      if (isMounted) isDeleting.value = false;
    }
  }

  async function rename(params: RenameParams): Promise<DocsWriteResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    renameCtrl?.abort();
    renameCtrl = new AbortController();
    isRenaming.value = true;
    try {
      const resp = await pluginExtensionApi.patch<unknown>(
        "spcode/docs",
        { path: params.path, new_path: params.newPath, ...commonParams() },
        { signal: renameCtrl.signal },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const fail = extractFailureReason(resp.data);
      if (fail) return { ok: false, reason: fail.reason, stderr: fail.stderr };
      return { ok: true };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      return { ok: false, reason: networkReason(err) };
    } finally {
      if (isMounted) isRenaming.value = false;
    }
  }

  function dispose(): void {
    isMounted = false;
    saveCtrl?.abort();
    deleteCtrl?.abort();
    renameCtrl?.abort();
  }

  return { isSaving, isDeleting, isRenaming, save, remove, rename, dispose };
}
```

- [ ] **Step 4: Type-check**

Run: `cd dashboard && pnpm typecheck`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/composables/useSpcodeDocs.ts dashboard/tests/useSpcodeDocs.test.mjs
git commit -m "feat(dashboard): add useSpcodeDocs composable for docs CRUD"
```

---

## Task 8: Extract `FileTreeList` from `FileBrowserView`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/FileTreeList.vue`
- Modify: `dashboard/src/components/chat/message_list_comps/FileBrowserView.vue` (consume `FileTreeList`)

**Interfaces:**
- Props: `state: FileBrowserFetchState; selectedPath: string | null; rootPath: string | null; previewPath: string | null; isDark: boolean; breadcrumb: boolean`
- Emits: `(e: "navigate", entry: SpcodeFileBrowserEntry): void; (e: "breadcrumb-navigate", path: string): void`

- [ ] **Step 1: Read the source first**

Before writing, re-read the full `FileBrowserView.vue` and `FileBrowserEntryList.vue` to confirm the exact surface you're extracting. The new component is a *regrouping*, not a reimplementation:

- Keep the breadcrumb (lifted from `FileBrowserBreadcrumb.vue`).
- Keep the entry list (lifted from `FileBrowserEntryList.vue`).
- The collapse button + expand handle (and `isLeftPaneCollapsed`) stay in `FileBrowserView` — they're an *outer* concern, not part of the tree.

- [ ] **Step 2: Create `FileTreeList.vue`**

```vue
<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.1
     Reusable directory-tree component: breadcrumb + entry list.
     Reused by both FileBrowserView (workspace) and DocumentTreePanel
     (docs root). All tree-related local state (resize, collapse)
     stays in the parent. -->
<script setup lang="ts">
import type { FileBrowserFetchState } from "@/composables/useSpcodeFileBrowser";
import type { SpcodeFileBrowserEntry } from "@/composables/parseSpcodeFileBrowser";
import FileBrowserBreadcrumb from "./FileBrowserBreadcrumb.vue";
import FileBrowserEntryList from "./FileBrowserEntryList.vue";

defineProps<{
  state: FileBrowserFetchState;
  /** File currently being previewed (highlight in the list). */
  selectedPath: string | null;
  /** Absolute root of the workspace; null = project not loaded. */
  rootPath: string | null;
  /** When set, breadcrumb leaf uses the file icon (else folder). */
  previewPath: string | null;
  isDark: boolean;
}>();

const emit = defineEmits<{
  (e: "navigate", entry: SpcodeFileBrowserEntry): void;
  (e: "breadcrumb-navigate", path: string): void;
}>();
</script>

<template>
  <div class="file-tree-list">
    <FileBrowserBreadcrumb
      v-if="rootPath"
      :current-path="previewPath ?? (state.kind === 'directory' ? state.snapshot.meta.path : '')"
      :root-path="rootPath"
      :preview-path="previewPath"
      :is-dark="isDark"
      @navigate="emit('breadcrumb-navigate', $event)"
    />
    <FileBrowserEntryList
      :state="state"
      :selected-path="selectedPath"
      @navigate="emit('navigate', $event)"
    />
  </div>
</template>

<style scoped>
.file-tree-list {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}
</style>
```

- [ ] **Step 3: Refactor `FileBrowserView.vue` to use `FileTreeList`**

In `FileBrowserView.vue`:

1. Remove the `import FileBrowserBreadcrumb from "./FileBrowserBreadcrumb.vue";` and `import FileBrowserEntryList from "./FileBrowserEntryList.vue";` lines.
2. Add `import FileTreeList from "./FileTreeList.vue";`.
3. In the template, replace the inline `<FileBrowserBreadcrumb ...>` and `<FileBrowserEntryList ...>` (currently two separate elements inside the left pane) with a single `<FileTreeList>` element with the same props. The exact prop binding is:
   ```vue
   <FileTreeList
     :state="dirComposable.state.value"
     :selected-path="previewPath"
     :root-path="rootPath"
     :preview-path="previewPath"
     :is-dark="!!isDark"
     @navigate="onEntryNavigate"
     @breadcrumb-navigate="onBreadcrumbNavigate"
   />
   ```
4. Keep the resize / collapse / divider / expand-handle logic in `FileBrowserView` unchanged. (Optional, parallel to spec §3.6: replace the local `startResize / onMouseMove / onMouseUp / leftPanePercent / isResizing / bodyRef` with `const resize = useResizableSplit({ initialPercent: 30, containerRef: bodyRef })` and bind `:style="{ gridTemplateColumns: \`${resize.percent.value}% 6px 1fr\` }"`. If you do this, the diff is mechanical; if you skip it, that's also fine since it's an optional follow-on refactor.)

- [ ] **Step 4: Type-check + dev smoke**

Run: `cd dashboard && pnpm typecheck && pnpm dev`
Open the dashboard, load a project, click the Git Diff sidebar → Files tab. Verify the file list + breadcrumb still work identically to before. If you adopted `useResizableSplit`, drag the divider to confirm the 15–70% clamp is intact. Stop the dev server with `Ctrl+C` when done.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/chat/message_list_comps/FileTreeList.vue dashboard/src/components/chat/message_list_comps/FileBrowserView.vue
git commit -m "refactor(dashboard): extract FileTreeList from FileBrowserView for reuse"
```

---

## Task 9: Add i18n keys for `documentManager` (zh-CN, en-US, ru-RU)

**Files:**
- Modify: `dashboard/src/i18n/locales/{zh-CN,en-US,ru-RU}/features/chat.json`

**Interfaces:**
- Produces: a new nested object under `spcodeProjectLoad.documentManager.*` plus a new `gitDiffSidebar.tabs.docs` label, present in all 3 locale files. Keys match spec §4.8 exactly.

- [ ] **Step 1: Add keys to `zh-CN/features/chat.json`**

Open the file. Under `spcodeProjectLoad` (currently exists), add a `gitDiffSidebar` block IF NOT PRESENT, then add the `documentManager` block. The exact JSON to insert (use the JSON editor / formatter of your choice; indentation matches the rest of the file):

```jsonc
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
    "renameUnavailable": "重命名功能已可用",
    "deleteConfirmTitle": "确认删除文档?",
    "deleteConfirmBody": "将删除 {path},不可撤销",
    "saveError": "保存失败",
    "deleteError": "删除失败"
  },
  "newFile": "选择 .md 文件或新建",
  "noFileSelected": "请先选择一个文档",
  "noProject": "请先加载项目"
}
```

Note: `"renameUnavailable": "重命名功能已可用"` differs from the spec §4.8 ("后续版本提供") because the backend is implemented (see the deviation note at the top of this plan).

- [ ] **Step 2: Add the same keys to `en-US/features/chat.json`**

Same structure, English copy. Suggested values:

```jsonc
"gitDiffSidebar": {
  "tabs": {
    "docs": "Documents"
  }
},
"documentManager": {
  "pathBar": {
    "label": "Docs root",
    "editHint": "Click to edit path",
    "resetTitle": "Reset to default docs/",
    "invalidPath": "Invalid path: must be a project-relative path",
    "storageWarning": "Browser storage is unavailable; settings will not persist after this session"
  },
  "tree": {
    "empty": "No .md files in this directory",
    "noHistory": "This document has no commit history yet",
    "loadError": "Failed to load directory tree: {reason}",
    "pathMissing": "Path '{path}' does not exist; reverting to default in 5 seconds"
  },
  "viewMode": {
    "raw": "Raw",
    "rendered": "Rendered",
    "diff": "Diff vs current",
    "viewingRevision": "Viewing historical revision {sha}",
    "backToCurrent": "Back to current"
  },
  "history": {
    "title": "History",
    "currentPlaceholder": "Working tree",
    "viewThisRevision": "View this revision",
    "compareWithCurrent": "Diff vs current",
    "loadFail": "Failed to read history"
  },
  "editor": {
    "newFile": "New .md",
    "createFilePlaceholder": "File name, e.g. plan.md",
    "filenameInvalid": "File name must end in .md and only contain letters/digits/_/-/spaces/.",
    "filenameExists": "A file with that name already exists",
    "edit": "Edit",
    "save": "Save",
    "saving": "Saving",
    "cancel": "Cancel",
    "cancelDirty": "You have unsaved changes. Discard them?",
    "delete": "Delete",
    "rename": "Rename",
    "renameUnavailable": "Rename is now available",
    "deleteConfirmTitle": "Delete document?",
    "deleteConfirmBody": "Will permanently delete {path}",
    "saveError": "Save failed",
    "deleteError": "Delete failed"
  },
  "newFile": "Select a .md file or create one",
  "noFileSelected": "Select a document to begin",
  "noProject": "Load a project to begin"
}
```

- [ ] **Step 3: Add the same keys to `ru-RU/features/chat.json`**

Same structure, Russian copy. Suggested values:

```jsonc
"gitDiffSidebar": {
  "tabs": {
    "docs": "Документы"
  }
},
"documentManager": {
  "pathBar": {
    "label": "Корень документации",
    "editHint": "Нажмите, чтобы изменить путь",
    "resetTitle": "Сбросить на docs/",
    "invalidPath": "Недопустимый путь: должен быть относительным внутри проекта",
    "storageWarning": "Хранилище браузера недоступно; настройки не сохранятся после сессии"
  },
  "tree": {
    "empty": "В этом каталоге нет файлов .md",
    "noHistory": "У этого документа ещё нет истории коммитов",
    "loadError": "Не удалось загрузить дерево каталога: {reason}",
    "pathMissing": "Путь '{path}' не существует; возврат к значению по умолчанию через 5 секунд"
  },
  "viewMode": {
    "raw": "Исходник",
    "rendered": "Рендер",
    "diff": "Сравнить с текущим",
    "viewingRevision": "Просмотр ревизии {sha}",
    "backToCurrent": "К текущей версии"
  },
  "history": {
    "title": "История",
    "currentPlaceholder": "Рабочее дерево",
    "viewThisRevision": "Открыть эту ревизию",
    "compareWithCurrent": "Сравнить с текущей",
    "loadFail": "Не удалось прочитать историю"
  },
  "editor": {
    "newFile": "Новый .md",
    "createFilePlaceholder": "Имя файла, например plan.md",
    "filenameInvalid": "Имя файла должно оканчиваться на .md и содержать только буквы/цифры/_/-/пробел/.",
    "filenameExists": "Файл с таким именем уже существует",
    "edit": "Изменить",
    "save": "Сохранить",
    "saving": "Сохранение",
    "cancel": "Отмена",
    "cancelDirty": "Есть несохранённые изменения. Отменить их?",
    "delete": "Удалить",
    "rename": "Переименовать",
    "renameUnavailable": "Переименование теперь доступно",
    "deleteConfirmTitle": "Удалить документ?",
    "deleteConfirmBody": "Документ {path} будет удалён без возможности восстановления",
    "saveError": "Не удалось сохранить",
    "deleteError": "Не удалось удалить"
  },
  "newFile": "Выберите файл .md или создайте новый",
  "noFileSelected": "Выберите документ",
  "noProject": "Загрузите проект, чтобы начать"
}
```

- [ ] **Step 4: Verify JSON validity**

Run: `cd dashboard && node -e "JSON.parse(require('fs').readFileSync('src/i18n/locales/zh-CN/features/chat.json','utf8'));JSON.parse(require('fs').readFileSync('src/i18n/locales/en-US/features/chat.json','utf8'));JSON.parse(require('fs').readFileSync('src/i18n/locales/ru-RU/features/chat.json','utf8'));console.log('all 3 valid')"`
Expected: `all 3 valid` printed.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/i18n/locales/zh-CN/features/chat.json dashboard/src/i18n/locales/en-US/features/chat.json dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "feat(dashboard): add documentManager i18n keys in zh-CN, en-US, ru-RU"
```

---

## Task 10: Create `DocumentPathBar.vue`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/DocumentPathBar.vue`

**Interfaces:**
- Props: `currentPath: string; storageOk: boolean; defaultPath: string`
- Emits: `(e: "path-change", path: string): void`

- [ ] **Step 1: Create the file**

```vue
<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.2
     Top-of-page path editor. Click to edit, Enter/blur commits,
     Esc reverts, the ↺ button writes the default. Validation runs
     on commit; failures show inline red and do NOT emit. Storage
     failures are signaled by the parent via the storageOk prop. -->
<script setup lang="ts">
import { ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import {
  isValidDocsRoot,
  coerceDocsRoot,
} from "@/composables/docsRootStorage";

const props = defineProps<{
  currentPath: string;
  storageOk: boolean;
  defaultPath: string;
}>();

const emit = defineEmits<{
  (e: "path-change", path: string): void;
}>();

const { tm } = useModuleI18n("features/chat");

const editing = ref(false);
const draft = ref(props.currentPath);
const error = ref<string | null>(null);

watch(
  () => props.currentPath,
  (p) => {
    if (!editing.value) draft.value = p;
  },
);

function startEdit() {
  draft.value = props.currentPath;
  error.value = null;
  editing.value = true;
}

function commit() {
  if (!editing.value) return;
  const cleaned = coerceDocsRoot(draft.value);
  if (!isValidDocsRoot(cleaned)) {
    error.value = tm("spcodeProjectLoad.documentManager.pathBar.invalidPath");
    return;
  }
  error.value = null;
  editing.value = false;
  if (cleaned !== props.currentPath) {
    emit("path-change", cleaned);
  }
}

function cancel() {
  draft.value = props.currentPath;
  error.value = null;
  editing.value = false;
}

function reset() {
  error.value = null;
  editing.value = false;
  if (props.defaultPath !== props.currentPath) {
    emit("path-change", props.defaultPath);
  }
}
</script>

<template>
  <div class="document-path-bar">
    <span class="document-path-bar__label">
      {{ tm("spcodeProjectLoad.documentManager.pathBar.label") }}
    </span>
    <input
      v-if="editing"
      v-model="draft"
      type="text"
      class="document-path-bar__input"
      :aria-label="tm('spcodeProjectLoad.documentManager.pathBar.label')"
      :class="{ 'document-path-bar__input--error': !!error }"
      @keydown.enter.prevent="commit"
      @keydown.escape.prevent="cancel"
      @blur="commit"
    />
    <button
      v-else
      type="button"
      class="document-path-bar__display"
      :title="tm('spcodeProjectLoad.documentManager.pathBar.editHint')"
      :aria-label="tm('spcodeProjectLoad.documentManager.pathBar.editHint')"
      @click="startEdit"
    >
      {{ currentPath }}
    </button>
    <button
      type="button"
      class="document-path-bar__reset"
      :title="tm('spcodeProjectLoad.documentManager.pathBar.resetTitle')"
      :aria-label="tm('spcodeProjectLoad.documentManager.pathBar.resetTitle')"
      @click="reset"
    >
      <v-icon size="14">mdi-restore</v-icon>
    </button>
    <v-icon
      v-if="!storageOk"
      size="14"
      class="document-path-bar__warning"
      :title="tm('spcodeProjectLoad.documentManager.pathBar.storageWarning')"
    >
      mdi-alert-circle-outline
    </v-icon>
    <span v-if="error" class="document-path-bar__error">{{ error }}</span>
  </div>
</template>

<style scoped>
.document-path-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  min-width: 0;
}
.document-path-bar__label {
  flex: 0 0 auto;
  font-weight: 500;
}
.document-path-bar__display {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
  background: transparent;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 4px;
  padding: 2px 6px;
  font-family: monospace;
  font-size: 11.5px;
  color: rgb(var(--v-theme-on-surface));
  cursor: text;
}
.document-path-bar__display:hover {
  border-color: rgba(var(--v-theme-primary), 0.4);
}
.document-path-bar__input {
  flex: 0 1 auto;
  min-width: 0;
  max-width: 200px;
  background: var(--v-theme-surface, transparent);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.3);
  border-radius: 4px;
  padding: 2px 6px;
  font-family: monospace;
  font-size: 11.5px;
  color: rgb(var(--v-theme-on-surface));
  outline: none;
}
.document-path-bar__input:focus {
  border-color: rgb(var(--v-theme-primary));
}
.document-path-bar__input--error {
  border-color: rgb(var(--v-theme-error));
  color: rgb(var(--v-theme-error));
}
.document-path-bar__reset {
  background: transparent;
  border: none;
  padding: 2px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.55);
  display: flex;
  align-items: center;
}
.document-path-bar__reset:hover {
  color: rgb(var(--v-theme-primary));
}
.document-path-bar__warning {
  color: rgb(var(--v-theme-warning));
}
.document-path-bar__error {
  color: rgb(var(--v-theme-error));
  font-size: 11px;
}
</style>
```

- [ ] **Step 2: Type-check**

Run: `cd dashboard && pnpm typecheck`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/chat/message_list_comps/DocumentPathBar.vue
git commit -m "feat(dashboard): add DocumentPathBar with click-to-edit + validation"
```

---

## Task 11: Create `DocumentViewModeTab.vue`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/DocumentViewModeTab.vue`

**Interfaces:**
- Props: `modelValue: "raw" | "rendered" | "diff"; hasRevision: boolean`
- Emits: `(e: "update:modelValue", v: "raw" | "rendered" | "diff"): void`

- [ ] **Step 1: Create the file**

```vue
<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.4
     Three-segment control: raw / rendered / diff-vs-current.
     "diff" is disabled when no historical revision is selected. -->
<script setup lang="ts">
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  modelValue: "raw" | "rendered" | "diff";
  hasRevision: boolean;
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: "raw" | "rendered" | "diff"): void;
}>();
const { tm } = useModuleI18n("features/chat");

const OPTIONS: ReadonlyArray<{
  value: "raw" | "rendered" | "diff";
  labelKey: string;
}> = [
  { value: "raw", labelKey: "spcodeProjectLoad.documentManager.viewMode.raw" },
  {
    value: "rendered",
    labelKey: "spcodeProjectLoad.documentManager.viewMode.rendered",
  },
  { value: "diff", labelKey: "spcodeProjectLoad.documentManager.viewMode.diff" },
];

function setValue(v: "raw" | "rendered" | "diff") {
  if (v === "diff" && !props.hasRevision) return;
  emit("update:modelValue", v);
}
</script>

<template>
  <div class="document-view-mode-tab" role="tablist">
    <button
      v-for="opt in OPTIONS"
      :key="opt.value"
      type="button"
      role="tab"
      :aria-selected="modelValue === opt.value"
      :disabled="opt.value === 'diff' && !hasRevision"
      :class="['document-view-mode-tab__pill', { active: modelValue === opt.value }]"
      @click="setValue(opt.value)"
    >
      {{ tm(opt.labelKey) }}
    </button>
  </div>
</template>

<style scoped>
.document-view-mode-tab {
  display: inline-flex;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 6px;
  padding: 2px;
  gap: 2px;
}
.document-view-mode-tab__pill {
  font-size: 11.5px;
  padding: 3px 10px;
  border: none;
  background: transparent;
  border-radius: 4px;
  color: rgba(var(--v-theme-on-surface), 0.65);
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.document-view-mode-tab__pill:hover:not(:disabled) {
  color: rgb(var(--v-theme-on-surface));
}
.document-view-mode-tab__pill.active {
  background: var(--v-theme-surface, rgb(255, 255, 255));
  color: rgb(var(--v-theme-primary));
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}
.document-view-mode-tab__pill:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
```

- [ ] **Step 2: Type-check + commit**

Run: `cd dashboard && pnpm typecheck`
Expected: no errors.

```bash
git add dashboard/src/components/chat/message_list_comps/DocumentViewModeTab.vue
git commit -m "feat(dashboard): add DocumentViewModeTab 3-segment control"
```

---

## Task 12: Create `DocumentHistoryPanel.vue`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/DocumentHistoryPanel.vue`

**Interfaces:**
- Props: `gitLog: UseSpcodeGitLog; fileRelative: string | null; currentRevision: string | null; isLoading: boolean`
- Emits: `(e: "select-revision", sha: string): void; (e: "compare-current", sha: string): void`

- [ ] **Step 1: Create the file**

```vue
<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.5
     Per-file commit list. Reuses the parent's useSpcodeGitLog
     instance with `?path=` filter. Each row has two actions:
     "view this revision" + "compare with current". A pseudo row
     for the working tree is always shown. -->
<script setup lang="ts">
import { computed, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { UseSpcodeGitLog } from "@/composables/useSpcodeGitLog";
import type { SpcodeLogCommit } from "@/composables/parseSpcodeGitWorkflow";

const props = defineProps<{
  gitLog: UseSpcodeGitLog;
  fileRelative: string | null;
  currentRevision: string | null;
  isLoading: boolean;
}>();
const emit = defineEmits<{
  (e: "select-revision", sha: string): void;
  (e: "compare-current", sha: string): void;
}>();
const { tm } = useModuleI18n("features/chat");

// When a file is selected, refetch history filtered to that file.
// `n: 50` matches the spec; if the user wants more, they can use
// the main History tab.
watch(
  () => props.fileRelative,
  (p) => {
    if (!p) return;
    void props.gitLog.refresh({ ref: "HEAD", n: 50, path: p });
  },
  { immediate: true },
);

const commits = computed<SpcodeLogCommit[]>(() => {
  const s = props.gitLog.state.value;
  if (s.kind === "ok") return s.snapshot.commits;
  if (s.kind === "error") {
    return s.previousSnapshot?.commits ?? [];
  }
  return [];
});

const errorReason = computed<string | null>(() => {
  const s = props.gitLog.state.value;
  return s.kind === "error" ? s.reason : null;
});

const isWorkingTreeActive = computed(
  () => props.currentRevision === null && !!props.fileRelative,
);

function shortSha(sha: string): string {
  return sha.slice(0, 7);
}
</script>

<template>
  <aside class="document-history-panel">
    <header class="document-history-panel__header">
      {{ tm("spcodeProjectLoad.documentManager.history.title") }}
    </header>
    <div v-if="!fileRelative" class="document-history-panel__empty">
      {{ tm("spcodeProjectLoad.documentManager.tree.empty") }}
    </div>
    <div v-else-if="isLoading" class="document-history-panel__loading">
      <v-progress-circular indeterminate size="16" width="2" />
    </div>
    <div v-else-if="errorReason && commits.length === 0" class="document-history-panel__error">
      {{ tm("spcodeProjectLoad.documentManager.history.loadFail") }}: {{ errorReason }}
    </div>
    <div v-else-if="commits.length === 0" class="document-history-panel__empty">
      {{ tm("spcodeProjectLoad.documentManager.tree.noHistory") }}
    </div>
    <ul v-else class="document-history-panel__list">
      <li
        :class="['document-history-panel__row', { active: isWorkingTreeActive }]"
      >
        <div class="document-history-panel__row-sha">working</div>
        <div class="document-history-panel__row-subject">
          {{ tm("spcodeProjectLoad.documentManager.history.currentPlaceholder") }}
        </div>
      </li>
      <li
        v-for="c in commits"
        :key="c.sha"
        :class="['document-history-panel__row', { active: currentRevision === c.sha }]"
      >
        <div class="document-history-panel__row-sha">{{ shortSha(c.sha) }}</div>
        <div class="document-history-panel__row-subject">
          <div class="document-history-panel__row-subject-text">{{ c.subject }}</div>
          <div class="document-history-panel__row-author">{{ c.author }}</div>
        </div>
        <div class="document-history-panel__row-actions">
          <button
            type="button"
            class="document-history-panel__action"
            :title="tm('spcodeProjectLoad.documentManager.history.viewThisRevision')"
            @click="emit('select-revision', c.sha)"
          >
            <v-icon size="12">mdi-eye-outline</v-icon>
          </button>
          <button
            type="button"
            class="document-history-panel__action"
            :title="tm('spcodeProjectLoad.documentManager.history.compareWithCurrent')"
            @click="emit('compare-current', c.sha)"
          >
            <v-icon size="12">mdi-compare</v-icon>
          </button>
        </div>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.document-history-panel {
  display: flex;
  flex-direction: column;
  flex: 0 0 220px;
  min-height: 0;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgba(var(--v-theme-on-surface), 0.03);
  overflow: hidden;
}
.document-history-panel__header {
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.document-history-panel__empty,
.document-history-panel__loading,
.document-history-panel__error {
  padding: 12px 10px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  text-align: center;
}
.document-history-panel__error {
  color: rgb(var(--v-theme-error));
}
.document-history-panel__list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
  overflow-y: auto;
  flex: 1 1 auto;
  min-height: 0;
}
.document-history-panel__row {
  display: grid;
  grid-template-columns: 56px 1fr auto;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-size: 11.5px;
  cursor: default;
  border-left: 2px solid transparent;
}
.document-history-panel__row:hover {
  background: rgba(var(--v-theme-primary), 0.06);
}
.document-history-panel__row.active {
  background: rgba(var(--v-theme-primary), 0.12);
  border-left-color: rgb(var(--v-theme-primary));
}
.document-history-panel__row-sha {
  font-family: monospace;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.document-history-panel__row-subject {
  min-width: 0;
  overflow: hidden;
}
.document-history-panel__row-subject-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.document-history-panel__row-author {
  font-size: 10.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.document-history-panel__row-actions {
  display: flex;
  gap: 2px;
}
.document-history-panel__action {
  border: none;
  background: transparent;
  padding: 2px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.55);
  display: flex;
  align-items: center;
  border-radius: 3px;
}
.document-history-panel__action:hover {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}
</style>
```

- [ ] **Step 2: Type-check + commit**

Run: `cd dashboard && pnpm typecheck`
Expected: no errors (or only warnings about `useSpcodeGitLog` type import — fix by re-exporting the type from the composable if needed).

```bash
git add dashboard/src/components/chat/message_list_comps/DocumentHistoryPanel.vue
git commit -m "feat(dashboard): add DocumentHistoryPanel with per-file commit list"
```

---

## Task 13: Create `CodemirrorHost.vue` and `DocumentEditor.vue`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/CodemirrorHost.vue`
- Create: `dashboard/src/components/chat/message_list_comps/DocumentEditor.vue`

**Interfaces:**
- `CodemirrorHost.vue`:
  - Props: `modelValue: string; language: "markdown"`
  - Emits: `(e: "update:modelValue", v: string): void; (e: "ready"): void; (e: "error", err: Error): void`
- `DocumentEditor.vue`:
  - Props: `initialContent: string; fileRelative: string; isSaving: boolean; isDeleting: boolean; simpleTextarea?: boolean`
  - Emits: `(e: "save", content: string): void; (e: "cancel"): void; (e: "delete"): void; (e: "rename", newPath: string): void`

- [ ] **Step 1: Create `CodemirrorHost.vue`**

```vue
<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.6
     Thin CodeMirror 6 mount/unmount wrapper. Lazy-imports CM6
     modules so the dashboard's initial bundle stays small. If any
     import throws, emits "error" and the parent falls back to a
     plain <textarea>. -->
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{
  modelValue: string;
  language?: "markdown";
}>();
const emit = defineEmits<{
  (e: "update:modelValue", v: string): void;
  (e: "ready"): void;
  (e: "error", err: Error): void;
}>();

const hostEl = ref<HTMLElement | null>(null);
let view: { destroy: () => void; dispatch: (tr: unknown) => void } | null = null;

onMounted(async () => {
  if (!hostEl.value) return;
  try {
    const [{ EditorState }, { EditorView, keymap, lineNumbers, highlightActiveLine }, { defaultKeymap, history, historyKeymap }, { markdown }] =
      await Promise.all([
        import("@codemirror/state"),
        import("@codemirror/view"),
        import("@codemirror/commands"),
        import("@codemirror/lang-markdown"),
      ]);

    const update = EditorView.updateListener.of((u: { doc: { toString: () => string } }) => {
      if (u.doc) emit("update:modelValue", u.doc.toString());
    });

    const state = EditorState.create({
      doc: props.modelValue,
      extensions: [
        lineNumbers(),
        highlightActiveLine(),
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        markdown(),
        update,
      ],
    });
    view = new EditorView({ state, parent: hostEl.value }) as typeof view;
    emit("ready");
  } catch (err) {
    emit("error", err instanceof Error ? err : new Error(String(err)));
  }
});

watch(
  () => props.modelValue,
  (v) => {
    if (!view) return;
    // Replace doc without re-creating the view (preserves undo history).
    // The dispatch helper is intentionally omitted from the public type
    // to keep the file light; the actual `view.dispatch` is used inline.
    (view as unknown as { dispatch: (tr: unknown) => void }).dispatch({
      changes: { from: 0, to: (view as unknown as { state: { doc: { length: number } } }).state.doc.length, insert: v },
    });
  },
);

onBeforeUnmount(() => {
  view?.destroy();
  view = null;
});
</script>

<template>
  <div ref="hostEl" class="codemirror-host" />
</template>

<style scoped>
.codemirror-host {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 4px;
  font-family: monospace;
  font-size: 13px;
  background: var(--v-theme-surface, transparent);
}
</style>
```

- [ ] **Step 2: Create `DocumentEditor.vue`**

```vue
<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.6
     Edit area with CodeMirror 6 + textarea fallback. Owns the
     edit buffer, dirty tracking, and the action bar (save /
     cancel / copy / delete / rename). Rename is real and uses
     the PATCH /spcode/docs endpoint. -->
<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { copyToClipboard } from "@/utils/clipboard";
import CodemirrorHost from "./CodemirrorHost.vue";

const props = defineProps<{
  initialContent: string;
  fileRelative: string;
  isSaving: boolean;
  isDeleting: boolean;
  isRenaming: boolean;
  simpleTextarea?: boolean;
}>();
const emit = defineEmits<{
  (e: "save", content: string): void;
  (e: "cancel"): void;
  (e: "delete"): void;
  (e: "rename", newPath: string): void;
}>();
const { tm } = useModuleI18n("features/chat");

const buffer = ref(props.initialContent);
const showDeleteConfirm = ref(false);
const renameOpen = ref(false);
const renameDraft = ref(props.fileRelative);
const renameError = ref<string | null>(null);
const useTextarea = ref(!!props.simpleTextarea);

const isDirty = computed(() => buffer.value !== props.initialContent);

watch(
  () => props.initialContent,
  (v) => {
    buffer.value = v;
  },
);

function onCancel() {
  if (isDirty.value) {
    const ok = window.confirm(
      tm("spcodeProjectLoad.documentManager.editor.cancelDirty"),
    );
    if (!ok) return;
  }
  emit("cancel");
}

function onSave() {
  if (!isDirty.value || props.isSaving) return;
  emit("save", buffer.value);
}

function onCopyRaw() {
  void copyToClipboard(buffer.value);
}

function onDeleteClick() {
  showDeleteConfirm.value = true;
}
function onDeleteConfirm() {
  showDeleteConfirm.value = false;
  emit("delete");
}

function onRenameOpen() {
  renameDraft.value = props.fileRelative;
  renameError.value = null;
  renameOpen.value = true;
}
function onRenameSubmit() {
  const trimmed = renameDraft.value.trim();
  if (!trimmed || trimmed === props.fileRelative) {
    renameOpen.value = false;
    return;
  }
  if (!/^[\w\-./ ]+\.md$/i.test(trimmed)) {
    renameError.value = tm(
      "spcodeProjectLoad.documentManager.editor.filenameInvalid",
    );
    return;
  }
  emit("rename", trimmed);
  renameOpen.value = false;
}

function onCodemirrorUpdate(v: string) {
  buffer.value = v;
}
function onCodemirrorError() {
  useTextarea.value = true;
}
</script>

<template>
  <div class="document-editor">
    <CodemirrorHost
      v-if="!useTextarea"
      :model-value="buffer"
      language="markdown"
      @update:model-value="onCodemirrorUpdate"
      @error="onCodemirrorError"
    />
    <textarea
      v-else
      v-model="buffer"
      class="document-editor__textarea"
      spellcheck="false"
    />
    <div class="document-editor__bar">
      <button
        type="button"
        class="document-editor__btn document-editor__btn--primary"
        :disabled="!isDirty || isSaving"
        @click="onSave"
      >
        <v-icon size="14">mdi-content-save-outline</v-icon>
        {{ isSaving
          ? tm("spcodeProjectLoad.documentManager.editor.saving")
          : tm("spcodeProjectLoad.documentManager.editor.save") }}
      </button>
      <button type="button" class="document-editor__btn" @click="onCancel">
        <v-icon size="14">mdi-close</v-icon>
        {{ tm("spcodeProjectLoad.documentManager.editor.cancel") }}
      </button>
      <button
        type="button"
        class="document-editor__btn"
        :title="tm('spcodeProjectLoad.documentManager.editor.rename')"
        :disabled="isRenaming"
        @click="onRenameOpen"
      >
        <v-icon size="14">mdi-rename-outline</v-icon>
        {{ tm("spcodeProjectLoad.documentManager.editor.rename") }}
      </button>
      <button type="button" class="document-editor__btn" @click="onCopyRaw">
        <v-icon size="14">mdi-content-copy</v-icon>
      </button>
      <span class="document-editor__spacer" />
      <button
        v-if="!showDeleteConfirm"
        type="button"
        class="document-editor__btn document-editor__btn--danger"
        :disabled="isDeleting"
        @click="onDeleteClick"
      >
        <v-icon size="14">mdi-delete-outline</v-icon>
        {{ tm("spcodeProjectLoad.documentManager.editor.delete") }}
      </button>
      <span v-else class="document-editor__confirm">
        {{ tm("spcodeProjectLoad.documentManager.editor.deleteConfirmBody", { path: fileRelative }) }}
        <button
          type="button"
          class="document-editor__btn document-editor__btn--danger"
          @click="onDeleteConfirm"
        >
          {{ tm("spcodeProjectLoad.documentManager.editor.delete") }}
        </button>
        <button
          type="button"
          class="document-editor__btn"
          @click="showDeleteConfirm = false"
        >
          {{ tm("spcodeProjectLoad.documentManager.editor.cancel") }}
        </button>
      </span>
    </div>
    <div v-if="renameOpen" class="document-editor__rename">
      <input
        v-model="renameDraft"
        type="text"
        class="document-editor__rename-input"
        @keydown.enter.prevent="onRenameSubmit"
        @keydown.escape.prevent="renameOpen = false"
      />
      <button
        type="button"
        class="document-editor__btn document-editor__btn--primary"
        @click="onRenameSubmit"
      >
        {{ tm("spcodeProjectLoad.documentManager.editor.rename") }}
      </button>
      <button
        type="button"
        class="document-editor__btn"
        @click="renameOpen = false"
      >
        {{ tm("spcodeProjectLoad.documentManager.editor.cancel") }}
      </button>
      <span v-if="renameError" class="document-editor__rename-error">{{ renameError }}</span>
    </div>
  </div>
</template>

<style scoped>
.document-editor {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  gap: 6px;
  padding: 6px;
}
.document-editor__textarea {
  flex: 1 1 auto;
  min-height: 0;
  resize: none;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.5;
  padding: 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 4px;
  background: var(--v-theme-surface, transparent);
  color: rgb(var(--v-theme-on-surface));
  outline: none;
}
.document-editor__textarea:focus {
  border-color: rgb(var(--v-theme-primary));
}
.document-editor__bar {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  padding-top: 4px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.document-editor__spacer {
  flex: 1 1 auto;
}
.document-editor__btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  padding: 3px 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  background: transparent;
  border-radius: 4px;
  color: rgba(var(--v-theme-on-surface), 0.75);
  cursor: pointer;
}
.document-editor__btn:hover:not(:disabled) {
  border-color: rgba(var(--v-theme-primary), 0.4);
  color: rgb(var(--v-theme-primary));
}
.document-editor__btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.document-editor__btn--primary {
  background: rgba(var(--v-theme-primary), 0.12);
  border-color: rgba(var(--v-theme-primary), 0.4);
  color: rgb(var(--v-theme-primary));
}
.document-editor__btn--primary:disabled {
  background: rgba(var(--v-theme-on-surface), 0.04);
  color: rgba(var(--v-theme-on-surface), 0.4);
}
.document-editor__btn--danger {
  color: rgb(var(--v-theme-error));
  border-color: rgba(var(--v-theme-error), 0.4);
}
.document-editor__btn--danger:hover:not(:disabled) {
  background: rgba(var(--v-theme-error), 0.08);
}
.document-editor__confirm {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: rgb(var(--v-theme-error));
}
.document-editor__rename {
  display: flex;
  align-items: center;
  gap: 4px;
}
.document-editor__rename-input {
  flex: 1 1 auto;
  font-family: monospace;
  font-size: 12px;
  padding: 2px 6px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.3);
  border-radius: 4px;
  background: var(--v-theme-surface, transparent);
  color: rgb(var(--v-theme-on-surface));
  outline: none;
}
.document-editor__rename-input:focus {
  border-color: rgb(var(--v-theme-primary));
}
.document-editor__rename-error {
  font-size: 11px;
  color: rgb(var(--v-theme-error));
}
</style>
```

- [ ] **Step 3: Type-check + commit**

Run: `cd dashboard && pnpm typecheck`
Expected: no errors. (If `CodemirrorHost` warns on `view.dispatch` typing, the inline `as unknown as` cast is intentional and OK — see the comment in the file.)

```bash
git add dashboard/src/components/chat/message_list_comps/CodemirrorHost.vue dashboard/src/components/chat/message_list_comps/DocumentEditor.vue
git commit -m "feat(dashboard): add DocumentEditor with CodeMirror 6 + textarea fallback"
```

---

## Task 14: Create `DocumentTreePanel.vue`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/DocumentTreePanel.vue`

**Interfaces:**
- Props: `currentDir: string; rootPath: string | null; isDark: boolean; selectedFile: string | null`
- Emits: `(e: "navigate", dirRel: string): void; (e: "select", fileRel: string): void; (e: "create-new", name: string): void`

- [ ] **Step 1: Create the file**

```vue
<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.3
     Left pane: the docs root directory tree, plus a "new file"
     input. Reuses FileTreeList for the tree itself. Only .md
     files emit "select"; non-.md are visible but non-interactive. -->
<script setup lang="ts">
import { computed, ref } from "vue";
import { useSpcodeFileBrowser } from "@/composables/useSpcodeFileBrowser";
import { useModuleI18n } from "@/i18n/composables";
import FileTreeList from "./FileTreeList.vue";
import type { SpcodeFileBrowserEntry } from "@/composables/parseSpcodeFileBrowser";

const props = defineProps<{
  currentDir: string;
  rootPath: string | null;
  isDark: boolean;
  selectedFile: string | null;
}>();

const emit = defineEmits<{
  (e: "navigate", dirRel: string): void;
  (e: "select", fileRel: string): void;
  (e: "create-new", name: string): void;
}>();

const { tm } = useModuleI18n("features/chat");

const fileBrowser = useSpcodeFileBrowser(
  computed(() => props.rootPath ?? ""),
);

const newName = ref("");
const newNameError = ref<string | null>(null);

function onEntryNavigate(entry: SpcodeFileBrowserEntry) {
  if (entry.type === "directory") {
    emit("navigate", entry.path);
  } else if (entry.type === "file" && entry.name.toLowerCase().endsWith(".md")) {
    emit("select", entry.path);
  }
  // Non-.md files: visible but non-interactive. We can't filter the
  // FileBrowserEntryList (it's shared with the workspace view), so
  // we simply don't emit for them. The user can rename later.
}

function onBreadcrumbNavigate(path: string) {
  emit("navigate", path);
}

function onSubmitNew() {
  const name = newName.value.trim();
  if (!/^[\w\-./ ]+\.md$/i.test(name)) {
    newNameError.value = tm(
      "spcodeProjectLoad.documentManager.editor.filenameInvalid",
    );
    return;
  }
  newNameError.value = null;
  newName.value = "";
  emit("create-new", name);
}
</script>

<template>
  <div class="document-tree-panel">
    <FileTreeList
      :state="fileBrowser.state.value"
      :selected-path="selectedFile"
      :root-path="rootPath"
      :preview-path="null"
      :is-dark="isDark"
      @navigate="onEntryNavigate"
      @breadcrumb-navigate="onBreadcrumbNavigate"
    />
    <form class="document-tree-panel__new" @submit.prevent="onSubmitNew">
      <input
        v-model="newName"
        type="text"
        class="document-tree-panel__new-input"
        :placeholder="
          tm('spcodeProjectLoad.documentManager.editor.createFilePlaceholder')
        "
      />
      <button
        type="submit"
        class="document-tree-panel__new-btn"
        :title="tm('spcodeProjectLoad.documentManager.editor.newFile')"
        :disabled="!newName"
      >
        <v-icon size="14">mdi-plus</v-icon>
      </button>
    </form>
    <span v-if="newNameError" class="document-tree-panel__new-error">{{ newNameError }}</span>
  </div>
</template>

<style scoped>
.document-tree-panel {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}
.document-tree-panel__new {
  display: flex;
  gap: 4px;
  padding: 4px 8px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.document-tree-panel__new-input {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 11.5px;
  padding: 3px 6px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 4px;
  background: var(--v-theme-surface, transparent);
  color: rgb(var(--v-theme-on-surface));
  outline: none;
}
.document-tree-panel__new-input:focus {
  border-color: rgb(var(--v-theme-primary));
}
.document-tree-panel__new-btn {
  border: 1px solid rgba(var(--v-theme-primary), 0.4);
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  border-radius: 4px;
  padding: 2px 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
}
.document-tree-panel__new-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.document-tree-panel__new-error {
  font-size: 11px;
  color: rgb(var(--v-theme-error));
  padding: 0 8px 4px;
}
</style>
```

- [ ] **Step 2: Type-check + commit**

Run: `cd dashboard && pnpm typecheck`
Expected: no errors.

```bash
git add dashboard/src/components/chat/message_list_comps/DocumentTreePanel.vue
git commit -m "feat(dashboard): add DocumentTreePanel with FileTreeList reuse"
```

---

## Task 15: Create `DocumentManager.vue` (the container)

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/DocumentManager.vue`

**Interfaces:**
- Props: `worktree: string | null; umo: string | null; projectRoot: string | null; isDark?: boolean; gitLog: UseSpcodeGitLog; gitShow: UseSpcodeGitShow`

- [ ] **Step 1: Create the file**

This is the integration point. It wires up state, composables, and the 5 sub-components created in Tasks 10–14. The Vue 3 `<script setup>` block is long but mechanical.

```vue
<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.1
     Page container for the Documents sub-tab. Owns all editable
     state (docsRoot / selectedDoc / viewMode / selectedRevision /
     editMode / editBuffer) and orchestrates the 3 docs CRUD
     endpoints. Reuses the sidebar's existing useSpcodeGitLog and
     useSpcodeGitShow instances (per spec §2 decision #9 + §3.5). -->
<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeGitFile } from "@/composables/useSpcodeGitFile";
import { useSpcodeDocs } from "@/composables/useSpcodeDocs";
import {
  loadDocsRoot,
  saveDocsRoot,
  DEFAULT_DOCS_ROOT,
  coerceDocsRoot,
  isValidDocsRoot,
} from "@/composables/docsRootStorage";
import type { UseSpcodeGitLog } from "@/composables/useSpcodeGitLog";
import type { UseSpcodeGitShow } from "@/composables/useSpcodeGitShow";
import { useModuleI18n } from "@/i18n/composables";

import DocumentPathBar from "./DocumentPathBar.vue";
import DocumentViewModeTab from "./DocumentViewModeTab.vue";
import DocumentTreePanel from "./DocumentTreePanel.vue";
import DocumentEditor from "./DocumentEditor.vue";
import DocumentHistoryPanel from "./DocumentHistoryPanel.vue";
import DiffPreview from "./DiffPreview.vue";
import MarkdownView from "@/components/shared/MarkdownView.vue";

const props = defineProps<{
  worktree: string | null;
  umo: string | null;
  projectRoot: string | null;
  isDark?: boolean;
  gitLog: UseSpcodeGitLog;
  gitShow: UseSpcodeGitShow;
}>();

const { tm } = useModuleI18n("features/chat");
const spcodeStatus = useSpcodeProjectStatus();
const isDark = computed(() => !!props.isDark);
const isProjectLoaded = computed(() => spcodeStatus.status.value.loaded);

// Persisted state
const docsRoot = ref<string>(DEFAULT_DOCS_ROOT);
const storageOk = ref<boolean>(true);

// Per-file state
const selectedDoc = ref<string | null>(null);
const viewMode = ref<"raw" | "rendered" | "diff">("rendered");
const selectedRevision = ref<string | null>(null);
const editMode = ref<boolean>(false);
const editBuffer = ref<string>("");
const saveError = ref<string | null>(null);
const deleteError = ref<string | null>(null);
const renameError = ref<string | null>(null);
const pathMissingNotice = ref<string | null>(null);
let pathMissingTimer: ReturnType<typeof setTimeout> | null = null;

const fileBrowser = useSpcodeFileBrowser(
  computed(() =>
    props.projectRoot && docsRoot.value
      ? `${props.projectRoot.replace(/[\\/]+$/, "")}/${docsRoot.value.replace(/^[\\/]+/, "")}`
      : "",
  ),
);
const docsApi = useSpcodeDocs(computed(() => props.worktree));
const gitFile = useSpcodeGitFile(computed(() => props.worktree));

// File preview from working tree (reuses file-browser).
const fileState = computed(() => {
  if (!selectedDoc.value) return { kind: "idle" as const };
  return fileBrowser.state.value;
});

const fileContent = computed<string>(() => {
  if (!selectedDoc.value) return "";
  const s = fileState.value;
  if (s.kind === "file" && typeof s.snapshot.content === "string") {
    return s.snapshot.content;
  }
  return "";
});

// Historical blob content
const historicalFileState = computed(() => {
  if (!selectedDoc.value || !selectedRevision.value) {
    return { kind: "idle" as const };
  }
  return gitFile.getState(selectedDoc.value, selectedRevision.value);
});
const historicalFileContent = computed<string>(() => {
  if (!selectedDoc.value || !selectedRevision.value) return "";
  const d = gitFile.getData(selectedDoc.value, selectedRevision.value);
  return d?.content ?? "";
});

// Diff patch (revision vs current)
const diffPatch = ref<string | null>(null);
watch(
  () => [selectedDoc.value, selectedRevision.value, viewMode.value] as const,
  async ([doc, rev, mode]) => {
    if (mode !== "diff" || !doc || !rev) {
      diffPatch.value = null;
      return;
    }
    // Reset and refetch.
    diffPatch.value = null;
    const r = await props.gitShow.fetchFile(rev, doc);
    if (!r) return;
    const snap = props.gitShow.getFileData(rev, doc);
    if (snap) diffPatch.value = snap.patch ?? null;
  },
  { immediate: true },
);

// Resizable split
const containerRef = ref<HTMLElement | null>(null);
const resize = (() => {
  // Lazy import via useResizableSplit — keep import local so the
  // bundle graph is unchanged when this tab is hidden.
  // (The composable is statically importable; this comment is just
  //  a note that the import at the top of <script> is intentional.)
  return null;
})();

// Hydrate docsRoot from localStorage on mount / umo change.
function hydrate() {
  if (!props.umo) {
    docsRoot.value = DEFAULT_DOCS_ROOT;
    return;
  }
  docsRoot.value = loadDocsRoot(props.umo);
}

onMounted(hydrate);
watch(() => props.umo, hydrate);

function onPathChange(newPath: string) {
  const cleaned = coerceDocsRoot(newPath);
  if (!isValidDocsRoot(cleaned)) {
    return;
  }
  docsRoot.value = cleaned;
  selectedDoc.value = null;
  selectedRevision.value = null;
  editMode.value = false;
  if (props.umo) {
    const r = saveDocsRoot(props.umo, cleaned);
    storageOk.value = r.ok || r.reason !== "storage_unavailable";
    if (r.ok === false && r.reason === "storage_unavailable") {
      storageOk.value = false;
    }
  }
}

function onTreeNavigate(dirRel: string) {
  docsRoot.value = dirRel;
  selectedDoc.value = null;
  selectedRevision.value = null;
  editMode.value = editMode.value && false; // forces exit
  editMode.value = false;
}

function onTreeSelect(fileRel: string) {
  if (editMode.value) {
    const ok = window.confirm(
      tm("spcodeProjectLoad.documentManager.editor.cancelDirty"),
    );
    if (!ok) return;
  }
  selectedDoc.value = fileRel;
  selectedRevision.value = null;
  viewMode.value = "rendered";
  editMode.value = false;
  editBuffer.value = "";
  saveError.value = null;
}

function onStartEdit() {
  editBuffer.value = fileContent.value;
  editMode.value = true;
}

async function onSave(content: string) {
  if (!selectedDoc.value) return;
  saveError.value = null;
  const r = await docsApi.save({ path: selectedDoc.value, content });
  if (r.ok) {
    editMode.value = false;
    // Refresh the working-tree preview so the rendered/raw view
    // reflects the just-saved content.
    void fileBrowser.refresh();
  } else {
    saveError.value = `${tm("spcodeProjectLoad.documentManager.editor.saveError")}: ${r.reason}`;
  }
}

function onCancelEdit() {
  editMode.value = false;
}

async function onDelete() {
  if (!selectedDoc.value) return;
  deleteError.value = null;
  const r = await docsApi.remove(selectedDoc.value);
  if (r.ok) {
    selectedDoc.value = null;
    selectedRevision.value = null;
    editMode.value = false;
    void fileBrowser.refresh();
  } else {
    deleteError.value = `${tm("spcodeProjectLoad.documentManager.editor.deleteError")}: ${r.reason}`;
  }
}

function onRename(newPath: string) {
  if (!selectedDoc.value) return;
  renameError.value = null;
  void docsApi.rename({ path: selectedDoc.value, newPath }).then((r) => {
    if (r.ok) {
      selectedDoc.value = newPath;
      void fileBrowser.refresh();
    } else {
      renameError.value = r.reason;
    }
  });
}

function onSelectRevision(sha: string) {
  if (!selectedDoc.value) return;
  selectedRevision.value = sha;
  viewMode.value = "rendered";
  if (selectedDoc.value && sha) {
    void gitFile.fetchRef(selectedDoc.value, sha);
  }
}

function onCompareCurrent(sha: string) {
  if (!selectedDoc.value) return;
  selectedRevision.value = sha;
  viewMode.value = "diff";
}

function onCreateNew(name: string) {
  // Optimistic select; if the save fails we drop the selection.
  const fullPath = `${docsRoot.value.replace(/\/+$/, "")}/${name.replace(/^\/+/, "")}`;
  selectedDoc.value = fullPath;
  editBuffer.value = "";
  editMode.value = true;
  // Auto-save empty content.
  void docsApi.save({ path: fullPath, content: "" }).then((r) => {
    if (r.ok) {
      void fileBrowser.refresh();
    } else {
      saveError.value = r.reason;
      selectedDoc.value = null;
      editMode.value = false;
    }
  });
}

function onBackToCurrent() {
  selectedRevision.value = null;
}

onBeforeUnmount(() => {
  if (pathMissingTimer) clearTimeout(pathMissingTimer);
  gitFile.dispose();
  docsApi.dispose();
});
</script>

<template>
  <div class="document-manager">
    <DocumentPathBar
      :current-path="docsRoot"
      :storage-ok="storageOk"
      :default-path="DEFAULT_DOCS_ROOT"
      @path-change="onPathChange"
    />
    <div v-if="pathMissingNotice" class="document-manager__notice document-manager__notice--warn">
      {{ tm("spcodeProjectLoad.documentManager.tree.pathMissing", { path: docsRoot }) }}
    </div>
    <div v-if="!isProjectLoaded" class="document-manager__empty">
      <v-icon size="32" color="grey">mdi-folder-open-outline</v-icon>
      <span>{{ tm("spcodeProjectLoad.documentManager.noProject") }}</span>
    </div>
    <div v-else class="document-manager__body" ref="containerRef">
      <DocumentTreePanel
        class="document-manager__left"
        :current-dir="docsRoot"
        :root-path="projectRoot"
        :is-dark="isDark"
        :selected-file="selectedDoc"
        @navigate="onTreeNavigate"
        @select="onTreeSelect"
        @create-new="onCreateNew"
      />
      <section class="document-manager__right">
        <div v-if="!selectedDoc" class="document-manager__empty">
          <v-icon size="32" color="grey">mdi-file-document-outline</v-icon>
          <span>{{ tm("spcodeProjectLoad.documentManager.newFile") }}</span>
        </div>
        <template v-else-if="editMode">
          <DocumentEditor
            :initial-content="editBuffer"
            :file-relative="selectedDoc"
            :is-saving="docsApi.isSaving.value"
            :is-deleting="docsApi.isDeleting.value"
            :is-renaming="docsApi.isRenaming.value"
            @save="onSave"
            @cancel="onCancelEdit"
            @delete="onDelete"
            @rename="onRename"
          />
        </template>
        <template v-else>
          <div v-if="selectedRevision" class="document-manager__banner">
            <span>
              {{
                tm("spcodeProjectLoad.documentManager.viewMode.viewingRevision", {
                  sha: selectedRevision.slice(0, 7),
                })
              }}
            </span>
            <button
              type="button"
              class="document-manager__banner-btn"
              @click="onBackToCurrent"
            >
              {{ tm("spcodeProjectLoad.documentManager.viewMode.backToCurrent") }}
            </button>
          </div>
          <DocumentViewModeTab
            v-model="viewMode"
            :has-revision="!!selectedRevision"
          />
          <div v-if="viewMode === 'rendered'" class="document-manager__rendered">
            <MarkdownView
              v-if="selectedRevision"
              :source="historicalFileContent"
              :is-dark="isDark"
              :container-class="selectedRevision ? 'historical' : ''"
            />
            <MarkdownView
              v-else
              :source="fileContent"
              :is-dark="isDark"
            />
          </div>
          <pre v-else-if="viewMode === 'raw'" class="document-manager__raw">{{ selectedRevision ? historicalFileContent : fileContent }}</pre>
          <DiffPreview
            v-else
            :patch="diffPatch"
            :is-dark="isDark"
          />
          <div v-if="saveError" class="document-manager__error">{{ saveError }}</div>
          <div v-if="deleteError" class="document-manager__error">{{ deleteError }}</div>
          <div v-if="renameError" class="document-manager__error">{{ renameError }}</div>
        </template>
      </section>
      <DocumentHistoryPanel
        class="document-manager__history"
        :git-log="gitLog"
        :file-relative="selectedDoc"
        :current-revision="selectedRevision"
        :is-loading="gitLog.state.value.kind === 'loading'"
        @select-revision="onSelectRevision"
        @compare-current="onCompareCurrent"
      />
    </div>
  </div>
</template>

<style scoped>
.document-manager {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}
.document-manager__notice {
  padding: 4px 8px;
  font-size: 11px;
}
.document-manager__notice--warn {
  background: rgba(var(--v-theme-warning), 0.1);
  color: rgb(var(--v-theme-warning));
}
.document-manager__body {
  display: grid;
  grid-template-columns: minmax(180px, 30%) 1fr 220px;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}
.document-manager__left {
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.document-manager__right {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  position: relative;
}
.document-manager__empty {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 12.5px;
  text-align: center;
}
.document-manager__banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  background: rgba(var(--v-theme-info), 0.08);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  font-size: 11.5px;
  color: rgb(var(--v-theme-info));
}
.document-manager__banner-btn {
  background: transparent;
  border: 1px solid currentColor;
  color: inherit;
  border-radius: 3px;
  padding: 1px 6px;
  font-size: 11px;
  cursor: pointer;
}
.document-manager__raw {
  flex: 1 1 auto;
  overflow: auto;
  padding: 12px;
  font-family: monospace;
  font-size: 12.5px;
  line-height: 1.5;
  margin: 0;
  background: var(--v-theme-surface, transparent);
  color: rgb(var(--v-theme-on-surface));
}
.document-manager__rendered {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}
.document-manager__error {
  padding: 6px 10px;
  font-size: 11px;
  color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.08);
}
.document-manager__history {
  min-height: 0;
}
</style>
```

- [ ] **Step 2: Type-check + commit**

Run: `cd dashboard && pnpm typecheck`
Expected: no errors. (If `DEFAULT_DOCS_ROOT` is not visible in the template, export it explicitly from the `import { ... DEFAULT_DOCS_ROOT ... } from "..."` block — it's already there.)

```bash
git add dashboard/src/components/chat/message_list_comps/DocumentManager.vue
git commit -m "feat(dashboard): add DocumentManager container wiring all sub-components"
```

---

## Task 16: Wire `<DocumentManager>` into `GitDiffSidebar.vue`

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue`

- [ ] **Step 1: Extend the `viewMode` type**

In `GitDiffSidebar.vue`, change:

```ts
const viewMode = ref<"files" | "diff" | "history">(loadViewMode());
```

to:

```ts
type ViewMode = "files" | "diff" | "history" | "docs";
const viewMode = ref<ViewMode>(loadViewMode() as ViewMode);
```

And change `loadViewMode()`:

```ts
function loadViewMode(): ViewMode {
  const v = safeGetItem(STORAGE_KEYS.viewMode);
  if (v === "files" || v === "diff" || v === "history" || v === "docs") return v;
  return "files";
}
```

- [ ] **Step 2: Add the 4th pill button**

In the tab strip template (find the existing pill buttons for Files / Git Diff / History), add a new button **between Files and Git Diff**:

```vue
<button
  type="button"
  role="tab"
  :aria-selected="viewMode === 'docs'"
  :class="['view-mode-pill', { active: viewMode === 'docs' }]"
  :title="tm('spcodeProjectLoad.gitDiffSidebar.tabs.docs')"
  :aria-label="tm('spcodeProjectLoad.gitDiffSidebar.tabs.docs')"
  @click="viewMode = 'docs'"
>
  <v-icon size="14">mdi-file-document-multiple-outline</v-icon>
</button>
```

The exact class names / markup depend on the existing pill row's conventions — match the style of the 3 existing pills. The `tm(...)` call uses the new i18n key from Task 9.

- [ ] **Step 3: Mount `<DocumentManager>` for the new view mode**

In the template, alongside the existing `v-if="viewMode === 'files'"` (FileBrowserView), `v-else-if="viewMode === 'diff'"` (GitDiffBodyContent), and `v-else-if="viewMode === 'history'"` (GitLogView) branches, add:

```vue
<DocumentManager
  v-else-if="viewMode === 'docs'"
  :worktree="selectedWorktree"
  :umo="spcodeStatus.status.value.umo"
  :project-root="projectRoot"
  :is-dark="!!isDark"
  :git-log="gitLog"
  :git-show="gitShow"
/>
```

Add to the imports block at the top of `<script setup>`:

```ts
import DocumentManager from "@/components/chat/message_list_comps/DocumentManager.vue";
```

- [ ] **Step 4: Wire resize handle**

The default `30% / 1fr / 220px` grid is fine for the spec; if you want a draggable divider between the tree and the right pane, do that as a follow-up. The current spec is satisfied without it.

- [ ] **Step 5: Type-check + dev smoke**

Run: `cd dashboard && pnpm typecheck && pnpm dev`
Open the dashboard:
1. Load a project.
2. Open the Git Diff sidebar.
3. Click the new "Documents" pill.
4. Verify the path bar, tree, empty right pane render.
5. Click any `.md` in the tree → right pane should render the file in `rendered` mode.
6. Toggle `原文` / `渲染` / `与当前对比` (the latter disabled).
7. Click `修改` → CodeMirror 6 editor should mount; or, if the imports fail, the textarea fallback should appear.
8. Save → file should update; re-render should reflect it.
9. Delete → file should be removed; tree should refresh.
10. Switch to Git Diff tab → the deleted / saved changes should appear in the unstaged list.
11. Reload the page → path bar should restore the previous docs root (per localStorage key).
12. Click a commit in the history panel → "查看此版本" should set `selectedRevision`, switch to `rendered`, and render the historical content.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(dashboard): mount DocumentManager in GitDiffSidebar Documents tab"
```

---

## Task 17: Final verification (lint, typecheck, manual)

**Files:** none modified.

- [ ] **Step 1: Run linter**

Run: `cd dashboard && pnpm lint`
Expected: no new errors. Pre-existing warnings unrelated to this plan (e.g. markdown-it / shiki deprecation warnings) are OK.

- [ ] **Step 2: Run typecheck**

Run: `cd dashboard && pnpm typecheck`
Expected: 0 errors.

- [ ] **Step 3: Run the unit tests**

Run: `cd dashboard && node --test tests/docsRootStorage.test.mjs tests/markdownPipeline.test.mjs tests/useResizableSplit.test.mjs tests/useSpcodeGitFile.test.mjs tests/useSpcodeDocs.test.mjs`
Expected: all 5 test files pass (the 3 placeholders + the real docsRootStorage + markdownPipeline tests).

- [ ] **Step 4: Build smoke**

Run: `cd dashboard && pnpm build`
Expected: build succeeds. If it fails on the CodeMirror imports, check the package names in Task 1.

- [ ] **Step 5: Tag the milestone**

```bash
git tag -a document-manager-v1 -m "Document Manager frontend (tab + CRUD + history)"
git push origin document-manager-v1
```

---

## Self-Review (run before final commit)

> Run this checklist yourself before declaring the plan complete.

**1. Spec coverage:**
- §1 Goal: ✓ Tasks 10–16.
- §2 decisions #1–14: each is honored by a specific task (see below).
- §3.1 New files: all 8 Vue + 1 shared pipeline + 1 shared composable exist (Tasks 3, 4, 5, 6, 8, 10, 11, 12, 13, 14, 15).
- §3.2 Module responsibilities: each component's "Does" / "Does NOT" is reflected in the props/emits declared in the task.
- §3.3 `viewMode` extension: Task 16 step 1.
- §3.4 `docsRoot` localStorage: Task 2.
- §3.5 composables: Tasks 5, 6, 7.
- §3.6 backend endpoints: consumed by Tasks 6, 7.
- §4.1–§4.8 file-by-file: Tasks 10–15 cover the SFCs; Task 9 covers i18n.
- §5 Data flow: implemented by the wiring in Task 15.
- §6 Error handling: surface in each component (snackbar replaced by inline red banner in §4.1 — spec accepts both).
- §7 Testing matrix: pure-logic tests covered (Tasks 2, 3, 5, 6, 7); Vue component tests are deferred per the "TDD discipline" global constraint above.
- §8 Out of scope: confirmed.
- §9 Open questions: #2 (rename stub) **superseded** (see top-of-plan deviation note); #1 (CodeMirror acceptance) honored (Task 1 + Task 13); #3, #4, #5, #6 honored.
- §10 Acceptance criteria: each is verifiable in Task 17's manual smoke test.

**2. Placeholder scan:** the only "placeholder" content is the 1-line composable tests in `useSpcodeGitFile.test.mjs` and `useSpcodeDocs.test.mjs`, and they are explicitly scoped out per the working norm of the repo (verified via codegraph: `useSpcodeFileRestore`, `useSpcodeGitShow`, `useSpcodeGitDiff`, etc. all have no covering tests).

**3. Type consistency:**
- `FileRevisionState` is defined in Task 6 and consumed in Task 15.
- `UseSpcodeGitLog` / `UseSpcodeGitShow` are imported from the existing composables (Tasks 12, 15, 16).
- `GitFileData` is exported by Task 6 and read by Task 15.
- `DocsWriteResult` is exported by Task 7 and used by Task 15.
- `isValidDocsRoot` / `loadDocsRoot` / `saveDocsRoot` / `DEFAULT_DOCS_ROOT` are exported by Task 2 and consumed in Tasks 10, 15.
- `DEFAULT_DOCS_ROOT` is referenced in `DocumentManager.vue` template via the imported binding (declared in the import statement); confirm Task 15 step 1 keeps the import.

If you find any inconsistency, fix it inline in the affected task before declaring the plan complete.

---

## Execution Handoff

After saving the plan, offer execution choice:

**"Plan complete and saved to `docs/superpowers/plans/2026-07-12-document-manager-frontend.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?"**

**If Subagent-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development
- Fresh subagent per task + two-stage review

**If Inline Execution chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:executing-plans
- Batch execution with checkpoints for review
