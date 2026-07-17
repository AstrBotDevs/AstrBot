# Selection Comment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add text-selection commenting (copy + comment) to file/code previews shared by Workspace and Document Manager; render-state markdown views get copy-only menu; all comments flow into the existing LLM-facing pipeline.

**Architecture:** Extend `FileComment` with optional `endLine`/`selection`; extract pure helpers from `useFileComments` (range-context extraction, LLM formatter, coverage predicate) and TDD them; introduce one shared `SelectionActionMenu.vue`; wire `FileBrowserCodeView` with DOM-selection-to-line mapping; widen the two parents + `FileCommentEditor` + `CommentsPreviewDialog` for range mode.

**Tech Stack:** Vue 3 (Composition API, `<script setup lang="ts">`), Vuetify icons, vitest (.test.mjs), `@/utils/clipboard`, `useFileComments` singleton.

**Spec:** `docs/superpowers/specs/2026-07-17-selection-comment-design.md`

## Global Constraints

- Branch: current (commit only the spec `16b9d834e` already on `all`). If executor uses a worktree, create from `all`.
- Conventional commit messages (English). Re-run `cd dashboard && pnpm typecheck` before each commit that touches TS/Vue.
- Do NOT modify the shared `MarkdownView` (used by chat bubbles). Rendering menu is added at the container level in the two parent components.
- Do NOT change `diffHunk` semantics; range comments are an additive field on `FileComment`.
- No new dependencies.
- Per repo convention (`tests/useSpcodeDocs.test.mjs` comment): composable lifecycle is smoke-tested manually; pure helpers get unit tests.
- All UI text: 3-locale parity (zh-CN, en-US, ru-RU in `dashboard/src/i18n/locales/<locale>/features/chat.json`).
- Comments and console output: English (per project rule).
- Preserve every existing behavior of single-line comments and the `diffHunk` path.

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `dashboard/src/components/chat/message_list_comps/SelectionActionMenu.vue` | Pure-presentational fixed-position menu: copy/comment items, copy feedback, edge clamping. |
| Modify | `dashboard/src/composables/useFileComments.ts` | Add `endLine`/`selection` to `FileComment`; export `commentCoversLine`, `extractRangeLineContext`, `formatCommentForLLM` (pure); add `addSelectionComment` wrapper; extend `formatForLLM` to use the pure formatter. |
| Create test | `dashboard/tests/useFileCommentsRange.test.mjs` | Unit tests for the three pure helpers (single + range paths). |
| Modify | `dashboard/src/components/chat/message_list_comps/FileBrowserCodeView.vue` | New `selectionCommentable` prop + `request-add-range` emit; DOM selection → `.line` index → line numbers; mount `SelectionActionMenu`; gutter coverage uses `commentCoversLine`; close on scroll/outside/collapse/file change. |
| Modify | `dashboard/src/components/chat/message_list_comps/FileCommentEditor.vue` | Accept optional `endLine`/`selectionContent`; render `L{start}-L{end}` header + selection preview in range mode; save payload unchanged. |
| Modify | `dashboard/src/components/chat/CommentsPreviewDialog.vue` | `previewRows` handles range comments (render range rows with `>` on every range line, mirroring `formatCommentForLLM`). |
| Modify | `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue` | `activeEditRange`; `onRequestAddRange`; save dispatch split; `:selection-commentable="false"` on historical `<FileBrowserCodeView>`; rendered-container `mouseup` → copy-only menu. |
| Modify | `dashboard/src/components/chat/message_list_comps/DocumentManager.vue` | Mirror Task 7 wiring for its raw view + `.document-manager__rendered` container. |
| Modify | `dashboard/src/i18n/locales/{zh-CN,en-US,ru-RU}/features/chat.json` | Add `spcodeProjectLoad.fileBrowser.comment.rangeLabel` in each. |

---

## Task 1: Pure helpers — `commentCoversLine`, `extractRangeLineContext`, `formatCommentForLLM` (TDD)

**Files:**
- Create: `dashboard/src/composables/useFileComments.ts` (additive exports; do not change existing API)
- Create: `dashboard/tests/useFileCommentsRange.test.mjs`

**Interfaces produced** (the implementer for later tasks reads these signatures verbatim):
```ts
// Returns true when `line` falls inside the comment's range.
export function commentCoversLine(c: FileComment, line: number): boolean;

// Computes the {lineContent, contextBefore, contextAfter} triple for a
// range comment. Uses the first line of `selection` as `lineContent`,
// `startLine - 1` as contextBefore, `endLine + 1` as contextAfter
// (from `content` when available, else null).
export function extractRangeLineContext(
  content: string,
  startLine: number,
  endLine: number,
  selection: string,
): LineContext;

// Pure renderer. `getFileContent(path)` returns the live file content
// (null if the cache has no entry yet). Output format:
//   {filePath}
//   L{start}             ← single line
//   L{start}-L{end}      ← range
//   window of ±CONTEXT_LINES rows from content (or frozen selection
//   for range rows when content is missing), with `>` on the anchor
//   line(s). Trailing user comment text.
export function formatCommentForLLM(
  c: FileComment,
  getFileContent: (path: string) => string | null,
): string;
```

- [ ] **Step 1: Write the failing test file** at `dashboard/tests/useFileCommentsRange.test.mjs`:

