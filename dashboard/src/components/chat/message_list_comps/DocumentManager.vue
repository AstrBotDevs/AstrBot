<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §4.1
     Page container for the Documents sub-tab. Owns all editable
     state (docsRoot / selectedDoc / viewMode / selectedRevision /
     editMode / editBuffer) and orchestrates the 3 docs CRUD
     endpoints. Reuses the sidebar's existing useSpcodeGitLog and
     useSpcodeGitShow instances (per spec §2 decision #9 + §3.5). -->
<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeGitFile } from "@/composables/useSpcodeGitFile";
import { useSpcodeDocs } from "@/composables/useSpcodeDocs";
import { useSpcodeFileBrowser } from "@/composables/useSpcodeFileBrowser";
import { useSpcodeFileSearch } from "@/composables/useSpcodeFileSearch";
import { copyToClipboard } from "@/utils/clipboard";
import { pluginExtensionApi } from "@/api/v1";
import {
  parseSpcodeFileBrowser,
  FileBrowserParseError,
  type SpcodeFileBrowserRawResponse,
} from "@/composables/parseSpcodeFileBrowser";
import {
  loadDocsRoot,
  saveDocsRoot,
  DEFAULT_DOCS_ROOT,
  coerceDocsRoot,
  isValidDocsRoot,
  isProjectRootDocs,
} from "@/composables/docsRootStorage";
import { projectRelativeFromDoc } from "@/composables/pathUtils";
import type { UseSpcodeGitLog } from "@/composables/useSpcodeGitLog";
import type { UseSpcodeGitShow } from "@/composables/useSpcodeGitShow";
import { useModuleI18n } from "@/i18n/composables";

import DocumentPathBar from "./DocumentPathBar.vue";
import FileBrowserCodeView from "./FileBrowserCodeView.vue";
import SearchPanel from "./SearchPanel.vue";
import FileCommentEditor from "./FileCommentEditor.vue";
import { useDocumentMarkdownHighlight } from "@/composables/useDocumentMarkdownHighlight";
import {
  useFileComments,
  extractLineContext,
  extractRangeLineContext,
  type LineContext,
} from "@/composables/useFileComments";
import SelectionActionMenu from "./SelectionActionMenu.vue";
import DocumentTreePanel from "./DocumentTreePanel.vue";
import DocumentEditor from "./DocumentEditor.vue";
import DocumentHistoryPanel from "./DocumentHistoryPanel.vue";
import FileBrowserBreadcrumb from "./FileBrowserBreadcrumb.vue";
import DiffPreview from "./DiffPreview.vue";
import MarkdownView from "@/components/shared/MarkdownView.vue";
import { useResizableSplit } from "@/composables/useResizableSplit";
import {
  projectRelativePath,
  docsRootRelativePath,
  absoluteFromSelectedDoc,
} from "@/composables/pathUtils";

const props = defineProps<{
  worktree: string | null;
  umo: string | null;
  /**
   * Root of the file tree the docs sub-page is rooted at.
   * In a worktree context this is the ACTIVE worktree's path
   * (e.g. `F:/repo/.worktrees/feature-x`), not the loaded
   * spcode project's main checkout. GitDiffSidebar wires this
   * to its `currentRoot` computed (selectedWorktree ??
   * mainWorktreePath ?? projectRoot), which is the same value
   * the workspace FileBrowserView uses — so the breadcrumb's
   * "项目根" segment and the docsRoot path math both reflect
   * the worktree the user is currently looking at.
   *
   * The CRUD composable (useSpcodeDocs) is rooted at `worktree`
   * separately, so the listing/preview path (= this prop) and
   * the writes path (= :worktree) are in sync.
   */
  projectRoot: string | null;
  isDark?: boolean;
  gitLog: UseSpcodeGitLog;
  gitShow: UseSpcodeGitShow;
}>();

const { tm } = useModuleI18n("features/chat");
const spcodeStatus = useSpcodeProjectStatus();
const isDark = computed(() => !!props.isDark);
const isProjectLoaded = computed(() => spcodeStatus.status.value.loaded);

// Persisted state
const docsRoot = ref<string>(DEFAULT_DOCS_ROOT);
const storageOk = ref<boolean>(true);

// Per-file state
const selectedDoc = ref<string | null>(null);
const viewMode = ref<"raw" | "rendered" | "diff">("rendered");
const selectedRevision = ref<string | null>(null);
const editMode = ref<boolean>(false);
const editBuffer = ref<string>("");
const saveError = ref<string | null>(null);
const deleteError = ref<string | null>(null);
const renameError = ref<string | null>(null);
const pathMissingNotice = ref<string | null>(null);
let pathMissingTimer: ReturnType<typeof setTimeout> | null = null;

// The single fileBrowser is shared between two states:
//   - no selectedDoc  → pathRef points at the docs/ directory so
//                       the right pane is idle (tree is the source
//                       of truth for the listing).
//   - selectedDoc set → pathRef points at the projectRoot+selectedDoc
//                       file so fileBrowser transitions to kind="file"
//                       and fileContent picks up the snapshot.content.
// useSpcodeFileBrowser's internal watcher drives the fetch whenever
// this pathRef changes, so the parent's `onSave`/`onRename`/etc.
// just need to call `fileBrowser.refresh()` (no path arg) to
// re-read the same path after a mutation.
// The file-browser composable takes an absolute path and lists/previews
// whatever sits under it. The glue `projectRoot + docsRoot + selectedDoc`
// lives in `absoluteFromSelectedDoc` (see pathUtils.ts) — it's the
// inverse of `docsRootRelativePath` and already covers the docsRoot="."
// (project root) and empty docsRoot cases. A docsRoot of "." means
// "list the project root itself" — the helper drops the docs prefix
// and just hands projectRoot + selectedDoc to the file-browser
// endpoint.
//
// 2026-07-15 docsRoot-dot-bug-fix: the previous hand-rolled glue had
// an early return `if (!base || isProjectRootDocs(base)) return root`
// that ignored `selectedDoc`. With docsRoot="." and no file selected
// pathRef == projectRoot; once the user clicked a file, selectedDoc
// became "README.md" but the early return fired again, so pathRef
// stayed at projectRoot and `useSpcodeFileBrowser`'s deep-equal
// watcher saw no change — no file-browser request was sent, the
// preview pane stayed empty, and the right side silently looked
// dead. Delegating to the helper removes the duplicate and routes
// the file preview through the same code path DocumentTreePanel
// already uses for its `is-selected` highlight.
const fileBrowser = useSpcodeFileBrowser(
  computed(() =>
    absoluteFromSelectedDoc(
      props.projectRoot,
      docsRoot.value,
      selectedDoc.value ?? "",
    ),
  ),
);
const docsApi = useSpcodeDocs(computed(() => props.worktree));
const gitFile = useSpcodeGitFile(computed(() => props.worktree));

// The left-pane tree lives inside DocumentTreePanel which owns
// its own useSpcodeFileBrowser instance pointed at docsRoot. Our
// top-level `fileBrowser` is pointed at the *selected file*, not
// at the tree, so refreshing it does not re-fetch the listing.
// After save / rename / delete / create we have to nudge the
// tree to re-list explicitly — exposing refresh via a ref is the
// cheapest way without restructuring into a shared composable.
const treeRef = ref<{ refresh: () => Promise<void> } | null>(null);

// File preview from working tree (reuses file-browser).
const fileState = computed(() => {
  if (!selectedDoc.value) return { kind: "idle" as const };
  return fileBrowser.state.value;
});

const fileContent = computed<string>(() => {
  if (!selectedDoc.value) return "";
  const s = fileState.value;
  if (s.kind === "file" && typeof s.snapshot.content === "string") {
    return s.snapshot.content;
  }
  return "";
});

/** 2026-07-17 meta-row-parity: meta (name/size/mtime/encoding) of
 *  the selected doc, sourced from the shared file-browser snapshot
 *  — null while loading or for non-file states. Mirrors the
 *  workspace preview's `.preview-file-meta` data. */
const docMeta = computed(() =>
  fileState.value.kind === "file" ? fileState.value.snapshot.meta : null,
);

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}
function formatMtime(mtime: number | null): string {
  if (!mtime) return "—";
  return new Date(mtime * 1000).toLocaleString();
}

// Historical blob content
const historicalFileState = computed(() => {
  if (!selectedDoc.value || !selectedRevision.value) {
    return { kind: "idle" as const };
  }
  return gitFile.getState(selectedDoc.value, selectedRevision.value);
});
const historicalFileContent = computed<string>(() => {
  if (!selectedDoc.value || !selectedRevision.value) return "";
  const d = gitFile.getData(selectedDoc.value, selectedRevision.value);
  return d?.content ?? "";
});

/** Raw view text: historical blob when a revision is selected, otherwise
 *  the current file content. Single source of truth so the
 *  FileBrowserCodeView and the binary/empty fallback agree. */
const rawContent = computed<string>(() =>
  selectedRevision.value ? historicalFileContent.value : fileContent.value,
);

/** The docsRoot-relative path (matches FileBrowser's partition key
 *  convention). Used as the filePath prop on FileBrowserCodeView and
 *  as the partition key for useFileComments in Task 3. Empty string
 *  when no doc is selected — consumers guard with v-if. */
const rawFilePath = computed<string>(() => selectedDoc.value ?? "");

const { highlightedHtml: rawHighlightedHtml, isReady: rawHighlightReady } =
  useDocumentMarkdownHighlight(rawContent, isDark);

