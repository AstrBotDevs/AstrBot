# Document Manager Fullscreen Review + Raw-View Inline Comments — Design Spec

| Field       | Value                                                    |
| ----------- | -------------------------------------------------------- |
| Spec author | elecvoid243                                              |
| Created at  | 2026-07-14 13:24 (CST)                                   |
| Status      | Implemented. Spec text revised to match landed behavior. |
| Scope       | Frontend-only (Astrbot dashboard). No backend changes.   |

> **Revision note (2026-07-14 17:24):** §3.2 was rewritten after the first
> implementation shipped an "in-sidebar" fullscreen (collapsed the left pane
> inside `.git-diff-sidebar-body`). That gave full-height but never escaped the
> sidebar's horizontal width, so it wasn't a true viewport fullscreen. The
> landed fix matches **DiffPreview** (`spec 2026-06-30-diff-fullscreen-design.md`):
> `<Teleport to="body" :disabled="!isFullscreen">` plus
> `position: fixed; inset: 0; z-index: 9999`. The drawer + rail + Esc behavior
> are unchanged; only the overlay containment model changed. A body-scroll-lock
> watcher (`document.body.style.overflow = "hidden"`) was added to match
> DiffPreview §3.4.

---

## 1. Background & Goals

### 1.1 Current state

The "文档管理 (Documents)" sub-tab (`DocumentManager.vue`, spec
`2026-07-11-document-manager-design.md`) ships with three view modes for the
center pane — `rendered` (MarkdownView), `raw` (plain `<pre>{{ content }}</pre>`),
and `diff` (DiffPreview). The right pane is the git log commit list. The left
pane is the docs directory tree.

**Pain points**

1. **Review is cramped.** When the user wants to read a doc carefully or compare
   it against a historical commit, the left tree + right history split eats too
   much horizontal space. There is no way to enter a focused review mode.
2. **Raw view is featureless.** `<pre>{{ content }}</pre>` has no line numbers
   and no way to leave comments. The user has to switch to "Files" tab to use
   `FileBrowserCodeView` (which already has both), losing the context of the
   document picker and history panel.

### 1.2 Goals

1. Add a **fullscreen review mode** to DocumentManager: hides the left pane by
   default (with a small re-open affordance), keeps the document view + right
   history panel, leaves the center/right split ratio alone.
2. Add **line numbers + inline comments** to the raw view, reusing the existing
   `FileBrowserCodeView` + `useFileComments` implementations. The editor (`edit
mode`) keeps CodeMirror's own line numbers — no change there.

### 1.3 Non-goals (this spec)

- Persisting inline comments across sessions. `useFileComments` is in-memory
  today; comments disappear when the tab closes. Matches FileBrowser behavior.
- Adding inline comments to the `rendered` view (MarkdownView has no line
  concept).
- Adding inline comments to the diff view. `DiffPreview.vue` already has its
  own gutter-comments implementation (spec
  `2026-06-30-diff-inline-comments-design.md`).
- Editing-mode inline comments beyond CodeMirror's existing `lineNumbers()`.
- Approve/reject / threaded conversation features.

---

## 2. Architecture

### 2.1 Layout

Two render-time layouts, only differing in DOM placement (see §3.2 for
the Teleport wrapper that picks one or the other per `isFullscreen` value):

