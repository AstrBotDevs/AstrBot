# DiffPreview Fullscreen Mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fullscreen overlay mode to `DiffPreview.vue` so users can expand any diff view to the full browser viewport, with a back button + Escape to return.

**Architecture:** A `<Teleport to="body">` overlay renders a separate copy of the diff content (sharing the same reactive refs: `viewMode`, `parsedHunks`, `splitHunks`, `isCollapsed`, `collapsedHunks`). The overlay uses `position: fixed; inset: 0` to fill the viewport. A floating back button at top-right and a `@keydown.escape` listener on the overlay handle the exit path. Body scroll is locked while the overlay is open. The change is entirely inside `DiffPreview.vue` — none of the 5+ call sites need modification.

**Tech Stack:** Vue 3 (Composition API + Teleport), Vuetify 3 (v-icon, CSS variables), i18n (vue-i18n JSON files)

## Global Constraints

- No modifications to any DiffPreview call site (ToolCallCard, GitDiffFileItem, FilePatchPanel, FileDiffResult, ThemeAwareMarkdownCodeBlock)
- Fullscreen overlay MUST use `<Teleport to="body">` to escape fixed-position parents (GitDiffSidebar)
- State sharing: normal view and fullscreen overlay share same Vue reactive refs — no duplication of computed/parsed state
- All new icon buttons match existing `.diff-view-toggle-btn` dimensions (22×22px)
- Body scroll lock via `document.body.style.overflow` toggle
- i18n keys follow existing `diffPreview.viewMode` pattern under a new `diffPreview.fullscreen` block

---

### Task 1: Add i18n keys for fullscreen

**Files:**
- Modify: `dashboard/src/i18n/locales/en-US/features/chat.json`
- Modify: `dashboard/src/i18n/locales/zh-CN/features/chat.json`
- Modify: `dashboard/src/i18n/locales/ru-RU/features/chat.json`

**Interfaces:**
- Consumes: existing `diffPreview` block in each locale file
- Produces: `diffPreview.fullscreen.*` i18n keys for the dashboard

- [ ] **Step 1: Add fullscreen block to en-US chat.json**

Insert after `"diffPreview.viewMode"` block (line ~255):

```json
    "fullscreen": {
      "enter": "Fullscreen",
      "exit": "Exit fullscreen",
      "exitLabel": "Back",
      "ariaLabel": "Diff fullscreen view"
    }
```

Location (within `chat.json`):

```json
  "diffPreview": {
    "viewMode": {
      "label": "View mode",
      "unified": "Unified",
      "split": "Split",
      "ariaLabel": "Switch diff view mode"
    },
    // ↓ ADD THIS BLOCK ↓
    "fullscreen": {
      "enter": "Fullscreen",
      "exit": "Exit fullscreen",
      "exitLabel": "Back",
      "ariaLabel": "Diff fullscreen view"
    }
  },
```

- [ ] **Step 2: Add fullscreen block to zh-CN chat.json**

```json
    "fullscreen": {
      "enter": "全屏",
      "exit": "退出全屏",
      "exitLabel": "返回",
      "ariaLabel": "全屏显示差异"
    }
```

- [ ] **Step 3: Add fullscreen block to ru-RU chat.json**

```json
    "fullscreen": {
      "enter": "На весь экран",
      "exit": "Выйти из полноэкранного режима",
      "exitLabel": "Назад",
      "ariaLabel": "Полноэкранный просмотр diff"
    }
```

- [ ] **Step 4: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/i18n/locales/en-US/features/chat.json dashboard/src/i18n/locales/zh-CN/features/chat.json dashboard/src/i18n/locales/ru-RU/features/chat.json
git commit -m "feat(diff): add fullscreen i18n keys for DiffPreview"
```

---

### Task 2: Add fullscreen state, functions, Teleport overlay, and CSS to DiffPreview.vue

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/DiffPreview.vue`

**Interfaces:**
- Consumes: i18n keys from Task 1 (`diffPreview.fullscreen.*`)
- Produces: A fully functional fullscreen overlay accessible from all 5+ call sites — no API change since fullscreen is purely internal state

- [ ] **Step 1: Update Vue imports to include `nextTick`, `watch`, `onBeforeUnmount`, and `nextTick`**

Old import (line 190):
```ts
import { computed, ref } from "vue";
```

New import:
```ts
import { computed, ref, nextTick, watch, onBeforeUnmount } from "vue";
```