/** True for binary historical files. The raw view must not attempt to
 *  render binary bytes as markdown — fall back to a "binary file"
 *  placeholder. The current (HEAD) view does not expose is_binary,
 *  so this is only true when a revision is selected. */
const rawIsBinary = computed<boolean>(() => {
  if (!selectedRevision.value) return false;
  const state = gitFile.getState(
    selectedDoc.value ?? "",
    selectedRevision.value,
  );
  return state.kind === "ok" && state.data.isBinary === true;
});

// ── Inline comments (in-memory, shared singleton with FileBrowser) ──
// Store is keyed on docsRoot-relative path so different docs have
// independent comment lists. Module-level singleton means comments
// survive switching between Documents / Files sub-tabs (matches
// FileBrowser's expected behavior).
const fileComments = useFileComments();
const activeEditLine = ref<number | null>(null);
const activeEditCommentId = ref<string | null>(null);
const activeEditContext = ref<LineContext | null>(null);
const editorInitialText = ref<string>("");
/** 2026-07-17 selection-comment: holds the drag-selected range when
 *  the editor was opened from a selection (not the gutter "+").
 *  Echoed back in the save payload for addSelectionComment routing. */
const activeEditRange = ref<{
  startLine: number;
  endLine: number;
  selection: string;
} | null>(null);
/** 2026-07-17 selection-comment: copy-only menu state for the
 *  rendered-markdown container. */
const renderedMenu = ref<{ x: number; y: number; text: string } | null>(null);

const rawComments = computed(() =>
  rawFilePath.value ? fileComments.commentsForFile(rawFilePath.value) : [],
);

/** INVARIANT: register the current raw content into the comments store
 *  so addComment can extract line context. Same pattern as
 *  FileBrowserFilePreview.vue:300. */
watch(
  () => rawContent.value,
  (content) => {
    if (rawFilePath.value && content) {
      fileComments.registerFileContent(rawFilePath.value, content);
    }
  },
  { immediate: true },
);

// Diff patch (revision vs current)
const diffPatch = ref<string | null>(null);

watch(
  () => [selectedDoc.value, selectedRevision.value, viewMode.value] as const,
  async ([doc, rev, mode]) => {
    if (mode !== "diff" || !doc || !rev) {
      diffPatch.value = null;
      return;
    }
    diffPatch.value = null;
    await props.gitShow.fetchFile(rev, doc);
    const snap = props.gitShow.getFileData(rev, doc);
    if (snap) diffPatch.value = snap.patch ?? null;
  },
  { immediate: true },
);

// Body ref feeds the resizable-split composable so the percent math
// uses our actual layout width (not document.body).
const containerRef = ref<HTMLElement | null>(null);
const treeSplit = useResizableSplit({
  initialPercent: 30,
  minPercent: 15,
  maxPercent: 70,
  containerRef,
});
// History pane resizer. Anchored to the RIGHT edge (so percent
// is "distance from the right", matching the pane being on the
// right of the body). 220/15/40 keeps it usable as a commit
// list at default width while still permitting the user to
// shrink it almost out of the way to give the preview more room.
const historySplit = useResizableSplit({
  initialPercent: 22,
  minPercent: 15,
  maxPercent: 40,
  containerRef,
  direction: "right",
});
const isLeftPaneCollapsed = ref<boolean>(false);
// 2026-07-15 document-history-empty: the history pane is per-file
// (commits belong to a specific doc), so when no file is selected
// on mount there's nothing useful to show there. Default the pane
// to collapsed in that case so the user doesn't see the (now fixed)
// "no file selected" placeholder for no reason. Once the user
// manually toggles it, that choice wins — no forced sync with
// selectedDoc.
const isHistoryCollapsed = ref<boolean>(!selectedDoc.value);

/** Fullscreen review mode. NOT persisted — each visit starts at false.
 *
 *  2026-07-15 fullscreen-layout-parity: fullscreen and normal modes
 *  share the SAME layout (same pane tree, same expand handles). The
 *  only thing that changes between modes is positioning: the root
 *  gets teleported to <body> and styled `position: fixed; inset: 0`
 *  in fullscreen (see <Teleport> + .document-manager.is-fullscreen).
 *  Earlier revisions overlaid a separate left-rail trigger + offscreen
 *  drawer in fullscreen, which both differed from the normal layout
 *  AND leaked a `position: absolute` collapse button over the
 *  breadcrumb. */
const isFullscreen = ref<boolean>(false);

function toggleFullscreen(): void {
  isFullscreen.value = !isFullscreen.value;
}

function exitFullscreen(): void {
  isFullscreen.value = false;
}

// 2026-07-20 search-trigger: detect Mac so the kbd hint on
// the idle search bar can show "⌘ F" instead of the
// Windows/Linux "Ctrl F". Mirrors the same IIFE in
// FileBrowserView.vue. Kept inline rather than extracted into
// a shared composable because (a) this is the second use, and
// the rule of thumb is 3+ before extracting, and (b) the result
// is constant for the page's lifetime, so the value is captured
// at module init and never re-evaluated.
const isMacPlatform: boolean = (() => {
  if (typeof navigator === "undefined") return false;
  const uaDataPlatform = (
    navigator as Navigator & { userAgentData?: { platform?: string } }
  ).userAgentData?.platform;
  const platform = uaDataPlatform ?? navigator.platform ?? "";
  return /mac|iphone|ipad|ipod/i.test(platform);
})();
const searchShortcutLabel: string = isMacPlatform ? "⌘ F" : "Ctrl F";

// ── Docs search (2026-07-17 docs-search) ──────────────────────────
// Mirrors the workspace Files-view search (GitDiffSidebar toolbar +
// SearchPanel) but scoped to docsRoot via the backend's path_filter.
// Reuses the singleton useSpcodeFileSearch: the shared `query` ref
// drives the 300ms debounce; priming with an empty pattern only
// records the routing context (umo/worktree/pathFilter) without
// firing a network request. searchOpen is NOT persisted — each visit
// starts with the panel closed (matches isFullscreen).
const searchOpen = ref<boolean>(false);
const searchInputRef = ref<HTMLInputElement | null>(null);
/** One-shot scroll target for the raw-view FileBrowserCodeView after
 *  a content-hit click (1-based line; null = no scroll). Sticky like
 *  the workspace equivalent — the CodeView watcher guards on value
 *  changes, not on mount. */
const searchScrollToLine = ref<number | null>(null);
const { query: docsSearchQuery, search: docsSearch } = useSpcodeFileSearch();

/** Repo-relative directory scope for the docs search. null when the
 *  docs root IS the project root: the backend rejects "." as an
 *  unsafe filter, and an absent filter already means "search the
 *  whole worktree", which is exactly the project root. Trailing
 *  slashes are stripped so the prefix-strip in onSearchOpenFile can
 *  blindly append "/". */
const searchPathFilter = computed<string | null>(() => {
  const cleaned = docsRoot.value.replace(/\/+$/, "");
  return isProjectRootDocs(cleaned) ? null : cleaned;
});

function primeDocsSearch(): void {
  void docsSearch({
    umo: props.umo,
    worktree: props.worktree,
    pattern: "",
    pathFilter: searchPathFilter.value ?? undefined,
  });
}

watch(searchOpen, async (open) => {
  if (open) {
    // Re-prime in case umo/worktree/docsRoot changed while closed.
    primeDocsSearch();
    await nextTick();
    searchInputRef.value?.focus();
  } else {
    docsSearchQuery.value = "";
  }
});

// Keep the scope honest when the user edits docsRoot mid-search:
// re-prime so the next debounced keystroke searches the new root.
// Existing results stay until the query changes (matches the
// workspace behaviour on worktree switches).
watch(docsRoot, () => {
  if (searchOpen.value) primeDocsSearch();
});

// :value + @input (not v-model) — the query is shared state owned by
// the composable singleton; writing it is what drives the search.
function onSearchInput(e: Event): void {
  docsSearchQuery.value = (e.target as HTMLInputElement).value;
}

function onSearchClose(e: KeyboardEvent): void {
  e.stopPropagation();
  searchOpen.value = false;
}

/** 2026-07-20 search-toggle-button: the explicit magnifier button
 *  on the right of the toolbar. Toggles the panel — opens when
 *  closed, closes when open. Mirrors the same role in
 *  FileBrowserView.vue. */
function toggleSearch(): void {
  searchOpen.value = !searchOpen.value;
}

/** Open a search hit in the manager. `path` is repo-relative POSIX
 *  (the backend searches with path_filter=docsRoot, so every hit is
 *  inside the docs root); selectedDoc is docsRoot-relative, hence the
 *  prefix strip. Content hits (line > 0) open in raw view centred on
 *  the hit line; filename hits mirror onTreeSelect's view resets. */
async function onSearchOpenFile(p: {
  path: string;
  line: number;
}): Promise<void> {
  // Same dirty-edit guard as onTreeSelect: switching docs discards
  // the unsaved buffer, so confirm first. Declining keeps the panel
  // open so the user can pick a different result.
  if (editMode.value) {
    const ok = window.confirm(
      tm("spcodeProjectLoad.documentManager.editor.cancelDirty"),
    );
    if (!ok) return;
  }
  const prefix = searchPathFilter.value ? searchPathFilter.value + "/" : "";
  // Defensive: the backend already scopes results, never trust it.
  if (prefix && !p.path.startsWith(prefix)) return;
  const doc = prefix ? p.path.slice(prefix.length) : p.path;
  if (!doc) return;
  selectedDoc.value = doc;
  selectedRevision.value = null;
  editMode.value = false;
  editBuffer.value = "";
  saveError.value = null;
  searchOpen.value = false;
  if (p.line > 0) {
    viewMode.value = "raw";
    // Two-step assignment: the CodeView watcher is not immediate, so a
    // null→line transition guarantees it fires even when the same line
    // is clicked twice, or when the view switch mounts the CodeView
    // with the highlight already rendered.
    searchScrollToLine.value = null;
    await nextTick();
    searchScrollToLine.value = p.line;
  } else {
    viewMode.value = "rendered";
    searchScrollToLine.value = null;
  }
}