```js
// Author: elecvoid243, 2026-07-17
// Spec: docs/superpowers/specs/2026-07-17-selection-comment-design.md §5-6
//
// Unit tests for the pure helpers extracted from useFileComments.
// We test the helpers directly via dynamic import; the composable
// wiring (addSelectionComment, etc.) is smoke-tested manually per
// repo convention.

import assert from "node:assert/strict";
import test from "node:test";

const mod = await import(
  "../src/composables/useFileComments.ts"
);

test("commentCoversLine: single line covers only that line", () => {
  const c = { line: 5 };
  assert.equal(mod.commentCoversLine(c, 4), false);
  assert.equal(mod.commentCoversLine(c, 5), true);
  assert.equal(mod.commentCoversLine(c, 6), false);
});

test("commentCoversLine: range covers inclusive span", () => {
  const c = { line: 5, endLine: 8 };
  assert.equal(mod.commentCoversLine(c, 4), false);
  assert.equal(mod.commentCoversLine(c, 5), true);
  assert.equal(mod.commentCoversLine(c, 7), true);
  assert.equal(mod.commentCoversLine(c, 8), true);
  assert.equal(mod.commentCoversLine(c, 9), false);
});

test("extractRangeLineContext: uses first line of selection as lineContent", () => {
  const content = "L1\nL2\nL3\nL4\nL5\nL6\n";
  const got = mod.extractRangeLineContext(
    content, /*startLine*/ 3, /*endLine*/ 5,
    /*selection*/ "L3 picked\nL4 picked\nL5 picked",
  );
  assert.equal(got.lineContent, "L3 picked");
  assert.equal(got.contextBefore, "L2");
  assert.equal(got.contextAfter, "L6");
});

test("extractRangeLineContext: null context at file boundaries", () => {
  const got = mod.extractRangeLineContext(
    "L1\nL2\nL3\n", 1, 2, "L1\nL2",
  );
  assert.equal(got.contextBefore, null);
  assert.equal(got.contextAfter, "L3");
});

test("formatCommentForLLM: single line — header + ±3 window", () => {
  const content =
    "L1\nL2\nL3\nL4\nL5\nL6\nL7\nL8\nL9\nL10\nL11\n";
  const c = {
    id: "x", filePath: "/abs/repo/foo.py",
    line: 5, lineContent: "L5", contextBefore: "L4", contextAfter: "L6",
    text: "explain this", createdAt: 0, updatedAt: 0,
  };
  const out = mod.formatCommentForLLM(c, () => content);
  assert.match(out, /foo\.py/);
  assert.match(out, /\bL5\b/);
  assert.match(out, /explain this/);
  // The anchored line must be marked.
  assert.match(out, /^>/m);
});

test("formatCommentForLLM: range — header is Lstart-Lend, every range line marked", () => {
  const content =
    "L1\nL2\nL3\nL4\nL5\nL6\nL7\nL8\nL9\nL10\nL11\nL12\n";
  const c = {
    id: "x", filePath: "/abs/repo/foo.py",
    line: 4, endLine: 6,
    lineContent: "L4 picked", contextBefore: "L3", contextAfter: "L7",
    selection: "L4 picked\nL5 picked\nL6 picked",
    text: "why", createdAt: 0, updatedAt: 0,
  };
  const out = mod.formatCommentForLLM(c, () => content);
  assert.match(out, /foo\.py/);
  assert.match(out, /L4-L6/);
  // Three range lines, each prefixed with `>`.
  const marked = out.split("\n").filter((l) => l.startsWith(">")).length;
  assert.equal(marked, 3);
});

test("formatCommentForLLM: range with missing content — falls back to frozen selection", () => {
  const c = {
    id: "x", filePath: "/abs/repo/foo.py",
    line: 10, endLine: 11,
    lineContent: "X", contextBefore: null, contextAfter: null,
    selection: "A\nB",
    text: "t", createdAt: 0, updatedAt: 0,
  };
  const out = mod.formatCommentForLLM(c, () => null);
  assert.match(out, /A/);
  assert.match(out, /B/);
  assert.match(out, /L10-L11/);
});
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd F:\github\Astrbot\dashboard && pnpm vitest run tests/useFileCommentsRange.test.mjs
```

Expected: FAIL (helpers not exported yet).

- [ ] **Step 3: Extract the pure helpers in `dashboard/src/composables/useFileComments.ts`**

Add these at module top-level (right after `extractLineContext`):

```ts
/** True when `line` falls inside the comment's range. Single-line
 *  comments cover only their `line`; range comments cover
 *  [line, endLine] inclusive. */
export function commentCoversLine(c: FileComment, line: number): boolean {
  const end = c.endLine ?? c.line;
  return c.line <= line && line <= end;
}

/** Line-context for a range comment. Mirrors `extractLineContext`'s
 *  shape so the editor preview stays consistent. `lineContent` is
 *  the first line of the frozen selection (fingerprint); the
 *  surrounding context lines come from the live `content` when
 *  available. */
export function extractRangeLineContext(
  content: string,
  startLine: number,
  endLine: number,
  selection: string,
): LineContext {
  const lines = content.split("\n");
  const firstLineOfSelection = selection.split("\n")[0] ?? "";
  return {
    lineContent: firstLineOfSelection,
    contextBefore: startLine - 2 >= 0 ? lines[startLine - 2] ?? null : null,
    contextAfter:
      endLine < lines.length ? lines[endLine] ?? null : null,
  };
}

/** Pure LLM-facing renderer for a single comment. The composable
 *  wrapper passes the content cache; keeping the formatter pure
 *  makes it unit-testable (no Vue reactivity). Output:
 *    {filePath}
 *    L{line}                (single) | L{start}-L{end} (range)
 *    ±3 window of rows, `>` marks the anchor (range: every range
 *    line). Frozen `selection` is used for range rows when the
 *    live content cache is missing.
 *    {text}                  (the user comment) */
export function formatCommentForLLM(
  c: FileComment,
  getFileContent: (path: string) => string | null,
): string {
  // Diff-hunk comments keep their existing renderer (unchanged).
  if (c.diffHunk) {
    return renderHunkGroup(c); // existing helper, called below unchanged
  }
  return renderWindow(c, getFileContent);
}
```

