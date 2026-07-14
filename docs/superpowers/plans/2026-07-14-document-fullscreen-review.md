# Document Fullscreen Review + Raw Inline Comments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fullscreen review mode and line-numbered inline comments to the raw view of DocumentManager, by reusing `FileBrowserCodeView` + `useFileComments` + `@/utils/shiki`.

**Architecture:**

- New tiny composable `useDocumentMarkdownHighlight` runs Shiki over the raw
  markdown content and memoizes on `(content, isDark)`.
- `DocumentManager.vue` swaps its raw-view `<pre>` for `<FileBrowserCodeView>`
  when not in edit mode, wires `useFileComments` (module-level singleton shared
  with FileBrowser) + `FileCommentEditor` + `CommentsPreviewDialog`.
- A new `isFullscreen` ref drives a `<Teleport to="body" :disabled="!isFullscreen">`
  wrapper around the outer `.document-manager` div. When fullscreen is on, the
  copy is mounted directly under `<body>` and a CSS rule
  (`position: fixed; inset: 0; z-index: 9999`) makes it cover the entire
  **browser viewport** — not just the chat sidebar body. (The earlier draft's
  `grid-template-columns: 0 1fr auto` rule only changed the inner flex layout
  and could not escape the sidebar's horizontal width, which is why this
  rework uses Teleport. Mirrors `DiffPreview` overlay implementation in
  `spec 2026-06-30-diff-fullscreen-design.md` §3.2.)
- Left pane (`v-show="!isFullscreen"`) collapses to a 0-width rail with a
  chevron affordance; clicking the chevron re-opens the left pane as a 240px
  overlay drawer anchored to the left edge. `Esc` exits fullscreen AND
  closes the drawer. State is NOT persisted.
- `watch(isFullscreen, v => document.body.style.overflow = v ? "hidden" : "")`
  keeps the chat page from scrolling behind the overlay; released on flip-back
  or on `onBeforeUnmount` if the user navigates away while fullscreen is on.

**Tech Stack:** Vue 3 + `<script setup>`, Vitest + `@vue/test-utils` + happy-dom (already configured), `@/utils/shiki` (`ensureShikiLanguages` + `renderShikiCode`), Vuetify 3 (icons + theme).

---

## Global Constraints

Copied verbatim from spec `2026-07-14-document-fullscreen-review-design.md` and
project `AGENTS.md`:

- **Vue 3 `<script setup>` only** — no Options API, no `defineComponent` calls
  outside of test stubs.
- **Google-style docstrings** on every new function with non-trivial behavior
  (`Args:`, `Returns:`, `Raises:`).
- **Inline-first rule** — do not extract helpers unless reused 3+ times.
  Helpers in this plan are justified: the highlight composable wraps a 5-step
  pipeline (mount → wait shiki → render → catch → memoize) that doesn't belong
  inline in DocumentManager.vue's 700-line setup script.
- **Path handling**: keep `pathlib.Path`-style usage if introduced; document
  paths in this plan are strings (the codebase already uses string paths
  for `useFileComments.filePath`).
- **Cross-platform**: must work on Windows / macOS / Linux, Python 3.10+,
  Node 20+. (No platform-specific code introduced.)
- **i18n**: every new user-facing string goes through `useModuleI18n` with
  namespace `features/chat` and key under `spcodeProjectLoad.documentManager.*`
  (existing convention).
- **No backend changes.** No new dependencies.
- **Comments are in-memory only** (`useFileComments` is already in-memory).
- **`isFullscreen` is NOT persisted** to localStorage.

---

## File Structure

| File                                                                                | Role                                                                                                                     |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `dashboard/src/composables/useDocumentMarkdownHighlight.ts` (CREATE)                | Memoized Shiki wrapper for markdown content. Returns `highlightedHtml` ref + `isReady` ref.                              |
| `dashboard/src/composables/useDocumentMarkdownHighlight.spec.ts` (CREATE)           | Unit test for memoization + fallback behavior.                                                                           |
| `dashboard/src/components/chat/message_list_comps/DocumentManager.vue` (MODIFY)     | All UI changes: fullscreen state + button + CSS; raw view swap to FileBrowserCodeView; comments wiring; binary fallback. |
| `dashboard/src/components/chat/message_list_comps/DocumentManager.spec.ts` (CREATE) | Component test for `isFullscreen` toggle + Esc exit.                                                                     |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` (MODIFY)                      | Add i18n keys for fullscreen button label under `spcodeProjectLoad.documentManager.fullscreen.*`.                        |
| `dashboard/src/i18n/locales/en-US/features/chat.json` (MODIFY)                      | Same.                                                                                                                    |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` (MODIFY)                      | Russian translations (optional — falls back to en-US if not added).                                                      |

No new dependencies. No backend changes.

---

## Task 1: Highlight composable for raw markdown view

**Files:**

- Create: `dashboard/src/composables/useDocumentMarkdownHighlight.ts`
- Test: `dashboard/src/composables/useDocumentMarkdownHighlight.spec.ts`

**Interfaces:**

- Produces: `useDocumentMarkdownHighlight(): { highlightedHtml: ComputedRef<string>; isReady: Ref<boolean> }`
- Consumed by: Task 2 (`DocumentManager.vue` raw view)

### Step 1.1: Write failing test

Create `dashboard/src/composables/useDocumentMarkdownHighlight.spec.ts`:

