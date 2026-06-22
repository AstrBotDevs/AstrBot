# Comments Preview Dialog Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing "N comments" chip in `ChatInput` so the chip body opens a v-dialog previewing all comments grouped by file, with per-comment delete; add a chip-top-right ✕ button that clears all comments behind a confirm dialog.

**Architecture:**
- Strip the `commentCount` prop from `ChatInput`; let it import the module-level `useFileComments()` singleton directly (same store as `FileBrowserFilePreview`).
- Two new focused components: `CommentsPreviewDialog.vue` (presentational, props+emit) and `ConfirmDialog.vue` (generic confirm).
- `useFileComments()` gains `commentsByFile()` (grouped) and `clearAll()`.

**Tech Stack:** Vue 3 + `<script setup lang="ts">` + Vuetify 3 (`v-dialog`, `v-card`, `v-btn`, `v-icon`) + Pinia-less composable singleton.

**Spec:** `docs/superpowers/specs/2026-06-22-comments-preview-dialog-design.md`

---

## File Structure

| File | Responsibility | Type |
|------|----------------|------|
| `dashboard/src/composables/useFileComments.ts` | Add `commentsByFile()` + `clearAll()` | Modify |
| `dashboard/src/components/chat/ConfirmDialog.vue` | Generic two-button confirm dialog (title/message + confirm/cancel slots+props) | Create |
| `dashboard/src/components/chat/CommentsPreviewDialog.vue` | Comment preview modal, grouped by file, with delete emits | Create |
| `dashboard/src/components/chat/ChatInput.vue` | Replace `<v-chip>` with custom container; add dialogs; consume `useFileComments` directly; remove `commentCount` prop | Modify |
| `dashboard/src/components/chat/Chat.vue` | Remove 2× `:comment-count="fileComments.totalCount.value"` (lines 323, 473) | Modify |
| `dashboard/src/components/chat/StandaloneChat.vue` | Remove 1× `:comment-count="fileComments.totalCount.value"` (line 154) | Modify |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | Add 12 new keys | Modify |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | Add 12 new keys | Modify |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | Add 12 new keys (translations follow v1 patterns) | Modify |

Note: spec §5.4 lists 11 keys; this plan ships 12 because the per-comment ✕ button in the preview dialog needs its own `aria-label` (`previewDialog.deleteButton`) per spec §6.3.

Each file has one clear responsibility. The two new Vue components are < 150 lines each. `ChatInput.vue` will grow by ~80 lines (chip container CSS + 2 dialog instances + 1 composable import); still well under the ~600 line threshold.

---

## Chunk 1: Foundation (composable + generic dialog + i18n)

### Task 1: Add `commentsByFile()` and `clearAll()` to `useFileComments`

**Files:**
- Modify: `dashboard/src/composables/useFileComments.ts`

- [ ] **Step 1: Read existing methods for style consistency**

Read `useFileComments.ts` lines 100–210 to confirm the existing function shape (parameter style, JSDoc style, return shape). Pattern: arrow functions inside `createFileComments`, exported via the `useFileComments()` factory.

- [ ] **Step 2: Add `commentsByFile()` after `commentsForFile()`**

Insert immediately after the existing `commentsForFile` function (around line 175). Both methods are pure projections of the reactive `comments` dict.

```ts
/**
 * All comments grouped by filePath, with each group sorted by line ASC.
 * Groups themselves are sorted by filePath ASC for stable rendering.
 * Returns a fresh array each call (safe to iterate / sort downstream).
 */
function commentsByFile(): Array<{ filePath: string; comments: FileComment[] }> {
  const entries = Object.entries(comments)
    .filter(([, list]) => list.length > 0)
    .map(([filePath, list]) => ({
      filePath,
      comments: [...list].sort((a, b) => a.line - b.line),
    }));
  entries.sort((a, b) => a.filePath.localeCompare(b.filePath));
  return entries;
}
```

- [ ] **Step 3: Add `clearAll()` after `commentsByFile()`**

