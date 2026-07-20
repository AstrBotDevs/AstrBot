<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.3
     Updated 2026-06-21 — draggable divider + split dir/preview composables
     so the left pane keeps showing the parent directory while the right
     pane previews a file inside it. -->
<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeFileBrowser } from "@/composables/useSpcodeFileBrowser";
import { useSpcodeFileSearch } from "@/composables/useSpcodeFileSearch";
import type { SpcodeFileBrowserEntry } from "@/composables/parseSpcodeFileBrowser";
import type { UseSpcodeGitLog } from "@/composables/useSpcodeGitLog";
import type { UseSpcodeGitShow } from "@/composables/useSpcodeGitShow";
import { useSpcodeGitFile } from "@/composables/useSpcodeGitFile";
import { useResizableSplit } from "@/composables/useResizableSplit";
import { projectRelativePath } from "@/composables/pathUtils";
import FileBrowserBreadcrumb from "./FileBrowserBreadcrumb.vue";
import FileBrowserFilePreview from "./FileBrowserFilePreview.vue";
import FileTreeList from "./FileTreeList.vue";
import SearchPanel from "./SearchPanel.vue";
import DocumentHistoryPanel from "./DocumentHistoryPanel.vue";
import RecentFilesBlock from "./RecentFilesBlock.vue";
import type { RecentEntry } from "@/composables/useRecentFiles";

const props = defineProps<{
  /** Directory whose entries are shown in the left pane. */
  currentPath: string;
  /** File path to preview in the right pane; null = show hint. */
  previewPath: string | null;
  isDark?: boolean;
  /** Current worktree root (parent computes: selectedWorktree ?? mainWorktreePath). null = project not loaded. */
  rootPath: string | null;
  /**
   * 2026-07-02 sidebar-search: 1-based line number to center in the
   * file preview after a search-result click. null = no scroll.
   * Propagated as-is to <FileBrowserFilePreview>, which forwards it
   * to <FileBrowserCodeView>, where the scrollIntoView() lives.
   */
  scrollToLine?: number | null;
  /** Unified message origin passed through to the search composable for backend routing. */
  umo?: string | null;
  /** Search scope (currently the active worktree path). */
  worktree?: string | null;
  /**
   * 2026-07-15 workspace-history-parity: the sidebar's
   * `useSpcodeGitLog` instance. Reused by the per-file history
   * pane so the workspace tab stays consistent with the
   * document-manager tab — both invoke the same composable
   * shared with the History sub-tab. `DocumentHistoryPanel`
   * needs the live composable (refresh + state), not a snapshot,
   * because it re-runs the refresh whenever the previewed file
   * changes.
   */
  gitLog: UseSpcodeGitLog;
  /**
   * 2026-07-15 workspace-history-inline: the sidebar's
   * `useSpcodeGitShow` instance. Per-file patch fetches (`?path=`)
   * are reusable across tabs — same composite as DocumentManager's
   * — so we receive the instance instead of mounting a fresh one.
   * Used by the [gitLogPath, selectedRevision, "diff"] watcher
   * below to lazily fetch `gitShow.fetchFile(rev, path)` whenever
   * the user asks for "view this change" in the history pane.
   */
  gitShow: UseSpcodeGitShow;
  /**
   * 2026-07-20 recent-files: per-worktree Recent bucket rendered
   * above the file tree. Optional so the workspace tab's older
   * call sites (and tests) keep mounting without supplying it.
   */
  recentEntries?: RecentEntry[];
}>();

/**
 * Navigation payload:
 * - `dirPath`: the directory the left pane should display (always set).
 * - `previewPath`: the file the right pane should preview, or null to
 *   clear the preview and show the "select from left" hint.
 * File clicks send { dirPath: parentOf(file), previewPath: file.path };
 * directory / breadcrumb clicks send { dirPath: <clicked>, previewPath: null }.
 */
const emit = defineEmits<{
  (
    e: "navigate",
    payload: { dirPath: string; previewPath: string | null },
  ): void;
  (e: "open-file", p: { path: string; line: number }): void;
  // 2026-07-20 recent-files: pass-throughs for <RecentFilesBlock>.
  // - recent-select: the user picked a row; parent mirrors onFileOpen
  //   with `line: 0` so the preview jumps without an anchor.
  // - recent-remove: parent drops the row from the worktree bucket.
  // - recent-clear: parent opens the secondary-confirm dialog.
  (e: "recent-select", p: { path: string }): void;
  (e: "recent-remove", p: { path: string }): void;
  (e: "recent-clear"): void;
}>();

const { tm } = useModuleI18n("features/chat");
const spcodeStatus = useSpcodeProjectStatus();

// Two independent composables so the directory listing stays in the
// left pane while the right pane shows a different (file) path.
// `dirComposable` always fetches `currentPath`; `previewComposable`
// only fetches when `previewPath` is non-empty (its watch has an
// empty-path short-circuit to avoid spurious path_not_found errors).
const dirComposable = useSpcodeFileBrowser(computed(() => props.currentPath));
const previewComposable = useSpcodeFileBrowser(
  computed(() => props.previewPath ?? ""),
);

// 2026-07-17 workspace file editor: the preview owns the edit state
// and exposes confirmLeaveEditing(); every navigation entry point
// below (tree click / breadcrumb / symlink target / search result /
// history pick) consults it first so an unsaved edit is never
// discarded silently.
const previewRef = ref<{ confirmLeaveEditing: () => boolean } | null>(null);
function confirmLeaveEditing(): boolean {
  return previewRef.value?.confirmLeaveEditing() ?? true;
}

// Breadcrumb path: when previewing a file, show the FILE'S path so
// the user can see "root / src / file.ts" in the breadcrumb instead
// of just "root / src". When browsing a directory, show currentPath.
//
// 2026-07-02 revision: the search composable returns REPO-RELATIVE
// forward-slash paths (see plugin/.../file_search.py and
// file_name_search.py — they call os.path.relpath +
// .replace(os.sep, "/") on the ripgrep output). The file-list and
// file-preview APIs both accept relative paths, so `previewPath`
// and `currentPath` are kept as-is for those consumers. But the
// breadcrumb needs an absolute path to render the
// "项目根 / astrbot / core / platform / file.py" hierarchy, so
// re-anchor the relative path against rootPath here. The
// FileBrowserBreadcrumb's case-insensitive root match would
// otherwise fall through to the basename-only fallback, leaving
// the user with no way to navigate to ancestor directories.
const breadcrumbPath = computed<string>(() => {
  const rel = props.previewPath ?? props.currentPath;
  if (!rel) return "";
  // Already absolute (Unix /foo, Windows \foo, or C:\foo / C:/foo).
  // The regex matches a leading slash, backslash, or drive letter
  // followed by a separator.
  if (/^([/\\]|[a-zA-Z]:[/\\])/.test(rel)) return rel;
  if (!props.rootPath) return rel;
  return (
    props.rootPath.replace(/[\\/]+$/, "") + "/" + rel.replace(/^[\\/]+/, "")
  );
});

/** Compute the parent directory of a path (POSIX + Windows separators). */
function parentOf(p: string): string {
  const isWindows = p.includes("\\");
  const lastSep = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  if (lastSep <= 0) return isWindows ? "\\" : "/";
  return p.slice(0, lastSep);
}

function onEntryNavigate(entry: SpcodeFileBrowserEntry): void {
  if (!confirmLeaveEditing()) return;
  // Dangling symlink: EntryList already filters clicks on these.
  if (entry.type === "directory") {
    emit("navigate", { dirPath: entry.path, previewPath: null });
  } else {
    // File or symlink: navigate to the parent (left pane shows the
    // directory listing) and preview the clicked path on the right.
    emit("navigate", {
      dirPath: parentOf(entry.path),
      previewPath: entry.path,
    });
  }
}

