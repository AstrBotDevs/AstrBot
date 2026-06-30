# DiffPreview Fullscreen Mode — Design Spec

| Field | Value |
| --- | --- |
| Spec author | elecvoid243 |
| Created at | 2026-06-30 16:04 (CST) |
| Status | Draft — pending user review |

---

## 1. Goal

Add a **fullscreen mode** to `DiffPreview.vue`, the shared diff rendering component used by all 5+ call sites across the dashboard (ToolCallCard, GitDiffFileItem, FilePatchPanel, FileDiffResult, ThemeAwareMarkdownCodeBlock). When activated, the diff expands to occupy the **entire browser viewport** — covering sidebar, message list, app shell chrome — and a **back button** (plus Escape key) returns to the normal view.

### Non-goals (out of scope)

- Browser Fullscreen API (`requestFullscreen`) — a CSS `position: fixed` overlay achieves the UX goal without browser permission / gesture constraints.
- URL-based deep-linking to fullscreen state.
- Persisting fullscreen state across reloads.
- Modifying any of the 5+ call site components.
- Adding a separate wrapper component — the logic lives inside DiffPreview itself.

---

## 2. Design Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | **Implementation location** | Inside `DiffPreview.vue` | Single change auto-benefits all call sites. The existing `viewMode` (unified/split) toggle is already inside DiffPreview for the same reason. |
| 2 | **Overlay mechanism** | `<Teleport to="body">` + `position: fixed; inset: 0` | Consistent with existing codebase pattern (worktree context menu uses Teleport). Avoids stacking-context clipping from `<ChatList>` or `<GitDiffSidebar>` fixed-position containers. |
| 3 | **Fullscreen button placement** | In the existing header bar, next to the unified/split toggle | Always reachable (even when body collapsed). Consistent with existing header layout. |
| 4 | **Return mechanism** | Floating button in top-right corner + Escape key | Dual-entry low-latency; Escape is standard fullscreen exit idiom. |
| 5 | **Header visibility in fullscreen** | **Retain** the header (path, stats, viewMode/unified/split toggle still visible and interactive) | Users need to see "what file is this" and may want to switch view mode while fullscreen. |
| 6 | **State preservation** | All current state preserved: `viewMode`, per-hunk collapse state, scroll position, truncation warning | Expected UX: enter/exit fullscreen should not reset or discard any visual state. |
| 7 | **Body scroll lock** | Apply `overflow: hidden` to `<body>` while fullscreen | Prevents background page from scrolling via touchpad / wheel events behind the overlay. |
| 8 | **State persistence** | Per-component-instance ref; **no** localStorage / URL persistence | Fullscreen is transient — the user explicitly exits before doing anything else. Persisting it would create confusing "still fullscreen" states after navigation. |
| 9 | **i18n** | New key block under existing `diffPreview.fullscreen` in `features/chat.json` | Follows existing `diffPreview.viewMode` convention. |

---

## 3. Template Structure

### 3.1 Normal mode — header gains one more icon

```diff
  <div class="diff-header-right">
    <!-- ... stats ... -->
    <div class="diff-view-toggle">...</div>
+   <button
+     type="button"
+     class="diff-fullscreen-btn"
+     :title="tm('diffPreview.fullscreen.enter')"
+     @click.stop="enterFullscreen"
+   >
+     <v-icon size="14">mdi-fullscreen</v-icon>
+   </button>
    <v-icon v-if="collapsible" ...>mdi-chevron-right</v-icon>
  </div>
```

Icon order in the header-right group: `[stats] [unified/split toggle] [fullscreen button] [collapse chevron]`.

### 3.2 Fullscreen overlay (Teleport)

Rendered as the **last child of `<template>`** (not inside the `.diff-preview` div, so the Teleport source is outside the normal layout flow):