Insert immediately after the new `commentsByFile` function.

```ts
/**
 * Delete every comment across all files. Idempotent. Does not
 * touch contentCache (content survives session switches).
 */
function clearAll(): void {
  for (const k of Object.keys(comments)) delete comments[k];
}
```

- [ ] **Step 4: Run ruff format + check**

Run: `cd dashboard && pnpm lint` (or `npx eslint src/composables/useFileComments.ts`)
Expected: 0 errors. New code follows existing style (4-space indent, arrow functions, JSDoc).

- [ ] **Step 5: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/composables/useFileComments.ts
git commit -m "feat(comments): add commentsByFile and clearAll to useFileComments"
```

### Task 2: Create `ConfirmDialog.vue` (generic confirm modal)

**Files:**
- Create: `dashboard/src/components/chat/ConfirmDialog.vue`

- [ ] **Step 1: Create file with header comment + script setup**

Path: `dashboard/src/components/chat/ConfirmDialog.vue`

```vue
<!-- Author: elecvoid243, 2026-06-22
     Generic two-button confirmation dialog. Used by ChatInput's
     "clear all comments" flow. Follows v-model pattern. -->
<script setup lang="ts">
defineProps<{
  modelValue: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  confirmColor?: string;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "confirm"): void;
  (e: "cancel"): void;
}>();

function close(): void {
  emit("update:modelValue", false);
}
function onConfirm(): void {
  emit("confirm");
  close();
}
function onCancel(): void {
  emit("cancel");
  close();
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="420"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title>{{ title }}</v-card-title>
      <v-card-text>
        <p>{{ message }}</p>
        <slot name="extra" />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="onCancel">
          {{ cancelText ?? "Cancel" }}
        </v-btn>
        <v-btn
          :color="confirmColor ?? 'error'"
          variant="flat"
          @click="onConfirm"
        >
          {{ confirmText ?? "Confirm" }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
```

- [ ] **Step 2: Verify file compiles**

Run: `cd dashboard && pnpm tsc --noEmit`
Expected: no new errors. `defineProps` with optional fields and `defineEmits` with typed tuples are both well-supported.

- [ ] **Step 3: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/ConfirmDialog.vue
git commit -m "feat(chat): add ConfirmDialog generic confirmation component"
```

### Task 3: Add 11 new i18n keys (zh-CN / en-US / ru-RU)

**Files:**
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json` (under `spcodeProjectLoad.fileBrowser.comment.*`)
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json` (same path)
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json` (same path)

Note: spec §5.4 lists 11 keys; this task adds 12 (adds `previewDialog.deleteButton` per spec §6.3).

- [ ] **Step 1: Inspect existing chat.json for structure**

Run: `cd dashboard && grep -n "spcodeProjectLoad.fileBrowser.comment" src/i18n/locales/zh-CN/features/chat.json`

Expected: existing keys like `countLabel`, `countTooltip`, `addButtonAria`, `indicatorAria`. Confirm the JSON structure ends with `}}` at the bottom of the comment namespace.

- [ ] **Step 2: Add 11 new keys to zh-CN**

Open the file and locate the closing `}` of the `comment` object (one level inside `fileBrowser`). Insert these keys (preserve alphabetical ordering for grep-ability):

```json
"chip": {
  "clearAll": "清空全部评论"
},
"confirmClear": {
  "cancel": "取消",
  "confirm": "全部删除",
  "message": "将删除当前会话的全部 {count} 条评论，此操作不可撤销。",
  "title": "清空全部评论？"
},
"previewDialog": {
  "clearAllButton": "全部删除",
  "closeButton": "关闭",
  "deleteButton": "删除此评论",
  "empty": "暂无评论",
  "lineLabel": "L {line}",
  "openWithCount": "打开评论预览 ({count})",
  "title": "评论预览 ({count})"
}
```

These are children of `spcodeProjectLoad.fileBrowser.comment`. Final structure:
```json
"spcodeProjectLoad": {
  "fileBrowser": {
    "comment": {
      "addButtonAria": "...",
      "chip": { ... },
      "confirmClear": { ... },
      "countLabel": "...",
      "countTooltip": "...",
      "indicatorAria": "...",
      "previewDialog": { ... }
    }
  }
}
```

- [ ] **Step 3: Add same 11 keys to en-US**

Same structure, English translations:
```json
"chip": {
  "clearAll": "Clear all comments"
},
"confirmClear": {
  "cancel": "Cancel",
  "confirm": "Clear all",
  "message": "This will delete all {count} comments in the current session. This action cannot be undone.",
  "title": "Clear all comments?"
},
"previewDialog": {
  "clearAllButton": "Clear all",
  "closeButton": "Close",
  "deleteButton": "Delete this comment",
  "empty": "No comments yet",
  "lineLabel": "L {line}",
  "openWithCount": "Open comments preview ({count})",
  "title": "Comments preview ({count})"
}
```

- [ ] **Step 4: Add same 11 keys to ru-RU**

Translations follow v1 patterns. Reference existing v1 keys for tone. Use these:
```json
"chip": {
  "clearAll": "Очистить все комментарии"
},
"confirmClear": {
  "cancel": "Отмена",
  "confirm": "Очистить все",
  "message": "Будут удалены все {count} комментариев в текущей сессии. Это действие необратимо.",
  "title": "Очистить все комментарии?"
},
"previewDialog": {
  "clearAllButton": "Очистить все",
  "closeButton": "Закрыть",
  "deleteButton": "Удалить этот комментарий",
  "empty": "Комментариев пока нет",
  "lineLabel": "С {line}",
  "openWithCount": "Открыть просмотр комментариев ({count})",
  "title": "Просмотр комментариев ({count})"
}
```

- [ ] **Step 5: Validate JSON files**

Run: `cd dashboard && node -e "['zh-CN','en-US','ru-RU'].forEach(l=>{JSON.parse(require('fs').readFileSync('src/i18n/locales/'+l+'/features/chat.json','utf8'))})"`
Expected: no output (all three parse cleanly).

- [ ] **Step 6: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/i18n/locales/
git commit -m "feat(i18n): add 11 keys for comments preview dialog and chip clear button"
```

