<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.6 -->
<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { pluginExtensionApi } from "@/api/v1";
import type { SpcodeFileBrowserRawResponse } from "@/composables/parseSpcodeFileBrowser";

const props = defineProps<{
  currentPath: string;
  /** Root path; null when project not loaded. */
  rootPath: string | null;
  /**
   * 2026-07-09: passed through from the file-browser's `previewPath`
   * so the leaf segment can pick the right icon. When `previewPath`
   * is non-null, the leaf represents the file being previewed and
   * renders a document icon; otherwise the leaf is the directory the
   * user is browsing and renders a folder icon to match its parents.
   */
  previewPath?: string | null;
  /**
   * 2026-07-02: pass through the dashboard's dark-mode flag so the
   * path bar's separator + hover tones map correctly to dark theme.
   */
  isDark?: boolean;
}>();
// 2026-07-20: the event signature switched from `(path: string)` to
// `(payload: { dirPath, previewPath })`. The payload shape mirrors
// the parent's `onFileBrowserNavigate` (FileBrowserView) and lets a
// single emit express both "navigate to this directory" (previewPath
// = null) and "navigate to the parent AND preview this file"
// (previewPath = the file). Without the file slot, the file case
// silently dropped into the empty-page bug — the file browser fetch
// would try to list a file as a directory, the directory listing
// would error out, and the user would see the breadcrumb + the
// "select from left" hint with no way to recover.
const emit = defineEmits<{
  (
    e: "navigate",
    payload: { dirPath: string; previewPath: string | null },
  ): void;
}>();
const { tm } = useModuleI18n("features/chat");

// 2026-07-09: leaf is "the file currently being previewed" only when
// the caller has a non-null previewPath. In all other cases the leaf
// is just another folder the user is browsing through, so it shares
// the parent folder icon and only changes its color (no border, no
// background, no bold — those treatments all proved visually heavy
// during the 2026-07-08 / 2026-07-09 iterations).
const leafIsFile = computed<boolean>(() => !!props.previewPath);

interface Segment {
  name: string;
  path: string;
  isRoot: boolean;
}

// Split currentPath into clickable segments. root segment is special
// (label = "Project root" / "项目根" / "Корень проекта").
//
// 2026-07-02 revision: case-insensitive root match on Windows, plus a
// "render the basename anyway" fallback when currentPath is outside
// the root. The previous strict equality check left the breadcrumb
// completely hidden when the search-result absolute path and the
// worktree root disagreed by even one case character (very common on
// Windows where the worktree path can be "C:/work/Repo" and the
// search result path can be "c:/work/repo/astrabot/cli/main.py" —
// different drive case). Hiding the breadcrumb was unacceptable
// because the user lost path navigation entirely, so we now render
// the basename as a single segment in that case (and still emit
// `navigate(currentPath)` so clicking it scrolls the file browser
// back to that directory).
function buildSegments(current: string, root: string | null): Segment[] {
  if (!current) return [];
  const normCurrent = current.replace(/\\/g, "/");

  // Basename fallback (used both for the "no root" case and for the
  // "current is outside root" case). Centralised so the two code
  // paths stay in sync.
  const basenameFallback = (): Segment[] => {
    const parts = normCurrent.split("/").filter(Boolean);
    if (parts.length === 0) return [];
    const basename = parts[parts.length - 1];
    return [{ name: basename, path: normCurrent, isRoot: false }];
  };

  if (!root) return basenameFallback();

  const normRoot = root.replace(/\\/g, "/").replace(/\/$/, "");
  // Case-insensitive comparison on Windows where the drive letter or
  // path segments can differ in case between the worktree root and
  // the absolute path returned by the search backend.
  const ci = (a: string, b: string): boolean =>
    a === b || a.toLowerCase() === b.toLowerCase();

  if (ci(normCurrent, normRoot)) {
    return [
      {
        name: tm("spcodeProjectLoad.fileBrowser.breadcrumbRoot"),
        path: normRoot,
        isRoot: true,
      },
    ];
  }
  if (ci(normCurrent.slice(0, normRoot.length + 1), normRoot + "/")) {
    const relative = normCurrent.slice(normRoot.length + 1);
    const parts = relative.split("/").filter(Boolean);
    const result: Segment[] = [
      {
        name: tm("spcodeProjectLoad.fileBrowser.breadcrumbRoot"),
        path: normRoot,
        isRoot: true,
      },
    ];
    let acc = normRoot;
    for (const p of parts) {
      acc += "/" + p;
      result.push({ name: p, path: acc, isRoot: false });
    }
    return result;
  }
  // currentPath is outside root (or the root comparison still failed
  // despite case-folding — e.g. UNC vs drive-letter, or a symlink
  // boundary). Fall back to the basename so the user always sees
  // SOMETHING and can click it to re-anchor the file browser on
  // this path.
  return basenameFallback();
}