Now **modify** `renderWindow` to handle range and use the cache-or-frozen-fallback. Find the existing `renderWindow` (around line 406 per the spec context) and replace its body so the per-line content resolution does the following (keep the `>`-marker logic; extend to every range line; when the cache has no entry, fill range rows from `c.selection` split by `\n`):

```ts
function renderWindow(
  c: FileComment,
  getFileContent: (path: string) => string | null,
): string {
  const CONTEXT_LINES = 3;
  const fileContent = getFileContent(c.filePath);
  const fileLines = fileContent?.split("\n") ?? [];
  const totalLines = fileLines.length;
  const end = c.endLine ?? c.line;
  const isRange = c.endLine !== undefined && c.endLine > c.line;
  const selectionLines = c.selection?.split("\n") ?? [];

  const ctxStart = Math.max(1, c.line - CONTEXT_LINES);
  const ctxEnd = totalLines > 0
    ? Math.min(totalLines, end + CONTEXT_LINES)
    : end + CONTEXT_LINES;

  const headerLine = isRange
    ? `${c.filePath} L${c.line}-${c.endLine}`
    : `${c.filePath} L${c.line}`;

  const rows: string[] = [];
  for (let n = ctxStart; n <= ctxEnd; n++) {
    const isAnchor = n >= c.line && n <= end;
    const prefix = isAnchor ? ">" : " ";
    const lineNo = String(n).padStart(4);
    let content: string;
    if (isAnchor && totalLines === 0) {
      // Cache missing + anchor row → frozen selection (range: pick
      // the right selection line by offset; single: line 0).
      content = selectionLines[n - c.line] ?? c.lineContent;
    } else if (n - 1 < fileLines.length) {
      content = fileLines[n - 1];
    } else {
      content = c.contextAfter ?? "";
    }
    rows.push(`${prefix} ${lineNo} | ${content}`);
  }
  return [headerLine, ...rows, c.text].join("\n");
}
```

**Note on diff-hunk path**: `renderHunkGroup` stays as-is. `formatForLLM` (the composable's exported function) now delegates to `formatCommentForLLM`, so refactor it:

```ts
// existing
function formatForLLM(comments: FileComment[]): string {
  ...
  for (const c of comments) {
    parts.push(formatCommentForLLM(c, (p) => getFileContent(p) ?? null));
  }
  return parts.join("\n\n");
}
```

Keep the *outer* `formatForLLM` name (composable's public) — only the inner per-comment logic moves to the pure `formatCommentForLLM` (which can be the same name: declare the pure one first, then the loop calls it; if name collision, rename the pure one to `formatOneCommentForLLM` and update the test imports accordingly — preferred for clarity).

- [ ] **Step 4: Run the test and confirm it passes**

```bash
cd F:\github\Astrbot\dashboard && pnpm vitest run tests/useFileCommentsRange.test.mjs
```

Expected: PASS (all 7 tests).

- [ ] **Step 5: Run typecheck + the full test suite**

```bash
cd F:\github\Astrbot\dashboard && pnpm typecheck && pnpm test
```

Expected: typecheck clean; no other tests regressed.

- [ ] **Step 6: Commit**

```bash
cd F:\github\Astrbot && git add dashboard/src/composables/useFileComments.ts dashboard/tests/useFileCommentsRange.test.mjs
git commit -m "feat(comments): extract range helpers and LLM renderer"
```

---

## Task 2: `addSelectionComment` in the composable

**Files:**
- Modify: `dashboard/src/composables/useFileComments.ts` (add `addSelectionComment` and ensure `FileComment` permits `endLine`/`selection`)

- [ ] **Step 1: Extend `FileComment` with the optional fields**

```ts
export interface FileComment {
  id: string;
  filePath: string;
  line: number;
  lineContent: string;
  contextBefore: string | null;
  contextAfter: string | null;
  text: string;
  createdAt: number;
  updatedAt: number;
  diffHunk?: DiffHunkContext;
  /** 2026-07-17 selection-comment: 1-based end line for range
   *  comments. Undefined (or === line) means single-line. */
  endLine?: number;
  /** 2026-07-17 selection-comment: verbatim selected text at comment
   *  time. Range comments only. */
  selection?: string;
}
```

- [ ] **Step 2: Add `addSelectionComment` to the returned API**

Inside `createFileComments` (right after `addCommentWithContext`), add:

```ts
function addSelectionComment(
  filePath: string,
  startLine: number,
  endLine: number,
  selection: string,
  text: string,
): FileComment {
  const content = getFileContent(filePath) ?? "";
  const ctx = extractRangeLineContext(
    content, startLine, endLine, selection,
  );
  const comment: FileComment = {
    id: newId(),
    filePath,
    line: startLine,
    endLine,
    selection,
    lineContent: ctx.lineContent,
    contextBefore: ctx.contextBefore,
    contextAfter: ctx.contextAfter,
    text,
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
  commentsByFileMap.value = upsertComment(commentsByFileMap.value, comment);
  return comment;
}
```

Add `addSelectionComment` to the return object of `createFileComments`.

- [ ] **Step 3: Typecheck**

```bash
cd F:\github\Astrbot\dashboard && pnpm typecheck
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
cd F:\github\Astrbot && git add dashboard/src/composables/useFileComments.ts
git commit -m "feat(comments): addSelectionComment API + FileComment endLine/selection"
```

---

## Task 3: `SelectionActionMenu.vue` (new component)

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/SelectionActionMenu.vue`

- [ ] **Step 1: Create the component** (verbatim contents of the new file):

```vue
<!-- Author: elecvoid243, 2026-07-17
     Spec: docs/superpowers/specs/2026-07-17-selection-comment-design.md §4.1
     Pure-presentational fixed-position popup. The parent owns the
     selection snapshot and is responsible for writing to the
     clipboard on `copy`; the menu shows an optimistic "copied"
     feedback and auto-closes after 1.5s. -->
<script setup lang="ts">
import { onBeforeUnmount, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  /** Viewport X for the menu's left edge (clamped to viewport). */
  x: number;
  /** Viewport Y for the menu's top edge (clamped to viewport). */
  y: number;
  /** Whether to render the "comment" item. False on rendering views. */
  showComment: boolean;
}>();

const emit = defineEmits<{
  (e: "copy"): void;
  (e: "comment"): void;
  (e: "close"): void;
}>();

const { tm } = useModuleI18n("features/chat");
const copied = ref(false);
let closeTimer: ReturnType<typeof setTimeout> | null = null;

function clampToViewport(x: number, y: number): { left: number; top: number } {
  // Leave a 6px margin so the menu never touches the edge.
  const maxLeft = Math.max(6, window.innerWidth - 140);
  const maxTop = Math.max(6, window.innerHeight - 40);
  return {
    left: Math.min(Math.max(6, x), maxLeft),
    top: Math.min(Math.max(6, y), maxTop),
  };
}

const pos = clampToViewport(props.x, props.y);

function onCopy(): void {
  copied.value = true;
  emit("copy");
  if (closeTimer) clearTimeout(closeTimer);
  closeTimer = setTimeout(() => emit("close"), 1500);
}

function onComment(): void {
  emit("comment");
}

onBeforeUnmount(() => {
  if (closeTimer) clearTimeout(closeTimer);
});
</script>

<template>
  <div
    class="selection-action-menu"
    role="menu"
    :style="{ left: pos.left + 'px', top: pos.top + 'px' }"
    @mousedown.stop
  >
    <button
      type="button"
      class="selection-action-menu__item"
      role="menuitem"
      @click="onCopy"
    >
      <v-icon size="12">mdi-content-copy</v-icon>
      {{
        copied
          ? tm("copy.copied")
          : tm("copy.copy")
      }}
    </button>
    <button
      v-if="showComment"
      type="button"
      class="selection-action-menu__item"
      role="menuitem"
      @click="onComment"
    >
      <v-icon size="12">mdi-comment-text-outline</v-icon>
      {{ tm("spcodeProjectLoad.fileBrowser.comment.add") }}
    </button>
  </div>
</template>

<style scoped>
.selection-action-menu {
  position: fixed;
  z-index: 1100;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  background: var(--v-theme-surface, rgb(255, 255, 255));
  color: rgb(var(--v-theme-on-surface));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.16);
  border-radius: 6px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.14);
  font-size: 11.5px;
  user-select: none;
}
.selection-action-menu__item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  border-radius: 4px;
  padding: 3px 8px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.82);
}
.selection-action-menu__item:hover {
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
}
</style>
```

i18n note: `tm("copy.copy")` and `tm("copy.copied")` already exist (`copy` is a top-level key in `features/chat.json`); `tm("spcodeProjectLoad.fileBrowser.comment.add")` should already exist because the gutter "+" button uses it — if not, fall back to the same `add` key the gutter uses (verify by reading the existing FileBrowserCodeView template). If the gutter uses a different key, mirror it.

- [ ] **Step 2: Typecheck**

```bash
cd F:\github\Astrbot\dashboard && pnpm typecheck
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
cd F:\github\Astrbot && git add dashboard/src/components/chat/message_list_comps/SelectionActionMenu.vue
git commit -m "feat(comments): add SelectionActionMenu component"
```

---

## Task 4: `FileBrowserCodeView` — selection listener, line mapping, range emit, coverage

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/FileBrowserCodeView.vue`