---

## Chunk 2: Preview dialog component + ChatInput refactor + parent cleanup

### Task 4: Create `CommentsPreviewDialog.vue`

**Files:**
- Create: `dashboard/src/components/chat/CommentsPreviewDialog.vue`

- [ ] **Step 1: Create file with the full content below**

Path: `dashboard/src/components/chat/CommentsPreviewDialog.vue`

```vue
<!-- Author: elecvoid243, 2026-06-22
     Read-only preview dialog for all file-review comments in the
     current session. Comments are grouped by file, sorted by line
     within each group. Per-comment delete (no confirm). Footer has
     "clear all" (parent handles confirm) + "close". Pure presentational;
     emits all mutations to the parent so the store stays a single source
     of truth (useFileComments). See spec §4.2. -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { FileComment } from "@/composables/useFileComments";

interface CommentGroup {
  filePath: string;
  comments: FileComment[];
}

const props = defineProps<{
  modelValue: boolean;
  groups: CommentGroup[];
}>();

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void;
  (e: "delete-comment", commentId: string): void;
  (e: "request-clear-all"): void;
}>();

const { tm } = useModuleI18n("features/chat");

const totalCount = computed<number>(() =>
  props.groups.reduce((n, g) => n + g.comments.length, 0),
);

function close(): void {
  emit("update:modelValue", false);
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="800"
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2">mdi-comment-text-outline</v-icon>
        {{ tm("spcodeProjectLoad.fileBrowser.comment.previewDialog.title", { count: totalCount }) }}
        <v-spacer />
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.previewDialog.closeButton')"
          @click="close"
        />
      </v-card-title>

      <v-card-text class="comments-preview-body">
        <div v-if="groups.length === 0" class="comments-preview-empty">
          {{ tm("spcodeProjectLoad.fileBrowser.comment.previewDialog.empty") }}
        </div>
        <section
          v-for="group in groups"
          :key="group.filePath"
          class="comments-preview-group"
        >
          <h3 class="comments-preview-file">{{ group.filePath }}</h3>
          <article
            v-for="c in group.comments"
            :key="c.id"
            class="comments-preview-item"
          >
            <header class="comments-preview-item-head">
              <span class="comments-preview-line">
                {{ tm("spcodeProjectLoad.fileBrowser.comment.previewDialog.lineLabel", { line: c.line }) }}
              </span>
              <code class="comments-preview-snippet">{{ c.lineContent }}</code>
              <v-spacer />
              <v-btn
                icon="mdi-close"
                variant="text"
                size="x-small"
                color="error"
                :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.previewDialog.deleteButton')"
                @click="emit('delete-comment', c.id)"
              />
            </header>
            <p class="comments-preview-text">{{ c.text }}</p>
          </article>
        </section>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn
          v-if="groups.length > 0"
          color="error"
          variant="text"
          prepend-icon="mdi-delete-sweep"
          @click="emit('request-clear-all')"
        >
          {{ tm("spcodeProjectLoad.fileBrowser.comment.previewDialog.clearAllButton") }}
        </v-btn>
        <v-btn variant="flat" @click="close">
          {{ tm("spcodeProjectLoad.fileBrowser.comment.previewDialog.closeButton") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.comments-preview-body {
  max-height: 60vh;
  padding-top: 8px;
}
.comments-preview-empty {
  text-align: center;
  color: rgba(var(--v-theme-on-surface), 0.5);
  padding: 48px 0;
}
.comments-preview-group + .comments-preview-group {
  margin-top: 16px;
}
.comments-preview-file {
  font-size: 12px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.65);
  margin: 0 0 6px;
  font-family: ui-monospace, monospace;
  word-break: break-all;
}
.comments-preview-item {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 6px;
  background: rgba(var(--v-theme-on-surface), 0.03);
}
.comments-preview-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.comments-preview-line {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.comments-preview-snippet {
  font-size: 12px;
  font-family: ui-monospace, monospace;
  background: rgba(var(--v-theme-on-surface), 0.06);
  padding: 1px 6px;
  border-radius: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.comments-preview-text {
  font-size: 13px;
  line-height: 1.45;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
```