/** Esc exits fullscreen (when fullscreen is on). Listener is attached
 *  on mount, detached on unmount. It does NOT preventDefault so other
 *  components can still handle Esc for their own purposes (e.g. close
 *  the comment editor) — we only react when fullscreen is on. The
 *  listener is bound to `document` (not the overlay) so that the
 *  keydown still fires after the root is teleported to <body>; the
 *  `isFullscreen` guard filters out the non-overlay case.
 *
 *  2026-07-18: the listener now runs in the CAPTURE phase and the
 *  fullscreen branch calls stopPropagation(). GitDiffSidebar's global
 *  fullscreen Escape handler lives on `document` in the bubble phase,
 *  so without this an Esc press with BOTH modes active would tear
 *  down the sidebar-wide fullscreen too — capture + stopPropagation
 *  makes Esc peel back only this inner overlay.
 *
 *  2026-07-17 docs-search: the same listener also owns the search
 *  shortcuts — Cmd/Ctrl+F toggles the panel, Esc closes it when
 *  focus is outside the toolbar input / panel (the input's own
 *  keydown.escape.stop handler wins there). Registered here rather
 *  than in GitDiffSidebar because this component only exists while
 *  viewMode === "docs", so the two never race. */
function onKeyDown(e: KeyboardEvent): void {
  if (e.key === "Escape" && isFullscreen.value) {
    e.stopPropagation();
    exitFullscreen();
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
      !target.closest(".document-manager__search-input")
    ) {
      searchOpen.value = false;
    }
  }
}
onMounted(() => document.addEventListener("keydown", onKeyDown, true));

// ── Copy content (2026-07-17 docs-copy-btn) ───────────────────────
// Mirrors FileBrowserFilePreview's copy affordance: copies the raw
// text (historical blob when a revision is selected, otherwise the
// working-tree content) and flashes a transient success/fail state
// on the button for 2s. Diff view is excluded (that body is owned
// by DiffPreview); edit mode has its own copy button inside
// DocumentEditor's action bar.
const copyButtonText = ref<string>(
  tm("spcodeProjectLoad.fileBrowser.preview.copy"),
);
const copyButtonState = ref<"idle" | "success" | "error">("idle");
/** 2026-07-17 toolbar-style-unify: v-btn color for the transient
 *  copy feedback (mirrors FileBrowserFilePreview.copyButtonColor). */
const copyButtonColor = computed<string>(() =>
  copyButtonState.value === "success"
    ? "success"
    : copyButtonState.value === "error"
      ? "error"
      : "primary",
);
let copyResetTimer: ReturnType<typeof setTimeout> | null = null;

/** Copy is only meaningful when there is raw text on screen: a doc
 *  selected, not in edit mode (DocumentEditor owns copying there),
 *  not the diff view, not a binary/empty body. */
const canCopyContent = computed<boolean>(
  () =>
    !!selectedDoc.value &&
    !editMode.value &&
    viewMode.value !== "diff" &&
    !rawIsBinary.value &&
    !!rawContent.value,
);

watch([selectedDoc, selectedRevision], () => {
  // New document / revision → clear leftover feedback so a "已复制"
  // from the previous target does not leak into the fresh header.
  copyButtonText.value = tm("spcodeProjectLoad.fileBrowser.preview.copy");
  copyButtonState.value = "idle";
});

async function onCopyContent(): Promise<void> {
  const text = rawContent.value;
  if (!text) return;
  // Cancel any in-flight reset before scheduling a new one so rapid
  // double-clicks don't race the old timer mid-feedback.
  if (copyResetTimer) {
    clearTimeout(copyResetTimer);
    copyResetTimer = null;
  }
  const ok = await copyToClipboard(text);
  copyButtonState.value = ok ? "success" : "error";
  copyButtonText.value = tm(
    ok
      ? "spcodeProjectLoad.fileBrowser.preview.copySuccess"
      : "spcodeProjectLoad.fileBrowser.preview.copyFail",
  );
  copyResetTimer = setTimeout(() => {
    copyButtonText.value = tm("spcodeProjectLoad.fileBrowser.preview.copy");
    copyButtonState.value = "idle";
    copyResetTimer = null;
  }, 2000);
}

onBeforeUnmount(() => {
  // Drop a pending reset timer so it can't write to destroyed refs.
  if (copyResetTimer) {
    clearTimeout(copyResetTimer);
    copyResetTimer = null;
  }
});

// ── Preset quick paths (2026-07-17 docs-presets) ─────────────────
// One-click shortcuts rendered next to the DocumentPathBar. Two
// kinds:
//   - "dir":  switch docsRoot to the directory (same as typing it
//             into the path bar — validated + persisted).
//   - "file": switch docsRoot to the project root (".") AND select
//             the file so it opens directly.
// Existence is probed per click via the stateless /spcode/file-browser
// endpoint (the same one the tree + preview use); a missing target
// shows a transient notice and does NOT navigate.
interface DocPreset {
  label: string;
  kind: "dir" | "file";
  /** Project-relative POSIX path (file presets live at the root). */
  path: string;
}
const DOC_PRESETS: readonly DocPreset[] = [
  { label: "AGENTS.md", kind: "file", path: "AGENTS.md" },
  { label: "README.md", kind: "file", path: "README.md" },
  { label: "specs", kind: "dir", path: "docs/superpowers/specs" },
  { label: "plans", kind: "dir", path: "docs/superpowers/plans" },
  { label: "changelogs", kind: "dir", path: "changelogs" },
];

const presetNotice = ref<string | null>(null);
let presetNoticeTimer: ReturnType<typeof setTimeout> | null = null;
/** Path of the preset currently being probed; disables that button
 *  so a slow filesystem doesn't collect duplicate clicks. */
const presetChecking = ref<string | null>(null);

function showPresetNotice(message: string): void {
  presetNotice.value = message;
  if (presetNoticeTimer) clearTimeout(presetNoticeTimer);
  presetNoticeTimer = setTimeout(() => {
    presetNotice.value = null;
    presetNoticeTimer = null;
  }, 5000);
}

/** Active-state for the preset chip: dir presets are active when
 *  they ARE the docs root; file presets when the project root is
 *  the docs root and the file itself is selected. */
function isPresetActive(p: DocPreset): boolean {
  if (p.kind === "dir") return docsRoot.value === p.path;
  return isProjectRootDocs(docsRoot.value) && selectedDoc.value === p.path;
}

async function onPresetClick(p: DocPreset): Promise<void> {
  if (!props.projectRoot || presetChecking.value) return;
  presetChecking.value = p.path;
  try {
    // Probe the same absolute target the tree would list (the
    // endpoint is stateless and resolves absolute paths).
    const abs = `${props.projectRoot.replace(/[\\/]+$/, "")}/${p.path}`;
    const resp = await pluginExtensionApi.get<SpcodeFileBrowserRawResponse>(
      "spcode/file-browser",
      { params: { path: abs } },
    );
    const data = resp.data?.data;
    if (!data) {
      showPresetNotice(
        tm("spcodeProjectLoad.documentManager.presets.checkFailed", {
          path: p.path,
        }),
      );
      return;
    }
    try {
      parseSpcodeFileBrowser(data);
    } catch (err) {
      const missing =
        err instanceof FileBrowserParseError &&
        err.reason === "path_not_found";
      showPresetNotice(
        tm(
          missing
            ? "spcodeProjectLoad.documentManager.presets.notFound"
            : "spcodeProjectLoad.documentManager.presets.checkFailed",
          { path: p.path },
        ),
      );
      return;
    }
  } catch {
    // Network / unexpected failure: never navigate blindly.
    showPresetNotice(
      tm("spcodeProjectLoad.documentManager.presets.checkFailed", {
        path: p.path,
      }),
    );
    return;
  } finally {
    presetChecking.value = null;
  }
  // Target exists → navigate.
  if (p.kind === "dir") {
    onPathChange(p.path); // validates + persists + clears selection
    return;
  }
  // File preset: root the manager at the project root and open the
  // file directly (mirrors onTreeSelect's state resets).
  onPathChange(".");
  selectedDoc.value = p.path;
  viewMode.value = "rendered";
  selectedRevision.value = null;
  editMode.value = false;
  editBuffer.value = "";
  saveError.value = null;
}

onBeforeUnmount(() => {
  if (presetNoticeTimer) {
    clearTimeout(presetNoticeTimer);
    presetNoticeTimer = null;
  }
});

/** Body scroll lock while fullscreen is on. Matches the DiffPreview
 *  fullscreen pattern (spec 2026-06-30 §3.4) — saves the user's
 *  scroll position implicitly via `overflow: hidden`. The watcher
 *  resets to "" (browser default), so any *previous* element on
 *  <body> that had set overflow:hidden is silently overwritten; we
 *  restore on unmount so the body returns to its normal scroll
 *  state even if the user navigates away mid-fullscreen. */
watch(isFullscreen, (v) => {
  document.body.style.overflow = v ? "hidden" : "";
});