- [ ] **Step 1: Extend props + emit**

```ts
const props = defineProps<{
  highlightedHtml: string;
  filePath: string;
  comments: FileComment[];
  activeEditLine: number | null;
  activeEditCommentId: string | null;
  isDark: boolean;
  scrollToLine?: number | null;
  /** 2026-07-17 selection-comment: when false, the menu shows only
   *  the "copy" item. Defaults to true. */
  selectionCommentable?: boolean;
}>();

const emit = defineEmits<{
  (e: "request-add", line: number): void;
  (e: "request-edit", commentId: string): void;
  (e: "request-add-range", payload: {
    startLine: number;
    endLine: number;
    selection: string;
  }): void;
  (e: "copy-selection", text: string): void;
}>();
```

Default the prop in a destructured `withDefaults`:
```ts
const props = withDefaults(defineProps<{ ... }>(), {
  selectionCommentable: true,
  scrollToLine: null,
});
```

(Combine the new default with any existing `scrollToLine` default if present.)

- [ ] **Step 2: Refactor `hasComment` / `commentIdFor` / `commentText` to use `commentCoversLine`**

Import at the top of `<script setup>`:
```ts
import { commentCoversLine } from "@/composables/useFileComments";
```

Replace the three helpers:
```ts
function hasComment(line: number): boolean {
  return props.comments.some((c) => commentCoversLine(c, line));
}
function commentIdFor(line: number): string | null {
  return props.comments.find((c) => commentCoversLine(c, line))?.id ?? null;
}
function commentText(line: number): string {
  return props.comments.find((c) => commentCoversLine(c, line))?.text ?? "";
}
```

- [ ] **Step 3: Add selection-to-line mapper + menu state**

Add at the bottom of the script:

```ts
import { onBeforeUnmount, ref } from "vue"; // already imported; ensure ref is in scope
import SelectionActionMenu from "./SelectionActionMenu.vue";

type RangeSnapshot = {
  x: number; y: number;
  startLine: number; endLine: number; selection: string;
};
const menuState = ref<RangeSnapshot | null>(null);

function lineElToIndex(node: Node | null): number | null {
  // Walk up to the nearest .line ancestor; if not found, return null.
  let n: Node | null = node;
  while (n && n instanceof HTMLElement && !n.classList.contains("line")) {
    n = n.parentElement;
  }
  if (!(n instanceof HTMLElement)) return null;
  if (!codeContentRef.value) return null;
  const all = codeContentRef.value.querySelectorAll<HTMLElement>(".line");
  return Array.from(all).indexOf(n);
}

function closeMenu(): void {
  menuState.value = null;
}

function onMouseUp(e: MouseEvent): void {
  // Only react to mouseups inside the code content (not the gutter).
  if (!codeContentRef.value) return;
  if (e.target instanceof HTMLElement && e.target.closest(".file-browser-code-view__gutter")) {
    return;
  }
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) {
    closeMenu();
    return;
  }
  if (!sel.anchorNode || !sel.focusNode) return;
  if (!codeContentRef.value.contains(sel.anchorNode)) {
    closeMenu();
    return;
  }
  const aIdx = lineElToIndex(sel.anchorNode);
  const fIdx = lineElToIndex(sel.focusNode);
  if (aIdx === null || fIdx === null) {
    closeMenu();
    return;
  }
  const startLine = Math.min(aIdx, fIdx) + 1;
  const endLine = Math.max(aIdx, fIdx) + 1;
  const text = sel.toString();
  if (!text.trim()) {
    closeMenu();
    return;
  }
  menuState.value = {
    x: e.clientX,
    y: e.clientY,
    startLine,
    endLine,
    selection: text,
  };
}

function onSelectionChange(): void {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) {
    // Collapse → close after a tick so the click that collapsed it
    // can finish propagating without an immediate re-open.
    queueMicrotask(closeMenu);
  }
}

function onMenuCopy(): void {
  if (menuState.value) emit("copy-selection", menuState.value.selection);
}

function onMenuComment(): void {
  if (!menuState.value) return;
  emit("request-add-range", {
    startLine: menuState.value.startLine,
    endLine: menuState.value.endLine,
    selection: menuState.value.selection,
  });
  closeMenu();
}

if (typeof window !== "undefined") {
  document.addEventListener("selectionchange", onSelectionChange);
  document.addEventListener("mousedown", (e) => {
    if (!menuState.value) return;
    const t = e.target;
    if (t instanceof HTMLElement && t.closest(".selection-action-menu")) return;
    closeMenu();
  });
}

onBeforeUnmount(() => {
  if (typeof window !== "undefined") {
    document.removeEventListener("selectionchange", onSelectionChange);
  }
  closeMenu();
});

// Hide the menu on scroll/contents-change: reset the menu when the
// highlightedHtml or filePath changes (the .line indices would be stale).
watch(
  () => [props.highlightedHtml, props.filePath],
  () => closeMenu(),
);
```

Also add a `scroll` listener on the scrollable container (find the existing scroll ref in this component — likely `codeScrollRef` or similar; if not, wrap the code area in `<div ref="codeScrollRef" class="..." @scroll="onScrollMaybeClose">`):

```ts
function onScrollMaybeClose(): void {
  if (menuState.value) closeMenu();
}
```

- [ ] **Step 4: Mount the menu in the template**

At the end of the existing template (after the line-comment editor area), add:

```html
<SelectionActionMenu
  v-if="menuState"
  :x="menuState.x"
  :y="menuState.y"
  :show-comment="props.selectionCommentable"
  @copy="onMenuCopy"
  @comment="onMenuComment"
  @close="closeMenu"
/>
```

- [ ] **Step 5: Wire `mouseup` to the code content element**

On the topmost `<div class="code-content">` (or whatever the existing wrapper is — find the element that has the Shiki `v-html="highlightedHtml"`), add `@mouseup="onMouseUp"`.

- [ ] **Step 6: Typecheck**

```bash
cd F:\github\Astrbot\dashboard && pnpm typecheck
```

Expected: clean.

- [ ] **Step 7: Manual smoke**

