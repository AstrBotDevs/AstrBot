# GitDiffSidebar Workspace Fullscreen Design

**Date:** 2026-07-15
**Status:** Approved

## Goal

Add a fullscreen mode to the GitDiffSidebar workspace page (`viewMode === "files"`) with the same interaction semantics and layout-preserving behavior already used by the document-management page.

## Scope

The feature applies only to the workspace/file-browser page. It must:

- expand the complete GitDiffSidebar to the browser viewport;
- preserve the existing header, project path strip, view tabs, worktree tabs, search toolbar, file tree, preview pane, and all current component state;
- provide an enter/exit control in the sidebar header actions while the workspace page is active;
- exit on `Escape`;
- prevent page-level scrolling while active;
- reset when the component is unmounted or when the user switches away from the workspace page;
- avoid persisting fullscreen state in `localStorage`.

The feature does not change the browser's native fullscreen API, file-browser data fetching, pane widths, or the behavior of the diff/history/document pages.

## Existing Structure

`GitDiffSidebar.vue` owns the four page modes and renders them inside one sidebar shell:

- `files` → `FileBrowserView` (workspace/file browser);
- `diff` → `GitDiffBodyContent`;
- `history` → `GitLogView`;
- `docs` → `DocumentManager` (file/document management).

The shell is currently rendered as a width-controlled `<aside>` inside a slide transition. Its header and path/view/worktree controls are shared by all four modes. `DocumentManager.vue` already implements fullscreen by teleporting its single root to `body`, applying a fixed viewport layout, handling `Escape`, and locking `document.body` scrolling.

## Recommended Architecture

Implement the feature in `dashboard/src/components/chat/GitDiffSidebar.vue` only.

1. Add a non-persisted `isFullscreen` ref plus `toggleFullscreen`, `exitFullscreen`, and an `Escape` key handler.
2. Wrap the existing transition/aside tree in a disabled Teleport:

   ```vue
   <Teleport to="body" :disabled="!isFullscreen">
     <transition name="slide-left">
       <aside ...>
         ...existing sidebar tree...
       </aside>
     </transition>
   </Teleport>
   ```

   With fullscreen disabled, Teleport is a transparent pass-through and the normal chat layout remains unchanged. With fullscreen enabled, the same DOM tree moves to `body`; no duplicate page templates, refs, or state are introduced.
3. Add an `is-fullscreen` class to the existing `<aside>`. Fullscreen CSS overrides the normal sidebar sizing and positioning with `position: fixed`, `inset: 0`, viewport dimensions, zero top margin, and a high stacking order. The width style binding must not prevent the fullscreen width from becoming viewport-wide.
4. Add a header action button that is rendered only for `viewMode === "files"`, uses the existing `mdi-fullscreen` / `mdi-fullscreen-exit` icons, and reuses the localized `spcodeProjectLoad.documentManager.fullscreen.enter/exit` labels already used by the document manager.
5. Watch `isFullscreen` to set `document.body.style.overflow` to `hidden` while active and restore the default value when inactive. Also restore it during unmount so navigation cannot leave the page locked.
6. Watch `viewMode` and exit fullscreen whenever it changes away from `files`. This keeps fullscreen scoped to the workspace page and guarantees the other three pages never appear fullscreen without their own control.

## Interaction and Accessibility

- The button exposes the localized label through both `title` and `aria-label`, and reflects the state through `aria-pressed`.
- `Escape` exits only when workspace fullscreen is active; it does not interfere with normal sidebar shortcuts when inactive.
- The existing close button remains available in fullscreen and continues to emit `update:modelValue` as before.
- Switching worktrees, navigating directories, opening previews, searching, resizing panes, and changing file-browser state all continue to use their existing refs because the same component tree is moved rather than remounted.

## Layout and Styling

Normal mode keeps all existing `.git-diff-sidebar` styles. The fullscreen modifier is limited to the sidebar root:

- `position: fixed`;
- `inset: 0`;
- `width: 100vw` and `height: 100vh`;
- `margin-top: 0`;
- a stacking order above the chat layout;
- the existing flex-column body layout remains responsible for filling the available height.

The inline width used for manual sidebar resizing must be bypassed or overridden in fullscreen. No changes are required in `FileBrowserView.vue`; it already fills the height of its parent and owns the workspace split-pane behavior.

## Error and Lifecycle Handling

There are no new network operations or failure states. Lifecycle cleanup is the important boundary:

- `onMounted` registers the document-level `keydown` listener;
- `onBeforeUnmount` removes it and restores body overflow;
- the fullscreen watcher restores body overflow whenever the state becomes false;
- leaving the `files` mode calls the same exit path before another page is shown.

The implementation should not use the native Fullscreen API, because that would introduce browser permission/UI differences and would not match the existing document-manager behavior.

## Verification

Verification must cover:

1. TypeScript/Vue syntax and lint for `GitDiffSidebar.vue`.
2. Dashboard production build or the repository's focused dashboard check.
3. Manual or component-level review that:
   - the workspace button enters and exits fullscreen;
   - the same file-browser layout is used in both modes;
   - `Escape` exits;
   - body scrolling is restored after exit and unmount;
   - switching to `diff`, `history`, or `docs` exits fullscreen;
   - the sidebar width returns to the user's resized width after exiting.

No new automated test harness is required because this component currently has no covering tests; the focused build/lint checks and diff review are the minimum validation for this UI-only change.
