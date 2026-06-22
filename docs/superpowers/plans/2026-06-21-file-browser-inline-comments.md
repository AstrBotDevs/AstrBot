# File Browser Inline Comments Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add GitHub-style line-level comments to the file browser preview. Hover a line to reveal a "+" gutter button, open a bottom-anchored editor, save the comment. Comments are accumulated in memory and appended (with frozen line content + ±1 context as LLM fingerprints) to the user's next outgoing message.

**Architecture:** Pure frontend. New `useFileComments` composable owns the comment store + content cache. New `FileBrowserCodeView` adds line numbers + hover gutter to Shiki output. New `FileCommentEditor` is a bottom-anchored panel. `FileBrowserFilePreview` integrates both. `StandaloneChat` provides the composable via inject + attaches formatted comments to `sendCurrentMessage`. `ChatInput` shows a chip with the count.

**Tech Stack:** Vue 3 (Composition API + `<script setup>`), TypeScript, Shiki (existing), Vuetify (`v-chip`, `v-btn`, `v-snackbar`), VeeValidate not used; i18n via `useModuleI18n("features/chat")`.

**Spec:** `docs/superpowers/specs/2026-06-21-file-browser-inline-comments-design.md`

**Pre-commit checks:** `ruff format` / `ruff check` / `pre-commit` are N/A for the dashboard (they're Python-focused). Linting: `pnpm lint` if the dashboard has it configured.

**Typecheck policy:** Every commit in the plan is preceded by `pnpm typecheck` exiting 0. Tasks that introduce a temporary typecheck failure (e.g. Chunk 1 Task 1.2 — intermediate state with `formatForLLM` not yet defined) defer their commit to the follow-up task that fixes the error. The plan's commit cadence respects this rule.

**i18n typecheck caveat:** `tm()` from `useModuleI18n` is typed as `(key: string, params?: ...) => string` and does NOT fail typecheck on missing keys (missing keys are a runtime concern that shows the raw key to the user). Steps that say "expected: typecheck fails on missing i18n key" are incorrect; typecheck always exits 0 — the only effect of missing keys is runtime fallback in the UI. The plan has been corrected to reflect this.

---

## File Structure

### New files
| File | Responsibility |
|------|----------------|
| `dashboard/src/composables/useFileComments.ts` | Comment store, content cache, helpers (`extractLineContext`), `FILE_COMMENTS_KEY` symbol |
| `dashboard/src/components/chat/message_list_comps/FileBrowserCodeView.vue` | Line numbers + hover-tracking gutter + Shiki output, three-column grid layout |
| `dashboard/src/components/chat/message_list_comps/FileCommentEditor.vue` | Bottom-anchored editor: textarea + save / cancel / delete, line context display |

### Modified files
| File | Change |
|------|--------|
| `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue` | Inject fileComments; split `<pre v-html>` into `<FileBrowserCodeView>` + mount `<FileCommentEditor>`; add invariant watch + editor state + snackbar |
| `dashboard/src/components/chat/StandaloneChat.vue` | `import { useFileComments, FILE_COMMENTS_KEY }`; create store + provide; `watch(currSessionId)` → `resetForSession()`; `sendCurrentMessage` prepends formatted comments |
| `dashboard/src/components/chat/ChatInput.vue` | Add `commentCount: number` prop; render `<v-chip>` inside `input-area__status-row__right` after `GitDiffChip` |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | Add `spcodeProjectLoad.fileBrowser.comment.*` keys (zh-CN) |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | Same keys (en-US) |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | Same keys (ru-RU) |

---

## Chunk 1: `useFileComments.ts` composable

**Spec ref:** §4.1.

**Files:**
- Create: `dashboard/src/composables/useFileComments.ts`
- Verify (no test files; runtime validation via §8.3 manual checklist after integration)

### Task 1.1: Scaffold composable with `FileComment` interface and `extractLineContext` helper

**Files:**
- Create: `dashboard/src/composables/useFileComments.ts`

- [ ] **Step 1: Write the file with type definitions + helpers (no composable logic yet)**

Open `dashboard/src/composables/useFileComments.ts` and write:

```typescript
// Author: elecvoid243, 2026-06-21
// Spec: docs/superpowers/specs/2026-06-21-file-browser-inline-comments-design.md §4.1
// In-memory comment store + content cache for the file-browser inline
// comments feature. See spec §1, §2 (decisions), §4.1, §5 for context.

/**
 * Single file comment, anchored to a line at comment-creation time.
 * `lineContent` and `contextBefore`/`contextAfter` are frozen snapshots
 * so the LLM can use `lineContent` as a content-fingerprint to relocate
 * the line even if the file has been edited since the comment was made.
 */
export interface FileComment {
  /** UUID, stable across edits/deletes. */
  id: string;
  /** Absolute path. Comments are partitioned by this. */
  filePath: string;
  /** 1-based line number at comment time. May drift if file is edited. */
  line: number;
  /** Exact line content at comment time. The LLM uses this as a fingerprint. */
  lineContent: string;
  /** Line above (null if line === 1). */
  contextBefore: string | null;
  /** Line below (null if line === last line). */
  contextAfter: string | null;
  /** User's comment text. Multi-line allowed. */
  text: string;
  createdAt: number;
  updatedAt: number;
}

/** Single source of truth for line context extraction. Used by both
 *  useFileComments (to freeze the snapshot in addComment) and by
 *  FileBrowserFilePreview (to populate the editor preview). Keeping
 *  the two call sites in lockstep via one helper means the editor
 *  preview is always consistent with what the comment will store. */
export interface LineContext {
  lineContent: string;
  contextBefore: string | null;
  contextAfter: string | null;
}

export function extractLineContext(content: string, line: number): LineContext | null {
  const lines = content.split("\n");
  const idx = line - 1;
  if (idx < 0 || idx >= lines.length) return null;
  return {
    lineContent: lines[idx],
    contextBefore: idx > 0 ? lines[idx - 1] : null,
    contextAfter: idx < lines.length - 1 ? lines[idx + 1] : null,
  };
}

/** UUID generator matching the pattern used in StandaloneChat.vue:311. */
function newId(): string {
  return (
    (globalThis.crypto?.randomUUID?.() as string | undefined) ??
    `${Date.now()}-${Math.random()}`
  );
}
```

- [ ] **Step 2: Run typecheck to verify the file compiles**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -30`
Expected: exits 0 (no errors).

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/composables/useFileComments.ts
git commit -m "feat(comments): scaffold useFileComments with FileComment + extractLineContext"
```

### Task 1.2: Implement the composable body (state + CRUD + reset)

**Files:**
- Modify: `dashboard/src/composables/useFileComments.ts`

- [ ] **Step 1: Add the composable body to the file**

Open the file and add the imports at the **top** of the file (before the existing `FileComment` interface). Then append the composable body after `function newId()`:

```typescript
import { reactive, computed } from "vue";

/**
 * In-memory comment store + content cache for the file-browser.
 *
 *   comments[filePath] = FileComment[]
 *   contentCache[filePath] = string
 *
 * Comments are cleared on session switch via `resetForSession()`. The
 * content cache survives session switches and is auto-rebuilt by
 * FileBrowserFilePreview's `immediate: true` watch whenever a file
 * is opened. addComment freezes the line snapshot from the cache;
 * returns null if the cache is empty (caller decides UX).
 */
export function useFileComments() {
  const comments = reactive<Record<string, FileComment[]>>({});
  const contentCache = reactive<Record<string, string>>({});

  /** Drop the current session's comments. Called by StandaloneChat
   *  when the user switches to a different session. Does NOT clear
   *  contentCache (see field doc above). */
  function resetForSession(): void {
    for (const k of Object.keys(comments)) delete comments[k];
  }

  /** Register a file's current full content. Idempotent. */
  function registerFileContent(filePath: string, content: string): void {
    contentCache[filePath] = content;
  }

  /** Add a comment, freezing lineContent / contextBefore / contextAfter
   *  from the cached content. Returns null if the cache has no entry
   *  for this file (caller shows a snackbar and keeps the editor open). */
  function addComment(input: {
    filePath: string;
    line: number;
    text: string;
  }): FileComment | null {
    const content = contentCache[input.filePath];
    if (content === undefined) return null;
    const ctx = extractLineContext(content, input.line);
    if (ctx === null) return null;
    const comment: FileComment = {
      id: newId(),
      filePath: input.filePath,
      line: input.line,
      lineContent: ctx.lineContent,
      contextBefore: ctx.contextBefore,
      contextAfter: ctx.contextAfter,
      text: input.text,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    (comments[input.filePath] ??= []).push(comment);
    return comment;
  }

  function updateComment(id: string, newText: string): void {
    for (const list of Object.values(comments)) {
      const c = list.find((c) => c.id === id);
      if (c) {
        c.text = newText;
        c.updatedAt = Date.now();
        return;
      }
    }
  }

  function deleteComment(id: string): void {
    for (const [path, list] of Object.entries(comments)) {
      const i = list.findIndex((c) => c.id === id);
      if (i >= 0) {
        list.splice(i, 1);
        if (list.length === 0) delete comments[path];
        return;
      }
    }
  }

  /** Find a comment by id in the current session. Returns null if not found. */
  function findCommentById(id: string): FileComment | null {
    for (const list of Object.values(comments)) {
      const c = list.find((c) => c.id === id);
      if (c) return c;
    }
    return null;
  }

  /** Total comment count for the current session (across all files). */
  const totalCount = computed<number>(() => {
    let n = 0;
    for (const list of Object.values(comments)) n += list.length;
    return n;
  });

  /** Comments for a specific file in the current session. */
  function commentsForFile(filePath: string): FileComment[] {
    return comments[filePath] ?? [];
  }

  return {
    totalCount,
    resetForSession,
    registerFileContent,
    addComment,
    updateComment,
    deleteComment,
    findCommentById,
    commentsForFile,
    formatForLLM,
  };
}
```

- [ ] **Step 2: Run typecheck (expect a missing `formatForLLM` error)**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -30`
Expected: FAIL with "Cannot find name 'formatForLLM'".

This is intentional — we'll add it in the next task. The error confirms the structure is being parsed.

### Task 1.3: Implement `formatForLLM`

**Files:**
- Modify: `dashboard/src/composables/useFileComments.ts`

- [ ] **Step 1: Add `formatForLLM` as a function inside the composable (before the return)**

Insert before the `return { ... }` line:

```typescript
  /** Format all comments in the current session as a structured
   *  plain-text block ready to be appended to the user's outgoing
   *  message. Returns "" if no comments.
   *
   *  Output format: a leading prose section, then for each file a
   *  markdown header and a fenced code block (4-backtick outer fence
   *  so the user's comment text can contain 3-backtick fences
   *  without breaking the outer block — markdown supports this).
   *  The code block uses git-diff-style `>` marker for the commented
   *  line. See spec §5.1 for the full format spec. */
  function formatForLLM(): string {
    const allComments: FileComment[] = [];
    for (const list of Object.values(comments)) allComments.push(...list);
    if (allComments.length === 0) return "";

    const byFile = new Map<string, FileComment[]>();
    for (const c of allComments) {
      if (!byFile.has(c.filePath)) byFile.set(c.filePath, []);
      byFile.get(c.filePath)!.push(c);
    }

    const out: string[] = [
      "[File review comments]",
      "Each entry shows the line content (and 1 line of context above/below)",
      "that was current when the comment was written. Use the line content",
      "as a fingerprint to locate the line in the current file — line numbers",
      "may have drifted if the file was edited since the comment.",
    ];

    for (const [filePath, commentList] of byFile) {
      const sorted = [...commentList].sort((a, b) => a.line - b.line);

      // Group adjacent comments (line diff <= 3) into a shared window.
      type Window = { startLine: number; endLine: number; comments: FileComment[] };
      const windows: Window[] = [];
      for (const c of sorted) {
        const last = windows[windows.length - 1];
        if (last && c.line - last.endLine <= 3) {
          last.endLine = Math.max(last.endLine, c.line);
          last.comments.push(c);
        } else {
          windows.push({ startLine: c.line, endLine: c.line, comments: [c] });
        }
      }

      for (const win of windows) {
        const ctxStart = win.comments.some((c) => c.contextBefore !== null)
          ? Math.max(1, win.startLine - 1)
          : win.startLine;
        const ctxEnd = win.comments.some((c) => c.contextAfter !== null)
          ? win.endLine + 1
          : win.endLine;

        const header =
          win.startLine === win.endLine
            ? `\`${filePath}\` line ${win.startLine}:`
            : `\`${filePath}\` lines ${win.startLine}-${win.endLine}:`;
        out.push("");
        out.push(header);
        out.push("````");  // 4-backtick fence (see spec §5.1)
        const commentedSet = new Set(win.comments.map((c) => c.line));
        const commentByLine = new Map(win.comments.map((c) => [c.line, c]));

        for (let line = ctxStart; line <= ctxEnd; line++) {
          const c = commentByLine.get(line);
          let lineContent: string;
          if (c) {
            lineContent = c.lineContent;
          } else if (line === ctxStart && win.comments[0].contextBefore !== null) {
            lineContent = win.comments[0].contextBefore ?? "";
          } else if (
            line === ctxEnd &&
            win.comments[win.comments.length - 1].contextAfter !== null
          ) {
            lineContent = win.comments[win.comments.length - 1].contextAfter ?? "";
          } else {
            lineContent = "";
          }
          const marker = commentedSet.has(line) ? ">" : " ";
          const padded = String(line).padStart(4);
          out.push(`  ${marker} ${padded} │ ${lineContent}`);
          if (c) {
            const textLines = c.text.split("\n");
            out.push(`         │ Comment: ${textLines[0]}`);
            for (let i = 1; i < textLines.length; i++) {
              out.push(`         │ ${textLines[i]}`);
            }
          }
        }
        out.push("````");
      }
    }
    return out.join("\n");
  }
```

- [ ] **Step 2: Run typecheck**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -30`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/composables/useFileComments.ts
git commit -m "feat(comments): add resetForSession, addComment, updateComment, deleteComment, findCommentById, commentsForFile, formatForLLM, totalCount"
```

### Task 1.4: Add `FILE_COMMENTS_KEY` export

**Files:**
- Modify: `dashboard/src/composables/useFileComments.ts`

- [ ] **Step 1: Add the InjectionKey export**

Add `import type { InjectionKey } from "vue";` to the top of the file (alongside the other imports). Then append the following at the bottom of the file:

```typescript

/**
 * Stable injection key for the file-comments store. Must be exported
 * from this single file (NOT re-declared in StandaloneChat.vue or
 * FileBrowserFilePreview.vue). A Symbol literal in two files would
 * produce two different symbols and silently break inject().
 */
export const FILE_COMMENTS_KEY: InjectionKey<ReturnType<typeof useFileComments>> =
  Symbol("fileComments");
```

- [ ] **Step 2: Run typecheck**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -30`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/composables/useFileComments.ts
git commit -m "feat(comments): export FILE_COMMENTS_KEY for provide/inject"
```

### Task 1.5: (Removed — defer formatForLLM smoke testing to Chunk 3)

The `formatForLLM` algorithm is the most logic-heavy piece of Chunk 1, but Node can't `require()` TypeScript files directly, and adding a temporary `console.log` to `FileBrowserFilePreview.vue` would leak into Chunk 3. Instead, the integration tests in Chunk 3 (specifically §8.3 #7) exercise `formatForLLM` end-to-end with a real comment in the UI.

### Task 1.6: Chunk 1 completion checklist

- [ ] All Tasks 1.1–1.5 done
- [ ] `pnpm typecheck` exits 0 from `dashboard/`
- [ ] 3 commits added: scaffold / composable body + formatForLLM / FILE_COMMENTS_KEY

---

## Chunk 2: `FileBrowserCodeView.vue` + `FileCommentEditor.vue`

**Spec ref:** §4.2 (CodeView), §4.3 (Editor).

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/FileBrowserCodeView.vue`
- Create: `dashboard/src/components/chat/message_list_comps/FileCommentEditor.vue`

### Task 2.1: Scaffold `FileBrowserCodeView.vue` (template + script setup with placeholder render)

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/FileBrowserCodeView.vue`

- [ ] **Step 1: Write the file with template, script setup, and styles**

```vue
<!-- Author: elecvoid243, 2026-06-21
     Spec: docs/superpowers/specs/2026-06-21-file-browser-inline-comments-design.md §4.2 -->
<script setup lang="ts">
import { computed, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { FileComment } from "@/composables/useFileComments";

const props = defineProps<{
  highlightedHtml: string;
  filePath: string;
  comments: FileComment[];
  activeEditLine: number | null;
  activeEditCommentId: string | null;
  isDark: boolean;
}>();

const emit = defineEmits<{
  (e: "request-add", line: number): void;
  (e: "request-edit", commentId: string): void;
}>();

const { tm } = useModuleI18n("features/chat");

/** Total line count derived from the Shiki output by counting
 *  `<span class="line">` wrappers. Single point that knows the
 *  Shiki DOM convention (see spec §6 risk #1). Returns a number
 *  (not an array) so the template can use `v-for="line in count"`. */
const lineCount = computed<number>(() => {
  const m = props.highlightedHtml.match(/<span class="line">/g);
  return m ? m.length : 0;
});

const codeContentRef = ref<HTMLElement | null>(null);
const hoveredLine = ref<number | null>(null);

function hasComment(line: number): boolean {
  return props.comments.some((c) => c.line === line);
}
function commentText(line: number): string {
  return props.comments.find((c) => c.line === line)?.text ?? "";
}
function commentIdFor(line: number): string | null {
  return props.comments.find((c) => c.line === line)?.id ?? null;
}

function onMouseMove(e: MouseEvent): void {
  if (!codeContentRef.value) return;
  const lineEls = codeContentRef.value.querySelectorAll<HTMLElement>(".line");
  for (let i = 0; i < lineEls.length; i++) {
    const rect = lineEls[i].getBoundingClientRect();
    if (rect.bottom > e.clientY) {
      hoveredLine.value = i + 1;
      return;
    }
  }
  hoveredLine.value = lineEls.length || null;
}
</script>

<template>
  <div class="code-view" :class="{ dark: isDark }">
    <div class="code-gutter">
      <div
        v-for="line in lineCount"
        :key="line"
        class="gutter-cell"
      >
        <button
          v-if="line === hoveredLine && !hasComment(line)"
          class="gutter-add-btn"
          :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.addButtonAria', { line })"
          @click="emit('request-add', line)"
        >+</button>
        <button
          v-else-if="hasComment(line)"
          class="gutter-comment-indicator"
          :title="commentText(line)"
          :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.indicatorAria', { line, preview: commentText(line) })"
          @click="emit('request-edit', commentIdFor(line) ?? '')"
        >
          <v-icon size="12">mdi-comment-text-outline</v-icon>
        </button>
      </div>
    </div>
    <div class="line-numbers">
      <div
        v-for="line in lineCount"
        :key="line"
        class="line-number-cell"
      >{{ line }}</div>
    </div>
    <pre
      ref="codeContentRef"
      class="code-content"
      v-html="highlightedHtml"
      @mousemove="onMouseMove"
    />
  </div>
</template>

<style scoped>
.code-view {
  flex: 1;
  display: grid;
  grid-template-columns: 24px auto 1fr;
  min-height: 0;
  overflow: auto;
  background: transparent;
}
.code-gutter,
.line-numbers {
  display: flex;
  flex-direction: column;
}
.gutter-cell,
.line-number-cell {
  min-height: 1.55em;       /* matches .code-content font-size 12.5px * 1.55 */
  display: flex;
  align-items: center;
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
  line-height: 1.55;
}
.gutter-add-btn {
  opacity: 0;
  width: 20px;
  height: 20px;
  background: transparent;
  border: 1px solid rgba(var(--v-theme-primary), 0.4);
  border-radius: 4px;
  cursor: pointer;
  color: rgb(var(--v-theme-primary));
  margin: 0 auto;
  font-size: 12px;
  line-height: 1;
}
.gutter-cell:hover .gutter-add-btn,
.gutter-add-btn:focus {
  opacity: 1;
}
.gutter-comment-indicator {
  width: 20px;
  height: 20px;
  background: rgba(var(--v-theme-warning), 0.15);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: rgb(var(--v-theme-warning));
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: center;
}
.line-number-cell {
  padding-right: 8px;
  justify-content: flex-end;
  color: rgba(var(--v-theme-on-surface), 0.4);
  font-variant-numeric: tabular-nums;
  user-select: none;
}
.code-content {
  margin: 0;
  padding: 0 14px;
  background: transparent !important;
  font-family: ui-monospace, monospace;
  font-size: 12.5px;
  line-height: 1.55;
}
.code-content :deep(.line) {
  display: block;
  min-height: 1.55em;
}
@media (max-width: 760px) {
  .code-view {
    grid-template-columns: 16px auto 1fr;
  }
  .gutter-add-btn,
  .gutter-comment-indicator {
    opacity: 1 !important;  /* always visible on mobile (no hover) */
    width: 14px;
    height: 14px;
  }
}
</style>
```

- [ ] **Step 2: Run typecheck**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -30`
Expected: exits 0. (`tm()` does NOT fail typecheck on missing keys; missing i18n keys are a runtime concern that shows the raw key to the user. Chunk 4 adds the keys so the runtime fallback doesn't trigger.)

### Task 2.2: Scaffold `FileCommentEditor.vue`

**Files:**
- Create: `dashboard/src/components/chat/message_list_comps/FileCommentEditor.vue`

- [ ] **Step 1: Write the file**

```vue
<!-- Author: elecvoid243, 2026-06-21
     Spec: docs/superpowers/specs/2026-06-21-file-browser-inline-comments-design.md §4.3 -->
<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  line: number | null;
  commentId: string | null;
  initialText: string;
  lineContent: string | null;
  contextBefore: string | null;
  contextAfter: string | null;
  filePath: string;
}>();

const emit = defineEmits<{
  (e: "save", payload: { text: string; commentId: string | null; line: number }): void;
  (e: "cancel"): void;
  (e: "delete", commentId: string): void;
}>();

const { tm } = useModuleI18n("features/chat");

const text = ref<string>("");
const textareaRef = ref<HTMLTextAreaElement | null>(null);

watch(
  () => [props.line, props.initialText] as const,
  ([newLine, newText]) => {
    text.value = newText;
    if (newLine !== null) {
      nextTick(() => textareaRef.value?.focus());
    }
  },
  { immediate: true },
);

function handleKeyDown(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    e.preventDefault();
    emit("cancel");
  } else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    if (text.value.trim() && props.line !== null) {
      emit("save", { text: text.value.trim(), commentId: props.commentId, line: props.line });
    }
  }
}
</script>

<template>
  <div
    v-if="line !== null"
    class="comment-editor"
    @keydown="handleKeyDown"
  >
    <div class="comment-editor-header">
      <v-icon size="14">mdi-comment-text-outline</v-icon>
      <span class="editor-title">
        {{ commentId
          ? tm("spcodeProjectLoad.fileBrowser.comment.editTitle", { line })
          : tm("spcodeProjectLoad.fileBrowser.comment.newTitle", { line }) }}
      </span>
      <span class="editor-context">
        <code v-if="contextBefore">{{ contextBefore }}</code>
        <code v-if="lineContent" class="commented-line">{{ lineContent }}</code>
        <code v-if="contextAfter">{{ contextAfter }}</code>
      </span>
    </div>
    <textarea
      ref="textareaRef"
      v-model="text"
      class="comment-editor-input"
      rows="3"
      :placeholder="tm('spcodeProjectLoad.fileBrowser.comment.placeholder')"
    />
    <div class="comment-editor-actions">
      <v-btn
        v-if="commentId"
        size="small"
        color="error"
        variant="text"
        @click="emit('delete', commentId)"
      >
        {{ tm("spcodeProjectLoad.fileBrowser.comment.delete") }}
      </v-btn>
      <v-spacer />
      <v-btn size="small" variant="text" @click="emit('cancel')">
        {{ tm("spcodeProjectLoad.fileBrowser.comment.cancel") }}
      </v-btn>
      <v-btn
        size="small"
        color="primary"
        variant="flat"
        :disabled="!text.trim()"
        @click="emit('save', { text: text.trim(), commentId, line })"
      >
        {{ tm("spcodeProjectLoad.fileBrowser.comment.save") }}
      </v-btn>
    </div>
  </div>
</template>

<style scoped>
.comment-editor {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  padding: 10px 14px;
  background: rgba(var(--v-theme-surface), 0.6);
  flex-shrink: 0;
}
.comment-editor-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
}
.editor-title {
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.8);
}
.editor-context {
  display: flex;
  gap: 6px;
  font-family: ui-monospace, monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.commented-line {
  color: rgba(var(--v-theme-on-surface), 0.85);
  background: rgba(var(--v-theme-warning), 0.1);
  padding: 0 4px;
  border-radius: 2px;
}
.comment-editor-input {
  width: 100%;
  resize: vertical;
  font-family: inherit;
  font-size: 13px;
  padding: 8px;
  border-radius: 4px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.2);
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  box-sizing: border-box;
}
.comment-editor-input:focus {
  outline: none;
  border-color: rgb(var(--v-theme-primary));
}
.comment-editor-actions {
  display: flex;
  align-items: center;
  margin-top: 8px;
  gap: 4px;
}
.file-browser-preview.is-mobile :deep(.comment-editor) {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgb(var(--v-theme-surface));
  display: flex;
  flex-direction: column;
}
.file-browser-preview.is-mobile :deep(.comment-editor-input) {
  flex: 1;
  resize: none;
}
</style>
```

- [ ] **Step 2: Run typecheck**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -30`
Expected: exits 0. (Same caveat as Task 2.1: `tm()` is runtime, not typecheck. Chunk 4 adds the keys.)

### Task 2.3: Chunk 2 commit (single commit covering both components)

**Files:**
- Both new files from Tasks 2.1 and 2.2

- [ ] **Step 1: Add both files to a single commit**

```bash
git add dashboard/src/components/chat/message_list_comps/FileBrowserCodeView.vue \
        dashboard/src/components/chat/message_list_comps/FileCommentEditor.vue
git commit -m "feat(comments): add FileBrowserCodeView (line numbers + gutter + hover) and FileCommentEditor (bottom-anchored panel)

FileBrowserCodeView renders a 3-column grid (gutter | line numbers |
code). Hover any line shows a + button in the gutter; lines with
existing comments show a comment indicator. Comment indicators route
to the request-edit emit. Shiki output is dropped into the right
column unchanged; Shiki's <span class=\"line\"> wrappers are CSS'd
to display:block so each line aligns with the gutter / line-number
columns. Hover line is detected via getBoundingClientRect() per
mousemove (O(N) per event; < 5ms for typical files).

FileCommentEditor is a bottom-anchored panel that mounts only when
props.line !== null. Watch on (line, initialText) syncs the
textarea state when the parent opens the editor. Esc cancels,
Cmd/Ctrl+Enter saves. On mobile (< 760px), the parent adds an
is-mobile class to .file-browser-preview; the scoped CSS rules
promote the editor to a fullscreen overlay (see spec §6.1).

Both components use the full i18n path
'spcodeProjectLoad.fileBrowser.comment.*' — useModuleI18n only
injects 'features.chat.', so the nested namespace must be explicit."
```

### Task 2.4: Chunk 2 completion checklist

- [ ] All Tasks 2.1–2.3 done
- [ ] Both components saved + 1 commit added
- [ ] (Acceptance: i18n keys still missing at this point; Chunk 4 adds them)

---

## Chunk 3: Integrate into `FileBrowserFilePreview.vue`

**Spec ref:** §4.4.

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`

### Task 3.1: Add the inject, watch, and editor state (no template changes yet)

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`

- [ ] **Step 1: Read the current `FileBrowserFilePreview.vue` to find the import block and the script setup**

Run: `codegraph_explore` with query `FileBrowserFilePreview script setup imports state` OR open the file and locate the `<script setup>` block.

- [ ] **Step 2: Add the new imports and `fileComments` inject near the top of `<script setup>`**

Merge into the existing `import { ... } from "vue";` line by adding `inject` to the existing import set (the file already imports `ref` from "vue"). Add new imports for the composable + Vuetify display helper:

```typescript
import { useDisplay } from "vuetify";
import {
  FILE_COMMENTS_KEY,
  extractLineContext,
  type LineContext,
} from "@/composables/useFileComments";
```

(If the existing `"vue"` import doesn't already include `inject`, also add it there — the plan's intent is to AVOID a second import-from-vue line that would trigger `import/no-duplicates` lint errors.)

After the existing `defineProps` / `defineEmits` / `useModuleI18n` lines, add:

```typescript
const fileComments = inject(FILE_COMMENTS_KEY);
if (!fileComments) {
  throw new Error(
    "FileBrowserFilePreview: FILE_COMMENTS_KEY not provided. " +
      "FileBrowserFilePreview must be rendered inside StandaloneChat.",
  );
}

const activeEditLine = ref<number | null>(null);
const activeEditCommentId = ref<string | null>(null);
const editorInitialText = ref<string>("");
const editorContext = ref<LineContext | null>(null);
const snackbar = ref<{ visible: boolean; text: string }>({
  visible: false,
  text: "",
});

const { width } = useDisplay();
const isMobile = computed(() => width.value < 760);
```

- [ ] **Step 3: Add the invariant watch + handler functions at the end of `<script setup>`, just before the closing `</script>` tag (not interleaved with existing code)**

```typescript
function currentFilePath(): string | null {
  return props.state.kind === "file" ? props.state.snapshot.meta.path : null;
}
function currentFileContent(): string | null {
  return props.state.kind === "file" ? props.state.snapshot.content : null;
}

/** INVARIANT: this watch is the ONLY point that writes to
 *  fileComments.contentCache. Both `onRequestAdd` (via extractLineContext
 *  on state.snapshot.content) and `addComment` (via contentCache)
 *  read the same value, so they MUST stay in sync — a stale
 *  preview would show context that doesn't match what the comment
 *  will actually store. */
watch(
  () => currentFileContent(),
  (content) => {
    const path = currentFilePath();
    if (path && content !== null) {
      fileComments.registerFileContent(path, content);
    }
  },
  { immediate: true },
);

function onRequestAdd(line: number): void {
  const path = currentFilePath();
  const content = currentFileContent();
  if (!path || content === null) return;
  activeEditLine.value = line;
  activeEditCommentId.value = null;
  editorInitialText.value = "";
  editorContext.value = extractLineContext(content, line);
}

function onRequestEdit(commentId: string): void {
  const existing = fileComments.findCommentById(commentId);
  if (!existing) return;
  activeEditLine.value = existing.line;
  activeEditCommentId.value = existing.id;
  editorInitialText.value = existing.text;
  editorContext.value = {
    lineContent: existing.lineContent,
    contextBefore: existing.contextBefore,
    contextAfter: existing.contextAfter,
  };
}

function onSaveComment(payload: {
  text: string;
  commentId: string | null;
  line: number;
}): void {
  if (payload.commentId) {
    fileComments.updateComment(payload.commentId, payload.text);
    closeEditor();
    return;
  }
  const path = currentFilePath();
  if (!path) return;
  const created = fileComments.addComment({
    filePath: path,
    line: payload.line,
    text: payload.text,
  });
  if (created === null) {
    snackbar.value = {
      visible: true,
      text: tm("spcodeProjectLoad.fileBrowser.comment.saveError"),
    };
    return;
  }
  closeEditor();
}

function closeEditor(): void {
  activeEditLine.value = null;
  activeEditCommentId.value = null;
  editorContext.value = null;
}

function onDeleteComment(commentId: string): void {
  fileComments.deleteComment(commentId);
  closeEditor();
}
```

- [ ] **Step 4: Verify typecheck (expect: missing i18n key for saveError, otherwise clean)**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -30`
Expected: exits 0. (`tm("saveError")` is a runtime concern; Chunk 4 adds the key.)

### Task 3.2: Replace `<pre v-html="highlightedHtml" />` with `<FileBrowserCodeView>` + mount `<FileCommentEditor>` + add snackbar

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`

- [ ] **Step 1: Find the existing `<pre v-html="highlightedHtml" />` (or equivalent) inside the `state.kind === 'file'` branch**

- [ ] **Step 2: Replace that `<pre>` with the new components**

Find (the existing pre):
```html
<pre v-else class="preview-file-content" v-html="highlightedHtml" />
```

Replace with:
```html
<FileBrowserCodeView
  v-else
  :highlighted-html="highlightedHtml"
  :file-path="state.snapshot.meta.path"
  :comments="fileComments.commentsForFile(state.snapshot.meta.path)"
  :active-edit-line="activeEditLine"
  :active-edit-comment-id="activeEditCommentId"
  :is-dark="isDark"
  @request-add="onRequestAdd"
  @request-edit="onRequestEdit"
/>
<FileCommentEditor
  v-if="activeEditLine !== null"
  :line="activeEditLine"
  :comment-id="activeEditCommentId"
  :initial-text="editorInitialText"
  :line-content="editorContext?.lineContent ?? null"
  :context-before="editorContext?.contextBefore ?? null"
  :context-after="editorContext?.contextAfter ?? null"
  :file-path="state.snapshot.meta.path"
  @save="onSaveComment"
  @cancel="closeEditor"
  @delete="onDeleteComment"
/>
```

- [ ] **Step 3: Add the import for the two new components (top of `<script setup>`)**

```typescript
import FileBrowserCodeView from "./FileBrowserCodeView.vue";
import FileCommentEditor from "./FileCommentEditor.vue";
```

- [ ] **Step 4: Add the `.is-mobile` class binding to the root `<div class="file-browser-preview">`**

Find the root div and add the binding:
```html
<div class="file-browser-preview" :class="{ 'is-mobile': isMobile }">
```

- [ ] **Step 5: Add a `<v-snackbar>` at the end of the root `<div class="file-browser-preview">` (after the closing `</div>` of the `state.kind === 'file'` branch, but still inside the root div)**

```html
<v-snackbar
  v-model="snackbar.visible"
  :timeout="4000"
  color="error"
  location="bottom"
>
  {{ snackbar.text }}
</v-snackbar>
```

- [ ] **Step 6: Run typecheck**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -30`
Expected: exits 0. (i18n saveError key is a runtime concern; Chunk 4 adds it.)

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue
git commit -m "feat(comments): integrate CodeView + Editor + snackbar into FileBrowserFilePreview

Replaces the inline <pre v-html=\"highlightedHtml\" /> with
<FileBrowserCodeView>, which renders the line numbers + hover
gutter + Shiki code in a 3-column grid. The new
<FileCommentEditor> mounts below when activeEditLine is non-null,
showing the commented line's frozen content + ±1 context.

Editor state lives locally in this component (activeEditLine,
activeEditCommentId, editorContext, snackbar). The invariant watch
on currentFileContent() is the only writer to fileComments.contentCache;
both onRequestAdd (editor preview) and addComment (snapshot freeze)
read the same value via extractLineContext.

When addComment returns null (cache empty — invariant broken), the
user sees a snackbar instead of silent failure. The editor stays
open so the user can retry after the file re-loads.

On viewports < 760px, the root .file-browser-preview gets an
is-mobile class, which triggers the .comment-editor fullscreen
overlay per spec §6.1."
```

### Task 3.3: Chunk 3 completion checklist

- [ ] All Tasks 3.1–3.2 done
- [ ] `pnpm typecheck` exits 0 (or only fails on i18n saveError key)
- [ ] 1 commit added: integration

---

## Chunk 4: `StandaloneChat` provide + sendCurrentMessage + `ChatInput` chip + i18n

**Spec ref:** §4.5, §4.6, §7.

**Files:**
- Modify: `dashboard/src/components/chat/StandaloneChat.vue`
- Modify: `dashboard/src/components/chat/ChatInput.vue`
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

### Task 4.1: Wire up `useFileComments` + provide + resetForSession in `StandaloneChat`

**Files:**
- Modify: `dashboard/src/components/chat/StandaloneChat.vue`

- [ ] **Step 1: Find the existing `provide` calls and `sendCurrentMessage` in `StandaloneChat.vue`**

- [ ] **Step 2: Add the import for the composable (top of file)**

```typescript
import { useFileComments, FILE_COMMENTS_KEY } from "@/composables/useFileComments";
```

- [ ] **Step 3: Create the store and provide it (after existing composable instantiations)**

```typescript
const fileComments = useFileComments();
provide(FILE_COMMENTS_KEY, fileComments);

// Reset comments on session change (see spec §4.1 resetForSession —
// wipes comments bucket, keeps contentCache).
watch(currSessionId, (newId, oldId) => {
  if (oldId && newId !== oldId) {
    fileComments.resetForSession();
  }
});
```

- [ ] **Step 4: Modify `sendCurrentMessage` to attach formatted comments to the user message**

Find:
```typescript
async function sendCurrentMessage() {
  if (!draft.value.trim() && !stagedFiles.value.length) return;
  const sessionId = await ensureSession();
  const userText = draft.value.trim();
  const parts = buildOutgoingParts(userText);
  // ...
}
```

Replace the guard + first lines with:
```typescript
async function sendCurrentMessage() {
  if (
    !draft.value.trim() &&
    !stagedFiles.value.length &&
    fileComments.totalCount.value === 0
  ) return;
  const sessionId = await ensureSession();
  const userText = draft.value.trim();
  const commentText = fileComments.formatForLLM();
  const fullText = [userText, commentText].filter(Boolean).join("\n\n");
  const parts = buildOutgoingParts(fullText);
  // ... rest unchanged (sendMessage, clear draft, etc.)
}
```

- [ ] **Step 5: Pass `commentCount` to `ChatInput`**

Find the `<ChatInput ...>` tag in the template and add `:comment-count="fileComments.totalCount.value"`. (The `.value` is needed because `totalCount` is a `ComputedRef<number>`.)

- [ ] **Step 6: Run typecheck**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -30`
Expected: exits 0. (i18n keys are runtime; Task 4.3 adds them.)

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/components/chat/StandaloneChat.vue
git commit -m "feat(comments): wire useFileComments into StandaloneChat (provide + reset + send attach)

Imports useFileComments + FILE_COMMENTS_KEY from the composable,
creates a store with useFileComments(), and provides it under
FILE_COMMENTS_KEY. FileBrowserFilePreview (Chunk 3) injects under
the same key.

The currSessionId watcher calls resetForSession() (no args) when
the active session changes; this wipes the comments bucket but
keeps contentCache (auto-rebuilt by the immediate watch on next
file open).

sendCurrentMessage now constructs fullText = userText + formatForLLM()
joined by \\n\\n when comments exist. The new guard
(allow send if totalCount > 0 even with empty draft) implements
decision D13 — users can accumulate multiple comments and send
without typing additional text."
```

### Task 4.2: Add `commentCount` prop + chip in `ChatInput.vue`

**Files:**
- Modify: `dashboard/src/components/chat/ChatInput.vue`

- [ ] **Step 1: Add the prop to `defineProps<{...}>()`**

Add `commentCount: number;` to the existing prop type.

- [ ] **Step 2: Add the chip inside `input-area__status-row__right`, after `GitDiffChip`**

Find the `<div class="input-area__status-row__right">` block and append (after the existing `<GitDiffChip>`):

```html
<v-chip
  v-if="commentCount > 0"
  size="x-small"
  variant="tonal"
  color="primary"
  class="comment-count-chip"
  prepend-icon="mdi-comment-text-outline"
  :title="tm('spcodeProjectLoad.fileBrowser.comment.countTooltip')"
>
  {{ tm("spcodeProjectLoad.fileBrowser.comment.countLabel", { count: commentCount }) }}
</v-chip>
```

- [ ] **Step 3: Hide the chip on mobile (per spec §6.1)**

Wrap the chip in a hidden-on-mobile guard. Add a class:
```html
<v-chip ... class="comment-count-chip d-none d-md-flex">
```

(`d-none d-md-flex` is a Vuetify utility class; `d-md-flex` overrides on ≥ medium breakpoints. Alternatively, use `v-if="!isMobile"` and pass `isMobile` from parent — but the existing code in this file doesn't track viewport, so the CSS class is the lightest approach.)

- [ ] **Step 4: Run typecheck**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -30`
Expected: exits 0. (i18n keys are runtime; Task 4.3 adds them.)

### Task 4.3: Add the i18n keys to all three locales

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

- [ ] **Step 1: Locate the `spcodeProjectLoad.fileBrowser` key in `zh-CN/features/chat.json`**

Use your editor's "Go to symbol" or search for `"fileBrowser"`. Look for the existing `"preview": { ... }` block as a sibling.

- [ ] **Step 2: Add the `comment` block (zh-CN)**

After `"preview": { ... }`, add:

```json
"comment": {
  "addButton": "添加评论",
  "addButtonAria": "在第 {line} 行添加评论",
  "newTitle": "对第 {line} 行发布评论",
  "editTitle": "编辑第 {line} 行的评论",
  "placeholder": "写下你的评论...",
  "save": "保存",
  "cancel": "取消",
  "delete": "删除",
  "saveError": "评论保存失败,请刷新文件后重试",
  "indicatorAria": "第 {line} 行的评论: {preview}",
  "countLabel": "{count} 个评论",
  "countTooltip": "下次发送时会带上这些评论"
}
```

(Place it with the correct JSON comma / nesting. The exact insertion depends on the existing file structure — read the surrounding JSON to maintain validity.)

- [ ] **Step 3: Add the same block to `en-US/features/chat.json`**

```json
"comment": {
  "addButton": "Add comment",
  "addButtonAria": "Add comment on line {line}",
  "newTitle": "Comment on line {line}",
  "editTitle": "Edit comment on line {line}",
  "placeholder": "Write your comment...",
  "save": "Save",
  "cancel": "Cancel",
  "delete": "Delete",
  "saveError": "Failed to save comment. Please reopen the file and retry.",
  "indicatorAria": "Comment on line {line}: {preview}",
  "countLabel": "{count} comments",
  "countTooltip": "These will be included with your next message"
}
```

- [ ] **Step 4: Add the same block to `ru-RU/features/chat.json`**

```json
"comment": {
  "addButton": "Добавить комментарий",
  "addButtonAria": "Добавить комментарий к строке {line}",
  "newTitle": "Комментарий к строке {line}",
  "editTitle": "Редактировать комментарий к строке {line}",
  "placeholder": "Напишите ваш комментарий...",
  "save": "Сохранить",
  "cancel": "Отмена",
  "delete": "Удалить",
  "saveError": "Не удалось сохранить комментарий. Обновите файл и повторите.",
  "indicatorAria": "Комментарий к строке {line}: {preview}",
  "countLabel": "{count} комментариев",
  "countTooltip": "Будут добавлены к следующему сообщению"
}
```

- [ ] **Step 5: Validate all three JSON files parse**

Run:
```bash
node -e "JSON.parse(require('fs').readFileSync('dashboard/src/i18n/locales/zh-CN/features/chat.json', 'utf8'))" && echo "zh-CN OK"
node -e "JSON.parse(require('fs').readFileSync('dashboard/src/i18n/locales/en-US/features/chat.json', 'utf8'))" && echo "en-US OK"
node -e "JSON.parse(require('fs').readFileSync('dashboard/src/i18n/locales/ru-RU/features/chat.json', 'utf8'))" && echo "ru-RU OK"
```
Expected: all three print "OK".

- [ ] **Step 6: Run typecheck (now everything should compile)**

Run: `cd dashboard && pnpm typecheck 2>&1 | tail -30`
Expected: exits 0.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/i18n/locales/zh-CN/features/chat.json \
        dashboard/src/i18n/locales/en-US/features/chat.json \
        dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "feat(comments): add spcodeProjectLoad.fileBrowser.comment.* i18n keys (3 locales)

Adds 12 keys each to zh-CN, en-US, and ru-RU chat.json:

  addButton, addButtonAria, newTitle, editTitle, placeholder,
  save, cancel, delete, saveError, indicatorAria, countLabel,
  countTooltip

All keys use simple {var} interpolation; no plurals needed since
{count} is rendered via Vuetify's v-chip text. The saveError key
is shown in the snackbar when addComment returns null (per spec
§4.1 null-return + spec §4.4 'don't close editor' UX)."
```

### Task 4.4: Verify the `commentCount` prop binding in `StandaloneChat` template

- [ ] **Step 1: Verify the `ChatInput` invocation in `StandaloneChat.vue` includes `:comment-count`**

This was already added in Task 4.1 Step 5. If you skipped it then, add it now.

- [ ] **Step 2: If you had to add the binding, amend the Task 4.1 commit (do NOT create a new commit)**

```bash
git add dashboard/src/components/chat/StandaloneChat.vue
git commit --amend --no-edit
```

This keeps the chunk's commit count at exactly 3 as the Task 4.5 checklist promises.

### Task 4.5: Chunk 4 completion checklist

- [ ] All Tasks 4.1–4.4 done
- [ ] `pnpm typecheck` exits 0
- [ ] 3 commits added: StandaloneChat wiring / ChatInput chip / i18n keys

---

## Final Verification (end-to-end)

After all 4 chunks complete, perform these manual end-to-end checks from the dashboard dev server:

```bash
cd dashboard
pnpm dev    # runs on http://localhost:3000
```

Then execute spec §8.3 manual checklist:
- #1: Files view shows file content with line numbers, gutter empty by default
- #2: Hover a line shows "+" button in the gutter
- #3: Click "+" opens the editor with "对第 N 行发布评论" + context lines
- #4: Save a comment → gutter shows comment icon, "1 个评论" chip appears
- #5: Switch to another file, switch back → comment is preserved (per filePath)
- #6: Switch chat session → comments cleared
- #7: Send a message with comments attached → LLM receives "[File review comments] ..." block
- #8: External file edit + page refresh → comments lost (not persisted, per D2)
- #9: 2 comments on adjacent lines (≤3 apart) → merged into one output block
- #10: 2 comments on far-apart lines → separate output blocks
- #11: Delete a comment via the editor's "删除" button → gutter icon disappears, chip count -1
- #12: Binary file → no gutter, no editor entry
- #13: > 5MB file → "too large" hint, no gutter
- #14: Keyboard focus on "+" button → button visible (opacity 1)
- #15: Send with only comments, no text → still sends, message contains only the comments block
- #16: External file refresh while comment exists → editor opens with frozen snapshot
- #17: Force `addComment` to return null (e.g. via dev console) → snackbar appears, editor stays open

## Acceptance Criteria

The plan is complete when:
- [ ] All 4 chunks committed
- [ ] `pnpm typecheck` exits 0 from `dashboard/`
- [ ] All 17 manual end-to-end checks from spec §8.3 pass
- [ ] Spec §6 risk #1 (Shiki structure) verified by visual inspection of rendered code

---