- [ ] **Step 2: Verify the file compiles**

Run: `cd dashboard && pnpm tsc --noEmit`
Expected: 0 errors related to the new component.

- [ ] **Step 3: Verify ESLint passes**

Run: `cd dashboard && npx eslint src/components/chat/CommentsPreviewDialog.vue`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/CommentsPreviewDialog.vue
git commit -m "feat(chat): add CommentsPreviewDialog component"
```

### Task 5: Refactor `ChatInput.vue` (chip replacement + state + dialogs)

**Files:**
- Modify: `dashboard/src/components/chat/ChatInput.vue`

- [ ] **Step 1: Remove the `commentCount` prop from `defineProps` AND its default in `withDefaults`**

The file uses `withDefaults(defineProps<Props>(), { ... commentCount: 0, ... })` (around line 454). Remove both:
1. The `commentCount?: number` field from the `Props` interface (around line 444).
2. The `commentCount: 0` entry from the `withDefaults` defaults object (around line 454).

Also remove the corresponding JSDoc block above the field (the one explaining "Drives the 'N comments' chip").

- [ ] **Step 2: Add new imports and reactive state**

In the `<script setup>` block, add at the top (after existing imports):

```ts
import { computed, ref, watch } from "vue";
import { useFileComments } from "@/composables/useFileComments";
import CommentsPreviewDialog from "@/components/chat/CommentsPreviewDialog.vue";
import ConfirmDialog from "@/components/chat/ConfirmDialog.vue";
```

Note: `computed` may already be imported. Adjust if so.

Add state inside the setup body (after existing state declarations):

```ts
const fileComments = useFileComments();
const previewDialogOpen = ref(false);
const confirmClearOpen = ref(false);
const chipHovered = ref(false);