// 2026-07-20: FileBrowserBreadcrumb switched its emit from a
// bare path string to a `{ dirPath, previewPath }` payload so the
// path-input feature can route a typed file path to "navigate to
// the parent + preview this file" (matching what <FileTreeList>
// does on a file click). Segment clicks always send
// previewPath: null, but we no longer second-guess that here —
// the breadcrumb is the single source of truth for whether the
// destination is a file or a directory.
function onBreadcrumbNavigate(payload: {
  dirPath: string;
  previewPath: string | null;
}): void {
  if (!confirmLeaveEditing()) return;
  emit("navigate", payload);
}

function onPreviewTargetNavigate(resolvedTarget: string): void {
  if (!confirmLeaveEditing()) return;
  // Symlink "go to target": treat as a file click so the right pane
  // previews it; if the target is actually a directory, the
  // previewComposable will land on a directory state and the user
  // can then click the entry in the right pane to navigate into it.
  emit("navigate", {
    dirPath: parentOf(resolvedTarget),
    previewPath: resolvedTarget,
  });
}

/** Search-result click: same dirty guard as the other navigation
 *  entry points before the event bubbles up to the sidebar.
 *  2026-07-18: closing the panel moved in from the sidebar's
 *  onFileOpen — the SearchPanel REPLACES the file-browser body, so
 *  it must close to reveal the file the user just picked. Declining
 *  the dirty-edit confirm keeps the panel open so the user can pick
 *  a different result (same as DocumentManager). */
function onSearchOpenFile(p: { path: string; line: number }): void {
  if (!confirmLeaveEditing()) return;
  searchOpen.value = false;
  emit("open-file", p);
}

// 2026-07-20 recent-files: pass-throughs for <RecentFilesBlock>.
// These are intentionally thin — the parent (GitDiffSidebar) is the
// one that owns the bucket and the dialog state, so FileBrowserView
// stays a pure adapter and stays test-mountable without a sidebar.
function onRecentSelect(p: { path: string }): void {
  emit("recent-select", p);
}
function onRecentRemove(p: { path: string }): void {
  emit("recent-remove", p);
}
function onRecentClear(): void {
  emit("recent-clear");
}

/** Manually re-fetch the workspace contents. Exposed to the parent
 *  sidebar so its header refresh button can mean "reload the
 *  workspace" in files view (mirroring how the same button means
 *  "reload git diff" in diff view). Always refreshes the directory
 *  listing; refreshes the file preview only if a file is currently
 *  being previewed — calling previewComposable.refresh() with no
 *  preview path would force it into the path_not_found error state. */
async function refresh(): Promise<void> {
  const tasks: Promise<void>[] = [dirComposable.refresh()];
  if (props.previewPath) {
    tasks.push(previewComposable.refresh());
  }
  await Promise.all(tasks);
}

defineExpose({ refresh });

// ── Draggable divider (left/right pane resize) ──────────────────
// leftPanePercent is the share of horizontal space the entry list
// takes; the preview takes (100 - leftPanePercent). Mirrors the
// resize pattern used by GitDiffSidebar.vue. Bounds [15, 70] keep
// both panes readable; 6px hover/active band gives a generous target.
//
// 2026-07-09: DEFAULT_PERCENT lowered from 40 to 30 (3:7
// left:right) so the right-hand file preview gets more room
// by default — the file content (syntax-highlighted code) is
// the primary payload here, the file list is the navigation
// rail. Users can still drag the divider to override this on
// a per-session basis; the chosen width sticks for the rest
// of the session because leftPanePercent is component-local
// state (no persistence).
const MIN_PERCENT = 15;
const MAX_PERCENT = 70;
const DEFAULT_PERCENT = 30;

const bodyRef = ref<HTMLElement | null>(null);
const leftPanePercent = ref<number>(DEFAULT_PERCENT);
const isResizing = ref<boolean>(false);

function startResize(e: MouseEvent): void {
  e.preventDefault();
  isResizing.value = true;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  document.addEventListener("mousemove", onMouseMove);
  document.addEventListener("mouseup", onMouseUp);
}

function onMouseMove(e: MouseEvent): void {
  if (!isResizing.value || !bodyRef.value) return;
  const rect = bodyRef.value.getBoundingClientRect();
  if (rect.width <= 0) return;
  const pct = ((e.clientX - rect.left) / rect.width) * 100;
  leftPanePercent.value = Math.min(MAX_PERCENT, Math.max(MIN_PERCENT, pct));
}

function onMouseUp(): void {
  if (!isResizing.value) return;
  isResizing.value = false;
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  document.removeEventListener("mousemove", onMouseMove);
  document.removeEventListener("mouseup", onMouseUp);
}

// ── Left-pane collapse / expand ──────────────────────────────────
// Lets the user temporarily hide the directory list so the right
// pane (file preview) gets full width — useful when reading a long
// file on a narrow sidebar. The collapse button is only shown while
// a file is being previewed (the only context where the user would
// reasonably want to hide the parent-dir list). When the preview
// clears (user navigates away or closes the file), we auto-restore
// the pane so the user can browse again.
const isLeftPaneCollapsed = ref<boolean>(false);
watch(
  () => props.previewPath,
  (p) => {
    if (!p) isLeftPaneCollapsed.value = false;
  },
);

// ── Per-file history pane (2026-07-15 workspace-history-parity) ──
// Mirrors the right-edge history panel in <DocumentManager> so the
// workspace tab has the same affordance as the documents tab:
// preview a file → see the commits that touched it, then either
// (a) peek at the file at any of those revisions, or (b) see how
// that revision differs from the current working copy.
//
// Data flow:
//   DocumentHistoryPanel emits `select-revision(sha)` /
//   `compare-current(sha)`. We own `selectedRevision` + `viewMode`
//   and forward both into <FileBrowserFilePreview>, exactly the way
//   <DocumentManager> does for its `selectedDoc` +
//   `selectedRevision` pair.
//
// (2026-07-15 workspace-history-inline:) previously both events
// routed through the injected `spcode:setLogPathFilter`, which
// switched the entire sidebar to the History sub-tab. The two tabs
// now share the same inline behavior — see <DocumentManager>'s
// `onSelectRevision` / `onCompareCurrent` for the reference impl.
//
// Reuses <DocumentHistoryPanel> verbatim + the sidebar's shared
// `useSpcodeGitLog` and `useSpcodeGitShow` instances. The local
// `useSpcodeGitFile` composable is mounted here for the same reason
// DocumentManager mounts its own: it owns the historical blob cache
// for THIS pane, independent from the document manager's. (The two
// `useSpcodeGitFile` instances don't share state, but git-show is
// global anyway, and the document manager's cache lives across
// file selections in a way we don't need here.)
const gitFile = useSpcodeGitFile(computed(() => props.worktree ?? null));

/** Repo-relative path of the currently-previewed file (or empty
 *  string when nothing is selected). Passed straight to
 *  `<DocumentHistoryPanel>` as `file-relative`; the panel's
 *  `useSpcodeGitLog` watcher fires a refresh whenever this value
 *  changes, so switching between files re-fetches the commit list
 *  for the new path. `projectRelativePath` handles both absolute
 *  (tree-click) and already-relative (search-result-click) inputs
 *  and returns "" for the project root itself. */
const gitLogPath = computed<string>(() =>
  projectRelativePath(props.previewPath ?? "", props.rootPath),
);

/** History pane resizer. Anchored to the right edge so the percent
 *  math matches the pane being on the right (mirrors the layout in
 *  DocumentManager). 22/15/40 keeps the panel usable as a commit
 *  list at default width while still permitting the user to shrink
 *  it almost out of the way to give the preview more room. */
