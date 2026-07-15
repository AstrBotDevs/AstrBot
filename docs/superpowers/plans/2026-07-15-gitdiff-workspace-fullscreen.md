# GitDiffSidebar Workspace Fullscreen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a non-persisted fullscreen mode to the GitDiffSidebar workspace page while preserving the existing file-browser layout and state.

**Architecture:** Add fullscreen state and lifecycle cleanup to `GitDiffSidebar.vue`, teleport the existing sidebar transition/aside tree to `body` only while fullscreen is active, and style the existing root aside as a fixed viewport-sized flex container. The fullscreen control is shown only for `viewMode === "files"`; switching to another page exits fullscreen.

**Tech Stack:** Vue 3 `<script setup>` with TypeScript, Vue `Teleport`/`Transition`, Vuetify `v-btn`/`v-icon`, scoped CSS, pnpm dashboard typecheck/build.

## Global Constraints

- Modify only `dashboard/src/components/chat/GitDiffSidebar.vue` for the feature.
- Do not add a new `localStorage` key or persist fullscreen state.
- Reuse `spcodeProjectLoad.documentManager.fullscreen.enter` and `.exit` translations already used by `DocumentManager.vue`.
- Keep the existing four page modes, file-browser refs, pane state, worktree state, and data fetching unchanged.
- Use `Escape` to exit fullscreen and restore `document.body.style.overflow` on exit and unmount.
- Keep existing mobile fullscreen behavior intact; the new `.is-fullscreen` modifier must not weaken the existing `@media (max-width: 760px)` rules.

---

### Task 1: Add workspace fullscreen state and lifecycle behavior

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue:209-276` for state and existing `viewMode` persistence watcher.
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue:888-902` for the existing mount listener registration.
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue:2246-2269` for unmount cleanup.
- Test: No new test file; this component has no existing covering test and the repository has no isolated fullscreen state module. Validate through the focused dashboard typecheck/build and diff review in Task 3.

**Interfaces:**
- Consumes: the existing `viewMode` ref, `onMounted` callback, `onBeforeUnmount` callback, and `document`/`body` DOM APIs.
- Produces: `isFullscreen`, `toggleFullscreen()`, `exitFullscreen()`, and `onFullscreenKeyDown()` used by the template and lifecycle hooks.

- [ ] **Step 1: Add non-persisted fullscreen state and handlers immediately after the `viewMode`/file-browser state declarations.**

Use this implementation:

```ts
const viewMode = ref<"files" | "diff" | "history" | "docs">(loadViewMode());
const fileBrowserCurrentPath = ref<string>(loadFileBrowserCurrentPath());
const isFullscreen = ref(false);

function toggleFullscreen(): void {
  isFullscreen.value = !isFullscreen.value;
}

function exitFullscreen(): void {
  isFullscreen.value = false;
}

function onFullscreenKeyDown(e: KeyboardEvent): void {
  if (e.key === "Escape" && isFullscreen.value) {
    exitFullscreen();
  }
}
```

Keep `fileBrowserPreviewPath` directly after `fileBrowserCurrentPath`; the new state does not replace or persist any file-browser state.

- [ ] **Step 2: Extend the existing `watch(viewMode, ...)` without changing its localStorage behavior.**

Change the watcher body from:

```ts
watch(viewMode, (v) => safeSetItem(STORAGE_KEYS.viewMode, v), {
  flush: "post",
});
```

to:

```ts
watch(
  viewMode,
  (v) => {
    if (v !== "files") exitFullscreen();
    safeSetItem(STORAGE_KEYS.viewMode, v);
  },
  { flush: "post" },
);
```

This keeps the existing persisted page selection while ensuring fullscreen is scoped to the workspace page.

- [ ] **Step 3: Add body scroll locking and mount/unmount listener cleanup.**

Insert the fullscreen watcher near the new handlers:

```ts
watch(
  isFullscreen,
  (v) => {
    document.body.style.overflow = v ? "hidden" : "";
  },
  { immediate: true },
);
```

Append the event registration to the existing `onMounted(() => { ... })` callback:

```ts
document.addEventListener("keydown", onFullscreenKeyDown);
```

Append cleanup to the existing `onBeforeUnmount(() => { ... })` callback:

```ts
document.removeEventListener("keydown", onFullscreenKeyDown);
document.body.style.overflow = "";
```

Do not create a second `onMounted` or `onBeforeUnmount` callback. The existing capture-phase context-menu listener remains unchanged; the fullscreen handler is a normal document listener and only reacts when fullscreen is active.

- [ ] **Step 4: Run the focused typecheck before editing the template.**

Run:

```cmd
cd /d F:\github\Astrbot\.worktrees\gitdiff-workspace-fullscreen\dashboard
pnpm typecheck
```

Expected: the command completes successfully. If it fails, fix only the new state/lifecycle typing before continuing.

---

### Task 2: Teleport the existing sidebar and add the workspace control

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue:2360-2370` for the Teleport wrapper and root class.
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue:2385-2412` for the workspace fullscreen button.
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue:3214-3228` for the fullscreen root styles.

**Interfaces:**
- Consumes: `isFullscreen`, `toggleFullscreen`, `viewMode`, and `tm` from Task 1.
- Produces: an unchanged sidebar component tree that moves to `body` only when fullscreen is active, plus an accessible workspace fullscreen action.