// Breadcrumb path. FileBrowserBreadcrumb expects an absolute
// path (it uses case-insensitive root match to render the
// "项目根 / docs / ... / README.md" hierarchy). When a file is
// being previewed we anchor on that file so the leaf shows a
// document icon; otherwise we anchor on the docs directory.
// A docsRoot of "." resolves to the project root — the breadcrumb
// shows just "项目根" with no extra "docs" segment in that case.
const breadcrumbPath = computed<string>(() => {
  const root = props.projectRoot;
  if (!root) return "";
  const dir = docsRoot.value?.trim() ?? "";
  const base =
    !dir || isProjectRootDocs(dir)
      ? root
      : `${root.replace(/[\\/]+$/, "")}/${dir.replace(/^[\\/]+/, "")}`;
  if (selectedDoc.value) {
    return `${base.replace(/[\\/]+$/, "")}/${selectedDoc.value.replace(
      /^[\\/]+/,
      "",
    )}`;
  }
  return base;
});
const breadcrumbPreviewPath = computed<string | null>(() => {
  return selectedDoc.value ? breadcrumbPath.value : null;
});

function hydrate() {
  if (!props.umo) {
    docsRoot.value = DEFAULT_DOCS_ROOT;
    return;
  }
  docsRoot.value = loadDocsRoot(props.umo);
}

onMounted(hydrate);
watch(() => props.umo, hydrate);

function onPathChange(newPath: string) {
  const cleaned = coerceDocsRoot(newPath);
  if (!isValidDocsRoot(cleaned)) {
    return;
  }
  docsRoot.value = cleaned;
  selectedDoc.value = null;
  selectedRevision.value = null;
  editMode.value = false;
  if (props.umo) {
    const r = saveDocsRoot(props.umo, cleaned);
    storageOk.value = r.ok || r.reason !== "storage_unavailable";
  }
}

function onTreeNavigate(dirRel: string) {
  // The breadcrumb's "项目根" segment emits an empty string.
  // 2026-07-17 breadcrumb-root-fix: navigate to the actual project
  // root (".") instead of falling back to the default docs/ folder —
  // users expect "项目根" to show the project root. The tree and the
  // preview already support a "." docs root (isProjectRootDocs), and
  // the breadcrumb renders just "项目根" for it.
  docsRoot.value = dirRel || ".";
  selectedDoc.value = null;
  selectedRevision.value = null;
  editMode.value = false;
}

// 2026-07-20: FileBrowserBreadcrumb's emit switched from a bare
// absolute path to a `{ dirPath, previewPath }` payload so the
// path-input feature can route a typed file path to "navigate to
// the parent AND select this file" (mirroring FileBrowserView's
// behaviour). Segment clicks always send previewPath: null so
// the directory branch below is a pure docsRoot change.
//
// Path glue is the same as the old single-string version:
// file-browser entries are absolute, but docsRoot / selectedDoc
// are stored project- / docsRoot-relative. projectRelativePath
// and docsRootRelativePath (pathUtils.ts) are the single source
// of truth for that translation — using them here keeps the
// "F:\repo\docs\F:\repo\docs/..." double-prefix bug out of this
// handler too.
//
// 2026-07-20 dirty-edit guard: the previous onTreeNavigate had
// no check (it just reset editMode), silently discarding unsaved
// edits on a segment click. The path-input flow is more
// "intentional" than a segment click, so we surface the prompt
// up front and let the user either confirm or cancel. Matches
// FileBrowserView's confirmLeaveEditing().
function onBreadcrumbNavigate(payload: {
  dirPath: string;
  previewPath: string | null;
}): void {
  if (editMode.value) {
    const ok = window.confirm(
      tm("spcodeProjectLoad.documentManager.editor.cancelDirty"),
    );
    if (!ok) return;
  }

  const dirRel = projectRelativePath(payload.dirPath, props.projectRoot);
  docsRoot.value = dirRel || ".";
  selectedRevision.value = null;
  editMode.value = false;
  editBuffer.value = "";
  saveError.value = null;

  if (payload.previewPath) {
    // File path typed in the path input: also select the file so
    // the right pane renders its content. docsRootRelativePath
    // strips projectRoot + docsRoot and returns the basename (or
    // nested segment if the user typed a deeper path than we
    // navigated to, which shouldn't happen for our file-vs-dir
    // detection in the breadcrumb but is defended by the helper).
    selectedDoc.value = docsRootRelativePath(
      payload.previewPath,
      props.projectRoot,
      dirRel || ".",
    );
    viewMode.value = "rendered";
  } else {
    // Directory navigation: clear any previously-selected file.
    selectedDoc.value = null;
  }
}

function onTreeSelect(fileRel: string) {
  if (editMode.value) {
    const ok = window.confirm(
      tm("spcodeProjectLoad.documentManager.editor.cancelDirty"),
    );
    if (!ok) return;
  }
  selectedDoc.value = fileRel;
  selectedRevision.value = null;
  viewMode.value = "rendered";
  editMode.value = false;
  editBuffer.value = "";
  saveError.value = null;
}

function onStartEdit() {
  editBuffer.value = fileContent.value;
  editMode.value = true;
}

async function onSave(content: string) {
  if (!selectedDoc.value) return;
  saveError.value = null;
  // docsApi.save expects a project-relative path (the backend
  // resolves it against projectRoot via _validate_repo_relative_file).
  // selectedDoc is docsRoot-relative, so we have to glue docsRoot
  // on the front. For docsRoot="." the file is already at the root
  // and projectRelativeFromDoc returns selectedDoc unchanged.
  const r = await docsApi.save({
    path: projectRelativeFromDoc(docsRoot.value, selectedDoc.value),
    content,
  });
  if (r.ok) {
    // Sync `editBuffer` to whatever we just sent to the backend so
    // DocumentEditor's `isDirty` (buffer !== props.initialContent) is
    // false on the next render. Without this the editor kept showing
    // "unsaved changes" after a successful save and a subsequent
    // cancel would surface a misleading dirty-confirm dialog. Pin
    // viewMode to "rendered" so the user lands on the read view they
    // were in before pressing Edit (matches the cancel path).
    editMode.value = false;
    viewMode.value = "rendered";
    editBuffer.value = content;
    void fileBrowser.refresh();
    void treeRef.value?.refresh();
  } else {
    saveError.value = `${tm(
      "spcodeProjectLoad.documentManager.editor.saveError",
    )}: ${r.reason}`;
    // Drop the stale editBuffer so the editor reverts to whatever is
    // actually on disk. The user can re-open the file and start over
    // from the latest persisted content rather than the failed draft.
    editBuffer.value = fileContent.value;
  }
}

function onCancelEdit() {
  editMode.value = false;
}

async function onDelete() {
  if (!selectedDoc.value) return;
  deleteError.value = null;
  // Same project-relative path fix as onSave: selectedDoc is
  // docsRoot-relative, the backend needs the project-relative form.
  const r = await docsApi.remove(
    projectRelativeFromDoc(docsRoot.value, selectedDoc.value),
  );
  if (r.ok) {
    selectedDoc.value = null;
    selectedRevision.value = null;
    editMode.value = false;
    void fileBrowser.refresh();
    void treeRef.value?.refresh();
  } else {
    deleteError.value = `${tm(
      "spcodeProjectLoad.documentManager.editor.deleteError",
    )}: ${r.reason}`;
  }
}

function onRename(newPath: string) {
  if (!selectedDoc.value) return;
  renameError.value = null;
  // Both `path` (the existing file) and `newPath` (the user-typed
  // value from DocumentEditor's rename input) are docsRoot-relative;
  // the backend resolves them against projectRoot, so we have to
  // glue docsRoot onto each.
  void docsApi
    .rename({
      path: projectRelativeFromDoc(docsRoot.value, selectedDoc.value),
      newPath: projectRelativeFromDoc(docsRoot.value, newPath),
    })
    .then((r) => {
      if (r.ok) {
        // Keep selectedDoc in docsRoot-relative form (it's still
        // the same file, just with a new name).
        selectedDoc.value = newPath;
        void fileBrowser.refresh();
        void treeRef.value?.refresh();
      } else {
        renameError.value = `${tm(
          "spcodeProjectLoad.documentManager.editor.renameError",
        )}: ${r.reason}`;
      }
    });
}

function onSelectRevision(sha: string) {
  if (!selectedDoc.value) return;
  selectedRevision.value = sha;
  viewMode.value = "rendered";
  if (selectedDoc.value && sha) {
    void gitFile.fetchRef(selectedDoc.value, sha);
  }
}

function onCompareCurrent(sha: string) {
  if (!selectedDoc.value) return;
  selectedRevision.value = sha;
  viewMode.value = "diff";
}

function onCreateNew(name: string) {
  // selectedDoc is always stored as a docsRoot-relative path.
  // The backend POST /spcode/docs resolves `path` against the
  // project root (project-relative), so we have to glue docsRoot
  // onto the user-supplied filename before sending. projectRelativeFromDoc
  // handles the docsRoot="." (project root) case by returning
  // `name` unchanged.
  const cleanName = name.replace(/^\/+/, "");
  selectedDoc.value = cleanName;
  editBuffer.value = "";
  editMode.value = true;
  void docsApi
    .save({
      path: projectRelativeFromDoc(docsRoot.value, cleanName),
      content: "",
    })
    .then((r) => {
      if (r.ok) {
        void fileBrowser.refresh();
        void treeRef.value?.refresh();
      } else {
        saveError.value = r.reason;
        selectedDoc.value = null;
        editMode.value = false;
      }
    });
}

function onBackToCurrent() {
  selectedRevision.value = null;
}