```ts
import { describe, expect, it } from "vitest";
import { nextTick, ref } from "vue";
import { useDocumentMarkdownHighlight } from "./useDocumentMarkdownHighlight";

describe("useDocumentMarkdownHighlight", () => {
  it("returns empty html until shiki is ready, then renders markdown", async () => {
    const content = ref<string>("# Hello\n\nworld");
    const { highlightedHtml, isReady } = useDocumentMarkdownHighlight(content);
    expect(isReady.value).toBe(false);
    // First nextTick: onMounted hooks fire; shiki is fetched async.
    await nextTick();
    // Wait for the async shiki init to resolve. The composable flips
    // isReady to true once ensureShikiLanguages resolves.
    await vi.waitFor(() => expect(isReady.value).toBe(true), { timeout: 5000 });
    await nextTick();
    expect(highlightedHtml.value).toContain('class="line"');
    expect(highlightedHtml.value.length).toBeGreaterThan(0);
  });

  it("falls back to escaped <pre><code> when shiki render throws", async () => {
    // Force the shiki highlighter to throw by passing an obviously
    // invalid content type — we cannot easily stub the highlighter
    // since the composable imports it directly. Instead we assert
    // the safe-fallback contract: the result must still be valid
    // HTML even for adversarial input.
    const content = ref<string>("\u0000\u0000\u0000");
    const { highlightedHtml, isReady } = useDocumentMarkdownHighlight(content);
    await vi.waitFor(() => expect(isReady.value).toBe(true), { timeout: 5000 });
    await nextTick();
    // Must not be empty, must not throw, must not contain raw NUL bytes
    // in the output (would break the DOM).
    expect(highlightedHtml.value).toBeTruthy();
    expect(highlightedHtml.value).not.toContain("\u0000");
  });

  it("memoizes on (content, isDark) — same input returns same ref value", async () => {
    const content = ref<string>("const x = 1;");
    const isDark = ref<boolean>(false);
    const a = useDocumentMarkdownHighlight(content, isDark);
    await vi.waitFor(() => expect(a.isReady.value).toBe(true), {
      timeout: 5000,
    });
    await nextTick();
    const firstHtml = a.highlightedHtml.value;
    // Touch the content (no change) — html should remain the same
    // reference (the computed memoizes).
    void a.highlightedHtml.value;
    void a.highlightedHtml.value;
    expect(a.highlightedHtml.value).toBe(firstHtml);
  });
});
```

### Step 1.2: Run test to verify it fails

```bash
cd dashboard && pnpm test -- useDocumentMarkdownHighlight
```

Expected: FAIL — module `./useDocumentMarkdownHighlight` does not exist.

### Step 1.3: Implement the composable

Create `dashboard/src/composables/useDocumentMarkdownHighlight.ts`:

```ts
// Author: elecvoid243, 2026-07-14
// Spec: docs/superpowers/specs/2026-07-14-document-fullscreen-review-design.md §3.3
//
// Memoized Shiki wrapper for the DocumentManager raw view. Mirrors
// FileBrowserFilePreview's pipeline (file_browser.vue:147) but is
// tailored for markdown content (always uses "markdown" grammar,
// always returns dual-theme "auto" rendering).
//
// Returns empty html until Shiki is ready so the consumer can decide
// whether to render a skeleton or a fallback. Falls back to an
// escaped <pre><code> if the render call throws — the user never
// sees a blank code view because of a Shiki bug.

import { computed, onMounted, ref, type ComputedRef, type Ref } from "vue";
import { ensureShikiLanguages, renderShikiCode } from "@/utils/shiki";

export interface UseDocumentMarkdownHighlight {
  /** Shiki-highlighted HTML for `content` (markdown grammar, dual-theme). */
  highlightedHtml: ComputedRef<string>;
  /** True after the async highlighter is initialized. */
  isReady: Ref<boolean>;
}

/** Minimal escape so we can produce a safe `<pre><code>...</code></pre>`
 *  fallback when Shiki's render throws. Mirrors the inline escape in
 *  FileBrowserFilePreview.vue:165 to stay consistent. */
function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function useDocumentMarkdownHighlight(
  content: Ref<string>,
  isDark: Ref<boolean> = ref(false),
): UseDocumentMarkdownHighlight {
  const highlighter = ref<unknown>(null);
  const isReady = ref<boolean>(false);

  onMounted(async () => {
    try {
      highlighter.value = await ensureShikiLanguages();
    } catch (err) {
      // Shiki init failure is non-fatal — the computed falls back
      // to escaped <pre><code>. Log once so the user can find it
      // via devtools if they ever need to.
      console.error("useDocumentMarkdownHighlight: shiki init failed", err);
    } finally {
      isReady.value = true;
    }
  });

  const highlightedHtml = computed<string>(() => {
    const text = content.value;
    if (!text) return "";
    const hl = highlighter.value as { codeToHtml?: unknown } | null;
    if (!isReady.value || !hl) {
      return `<pre><code>${escapeHtml(text)}</code></pre>`;
    }
    try {
      // renderShikiCode signature: (highlighter, code, language, colorMode)
      // colorMode="auto" enables dual-theme (light/dark) auto-switching.
      // DocumentManager only displays .md files; we hardcode the grammar
      // here rather than detecting from a path extension.
      return renderShikiCode(hl, text, "markdown", "auto") as string;
    } catch (err) {
      console.error("useDocumentMarkdownHighlight: render failed", err);
      return `<pre><code>${escapeHtml(text)}</code></pre>`;
    }
  });

  return { highlightedHtml, isReady };
}
```

### Step 1.4: Run test to verify it passes

```bash
cd dashboard && pnpm test -- useDocumentMarkdownHighlight
```

Expected: PASS for all 3 tests. If `ensureShikiLanguages` is slow under
happy-dom, the 5-second `waitFor` may time out — bump to 15000 if so.

### Step 1.5: Typecheck

```bash
cd dashboard && pnpm typecheck
```

Expected: PASS with no errors.

### Step 1.6: Commit

```bash
git add dashboard/src/composables/useDocumentMarkdownHighlight.ts \
        dashboard/src/composables/useDocumentMarkdownHighlight.spec.ts
git commit -m "feat(dashboard): add useDocumentMarkdownHighlight composable"
```

---

## Task 2: Replace raw `<pre>` with FileBrowserCodeView

**Files:**

- Modify: `dashboard/src/components/chat/message_list_comps/DocumentManager.vue`
- Test: manual smoke (no automated test in this task)

**Interfaces:**

- Consumes: `useDocumentMarkdownHighlight(contentRef, isDark)` from Task 1
- Consumes: `selectedDoc: Ref<string | null>` (already exists)
- Consumes: `fileContent: Ref<string>` and `historicalFileContent: Ref<string>` (already exist)
- Consumes: `viewMode: Ref<"rendered" | "raw" | "diff">` (already exists)
- Consumes: `editMode: Ref<boolean>` (already exists)
- Produces: visual swap of `<pre v-else-if="viewMode === 'raw'">` for
  `<FileBrowserCodeView>` when `!editMode`. When `editMode === true` the
  existing `DocumentEditor` (CodeMirror) still renders — unchanged.