const segments = computed<Segment[]>(() => {
  return buildSegments(props.currentPath, props.rootPath);
});

// ── Inline path-edit (2026-07-20, elecvoid243) ────────────────────
// Click the leaf (the "you are here" segment) to replace the
// breadcrumb with a single text input. The user can then type any
// path — absolute (C:/..., /...) or project-relative (foo/bar) —
// and press Enter to jump there, matching the click-to-segment
// behavior of the existing breadcrumb. Escape or blur cancels.
//
// Why drive this off the leaf rather than the whole nav: the
// segments are already click targets for navigation, and turning
// the empty nav background into a click target felt invisible
// (no visual affordance). The leaf is the natural "where I am"
// anchor — the same pattern macOS Finder and Windows Explorer
// use — and the `cursor: text` + subtle hover wash below tells
// the user it is interactive.
//
// Resolution rules (see commitEdit for full logic):
//   1. empty / whitespace → no-op (stay on current path)
//   2. absolute path (leading /, \, or <Drive>:\) → use as-is
//      after backslash → forward-slash normalisation
//   3. anything else → resolve against rootPath, treating the
//      input as project-relative (so `dashboard/src` works the
//      same whether the active worktree is the main repo or a
//      .worktrees/feature-x checkout)
//   4. rootPath missing → cancel (cannot resolve anything)
//
// 2026-07-20 path-relative-only: rule (2) was tightened to
// "must be project-relative". The original commitEdit happily
// navigated to "C:/Windows/System32" if the user typed it, which
// silently broke the "this view shows the project" mental model
// and let users poke at whatever their backend had access to.
// We now reject (with an inline error, no navigation):
//   - any leading "/" (POSIX absolute)
//   - any "C:/" / "C:\" style drive-letter absolute
//   - any ".." segment, which would let the user escape root
//     even from a relative-looking input (e.g. "foo/../../etc")
// `..` is a per-segment match (split on "/"), so "foo..." and
// "..foo" are still valid filenames — only the literal ".."
// segment is rejected. Validation lives in validatePath() so
// commitEdit stays focused on the navigation flow.
const isEditing = ref<boolean>(false);
const isResolving = ref<boolean>(false);
const inputValue = ref<string>("");
// 2026-07-20: last validation failure message shown below the
// input. Null when the user is typing a fresh value or when the
// previous commit succeeded. Cleared on every keystroke (see
// the watch below) so a stale red bar never lingers after the
// user starts typing a corrected version.
const inputError = ref<string | null>(null);
const inputRef = ref<HTMLInputElement | null>(null);
// 2026-07-20: in-flight type-detection request. Cancelled when the
// user starts a new commit so the stale response cannot navigate
// to a path the user has already moved on from.
let resolveAbort: AbortController | null = null;

// Clear the validation error the moment the user edits again.
// We don't want a stale "absolute paths not allowed" red bar to
// linger while the user is mid-typing a corrected version —
// re-validation only happens on the next commit.
watch(inputValue, () => {
  if (inputError.value) inputError.value = null;
});