function onRequestAddComment(line: number): void {
  if (!rawFilePath.value || !rawContent.value) return;
  const ctx = extractLineContext(rawContent.value, line);
  if (!ctx) return;
  activeEditLine.value = line;
  activeEditCommentId.value = null;
  activeEditRange.value = null;
  activeEditContext.value = ctx;
  editorInitialText.value = "";
}

/** 2026-07-17 selection-comment: open the editor in range mode from
 *  a drag-selection. `activeEditContext` is populated via
 *  extractRangeLineContext so the existing
 *  `v-if="activeEditLine !== null && activeEditContext"` gate keeps
 *  working unchanged. */
function onRequestAddRange(payload: {
  startLine: number;
  endLine: number;
  selection: string;
}): void {
  if (!rawFilePath.value || !rawContent.value) return;
  const ctx = extractRangeLineContext(
    rawContent.value,
    payload.startLine,
    payload.endLine,
    payload.selection,
  );
  activeEditLine.value = payload.startLine;
  activeEditCommentId.value = null;
  activeEditRange.value = payload;
  activeEditContext.value = ctx;
  editorInitialText.value = "";
}

function onRequestCopySelection(text: string): void {
  void copyToClipboard(text);
}

/** 2026-07-17 selection-comment: rendered-markdown container
 *  mouseup → copy-only menu (no source-line mapping in rendered
 *  HTML, so the comment item is hidden). */
function onRenderedMouseUp(e: MouseEvent): void {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) {
    renderedMenu.value = null;
    return;
  }
  const root = e.currentTarget as HTMLElement | null;
  if (!root || !sel.anchorNode || !root.contains(sel.anchorNode)) {
    renderedMenu.value = null;
    return;
  }
  const text = sel.toString();
  if (!text.trim()) {
    renderedMenu.value = null;
    return;
  }
  renderedMenu.value = { x: e.clientX, y: e.clientY, text };
}

function onRenderedCopy(): void {
  if (renderedMenu.value) void copyToClipboard(renderedMenu.value.text);
  renderedMenu.value = null;
}

// 2026-07-17 selection-comment: a view-mode switch swaps the DOM
// under the menu (the selection itself is gone), so drop any open
// copy-menu instead of leaving it floating at stale coordinates.
watch(viewMode, () => {
  renderedMenu.value = null;
});

function onRequestEditComment(commentId: string): void {
  const c = fileComments.findCommentById(commentId);
  if (!c) return;
  activeEditLine.value = c.line;
  activeEditCommentId.value = c.id;
  // 2026-07-17 selection-comment: restore range mode when editing
  // an existing range comment.
  activeEditRange.value =
    c.endLine !== undefined && c.endLine > c.line
      ? {
          startLine: c.line,
          endLine: c.endLine,
          selection: c.selection ?? c.lineContent,
        }
      : null;
  activeEditContext.value = {
    lineContent: c.lineContent,
    contextBefore: c.contextBefore,
    contextAfter: c.contextAfter,
  };
  editorInitialText.value = c.text;
}

function onSaveComment(payload: {
  text: string;
  commentId: string | null;
  line: number;
  endLine: number | null;
  selection: string | null;
}): void {
  if (payload.commentId) {
    fileComments.updateComment(payload.commentId, payload.text);
    closeCommentEditor();
    return;
  }
  if (!rawFilePath.value) return;
  // 2026-07-17 selection-comment: the editor echoes the range in
  // the save payload when it was opened in range mode.
  const created =
    payload.endLine !== null &&
    payload.endLine > payload.line &&
    payload.selection !== null
      ? fileComments.addSelectionComment({
          filePath: rawFilePath.value,
          startLine: payload.line,
          endLine: payload.endLine,
          selection: payload.selection,
          text: payload.text,
        })
      : fileComments.addComment({
          filePath: rawFilePath.value,
          line: payload.line,
          text: payload.text,
        });
  // created === null means the contentCache was empty (would happen
  // only if the user clicked a line before rawContent arrived).
  // Silently close — same behavior as FileBrowserFilePreview.
  closeCommentEditor();
}

function onDeleteComment(commentId: string): void {
  fileComments.deleteComment(commentId);
  closeCommentEditor();
}

function closeCommentEditor(): void {
  activeEditLine.value = null;
  activeEditCommentId.value = null;
  activeEditRange.value = null;
  activeEditContext.value = null;
}

/** Single teardown hook: detach the Esc listener, release the body
 *  scroll lock if it was applied, and dispose of the long-lived
 *  composables. Kept as one hook (instead of three small ones) per
 *  AGENTS.md's "no unnecessary helpers / no fragmentation" rule:
 *  every line here runs unconditionally on unmount, and the order
 *  doesn't matter — splitting them would just produce more Vue
 *  lifecycle overhead. */
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKeyDown, true);
  if (isFullscreen.value) {
    document.body.style.overflow = "";
  }
  if (pathMissingTimer) {
    clearTimeout(pathMissingTimer);
    pathMissingTimer = null;
  }
  gitFile.dispose();
  docsApi.dispose();
});
</script>