- [ ] **Step 2: Add `isFullscreen` state, `fullscreenBtnRef`, `overlayRef`, and `enterFullscreen`/`exitFullscreen` functions**

Insert after the `setViewMode` function (around line 310, after the `const viewModeAriaLabel` line):

```ts
// ── Fullscreen state (spec 2026-06-30-diff-fullscreen-design.md §4) ─
const isFullscreen = ref(false);
const fullscreenBtnRef = ref<HTMLElement | null>(null);
const overlayRef = ref<HTMLElement | null>(null);

function enterFullscreen(): void {
  isFullscreen.value = true;
  nextTick(() => overlayRef.value?.focus());
}

function exitFullscreen(): void {
  isFullscreen.value = false;
  nextTick(() => fullscreenBtnRef.value?.focus());
}
```

- [ ] **Step 3: Add body scroll lock watcher**

Insert anywhere after `isFullscreen` ref definition, for example right after the `exitFullscreen` function:

```ts
// Body scroll lock while fullscreen (spec §3.4)
watch(isFullscreen, (v) => {
  document.body.style.overflow = v ? "hidden" : "";
});

// Cleanup on unmount (spec §8 — edge case: component unmounts while fullscreen)
onBeforeUnmount(() => {
  if (isFullscreen.value) {
    document.body.style.overflow = "";
  }
});
```

- [ ] **Step 4: Add fullscreen button to the header template**

Find the `.diff-header-right` section (around line ~65). Add the fullscreen button **between the `.diff-view-toggle` div and the `.diff-chevron` v-icon**. Insert this block after the closing `</div>` of `.diff-view-toggle`:

```html
        <!-- Fullscreen button (spec 2026-06-30-diff-fullscreen-design.md §3.1) -->
        <button
          ref="fullscreenBtnRef"
          type="button"
          class="diff-fullscreen-btn"
          :title="tm('diffPreview.fullscreen.enter')"
          :aria-label="tm('diffPreview.fullscreen.enter')"
          @click.stop="enterFullscreen"
        >
          <v-icon size="14">mdi-fullscreen</v-icon>
        </button>
```

Resulting diff:

```html
        <div class="diff-view-toggle" ...>...</div>
        <!-- + NEW fullscreen button block + -->
        <button ...>
          <v-icon size="14">mdi-fullscreen</v-icon>
        </button>
        <v-icon v-if="collapsible" size="18" class="diff-chevron" ...>mdi-chevron-right</v-icon>
```

- [ ] **Step 5: Add Teleport overlay at the end of `<template>`**

Insert right **before the closing `</template>` tag** (after line ~180, where the template ends and `<script setup>` begins):

