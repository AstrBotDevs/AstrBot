# GitDiffSidebar Workspace Fullscreen Design

**Date:** 2026-07-15
**Status:** Approved (revised after first implementation review)

## Goal

Add fullscreen affordances to the GitDiffSidebar so the user can both expand the entire sidebar across the browser viewport **and** expand the currently-previewed file across the viewport, with consistent, mutually-exclusive semantics that match the existing `DocumentManager` pattern.

## Scope

The feature applies to:

- the workspace/file-browser page (`viewMode === "files"`), for both the sidebar-wide and the file-preview expansion;
- all other GitDiffSidebar pages (`diff`, `history`, `docs`) **only** for the sidebar-wide expansion. Once the sidebar-wide fullscreen is active it must persist across page switches and through any page-bound shortcut.

The feature must:

- expand the complete GitDiffSidebar to the browser viewport when global fullscreen is on;
- expand only the selected file's preview area when inner fullscreen is on;
- preserve all existing component state (header, project path strip, view tabs, worktree tabs, search toolbar, file tree, preview pane, pane widths, worktree selection, scroll position, etc.);
- never allow more than one fullscreen mode to be active at a time (no nesting);
- expose a single cancel action on whichever button the user reaches for; the cancel action turns **all** fullscreen off, regardless of which mode is active;
- enter from each entry point only when no fullscreen is currently active;
- exit on `Escape`, regardless of which mode is active;
- prevent page-level scrolling while either mode is active;
- reset when the component is unmounts;
- avoid persisting fullscreen state in `localStorage`.

The feature does not change the browser's native Fullscreen API, file-browser data fetching, pane widths, or the behavior of the diff/history/document pages outside of fullscreen.

## Fullscreen Modes

Two mutually exclusive modes, both non-persistent:

- **globalFullscreen** — the whole GitDiffSidebar expands to viewport; survives page switches.
- **innerFullscreen** — only the currently-previewed file (in `<FileBrowserFilePreview>`) expands to viewport.

Mutual-exclusion rules:

- The two modes can never both be `true`.
- When the user clicks the **top** button (in the sidebar header):
  - if any fullscreen is on, both modes are turned off;
  - otherwise, `globalFullscreen` is turned on.
- When the user clicks the **inner** button (in the file-preview header, visible only when a file is being previewed):
  - if any fullscreen is on, both modes are turned off;
  - otherwise, `innerFullscreen` is turned on.
- When `Escape` is pressed:
  - if any fullscreen is on, both modes are turned off;
  - otherwise, the keydown is ignored (other shortcuts keep working).
- When the sidebar unmounts, both modes are reset and body overflow is restored.

The inner button therefore acts as the "cancel" control for **either** mode while a file is previewed. The user does not have to remember which mode is active — pressing either button always cancels whatever is on.

## Existing Structure

`GitDiffSidebar.vue` owns the four page modes and renders them inside one sidebar shell:

- `files` → `FileBrowserView` → `FileBrowserFilePreview`;
- `diff` → `GitDiffBodyContent`;
- `history` → `GitLogView`;
- `docs` → `DocumentManager`.

The shell is currently rendered as a width-controlled `<aside>` inside a slide transition. Its header and path/view/worktree controls are shared by all four modes. `DocumentManager.vue` already implements fullscreen by teleporting its single root to `body`, applying a fixed viewport layout, handling `Escape`, and locking `document.body` scrolling. `FileBrowserFilePreview.vue` is the analog for the inner button — the button lives in its meta header next to the existing "history" and "copy" buttons, and its own root is teleported when `innerFullscreen` is on.

## Recommended Architecture

Implement the feature in two files only:

1. `dashboard/src/components/chat/GitDiffSidebar.vue`
2. `dashboard/src/components/chat/message_list_comps/FileBrowserFilePreview.vue`

`GitDiffSidebar.vue` changes:

- Add two non-persisted refs: `globalFullscreen` and `innerFullscreen`.
- Add `toggleGlobalFullscreen()` and `toggleInnerFullscreen()` with the mutual-exclusion semantics above.
- Add an `Escape` keydown handler that cancels whichever mode is active.
- Watch both refs (combined) to set `document.body.style.overflow` to `hidden` while either is true and to restore the default value when both are false. Also restore body overflow on unmount.
- Wrap the existing transition/aside tree in a disabled Teleport that activates only when `globalFullscreen` is true. The modifier class `is-fullscreen` is applied to the `<aside>` only when `globalFullscreen` is true.
- Add the top button to the existing `.git-diff-sidebar-actions` group. It is **always** visible (not gated by `viewMode === "files"`). Its icon and `aria-pressed` reflect the **combined** state (`globalFullscreen || innerFullscreen`) so the user sees an "exit" button when either mode is on.
- Remove the prior `watch(viewMode)` exit-on-page-switch rule — `globalFullscreen` must persist across page switches.

Provide/inject contract:

- Provide three values from `GitDiffSidebar`:
  - `globalFullscreen: Ref<boolean>`,
  - `innerFullscreen: Ref<boolean>`,
  - `toggleInnerFullscreen: () => void`.
- Provide also a computed-equivalent ref `isAnyFullscreen = computed(() => globalFullscreen || innerFullscreen)` so the inner component renders the correct icon/aria-label without depending on both refs individually.

`FileBrowserFilePreview.vue` changes:

- Inject the four values above.
- Wrap the existing root (`<div v-else-if="state.kind === 'file'" class="preview-file">`) in a disabled `<Teleport to="body">` that activates only when `innerFullscreen` is true. Apply an `is-fullscreen` class to the wrapper only when `innerFullscreen` is true.
- Add the inner button inside the existing `.preview-file-meta` row, after the "history" and "copy" buttons. The button is gated on `state.kind === "file"`. Its icon, `aria-pressed`, `aria-label`, and `title` all reflect `isAnyFullscreen`. Its click handler calls `toggleInnerFullscreen()`.
- Add a scoped CSS rule `.preview-file.is-fullscreen` that overrides the root's layout to fill the viewport, preserving the meta header at the top and letting the body scroll within the remaining space.

## Interaction and Accessibility

- Both buttons expose the localized label through both `title` and `aria-label`, and reflect the state through `aria-pressed`. Reuse `spcodeProjectLoad.documentManager.fullscreen.enter/exit` already used elsewhere.
- The inner button is only rendered when a file is being previewed (binary, too-large, or non-file states hide it). It is never rendered when the file tree is showing on its own.
- The inner button does not render any per-file action when `state.kind !== "file"` — this matches the existing "history" and "copy" buttons' visibility rules.
- `Escape` cancels whichever fullscreen is on. It does not interfere with normal sidebar shortcuts when no fullscreen is active.
- The existing close button remains available in global fullscreen and continues to emit `update:modelValue`. Closing the sidebar resets both fullscreen modes because the entire component unmounts.

## Layout and Styling

For global fullscreen the existing rule set is reused unchanged:

- `position: fixed`;
- `inset: 0`;
- `width: 100vw` and `height: 100vh`;
- `margin-top: 0`;
- a stacking order above the chat layout;
- the inline `style="width: ...px"` binding is overridden with `width: 100vw !important` so the user-resized sidebar width does not leak into fullscreen;
- the existing flex-column body layout continues to fill the available height, so `FileBrowserView` and the file tree/preview split work without modification.

For inner fullscreen, the preview wrapper becomes a fixed fullscreen flex column:

- `position: fixed`;
- `inset: 0`;
- a stacking order that matches the global fullscreen value;
- `display: flex; flex-direction: column;`;
- the meta header (`preview-file-meta`) stays at the top with `flex-shrink: 0` and gains a subtle bottom border;
- the content area (text view via `<FileBrowserCodeView>` or the binary/too-large placeholder) takes `flex: 1; min-height: 0; overflow: auto;` so the file content scrolls within the viewport.

## Error and Lifecycle Handling

- `onMounted` registers the document-level `keydown` listener.
- `onBeforeUnmount` removes the listener and restores body overflow.
- The body-overflow watcher resets overflow to the default whenever both modes become false, so transitions out of fullscreen never leave the page locked.
- The implementation does not use the native Fullscreen API, because that would introduce browser permission/UI differences and would not match the document-manager pattern.

## Verification

1. `pnpm typecheck` for the dashboard workspace.
2. `pnpm build` for the dashboard workspace.
3. Manual review of the diff for `GitDiffSidebar.vue` and `FileBrowserFilePreview.vue` confirming:
   - the top button is always visible;
   - the inner button is gated on `state.kind === "file"`;
   - the inner Teleport and `is-fullscreen` class only activate for `innerFullscreen`;
   - the global Teleport and `is-fullscreen` class only activate for `globalFullscreen`;
   - no `localStorage` key was added;
   - the previous "exit on `viewMode` change" rule was removed.
4. Behavior checklist (to be exercised in the dev environment):
   - In the workspace with a file selected, clicking the inner button enters inner fullscreen. The preview fills the viewport; the file tree and sidebar header are hidden.
   - Pressing `Escape` exits inner fullscreen.
   - Switching to `diff`, `history`, or `docs` does not exit inner fullscreen on its own, but inner fullscreen cannot be re-entered while on those pages (no inner button is rendered there).
   - Clicking the top button while inner fullscreen is on cancels all fullscreen.
   - With no fullscreen active, clicking the top button enters global fullscreen; the entire sidebar fills the viewport.
   - Switching from `files` to `diff` while global fullscreen is on keeps global fullscreen on, and the diff page renders fullscreen.
   - Clicking the inner button while global fullscreen is on cancels all fullscreen (no nested inner fullscreen).
   - Closing the sidebar (the existing close button) unmounts the component and resets body overflow.

No new automated test harness is required because neither component has covering tests today.