const historySplit = useResizableSplit({
  initialPercent: 22,
  minPercent: 15,
  maxPercent: 40,
  containerRef: bodyRef,
  direction: "right",
});

// 2026-07-15 document-history-empty: the history pane is per-file
// (commits belong to a specific file), so when no file is selected
// on mount there's nothing useful to show there. Default the pane
// to collapsed in that case so the user doesn't see the "no file
// selected" placeholder for no reason. Once the user manually
// toggles it, that choice wins — no forced sync with previewPath
// (matches DocumentManager's behavior).
const isHistoryCollapsed = ref<boolean>(!props.previewPath);

// ── Inline history render state (2026-07-15 workspace-history-inline) ──
// Mirrors <DocumentManager>'s selectedRevision / viewMode pair.
// `selectedRevision` is null when no revision is picked (= show
// the current working copy); `viewMode` only matters when a
// revision is set:
//   - "raw"  → render the file content at that revision (peeking)
//   - "diff" → render the unified diff vs the current working copy
const selectedRevision = ref<string | null>(null);
const viewMode = ref<"raw" | "diff">("raw");
/** Lazy-loaded unified diff for the (current-file, picked-revision)
 *  pair. Populated by the watcher below whenever (path, revision,
 *  "diff") are all set. Null whenever no revision is picked or the
 *  fetch is still in flight / failed. */
const diffPatch = ref<string | null>(null);

/** Pick / replace the historical blob content via gitFile. Mirrors
 *  DocumentManager's `historicalFileContent` computed — same shape
 *  (string), same null-on-bad-state contract. */
const historicalFileContent = computed<string>(() => {
  const path = gitLogPath.value;
  const rev = selectedRevision.value;
  if (!path || !rev) return "";
  const data = gitFile.getData(path, rev);
  return data?.content ?? "";
});
/** True if the historical blob is binary. Empty content for a binary
 *  file is expected (the backend never sends blob bytes for
 *  binaries); the preview must show a "binary file" placeholder
 *  instead of trying to highlight the empty string. */
const historicalIsBinary = computed<boolean>(() => {
  const path = gitLogPath.value;
  const rev = selectedRevision.value;
  if (!path || !rev) return false;
  const state = gitFile.getState(path, rev);
  return state.kind === "ok" && state.data.isBinary === true;
});
/** True if the file at the picked revision is binary or otherwise
 *  patch-less (the git-show backend returns patch=null for binary
 *  files). Used by the diff body to render a "binary file"
 *  placeholder instead of the (also-null) patch text. */
const diffIsBinary = computed<boolean>(() => {
  const path = gitLogPath.value;
  const rev = selectedRevision.value;
  if (!path || !rev) return false;
  const data = props.gitShow.getFileData(rev, path);
  return data?.isBinary === true;
});

/** Lazy fetch for the (revision, path) patch — runs whenever the
 *  picker lands on a (path, revision) pair in diff mode, and clears
 *  the patch whenever any of those three change. Pattern mirrors
 *  DocumentManager's diff watcher: clear → fetch → read.
 *  The `immediate: true` guards the initial state (all three
 *  inputs unset → diffPatch = null). */
watch(
  () => [gitLogPath.value, selectedRevision.value, viewMode.value] as const,
  async ([path, rev, mode]) => {
    if (mode !== "diff" || !path || !rev) {
      diffPatch.value = null;
      return;
    }
    diffPatch.value = null;
    await props.gitShow.fetchFile(rev, path);
    const snap = props.gitShow.getFileData(rev, path);
    if (snap) diffPatch.value = snap.patch ?? null;
  },
  { immediate: true },
);

/** Switching to a different file implicitly drops any picked
 *  revision — same rule DocumentManager enforces in
 *  `onTreeSelect` / `onPathChange` / `onBreadcrumbNavigate`. We
 *  reset both `selectedRevision` and `viewMode` here so the
 *  preview snaps back to the working copy and the diff watcher
 *  above clears `diffPatch`. */
watch(
  () => gitLogPath.value,
  (path, prev) => {
    if (path !== prev) {
      selectedRevision.value = null;
      viewMode.value = "raw";
    }
  },
);

/** History-panel event handlers. Both accept the SHA emitted by
 *  <DocumentHistoryPanel> and set local state; the lazy watchers
 *  above / the gitFile composable do the actual fetching. */
function onHistorySelectRevision(sha: string): void {
  if (!confirmLeaveEditing()) return;
  if (!gitLogPath.value) return;
  selectedRevision.value = sha;
  viewMode.value = "raw";
  // Kick the historical-blob fetch — `getData()` is reactive so the
  // computed above re-fires when state transitions to "ok".
  void gitFile.fetchRef(gitLogPath.value, sha);
}
function onHistoryCompareCurrent(sha: string): void {
  if (!confirmLeaveEditing()) return;
  if (!gitLogPath.value) return;
  selectedRevision.value = sha;
  viewMode.value = "diff";
  // No explicit fetch here — the diffPatch watcher above sees the
  // (path, rev, "diff") triple and runs gitShow.fetchFile itself.
  // We still want the historical blob too (for the meta-header's
  // file-name / size, etc.), so kick the same fetchRef.
  void gitFile.fetchRef(gitLogPath.value, sha);
}

/**
 * 2026-07-15 workspace-history-banner: drop the picked
 * revision and snap back to the working copy. Mirrors
 * <DocumentManager>'s `onBackToCurrent`: the state lives
 * here, so the child (`<FileBrowserFilePreview>`) just
 * emits a `back-to-current` event and we mutate
 * `selectedRevision` + reset `viewMode` so the diff watcher
 * above clears `diffPatch`. Bound to the banner's
 * "回到当前" button so the workspace tab reads identically
 * to the document-manager tab.
 */
function onBackToCurrent(): void {
  selectedRevision.value = null;
  viewMode.value = "raw";
}

// 2026-07-18 editor toolbar parity: after a rename/delete from the
// preview toolbar, reload the directory listing (the old entry is
// gone) and steer the preview — follow the renamed file, or clear
// the preview after a delete. Both bubble through the parent's
// `navigate` contract so currentPath stays untouched.
function onPreviewRenamed(newPath: string): void {
  dirComposable.refresh();
  emit("navigate", { dirPath: props.currentPath, previewPath: newPath });
}

function onPreviewDeleted(): void {
  dirComposable.refresh();
  emit("navigate", { dirPath: props.currentPath, previewPath: null });
}

// ── Workspace search (2026-07-18 workspace-search-parity) ────────
// The search toolbar (toggle + inline input) moved IN from
// GitDiffSidebar so it travels with the file-area fullscreen
// Teleport — previously the toolbar stayed behind in the sidebar
// and the fullscreen overlay had no search affordance. Structure
// mirrors DocumentManager's docs search: the shared `query` ref
// from the singleton composable is bound to the input via :value +
// @input (the composable owns the 300ms debounce), and SearchPanel
// reads the same ref for its results UI.
//
// searchOpen is still persisted to localStorage under the same key
// the sidebar used, so existing users keep their panel state across
// reloads. (DocumentManager deliberately does NOT persist its panel
// state; the workspace view has persisted since 2026-07-02 and we
// keep that behavior rather than regressing it.)
// 2026-07-20 search-trigger: detect Mac so the kbd hint on
// the idle search bar can show "⌘ F" instead of the
// Windows/Linux "Ctrl F". userAgentData is the modern API
// (Chromium only, but covers the dashboard's deployment
// surface); navigator.platform is the fallback for the
// remaining browsers. Wrapped in an IIFE so the value is
// computed once at module-init instead of on every render
// — the result is constant for the page's lifetime.
const isMacPlatform: boolean = (() => {
  if (typeof navigator === "undefined") return false;
  const uaDataPlatform = (
    navigator as Navigator & { userAgentData?: { platform?: string } }
  ).userAgentData?.platform;
  const platform = uaDataPlatform ?? navigator.platform ?? "";
  return /mac|iphone|ipad|ipod/i.test(platform);
})();
/** Keyboard-shortcut label rendered inside the idle search
 *  bar's right-side kbd chip. Pure platform detection — no
 *  locale dependency — so it lives in code rather than i18n. */