```
┌─ DocumentManager (outer) ──────────────────────────────────────────┐
│                                                                  │
│ Normal (is-fullscreen=false):       Fullscreen (is-fullscreen=true):  │
│ ┌────────┐ ┌────────┬────────┐     ┌─ overlay at <body> ──────────────┐│
│ │ left   │ │ center │ right  │     │ ┌─┐ ┌─────────────┬─────────────┐││
│ │ tree   │ │  view  │ history│     │ │·│ │   center    │   right     │││
│ │        │ │        │        │     │ │·│ │    view     │   history   │││
│ └────────┘ └────────┴────────┘     │ └─┘ └─────────────┴─────────────┘││
│ ↑ inside .git-diff-sidebar-body    │ ↑ direct child of <body>,        ││
│                                     │   position: fixed; inset: 0     ││
│                                     └─────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

- `is-fullscreen=false`: rendered in-place as a child of
  `.git-diff-sidebar-body`. The left pane shows the docs tree, the center
  pane shows the document view, and the right pane shows the git log.
- `is-fullscreen=true`: rendered as a direct child of `<body>` (Teleport).
  The left pane collapses to a 0-width rail with a single chevron button
  (same position as the existing collapse handle). Clicking the chevron
  re-opens the left pane as a 240px drawer; clicking anywhere outside or
  pressing `Esc` collapses it again. The overlay fills the entire viewport
  (browser window), not just the chat sidebar body.
- Center + right panes stay, the user-resizable divider between them is
  preserved in both layouts.

### 2.2 Components / files

| Layer     | File                                                                       | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| --------- | -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Layout    | `dashboard/src/components/chat/message_list_comps/DocumentManager.vue`     | Add `isFullscreen` ref + toggle button + `Esc` keybinding. Wrap the outer `.document-manager` div in `<Teleport to="body" :disabled="!isFullscreen">` so fullscreen renders at `<body>` root; CSS rule `position: fixed; inset: 0; z-index: 9999` then covers the viewport. Add body scroll-lock watcher (`document.body.style.overflow = "hidden"`) released on exit / unmount. Replace `<pre class="document-manager__raw">` with `<FileBrowserCodeView>` when not editing. |
| Reused    | `dashboard/src/components/chat/message_list_comps/FileBrowserCodeView.vue` | No change. Already accepts `highlightedHtml`, `filePath`, `comments`, `activeEditLine`, `activeEditCommentId`, `isDark`.                                                                                                                                                                                                                                                                                                                                                      |
| Reused    | `dashboard/src/composables/useFileComments.ts`                             | No change. Already provides `addComment / commentsByFile / ...`.                                                                                                                                                                                                                                                                                                                                                                                                              |
| Reused    | `dashboard/src/components/chat/CommentsPreviewDialog.vue`                  | No change. Used to show the comment thread on a clicked line.                                                                                                                                                                                                                                                                                                                                                                                                                 |
| Highlight | Inline Shiki markdown render                                               | New small helper (see §3.3).                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| i18n      | `dashboard/src/locales/modules/features/chat/zh-CN.json` (+ others)        | Add keys for the fullscreen toggle button (`全屏` / `退出全屏`) and Esc hint.                                                                                                                                                                                                                                                                                                                                                                                                 |

No backend changes. No new dependencies.

---

## 3. Behavior

### 3.1 Fullscreen toggle

- A new icon button sits to the right of the existing `DocumentViewModeTab`
  (rendered / raw / diff). Icon: `mdi-fullscreen` when off, `mdi-fullscreen-exit`
  when on.
- Clicking toggles `isFullscreen`. No animation requirement (instant flip is
  fine; collapse panels already snap).
- `Esc` key (while focus is anywhere on the page — including inside the
  fullscreen overlay, the comment editor, the preview dialog, or any
  input element) also toggles `isFullscreen` back to `false`.
  Implementation: a `keydown` listener bound at the `document` level
  (not scoped to the teleported overlay, which would not exist on the
  page in the non-fullscreen state). Attached on mount / detached on
  unmount. Only fires when `isFullscreen === true` to avoid hijacking
  Esc in non-fullscreen modals.
- State is **not** persisted to localStorage. Each visit to the sub-tab starts
  with `isFullscreen = false`. (Rationale: fullscreen is a temporary review
  posture; leaving the tab and coming back should not re-trap the user.)
- `Esc` is bound to a _document-level_ `keydown` listener (not scoped to the
  teleported overlay) so it keeps working while the user is interacting
  with the comment editor, the preview dialog, or any input element inside
  the fullscreen overlay.
- `onBeforeUnmount` chains three teardown steps in order: remove the
  keydown listener, restore `document.body.style.overflow` if still
  hidden, and dispose the highlight composable's in-flight work.
  See §3.2 for the layout model + body scroll lock.

### 3.2 Fullscreen layout (Teleport-to-body overlay)

Fullscreen mode moves the entire `<div class="document-manager">` out of its
sidebar-body parent and ports it to `<body>` via Vue's `<Teleport>`. The CSS
on the teleported copy positions it `fixed; inset: 0` so it covers the
entire **browser viewport**, not just the chat sidebar body. When fullscreen
is off the Teleport becomes transparent (`disabled`) and the layout reverts
to its normal in-place rendering with no API change for sibling components.

**Why Teleport (vs the earlier `grid-template-columns: 0 1fr auto` rule):**
the sidebar body holds a fixed-width container and a vertical scrollbar. A
fullscreen-only class on the sidebar's child can never escape that
horizontal containment, so the previous rule only produced "sidebar-pane
fills its width" — not viewport fullscreen. Teleport is the only way to
render the fullscreen overlay above every other layout container on the
page (chat column, header, dialog stack). This mirrors the **DiffPreview**
overlay implementation (spec `2026-06-30-diff-fullscreen-design.md` §3.2),
so the two overlays share the same mount lifecycle, Escape handling, and
z-index layer (`9999`).

**Template (change vs the existing single-file <div> root):**

```vue
<Teleport to="body" :disabled="!isFullscreen">
  <div class="document-manager" :class="{ 'is-fullscreen': isFullscreen }">
    <!-- existing children, untouched -->
  </div>