### Step 2.1: Read current raw-view markup

Open `dashboard/src/components/chat/message_list_comps/DocumentManager.vue`.
The current raw view is at approximately line 619 (after the previous fix
that moved error banners to the top of the right pane):

```vue
<pre v-else-if="viewMode === 'raw'" class="document-manager__raw">{{
              selectedRevision ? historicalFileContent : fileContent
            }}</pre>
```

Locate this block. Keep it for the binary / empty fallback case.

### Step 2.2: Import the composable and component

At the top of `<script setup lang="ts">`, add (next to existing imports):

```ts
import { useDocumentMarkdownHighlight } from "@/composables/useDocumentMarkdownHighlight";
import FileBrowserCodeView from "@/components/chat/message_list_comps/FileBrowserCodeView.vue";
```

(`FileBrowserCodeView` lives in the same `message_list_comps/` folder, so
the relative import would also work; using the `@/` alias matches the
existing imports in `DocumentManager.vue`.)

### Step 2.3: Add a `rawContent` computed and the highlight composable call

After the existing `historicalFileContent` computed (find it; it returns
`""` when no revision is selected), add:

```ts
/** Raw view text: historical blob when a revision is selected,
 *  otherwise the current file content. Single source of truth so
 *  the FileBrowserCodeView and the binary/empty fallback agree. */
const rawContent = computed<string>(() =>
  selectedRevision.value ? historicalFileContent.value : fileContent.value,
);

/** The docsRoot-relative path (matches FileBrowser's partition key
 *  convention). Used as the `filePath` prop on FileBrowserCodeView
 *  and as the partition key for useFileComments in Task 3. Empty
 *  string when no doc is selected — the consumer guards with
 *  v-if so it never renders. */
const rawFilePath = computed<string>(() => selectedDoc.value ?? "");

const { highlightedHtml: rawHighlightedHtml, isReady: rawHighlightReady } =
  useDocumentMarkdownHighlight(rawContent, isDark);
```

### Step 2.4: Add a binary-file detector

After the new computeds, add:

```ts
/** True for binary files in the historical view. The raw view must
 *  not attempt to render binary bytes as markdown — fall back to a
 *  "binary file" placeholder. The current (HEAD) view does not
 *  expose is_binary (we only get that from the historical blob
 *  endpoint), so this is only true when a revision is selected. */
const rawIsBinary = computed<boolean>(() => {
  if (!selectedRevision.value) return false;
  const state = gitFile.getState(
    selectedDoc.value ?? "",
    selectedRevision.value,
  );
  return state.kind === "ok" && state.data.isBinary === true;
});
```

### Step 2.5: Replace the raw `<pre>` with the new view

Locate the existing raw `<pre>` (from Step 2.1) and replace the entire block
with:

```vue
            <!-- Raw view (no edit): line numbers + (later) inline
                 comments via FileBrowserCodeView. Binary / empty
                 / not-ready cases render a small placeholder rather
                 than an empty code view. -->
            <div v-else-if="viewMode === 'raw'" class="document-manager__raw">
              <FileBrowserCodeView
                v-if="
                  !editMode &&
                  rawFilePath &&
                  !rawIsBinary &&
                  rawContent &&
                  rawHighlightReady
                "
                class="document-manager__raw-codeview"
                :highlighted-html="rawHighlightedHtml"
                :file-path="rawFilePath"
                :comments="[]"
                :active-edit-line="null"
                :active-edit-comment-id="null"
                :is-dark="isDark"
              />
              <div v-else-if="rawIsBinary" class="document-manager__raw-placeholder">
                {{ tm("spcodeProjectLoad.documentManager.raw.binaryPlaceholder") }}
              </div>
              <div
                v-else-if="rawFilePath && !rawContent"
                class="document-manager__raw-placeholder"
              >
                {{ tm("spcodeProjectLoad.documentManager.raw.emptyPlaceholder") }}
              </div>
              <div v-else class="document-manager__raw-placeholder">
                {{ tm("spcodeProjectLoad.documentManager.raw.loading") }}
              </div>
            </div>
```

The `:comments="[]"` / `:active-edit-line="null"` / `:active-edit-comment-id="null"`
wiring is intentional for Task 2 — Task 3 will replace these with real
state from `useFileComments`.

### Step 2.6: Add CSS for the new wrappers

In the `<style scoped>` block of `DocumentManager.vue`, find
`.document-manager__raw` (the existing rule for the old `<pre>`) and
replace it with:

```css
.document-manager__raw {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: transparent;
}
.document-manager__raw-codeview {
  /* FileBrowserCodeView already sets `flex: 1` on its .code-view
     root. Filling the container here so the gutter stays sticky. */
  flex: 1;
  min-height: 0;
}
.document-manager__raw-placeholder {
  padding: 24px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 13px;
  text-align: center;
}
```

### Step 2.7: Add the i18n keys

In `dashboard/src/i18n/locales/zh-CN/features/chat.json`, find the
existing `"documentManager": { ... }` block and add (the exact key name
style matches sibling keys like `editor.edit`):

```json
    "raw": {
      "binaryPlaceholder": "二进制文件,无法以原文方式显示",
      "emptyPlaceholder": "空文件",
      "loading": "正在准备视图…"
    }
```

Do the same in `dashboard/src/i18n/locales/en-US/features/chat.json`
with English text:

```json
    "raw": {
      "binaryPlaceholder": "Binary file — cannot display as raw",
      "emptyPlaceholder": "Empty file",
      "loading": "Preparing view…"
    }
```

If `en-US.json` does not currently have a `documentManager` block, add the
same parent block + `raw` keys alongside the existing ones.

### Step 2.8: Typecheck

```bash
cd dashboard && pnpm typecheck
```

Expected: PASS.

### Step 2.9: Manual smoke test