const searchShortcutLabel: string = isMacPlatform ? "⌘ F" : "Ctrl F";

const SEARCH_OPEN_STORAGE_KEY = "astrbot.spcode.gitDiffSidebar.searchOpen";

/** Load the persisted panel state; any value other than the literal
 *  "true" (including absent / storage-disabled) starts collapsed. */
function loadSearchOpen(): boolean {
  try {
    return localStorage.getItem(SEARCH_OPEN_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}
const searchOpen = ref<boolean>(loadSearchOpen());

const { query: fileSearchQuery, search: fileSearchSearch } =
  useSpcodeFileSearch();
const searchInputRef = ref<HTMLInputElement | null>(null);

/** Push the current umo/worktree into the composable so the debounced
 *  search re-fires with the right routing context after a toolbar
 *  keystroke. Idempotent (the composable stores the last values) —
 *  mirrors the priming call in SearchPanel.vue / DocumentManager. */
function primeFileSearch(): void {
  void fileSearchSearch({
    umo: props.umo ?? null,
    worktree: props.worktree ?? null,
    pattern: "",
  });
}
primeFileSearch();

/** Single watcher for the panel toggle: persist the state, and on
 *  open re-prime (umo/worktree may have changed while closed) then
 *  auto-focus the input; on close clear the shared query (which
 *  resets the composable's results state to idle). */
watch(searchOpen, async (open) => {
  try {
    localStorage.setItem(SEARCH_OPEN_STORAGE_KEY, String(open));
  } catch {
    /* localStorage may be unavailable (private mode) — non-fatal */
  }
  if (open) {
    primeFileSearch();
    await nextTick();
    searchInputRef.value?.focus();
  } else {
    fileSearchQuery.value = "";
  }
});

/** Wire native input events to the shared ref (:value + @input, not
 *  v-model — the query is singleton state owned by the composable,
 *  not local to this component). */
function onSearchInput(e: Event): void {
  fileSearchQuery.value = (e.target as HTMLInputElement).value;
}

/** Esc on the input closes the panel. stopPropagation keeps the
 *  capture-phase onKeyDown fallback below from re-handling the same
 *  keypress. */
function onSearchClose(e: KeyboardEvent): void {
  e.stopPropagation();
  searchOpen.value = false;
}

/** 2026-07-20 search-toggle-button: the explicit magnifier button
 *  on the right of the toolbar. Toggles the panel — opens when
 *  closed, closes when open. Same role as the Cmd/Ctrl+F shortcut
 *  (which also toggles via the onKeyDown handler) and the fake
 *  search bar's click (which is hard-coded to `searchOpen = true`
 *  because the fake bar is only mounted when the panel is closed).
 *  The watcher above already handles focus + query reset on every
 *  transition, so this just flips the ref. */
function toggleSearch(): void {
  searchOpen.value = !searchOpen.value;
}

// ── File-area fullscreen (2026-07-18, elecvoid243) ───────────────
// Teleports the whole view (breadcrumb topbar + tree/preview/history
// panes) to <body> and pins it `position: fixed; inset: 0`. NOT
// persisted — each mount starts embedded in the sidebar. Mirrors
// DocumentManager's overlay pattern (z-index 9999 sits above the
// sidebar's own global fullscreen at 1300) so the two modes can
// nest: the file area covers the viewport, Esc peels back one layer
// at a time.
const isFullscreen = ref<boolean>(false);

function toggleFullscreen(): void {
  isFullscreen.value = !isFullscreen.value;
}

/** Capture-phase document keydown handler (registered on mount).
 *  Owns three shortcuts, mirroring DocumentManager's onKeyDown:
 *
 *  1. Esc exits the file-area fullscreen. Registered in the CAPTURE
 *     phase so it runs before GitDiffSidebar's global-fullscreen
 *     Escape handler (bubble phase) — when both fullscreen modes are
 *     active, Esc only exits this inner overlay. stopPropagation()
 *     keeps the sidebar's handler from also firing.
 *  2. Cmd/Ctrl+F toggles the search panel (preventDefault beats the
 *     browser's native find-in-page). Registered here rather than in
 *     GitDiffSidebar because this component only exists while
 *     viewMode === "files", so the shortcut can never race the
 *     diff/history/docs views (DocumentManager owns its own).
 *  3. Esc closes the search panel as a FALLBACK when focus is
 *     outside the panel and the toolbar input — SearchPanel and the
 *     input each have their own Esc handlers that run first (the
 *     input's uses .stop), so this branch only fires when focus has
 *     drifted elsewhere (e.g. the breadcrumb after a result click). */
function onKeyDown(e: KeyboardEvent): void {
  if (e.key === "Escape" && isFullscreen.value) {
    e.stopPropagation();
    isFullscreen.value = false;
    return;
  }
  const isMod = e.metaKey || e.ctrlKey;
  if (isMod && (e.key === "f" || e.key === "F")) {
    e.preventDefault();
    searchOpen.value = !searchOpen.value;
  } else if (e.key === "Escape" && searchOpen.value) {
    const target = e.target as HTMLElement | null;
    if (
      target &&
      !target.closest(".search-panel") &&
      !target.closest(".file-browser-search-input")
    ) {
      searchOpen.value = false;
    }
  }
}

/** Body scroll lock while fullscreen is on (same pattern as
 *  DocumentManager / DiffPreview): the fixed overlay never scrolls
 *  with the page, so the underlying <body> is frozen instead. The
 *  empty-string reset restores the browser default on exit. */
watch(isFullscreen, (v) => {
  document.body.style.overflow = v ? "hidden" : "";
});

onMounted(() => {
  document.addEventListener("keydown", onKeyDown, true);
});

onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeyDown, true);
  // Release the scroll lock if the sidebar closes mid-fullscreen.
  if (isFullscreen.value) {
    document.body.style.overflow = "";
  }
  // If user is mid-drag on either divider, release cleanly.
  if (isResizing.value) onMouseUp();
  if (historySplit.isResizing.value) {
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    isResizing.value = false;
  }
  // Release ALL THREE composables. Without this, an AbortController
  // stays alive across re-mounts (e.g. toggling viewMode files ↔
  // diff), and the in-flight request can still write to a stale
  // `state` ref. gitFile is in here for the same reason — its
  // inflight history-blob fetches would otherwise leak after the
  // workspace tab unmounts.
  dirComposable.dispose();
  previewComposable.dispose();
  gitFile.dispose();
});
</script>