```html
<!-- Fullscreen overlay — Teleported to <body> to escape fixed-position
     stacking contexts. Shares same reactive refs as normal view.
     Spec 2026-06-30-diff-fullscreen-design.md §3.2 -->
<Teleport to="body">
  <div
    v-if="isFullscreen"
    ref="overlayRef"
    class="diff-fullscreen-overlay"
    role="dialog"
    aria-modal="true"
    :aria-label="tm('diffPreview.fullscreen.ariaLabel')"
    tabindex="-1"
    @keydown.escape="exitFullscreen"
  >
    <!-- Back button: fixed top-right corner -->
    <button
      type="button"
      class="diff-fullscreen-back-btn"
      :title="tm('diffPreview.fullscreen.exit')"
      :aria-label="tm('diffPreview.fullscreen.exit')"
      @click="exitFullscreen"
    >
      <v-icon size="20">mdi-fullscreen-exit</v-icon>
      <span class="diff-fullscreen-back-label">{{
        tm("diffPreview.fullscreen.exitLabel")
      }}</span>
    </button>

    <!-- Fullscreen diff content — same refs as normal view.
         The header and diff body are re-rendered here so they appear
         inside the overlay. The isFullscreen ref is shared, so
         clicking the fullscreen button inside the overlay is a
         no-op (the button is at the normal view and is not rendered
         here because it is behind the overlay). -->
    <div class="diff-fullscreen-body">
      <div
        class="diff-preview is-fullscreen"
        :class="{ 'is-dark': isDark, collapsed: isCollapsed, 'is-split': viewMode === 'split' }"
      >
        <!-- Same header — the fullscreen button in the normal header
             is behind the overlay, so it doesn't appear here. -->
        <button
          v-if="summary || filePath || statsAdds || statsDels"
          type="button"
          class="diff-header"
          @click="toggleCollapsed"
        >
          <div class="diff-header-left">
            <v-icon size="16" class="diff-header-icon"
              >mdi-file-document-edit-outline</v-icon
            >
            <span v-if="filePath" class="diff-file-path">{{ filePath }}</span>
          </div>
          <div class="diff-header-right">
            <template v-if="statsAdds || statsDels">
              <span v-if="statsAdds" class="diff-stats diff-stats-add"
                >+{{ statsAdds }}</span
              >
              <span v-if="statsDels" class="diff-stats diff-stats-del"
                >−{{ statsDels }}</span
              >
            </template>
            <div
              class="diff-view-toggle"
              role="group"
              :aria-label="viewModeAriaLabel"
            >
              <button
                type="button"
                class="diff-view-toggle-btn"
                :class="{ active: viewMode === 'unified' }"
                :aria-pressed="viewMode === 'unified'"
                :title="unifiedLabel"
                @click.stop="setViewMode('unified')"
              >
                <v-icon size="14">mdi-format-align-justify</v-icon>
              </button>
              <button
                type="button"
                class="diff-view-toggle-btn"
                :class="{ active: viewMode === 'split' }"
                :aria-pressed="viewMode === 'split'"
                :title="splitLabel"
                @click.stop="setViewMode('split')"
              >
                <v-icon size="14">mdi-view-split-vertical</v-icon>
              </button>
            </div>
            <!-- Fullscreen button is intentionally omitted here:
                 the overlay has its own "Back" exit button above. -->
            <v-icon
              v-if="collapsible"
              size="18"
              class="diff-chevron"
              :class="{ expanded: !isCollapsed }"
            >
              mdi-chevron-right
            </v-icon>
          </div>
        </button>

        <!-- Summary text -->
        <div v-if="summary && !isCollapsed" class="diff-summary-text">
          {{ summary }}
        </div>

        <!-- Diff body -->
        <div v-if="!isCollapsed" class="diff-body">
          <div v-if="truncated" class="diff-truncation-warning">
            ⚠ Diff truncated (showing first
            {{ maxChars.toLocaleString() }} characters)
          </div>

          <!-- Unified mode -->
          <template v-if="viewMode === 'unified'">
            <div
              v-for="(hunk, hi) in parsedHunks"
              :key="hi"
              class="diff-hunk"
              :class="{ 'is-hunk-folded': collapsedHunks.has(hi) }"
            >
              <button
                type="button"
                class="hunk-header"
                :aria-expanded="!collapsedHunks.has(hi)"
                @click="toggleHunk(hi)"
              >
                <v-icon
                  size="12"
                  class="hunk-chevron"
                  :class="{ expanded: !collapsedHunks.has(hi) }"
                >
                  mdi-chevron-right
                </v-icon>
                <span class="hunk-header-text">{{ hunk.header }}</span>
                <span class="hunk-header-count">{{
                  hunk.lines.length
                }}</span>
              </button>
              <div
                v-show="!collapsedHunks.has(hi)"
                class="diff-hunk-body"
              >
                <div
                  v-for="(line, li) in hunk.lines"
                  :key="li"
                  class="diff-line"
                  :class="line.type"
                >
                  <span class="line-number old">{{ line.oldNo }}</span>
                  <span class="line-number new">{{ line.newNo }}</span>
                  <span class="line-prefix">{{ line.prefix }}</span>
                  <span class="line-content">{{ line.content }}</span>
                </div>
              </div>
            </div>
          </template>

          <!-- Split mode -->
          <template v-else>
            <div
              v-for="(hunk, hi) in splitHunks"
              :key="hi"
              class="diff-hunk diff-hunk-split"
            >
              <div class="hunk-header">
                {{ hunk.header }}
              </div>
              <div
                v-for="(row, ri) in hunk.rows"
                :key="ri"
                class="diff-row-split"
                :class="row.kind"
              >
                <div class="diff-cell left">
                  <span class="line-number">{{ row.left?.oldNo ?? '' }}</span>
                  <span class="line-prefix">{{ row.left?.prefix ?? '' }}</span>
                  <span class="line-content">{{ row.left?.content ?? '' }}</span>
                </div>
                <div class="diff-cell right">
                  <span class="line-number">{{ row.right?.newNo ?? '' }}</span>
                  <span class="line-prefix">{{ row.right?.prefix ?? '' }}</span>
                  <span class="line-content">{{ row.right?.content ?? '' }}</span>
                </div>
              </div>
            </div>
          </template>

          <div v-if="collapsedOverflow > 0" class="diff-overflow-bar">
            <button
              type="button"
              class="diff-show-more"
              @click="showAllLines = true"
            >
              Show all {{ totalLines.toLocaleString() }} lines ({{
                collapsedOverflow
              }}
              more)
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</Teleport>
```