<template>
  <!--
    Fullscreen overlay (spec 2026-07-14 §3.2 + DiffPreview pattern
    from spec 2026-06-30): escape the parent sidebar by teleporting
    the root to <body> while fullscreen is on, then position it
    fixed inset 0. The `:disabled` flag keeps the same component
    tree in-place when fullscreen is off — Vue 3's Teleport becomes
    a transparent pass-through, so the existing chat-panel layout
    (sidebar body → document-manager flex column) is untouched on
    the normal-render path. No duplicated templates, no duplicated
    refs, no duplicated state.
  -->
  <Teleport to="body" :disabled="!isFullscreen">
    <div class="document-manager" :class="{ 'is-fullscreen': isFullscreen }">
      <div class="document-manager__path-row">
        <DocumentPathBar
          :current-path="docsRoot"
          :storage-ok="storageOk"
          :default-path="DEFAULT_DOCS_ROOT"
          @path-change="onPathChange"
        />
        <!-- 2026-07-17 docs-presets: one-click quick paths. dir
             presets switch the docs root; file presets root the
             manager at the project root and open the file directly.
             A missing target shows a transient notice (below) and
             does NOT navigate. -->
        <div
          class="document-manager__presets"
          role="group"
          :aria-label="tm('spcodeProjectLoad.documentManager.presets.label')"
        >
          <button
            v-for="p in DOC_PRESETS"
            :key="p.path"
            type="button"
            class="document-manager__preset-btn"
            :class="{ 'is-active': isPresetActive(p) }"
            :disabled="presetChecking === p.path"
            :title="p.path"
            @click="onPresetClick(p)"
          >
            <v-icon size="12">{{
              p.kind === "file"
                ? "mdi-file-document-outline"
                : "mdi-folder-outline"
            }}</v-icon>
            {{ p.label }}
          </button>
        </div>
        <!-- 2026-07-18 file-area fullscreen (elecvoid243): re-add the
             toggle that drives the long-dormant isFullscreen/Teleport
             machinery below (the button was dropped in an earlier
             toolbar rework, leaving the overlay unreachable). Pinned
             to the right edge of the path row via margin-left:auto;
             icon-only v-btn matching the sidebar header chrome and
             the workspace tab's new fullscreen button. -->
        <v-btn
          class="document-manager__fullscreen-toggle"
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
      <div
        v-if="pathMissingNotice"
        class="document-manager__notice document-manager__notice--warn"
      >
        {{
          tm("spcodeProjectLoad.documentManager.tree.pathMissing", {
            path: docsRoot,
          })
        }}
      </div>
      <!-- 2026-07-17 docs-presets: transient not-found / check-failed
           notice for preset clicks (auto-clears after 5s). -->
      <div
        v-if="presetNotice"
        class="document-manager__notice document-manager__notice--warn"
      >
        {{ presetNotice }}
      </div>
      <div v-if="!isProjectLoaded" class="document-manager__empty">
        <v-icon size="32" color="grey">mdi-folder-open-outline</v-icon>
        <span>{{ tm("spcodeProjectLoad.documentManager.noProject") }}</span>
      </div>
      <template v-else>
        <!--
        2026-07-13: mirror the FileBrowserView layout — lift the
        breadcrumb out of the file-list pane so it stays visible
        while a file is being previewed, then put the resizable +
        collapsible panes below. FileBrowserBreadcrumb's
        case-insensitive root match needs an absolute currentPath
        (we feed it projectRoot+docsRoot+selectedDoc), and the
        breadcrumb-navigate emit is wired to onTreeNavigate so
        clicking a segment updates docsRoot via the toProjectRel
        conversion in DocumentTreePanel.
      -->
        <!-- 2026-07-17 docs-search: search toolbar (toggle + input).
             Sits above the breadcrumb/body so it survives the
             SearchPanel ↔ body v-if swap below — mirrors the
             git-diff-sidebar-files-toolbar pattern. The input binds
             the shared docsSearchQuery ref (:value + @input); the
             composable owns the 300ms debounce. Esc on the input
             closes the panel. -->
        <!-- 2026-07-20 search-trigger: idle state is a full-width
             "fake" search bar (button styled as an input). Click
             activates it; the existing watcher auto-focuses the
             real <input>. Mirrors FileBrowserView's search
             toolbar — they share the same data shape, i18n
             keys, and the same shared CSS variables so the two
             read identically. -->
        <div
          class="document-manager__search-toolbar"
          data-testid="document-manager-search-toolbar"
        >
          <button
            v-if="!searchOpen"
            type="button"
            class="document-manager__search-trigger"
            :title="tm('spcodeProjectLoad.diffSidebar.search.button')"
            :aria-label="tm('spcodeProjectLoad.diffSidebar.search.button')"
            @click="searchOpen = true"
          >
            <v-icon size="16" class="document-manager__search-trigger__icon">mdi-magnify</v-icon>
            <span class="document-manager__search-trigger__placeholder">
              {{ tm('spcodeProjectLoad.diffSidebar.search.placeholder') }}
            </span>
            <kbd class="document-manager__search-trigger__hint" aria-hidden="true">{{ searchShortcutLabel }}</kbd>
          </button>
          <input
            v-else
            ref="searchInputRef"
            :value="docsSearchQuery"
            type="text"
            class="document-manager__search-input"
            :placeholder="
              tm('spcodeProjectLoad.diffSidebar.search.placeholder')
            "
            spellcheck="false"
            autocomplete="off"
            @input="onSearchInput"
            @keydown.escape.stop="onSearchClose"
          />
          <v-btn
            icon
            size="small"
            variant="text"
            :class="[
              'document-manager__search-toggle',
              { 'is-active': searchOpen },
            ]"
            :title="tm('spcodeProjectLoad.diffSidebar.search.button')"
            :aria-label="tm('spcodeProjectLoad.diffSidebar.search.button')"
            :aria-pressed="searchOpen"
            @click="toggleSearch"
          >
            <v-icon size="16">mdi-magnify</v-icon>
          </v-btn>
        </div>
        <FileBrowserBreadcrumb
          v-if="projectRoot"
          class="document-manager__breadcrumb"
          :current-path="breadcrumbPath"
          :root-path="projectRoot"
          :preview-path="breadcrumbPreviewPath"
          :is-dark="isDark"
          @navigate="onBreadcrumbNavigate"
        />
        <!-- 2026-07-17 docs-search: SearchPanel replaces the panes
             body while open (toolbar + breadcrumb stay visible above),
             mirroring FileBrowserView. path-filter scopes the backend
             search to the docs root. -->
        <SearchPanel
          v-if="searchOpen"
          v-model="searchOpen"
          :worktree="worktree"
          :umo="umo"
          :path-filter="searchPathFilter"
          @open-file="onSearchOpenFile"
        />
        <div
          v-else
          ref="containerRef"
          class="document-manager__body"
          :class="{
            // The .resizing class flips the pane transition off
            // (see .document-manager__body.resizing … in the styles).
            // Both instances must be considered: the original code
            // only watched treeSplit, which made the tree drag feel
            // smooth (transition was off) but the history drag feel
            // laggy (the 0.2s transition was still firing on every
            // mousemove). OR-ing both keeps either drag equally
            // responsive.
            resizing:
              treeSplit.isResizing.value || historySplit.isResizing.value,
            'left-collapsed': isLeftPaneCollapsed,
            'history-collapsed': isHistoryCollapsed,
          }"
        >
          <!-- Tree expand handle: shown only when the left pane is
             collapsed, sitting at the leftmost flex position so the
             user can restore the tree at its previous width. -->
          <button
            v-if="isLeftPaneCollapsed"
            type="button"
            class="document-manager__expand-handle"
            :title="tm('spcodeProjectLoad.documentManager.pane.expandTree')"
            :aria-label="
              tm('spcodeProjectLoad.documentManager.pane.expandTree')
            "
            @click="isLeftPaneCollapsed = false"
          >
            <v-icon size="14" class="document-manager__expand-handle-icon"
              >mdi-chevron-double-right</v-icon
            >
            <span class="document-manager__expand-handle-label">{{
              tm("spcodeProjectLoad.documentManager.pane.expandTree")
            }}</span>
          </button>

          <!-- Left pane wrapper (tree + collapse button). The wrapper
             carries the inline width set by the resize handler so
             collapse ↔ expand preserves the user's chosen share. -->
          <!-- 2026-07-15 fullscreen-layout-parity: pane-left is
               visible in BOTH normal AND fullscreen modes — fullscreen
               shares the same layout tree. The only gate is the user's
               collapse choice. -->
          <div
            v-show="!isLeftPaneCollapsed"
            class="document-manager__pane-left"
            :style="{ width: treeSplit.percent.value + '%' }"
          >
            <DocumentTreePanel
              ref="treeRef"
              class="document-manager__left"
              :current-dir="docsRoot"
              :root-path="projectRoot"
              :is-dark="isDark"
              :selected-file="selectedDoc"
              :breadcrumb="false"
              @navigate="onTreeNavigate"
              @breadcrumb-navigate="onTreeNavigate"
              @select="onTreeSelect"
              @create-new="onCreateNew"
            />
            <button
              type="button"
              class="document-manager__collapse-btn document-manager__collapse-btn--tree"
              :title="tm('spcodeProjectLoad.documentManager.pane.collapseTree')"
              :aria-label="
                tm('spcodeProjectLoad.documentManager.pane.collapseTree')
              "
              @click="isLeftPaneCollapsed = true"
            >
              <v-icon size="14">mdi-chevron-double-left</v-icon>
            </button>
          </div>

          <div
            v-show="!isLeftPaneCollapsed"
            class="document-manager__divider"
            role="separator"
            aria-orientation="vertical"
            :aria-valuenow="Math.round(treeSplit.percent.value)"
            :aria-valuemin="15"
            :aria-valuemax="70"
            @mousedown="treeSplit.startResize"
          />


          <section
            class="document-manager__right"
            :class="{
              'is-expanded': isLeftPaneCollapsed && isHistoryCollapsed,
            }"
          >
            <!-- Error banners are surfaced at the top of the right pane so
               they stay visible while the user is still in the editor
               (previously they only rendered in the read view, which
               meant a failed save / delete appeared to "succeed" since
               the editor kept showing the pre-failure draft). -->
            <div v-if="saveError" class="document-manager__error">
              {{ saveError }}
            </div>
            <div v-if="deleteError" class="document-manager__error">
              {{ deleteError }}
            </div>
            <div v-if="renameError" class="document-manager__error">
              {{ renameError }}
            </div>
            <div v-if="!selectedDoc" class="document-manager__empty">
              <v-icon size="32" color="grey">mdi-file-document-outline</v-icon>
              <span>{{ tm("spcodeProjectLoad.documentManager.newFile") }}</span>
            </div>
            <template v-else-if="editMode">
              <DocumentEditor
                :initial-content="editBuffer"
                :file-relative="selectedDoc"
                :is-saving="docsApi.isSaving.value"
                :is-deleting="docsApi.isDeleting.value"
                :is-renaming="docsApi.isRenaming.value"
                :rename-error-message="renameError"
                @save="onSave"
                @cancel="onCancelEdit"
                @delete="onDelete"
                @rename="onRename"
                @rename-cancel="renameError = null"
              />
            </template>
            <template v-else>
              <div v-if="selectedRevision" class="document-manager__banner">
                <span>
                  {{
                    tm(
                      "spcodeProjectLoad.documentManager.viewMode.viewingRevision",
                      {
                        sha: selectedRevision.slice(0, 7),
                      },
                    )
                  }}
                </span>
                <button
                  type="button"
                  class="document-manager__banner-btn"
                  @click="onBackToCurrent"
                >
                  {{
                    tm(
                      "spcodeProjectLoad.documentManager.viewMode.backToCurrent",
                    )
                  }}
                </button>
              </div>

              <div class="document-manager__view-toolbar">
                <!-- 2026-07-17 meta-row-parity: file name / encoding /
                     size / mtime ahead of the action buttons — same
                     meta header as the workspace preview
                     (.preview-file-meta). The meta describes the
                     current working copy even when a historical
                     revision is viewed (workspace behaves the same;
                     the banner above flags the revision). -->
                <template v-if="docMeta">
                  <span
                    class="document-manager__doc-name"
                    :title="docMeta.path"
                    >{{ docMeta.name }}</span
                  >
                  <span
                    v-if="docMeta.encoding && docMeta.encoding !== 'utf-8'"
                    class="document-manager__doc-encoding"
                    :title="
                      tm(
                        'spcodeProjectLoad.fileBrowser.preview.encodingLabel',
                        { encoding: docMeta.encoding },
                      )
                    "
                  >
                    {{ docMeta.encoding }}
                  </span>
                  <span class="document-manager__doc-size">{{
                    formatBytes(docMeta.size)
                  }}</span>
                  <span class="document-manager__doc-mtime">{{
                    formatMtime(docMeta.mtime)
                  }}</span>
                </template>
                <div class="document-manager__view-toolbar-actions">
                  <!-- 2026-07-17 toolbar-style-unify: the three-segment
                       DocumentViewModeTab (原文|渲染|本次改动) was
                       replaced by the workspace-style single icon
                       toggle so both md toolbars read identically.
                       The "本次改动" (diff) mode is now entered only
                       from the history sidebar; the toggle hides
                       while in diff mode (exit via the banner /
                       sidebar). -->
                  <v-btn
                    v-if="viewMode !== 'diff'"
                    size="x-small"
                    variant="text"
                    color="primary"
                    :prepend-icon="
                      viewMode === 'rendered'
                        ? 'mdi-language-markdown-outline'
                        : 'mdi-code-tags'
                    "
                    :aria-pressed="viewMode === 'rendered'"
                    @click="
                      viewMode = viewMode === 'rendered' ? 'raw' : 'rendered'
                    "
                  >
                    {{
                      tm(
                        viewMode === 'rendered'
                          ? "spcodeProjectLoad.documentManager.viewMode.rendered"
                          : "spcodeProjectLoad.documentManager.viewMode.raw",
                      )
                    }}
                  </v-btn>
                  <v-btn
                    size="x-small"
                    variant="text"
                    color="primary"
                    prepend-icon="mdi-pencil-outline"
                    @click="onStartEdit"
                  >
                    {{ tm("spcodeProjectLoad.fileBrowser.editor.edit") }}
                  </v-btn>
                  <v-btn
                    v-if="canCopyContent"
                    size="x-small"
                    variant="text"
                    :color="copyButtonColor"
                    prepend-icon="mdi-content-copy"
                    @click="onCopyContent"
                  >
                    {{ copyButtonText }}
                  </v-btn>
                </div>
              </div>
              <div
                v-if="viewMode === 'rendered'"
                class="document-manager__rendered"
                @mouseup="onRenderedMouseUp"
              >
                <MarkdownView
                  v-if="selectedRevision"
                  :source="historicalFileContent"
                  :is-dark="isDark"
                  :container-class="selectedRevision ? 'historical' : ''"
                />
                <MarkdownView v-else :source="fileContent" :is-dark="isDark" />
              </div>
              <!-- Raw view (no edit): line numbers + (later) inline
                 comments via FileBrowserCodeView. Binary / empty /
                 not-ready cases render a small placeholder rather than
                 an empty code view. -->
              <div v-else-if="viewMode === 'raw'" class="document-manager__raw">
                <FileBrowserCodeView
                  v-if="
                    !editMode &&
                    rawFilePath &&
                    !rawIsBinary &&
                    rawContent &&
                    rawHighlightReady
                  "
                  class="document-manager__raw-codeview"
                  :highlighted-html="rawHighlightedHtml"
                  :file-path="rawFilePath"
                  :comments="rawComments"
                  :active-edit-line="activeEditLine"
                  :active-edit-comment-id="activeEditCommentId"
                  :is-dark="isDark"
                  :scroll-to-line="searchScrollToLine"
                  :selection-commentable="!selectedRevision"
                  @request-add="onRequestAddComment"
                  @request-edit="onRequestEditComment"
                  @request-add-range="onRequestAddRange"
                  @copy-selection="onRequestCopySelection"
                />
                <div
                  v-else-if="rawIsBinary"
                  class="document-manager__raw-placeholder"
                >
                  {{
                    tm(
                      "spcodeProjectLoad.documentManager.raw.binaryPlaceholder",
                    )
                  }}
                </div>
                <div
                  v-else-if="rawFilePath && !rawContent"
                  class="document-manager__raw-placeholder"
                >
                  {{
                    tm("spcodeProjectLoad.documentManager.raw.emptyPlaceholder")
                  }}
                </div>
                <div v-else class="document-manager__raw-placeholder">
                  {{ tm("spcodeProjectLoad.documentManager.raw.loading") }}
                </div>
                <FileCommentEditor
                  v-if="activeEditLine !== null && activeEditContext"
                  :line="activeEditLine"
                  :comment-id="activeEditCommentId"
                  :initial-text="editorInitialText"
                  :line-content="activeEditContext.lineContent"
                  :context-before="activeEditContext.contextBefore"
                  :context-after="activeEditContext.contextAfter"
                  :file-path="rawFilePath"
                  :end-line="activeEditRange?.endLine ?? null"
                  :selection-content="activeEditRange?.selection ?? null"
                  @save="onSaveComment"
                  @cancel="closeCommentEditor"
                  @delete="onDeleteComment"
                />
              </div>
              <DiffPreview
                v-else
                :content="diffPatch ?? ''"
                :is-dark="isDark"
              />
              <!-- 2026-07-17 selection-comment: copy-only menu for the
                   rendered container. MUST be a sibling of the
                   rendered/raw/diff branches, NOT inside the raw
                   branch — mounting it inside `viewMode === 'raw'`
                   made the menu invisible in rendered mode and pop
                   up stale on switching back (bug report 2026-07-17). -->
              <SelectionActionMenu
                v-if="renderedMenu"
                :x="renderedMenu.x"
                :y="renderedMenu.y"
                :show-comment="false"
                @copy="onRenderedCopy"
                @close="renderedMenu = null"
              />
              <!--
                2026-07-14: the "查看评论列表" button (and its
                CommentsPreviewDialog instance) is removed. Users
                still browse / delete / clear comments via the
                chip + preview dialog surfaced from ChatInput's
                comment indicator, which is the canonical entry
                point. The line-level comment editor on the right
                pane is unchanged.

                2026-07-17 btn-overlap fix: the edit button moved
                into the view-toolbar row above (it previously
                floated absolute top-right and collided with the
                copy button added the same day).
              -->
            </template>
          </section>

          <div
            v-show="!isHistoryCollapsed"
            class="document-manager__divider document-manager__divider--history"
            role="separator"
            aria-orientation="vertical"
            :aria-valuenow="Math.round(historySplit.percent.value)"
            :aria-valuemin="15"
            :aria-valuemax="40"
            @mousedown="historySplit.startResize"
          />

          <DocumentHistoryPanel
            v-show="!isHistoryCollapsed"
            class="document-manager__history"
            :style="{ width: historySplit.percent.value + '%' }"
            :git-log="gitLog"
            :file-relative="selectedDoc"
            :current-revision="selectedRevision"
            :is-loading="gitLog.state.value.kind === 'loading'"
            @select-revision="onSelectRevision"
            @compare-current="onCompareCurrent"
            @collapse="isHistoryCollapsed = true"
          />

          <!-- History expand handle: mirrors the left expand handle
             but anchored to the right edge of the body. -->
          <button
            v-if="isHistoryCollapsed"
            type="button"
            class="document-manager__expand-handle document-manager__expand-handle--history"
            :title="tm('spcodeProjectLoad.documentManager.pane.expandHistory')"
            :aria-label="
              tm('spcodeProjectLoad.documentManager.pane.expandHistory')
            "
            @click="isHistoryCollapsed = false"
          >
            <v-icon size="14" class="document-manager__expand-handle-icon"
              >mdi-chevron-double-left</v-icon
            >
            <span class="document-manager__expand-handle-label">{{
              tm("spcodeProjectLoad.documentManager.pane.expandHistory")
            }}</span>
          </button>
        </div>
      </template>
    </div>
  </Teleport>