```html
<!-- Fullscreen overlay — Teleported to <body> to escape any
     fixed-position stacking context (GitDiffSidebar, ChatList, etc.). -->
<Teleport to="body">
  <div
    v-if="isFullscreen"
    class="diff-fullscreen-overlay"
    role="dialog"
    aria-modal="true"
    :aria-label="tm('diffPreview.fullscreen.ariaLabel')"
    @keydown.escape="exitFullscreen"
    tabindex="-1"
  >
    <!-- Back button: small FAB in top-right corner.
         Always visible; allows exit without muscle-memory overhead. -->
    <button
      type="button"
      class="diff-fullscreen-back-btn"
      :title="tm('diffPreview.fullscreen.exit')"
      @click="exitFullscreen"
    >
      <v-icon size="20">mdi-fullscreen-exit</v-icon>
      <span class="diff-fullscreen-back-label">{{
        tm("diffPreview.fullscreen.exitLabel")
      }}</span>
    </button>

    <!-- Re-render the same diff content. We clone the template
         structure rather than using <slot> because DiffPreview is
         self-contained (it receives `content` as a prop and renders
         parsed hunks). In fullscreen we render the same internal
         `.diff-body` with a small top padding offset (the back button
         occupies ~48px). The viewMode ref is the same; collapse
         state is shared. -->
    <div class="diff-fullscreen-body">
      <!-- Same diff content: header + summary + diff body.
           The header is interactive (viewMode toggle, collapse). -->
      <div class="diff-preview is-fullscreen" :class="'is-split': viewMode === 'split'">
        <!-- Render the same internal structure as the normal
             template — header (clickable for collapse), summary
             text, unified/split hunks. -->
        <button type="button" class="diff-header" @click="toggleCollapsed">
          <!-- same header-layout as normal -->
        </button>
        <div v-if="!isCollapsed" class="diff-body">
          <!-- same unified/split hunk rendering as normal -->
        </div>
      </div>
    </div>
  </div>
</Teleport>
```

The fullscreen body **reuses the same refs** (`viewMode`, `isCollapsed`, `isCollapsedHunks`, `parsedHunks` / `splitHunks`) as the normal view — they are shared by reference, not duplicated. This guarantees state consistency: collapsing a hunk in fullscreen is immediately reflected when the user exits (and vice versa).

### 3.3 Focus management

On entering fullscreen:
- Call `overlayRef.value?.focus()` (the overlay has `tabindex="-1"`) so keyboard focus moves into the overlay.
- `@keydown.escape="exitFullscreen"` on the overlay div handles the exit.

On exiting fullscreen:
- Call `fullscreenBtnRef.value?.focus()` (the button in the header) so focus returns to the trigger point.

### 3.4 Body scroll lock

```ts
watch(isFullscreen, (v) => {
  if (v) {
    document.body.style.overflow = "hidden";
  } else {
    document.body.style.overflow = "";
  }
});
```

---

## 4. New State

```ts
const isFullscreen = ref(false);

function enterFullscreen(): void {
  isFullscreen.value = true;
  // Focus the overlay in next tick so the dialog is announced.
  nextTick(() => overlayRef.value?.focus());
}

function exitFullscreen(): void {
  isFullscreen.value = false;
  // Return focus to the fullscreen button.
  nextTick(() => fullscreenBtnRef.value?.focus());
}
```

No additional props needed — fullscreen is purely internal to DiffPreview.

---

## 5. Keyboard Shortcut

`Escape` exits fullscreen. Handled via `@keydown.escape="exitFullscreen"` on the overlay div.

No other keyboard shortcuts are needed.

---

## 6. i18n Keys

Add to `features/chat.json` under the existing `diffPreview` block:

### en-US (`chat.json`)

```json
"diffPreview": {
  "viewMode": { /* existing */ },
  "fullscreen": {
    "enter": "Fullscreen",
    "exit": "Exit fullscreen",
    "exitLabel": "Back",
    "ariaLabel": "Diff fullscreen view"
  }
}
```

### zh-CN (`chat.json`)

```json
"diffPreview": {
  "viewMode": { /* existing */ },
  "fullscreen": {
    "enter": "全屏",
    "exit": "退出全屏",
    "exitLabel": "返回",
    "ariaLabel": "全屏显示差异"
  }
}
```

### ru-RU (`chat.json`)