</Teleport>
```

- `disabled=true` (fullscreen off): Teleport is a transparent pass-through —
  Vue renders the inner `<div>` at its natural position in
  `.git-diff-sidebar-body`. Existing layout / state / refs are untouched.
- `disabled=false` (fullscreen on): Vue moves the inner `<div>` to become a
  direct child of `<body>`; the `<Teleport>` element itself is not in the
  rendered DOM after the move.

`:disabled` (rather than rendering two copies, the way `DiffPreview` does
inside its `<Teleport>`) is chosen because DocumentManager's children —
`FileBrowserCodeView`, `DocumentTreePanel`, `DocumentHistoryPanel`,
`DocumentEditor`, etc. — are refs and state-heavy. Keeping a single live
instance means state (current file, view mode, split percentages, comments,
edit buffer) survives the fullscreen toggle with zero extra plumbing.

**CSS rule (applied to the teleported copy, only when `is-fullscreen=true`):**

```css
.document-manager.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  width: 100%;
  height: 100%;
  background: rgb(var(--v-theme-background));
}
```

`position: fixed` resets the containing block for any absolutely-positioned
descendants (the left-rail button, the drawer, the comments dialog) so they
anchor to the viewport rather than the original sidebar body. The
inner `.document-manager__body` flex row and `.document-manager__right`
flex column layout rules are unchanged, since the document-manager element
itself is still the flex parent for its children.

**Left pane behavior (unchanged from earlier draft):** `.document-manager__pane-left`
is `v-show="!isFullscreen"`. The left pane's collapse affordance stays
mounted (it lives on the divider, not inside the left pane). When
`is-fullscreen=true` the chevron button (`__left-rail`) opens a 240 px
overlay drawer (`__left-drawer`) anchored to the left edge of the viewport.
The drawer body and the backdrop close it via single click handlers — no
`document` listener needed because the fullscreen overlay is the topmost
element on the page.

**Resize behavior:** the `.document-manager__body` flex row keeps its
existing `.treeSplit.percent` / `.historySplit.percent` percentages. When
the left pane hides, the body simply has no left child; the center and
right panes re-divide the available width via their existing divider rule
(we did not touch flex-basis math).

**Body scroll lock** (matches DiffPreview spec §3.4): while fullscreen is
on we set `document.body.style.overflow = "hidden"` so the chat page
itself does not scroll behind the overlay. Released on `isFullscreen` flip
back to false OR on `onBeforeUnmount` if the user navigates away while
fullscreen is still on:

```ts
watch(isFullscreen, (v) => {
  document.body.style.overflow = v ? "hidden" : "";
});

