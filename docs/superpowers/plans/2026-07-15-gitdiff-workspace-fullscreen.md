# GitDiffSidebar Workspace Fullscreen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a sidebar-wide fullscreen control and a file-preview fullscreen control to GitDiffSidebar with mutually-exclusive semantics that share a single "cancel" action.

**Architecture:** Two non-persisted refs (`globalFullscreen`, `innerFullscreen`) live in `GitDiffSidebar.vue` and are toggled through functions that enforce mutual exclusion. The top button toggles `globalFullscreen`; the inner button (in `FileBrowserFilePreview`) toggles `innerFullscreen`. Both buttons show an exit icon when either mode is on, and clicking either while any fullscreen is active cancels all fullscreen. Global fullscreen persists across page switches; inner fullscreen applies only while a file is previewed.

**Tech Stack:** Vue 3 `<script setup>` with TypeScript, Vue `Teleport`, Vuetify `v-btn`/`v-icon`, scoped CSS, provide/inject for state sharing, pnpm dashboard typecheck/build.

## Global Constraints

- Modify only `dashboard/src/components/chat/GitDiffSidebar.vue` and `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`.
- Do not add a new `localStorage` key or persist fullscreen state.
- Reuse `spcodeProjectLoad.documentManager.fullscreen.enter` and `.exit` translations.
- Do not nest fullscreen: only one of `globalFullscreen` / `innerFullscreen` can be `true` at a time.
- Keep existing close button, mobile fullscreen rules, and all existing fetch/state behavior.
- Use `Escape` to cancel whichever fullscreen is on and restore `document.body.style.overflow`.
- The top button must be visible regardless of `viewMode`.
- The inner button must only render when `state.kind === "file"`.

---

### Task 1: Refactor fullscreen state and lifecycle in `GitDiffSidebar.vue`

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue` — the prior `isFullscreen` block (added in the reverted commit).
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue` — the `watch(viewMode, ...)` block (remove the exit-fullscreen rule).
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue` — `onMounted`/`onBeforeUnmount` blocks (keep the keydown listener with shared semantics).

**Interfaces:**
- Consumes: existing `viewMode` ref, `onMounted`, `onBeforeUnmount`.
- Produces: `globalFullscreen`, `innerFullscreen`, `toggleGlobalFullscreen`, `toggleInnerFullscreen`, `isAnyFullscreen`, `onFullscreenKeyDown`, plus three `provide()` values for the inner component.

- [ ] **Step 1: Replace the single `isFullscreen` ref with two refs and mutual-exclusion helpers.**

Use this implementation in place of the prior `isFullscreen` + `toggleFullscreen` + `exitFullscreen` + `onFullscreenKeyDown` block:

```ts
const globalFullscreen = ref(false);
const innerFullscreen = ref(false);
const isAnyFullscreen = computed(() => globalFullscreen.value || innerFullscreen.value);

function toggleGlobalFullscreen(): void {
  if (isAnyFullscreen.value) {
    globalFullscreen.value = false;
    innerFullscreen.value = false;
    return;
  }
  globalFullscreen.value = true;
}

function toggleInnerFullscreen(): void {
  if (isAnyFullscreen.value) {
    globalFullscreen.value = false;
    innerFullscreen.value = false;
    return;
  }
  innerFullscreen.value = true;
}