- [ ] **Step 1: Wrap the existing transition/aside tree with a disabled Teleport.**

Replace the current template opening:

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
```

with:

```vue
<template>
  <Teleport to="body" :disabled="!isFullscreen">
    <transition name="slide-left">
      <aside
        v-if="modelValue"
        ref="sidebarRef"
        class="git-diff-sidebar"
        :class="{ resizing: isResizing, 'is-fullscreen': isFullscreen }"
        :style="{ width: sidebarWidth + 'px' }"
      >
```

At the end of the template, close the new wrapper after the existing transition:

```vue
      </aside>
    </transition>
  </Teleport>
</template>
```

Do not duplicate or move any of the four page templates. The existing `aside` remains the single stateful component tree.

- [ ] **Step 2: Add the workspace-only fullscreen button to the existing header action group.**

Insert this button in `.git-diff-sidebar-actions` between the refresh tooltip and the existing close button:

```vue
          <v-btn
            v-if="viewMode === 'files'"
            :icon="
              isFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'
            "
            size="small"
            variant="text"
            :aria-pressed="isFullscreen"
            :aria-label="
              tm(
                isFullscreen
                  ? 'spcodeProjectLoad.documentManager.fullscreen.exit'
                  : 'spcodeProjectLoad.documentManager.fullscreen.enter',
              )
            "
            :title="
              tm(
                isFullscreen
                  ? 'spcodeProjectLoad.documentManager.fullscreen.exit'
                  : 'spcodeProjectLoad.documentManager.fullscreen.enter',
              )
            "
            @click="toggleFullscreen"
          />
```

Keep the refresh and close buttons unchanged. The button is intentionally hidden on `diff`, `history`, and `docs`; changing `viewMode` exits fullscreen through the watcher from Task 1.

- [ ] **Step 3: Add a fullscreen modifier that overrides the inline sidebar width.**

Insert this rule immediately after the existing `.git-diff-sidebar` rule:

```css
.git-diff-sidebar.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1300;
  width: 100vw !important;
  height: 100vh;
  margin-top: 0;
  border-left: 0;
}
```

Keep the normal `.git-diff-sidebar` rule and the existing mobile media-query rule unchanged. The modifier preserves the existing flex-column layout, so `.git-diff-sidebar-body` continues to provide the scrollable workspace body and `FileBrowserView` continues to fill its parent.

- [ ] **Step 4: Run formatting-safe focused checks on the changed SFC.**

Run:

```cmd
cd /d F:\github\Astrbot\.worktrees\gitdiff-workspace-fullscreen\dashboard
pnpm exec eslint src/components/chat/GitDiffSidebar.vue
pnpm typecheck
```

Expected: ESLint and Vue TypeScript checking both complete without errors.

---

### Task 3: Verify the integrated dashboard behavior and commit the implementation

**Files:**
- Verify: `dashboard/src/components/chat/GitDiffSidebar.vue`.
- Verify: `docs/superpowers/specs/2026-07-15-gitdiff-workspace-fullscreen-design.md`.

**Interfaces:**
- Consumes: the complete implementation from Tasks 1–2.
- Produces: a clean, typechecked, buildable feature branch with a focused conventional commit.

- [ ] **Step 1: Review the final diff for scope and lifecycle correctness.**

Run:

```cmd
cd /d F:\github\Astrbot\.worktrees\gitdiff-workspace-fullscreen
git diff --check
git diff -- dashboard/src/components/chat/GitDiffSidebar.vue
```

Confirm the diff contains only:

- the non-persisted fullscreen state and handlers;
- the view-mode exit guard;
- body overflow and keydown lifecycle cleanup;
- the disabled Teleport wrapper;
- the workspace-only action button;
- the fullscreen CSS modifier.

- [ ] **Step 2: Run the dashboard production build.**

Run:

```cmd
cd /d F:\github\Astrbot\.worktrees\gitdiff-workspace-fullscreen\dashboard
pnpm build
```

Expected: `vue-tsc --noEmit` and the Vite production build both complete successfully.

- [ ] **Step 3: Perform the behavior review against the approved design.**

Check the following manually in the dashboard if the development environment is available:

1. Open the GitDiffSidebar and select the workspace/files page.
2. Click the fullscreen icon; confirm the entire sidebar (header, path strip, tabs, worktree controls, search, file tree, and preview) fills the browser viewport.
3. Navigate directories, open a file, resize/collapse panes, and confirm those states remain intact while entering and exiting fullscreen.
4. Press `Escape`; confirm fullscreen exits and the body becomes scrollable again.
5. Switch to `diff`, `history`, or `docs`; confirm fullscreen exits and the selected page remains usable.
6. Resize the sidebar in normal mode, enter and exit fullscreen, and confirm the previous sidebar width is restored.

- [ ] **Step 4: Commit the implementation.**

Run:

```cmd
cd /d F:\github\Astrbot\.worktrees\gitdiff-workspace-fullscreen
git add dashboard/src/components/chat/GitDiffSidebar.vue
git commit -m "feat(dashboard): add workspace fullscreen mode"
git status --short --branch
```

Expected: the commit succeeds with no uncommitted implementation changes, and the branch remains `feat/gitdiff-workspace-fullscreen`.