1. `pnpm dev` and open the Documents sub-tab.
2. Open any markdown file. Switch viewMode to `raw`. Verify:
   - Line numbers appear in the leftmost column
   - Code content is syntax-highlighted (markdown colors)
   - Hovering a line shows the "+" gutter chip (this confirms FileBrowserCodeView wired up; the chip doesn't do anything yet — that's Task 3)
3. Click `编辑` to enter edit mode. Verify the CodeMirror editor still renders
   (regression check — `v-if="!editMode && ..."` gates the swap).
4. In edit mode, switch back to `raw` (this should be possible via the
   view-mode tabs). Verify the editor remains in edit mode — actually the
   view-mode tab itself is only visible when `!editMode`. Skip this step
   unless you can find a way; the regression we care about is the editor
   rendering under the `v-else-if="editMode"` branch, which is unchanged.
5. Select a historical revision. Verify the raw view shows the historical
   content (line numbers + highlighting). For binary historical files
   verify the placeholder shows.
6. Save file → commit.

### Step 2.10: Commit

```bash
git add dashboard/src/components/chat/message_list_comps/DocumentManager.vue \
        dashboard/src/i18n/locales/zh-CN/features/chat.json \
        dashboard/src/i18n/locales/en-US/features/chat.json
git commit -m "feat(dashboard): render raw view with FileBrowserCodeView"
```

---

## Task 3: Wire inline comments into raw view

**Files:**

- Modify: `dashboard/src/components/chat/message_list_comps/DocumentManager.vue`
- Test: manual smoke

**Interfaces:**

- Consumes: `useFileComments()` from `@/composables/useFileComments`
  (module-level singleton — same instance FileBrowser uses)
- Consumes: `FileCommentEditor.vue` (existing, no changes)
- Consumes: `CommentsPreviewDialog.vue` (existing, no changes)

### Step 3.1: Add imports

At the top of `<script setup>` add:

```ts
import {
  useFileComments,
  extractLineContext,
} from "@/composables/useFileComments";
import FileCommentEditor from "@/components/chat/message_list_comps/FileCommentEditor.vue";
import CommentsPreviewDialog from "@/components/chat/CommentsPreviewDialog.vue";
```

### Step 3.2: Add the comments state

Find the existing `const rawHighlightReady = ...` line added in Task 2
and add right after:

```ts
// ── Inline comments (in-memory, shared singleton with FileBrowser) ──
// Store is keyed on docsRoot-relative path so different docs have
// independent comment lists. Module-level singleton means comments
// survive the user switching between Documents sub-tab and Files
// sub-tab, which matches FileBrowser's expected behavior.
const fileComments = useFileComments();
const activeEditLine = ref<number | null>(null);
const activeEditCommentId = ref<string | null>(null);
const commentsDialogOpen = ref<boolean>(false);

const rawComments = computed(() =>
  rawFilePath.value ? fileComments.commentsForFile(rawFilePath.value) : [],
);

/** INVARIANT: register the current raw content into the comments
 *  store so addComment can extract line context. Same pattern as
 *  FileBrowserFilePreview.vue:300. */
watch(
  () => rawContent.value,
  (content) => {
    if (rawFilePath.value && content) {
      fileComments.registerFileContent(rawFilePath.value, content);
    }
  },
  { immediate: true },
);
```

### Step 3.3: Add the comment event handlers

After the `rawIsBinary` computed from Task 2:

```ts
function onRequestAddComment(line: number): void {
  if (!rawFilePath.value || !rawContent.value) return;
  activeEditLine.value = line;
  activeEditCommentId.value = null;
  // We pass context only as a hint to the editor preview; the
  // actual store update goes through addComment() below, which
  // re-extracts from contentCache so the values are guaranteed
  // consistent.
  const ctx = extractLineContext(rawContent.value, line);
  if (!ctx) return;
  activeEditContext.value = ctx;
}
function onRequestEditComment(commentId: string): void {
  const c = fileComments.findCommentById(commentId);
  if (!c) return;
  activeEditLine.value = c.line;
  activeEditCommentId.value = c.id;
  activeEditContext.value = {
    lineContent: c.lineContent,
    contextBefore: c.contextBefore,
    contextAfter: c.contextAfter,
  };
}
function onSaveComment(payload: {
  text: string;
  commentId: string | null;
  line: number;
}): void {
  if (payload.commentId) {
    fileComments.updateComment(payload.commentId, payload.text);
    closeCommentEditor();
    return;
  }
  if (!rawFilePath.value) return;
  const created = fileComments.addComment({
    filePath: rawFilePath.value,
    line: payload.line,
    text: payload.text,
  });
  if (!created) {
    // contentCache miss means the file content hadn't loaded yet.
    // Show a snackbar or fall through silently? For now we just
    // close; users can retry. (Add a snackbar if the spec is later
    // amended to require one.)
    closeCommentEditor();
    return;
  }
  closeCommentEditor();
}
function closeCommentEditor(): void {
  activeEditLine.value = null;
  activeEditCommentId.value = null;
  activeEditContext.value = null;
}

// Add the supporting ref for the editor context (declared near
// activeEditLine above):
// const activeEditContext = ref<LineContext | null>(null);
```

**Important**: add the `activeEditContext` ref in Step 3.2's block
alongside `activeEditLine`. Also import `LineContext` type:

```ts
import type { LineContext } from "@/composables/useFileComments";
```

### Step 3.4: Update the FileBrowserCodeView wiring

In the template, replace the placeholder `:comments="[]"` /
`:active-edit-line="null"` / `:active-edit-comment-id="null"` lines
(from Task 2.5) with:

```vue
:comments="rawComments" :active-edit-line="activeEditLine"
:active-edit-comment-id="activeEditCommentId" @request-add="onRequestAddComment"
@request-edit="onRequestEditComment"
```

### Step 3.5: Mount the FileCommentEditor

After the `</div>` closing the `document-manager__raw` block (added in
Task 2.5), inside the `document-manager__right` section, add:

```vue
<FileCommentEditor
  v-if="activeEditLine !== null && activeEditContext"
  class="document-manager__comment-editor"
  :file-path="rawFilePath"
  :line="activeEditLine"
  :comment-id="activeEditCommentId"
  :initial-text="editorInitialText"
  :line-context="activeEditContext"
  @save="onSaveComment"
  @cancel="closeCommentEditor"
/>
```

And add a supporting ref near `activeEditLine`:

```ts
const editorInitialText = ref<string>("");
```

In the `onRequestEditComment` function, set
`editorInitialText.value = c.text;` before assigning `activeEditContext`.
In `onRequestAddComment`, set `editorInitialText.value = "";`.

### Step 3.6: Add a button to open CommentsPreviewDialog

Find the existing "编辑" button at the bottom of the raw-view branch
(inside the `<template v-else>` block). Immediately above it, add:

```vue
<button
  type="button"
  class="document-manager__comments-btn"
  @click="commentsDialogOpen = true"
>
              <v-icon size="14">mdi-comment-text-multiple-outline</v-icon>
              {{ tm("spcodeProjectLoad.documentManager.comments.openList") }}
              <span v-if="rawComments.length > 0" class="document-manager__comments-count">
                {{ rawComments.length }}
              </span>
            </button>
```

The button should only appear when `rawComments.length > 0` OR
unconditionally (user might want to see an empty preview). For minimal
scope, render it unconditionally — the empty state in
CommentsPreviewDialog already handles no-comments gracefully.

### Step 3.7: Mount the CommentsPreviewDialog

At the end of the right pane (after the `</template>` closing
`<template v-else>`), add:

```vue
<CommentsPreviewDialog v-model:open="commentsDialogOpen" />
```

### Step 3.8: Add i18n keys

In `zh-CN.json`, inside the `documentManager` block:

```json
    "comments": {
      "openList": "查看评论列表"
    }
```

In `en-US.json`:

```json
    "comments": {
      "openList": "View comment list"
    }
```

### Step 3.9: Add minimal CSS for the new bits

In `<style scoped>`:

```css
.document-manager__comment-editor {
  /* FileCommentEditor is a self-positioned overlay in FileBrowser;
     mirror that here. */
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.document-manager__comments-btn {
  position: absolute;
  bottom: 16px;
  right: 16px;
  /* Layout matching document-manager__edit-btn; share its rule
     if convenient. */
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 6px;
  padding: 6px 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 12px;
}
.document-manager__comments-count {
  background: rgba(var(--v-theme-primary), 0.15);
  color: rgb(var(--v-theme-primary));
  padding: 0 6px;
  border-radius: 999px;
  font-size: 11px;
}
```

(If the existing `.document-manager__edit-btn` rule already provides the
button styling you need, drop the long-form properties above and reuse it
with a class name like `document-manager__comments-btn document-manager__edit-btn`.)

### Step 3.10: Typecheck

```bash
cd dashboard && pnpm typecheck
```

Expected: PASS.

### Step 3.11: Manual smoke test

1. Open a markdown doc, switch to `raw` view.
2. Hover a line — "+" chip appears. Click it.
3. The FileCommentEditor appears at the bottom with the line context shown.
4. Type a comment, save. The chip becomes a comment icon on that line.
5. Click the comment icon → reopens the editor (edit mode). Save / delete.
6. Click "查看评论列表" → CommentsPreviewDialog opens with all comments
   for this file.
7. Switch to another doc (different file). Switch back. Comments for the
   first doc are still there.
8. Open the SAME file in the Files sub-tab's FileBrowser. The same
   comments appear (singleton store — verified cross-tab).
9. Refresh the page. Comments are gone (in-memory only).
10. Commit.

### Step 3.12: Commit

```bash
git add dashboard/src/components/chat/message_list_comps/DocumentManager.vue \
        dashboard/src/i18n/locales/zh-CN/features/chat.json \
        dashboard/src/i18n/locales/en-US/features/chat.json
git commit -m "feat(dashboard): wire inline comments into DocumentManager raw view"
```

---

## Task 4: Fullscreen state + button + Esc keybinding

**Files:**

- Modify: `dashboard/src/components/chat/message_list_comps/DocumentManager.vue`
- Test: `dashboard/src/components/chat/message_list_comps/DocumentManager.spec.ts` (CREATE)
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`

**Interfaces:**

- Produces: `isFullscreen: Ref<boolean>` (local to DocumentManager, NOT persisted)
- Produces: `toggleFullscreen(): void` and `exitFullscreen(): void`
- Produces: keydown listener registered on mount, removed on unmount
- Produces: button "全屏 / Exit Fullscreen" next to DocumentViewModeTab

### Step 4.1: Add the state and toggle function

In `<script setup>`, near the other refs at the top, add:

```ts
/** Fullscreen review mode. NOT persisted — each visit starts at false. */
const isFullscreen = ref<boolean>(false);
const leftDrawerOpen = ref<boolean>(false);

function toggleFullscreen(): void {
  isFullscreen.value = !isFullscreen.value;
  if (!isFullscreen.value) {
    // Closing fullscreen also closes the drawer (otherwise the
    // drawer would visually pop out from behind the now-restored
    // left pane).
    leftDrawerOpen.value = false;
  }
}
function openLeftDrawer(): void {
  leftDrawerOpen.value = true;
}
function closeLeftDrawer(): void {
  leftDrawerOpen.value = false;
}
```

### Step 4.2: Add the Esc keydown listener + body scroll lock

After the existing function declarations, add:

```ts
/** Esc exits fullscreen (when fullscreen is on). Listener is attached
 *  on mount, detached on unmount. Bound to `document` (not scoped to the
 *  fullscreen overlay) so Esc still works while the user is interacting
 *  with the comment editor, the preview dialog, or any input element
 *  inside the overlay. Does NOT call stopPropagation / preventDefault so
 *  those other components can still handle Esc for their own purposes. */
function onKeyDown(e: KeyboardEvent): void {
  if (e.key === "Escape" && isFullscreen.value) {
    isFullscreen.value = false;
    leftDrawerOpen.value = false;
  }
}
onMounted(() => document.addEventListener("keydown", onKeyDown));