function onFullscreenKeyDown(e: KeyboardEvent): void {
  if (e.key !== "Escape" || !isAnyFullscreen.value) return;
  globalFullscreen.value = false;
  innerFullscreen.value = false;
}
```

Keep the body-overflow watcher but key it on both refs:

```ts
watch(
  isAnyFullscreen,
  (v) => {
    document.body.style.overflow = v ? "hidden" : "";
  },
  { immediate: true },
);
```

- [ ] **Step 2: Restore the original `watch(viewMode, ...)` body so `viewMode` only persists its value.**

Replace:

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

with:

```ts
watch(viewMode, (v) => safeSetItem(STORAGE_KEYS.viewMode, v), {
  flush: "post",
});
```

`globalFullscreen` no longer exits when the page changes — that is required for the new "global survives sub-page switches" semantics.

- [ ] **Step 3: Provide the new state to the inner component via inject keys.**

Add right after the existing `provide`/`setLogPathFilter` block:

```ts
const FULLSCREEN_GLOBAL_KEY = "spcode:globalFullscreen";
const FULLSCREEN_INNER_KEY = "spcode:innerFullscreen";
const FULLSCREEN_IS_ANY_KEY = "spcode:isAnyFullscreen";
const FULLSCREEN_TOGGLE_INNER_KEY = "spcode:toggleInnerFullscreen";
provide<Ref<boolean>>(FULLSCREEN_GLOBAL_KEY, globalFullscreen);
provide<Ref<boolean>>(FULLSCREEN_INNER_KEY, innerFullscreen);
provide<ComputedRef<boolean>>(FULLSCREEN_IS_ANY_KEY, isAnyFullscreen);
provide<() => void>(FULLSCREEN_TOGGLE_INNER_KEY, toggleInnerFullscreen);
```

These are consumed in Task 2 by `FileBrowserFilePreview.vue`.

- [ ] **Step 4: Run `pnpm typecheck` before continuing.**

Run:

```cmd
cd /d F:\github\Astrbot\.worktrees\gitdiff-workspace-fullscreen\dashboard
pnpm typecheck
```

Expected: passes without errors. The previous `.is-fullscreen` class binding and Teleport wiring still references `globalFullscreen` only — that is correct.

---

### Task 2: Update the top button and global fullscreen wiring in `GitDiffSidebar.vue`

**Files:**
- Modify: `dashboard/src/components/chat/GitDiffSidebar.vue` — the header action group and the `<aside>`/Teleport wrapper.

**Interfaces:**
- Consumes: `isAnyFullscreen`, `toggleGlobalFullscreen` from Task 1.
- Produces: a top button that always renders and shows the correct icon; an `<aside>` whose `.is-fullscreen` class tracks only `globalFullscreen`.

- [ ] **Step 1: Make the top button always render and reflect the combined state.**

Replace the current top button (with the `v-if="viewMode === 'files'"` guard and `isFullscreen`-based icon/title/aria-label) with:

```vue
          <v-btn
            :icon="
              isAnyFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'
            "
            size="small"
            variant="text"
            :aria-pressed="isAnyFullscreen"
            :aria-label="
              tm(
                isAnyFullscreen
                  ? 'spcodeProjectLoad.documentManager.fullscreen.exit'
                  : 'spcodeProjectLoad.documentManager.fullscreen.enter',
              )
            "
            :title="
              tm(
                isAnyFullscreen
                  ? 'spcodeProjectLoad.documentManager.fullscreen.exit'
                  : 'spcodeProjectLoad.documentManager.fullscreen.enter',
              )
            "
            @click="toggleGlobalFullscreen"
          />
```

Do not add `v-if`. The button now appears in every page mode.

- [ ] **Step 2: Keep the global Teleport and `.is-fullscreen` class bound to `globalFullscreen` only.**

The reverted commit's `<Teleport to="body" :disabled="!isFullscreen">` and `<aside ... :class="{ resizing: isResizing, 'is-fullscreen': isFullscreen }" ...>` must read `globalFullscreen` instead. Update both expressions to use `globalFullscreen`. No change is required to the scoped `.git-diff-sidebar.is-fullscreen` CSS rule.

- [ ] **Step 3: Run `pnpm typecheck` again before touching the inner component.**

Run:

```cmd
cd /d F:\github\Astrbot\.worktrees\gitdiff-workspace-fullscreen\dashboard
pnpm typecheck
```

Expected: passes.

---

### Task 3: Add the inner button and inner-fullscreen wiring to `FileBrowserFilePreview.vue`

**Files:**
- Modify: `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue` — the imports, the `<template>` root, and the `.preview-file-meta` row.

**Interfaces:**
- Consumes: `globalFullscreen`, `innerFullscreen`, `isAnyFullscreen`, `toggleInnerFullscreen` from `GitDiffSidebar` via inject.
- Produces: an inner button visible when a file is previewed; a Teleport + `.is-fullscreen` class on the preview root that activates only for `innerFullscreen`.

- [ ] **Step 1: Import the inject helper and the shared keys, then wire up the four bindings.**

Update the existing import line near the top of `<script setup>` so it also brings in `inject` from `vue` (it is likely already imported; verify with `grep`). Add the four inject calls near the other inject calls (`setLogPathFilter`):

```ts
import { computed, inject, ref, watch } from "vue";

const globalFullscreen = inject<Ref<boolean>>(
  "spcode:globalFullscreen",
  ref(false),
);
const innerFullscreen = inject<Ref<boolean>>(
  "spcode:innerFullscreen",
  ref(false),
);
const isAnyFullscreen = inject<ComputedRef<boolean>>(
  "spcode:isAnyFullscreen",
  computed(() => false),
);
const toggleInnerFullscreen = inject<() => void>(
  "spcode:toggleInnerFullscreen",
  () => {},
);
```

The fallbacks keep the component usable in isolation (storybook / unit tests).

- [ ] **Step 2: Wrap the existing `.preview-file` root in a Teleport and apply the `is-fullscreen` class.**

Change the existing opening:

```vue
      <!-- 文件 -->
      <div v-else-if="state.kind === 'file'" class="preview-file">
```

to:

```vue
      <!-- 文件 -->
      <Teleport to="body" :disabled="!innerFullscreen">
        <div
          v-else-if="state.kind === 'file'"
          class="preview-file"
          :class="{ 'is-fullscreen': innerFullscreen }"
        >