<template>
  <!--
    2026-07-18 file-area fullscreen: escape the sidebar by teleporting
    the root to <body> while fullscreen is on, then position it fixed
    inset 0 (see .file-browser-view.is-fullscreen). The `:disabled`
    flag keeps the same component tree in-place when fullscreen is
    off — Vue 3's Teleport becomes a transparent pass-through, so the
    sidebar-body layout is untouched on the normal-render path. No
    duplicated templates, no duplicated refs, no duplicated state.
    (Pattern mirrors DocumentManager / DiffPreview.)
  -->
  <Teleport to="body" :disabled="!isFullscreen">
    <div class="file-browser-view" :class="{ 'is-fullscreen': isFullscreen }">
      <!-- 2026-07-18 workspace-search-parity: search toolbar (toggle +
           inline input) moved IN from GitDiffSidebar so it travels
           with the fullscreen Teleport — the sidebar's own toolbar
           used to stay behind, leaving the overlay with no search
           affordance. Sits ABOVE the breadcrumb topbar (same order
           the sidebar had, and the same layout DocumentManager uses).
           The input binds the shared `fileSearchQuery` ref via :value
           + @input; the composable owns the 300ms debounce. Esc on
           the input closes the panel (stopPropagation prevents the
           capture-phase fallback from also firing). Gated on the
           project being loaded, same as the topbar below.

           2026-07-20 search-trigger: the idle state is a
           full-width "fake" search bar: same border, radius,
           padding, and font as the active input, with a placeholder
           string in the middle and a kbd shortcut hint on the
           right. Clicking it swaps in the real <input> and the
           existing watcher auto-focuses it. The two elements
           share every visual property that matters, so the
           transition is a no-op for layout — no jump, no
           reflow flicker, no width recompute.

           2026-07-20 search-toggle-button: re-added the explicit
           magnifier button (right of the input) so users have a
           way to close the panel from the toolbar — previously the
           only way out was Esc or Cmd/Ctrl+F, both keyboard-only.
           The button toggles searchOpen, same as the trigger
           button on the left: it opens the panel when closed and
           closes it when open. Stays mounted in both states so the
           user always sees a mouse-friendly exit when the input
           has focus. -->
      <div
        v-if="spcodeStatus.status.value.loaded"
        class="file-browser-search-toolbar"
        data-testid="file-browser-search-toolbar"
      >
        <button
          v-if="!searchOpen"
          type="button"
          class="file-browser-search-trigger"
          :title="tm('spcodeProjectLoad.diffSidebar.search.button')"
          :aria-label="tm('spcodeProjectLoad.diffSidebar.search.button')"
          @click="searchOpen = true"
        >
          <v-icon size="16" class="file-browser-search-trigger__icon">mdi-magnify</v-icon>
          <span class="file-browser-search-trigger__placeholder">
            {{ tm('spcodeProjectLoad.diffSidebar.search.placeholder') }}
          </span>
          <kbd class="file-browser-search-trigger__hint" aria-hidden="true">{{ searchShortcutLabel }}</kbd>
        </button>
        <input
          v-else
          ref="searchInputRef"
          :value="fileSearchQuery"
          type="text"
          class="file-browser-search-input"
          :placeholder="tm('spcodeProjectLoad.diffSidebar.search.placeholder')"
          spellcheck="false"
          autocomplete="off"
          @input="onSearchInput"
          @keydown.escape.stop="onSearchClose"
        />
        <v-btn
          icon
          size="small"
          variant="text"
          :class="['file-browser-search-toggle', { 'is-active': searchOpen }]"
          :title="tm('spcodeProjectLoad.diffSidebar.search.button')"
          :aria-label="tm('spcodeProjectLoad.diffSidebar.search.button')"
          :aria-pressed="searchOpen"
          @click="toggleSearch"
        >
          <v-icon size="16">mdi-magnify</v-icon>
        </v-btn>
      </div>
      <!-- 2026-07-18: topbar = breadcrumb (flex 1) + the file-area
           fullscreen toggle pinned to the right edge. The bar's own
           bottom hairline replaces the breadcrumb's (overridden below)
           so the divider runs under the button as well. The whole bar
           is gated on the project being loaded (same condition the
           breadcrumb used to carry), which also hides the fullscreen
           affordance when there is nothing to browse. -->
      <div
        v-if="spcodeStatus.status.value.loaded"
        class="file-browser-topbar"
      >
        <!-- 2026-07-02: breadcrumb lifted out of the v-if="!searchOpen"
           block so it stays visible even while the search panel is
           open. Previously the SearchPanel REPLACED the file browser
           entirely (including the breadcrumb), so the user had to
           close the search panel before they could navigate to a
           different directory. Now the breadcrumb is always rendered
           at the top of the file browser (when the project is loaded),
           and the user can click a segment to switch paths without
           touching the search panel. The SearchPanel and the
           file-list/preview body remain mutually exclusive below. -->
        <FileBrowserBreadcrumb
          class="file-browser-topbar-breadcrumb"
          :current-path="breadcrumbPath"
          :root-path="rootPath"
          :preview-path="props.previewPath"
          :is-dark="!!isDark"
          @navigate="onBreadcrumbNavigate"
        />
        <!-- File-area fullscreen toggle (2026-07-18). Icon-only v-btn
             matching the sidebar header chrome; the icon swaps between
             mdi-fullscreen / mdi-fullscreen-exit with the state. -->
        <v-btn
          class="file-browser-fullscreen-btn"
          :icon="isFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'"
          size="small"
          variant="text"
          :aria-pressed="isFullscreen"
          :aria-label="
            tm(
              isFullscreen
                ? 'spcodeProjectLoad.fileBrowser.fullscreen.exit'
                : 'spcodeProjectLoad.fileBrowser.fullscreen.enter',
            )
          "
          :title="
            tm(
              isFullscreen
                ? 'spcodeProjectLoad.fileBrowser.fullscreen.exit'
                : 'spcodeProjectLoad.fileBrowser.fullscreen.enter',
            )
          "
          @click="toggleFullscreen"
        />
      </div>
      <SearchPanel
        v-if="searchOpen"
        v-model="searchOpen"
        :worktree="props.worktree ?? null"
        :umo="props.umo ?? null"
        @open-file="onSearchOpenFile"
      />
      <template v-else>
        <div v-if="!spcodeStatus.status.value.loaded" class="file-browser-empty">
          <v-icon size="36" color="grey">mdi-folder-open-outline</v-icon>
          <span class="empty-text">{{
            tm("spcodeProjectLoad.fileBrowser.placeholder")
          }}</span>
        </div>
        <div
          v-else
          ref="bodyRef"
          class="file-browser-body"
          :class="{
            resizing: isResizing || historySplit.isResizing.value,
            'left-collapsed': isLeftPaneCollapsed,
            'history-collapsed': isHistoryCollapsed,
          }"
        >
          <!-- Expand handle: only when collapsed. Placed FIRST in DOM
                 order so it sits at the leftmost position in the flex
                 row. Click to restore the left pane at its previous
                 width (leftPanePercent ref is preserved across collapse).

               2026-07-14: the previous incarnation stacked a chevron
               and a vertical-text label inside a 24px-wide, fully
               transparent strip. The vertical label forced the button
               to grow to ~90–255px tall (zh-CN ≈ 90px, en-US ≈ 225px,
               ru-RU ≈ 255px — see the 2026-07-09 author comment).
               When the surrounding container was short (e.g. inside
               the diff-preview fullscreen overlay where the body can
               be only ~100px tall), the label overflowed the button,
               rendering on top of the breadcrumb above and making
               the affordance look like floating text. This rewrite
               keeps the chevron only and drops the vertical label;
               the i18n string is still surfaced via the native
               `title` tooltip on hover / focus, so accessibility is
               unchanged. A subtle primary-tinted background gives
               the handle visual chrome so it no longer reads as
               floating glyphs. -->
          <button
            v-if="isLeftPaneCollapsed"
            type="button"
            class="file-browser-expand-handle"
            :title="tm('spcodeProjectLoad.fileBrowser.pane.expand')"
            :aria-label="tm('spcodeProjectLoad.fileBrowser.pane.expand')"
            @click="isLeftPaneCollapsed = false"
          >
            <v-icon size="16" class="file-browser-expand-handle-icon"
              >mdi-chevron-double-right</v-icon
            >
          </button>

          <!-- Left pane wrapper: holds the entry list AND the collapse
                 button. `position: relative` so the absolutely-positioned
                 collapse button anchors to the pane's top-right. v-show
                 preserves the inline `width` style so collapse ↔ expand
                 animations are smooth. -->
          <div
            v-show="!isLeftPaneCollapsed"
            class="file-browser-pane-left"
            :style="{ width: leftPanePercent + '%' }"
          >
            <!-- 2026-07-20 recent-files: per-worktree recent list,
                 default-collapsed block sitting above the directory
                 tree. v-if="rootPath" so we never render the panel
                 when there's no project context (spec §4.1). -->
            <RecentFilesBlock
              v-if="rootPath"
              :entries="recentEntries ?? []"
              :current-root="rootPath"
              @select="onRecentSelect"
              @remove="onRecentRemove"
              @clear="onRecentClear"
            />
            <FileTreeList
              :state="dirComposable.state.value"
              :selected-path="previewPath"
              :root-path="rootPath"
              :preview-path="previewPath"
              :is-dark="!!isDark"
              :breadcrumb="false"
              @navigate="onEntryNavigate"
              @breadcrumb-navigate="onBreadcrumbNavigate"
            />
            <!-- 2026-07-17: always rendered (previously
                 v-if="previewPath" hid it until a file was selected,
                 which made the collapse affordance undiscoverable
                 on a fresh workspace). -->
            <button
              type="button"
              class="file-browser-collapse-btn"
              :title="tm('spcodeProjectLoad.fileBrowser.pane.collapse')"
              :aria-label="tm('spcodeProjectLoad.fileBrowser.pane.collapse')"
              @click="isLeftPaneCollapsed = true"
            >
              <v-icon size="14">mdi-chevron-double-left</v-icon>
            </button>
          </div>

          <div
            v-show="!isLeftPaneCollapsed"
            class="file-browser-divider"
            role="separator"
            aria-orientation="vertical"
            :aria-valuenow="Math.round(leftPanePercent)"
            aria-valuemin="15"
            aria-valuemax="70"
            @mousedown="startResize"
          />

          <!-- Right pane: when collapsed, suppress the inline width
                 (rely on flex: 1 1 auto to fill the remaining space
                 after the expand handle). Otherwise size to the
                 complement of leftPanePercent. -->
          <!--
            Right pane: 2026-07-15 width is now driven by flex (the
            middle item in a row of left-pane / preview / history).
            Earlier revisions calculated `100 - leftPanePercent%` and
            applied it inline, which broke as soon as a third pane
            (the per-file history) was added — the history pane
            would have eaten into the preview width silently. With
            `flex: 1 1 auto` on `.file-browser-pane-right`, the
            preview automatically takes whatever space remains after
            the tree pane and history pane (and their dividers)
            have claimed theirs.
          -->
          <FileBrowserFilePreview
            v-if="previewPath"
            ref="previewRef"
            class="file-browser-pane-right"
            :state="previewComposable.state.value"
            :is-dark="!!isDark"
            :scroll-to-line="props.scrollToLine ?? null"
            :selected-revision="selectedRevision"
            :view-mode="viewMode"
            :historical-content="historicalFileContent"
            :historical-is-binary="historicalIsBinary"
            :diff-patch="diffPatch"
            :diff-is-binary="diffIsBinary"
            :file-relative-path="gitLogPath"
            :worktree="props.worktree ?? null"
            @navigate-target="onPreviewTargetNavigate"
            @retry="() => previewComposable.refresh()"
            @saved="() => previewComposable.refresh()"
            @renamed="onPreviewRenamed"
            @deleted="onPreviewDeleted"
            @back-to-current="onBackToCurrent"
          />
          <div v-else class="file-browser-pane-right file-browser-preview-empty">
            <v-icon size="32" color="grey">mdi-folder-open-outline</v-icon>
            <span class="preview-hint">
              {{ tm("spcodeProjectLoad.fileBrowser.preview.selectFromLeft") }}
            </span>
          </div>

          <!--
            2026-07-15 workspace-history-parity: per-file commit list
            shown on the right edge of the body, mirroring the
            right-edge pane in <DocumentManager>. Reuses
            <DocumentHistoryPanel> verbatim and reads from the same
            `useSpcodeGitLog` instance the History sub-tab uses — so
            selecting a different file in the preview re-fetches the
            history for just that file, with no extra wiring.

            Both dividers (tree + history) reuse the .file-browser-divider
            base styles; the history one opts out of `v-show` when the
            pane is collapsed via `.history-collapsed` on the parent.
            Mirrors DocumentManager's `.document-manager__divider--history`
            pattern (border-left, hover band).
          -->
          <div
            v-show="!isHistoryCollapsed"
            class="file-browser-divider file-browser-divider--history"
            role="separator"
            aria-orientation="vertical"
            :aria-valuenow="Math.round(historySplit.percent.value)"
            aria-valuemin="15"
            aria-valuemax="40"
            @mousedown="historySplit.startResize"
          />
          <div
            v-show="!isHistoryCollapsed"
            class="file-browser-history"
            :style="{ width: historySplit.percent.value + '%' }"
          >
            <DocumentHistoryPanel
              :git-log="gitLog"
              :file-relative="gitLogPath"
              :current-revision="selectedRevision"
              :is-loading="gitLog.state.value.kind === 'loading'"
              @select-revision="onHistorySelectRevision"
              @compare-current="onHistoryCompareCurrent"
              @collapse="isHistoryCollapsed = true"
            />
          </div>

          <!--
            History expand handle: shown only when the history pane
            is collapsed. Sits at the rightmost flex position so the
            user can restore the pane at its previous width. Mirrors
            the left expand handle (same .file-browser-expand-handle
            base; --history modifier swaps the chevron direction and
            the border side).
          -->
          <button
            v-if="isHistoryCollapsed"
            type="button"
            class="file-browser-expand-handle file-browser-expand-handle--history"
            :title="tm('spcodeProjectLoad.documentManager.pane.expandHistory')"
            :aria-label="
              tm('spcodeProjectLoad.documentManager.pane.expandHistory')
            "
            @click="isHistoryCollapsed = false"
          >
            <v-icon size="16" class="file-browser-expand-handle-icon"
              >mdi-chevron-double-left</v-icon
            >
          </button>
        </div>
      </template>
    </div>
  </Teleport>