</template>

<style scoped>
.document-manager {
  /* Mirror the .file-browser-view sizing in
     dashboard/src/components/chat/message_list_comps/FileBrowserView.vue:
     height: 100% so the root is constrained to the parent
     .git-diff-sidebar-body (which is itself sized by its own
     column-flex `flex: 1` slot). Without an explicit height here,
     the root falls back to its content height — and the content is
     the long markdown file, which blows past the sidebar body and
     triggers the sidebar body's own `overflow-y: auto`. The
     historical `flex: 1 1 auto` line was a no-op: the parent
     .git-diff-sidebar-body is not a flex container, so no flex
     sizing rule applied and the root height became content-sized.
     Keeping `display: flex; flex-direction: column; min-height: 0;
     overflow: hidden` so the rest of the existing flex-column
     pattern (__body, __right, __rendered scroll) still works. */
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}
.document-manager__notice {
  padding: 4px 8px;
  font-size: 11px;
}
.document-manager__notice--warn {
  background: rgba(var(--v-theme-warning), 0.1);
  color: rgb(var(--v-theme-warning));
}
.document-manager__breadcrumb {
  /* No extra padding: the breadcrumb component already carries
     its own 9px 12px padding. */
  flex: 0 0 auto;
}
/* 2026-07-13: flex-based body so we can drive pane widths from
   useResizableSplit. Mirrors the FileBrowserView layout. */