```

and change the matching closing `</div>` to `</div></Teleport>`. The `v-else-if` stays on the inner `<div>`; Vue's Teleport is transparent when disabled, so the existing v-if/v-else-if chain in the parent is unaffected.

- [ ] **Step 3: Add the inner button after the existing copy button.**

Insert this button immediately after the existing `<v-btn>` that toggles `copyContent` and before the closing `</div>` of `.preview-file-meta`:

```vue
        <v-btn
          v-if="state.kind === 'file'"
          size="x-small"
          variant="text"
          color="primary"
          :icon="
            isAnyFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'
          "
          :aria-pressed="isAnyFullscreen"
          :aria-label="
            tm(
              isAnyFullscreen
                ? 'spcodeProjectLoad.documentManager.fullscreen.exit'
                : 'spcodeProjectLoad.documentManager.fullscreen.enter',
            )
          "
          :title="
            tm(
              isAnyFullscreen
                ? 'spcodeProjectLoad.documentManager.fullscreen.exit'
                : 'spcodeProjectLoad.documentManager.fullscreen.enter',
            )
          "
          @click="toggleInnerFullscreen"
        />
```

It mirrors the size/style of the existing history/copy buttons. The `state.kind === "file"` guard is intentionally repeated even though the parent `v-else-if` already enforces it; it keeps the button a no-op if the inner-fullscreen wrapper is ever generalized.

- [ ] **Step 4: Add the inner-fullscreen CSS to the existing `<style scoped>` block.**

Insert this rule next to the existing `.preview-file` styles:

```css
.preview-file.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1300;
  display: flex;
  flex-direction: column;
  background: rgb(var(--v-theme-surface));
  margin: 0;
}
.preview-file.is-fullscreen .preview-file-meta {
  flex-shrink: 0;
  border-bottom: 1px solid
    var(--chat-border, rgba(var(--v-theme-on-surface), 0.1));
}
.preview-file.is-fullscreen :deep(.file-browser-code-view),
.preview-file.is-fullscreen .preview-binary {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}
```

The deep selector targets the `<FileBrowserCodeView>` component inside the preview area; if its actual class name differs (verify via grep before committing), update the selector.

---

### Task 4: Verify and commit

**Files:**
- Verify: `dashboard/src/components/chat/GitDiffSidebar.vue` and `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`.

- [ ] **Step 1: Run dashboard typecheck.**

Run:

```cmd
cd /d F:\github\Astrbot\.worktrees\gitdiff-workspace-fullscreen\dashboard
pnpm typecheck
```

Expected: passes.

- [ ] **Step 2: Run dashboard production build.**

Run:

```cmd
cd /d F:\github\Astrbot\.worktrees\gitdiff-workspace-fullscreen\dashboard
pnpm build
```

Expected: `vue-tsc --noEmit` and the Vite production build complete successfully.

- [ ] **Step 3: Restore the working tree's MDI font subset artifact (if produced).**

If `pnpm build` modified `dashboard/src/assets/mdi-subset/materialdesignicons-subset.css`, revert that file so the commit does not include a generated artifact:

```cmd
cd /d F:\github\Astrbot\.worktrees\gitdiff-workspace-fullscreen
git checkout -- dashboard/src/assets/mdi-subset/materialdesignicons-subset.css
git status --short --branch
```

Expected: `git status` shows only the two intentionally modified SFCs.

- [ ] **Step 4: Commit the spec, plan, and implementation.**

Stage and commit the design + plan + code as a single commit (or split them if the user prefers):

```cmd
cd /d F:\github\Astrbot\.worktrees\gitdiff-workspace-fullscreen
git add docs/superpowers/specs/2026-07-15-gitdiff-workspace-fullscreen-design.md docs/superpowers/plans/2026-07-15-gitdiff-workspace-fullscreen.md dashboard/src/components/chat/GitDiffSidebar.vue dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue
git commit -m "feat(dashboard): add sidebar and file-preview fullscreen"
git status --short --branch
git log -4 --oneline
```

Expected: a clean commit on `feat/gitdiff-workspace-fullscreen` and no uncommitted changes.

---

### Self-Review Notes (filled in after writing the plan)

- Spec coverage:
  - Two non-persisted refs → covered by Task 1.
  - Mutual exclusion / shared cancel → covered by `isAnyFullscreen` checks in `toggleGlobalFullscreen`/`toggleInnerFullscreen`.
  - Inner button placement in preview header → covered by Task 3 Step 3.
  - Global fullscreen survives page switches → covered by Task 1 Step 2 (removed the exit-on-page-switch rule).
  - Esc cancels whichever is on → covered by `onFullscreenKeyDown`.
  - Body overflow restored on unmount → covered by the watcher + Task 1 Step 1.
- Placeholder scan: no TBD/TODO/"implement later" markers.
- Type consistency: refs and `provide` types (`Ref<boolean>`, `ComputedRef<boolean>`, `() => void`) match between provider and consumer.