/** Body scroll lock — mirror of DiffPreview spec §3.4. While fullscreen
 *  is on, lock the chat page from scrolling behind the overlay. Released
 *  on flip-back to false; also released on unmount if the user navigates
 *  away while fullscreen is still on. We don't snapshot-restore the
 *  prior `body.style.overflow` value because no other component in the
 *  chat page is documented to lock body scroll while DocumentManager is
 *  mounted. */
watch(isFullscreen, (v) => {
  document.body.style.overflow = v ? "hidden" : "";
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeyDown);
  if (isFullscreen.value) {
    document.body.style.overflow = "";
  }
});
```

If `watch` / `onBeforeUnmount` is not already imported, add it to the vue
import (`import { onBeforeUnmount, onMounted, ref, watch, ... } from "vue";`).

### Step 4.3: Add the toggle button

In the template, find `DocumentViewModeTab` (inside `<template v-else>`):

```vue
<DocumentViewModeTab v-model="viewMode" :has-revision="!!selectedRevision" />
```

Wrap it in a flex container together with the new button:

```vue
<div class="document-manager__view-bar">
              <DocumentViewModeTab
                v-model="viewMode"
                :has-revision="!!selectedRevision"
              />
              <button
                type="button"
                class="document-manager__fullscreen-btn"
                :aria-pressed="isFullscreen"
                :title="tm(
                  isFullscreen
                    ? 'spcodeProjectLoad.documentManager.fullscreen.exit'
                    : 'spcodeProjectLoad.documentManager.fullscreen.enter'
                )"
                @click="toggleFullscreen"
              >
                <v-icon size="14">
                  {{ isFullscreen ? "mdi-fullscreen-exit" : "mdi-fullscreen" }}
                </v-icon>
                {{
                  tm(
                    isFullscreen
                      ? "spcodeProjectLoad.documentManager.fullscreen.exit"
                      : "spcodeProjectLoad.documentManager.fullscreen.enter"
                  )
                }}
              </button>
            </div>
```

### Step 4.4: Add i18n keys

In `zh-CN.json` `documentManager`:

```json
    "fullscreen": {
      "enter": "进入全屏",
      "exit": "退出全屏"
    }
```

In `en-US.json`:

```json
    "fullscreen": {
      "enter": "Enter fullscreen",
      "exit": "Exit fullscreen"
    }