</template>

<style scoped>
.file-browser-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
/* 2026-07-18 file-area fullscreen: topbar = breadcrumb (flex 1) +
   the fullscreen toggle pinned to the right edge. The hairline that
   used to sit on the breadcrumb itself moves up to the bar so the
   divider also runs under the button. */
.file-browser-topbar {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  border-bottom: 1px solid
    var(--chat-border, rgba(var(--v-theme-on-surface), 0.08));
}
.file-browser-topbar .file-browser-topbar-breadcrumb {
  flex: 1 1 auto;
  min-width: 0;
  /* Two-class specificity so this beats the component's own scoped
     `.file-browser-breadcrumb { border-bottom }` regardless of
     stylesheet injection order. */
  border-bottom: none;
}
.file-browser-fullscreen-btn {
  flex: 0 0 auto;
  margin-right: 4px;
}
/* 2026-07-18 workspace-search-parity: search toolbar (toggle + input).
   Visual spec mirrors DocumentManager's __search-toolbar (which itself
   mirrors the sidebar's old files-toolbar) so all three search UIs
   read identically.

   2026-07-20 search-trigger: the toolbar now hosts a single
   full-width element — either the "fake" search bar (idle, looks
   like an input) or the real <input> (active). The two share
   every visual property that matters (border, radius, padding,
   background, font) so the swap is a no-op for layout. The
   container's own padding is reduced to 0 vertically because the
   inner element carries the border, so adding container padding
   on top would make the bar taller when active than when idle
   (or vice versa). */