function startEdit(): void {
  // Pre-fill with the path the user is currently looking at,
  // normalised to forward slashes. The input accepts both, but
  // forward slashes are the canonical form on every platform
  // here (the file-browser fetch normalises either way).
  inputValue.value = (props.currentPath || "").replace(/\\/g, "/");
  inputError.value = null;
  isEditing.value = true;
  // Focus + select on next tick so the input has mounted and the
  // selection is fully visible before the user starts typing.
  // Without nextTick the .focus() call would race the v-if and
  // the cursor would land before the value was painted.
  void nextTick(() => {
    inputRef.value?.focus();
    inputRef.value?.select();
  });
}

function cancelEdit(): void {
  isEditing.value = false;
  isResolving.value = false;
  inputValue.value = "";
  inputError.value = null;
  // 2026-07-20: also drop any in-flight type-detection request so
  // it cannot fire a navigate after the user has moved on (e.g.
  // typed a new path while the first API call was still in flight).
  resolveAbort?.abort();
  resolveAbort = null;
}

/** Compute the parent directory of a path. POSIX + Windows aware —
 *  matches the helper of the same name in FileBrowserView so file
 *  paths the user types in the breadcrumb route to the same parent
 *  string the tree-click path takes. */
function parentOf(p: string): string {
  const isWindows = p.includes("\\");
  const lastSep = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  if (lastSep <= 0) return isWindows ? "\\" : "/";
  return p.slice(0, lastSep);
}

/** Result of validating a user-typed breadcrumb path. The
 *  discriminated union lets commitEdit's caller (commitEdit
 *  itself) split the two cases without an extra `if (!ok)`
 *  branch hiding the success path. */
type PathValidation =
  | { ok: true; resolved: string }
  | { ok: false; reason: string };

/** Validate a raw user-typed path and, on success, return the
 *  absolute path the file-browser API will accept. Rejection
 *  reasons are localised via tm() so the error string flows
 *  through i18n without a separate mapping layer.
 *
 *  See the path-relative-only comment block on isEditing for
 *  the full rule set. The short version: any input that would
 *  resolve to a path outside `rootPath` is rejected. */