```json
"diffPreview": {
  "viewMode": { /* existing */ },
  "fullscreen": {
    "enter": "На весь экран",
    "exit": "Выйти из полноэкранного режима",
    "exitLabel": "Назад",
    "ariaLabel": "Полноэкранный просмотр diff"
  }
}
```

---

## 7. CSS

### 7.1 New class: `.diff-fullscreen-btn`

```css
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
  color: rgb(var(--v-theme-on-surface-variant));
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.diff-fullscreen-btn:hover {
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.08);
}
```

(Matches existing `.git-diff-sidebar-tab-add` pattern — same dimensions, same transition.)

### 7.2 New class: `.diff-fullscreen-overlay`

```css
.diff-fullscreen-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgb(var(--v-theme-background));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
```

### 7.3 New class: `.diff-fullscreen-back-btn`

```css
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
}
.diff-fullscreen-back-btn:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.diff-fullscreen-back-label {
  /* Label: "Back". Visible so users immediately know what the
     button does; kept as a <span> for i18n flexibility. */
}
```

### 7.4 New class: `.diff-fullscreen-body`

```css
.diff-fullscreen-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  /* The back button is fixed at top-right, so we need top padding
     to prevent the header from being hidden behind it. */
  padding-top: 52px;
}
```

### 7.5 Override for `diff-preview` inside fullscreen

```css
.diff-preview.is-fullscreen {
  max-width: 100%;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 8px;
}
```

---

## 8. Edge Cases

| Edge Case | Behavior | Rationale |
|-----------|----------|-----------|
| Multiple DiffPreview instances in one chat | Each has its own `isFullscreen` ref | Independent instances; user can fullscreen only one at a time. |
| Component unmount (worktree switch, file change) while fullscreen | `onUnmounted` hook exits fullscreen via `document.body.style.overflow = ""` | Prevents "stuck fullscreen" on route change. |
| Two consecutive fullscreen enters/exits | Idempotent: `exitFullscreen` sets `false`, enter sets `true`; body scroll is toggled via watcher | No-op on re-entry. |
| Diff is empty / no content in fullscreen | Shows the same empty state as normal (no hunks rendered) | Consistent. |
| Mobile / narrow viewport | Back button and header layout remain responsive (flex-wrap) | All elements use existing responsive patterns. |
| Focus trap | Not implemented — user can tab to browser URL bar etc. | Fullscreen is an overlay, not a modal dialog. Simple parity with other dashboard overlays is sufficient. |

---

## 9. Files Changed

| File | Change |
|------|--------|
| `dashboard/src/components/chat/message_list_comps/DiffPreview.vue` | Add `isFullscreen` ref + `enterFullscreen`/`exitFullscreen` functions + Teleport overlay in template + body scroll lock watcher + new CSS |
| `dashboard/src/i18n/locales/en-US/features/chat.json` | Add `diffPreview.fullscreen` i18n block |
| `dashboard/src/i18n/locales/zh-CN/features/chat.json` | Add `diffPreview.fullscreen` i18n block |
| `dashboard/src/i18n/locales/ru-RU/features/chat.json` | Add `diffPreview.fullscreen` i18n block |

No changes to: `ToolCallCard.vue`, `GitDiffFileItem.vue`, `FilePatchPanel.vue`, `FileDiffResult.vue`, `ThemeAwareMarkdownCodeBlock.vue`, `GitDiffBodyContent.vue`, or any other call site.

---

## 10. Verification

1. **Enter fullscreen**: Click the fullscreen `⛶` button in any DiffPreview — overlay appears covering entire viewport; back button visible at top-right.
2. **ViewMode preserved**: Switch to split mode while normal, enter fullscreen — still split mode; switch back — still split.
3. **Collapse state preserved**: Collapse a hunk in fullscreen, exit — hunk still collapsed.
4. **Escape key**: While fullscreen, press Escape — returns to normal view.
5. **Back button**: Click the "Back" button — same result as Escape.
6. **Body scroll**: While fullscreen, attempt to scroll the page behind — no scrolling occurs.
7. **Multiple instances**: Open two diffs in the chat, fullscreen one — the other remains normal.
8. **Component unmount**: Force a file change while fullscreen — overlay closes, body scroll restored.