Run `pnpm dev`, open a file in the Workspace. Drag-select text in the code view → popup with 复制/评论 → 复制 writes clipboard; 评论 opens editor (which doesn't yet support range — Task 5 will fix; for now it just opens with line=startLine). Confirm no console errors and the popup closes on scroll/outside click.

- [ ] **Step 8: Commit**

```bash
cd F:\github\Astrbot && git add dashboard/src/components/chat/message_list_comps/FileBrowserCodeView.vue
git commit -m "feat(comments): FileBrowserCodeView selection-comment support"
```

---

## Task 5: `FileCommentEditor` — range mode

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/FileCommentEditor.vue`

- [ ] **Step 1: Add the new optional props**

```ts
const props = defineProps<{
  line: number;
  commentId?: string | null;
  initialText: string;
  lineContent: string;
  contextBefore: string | null;
  contextAfter: string | null;
  filePath: string;
  /** 2026-07-17 selection-comment: present and > line for range comments. */
  endLine?: number | null;
  /** 2026-07-17 selection-comment: frozen selected text (range mode). */
  selectionContent?: string | null;
}>();
```

Defaults via `withDefaults` if the rest of the file already uses it; otherwise leave optional and treat as nullable in the template.

- [ ] **Step 2: Compute `isRange` and the header label**

In the script:
```ts
const { tm } = useModuleI18n("features/chat");
const isRange = computed(
  () => (props.endLine ?? 0) > props.line,
);
const rangeLabel = computed(() => {
  if (!isRange.value) return "";
  return tm("spcodeProjectLoad.fileBrowser.comment.rangeLabel", {
    start: props.line,
    end: props.endLine,
  });
});
```

- [ ] **Step 3: Update the header markup**

Find the existing header (currently shows line number, line content, ±1 context). Replace with conditional logic:

```html
<div class="file-comment-editor__header">
  <span class="file-comment-editor__line" v-if="!isRange">
    L{{ line }}
  </span>
  <span class="file-comment-editor__line file-comment-editor__line--range" v-else>
    {{ rangeLabel }}
  </span>
  <span class="file-comment-editor__path" :title="filePath">{{ filePath }}</span>
</div>

<div v-if="isRange" class="file-comment-editor__selection">
  <pre>{{ selectionContent }}</pre>
</div>
<div v-else class="file-comment-editor__context">
  <div v-if="contextBefore" class="file-comment-editor__context-line file-comment-editor__context-line--before">
    <span class="file-comment-editor__context-no">{{ line - 1 }}</span>
    <span class="file-comment-editor__context-text">{{ contextBefore }}</span>
  </div>
  <div class="file-comment-editor__context-line file-comment-editor__context-line--anchor">
    <span class="file-comment-editor__context-no">{{ line }}</span>
    <span class="file-comment-editor__context-text">{{ lineContent }}</span>
  </div>
  <div v-if="contextAfter" class="file-comment-editor__context-line file-comment-editor__context-line--after">
    <span class="file-comment-editor__context-no">{{ line + 1 }}</span>
    <span class="file-comment-editor__context-text">{{ contextAfter }}</span>
  </div>
</div>
```

Keep the rest of the editor (textarea, save/cancel/delete buttons) unchanged. `save` payload stays the same (the `text`).

- [ ] **Step 4: Add CSS** (append to `<style scoped>`)

```css
.file-comment-editor__line--range {
  color: rgb(var(--v-theme-primary));
  font-weight: 500;
}
.file-comment-editor__selection {
  max-height: 140px;
  overflow: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 4px;
  padding: 6px 8px;
  background: rgba(var(--v-theme-primary), 0.04);
}
.file-comment-editor__selection pre {
  margin: 0;
  font-family: monospace;
  font-size: 11.5px;
  white-space: pre;
  color: rgba(var(--v-theme-on-surface), 0.85);
}
```

- [ ] **Step 5: Typecheck + commit**

```bash
cd F:\github\Astrbot\dashboard && pnpm typecheck
cd F:\github\Astrbot && git add dashboard/src/components/chat/message_list_comps/FileCommentEditor.vue
git commit -m "feat(comments): FileCommentEditor range mode"
```

---

## Task 6: `CommentsPreviewDialog` — `previewRows` range branch

**Files:**
- Modify: `dashboard/src/components/chat/CommentsPreviewDialog.vue`

- [ ] **Step 1: Add range handling in `previewRows`**

Current body handles `c.diffHunk` and a single-line window. Extend to detect range:

```ts
function previewRows(c: FileComment): PreviewRow[] {
  if (c.diffHunk) {
    return c.diffHunk.lines.map((line) => {
      const isMarked = line.newNo === c.diffHunk!.newLine;
      const prefix = isMarked
        ? ">"
        : line.type === "add"
        ? "+"
        : line.type === "del"
        ? "-"
        : " ";
      const lineNo =
        line.newNo !== null
          ? String(line.newNo)
          : line.oldNo !== null
          ? String(line.oldNo)
          : "    ";
      return { lineNo: lineNo.padStart(4), prefix, content: line.content };
    });
  }
  // Range comments: identical window logic to formatCommentForLLM.
  const fileContent = fileComments.getFileContent(c.filePath);
  const fileLines = fileContent?.split("\n") ?? [];
  const totalLines = fileLines.length;
  const end = c.endLine ?? c.line;
  const isRange = c.endLine !== undefined && c.endLine > c.line;
  const selLines = c.selection?.split("\n") ?? [];
  const ctxStart = Math.max(1, c.line - CONTEXT_LINES);
  const ctxEnd = totalLines > 0
    ? Math.min(totalLines, end + CONTEXT_LINES)
    : end + CONTEXT_LINES;
  const rows: PreviewRow[] = [];
  for (let n = ctxStart; n <= ctxEnd; n++) {
    const isAnchor = n >= c.line && n <= end;
    const prefix = isAnchor ? ">" : " ";
    let content: string;
    if (isAnchor && totalLines === 0) {
      content = selLines[n - c.line] ?? c.lineContent;
    } else if (n - 1 < fileLines.length) {
      content = fileLines[n - 1];
    } else {
      content = "";
    }
    rows.push({
      lineNo: String(n).padStart(4),
      prefix,
      content,
    });
  }
  return rows;
}
```

- [ ] **Step 2: Add a range header line at the top of the dialog's per-comment block** (search for the `v-for` over `group.comments` in the template; add above the existing line-number header):

```html
<div v-if="c.endLine && c.endLine > c.line" class="comments-preview-dialog__range-header">
  L{{ c.line }}-{{ c.endLine }}
</div>
```

Tiny CSS:
```css
.comments-preview-dialog__range-header {
  font-size: 10.5px;
  color: rgb(var(--v-theme-primary));
  font-weight: 500;
  margin-bottom: 2px;
}
```

- [ ] **Step 3: Typecheck + commit**

```bash
cd F:\github\Astrbot\dashboard && pnpm typecheck
cd F:\github\Astrbot && git add dashboard/src/components/chat/CommentsPreviewDialog.vue
git commit -m "feat(comments): preview dialog renders range comments"
```

---

## Task 7: `FileBrowserFilePreview` wiring (workspace page)

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`

- [ ] **Step 1: Add `activeEditRange` state + handler**

In the script (near `activeEditLine`):

```ts
const activeEditRange = ref<{
  startLine: number; endLine: number; selection: string;
} | null>(null);

function onRequestAddRange(payload: {
  startLine: number; endLine: number; selection: string;
}): void {
  if (editMode.value) return; // editor owns the body
  activeEditRange.value = payload;
  activeEditLine.value = null;
  activeEditCommentId.value = null;
  editorInitialText.value = "";
}

function onRequestCopySelection(text: string): void {
  void copyToClipboard(text);
}
```

(Ensure `copyToClipboard` is imported — if not, add `import { copyToClipboard } from "@/utils/clipboard";`.)

- [ ] **Step 2: Update `onSaveComment` split**

Find the current `onSaveComment`. It calls `fileComments.addComment(...)`. Wrap with a range check:

```ts
async function onSaveComment(text: string): Promise<void> {
  const path = activeEditFilePath.value ?? filePathForComment();
  if (!path) return;
  if (activeEditRange.value) {
    const { startLine, endLine, selection } = activeEditRange.value;
    fileComments.addSelectionComment(path, startLine, endLine, selection, text);
  } else if (activeEditLine.value !== null) {
    // existing single-line path
    const file = fileContent.value ?? rawContent.value;
    fileComments.addComment(path, activeEditLine.value, text, file);
  }
  closeCommentEditor();
}

function closeCommentEditor(): void {
  activeEditLine.value = null;
  activeEditCommentId.value = null;
  activeEditRange.value = null;
  editorInitialText.value = "";
}
```

(Adjust to the existing local names — `fileContent` / `rawContent` / `path` — by reading the file's current implementation and reusing the same resolution logic.)

- [ ] **Step 3: Update `<FileCommentEditor>` usage**

The single existing call passes `:line="activeEditLine"`. Add:

```html
<FileCommentEditor
  v-if="activeEditLine !== null || activeEditRange !== null"
  :line="activeEditRange?.startLine ?? activeEditLine ?? 1"
  :end-line="activeEditRange?.endLine ?? null"
  :selection-content="activeEditRange?.selection ?? null"
  :initial-text="editorInitialText"
  :line-content="..."
  :context-before="..."
  :context-after="..."
  :file-path="..."
  @save="onSaveComment"
  @cancel="closeCommentEditor"
  @delete="onDeleteComment"
/>
```

(Resolve the `lineContent`/`contextBefore`/`contextAfter` props the same way the file already does — the range path uses the selection's first line as `lineContent` and the live file lines as context, computed in `onRequestAddRange` and stored on a sibling ref. Keep the existing single-line branch intact for non-range calls.)

- [ ] **Step 4: Disable selection on historical-raw code view**

Find the existing `<FileBrowserCodeView v-else-if="isHistoricalRaw && highlightedHistoricalHtml" .../>` and add `:selection-commentable="false"`.

- [ ] **Step 5: Wire emits on every `<FileBrowserCodeView>`**

Each instance (historical-raw, current) needs:

```html
@request-add="onRequestAdd"
@request-add-range="onRequestAddRange"
@copy-selection="onRequestCopySelection"
```

(Keep existing `@request-add` and `@request-edit`.)

- [ ] **Step 6: Rendered-container copy-only menu (`.preview-markdown`)**

On the existing `<div ... class="preview-markdown">` (the rendered-markdown body), add `@mouseup="onRenderedMouseUp"`:

```ts
const renderedMenu = ref<{ x: number; y: number; text: string } | null>(null);
function onRenderedMouseUp(e: MouseEvent): void {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) {
    renderedMenu.value = null;
    return;
  }
  const root = e.currentTarget as HTMLElement | null;
  if (!root || !root.contains(sel.anchorNode)) {
    renderedMenu.value = null;
    return;
  }
  const text = sel.toString();
  if (!text.trim()) {
    renderedMenu.value = null;
    return;
  }
  renderedMenu.value = { x: e.clientX, y: e.clientY, text };
}
function onRenderedCopy(): void {
  if (renderedMenu.value) void copyToClipboard(renderedMenu.value.text);
  renderedMenu.value = null;
}
```

Render the menu at the end of the template:

```html
<SelectionActionMenu
  v-if="renderedMenu"
  :x="renderedMenu.x"
  :y="renderedMenu.y"
  :show-comment="false"
  @copy="onRenderedCopy"
  @close="renderedMenu = null"
/>
```

- [ ] **Step 7: Typecheck + commit**

```bash
cd F:\github\Astrbot\dashboard && pnpm typecheck
cd F:\github\Astrbot && git add dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue
git commit -m "feat(comments): workspace selection-comment wiring"
```

---

## Task 8: `DocumentManager` wiring (docs page)

> **Read Task 7 first** for the rendered-menu implementation
> (`onRenderedMouseUp` / `renderedMenu` / `onRenderedCopy` / menu
> template); Task 8 is the docs-page mirror with the same shape
> but using `selectedDoc` / `fileContent` / `editMode` instead of
> the workspace's own local names.

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/DocumentManager.vue`

- [ ] **Step 1: Add `activeEditRange` state + handlers**

Mirror Task 7's additions, using the existing local names in DocumentManager (its single-line handler is `onSaveComment`; its `onRequestAdd` already routes to `onRequestAddComment`; mirror that):

```ts
const activeEditRange = ref<{
  startLine: number; endLine: number; selection: string;
} | null>(null);

function onRequestAddRange(payload: {
  startLine: number; endLine: number; selection: string;
}): void {
  if (editMode.value) return;
  activeEditRange.value = payload;
  selectedRevision.value = null;
  activeEditLine.value = null;
  activeEditCommentId.value = null;
}

function onRequestCopySelection(text: string): void {
  void copyToClipboard(text);
}
```

- [ ] **Step 2: Range branch in save dispatch**

Find the existing `onSaveComment` (or the equivalent that calls `addComment`). Split:

```ts
if (activeEditRange.value) {
  const { startLine, endLine, selection } = activeEditRange.value;
  fileComments.addSelectionComment(
    selectedDoc.value ?? props.worktree ?? "",
    startLine, endLine, selection, text,
  );
} else {
  // existing single-line path
  fileComments.addComment(...);
}
activeEditRange.value = null;
```

(Use the file's existing path-resolution — `selectedDoc` is docs-root-relative; for the LLM the comment stores the absolute path, so derive it the same way the existing call does.)

- [ ] **Step 3: Pass new props to `<FileCommentEditor>`**

On the existing `<FileCommentEditor ...>` instance, add:

```html
:line="activeEditRange?.startLine ?? activeEditLine ?? 1"
:end-line="activeEditRange?.endLine ?? null"
:selection-content="activeEditRange?.selection ?? null"
```

- [ ] **Step 4: Wire `<FileBrowserCodeView>` events**

The component's only `<FileBrowserCodeView>` (the raw view branch). Add:

```html
@request-add="onRequestAddComment"
@request-add-range="onRequestAddRange"
@copy-selection="onRequestCopySelection"
```

- [ ] **Step 5: Rendered-container copy-only menu (`.document-manager__rendered`)**

On the existing `<div v-if="viewMode === 'rendered'" class="document-manager__rendered">`, add `@mouseup="onRenderedMouseUp"` and a `<SelectionActionMenu>` child (same shape as Task 7 Step 6, with copy-only). Use the file's existing `renderedMenu` ref style or add a new one.

- [ ] **Step 6: Typecheck + commit**

```bash
cd F:\github\Astrbot\dashboard && pnpm typecheck
cd F:\github\Astrbot && git add dashboard/src/components/chat/message_list_comps/DocumentManager.vue
git commit -m "feat(comments): document manager selection-comment wiring"
```

---

## Task 9: i18n — `rangeLabel` in three locales

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

- [ ] **Step 1: Add the key to each `comment` block**

Find the `"comment": { ... }` block in each locale (it contains `confirmClear` etc., matching the key prefix used by `FileCommentEditor`). Add:

`zh-CN/features/chat.json`:
```json
"rangeLabel": "第 {start}–{end} 行",
```

`en-US/features/chat.json`:
```json
"rangeLabel": "Lines {start}–{end}",
```

`ru-RU/features/chat.json`:
```json
"rangeLabel": "Строки {start}–{end}",
```

- [ ] **Step 2: Validate JSON + commit**

```bash
cd F:\github\Astrbot\dashboard && node -e "for (const l of ['zh-CN','en-US','ru-RU']) JSON.parse(require('fs').readFileSync('src/i18n/locales/'+l+'/features/chat.json','utf8')).spcodeProjectLoad.fileBrowser.comment.rangeLabel && console.log(l,'ok')"
cd F:\github\Astrbot && git add dashboard/src/i18n/locales
git commit -m "feat(comments): i18n rangeLabel key for three locales"
```

Expected: prints `zh-CN ok` / `en-US ok` / `ru-RU ok`.

---

## Task 10: Final verification walkthrough

- [ ] **Step 1: Full typecheck + tests**

```bash
cd F:\github\Astrbot\dashboard && pnpm typecheck && pnpm test
```

Expected: clean; 7 new tests pass; no other tests regressed.

- [ ] **Step 2: Manual walkthrough (dev server)**

`cd dashboard && pnpm dev`. Verify, for **both Workspace and Document Manager**:

1. Code view: single-line drag → menu `[复制] [评论]`; copy writes clipboard; comment opens editor with `L<n>` and saves; chip count +1.
2. Code view: cross-line drag (forward) → menu; comment saves; chip shown on every covered line in the gutter.
3. Code view: cross-line drag (reverse) → same; start/end take min/max.
4. Code view: selection spans only the gutter → no menu.
5. **Rendered markdown view** (open an `.md` file): drag → menu `[复制]` only (no comment item); copy works.
6. **Historical-raw** (in workspace, pick a revision + view raw): no selection menu appears (prop `selection-commentable=false`).
7. **Diff view**: no selection menu.
8. **Edit mode** (workspace editor / document editor): no selection menu.
9. **Preview dialog** (open the comment chip): range comment expands to a window where every range line is `>`-marked; the dialog header shows `L{start}-L{end}`.
10. **End-to-end LLM payload**: open the preview dialog for a range comment — what you see matches what `formatCommentForLLM` emits. Sanity check: `file path` line + `L{start}-L{end}` line + window of rows with `>` markers on the range lines + the comment text.
11. Edge: drag in the code view, then click outside → menu closes; scroll while menu is open → menu closes; switch files → menu closes.

- [ ] **Step 3: Final commit (if any walkthrough fixes were needed)**

```bash
cd F:\github\Astrbot && git add -A && git commit -m "fix(comments): walkthrough adjustments" || true
```

(Skip if nothing changed.)

- [ ] **Step 4: Open PR (if workflow uses PRs)**

Branch is `all`; if the repo flow expects a PR from a feature branch, branch off `all` per the repo's Git workflow before opening one. Title: `feat(comments): add text-selection commenting`.

---

## Spec Coverage Map

| Spec section | Implemented in |
|---|---|
| §3 interaction matrix | Tasks 3, 4, 7, 8 |
| §4.1 `SelectionActionMenu` | Task 3 |
| §4.2 `FileBrowserCodeView` integration | Task 4 |
| §4.3 `FileCommentEditor` range mode | Task 5 |
| §4.4 parent wiring (both) | Tasks 7, 8 |
| §5 `FileComment` extension + `addSelectionComment` | Tasks 1, 2 |
| §6 LLM output format | Task 1 (range renderer) + Task 6 (preview mirror) |
| §7 edge cases | Tasks 4 (scroll/outside), 7/8 (mode gates), 5 (range mode header) |
| §8 i18n | Task 9 |
| §9 verification | Task 10 |