.file-browser-search-toolbar {
  display: flex;
  align-items: center;
  /* 2026-07-20 search-toggle-button: gap between the input and
     the toggle button on the right. The input itself uses
     flex:1 to claim the rest, and the toggle button is a
     fixed-width Vuetify icon button (size=small). 6px matches
     the rhythm of the rest of the toolbar / breadcrumb row. */
  gap: 6px;
  padding: 4px 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  flex-shrink: 0;
}
/* 2026-07-20 search-toggle-button: active state for the
   right-side magnifier. When search is open the button
   takes a primary tint so the user can see at a glance that
   clicking it will close the panel. Matches the pre-trigger
   v-btn design (round button, primary-tinted background,
   primary text colour). */
.file-browser-search-toggle.is-active {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}
/* Shared "looks like an input" baseline. Both the idle trigger
   button and the active <input> use these properties so the
   click-to-activate transition doesn't shift the layout. The
   flex:1 block is the load-bearing part — without it the
   trigger collapses to its content width and the bar looks
   tiny, defeating the affordance. Note: <input> is a
   replaced element, so we do NOT put `display: flex` in the
   shared block — flex layout is added separately on the
   trigger-only rule below. */
.file-browser-search-trigger,
.file-browser-search-input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--chat-border, rgba(var(--v-theme-on-surface), 0.2));
  border-radius: 8px;
  outline: none;
  background: rgb(var(--v-theme-surface));
  padding: 5px 10px;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface));
  font-family: inherit;
  /* Triggers a "this is clickable" hover without changing the
     shape — only the border + a subtle background shift, so the
     swap to the real <input> (which keeps the same border)
     stays visually consistent. */
  transition:
    border-color 0.14s ease,
    box-shadow 0.14s ease,
    background 0.14s ease;
}
/* Trigger-only flex layout for the icon + placeholder + kbd
   row, plus button resets so the browser's default button
   styles (font, line-height, padding) don't leak in and
   offset the alignment relative to the active <input>. The
   text-align: left + appearance: none are required to get the
   iOS Safari / Firefox default-button reset; otherwise the
   placeholder text starts centered and the kbd hint moves
   away from the right edge. */
.file-browser-search-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  text-align: left;
  -webkit-appearance: none;
  appearance: none;
}
.file-browser-search-trigger:hover {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.04);
}
.file-browser-search-trigger:focus-visible {
  /* Same focus ring as the active input so keyboard users get a
     consistent focus indicator. :focus-visible (not :focus) so
     mouse clicks don't paint the ring. */
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), 0.16);
}
.file-browser-search-trigger__icon {
  /* Slightly muted to read as decoration, not as a primary
     affordance — the bar itself is the affordance. */
  color: var(--chat-section-label, rgba(var(--v-theme-on-surface), 0.48));
  flex-shrink: 0;
}
.file-browser-search-trigger__placeholder {
  /* Placeholder-style muted text, but rendered as a real <span>
     so the search bar still has visible content (pure CSS
     placeholders disappear on focus, and there's no focus
     state here). The flex:1 + overflow:ellipsis combo lets the
     placeholder shrink gracefully on narrow viewports without
     pushing the kbd hint off the right edge. */
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--chat-section-label, rgba(var(--v-theme-on-surface), 0.48));
}
.file-browser-search-trigger__hint {
  /* Small monospace pill on the right. Looks like a key
     cap — the standard "this has a shortcut" hint. The
     uppercase + small font size keeps it from competing
     with the placeholder text. Pointer-events:none so
     the whole button is still a single click target — if
     the user happens to click on the kbd, it should
     activate the search bar, not select the kbd text. */
  pointer-events: none;
  flex-shrink: 0;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 10.5px;
  line-height: 1;
  padding: 3px 6px;
  border: 1px solid var(--chat-border, rgba(var(--v-theme-on-surface), 0.2));
  border-radius: 4px;
  color: var(--chat-section-label, rgba(var(--v-theme-on-surface), 0.56));
  background: rgba(var(--v-theme-on-surface), 0.03);
  letter-spacing: 0.02em;
  text-transform: uppercase;
}
/* Inline search input. The shared block above handles flex /
   border / padding; this rule adds the focus ring on top so
   clicking the trigger -> focusing the input looks seamless. */
.file-browser-search-input::placeholder {
  color: var(--chat-section-label, rgba(var(--v-theme-on-surface), 0.48));
}
.file-browser-search-input:focus {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), 0.16);
}
/* True viewport fullscreen (2026-07-18). The Teleport wrapper in
   <template> moves this element to <body> while fullscreen is on;
   CSS then positions it `fixed; inset: 0` so it covers the entire
   viewport — not just the .git-diff-sidebar-body that normally
   hosts the file browser. z-index 9999 matches DocumentManager's
   overlay and sits above the sidebar's global fullscreen (1300),
   so the two modes can nest (file area covers the viewport; Esc
   peels back one layer at a time). The existing inner layout rules
   (flex-column root, flex-row body) keep working unchanged. */
.file-browser-view.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  width: 100%;
  height: 100%;
  background: rgb(var(--v-theme-background));
}
.file-browser-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  /* While dragging, suppress text selection / pointer-events on
     children so the cursor doesn't flicker into text-cursor mode
     over the entry list. */
}
.file-browser-body.resizing {
  cursor: col-resize;
  user-select: none;
}
/* Left pane takes the user-resized percent; min-width keeps long
   file names readable even at MIN_PERCENT. Right pane fills the
   remainder. Both are flex children with inline width from the
   resize handler so :style overrides any default flex-basis.
   `position: relative` anchors the absolutely-positioned collapse
   button to the pane's top-right corner. */