.document-manager__body {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}
.document-manager__body.resizing {
  cursor: col-resize;
  user-select: none;
}
.document-manager__pane-left {
  position: relative;
  flex: 0 0 auto;
  min-width: 120px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.document-manager__left {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
.document-manager__right {
  flex: 1 1 auto;
  min-width: 0;
  /* Flex-column + overflow: hidden so that the inner
     __rendered / __raw / __diff (and DocumentEditor's textarea in
     edit mode) — each declared as `flex: 1 1 auto; overflow: auto` —
     actually act as the *scrolling* sub-pane, matching the
     .file-browser-preview pattern used by the workspace tab. Without
     `display: flex; flex-direction: column; min-height: 0` here, the
     inner `flex: 1` rules are no-ops (the children stack as ordinary
     block elements), the right pane's content height blows past the
     body's available height, and the user-visible scroll ends up
     happening on a much higher ancestor (the whole project-changes
     panel), which is what made the bottom action button get pushed
     off-screen on long files. */
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  position: relative;
}
.document-manager__history {
  /* Width is now driven by useResizableSplit (history pane lives on
     the right edge, direction: 'right'). flex: 0 0 auto lets the
     inline style from `historySplit.percent.value` take over while
     still preventing the pane from flex-growing. min-width: 0 lets
     the panel's internal scroll/list handle overflow without
     blowing out the layout. */
  flex: 0 0 auto;
  min-width: 0;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}
/* 6px drag target. Negative horizontal margin widens the hit
   area without changing the visible 1px line. */
.document-manager__divider {
  flex: 0 0 6px;
  margin: 0 -2px;
  background: transparent;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  cursor: col-resize;
  position: relative;
  transition:
    background 0.15s ease,
    border-color 0.15s ease;
}
.document-manager__divider:hover,
.document-manager__divider:active {
  background: rgba(var(--v-theme-primary), 0.18);
  border-left-color: rgba(var(--v-theme-primary), 0.5);
}
.document-manager__empty {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 12.5px;
  text-align: center;
}
.document-manager__banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  background: rgba(var(--v-theme-info), 0.08);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  font-size: 11.5px;
  color: rgb(var(--v-theme-info));
}
.document-manager__banner-btn {
  background: transparent;
  border: 1px solid currentColor;
  color: inherit;
  border-radius: 3px;
  padding: 1px 6px;
  font-size: 11px;
  cursor: pointer;
}
.document-manager__raw {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: transparent;
}
.document-manager__raw-codeview {
  /* FileBrowserCodeView sets flex: 1 on its .code-view root. Filling
     the container here so the gutter stays sticky. */
  flex: 1;
  min-height: 0;
}
.document-manager__raw-placeholder {
  padding: 24px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 13px;
  text-align: center;
}
.document-manager__rendered {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}
.document-manager__error {
  padding: 6px 10px;
  font-size: 11px;
  color: rgb(var(--v-theme-error));
  background: rgba(var(--v-theme-error), 0.08);
}
.document-manager__view-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  /* 2026-07-17 meta-row-parity: the toolbar row doubles as the
     meta header (name/size/mtime + actions), so it takes the
     workspace .preview-file-meta visual spec. */
  padding: 6px 14px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.4);
}
.document-manager__doc-name {
  font-family: ui-monospace, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.document-manager__doc-size,
.document-manager__doc-mtime {
  font-variant-numeric: tabular-nums;
  color: rgba(var(--v-theme-on-surface), 0.4);
  flex-shrink: 0;
}
.document-manager__doc-encoding {
  font-family: ui-monospace, monospace;
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.7);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  cursor: help;
  user-select: none;
  flex-shrink: 0;
}
/* 2026-07-17 toolbar-style-unify: the toggle/edit/copy trio lives
   in this wrapper; margin-left:auto pushes it to the right edge
   (same layout as the workspace meta header). The buttons
   themselves are stock v-btns now — the old custom
   .document-manager__edit-btn / __copy-btn styles were removed
   with the segmented tab. */
.document-manager__view-toolbar-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
/* 2026-07-17 docs-search: search toolbar. Visual spec mirrors
   .file-browser-search-toolbar (and git-diff-sidebar-files-toolbar
   before that) so all three search UIs look identical.

   2026-07-20 search-trigger: the toolbar now hosts a single
   full-width element — either the "fake" search bar (idle, looks
   like an input) or the real <input> (active). They share every
   visual property that matters (border, radius, padding,
   background, font) so the swap is a no-op for layout. The
   shared selector at the top is the load-bearing block. */
.document-manager__search-toolbar {
  display: flex;
  align-items: center;
  /* 2026-07-20 search-toggle-button: gap between the input and
     the toggle button. Mirrors the FileBrowserView toolbar. */
  gap: 6px;
  padding: 4px 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  flex-shrink: 0;
}
/* 2026-07-20 search-toggle-button: active state for the
   right-side magnifier. Mirrors FileBrowserView. */
.document-manager__search-toggle.is-active {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}
.document-manager__search-trigger,
.document-manager__search-input {
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
  transition:
    border-color 0.14s ease,
    box-shadow 0.14s ease,
    background 0.14s ease;
}
.document-manager__search-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  text-align: left;
  -webkit-appearance: none;
  appearance: none;
}
.document-manager__search-trigger:hover {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.04);
}
.document-manager__search-trigger:focus-visible {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), 0.16);
}
.document-manager__search-trigger__icon {
  color: var(--chat-section-label, rgba(var(--v-theme-on-surface), 0.48));
  flex-shrink: 0;
}
.document-manager__search-trigger__placeholder {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--chat-section-label, rgba(var(--v-theme-on-surface), 0.48));
}
.document-manager__search-trigger__hint {
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
.document-manager__search-input::placeholder {
  color: var(--chat-section-label, rgba(var(--v-theme-on-surface), 0.48));
}
.document-manager__search-input:focus {
  border-color: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), 0.16);
}
/* 2026-07-17 docs-presets: quick-path chips on the path-bar row.
   Pill-shaped (radius 10px) to read as shortcuts, not actions;
   the active chip mirrors the "current location" so the row also
   doubles as a where-am-I indicator. */
.document-manager__path-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.document-manager__presets {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 4px 8px 4px 0;
  min-width: 0;
}
.document-manager__preset-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  padding: 2px 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 10px;
  background: var(--v-theme-surface, transparent);
  color: rgba(var(--v-theme-on-surface), 0.75);
  cursor: pointer;
  white-space: nowrap;
}
.document-manager__preset-btn:hover {
  border-color: rgba(var(--v-theme-primary), 0.4);
  color: rgb(var(--v-theme-primary));
}
.document-manager__preset-btn.is-active {
  background: rgba(var(--v-theme-primary), 0.12);
  border-color: rgba(var(--v-theme-primary), 0.4);
  color: rgb(var(--v-theme-primary));
}
.document-manager__preset-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
/* 2026-07-18: pin the re-added fullscreen toggle to the right edge
   of the path row. Replaces the old labeled __fullscreen-btn styles,
   which went dead when that button was dropped from the template. */
.document-manager__fullscreen-toggle {
  margin-left: auto;
  flex-shrink: 0;
}
.document-manager.is-fullscreen {
  /* True viewport fullscreen (spec 2026-07-14 §3.2 + DiffPreview
     pattern, spec 2026-06-30). The Teleport wrapper in <template>
     moves this element to <body> when fullscreen is on; CSS then
     positions it `fixed; inset: 0` so it covers the entire
     viewport — not just the .git-diff-sidebar-body that normally
     hosts DocumentManager.

     The existing inner layout rules (flex-column for the root,
     flex-row for .document-manager__body) keep working unchanged:
     `position: fixed` resets the containing-block for absolutely
     positioned descendants, but the document-manager itself is
     still the flex parent for its children. */
  position: fixed;
  inset: 0;
  z-index: 9999;
  width: 100%;
  height: 100%;
  background: rgb(var(--v-theme-background));
  /* The chat page keeps other fullscreen surfaces in this slot
     (e.g. image viewers, dialog overlays). z-index: 9999 matches
     the DiffPreview overlay so they layer consistently. */
}

/* Collapse button: small chevron anchored to the top-right of
   the tree pane. The history pane owns its own collapse button
   inside DocumentHistoryPanel — that keeps the button inside a
   `position: relative` ancestor and avoids the "absolute
   positioning escapes to a far-away ancestor" pitfall we hit
   when the button lived here with a hard-coded right offset. */
.document-manager__collapse-btn {
  position: absolute;
  top: 4px;
  z-index: 5;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-surface), 0.85);
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
.document-manager__collapse-btn:hover,
.document-manager__collapse-btn:focus-visible {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  border-color: rgba(var(--v-theme-primary), 0.4);
  outline: none;
}
.document-manager__collapse-btn--tree {
  right: 4px;
}

/* Expand handle: thin vertical strip on the outermost edge of
   the body when its pane is collapsed. Mirrors the divider's
   hover treatment and the FileBrowserView handle: flex column
   with a chevron (top) and a vertical text label (bottom). */
.document-manager__expand-handle {
  flex: 0 0 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: transparent;
  border: none;
  color: rgba(var(--v-theme-on-surface), 0.5);
  cursor: pointer;
  padding: 14px 0;
  transition:
    background 0.1s ease,
    color 0.1s ease,
    border-color 0.1s ease;
}
.document-manager__expand-handle:hover,
.document-manager__expand-handle:focus-visible {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  outline: none;
}
.document-manager__expand-handle:not(
    .document-manager__expand-handle--history
  ) {
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.document-manager__expand-handle--history {
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.document-manager__expand-handle--history:hover,
.document-manager__expand-handle--history:focus-visible {
  border-left-color: rgba(var(--v-theme-primary), 0.4);
}
.document-manager__expand-handle-icon {
  flex-shrink: 0;
  opacity: 0.85;
  writing-mode: horizontal-tb;
}
.document-manager__expand-handle-label {
  writing-mode: vertical-rl;
  text-orientation: upright;
  letter-spacing: 4px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  user-select: none;
}

/* Smooth width transition for collapse / expand. Suppressed while
   dragging so mousemove updates don't lag behind the cursor. */
.document-manager__pane-left,
.document-manager__right,
.document-manager__divider,
.document-manager__history,
.document-manager__expand-handle {
  transition:
    width 0.2s ease,
    flex-basis 0.2s ease,
    padding 0.2s ease;
}
.document-manager__body.resizing .document-manager__pane-left,
.document-manager__body.resizing .document-manager__right,
.document-manager__body.resizing .document-manager__divider,
.document-manager__body.resizing .document-manager__history,
.document-manager__body.resizing .document-manager__expand-handle {
  transition: none;
}

/* Mobile: stack vertically and hide the desktop-only collapse /
   expand affordances (the user can scroll the list out of view
   instead). */
@media (max-width: 760px) {
  .document-manager__body {
    flex-direction: column;
  }
  .document-manager__pane-left,
  .document-manager__right,
  .document-manager__history {
    width: 100% !important;
    flex: 1 1 auto;
  }
  .document-manager__history {
    flex: 0 0 auto;
    max-height: 40vh;
  }
  .document-manager__divider {
    width: auto;
    height: 6px;
    margin: 0;
    border-left: none;
    border-top: 1px solid rgba(var(--v-theme-on-surface), 0.1);
    cursor: default;
  }
  .document-manager__collapse-btn,
  .document-manager__expand-handle {
    display: none;
  }
}
</style>