- [ ] **Step 6: Add CSS for the fullscreen overlay, back button, and body**

Insert at the **end of the `<style scoped>` block** (before the closing `</style>` tag — at the end of the file):

```css
/* ══════════════════════════════════════════════════════════════════
   Fullscreen overlay — spec 2026-06-30-diff-fullscreen-design.md §7
   ══════════════════════════════════════════════════════════════════ */

/* Overlay backdrop: fills entire viewport */
.diff-fullscreen-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgb(var(--v-theme-background));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Back button: small FAB fixed at top-right corner */
.diff-fullscreen-back-btn {
  position: fixed;
  top: 12px;
  right: 12px;
  z-index: 10000;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1px solid rgb(var(--v-theme-outline));
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  font-size: 13px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  transition: background 0.15s;
  white-space: nowrap;
}
.diff-fullscreen-back-btn:hover {
  background: rgb(var(--v-theme-surface-variant));
}

/* Fullscreen body: scrollable container */
.diff-fullscreen-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  padding-top: 52px; /* room for the fixed back button at top-right */
}

/* Override for diff-preview inside fullscreen: wider border,
   no max-width constraint. */
.diff-preview.is-fullscreen {
  max-width: 100%;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 8px;
}

/* Fullscreen button in the normal header. Matches existing
   .diff-view-toggle-btn dimensions (22×22px) and transitions. */
.diff-fullscreen-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: none;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.55);
  transition:
    border-color 0.15s,
    color 0.15s,
    background 0.15s;
  flex-shrink: 0;
}
.diff-fullscreen-btn:hover {
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}
.diff-fullscreen-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
```

- [ ] **Step 7: Run typecheck to verify no TypeScript errors**

```bash
cd F:\github\Astrbot\dashboard
npx vue-tsc --noEmit
```

Expected: No errors.

- [ ] **Step 8: Commit**

```bash
cd F:\github\Astrbot
git add dashboard/src/components/chat/message_list_comps/DiffPreview.vue
git commit -m "feat(diff): add fullscreen overlay to DiffPreview"
```

---

### Task 3: Manual verification

- [ ] **Step 1: Start the dev server**

```bash
cd F:\github\Astrbot\dashboard
pnpm dev
```

- [ ] **Step 2: Verify with chat diff (ToolCallCard)**

1. Open browser and send an `astrbot_file_compare` or `astrbot_file_edit` tool call that generates a diff.
2. Verify: the diff renders normally in the chat message.
3. Verify: a `⛶` (fullscreen) icon button is visible in the diff header, next to the unified/split toggle.
4. Click the fullscreen button.
5. Verify: a fullscreen overlay covers the entire viewport.
6. Verify: a "Back" button is visible at the top-right corner (icon + label).
7. Verify: the diff header (path, stats, unified/split toggle) is visible and interactive.
8. Click the "Back" button.
9. Verify: the normal view is restored, the chat is still scrolled to the same position.

- [ ] **Step 3: Verify with git diff sidebar (GitDiffFileItem)**

1. Load a project with some git changes.
2. Open the git diff sidebar.
3. Click any file to expand its diff.
4. Verify: the fullscreen button is visible in each file's DiffPreview header.
5. Click fullscreen → verify overlay + back button.
6. Switch to split mode while fullscreen → verify split works inside the overlay.
7. Press Escape → verify returns to normal view.

- [ ] **Step 4: Verify body scroll lock**

1. While in fullscreen, try to scroll the page behind the overlay (touchpad or mouse wheel).
2. Verify: the background does not scroll.
3. Exit fullscreen.
4. Verify: the page scrolls normally again.

- [ ] **Step 5: Verify keyboard focus**

1. Enter fullscreen.
2. Press the Tab key several times.
3. Verify: focus moves through elements inside the overlay (header buttons, back button).
4. Press Escape → verify exit.

- [ ] **Step 6: Verify component unmount safety**

1. While in fullscreen on a diff in the git sidebar, quickly switch worktrees or refresh the project.
2. Verify: the overlay closes cleanly, body scroll is restored (no "stuck in overflow:hidden" state).