/** Auto-close preview/confirm dialogs when the last comment is gone,
 *  e.g. after clearAll() or session reset. */
watch(
  () => fileComments.totalCount.value,
  (n) => {
    if (n === 0) {
      previewDialogOpen.value = false;
      confirmClearOpen.value = false;
    }
  },
);

const previewGroups = computed(() => fileComments.commentsByFile());

function openPreview(): void {
  previewDialogOpen.value = true;
  chipHovered.value = false;
}

function onDeleteComment(id: string): void {
  fileComments.deleteComment(id);
}

function onConfirmClearAll(): void {
  fileComments.clearAll();
  confirmClearOpen.value = false;
}
```

- [ ] **Step 3: Replace the existing `<v-chip>` block (lines 40–52)**

Find the existing `<v-chip v-if="commentCount > 0" ...>...</v-chip>` block and replace it with:

```vue
<div
  v-if="fileComments.totalCount.value > 0"
  class="comment-count-chip d-none d-md-flex"
  :class="{ 'comment-count-chip--hovered': chipHovered }"
  @mouseenter="chipHovered = true"
  @mouseleave="chipHovered = false"
>
  <button
    type="button"
    class="comment-count-chip__main"
    :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.previewDialog.openWithCount', { count: fileComments.totalCount.value })"
    @click="openPreview"
  >
    <v-icon size="14" start>mdi-comment-text-outline</v-icon>
    {{ tm("spcodeProjectLoad.fileBrowser.comment.countLabel", { count: fileComments.totalCount.value }) }}
  </button>
  <button
    v-if="chipHovered"
    type="button"
    class="comment-count-chip__clear"
    :aria-label="tm('spcodeProjectLoad.fileBrowser.comment.chip.clearAll')"
    @click.stop="confirmClearOpen = true"
  >
    <v-icon size="14">mdi-close</v-icon>
  </button>
</div>
```

Note: The `v-if` is now on the outer `<div>`. Existing `d-none d-md-flex` class preserved (mobile hidden).

- [ ] **Step 4: Append dialog instances at the end of the template**

Find the closing `</template>` tag (search for `^</template>`). Just before it, insert:

```vue
<CommentsPreviewDialog
  v-model="previewDialogOpen"
  :groups="previewGroups"
  @delete-comment="onDeleteComment"
  @request-clear-all="confirmClearOpen = true"
/>
<ConfirmDialog
  v-model="confirmClearOpen"
  :title="tm('spcodeProjectLoad.fileBrowser.comment.confirmClear.title')"
  :message="tm('spcodeProjectLoad.fileBrowser.comment.confirmClear.message', { count: fileComments.totalCount.value })"
  :confirm-text="tm('spcodeProjectLoad.fileBrowser.comment.confirmClear.confirm')"
  :cancel-text="tm('spcodeProjectLoad.fileBrowser.comment.confirmClear.cancel')"
  confirm-color="error"
  @confirm="onConfirmClearAll"
/>
```

- [ ] **Step 5: Add chip container CSS to the `<style scoped>` block**

At the end of the existing `<style scoped>` block, append:

```css
.comment-count-chip {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 10px;
  border-radius: 12px;
  background: rgba(var(--v-theme-warning), 0.16);
  color: rgb(var(--v-theme-warning));
  font-size: 12px;
  line-height: 1;
}
.comment-count-chip__main {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: 0;
  padding: 0;
  margin: 0;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.comment-count-chip__main:hover,
.comment-count-chip__main:focus-visible {
  filter: brightness(1.1);
}
.comment-count-chip__clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: rgba(var(--v-theme-error), 0.85);
  color: rgb(var(--v-theme-on-error));
  border: 0;
  padding: 0;
  margin-left: 2px;
  cursor: pointer;
  opacity: 0.85;
  transition: opacity 0.12s, transform 0.12s;
}
.comment-count-chip__clear:hover {
  opacity: 1;
  transform: scale(1.08);
}
```

- [ ] **Step 6: Verify the file compiles and lints**

Run: `cd dashboard && pnpm tsc --noEmit && npx eslint src/components/chat/ChatInput.vue`
Expected: 0 errors. If unused-imports warning appears, remove unused imports.

- [ ] **Step 7: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/ChatInput.vue
git commit -m "feat(chat): make comment chip clickable with clear-all button"
```