.file-browser-pane-left {
  position: relative;
  flex: 0 0 auto;
  min-width: 120px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.file-browser-pane-right {
  /* 2026-07-15: flex: 1 1 auto is now the SOLE width driver for
     the preview. Earlier revisions applied
     `width: 100 - leftPanePercent%` inline, which broke once a
     third pane (the history pane) was added — the inline style
     silently ignored the history pane and left the layout
     overflowing the sidebar body. flex: 1 1 auto lets the
     preview automatically take whatever space the left-pane /
     history-pane / dividers leave behind. min-width: 0 keeps
     long file paths from blowing out the pane. */
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
/* History pane container (2026-07-15 workspace-history-parity).
   Same flex contract as the document-manager history wrapper:
   `flex: 0 0 auto` lets the inline `width` from `historySplit`
   take over without flex-growing, and `min-width: 0` lets the
   panel's internal scroll handle overflow cleanly. The 1px
   left border is intentionally OMITTED here because the
   `file-browser-divider--history` divider right before this
   pane already supplies the visual separator (DocumentManager
   applies the same pattern). */
.file-browser-history {
  /* 2026-07-15 workspace-history-scroll: re-introduce the flex
     column context so the panel inside can fill the body height
     instead of growing with its content. Without `display: flex;
     flex-direction: column;` here, <DocumentHistoryPanel> renders
     as a regular block child at content height — long commit lists
     push past .file-browser-body's bottom edge and get clipped by
     its overflow:hidden, with .document-history-panel__list's
     overflow-y:auto never engaging. With it set, the panel
     becomes a flex item whose own `flex: 0 0 220px` would pin
     the height to 220px; the :deep() override below swaps that
     for `flex: 1 1 auto; min-height: 0` so the panel stretches to
     the body height and the inner list scrolls as intended.

     Width still comes from the inline `historySplit.percent.value`
     style (driven by the right-edge drag divider); flex: 0 0 auto
     keeps that inline width from being overridden by flex-grow. */
  flex: 0 0 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
/* Override <DocumentHistoryPanel>'s `flex: 0 0 220px` only inside
   the FileBrowserView tab. The panel is shared with
   <DocumentManager>, where its wrapper (.document-manager__history)
   is a plain block — flex-basis:220px is ignored there and the
   panel renders at content height. Here, with .file-browser-history
   a flex column container, the basis would resolve as a HEIGHT
   constraint in column direction; this override switches it to
   `flex: 1 1 auto; min-height: 0` so the panel stretches to the
   body's full height (via the grandparent's align-items: stretch)
   and the inner commit list scrolls within it. `:deep()` is
   required because DocumentHistoryPanel's <style scoped> attribute
   wouldn't otherwise reach into it. */
.file-browser-history :deep(.document-history-panel) {
  flex: 1 1 auto;
  min-height: 0;
}
/* Smooth width transition for collapse / expand. Suppressed during
   drag (`.resizing`) so mousemove updates don't lag behind the
   cursor. Also covers the divider + expand handle so the layout
   shifts as a single unit. */
.file-browser-pane-left,
.file-browser-pane-right,
.file-browser-divider,
.file-browser-divider--history,
.file-browser-expand-handle,
.file-browser-history {
  transition:
    width 0.2s ease,
    flex-basis 0.2s ease,
    padding 0.2s ease;
}
.file-browser-body.resizing .file-browser-pane-left,
.file-browser-body.resizing .file-browser-pane-right,
.file-browser-body.resizing .file-browser-divider,
.file-browser-body.resizing .file-browser-divider--history,
.file-browser-body.resizing .file-browser-expand-handle,
.file-browser-body.resizing .file-browser-history {
  transition: none;
}
.file-browser-preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 12.5px;
  text-align: center;
  padding: 32px 16px;
}
.file-browser-divider {
  width: 6px;
  margin: 0 -2px;
  /* Negative margin widens the hit target without changing the
     visible divider. The 1px inner border looks the same as before. */
  background: transparent;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  cursor: col-resize;
  flex-shrink: 0;
  position: relative;
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
}
.file-browser-divider:hover,
.file-browser-divider:active {
  background: rgba(var(--v-theme-primary), 0.18);
  border-left-color: rgba(var(--v-theme-primary), 0.5);
}
/* History divider (2026-07-15 workspace-history-parity): same
   hit-target band + hover treatment as the tree divider, but
   lives on the right edge of the body (next to the history
   pane). Identical styling so the two drag affordances read as
   the same UI component. */
.file-browser-divider--history:hover,
.file-browser-divider--history:active {
  background: rgba(var(--v-theme-primary), 0.18);
  border-left-color: rgba(var(--v-theme-primary), 0.5);
}
/* Collapse button: small chevron anchored to the top-right of the
   left pane. Only meaningful while a file is being previewed, but
   we always render it when previewPath is set (visibility is
   handled by the v-if guard in the template, not by display:none
   here). Subtle border + hover surface so it doesn't compete with
   the entry rows. */
.file-browser-collapse-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 5;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-surface), 0.6);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 4px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  cursor: pointer;
  padding: 0;
  transition:
    background 0.1s ease,
    color 0.1s ease,
    border-color 0.1s ease;
}
.file-browser-collapse-btn:hover,
.file-browser-collapse-btn:focus-visible {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  border-color: rgba(var(--v-theme-primary), 0.4);
  outline: none;
}
/* Expand handle: thin strip at the leftmost edge of the body when
   the left pane is collapsed. Mirrors the divider's hover treatment
   so the affordance is discoverable.

   2026-07-14: the previous version stacked a chevron and a vertical
   text label inside a fully-transparent 24px-wide strip. The label
   forced the button to grow to ~90–255px tall (zh-CN ≈ 90px, en-US
   ≈ 225px, ru-RU ≈ 255px), which overflowed the button area inside
   short containers (notably the diff-preview fullscreen overlay)
   and rendered on top of the breadcrumb above — making the handle
   look like floating text. This rewrite:
     - drops the vertical label (the i18n string is still on the
       native `title` tooltip, so accessibility is unchanged);
     - adds a subtle primary-tinted background + 1px border so the
       handle reads as a real button, not a floating glyph;
     - keeps the icon-only chevron centered so the button height
       stays anchored to the icon (~16px) plus padding, no matter
       how short the parent is. */
.file-browser-expand-handle {
  flex: 0 0 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-primary), 0.08);
  border: none;
  border-right: 1px solid rgba(var(--v-theme-primary), 0.2);
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  padding: 6px 0;
  align-self: stretch;
  transition:
    background 0.1s ease,
    color 0.1s ease,
    border-color 0.1s ease;
}
.file-browser-expand-handle:hover,
.file-browser-expand-handle:focus-visible {
  background: rgba(var(--v-theme-primary), 0.18);
  color: rgb(var(--v-theme-primary));
  border-right-color: rgba(var(--v-theme-primary), 0.5);
  outline: none;
}
/* Icon: stays horizontal so the chevron points right as expected.
   A small opacity dip keeps the icon from screaming at the user
   while still being clearly readable as the only label. */
.file-browser-expand-handle-icon {
  flex-shrink: 0;
  opacity: 0.95;
  writing-mode: horizontal-tb;
}
/* History expand handle (2026-07-15 workspace-history-parity):
   mirror of the left-handle with the chevron pointing the other
   way and the border on the LEFT edge so the handle reads as
   part of the body even though it's anchored to the right.
   Same icon-only chevron + primary tint + hover treatment as
   the left version — clicking it re-opens the pane at its
   previous `historySplit.percent` value (the percent ref
   survives the collapse so the layout doesn't snap to a new
   size on re-expand). */
.file-browser-expand-handle--history {
  /* Swap border-right to border-left so the visible separator
     sits on the side facing the body, not the outside. */
  border-right: none;
  border-left: 1px solid rgba(var(--v-theme-primary), 0.2);
}
.file-browser-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px 16px;
  min-height: 200px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.empty-text {
  font-size: 14px;
}

/* Mobile: stack the two panes vertically. The divider becomes a
   thin horizontal bar; on touch devices there's no drag, so the
   hit target stays 6px high. The collapse button is hidden on
   mobile (limited screen real estate — the user can use the
   breadcrumb / back button instead). */
@media (max-width: 760px) {
  .file-browser-body {
    flex-direction: column;
  }
  .file-browser-pane-left,
  .file-browser-pane-right {
    width: 100% !important;
  }
  .file-browser-pane-left {
    flex: 0 0 auto;
    max-height: 40vh;
    min-width: 0;
  }
  .file-browser-pane-right {
    flex: 1 1 auto;
  }
  .file-browser-divider {
    width: auto;
    height: 6px;
    margin: 0;
    border-left: none;
    border-top: 1px solid rgba(var(--v-theme-on-surface), 0.1);
    cursor: default;
  }
  /* 2026-07-15 workspace-history-parity: history pane stacks
     below the preview on narrow viewports, occupying the same
     column as the (resized) tree list. `flex: 0 0 auto` +
     `max-height: 40vh` keeps the per-file commit list scannable
     without monopolising the screen — mirrors how the tree
     pane caps itself above. The drag divider also rotates to
     horizontal here so the user can still resize by gesture. */
  .file-browser-history {
    width: 100% !important;
    flex: 0 0 auto;
    max-height: 40vh;
  }
  /* On mobile, the collapse button is redundant (the user can
     already scroll the entry list out of view by scrolling the
     pane). Hide it to save vertical space. */
  .file-browser-collapse-btn,
  .file-browser-expand-handle {
    display: none;
  }
}
</style>