function validatePath(raw: string): PathValidation {
  const normalised = raw.replace(/\\/g, "/").trim();
  // No need to surface a "path is empty" error here —
  // commitEdit treats whitespace-only input as a cancel, so
  // this branch should never run for that case. Defensive
  // guard anyway in case validatePath is called directly
  // from a future site.
  if (!normalised) {
    return {
      ok: false,
      reason: tm("spcodeProjectLoad.fileBrowser.pathInput.error.empty"),
    };
  }
  // POSIX absolute ("/...") or Windows drive-letter absolute
  // ("C:/...", "C:\..." — backslashes were already normalised
  // above, so the regex only needs to match "C:/" or "C:").
  if (
    normalised.startsWith("/") ||
    /^[a-zA-Z]:\/?/.test(normalised)
  ) {
    return {
      ok: false,
      reason: tm("spcodeProjectLoad.fileBrowser.pathInput.error.absolute"),
    };
  }
  // ".." as a path segment is the one and only way to escape
  // the project root without using an absolute prefix, so
  // catch it explicitly. Split on "/" (not "\" — already
  // normalised) and match the exact string "..", not
  // filenames that merely start with "..".
  if (normalised.split("/").some((seg) => seg === "..")) {
    return {
      ok: false,
      reason: tm("spcodeProjectLoad.fileBrowser.pathInput.error.parentSegment"),
    };
  }
  if (!props.rootPath) {
    // Same defensive default as the old "fall back to the
    // input verbatim" branch — the file-browser endpoint will
    // then return path_not_found and the user sees the
    // standard error UI. We still treat it as a validation
    // failure (no navigation) because the input is
    // unsatisfiable as a project-relative path.
    return {
      ok: false,
      reason: tm("spcodeProjectLoad.fileBrowser.pathInput.error.noRoot"),
    };
  }
  // Strip any leading "./" so the joined path doesn't carry a
  // redundant prefix; keep internal "./" (e.g. "foo/./bar")
  // intact — it's not a security concern and the backend
  // resolves it the same as "foo/bar".
  const cleaned = normalised.replace(/^\.\//, "");
  const joined =
    props.rootPath.replace(/[\\/]+$/, "") + "/" + cleaned;
  return { ok: true, resolved: joined };
}

async function commitEdit(): Promise<void> {
  if (isResolving.value) return; // a previous commit is still in flight
  const raw = inputValue.value.trim();
  if (!raw) {
    cancelEdit();
    return;
  }
  // 2026-07-20 path-relative-only: refuse to navigate outside
  // the project. The error string from validatePath goes into
  // inputError (shown below the input); the user stays in
  // edit mode so they can correct the value without having to
  // click the leaf again.
  const validation = validatePath(raw);
  if (!validation.ok) {
    inputError.value = validation.reason;
    return;
  }
  const resolved = validation.resolved;
  // Exit edit mode immediately so the user sees the breadcrumb
  // collapse back to the segment row. The resolving state on the
  // input keeps the input mounted + disabled while we ask the
  // backend what kind of path this is, so the user can still
  // see what they typed and knows work is happening.
  isResolving.value = true;
  resolveAbort?.abort();
  resolveAbort = new AbortController();

  try {
    const resp = await pluginExtensionApi.get<SpcodeFileBrowserRawResponse>(
      "spcode/file-browser",
      { params: { path: resolved }, signal: resolveAbort.signal },
    );
    const data = resp.data?.data;
    if (data?.type === "file") {
      // 2026-07-20 file-vs-dir: the user typed a file path. Emit
      // the same shape <FileTreeList> uses for file clicks — the
      // parent (parentOf(resolved)) becomes the directory listing
      // on the left, and the file itself is previewed on the
      // right. The right-pane preview also opens the per-file
      // git-history pane (it's hidden by default when no file is
      // previewed, but stays visible once the user has opened it
      // — matches DocumentManager's behavior).
      cancelEdit();
      emit("navigate", {
        dirPath: parentOf(resolved),
        previewPath: resolved,
      });
      return;
    }
    // directory / symlink / unknown — treat as a directory. The
    // file-browser fetch will follow the symlink (or return an
    // error if the target is missing); either way the user lands
    // on a directory listing, which is the safe default.
    cancelEdit();
    emit("navigate", { dirPath: resolved, previewPath: null });
  } catch (err) {
    // Network error, AbortError, or path-not-found: fall through
    // to the directory navigation so the user at least sees the
    // file-browser's standard error UI (the "path_not_found"
    // empty state). Cancel first so the resolving state doesn't
    // linger.
    const isAbort =
      (err as { name?: string })?.name === "CanceledError" ||
      (err as { code?: string })?.code === "ERR_CANCELED";
    cancelEdit();
    if (isAbort) return;
    emit("navigate", { dirPath: resolved, previewPath: null });
  }
}
</script>

<template>
  <nav
    v-if="segments.length > 0 || isEditing"
    class="file-browser-breadcrumb"
    :class="{ dark: props.isDark, 'is-editing': isEditing }"
  >
    <!-- 2026-07-20: inline path-edit. Replaces the whole segment
         row with a single text input. The input takes the same
         vertical space as a segment row (padding matches), so
         the bar height stays identical and the file tree below
         does not shift. Auto-focus + select on enter so the user
         can immediately type a replacement. -->
    <input
      v-if="isEditing"
      ref="inputRef"
      v-model="inputValue"
      type="text"
      class="breadcrumb-path-input"
      :class="{ 'is-resolving': isResolving, 'is-error': !!inputError }"
      spellcheck="false"
      autocomplete="off"
      autocorrect="off"
      autocapitalize="off"
      :readonly="isResolving"
      :placeholder="tm('spcodeProjectLoad.fileBrowser.pathInputPlaceholder')"
      :aria-label="tm('spcodeProjectLoad.fileBrowser.pathInputPlaceholder')"
      :aria-invalid="!!inputError"
      :aria-describedby="inputError ? 'breadcrumb-path-input-error' : undefined"
      @keydown.enter.prevent="commitEdit"
      @keydown.escape.prevent="cancelEdit"
      @blur="cancelEdit"
    />
    <!-- 2026-07-20: validation error string. Mounted on the
         breadcrumb row (not floated below) so the bar height
         grows by exactly one line of text and the file tree
         below shifts down by a predictable amount instead of
         popping. id matches the input's aria-describedby for
         screen-reader users. role="alert" + aria-live="polite"
         announces the change as soon as validation fails. -->
    <span
      v-if="inputError"
      id="breadcrumb-path-input-error"
      class="breadcrumb-path-input-error"
      role="alert"
      aria-live="polite"
      >{{ inputError }}</span
    >
    <template v-else>
      <template v-for="(seg, i) in segments" :key="seg.path">
        <!--
          2026-07-09 redesign — macOS Finder Path Bar style:
          - parents are real <button>s (clickable, focusable, keyboard
            accessible); their icon disambiguates "this is a folder you
            can navigate into"
          - the leaf is a plain <span> (no button affordance; it is
            the user's "current location" and clicking it would be a
            no-op, so we don't pretend it can be clicked)
          - the chevron `›` separates segments; rotated 0deg (already
            points right in the chosen glyph) and styled muted
          - when there is only one segment and it IS the root, the
            leaf still gets the file-vs-folder icon distinction via
            previewPath; the breadcrumb simply renders the root alone
        -->
        <button
          v-if="i < segments.length - 1"
          type="button"
          class="breadcrumb-segment"
          :title="seg.path"
          @click="emit('navigate', { dirPath: seg.path, previewPath: null })"
        >
          <v-icon :size="13" class="breadcrumb-segment-icon">{{
            seg.isRoot ? "mdi-folder" : "mdi-folder-outline"
          }}</v-icon>
          <span class="breadcrumb-segment-name">{{ seg.name }}</span>
        </button>
        <!-- 2026-07-20: leaf is now a <button> so it is keyboard-
             focusable and announces itself as interactive. The
             button's only action is to swap into edit mode — the
             same affordance the previous plain <span> had, just
             with a real role so screen readers + Tab navigation
             pick it up. The visual styling is identical to the
             old span (color/weight/padding). -->
        <button
          v-else
          type="button"
          class="breadcrumb-leaf"
          :title="
            tm('spcodeProjectLoad.fileBrowser.pathInputTooltip') +
            ' — ' +
            seg.path
          "
          @click="startEdit"
        >
          <v-icon :size="13" class="breadcrumb-leaf-icon">{{
            leafIsFile
              ? "mdi-file-document-outline"
              : seg.isRoot
              ? "mdi-folder"
              : "mdi-folder-outline"
          }}</v-icon>
          <span class="breadcrumb-leaf-name">{{ seg.name }}</span>
        </button>
        <span
          v-if="i < segments.length - 1"
          class="breadcrumb-sep"
          aria-hidden="true"
          >›</span
        >
      </template>
    </template>
  </nav>
</template>

<style scoped>
/* ── 2026-07-09 redesign — macOS Finder Path Bar ──────────────────
   Three prior iterations (background wash, primary bottom-border,
   then 3px left-accent + 8% wash) all left the leaf feeling
   visually heavy in this sidebar. This rewrite drops the chrome
   entirely: the bar is just a hairline divider with system-font
   text, folder/file icons, and a muted chevron. The leaf is
   emphasized purely through color + medium weight — no background
   fill, no border, no shadow. The result reads as a flat
   navigation strip rather than a card or banner. */
.file-browser-breadcrumb {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1px;
  padding: 9px 12px;
  font-size: 12.5px;
  font-family: inherit;
  line-height: 1.4;
  /* No background. A single 1px hairline below separates the
     bar from the file tree beneath; using the same chat-border
     token as the sidebar chrome keeps the visual rhythm aligned. */
  border-bottom: 1px solid
    var(--chat-border, rgba(var(--v-theme-on-surface), 0.08));
  /* The bar can wrap on narrow widths (420px sidebar + deep path);
     align the wrapped rows consistently. */
  row-gap: 2px;
}

/* Clickable parent: a quiet button that becomes obvious on hover
   through a primary-tinted 8% wash. The icon inherits the text
   color so the entire row tints together on hover (not just the
   text). max-width + ellipsis prevents a single deep folder name
   from blowing out the layout. */
.breadcrumb-segment {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 200px;
  padding: 3px 8px;
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  color: rgba(var(--v-theme-on-surface), 0.62);
  transition:
    background 0.12s ease,
    color 0.12s ease;
  overflow: hidden;
}
.breadcrumb-segment:hover {
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
}
.breadcrumb-segment:focus-visible {
  outline: 2px solid rgba(var(--v-theme-primary), 0.45);
  outline-offset: 1px;
}
.breadcrumb-segment-icon {
  color: rgba(var(--v-theme-on-surface), 0.45);
  flex-shrink: 0;
  transition: color 0.12s ease;
}
.breadcrumb-segment:hover .breadcrumb-segment-icon {
  color: rgb(var(--v-theme-primary));
}
.breadcrumb-segment-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* Leaf ("you are here"): button so it is keyboard-focusable and
   announces itself as interactive. Visual emphasis stays the same
   as the previous <span> (primary color + medium weight, no fill /
   border / shadow). The hover wash + cursor: text tells the user
   clicking will let them edit the path. user-select stays "text"
   so the leaf is still drag-selectable for copy. */
.breadcrumb-leaf {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 240px;
  padding: 3px 6px;
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: text;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  font-weight: 500;
  color: rgb(var(--v-theme-primary));
  user-select: text;
  overflow: hidden;
  transition: background 0.12s ease;
}
.breadcrumb-leaf:hover {
  background: rgba(var(--v-theme-primary), 0.1);
}
.breadcrumb-leaf:focus-visible {
  outline: 2px solid rgba(var(--v-theme-primary), 0.45);
  outline-offset: 1px;
}

/* 2026-07-20: inline path-edit input. Replaces the whole segment
   row when active. Sized to match the bar's vertical rhythm
   (padding 9px 12px on .file-browser-breadcrumb + ~22px content
   height) so the bar does not jump on mode swap. The 1px primary
   outline on focus is a deliberate departure from the segment
   focus ring — the input is the primary interactive element while
   it is mounted, so a slightly stronger ring (vs the segments'
   2px outline) helps signal that. */
.breadcrumb-path-input {
  flex: 1 1 100%;
  min-width: 0;
  padding: 4px 8px;
  background: var(--chat-input-bg, rgb(var(--v-theme-surface)));
  border: 1px solid
    var(--chat-border, rgba(var(--v-theme-on-surface), 0.16));
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
    "Liberation Mono", monospace;
  font-size: 12.5px;
  line-height: 1.4;
  color: rgb(var(--v-theme-on-surface));
  outline: none;
  transition:
    border-color 0.12s ease,
    box-shadow 0.12s ease;
}
.breadcrumb-path-input:focus {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), 0.18);
}
.breadcrumb-path-input::placeholder {
  color: rgba(var(--v-theme-on-surface), 0.42);
  font-family: inherit;
  font-style: italic;
}
/* 2026-07-20: in-flight state while we ask the file-browser
   endpoint whether the typed path is a file or directory.
   cursor: wait is the universal "I'm doing something" signal;
   the slight primary-tinted background is subtle enough not to
   fight the focus ring but unmistakable on the bar. We use
   `readonly` (not `disabled`) on the input so the user can
   still press Escape to cancel, or click outside to blur, while
   the request is in flight — `disabled` would suppress those
   keyboard / blur events entirely. */