### Task 6: Remove `:comment-count` bindings from `Chat.vue` and `StandaloneChat.vue`

**Files:**
- Modify: `dashboard/src/components/chat/Chat.vue` (lines 323, 473)
- Modify: `dashboard/src/components/chat/StandaloneChat.vue` (line 154)

- [ ] **Step 1: Remove line 323 from `Chat.vue`**

Locate `:comment-count="fileComments.totalCount.value"` at line 323 and delete that line.

- [ ] **Step 2: Remove line 473 from `Chat.vue`**

Locate `:comment-count="fileComments.totalCount.value"` at line 473 (now 472 after previous deletion) and delete that line.

- [ ] **Step 3: Remove line 154 from `StandaloneChat.vue`**

Locate `:comment-count="fileComments.totalCount.value"` at line 154 and delete that line.

- [ ] **Step 4: Verify no remaining `:comment-count` references**

Run: `cd dashboard && grep -rn "comment-count" src/`
Expected: no matches in `Chat.vue` / `StandaloneChat.vue` / `ChatInput.vue` (the prop is gone).

- [ ] **Step 5: Verify TypeScript and ESLint pass**

Run: `cd dashboard && pnpm tsc --noEmit`
Expected: 0 errors. The `fileComments` import in `Chat.vue` / `StandaloneChat.vue` is still used elsewhere (e.g., `formatForLLM()` calls) — do NOT remove the import.

- [ ] **Step 6: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/Chat.vue dashboard/src/components/chat/StandaloneChat.vue
git commit -m "refactor(chat): drop commentCount prop, ChatInput reads store directly"
```

### Task 7: Final verification — type-check, lint, build, manual smoke test

**Files:** none modified

- [ ] **Step 1: Full TypeScript check**

Run: `cd dashboard && pnpm tsc --noEmit`
Expected: 0 errors across the entire dashboard codebase.

- [ ] **Step 2: Full ESLint check**

Run: `cd dashboard && pnpm lint`
Expected: 0 errors.

- [ ] **Step 3: Build check**

Run: `cd dashboard && pnpm build`
Expected: build succeeds; new i18n keys surface in `dist/assets/*.json`.

- [ ] **Step 4: Manual smoke test (10 steps from spec §7.1)**

Open the chat page in a browser, then:
1. No comments → chip is hidden ✓
2. Add a comment via file browser → chip appears with "1 comments" ✓
3. Hover chip → red ✕ button fades in ✓
4. Click chip body → preview dialog opens with the comment ✓
5. Click chip ✕ → confirm dialog appears with "Clear all 1 comment?" ✓
6. Click Confirm → comments cleared, chip disappears, dialog auto-closes ✓
7. Click Cancel (re-test) → confirm dialog closes, comment preserved ✓
8. Add comments across 2 files → preview groups by file, sorted by line within each ✓
9. Click single ✕ in preview → that comment removed, dialog stays open ✓
10. Click "Clear all" in preview footer → same confirm dialog flow as chip ✕ ✓

- [ ] **Step 5: Switch to en-US locale and repeat steps 1–10**

In browser devtools / settings, switch to English. Verify all new strings render in English (no `[missing]` markers, no fallback to key path).

- [ ] **Step 6: Final commit (if any fix-ups)**

If smoke test surfaced any issue, fix it in a final commit. Otherwise skip this step.

```bash
cd F:\github\Astrbot
git status  # should be clean
```

---

## End of Plan

Plan complete and saved to `docs/superpowers/plans/2026-06-22-comments-preview-dialog.md`. Ready to execute.