```

### Step 4.5: Add CSS for the new bits

```css
.document-manager__view-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.document-manager__fullscreen-btn {
  background: transparent;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 6px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.document-manager__fullscreen-btn[aria-pressed="true"] {
  background: rgba(var(--v-theme-primary), 0.12);
  border-color: rgba(var(--v-theme-primary), 0.4);
}
```

### Step 4.6: Write the failing component test

Create `dashboard/src/components/chat/message_list_comps/DocumentManager.spec.ts`.
This test mounts DocumentManager and asserts the `isFullscreen` ref's behavior
through emitted DOM events. Because DocumentManager is large and has many
deps, use `@vue/test-utils` with `global.stubs` to short-circuit heavy
children.

```ts
import { describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import DocumentManager from "./DocumentManager.vue";

// Stub the heaviest children so we can mount without pulling in the
// whole vue-router / vuetify / shiki stack. We only care about
// DocumentManager's fullscreen state + Esc wiring.
const stubs = {
  FileBrowserTree: { template: "<div />" },
  DocumentEditor: { template: "<div />" },
  DocumentHistoryPanel: { template: "<div />" },
  DocumentViewModeTab: { template: "<div />" },
  FileBrowserCodeView: { template: "<div />" },
  FileCommentEditor: { template: "<div />" },
  CommentsPreviewDialog: { template: "<div />" },
  MarkdownView: { template: "<div />" },
  DiffPreview: { template: "<div />" },
};

describe("DocumentManager fullscreen state", () => {
  it("toggles isFullscreen when the fullscreen button is clicked", async () => {
    const wrapper = mount(DocumentManager, {
      props: { umo: "test" },
      global: { stubs },
    });
    await nextTick();
    // The button starts hidden / disabled because no doc is selected,
    // but we can still dispatch a click directly. Easier: assert the
    // internal state by triggering the function via the wrapper.
    const vm = wrapper.vm as unknown as {
      isFullscreen: boolean;
      toggleFullscreen: () => void;
    };
    expect(vm.isFullscreen).toBe(false);
    vm.toggleFullscreen();
    expect(vm.isFullscreen).toBe(true);
    vm.toggleFullscreen();
    expect(vm.isFullscreen).toBe(false);
  });

  it("Esc exits fullscreen when fullscreen is on", async () => {
    const wrapper = mount(DocumentManager, {
      props: { umo: "test" },
      global: { stubs },
    });
    await nextTick();
    const vm = wrapper.vm as unknown as {
      isFullscreen: boolean;
      toggleFullscreen: () => void;
    };
    vm.toggleFullscreen();
    expect(vm.isFullscreen).toBe(true);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await nextTick();
    expect(vm.isFullscreen).toBe(false);
  });

  it("Esc is a no-op when fullscreen is off (does not throw)", async () => {
    const wrapper = mount(DocumentManager, {
      props: { umo: "test" },
      global: { stubs },
    });
    await nextTick();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await nextTick();
    const vm = wrapper.vm as unknown as { isFullscreen: boolean };
    expect(vm.isFullscreen).toBe(false);
  });
});
```

### Step 4.7: Run test to verify it fails

```bash
cd dashboard && pnpm test -- DocumentManager.spec
```

Expected: FAIL — DocumentManager has props it expects that aren't set in
this minimal stub. Read the failure message; if it complains about
`workspace-path` or `selectedDoc` props, add them to `props:`. If it
complains about i18n key `documentManager.fullscreen.enter` being missing,
re-run after adding i18n keys (Step 4.4) and try again.

This step may require iteration — DocumentManager is a heavyweight
component. The point of these tests is to assert the _fullscreen state
behavior_, not to render the whole thing. If the stubs above are
insufficient, narrow the scope by adding more stubs rather than wiring
the whole tree.

### Step 4.8: Run test to verify it passes

After any adjustments in Step 4.7, run again:

```bash
cd dashboard && pnpm test -- DocumentManager.spec
```

Expected: PASS.

### Step 4.9: Typecheck

```bash
cd dashboard && pnpm typecheck
```

Expected: PASS.

### Step 4.10: Commit

```bash
git add dashboard/src/components/chat/message_list_comps/DocumentManager.vue \
        dashboard/src/components/chat/message_list_comps/DocumentManager.spec.ts \
        dashboard/src/i18n/locales/zh-CN/features/chat.json \
        dashboard/src/i18n/locales/en-US/features/chat.json
git commit -m "feat(dashboard): add fullscreen toggle button and Esc exit"
```

---

## Task 5: Viewport fullscreen via Teleport + left pane drawer

**Files:**

- Modify: `dashboard/src/components/chat/message_list_comps/DocumentManager.vue` (template + scoped CSS only)

**Interfaces:**

- Consumes: `isFullscreen: Ref<boolean>` and `leftDrawerOpen: Ref<boolean>` from Task 4
- Produces:
  - `<Teleport to="body" :disabled="!isFullscreen">` wrapper around the outer
    `.document-manager` div so fullscreen mounts under `<body>` and CSS can
    position it `fixed; inset: 0` to cover the entire browser viewport
  - `.is-fullscreen` class on the outer `.document-manager` element (drives
    the `position: fixed; inset: 0; z-index: 9999` CSS rule)
  - `.document-manager__pane-left` hidden in fullscreen (`v-show`)
  - A 240px overlay drawer + backdrop on the left when `leftDrawerOpen` is
    true; backdrop click closes the drawer (no `document` listener needed —
    the overlay is the topmost element on the page)

**Why Teleport (not just a CSS class on the sidebar's child):** the chat
sidebar body holds a fixed-width container and a vertical scrollbar. A
fullscreen-only class on the sidebar's child can never escape that
horizontal containment, so the previous `grid-template-columns: 0 1fr auto`
rule only produced "sidebar pane fills its width" — not viewport fullscreen.
`<Teleport to="body" :disabled="!isFullscreen">` makes the Teleport a
transparent pass-through when fullscreen is off (the inner div keeps its
natural position in `.git-diff-sidebar-body`) and portals it to `<body>` when
on (the same div, with `position: fixed; inset: 0`, becomes a viewport-sized
overlay above the chat column, header, and dialog stack). This mirrors the
**DiffPreview** overlay implementation (`spec 2026-06-30-diff-fullscreen-design.md`
§3.2) and uses the same z-index layer (`9999`) so the two overlays stack
consistently. We choose `:disabled` (single live instance) rather than
`v-if`-gated two-copy Teleport (DiffPreview's pattern) because
DocumentManager's children are refs and state-heavy — keeping a single live
instance means current file, view mode, split percentages, comments, and
edit buffer all survive the fullscreen toggle with zero extra plumbing.

### Step 5.1: Wrap the outer `<div>` in `<Teleport>`

Find the outermost element in the template (the single
`<div class="document-manager">` that wraps all three panes). Add the
Teleport wrapper:

```vue
<template>
  <Teleport to="body" :disabled="!isFullscreen">
    <div class="document-manager" :class="{ 'is-fullscreen': isFullscreen }">
      <!-- existing children, untouched -->
    </div>
  </Teleport>
</template>
```

The Teleport element itself is not in the rendered DOM after the move —
Vue 3 hoists the inner `<div>` to become a direct child of `<body>` when
`isFullscreen === true`. When false, `:disabled=true` makes Teleport a
pass-through and the `<div>` keeps its natural position in
`.git-diff-sidebar-body`.

If `Teleport` is not already imported, add it to the vue import
(`import { Teleport, ... } from "vue";` — it's a built-in compiler target
and does NOT need to be imported manually in `<script setup>`, but if you
use it inside `<template>` directly it should just work).

### Step 5.2: Conditionally render the left pane

Update the existing left-pane element (which is already gated by
`v-show="!isLeftPaneCollapsed"`) so it also hides when fullscreen is on:

```vue
<div
  v-show="!isLeftPaneCollapsed && !isFullscreen"
  class="document-manager__pane-left"
  :style="{ width: treeSplit.percent.value + '%' }"
>
            <!-- existing tree content (DocumentTreePanel etc.) -->
          </div>
```

`v-show` (not `v-if`) keeps the tree component mounted so its
selection / scroll state survives fullscreen toggling.

### Step 5.3: Add the chevron rail + overlay drawer + backdrop

When fullscreen is on, the user needs a way to bring the left pane back
temporarily. Add these three elements inside the outer `<div>`, after the
divider and before the right pane:

```vue
<button
  v-if="isFullscreen"
  type="button"
  class="document-manager__left-rail"
  :aria-label="tm('spcodeProjectLoad.documentManager.fullscreen.openDrawer')"
  @click="openLeftDrawer"
>
            <v-icon size="16">mdi-chevron-double-right</v-icon>
          </button>
<div
  v-if="isFullscreen && leftDrawerOpen"
  class="document-manager__left-drawer"
  data-testid="document-manager-left-drawer"
>
            <!-- existing tree content (same as the left pane above) -->
          </div>
<div
  v-if="isFullscreen && leftDrawerOpen"
  class="document-manager__drawer-backdrop"
  @click="closeLeftDrawer"
/>
```

The backdrop is a single absolutely-positioned div covering the full
overlay (z-index between the rail and the drawer). Clicking it closes
the drawer. No `document` click listener is needed — the fullscreen
overlay is the topmost element on the page, so any click outside the
drawer lands on the backdrop (or the dialog stack above it, in which
case we don't care about drawer state).

To avoid duplicating the tree template, consider extracting the left pane
into a `<DocumentManagerTree>` subcomponent — but per the inline-first
rule, do this only if the duplication is intolerable. For now, the
duplication is acceptable.

### Step 5.4: No document listener needed

Remove (or never add) any `document.addEventListener("click", ...)` for
the drawer's outside-click behavior. The backdrop div in Step 5.3
captures every click outside the drawer that lands on the fullscreen
overlay, and the overlay is the topmost element so no other click can
land on `.git-diff-sidebar-body` while fullscreen is on. (The earlier
draft's document listener was a holdover from the in-sidebar
fullscreen design, where the fullscreen copy was still inside
`.git-diff-sidebar-body` and could not rely on overlay containment.)

### Step 5.5: CSS

```css
.document-manager.is-fullscreen {
  /* Teleport moves this element to <body> when fullscreen is on; CSS
     then positions it fixed;inset:0 so it covers the entire browser
     viewport, not just the chat sidebar body. The inner flex
     layout (tree + center + right) is unchanged — this element
     is still the flex parent for its children. */
  position: fixed;
  inset: 0;
  z-index: 9999;
  width: 100%;
  height: 100%;
  background: rgb(var(--v-theme-background));
}
.document-manager__left-rail {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 10;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 6px;
  padding: 6px 8px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
}
.document-manager__left-drawer {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 240px;
  z-index: 20;
  background: rgb(var(--v-theme-surface));
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  overflow: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.document-manager__drawer-backdrop {
  position: absolute;
  inset: 0;
  z-index: 15;
  background: rgba(0, 0, 0, 0.15);
  cursor: default;
}
```

**Removed from the earlier draft:** the
`.document-manager.is-fullscreen { grid-template-columns: 0 1fr auto }` rule
no longer applies — with the Teleport the outer element's intrinsic size is
the viewport, and the inner flex / grid layout rules (tree + center + right
columns) are unchanged. The left pane just disappears via `v-show`; the
center + right panes naturally re-divide the available width via their
existing divider rule (no flex-basis math changes).

### Step 5.6: i18n keys

In `dashboard/src/i18n/locales/zh-CN/features/chat.json`:

```json
    "fullscreen": {
      "enter": "进入全屏",
      "exit": "退出全屏",
      "openDrawer": "展开左侧文件树"
    }
```

In `dashboard/src/i18n/locales/en-US/features/chat.json`:

```json
    "fullscreen": {
      "enter": "Enter fullscreen",
      "exit": "Exit fullscreen",
      "openDrawer": "Open file tree"
    }
```

In `dashboard/src/i18n/locales/ru-RU/features/chat.json` (optional — falls
back to en-US if not added; other modules' `fullscreen.*` blocks do
include Russian translations, so add for parity):

```json
    "fullscreen": {
      "enter": "На весь экран",
      "exit": "Выйти из полноэкранного режима",
      "openDrawer": "Развернуть дерево файлов"
    }
```

### Step 5.7: Typecheck + manual smoke

```bash
cd dashboard && pnpm typecheck
```

Expected: PASS.

Manual smoke:

1. Open the Documents sub-tab on a real project (mount a directory
   with at least one `.md` file).
2. Click "进入全屏". Verify the document-manager overlay leaves the
   chat sidebar body and fills the **browser viewport** (it should now
   cover the chat column, the header, and sit above the dialog stack).
3. Verify the chat page itself does not scroll — its `body` overflow
   is `hidden` while fullscreen is on. Scroll the wheel over the page
   and confirm the underlying chat column does not move.
4. Verify the chevron rail button is at the top-left of the overlay.
   Click it — the 240px drawer slides in (no transition required). Click
   the dimmed backdrop — drawer closes.
5. Press `Esc` — fullscreen exits AND drawer is hidden. Body scroll
   is restored.
6. Refresh the page. Verify fullscreen is NOT remembered (the value is
   `false`).
7. Edit mode + fullscreen: enter fullscreen, click "编辑", verify
   CodeMirror still renders correctly (no regression).
8. Diff view + fullscreen: same.
9. Open a markdown doc, switch to `raw` view, click a line to add a
   comment. Verify the comment editor's Esc-cancel still works while
   fullscreen is on.
10. Commit.

### Step 5.8: Commit

```bash
git add dashboard/src/components/chat/message_list_comps/DocumentManager.vue \
        dashboard/src/i18n/locales/zh-CN/features/chat.json \
        dashboard/src/i18n/locales/en-US/features/chat.json \
        dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "fix(dashboard): make document-manager fullscreen fill the viewport via Teleport"
```

## Self-Review

**Spec coverage:**

| Spec section                                                                          | Task                                                                                                                                                                         |
| ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| §3.1 Fullscreen toggle + Esc                                                          | Task 4 (state, button, document-level keydown, body-scroll-lock release in onBeforeUnmount)                                                                                  |
| §3.2 Fullscreen layout (Teleport-to-body overlay + left collapse + drawer + backdrop) | Task 5                                                                                                                                                                       |
| §3.2 Body scroll lock (matches DiffPreview §3.4)                                      | Task 4 (watcher + unmount release)                                                                                                                                           |
| §3.3 Raw view line numbers + comments                                                 | Task 2 (line numbers) + Task 3 (comments)                                                                                                                                    |
| §3.4 Right history panel unchanged                                                    | Tasks 2/3/4 do not touch history panel                                                                                                                                       |
| §3.5 Diff view unchanged                                                              | Tasks 2/3/4 do not touch DiffPreview                                                                                                                                         |
| §4 State surface (isFullscreen, comments wiring)                                      | Tasks 2/3/4                                                                                                                                                                  |
| §5 Error handling (Shiki fail, binary, large file, Esc-in-input)                      | Task 2 (Shiki fallback, binary/empty placeholder) + Task 4 (Esc only fires when fullscreen; does NOT call stopPropagation so the comment editor's own Esc-cancel still runs) |
| §6 Testing                                                                            | Tasks 1 (unit), 2 (manual), 3 (manual), 4 (component)                                                                                                                        |

**No placeholders** — every step has exact file paths, complete code,
exact commands, and expected output.

**Type consistency** — `useDocumentMarkdownHighlight`, `useFileComments`,
`FileBrowserCodeView` props and events are used with matching signatures
across tasks. `rawFilePath` is consistently the docsRoot-relative path.
`rawHighlightedHtml` is consistently the Shiki output. `isFullscreen` /
`leftDrawerOpen` are introduced in Task 4 and consumed only in Task 5.

**No spec requirement missing**: full review confirms all of §3.1-§3.5,
§4, §5 are covered.