onBeforeUnmount(() => {
  if (isFullscreen.value) {
    document.body.style.overflow = "";
  }
  // ... existing dispose chain
});
```

We don't snapshot-and-restore the prior `body.style.overflow` value because
no other component in the chat page is documented to lock body scroll while
DocumentManager is mounted. If a future component adds such behavior, this
rule should be revisited (e.g. swap for a `data-attribute` + `body.dataset`
counter) to avoid the "last one wins" overwrite.

### 3.3 Raw view with line numbers + inline comments

- When `viewMode === "raw"` **and** `editMode === false` (i.e. the user is
  viewing, not editing), replace:

  ```html
  <pre class="document-manager__raw">{{ content }}</pre>
  ```

  with:

  ```html
  <FileBrowserCodeView
    :highlighted-html="rawHighlightedHtml"
    :file-path="rawFilePath"
    :comments="commentsForRaw"
    :active-edit-line="activeEditLine"
    :active-edit-comment-id="activeEditCommentId"
    :is-dark="isDark"
    @request-add="onRequestAddComment"
    @request-edit="onRequestEditComment"
  />
  ```

  where `commentsForRaw`, `activeEditLine`, `activeEditCommentId` come from a
  per-file `useFileComments(rawFilePath)` instance scoped to
  `DocumentManager`.

- When `viewMode === "raw"` **and** `editMode === true`, the existing CodeMirror
  editor (via `DocumentEditor.vue` → `CodemirrorHost.vue`) renders. No change.

- **Highlight pipeline**: DocumentManager.vue gains a small helper
  `highlightMarkdown(content: string): string` that runs the existing
  Shiki pipeline (markdown language) synchronously and returns the HTML. The
  same pipeline is what `FileBrowserFilePreview` already uses for `.md` files;
  if a shared helper exists we re-export it, otherwise a 30-line local copy is
  acceptable. The output is memoized on `(content, isDark)`.

- **`rawFilePath`**: must be unique per file so `useFileComments` partitions
  correctly. Use the docsRoot-relative path (`selectedDoc.value` —
  e.g. `docs/123456.md`). This is consistent with how FileBrowser partitions
  comments.

- **Hovered line + comment click**: `FileBrowserCodeView` already emits
  `request-add` (line number) and `request-edit` (comment id). DocumentManager
  wires these to `useFileComments().addComment({...})` and
  `CommentsPreviewDialog` open respectively. Identical to FileBrowser wiring.

- **Empty content**: if `rawHighlightedHtml` is empty (file is empty or
  Shiki threw), fall back to a small "空文件" placeholder. Do NOT silently
  render an empty code view with no UI.

### 3.4 Right history panel

- No structural change. When `is-fullscreen` is on, the history panel
  occupies a larger horizontal share automatically because the left pane is
  gone. The user can still drag the history divider to widen / narrow it.

### 3.5 Diff view

- No change. `DiffPreview.vue` already has its own gutter-comments UX.

---

## 4. State surface

```ts
// DocumentManager.vue
const isFullscreen = ref(false);

// Per-file comments instance (re-keyed on selectedDoc so file switches
// don't leak comments across files). Same pattern as FileBrowser's
// `useFileComments(filePath)` usage.
const commentsStore = useFileComments(rawFilePath);
const {
  commentsForRaw,
  activeEditLine,
  activeEditCommentId,
  onRequestAddComment,
  onRequestEditComment,
} = bindFileCommentsUI(commentsStore);