.breadcrumb-path-input.is-resolving {
  cursor: wait;
  background: rgba(var(--v-theme-primary), 0.05);
  border-color: rgba(var(--v-theme-primary), 0.4);
  color: rgba(var(--v-theme-on-surface), 0.7);
}
/* 2026-07-20 path-relative-only: validation failure state. The
   red border + small helper line below tells the user the
   value was rejected; the input stays in edit mode so they
   can fix the typo without clicking the leaf again. Border
   colour uses the theme's error token so it reads correctly
   in both light and dark modes without a separate override. */
.breadcrumb-path-input.is-error {
  border-color: rgb(var(--v-theme-error));
}
.breadcrumb-path-input.is-error:focus {
  /* Slightly thicker focus ring so the error state is still
     visible when the input is focused (the focus halo can
     otherwise drown out a 1px red border). */
  box-shadow: 0 0 0 2px rgba(var(--v-theme-error), 0.18);
}
.breadcrumb-path-input-error {
  /* Single-line helper text below the input. The font size
     matches the rest of the breadcrumb label so the bar's
     vertical rhythm doesn't shift by a noticeable amount.
     `flex-basis: 100%` makes the span drop to a new line in
     the breadcrumb's flex row (the input is a flex item that
     already claims the rest of the width). */
  flex-basis: 100%;
  font-size: 11px;
  line-height: 1.3;
  color: rgb(var(--v-theme-error));
  padding: 2px 4px 0;
  font-style: normal;
}
.breadcrumb-leaf-icon {
  color: rgb(var(--v-theme-primary));
  flex-shrink: 0;
  /* Slight opacity dip on the icon (vs. the text) so the
     filename is the most prominent thing in the leaf. */
  opacity: 0.85;
}
.breadcrumb-leaf-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* Chevron separator. `›` is a single glyph that already points
   right, so no transform needed. Color stays low-contrast so
   the user's eye flows past the separators to the segments. */