// Esc handler — does NOT call stopPropagation / preventDefault so other
// components (the comment editor's own Esc-cancel, the preview dialog)
// can still handle Esc for their own purposes. We only react when
// fullscreen is on, so non-fullscreen Esc bindings are unaffected.
function onKeyDown(e: KeyboardEvent) {
  if (e.key === "Escape" && isFullscreen.value) {
    isFullscreen.value = false;
    leftDrawerOpen.value = false;
  }
}
onMounted(() => document.addEventListener("keydown", onKeyDown));
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeyDown);
  if (isFullscreen.value) {
    document.body.style.overflow = "";
  }
});
```

- `rawFilePath` is a `computed<string>` that returns
  `selectedDoc.value ?? ""`. When `selectedDoc` is null the FileBrowserCodeView
  is not rendered (already guarded by the existing `v-if="selectedDoc"`).

---

## 5. Error handling

| Scenario                                                       | Behavior                                                                                                                                                                                                                                                                                                                          |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Shiki render fails / throws                                    | Catch in the memoized helper, log to console, fall back to a `<pre>` showing the raw text (no line numbers, no comments). No error banner — markdown rendering failure should be invisible to the user.                                                                                                                           |
| File content very large (> 1 MB)                               | Already capped by `useSpcodeGitFile` / `FileBrowserFilePreview` upstream. DocumentManager just displays whatever it receives. If the file is binary / `is_binary=true` (historical view), show a "二进制文件,无法显示" placeholder instead of FileBrowserCodeView.                                                                |
| Fullscreen + Esc pressed inside an input (e.g. comment editor) | Handler does **not** call `stopPropagation` or `preventDefault`. The comment editor's own Esc-cancel logic runs as today; the fullscreen handler still toggles fullscreen off in parallel. Net effect: Esc closes both the editor and fullscreen, which is what the user expects (one keypress, two closable layers, both close). |
| Comments from another file leak into this file                 | Prevented by keying `useFileComments` on `rawFilePath` (docsRoot-relative).                                                                                                                                                                                                                                                       |

---

## 6. Testing

| Layer         | What to test                                                                                                                                                                                                                                                                                                                                                                  |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit (vitest) | `isFullscreen` toggles on button click + Esc keydown (component-level test with `@vue/test-utils`).                                                                                                                                                                                                                                                                           |
| Unit (vitest) | `rawFilePath` computed reflects `selectedDoc`.                                                                                                                                                                                                                                                                                                                                |
| Manual        | Toggle fullscreen: the document-manager overlay leaves the chat sidebar body and fills the **browser viewport** (above the chat column, header, dialog stack). Left pane is hidden; chevron rail at the left edge opens a 240px drawer. Outside-click closes the drawer. Esc exits fullscreen AND closes the drawer. Refresh tab — fullscreen off (verifies non-persistence). |
| Manual        | Open a markdown doc → switch to `raw` view → see line numbers on the left gutter. Hover a line → "+" chip appears. Click → comment editor pops. Save → comment dot appears on the line. Click dot → `CommentsPreviewDialog` opens. Switch to another doc → comments for the first doc do not appear. Switch back → comments restored.                                         |
| Manual        | Edit mode (`编辑` button) → CodeMirror renders, line numbers show as today. Toggle fullscreen from edit mode → same behavior, no regression.                                                                                                                                                                                                                                  |
| Manual        | Diff view → existing gutter comments still work.                                                                                                                                                                                                                                                                                                                              |

No new backend contract. No contract changes to existing endpoints.

---

## 7. Open questions / risks

1. **Comments are in-memory only.** Users will likely expect them to persist
   across sessions. This spec explicitly does **not** ship persistence. A
   follow-up spec will need a backend store (likely a JSON sidecar in the docs
   root) and a small set of CRUD endpoints. Out of scope here.
2. **Fullscreen CSS collision.** The existing `.is-expanded` class (used when
   both `isLeftPaneCollapsed && isHistoryCollapsed`) is set on the right pane
   (`__right`), not on the outer `.document-manager` element, so the new
   `.is-fullscreen` class on the outer element (which is now teleported to
   `<body>` when active) cannot collide. Verified by reading
   `DocumentManager.vue` template and the right-pane binding around line 794.
3. **`useFileComments` and file-path collisions with FileBrowser.** If the user
   has the same file open in both the Documents sub-tab and the Files sub-tab,
   the comment stores are independent instances today. This is the existing
   behavior across both surfaces; we do not unify them in this spec.

---

## 8. Migration / rollout

- Single feature branch, single PR. No DB migration. No backend deploy.
- i18n keys added (zh-CN + en-US): `documentManager.fullscreen.enter`,
  `documentManager.fullscreen.exit`, `documentManager.fullscreen.openDrawer`.
  Russian (`ru-RU`) is optional — it falls back to en-US today via
  `useModuleI18n`'s standard fallback chain. Other locales get English
  fallback if the key is missing (existing behavior of `useModuleI18n`).

---

## 9. Alternatives considered (and why rejected)

1. **`<v-dialog>` fullscreen modal** — adds focus-trap boilerplate, breaks
   DocumentManager's natural layout flow, and the user's split ratio has to be
   restored when the dialog closes. The Teleport-to-body overlay is lighter
   and keeps the live DOM tree (current file, view mode, comments, edit
   buffer) intact across toggles.
2. **Route-based fullscreen** (`/documents/fullscreen/...`) — too heavy for a
   transient review posture; needs router changes and back-button handling.
3. **Persist `isFullscreen` to localStorage** — user explicitly rejected this:
   fullscreen is a temporary review state; leaving the sub-tab and coming back
   should not re-trap the user.
4. **Re-implement raw-view line numbers + comments from scratch** — would
   duplicate ~300 lines of FileBrowserCodeView / useFileComments logic. The
   whole point is reuse.