.breadcrumb-sep {
  color: rgba(var(--v-theme-on-surface), 0.28);
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
  user-select: none;
  flex-shrink: 0;
  /* Visual baseline alignment with the icon-cap of the segments.
     13px icons sit slightly above the text baseline; nudge the
     chevron down 1px to match. */
  position: relative;
  top: 1px;
}

/* ── Dark mode ────────────────────────────────────────────────────
   The base colors (text and hairline) already inherit correctly
   from the v-theme variables, so dark mode only needs to bump
   the segment-icon alpha and the hover wash a touch lighter so
   the affordance reads on the dark surface. */
.file-browser-breadcrumb.dark .breadcrumb-segment {
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.file-browser-breadcrumb.dark .breadcrumb-segment:hover {
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-primary));
}
.file-browser-breadcrumb.dark .breadcrumb-segment-icon {
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.file-browser-breadcrumb.dark
  .breadcrumb-segment:hover
  .breadcrumb-segment-icon {
  color: rgb(var(--v-theme-primary));
}
.file-browser-breadcrumb.dark .breadcrumb-sep {
  color: rgba(var(--v-theme-on-surface), 0.35);
}
/* 2026-07-20 dark-mode affordances for the new interactive leaf
   + path input. Hover wash is bumped to 0.16 (vs 0.10 in light
   mode) so the affordance reads on the dark surface, matching
   the segment-hover treatment above. The input's surface is
   pushed slightly lighter than the bar so the focused field
   still feels raised on dark. */
.file-browser-breadcrumb.dark .breadcrumb-leaf:hover {
  background: rgba(var(--v-theme-primary), 0.16);
}
.file-browser-breadcrumb.dark .breadcrumb-path-input {
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-color: rgba(var(--v-theme-on-surface), 0.2);
}
.file-browser-breadcrumb.dark .breadcrumb-path-input.is-resolving {
  background: rgba(var(--v-theme-primary), 0.08);
  border-color: rgba(var(--v-theme-primary), 0.5);
  color: rgba(var(--v-theme-on-surface), 0.8);
}
</style>
