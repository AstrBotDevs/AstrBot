<!-- Author: elecvoid243, 2026-06-18
     Updated 2026-06-18 — worktree switcher (docs/superpowers/specs/2026-06-18-git-worktree-switcher-design.md)
     Updated 2026-06-20 — scope switcher (docs/superpowers/specs/2026-06-20-git-diff-scope-switcher-design.md)
     Layout mirrors ReasoningSidebar.vue so resizing the sidebar takes
     space from .chat-main (flex sibling) instead of overlaying it. -->
<script setup lang="ts">
import {
  ref,
  watch,
  provide,
  onBeforeUnmount,
  computed,
  onMounted,
  nextTick,
} from "vue";
import {
  useSpcodeGitDiff,
  DEFAULT_SCOPE,
  type GitDiffScope,
  type GitDiffFetchState,
} from "@/composables/useSpcodeGitDiff";
import { useSpcodeGitStatus } from "@/composables/useSpcodeGitStatus";
import {
  isNewFileScope,
  type SpcodeGitStatusFile,
} from "@/composables/parseSpcodeGitStatus";
import type {
  SpcodeGitDiffFile,
  SpcodeGitDiffSnapshot,
  FileStatus,
} from "@/composables/parseSpcodeGitDiff";
import type { SpcodeGitWorktree } from "@/composables/parseSpcodeWorktrees";
import {
  useSpcodeWorktrees,
  type WorktreeAddParams,
  type WorktreeLockParams,
} from "@/composables/useSpcodeWorktrees";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeGitRepoProbe } from "@/composables/useSpcodeGitRepoProbe";
import GitRepoInitPrompt from "@/components/chat/message_list_comps/GitRepoInitPrompt.vue";
import {
  useSpcodeFileRestore,
  type RestoreResult,
} from "@/composables/useSpcodeFileRestore";
import {
  useSpcodeFileDiscardHunk,
  type DiscardHunkResult,
} from "@/composables/useSpcodeFileDiscardHunk";
import { useSpcodeGitStage } from "@/composables/useSpcodeGitStage";
import { useSpcodeGitUnstage } from "@/composables/useSpcodeGitUnstage";
import { useSpcodeGitCommit } from "@/composables/useSpcodeGitCommit";
import { useSpcodeGitRevert } from "@/composables/useSpcodeGitRevert";
import { useSpcodeFileWrite } from "@/composables/useSpcodeFileWrite";
import GitIgnoreEditor from "@/components/chat/message_list_comps/GitIgnoreEditor.vue";
import { useSpcodeGitLog, type LogFilter } from "@/composables/useSpcodeGitLog";
import { useSpcodeGitShow } from "@/composables/useSpcodeGitShow";
import { useSpcodeGitStats } from "@/composables/useSpcodeGitStats";
import { useSpcodeNewFileLineCounts } from "@/composables/useSpcodeNewFileLineCounts";
import { classifyReason } from "@/composables/parseSpcodeGitWorkflow";
import { classifyWorktreeReason } from "@/composables/parseSpcodeWorktreeManagement";
import { pluginExtensionApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import GitDiffBodyContent from "@/components/chat/message_list_comps/GitDiffBodyContent.vue";
import FileBrowserView from "@/components/chat/message_list_comps/FileBrowserView.vue";
import GitCommitBar from "@/components/chat/message_list_comps/GitCommitBar.vue";
import GitCommitDialog from "@/components/chat/message_list_comps/GitCommitDialog.vue";
import WorktreeCreateDialog from "@/components/chat/message_list_comps/WorktreeCreateDialog.vue";
import LockReasonDialogBody from "@/components/chat/message_list_comps/LockReasonDialogBody.vue";
import GitLogView from "@/components/chat/message_list_comps/GitLogView.vue";
import DocumentManager from "@/components/chat/message_list_comps/DocumentManager.vue";
const { tm } = useModuleI18n("features/chat");

// ── localStorage persistence (spec 2026-06-20 §5.1 + §6) ────────────
// Persists 4 view-state keys across page reloads. Values are loaded
// once at component creation and saved on every change (most are
// flush:"post" watchers; currentPath uses a 300ms debounce per spec
// §2 decision #9 to avoid thrashing during fast navigation).
//
// Validation rules: invalid persisted values are silently replaced
// with the spec-defined default. We never throw — localStorage may
// be disabled (private browsing) or the value may have been written
// by an older app version.
const STORAGE_KEYS = {
  viewMode: "astrbot.spcode.gitDiffSidebar.viewMode",
  fileBrowserCurrentPath:
    "astrbot.spcode.gitDiffSidebar.fileBrowserCurrentPath",
  selectedWorktree: "astrbot.spcode.gitDiffSidebar.selectedWorktree",
  selectedScope: "astrbot.spcode.gitDiffSidebar.selectedScope",
  // 2026-07-18 git-stats heatmap: stats-panel collapsed state.
  gitStatsOpen: "astrbot.spcode.gitDiffSidebar.gitStatsOpen",
} as const;

function safeGetItem(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* no-op */
  }
}

function loadViewMode(): "files" | "diff" | "history" | "docs" {
  const v = safeGetItem(STORAGE_KEYS.viewMode);
  // Spec §2 决策 #10:History 是第 3 个 viewMode,持久化时同样支持。
  // 2026-07-11 document-manager:docs 是第 4 个 viewMode。
  if (v === "files" || v === "diff" || v === "history" || v === "docs") {
    return v;
  }
  return "files";
}
function loadFileBrowserCurrentPath(): string {
  return safeGetItem(STORAGE_KEYS.fileBrowserCurrentPath) ?? "";
}
function loadSelectedScope(): GitDiffScope {
  const v = safeGetItem(STORAGE_KEYS.selectedScope);
  if (v === "unstaged" || v === "staged" || v === "all") return v;
  return DEFAULT_SCOPE;
}

// 2026-07-18 git-stats heatmap: unlike the (now FileBrowserView-owned)
// search panel, the stats panel defaults to EXPANDED (only the literal
// "false" collapses) — the heatmap is the primary entry point of the
// History view.
function loadGitStatsOpen(): boolean {
  return safeGetItem(STORAGE_KEYS.gitStatsOpen) !== "false";
}

// Debounced writer for currentPath (spec §5.1 lines 1273-1280).
// Avoids localStorage thrashing when the user clicks through
// directories rapidly.
let persistCurrentPathTimer: ReturnType<typeof setTimeout> | null = null;
function persistCurrentPath(path: string): void {
  if (persistCurrentPathTimer) clearTimeout(persistCurrentPathTimer);
  persistCurrentPathTimer = setTimeout(() => {
    safeSetItem(STORAGE_KEYS.fileBrowserCurrentPath, path);
  }, 300);
}

// Cross-root validator (spec §5.1 lines 1300-1310). Returns the input
// if it's inside the root, else the root. Used to reset stale paths
// after project / worktree switches.
function validateCurrentPath(
  persisted: string | null,
  root: string | null,
): string {
  if (!root) return "";
  if (!persisted) return root;
  const normPersisted = persisted.replace(/\\/g, "/");
  const normRoot = root.replace(/\\/g, "/").replace(/\/$/, "");
  if (normPersisted === normRoot || normPersisted.startsWith(normRoot + "/")) {
    return persisted;
  }
  return root;
}
const props = defineProps<{
  modelValue: boolean;
  isDark?: boolean;
}>();
const emit = defineEmits<{ (e: "update:modelValue", v: boolean): void }>();

// ── Scope switcher (spec 2026-06-20 §3) ────────────────────────────
// `selectedScope` is the user's currently-displayed scope; it is
// forwarded to useSpcodeGitDiff which auto-refreshes on changes.
// `pendingScope` tracks the scope the user just clicked but whose
// response has not yet arrived; it powers the inline spinner on the
// active pill and the disabled state on the other two.
const selectedScope = ref<GitDiffScope>(DEFAULT_SCOPE);
const pendingScope = ref<GitDiffScope | null>(null);

interface ScopeOption {
  value: GitDiffScope;
  icon: string;
  labelKey: string;
}

// Single source of truth for the three pills: the v-for in the
// template iterates this list, so adding/removing a scope is a
// one-line change here. ReadonlyArray makes the contract explicit.
const SCOPE_OPTIONS: ReadonlyArray<ScopeOption> = [
  {
    value: "unstaged",
    icon: "mdi-pencil-outline",
    labelKey: "spcodeProjectLoad.diffSidebar.scope.unstaged",
  },
  {
    value: "staged",
    icon: "mdi-check-circle-outline",
    labelKey: "spcodeProjectLoad.diffSidebar.scope.staged",
  },
  {
    value: "all",
    icon: "mdi-format-list-bulleted",
    labelKey: "spcodeProjectLoad.diffSidebar.scope.all",
  },
];

// ── Worktree switcher state (spec 2026-06-18 §3.4) ─────────────────
// selectedWorktree is the path of the currently-displayed worktree.
// null = use primary (main) worktree. This ref is passed to
// useSpcodeGitDiff which auto-refreshes on changes.
const selectedWorktree = ref<string | null>(null);

// ── View-mode tab (spec 2026-06-20 §5.1 + §5.2) ─────────────────────
// "files" shows <FileBrowserView>; "diff" shows <GitDiffBodyContent>;
// "history" shows <GitLogView> (spec 2026-06-24 §2 决策 #10)。
// "docs" shows <DocumentManager> (spec 2026-07-11 document-manager §2 #1)。
// Default: "files" per spec §2 decision #10 (the more general view;
// first-time users likely want to "see what's in the project").
const viewMode = ref<"files" | "diff" | "history" | "docs">(loadViewMode());
const fileBrowserCurrentPath = ref<string>(loadFileBrowserCurrentPath());
// ── Fullscreen state ──────────────────────────────────────────────
// Non-persisted. globalFullscreen expands the entire sidebar to the
// viewport and survives page switches (e.g. files → diff).
// 2026-07-17: the innerFullscreen mode (preview-only Teleport inside
// FileBrowserFilePreview) was removed — its role duplicated this
// sidebar-wide fullscreen button.
const globalFullscreen = ref(false);

function toggleGlobalFullscreen(): void {
  globalFullscreen.value = !globalFullscreen.value;
}

function onFullscreenKeyDown(e: KeyboardEvent): void {
  if (e.key !== "Escape" || !globalFullscreen.value) return;
  globalFullscreen.value = false;
}

watch(
  globalFullscreen,
  (v) => {
    document.body.style.overflow = v ? "hidden" : "";
  },
  { immediate: true },
);
// fileBrowserPreviewPath is the file (if any) currently shown in the
// right pane. It is intentionally NOT persisted: when the user reloads
// the page we want the directory listing (persisted via currentPath),
// not an auto-reopened file. Cleared on worktree / project switches,
// breadcrumb clicks, and any directory navigation.
const fileBrowserPreviewPath = ref<string | null>(null);

// 2026-07-02 sidebar-search: scroll target for the file preview, set
// by onFileOpen() when the user clicks a search result. 1-based line
// number, null = no scroll. The watch in FileBrowserCodeView
// re-fires the scroll when (scrollToLine, filePath, highlightedHtml)
// changes, so the scroll also runs correctly after the file content
// finishes loading. Cleared by onFileBrowserNavigate() so a manual
// tree click does not inherit a stale scroll target.
const fileSearchScrollToLine = ref<number | null>(null);

// 2026-07-18 git-stats heatmap: History-tab stats panel toggle,
// persisted (flush:"post" writer).
const statsOpen = ref<boolean>(loadGitStatsOpen());
watch(
  statsOpen,
  (v) => safeSetItem(STORAGE_KEYS.gitStatsOpen, String(v)),
  { flush: "post" },
);

// Hydrate selectedScope from localStorage (validated; fall back to default).
const _persistedScope = loadSelectedScope();
if (_persistedScope !== DEFAULT_SCOPE) selectedScope.value = _persistedScope;

// Hydrate selectedWorktree from localStorage. We store the literal
// string "null" for null (workaround: localStorage.getItem returns
// null for both "missing" and "stored null"). Validation against the
// worktree list happens in the worktree-list watcher below.
const _persistedWorktree = safeGetItem(STORAGE_KEYS.selectedWorktree);
if (_persistedWorktree !== null && _persistedWorktree !== "null") {
  selectedWorktree.value = _persistedWorktree;
}

const worktreesComposable = useSpcodeWorktrees();
// Spec 2026-07-16: "is this a Git repo?" probe + init mutation. Used by
// the GitRepoInitPrompt slot in the template to surface a one-click
// `git init` flow when the loaded directory has no .git/.
const gitRepoProbe = useSpcodeGitRepoProbe();
const worktreeList = computed(() => {
  const s = worktreesComposable.state.value;
  if (s.kind !== "ok") return [];
  return s.snapshot.worktrees;
});
const hasMultipleWorktrees = computed(() => worktreeList.value.length > 0);
// Path of the main worktree (used as the "active" comparison when
// selectedWorktree is null). Lets the main tab stay highlighted.
const mainWorktreePath = computed(
  () => worktreeList.value.find((w) => w.isMain)?.path ?? null,
);
// Path of the loaded project's root directory (from
// /spcode/project-status, independent of git). Used as a fallback
// root for the file browser when the project is NOT a git project
// (worktree list is empty → no main worktree path). Without this
// fallback, fileBrowserCurrentPath would collapse to "" and
// useSpcodeFileBrowser's watcher would skip the fetch
// (`if (!path) return`), leaving the Files view empty.
const projectRoot = computed(() => spcodeStatus.status.value.directory);

// Persist viewMode / selectedScope / selectedWorktree on every change.
// fileBrowserCurrentPath uses persistCurrentPath (300ms debounce).
watch(viewMode, (v) => safeSetItem(STORAGE_KEYS.viewMode, v), {
  flush: "post",
});
watch(selectedScope, (v) => safeSetItem(STORAGE_KEYS.selectedScope, v), {
  flush: "post",
});
watch(
  selectedWorktree,
  (v) => safeSetItem(STORAGE_KEYS.selectedWorktree, v === null ? "null" : v),
  { flush: "post" },
);

// Closed-over by the worktree-list watcher below. Tracks the previous
// worktree path set so we can detect *topology* changes (paths
// added/removed) and skip the validation sweep on no-op polling
// ticks. Declared before the watcher so the closure binding is
// unambiguous; Vue's `<script setup>` does not hoist `let`.
let prevWorktreePaths: ReadonlySet<string> | null = null;

// When the worktree list first loads, validate the persisted worktree
// AND cross-validate the persisted currentPath against the new root.
// This is the only place where fileBrowserCurrentPath is overwritten
// during initial hydration; thereafter the user is in control.
// Also clear any preview path: a preview from a different worktree
// would be invalid in the new context.
watch(
  () => worktreesComposable.state.value,
  (s) => {
    if (s.kind !== "ok") return;
    const wtList = s.snapshot.worktrees;
    const newPaths = new Set(wtList.map((w) => w.path));

    // Topology-only change detection.
    //
    // Pre-polling, this watcher was event-driven: a worktree-list
    // mutation triggered a one-shot sanity sweep (reset stale
    // selectedWorktree, re-validate currentPath, clear stale
    // preview). The 30s polling added in 2026-06-25 turned it into
    // a periodic callback — `state.value` is replaced on every
    // tick, even when the response is byte-for-byte identical.
    // Running the full sweep on every tick had a concrete user-
    // visible cost: `fileBrowserPreviewPath.value = null` (below)
    // unmounted <FileBrowserFilePreview> and reset the right pane
    // to the "select from left" hint, so the user lost their
    // scroll position mid-read.
    //
    // We only care about the WORKTREE SET (paths added/removed) —
    // a worktree's branch / head_sha / locked / prunable flipping
    // does not invalidate which files are accessible in the
    // current preview, so they must not trigger a reset. We track
    // the previous path set in a closure and skip the sweep when
    // the set is unchanged. The initial run (prevWorktreePaths ===
    // null) always runs, preserving the original hydration behavior
    // (validate persisted selectedWorktree / currentPath against
    // the freshly-loaded list).
    // Local alias so the type-narrowed `prev` is used in the every()
    // callback without a non-null assertion. After the `=== null`
    // check, `prev` is guaranteed non-null for the size/every
    // comparisons (TypeScript can't see this through the
    // short-circuit on its own).
    const prev = prevWorktreePaths;
    const topologyChanged =
      prev === null ||
      prev.size !== newPaths.size ||
      ![...newPaths].every((p) => prev.has(p));
    prevWorktreePaths = newPaths;
    if (!topologyChanged) return;

    // Validate selectedWorktree
    if (
      selectedWorktree.value &&
      !wtList.some((w) => w.path === selectedWorktree.value)
    ) {
      selectedWorktree.value = null;
    }
    // Validate currentPath against the (possibly new) root.
    // Fall back to projectRoot for non-git projects (no worktrees →
    // no main worktree path); otherwise fileBrowserCurrentPath would
    // collapse to "" and the file-browser fetch would be skipped.
    const root =
      selectedWorktree.value ??
      wtList.find((w) => w.isMain)?.path ??
      projectRoot.value;
    const validated = validateCurrentPath(fileBrowserCurrentPath.value, root);
    if (fileBrowserCurrentPath.value !== validated) {
      fileBrowserCurrentPath.value = validated;
    }
    // Preview path is transient and almost certainly invalid in a
    // worktree-set change context (the file it points to is in a
    // worktree that no longer exists in the new list). Clear it so
    // the right pane shows the "select from left" hint instead of a
    // stale file. Skipped on no-op polls by the topology guard above.
    if (fileBrowserPreviewPath.value !== null) {
      fileBrowserPreviewPath.value = null;
    }
  },
  { immediate: true },
);

// When selectedWorktree changes, reset currentPath to the new root.
// This fires for BOTH manual worktree switches and project switches
// (which reset selectedWorktree to null via the directory watcher
// further below). Per spec §5.1: "reset currentPath regardless of
// current viewMode" — we don't want stale paths leaking into a
// different worktree. The preview path is also cleared: a preview
// pointing into the old worktree is meaningless in the new one.
watch(selectedWorktree, (newVal) => {
  const root = newVal ?? mainWorktreePath.value;
  if (root && fileBrowserCurrentPath.value !== root) {
    fileBrowserCurrentPath.value = root;
    persistCurrentPath(root);
  }
  fileBrowserPreviewPath.value = null;
});

// Persist currentPath (debounced 300ms, spec §5.1 line 1357-1361).
// Empty path is skipped — we don't want to overwrite a valid persisted
// value with an empty string during the brief interval before the
// worktree-list watcher fires.
watch(fileBrowserCurrentPath, (newPath) => {
  if (newPath) persistCurrentPath(newPath);
});

const composable = useSpcodeGitDiff(selectedWorktree, selectedScope);
// git-status is fetched alongside git-diff ONLY for the unstaged view.
// The endpoint is complementary (branch / untracked / intent-to-add)
// and is not relevant to staged or all-scope views. Lifecycle
// (refresh + 10s polling + dispose) is wired in the modelValue / viewMode
// watcher and onBeforeUnmount below.
const gitStatus = useSpcodeGitStatus(selectedWorktree);
const spcodeStatus = useSpcodeProjectStatus();
const expandedSet = ref<Set<string>>(new Set());

// ── Git workflow composables (spec 2026-06-24 §3.2) ──────────────
// All 4 live at the sidebar level so they can share stagedFiles state
// and call composable.refresh() after a write.
const gitStage = useSpcodeGitStage();
const gitUnstage = useSpcodeGitUnstage();
const gitCommit = useSpcodeGitCommit();
const gitLog = useSpcodeGitLog(selectedWorktree);
// 2026-07-17 git-revert: History-view per-commit revert. The sidebar
// owns the confirm dialog + the write call (mirroring stage/commit).
const gitRevert = useSpcodeGitRevert();

// ── .gitignore editor overlay (2026-07-17, latency rework 2026-07-18) ─
// Spec: docs/superpowers/specs/2026-07-17-gitignore-editor-design.md
// The sidebar owns load/save orchestration; GitIgnoreEditor is a
// purely presentational overlay (initial-content in, save(out) out).
// 2026-07-18: the editing buffer lives INSIDE the editor — per
// keystroke state no longer reaches the sidebar, so this 4600-line
// component is no longer in the typing render path.
const gitIgnoreEditorOpen = ref(false);
// On-disk content loaded by loadGitIgnore (the dirty baseline passed
// to the editor as `initial-content`). Persists across the editing
// session; updated only on a fresh load (open / retry).
const gitIgnoreLoadedContent = ref("");
const gitIgnoreIsNewFile = ref(false);
const gitIgnoreLoadError = ref<string | null>(null);
const gitIgnoreSaveError = ref<string | null>(null);
const gitIgnoreFileWrite = useSpcodeFileWrite(selectedWorktree);
// Repo-root .gitignore as an absolute path for the read endpoint
// (file-browser takes absolute paths; trailing slashes stripped).
const gitIgnoreAbsPath = computed(
  () => `${(currentRoot.value ?? "").replace(/\/+$/, "")}/.gitignore`,
);
const GITIGNORE_I18N_PREFIX =
  "spcodeProjectLoad.diffSidebar.gitWorkflow.gitignore";

async function loadGitIgnore(): Promise<void> {
  gitIgnoreLoadError.value = null;
  try {
    const resp = await pluginExtensionApi.get<unknown>(
      "spcode/file-browser",
      { params: { path: gitIgnoreAbsPath.value } },
    );
    const data = (
      resp.data as {
        data?: {
          type?: string | null;
          content?: unknown;
          reason?: string | null;
        };
      }
    )?.data;
    if (data?.type === "file" && typeof data.content === "string") {
      gitIgnoreLoadedContent.value = data.content;
      gitIgnoreIsNewFile.value = false;
      return;
    }
    // type === null + reason path_not_found → the repo simply has no
    // .gitignore yet: empty baseline + "will be created" hint.
    if (data?.reason === "path_not_found") {
      gitIgnoreLoadedContent.value = "";
      gitIgnoreIsNewFile.value = true;
      return;
    }
    gitIgnoreLoadError.value = tm(`${GITIGNORE_I18N_PREFIX}.loadError`, {
      reason: data?.reason ?? "unknown",
    });
  } catch (err) {
    const anyErr = err as { code?: string; message?: string };
    gitIgnoreLoadError.value = tm(`${GITIGNORE_I18N_PREFIX}.loadError`, {
      reason:
        anyErr.code === "ERR_NETWORK" || /network/i.test(anyErr.message ?? "")
          ? "network"
          : "unknown",
    });
  }
}

function onOpenGitIgnoreEditor(): void {
  gitIgnoreSaveError.value = null;
  gitIgnoreEditorOpen.value = true;
  void loadGitIgnore();
}

function onGitIgnoreCancel(): void {
  gitIgnoreEditorOpen.value = false;
}

async function onGitIgnoreSave(content: string): Promise<void> {
  if (gitIgnoreFileWrite.isSaving.value) return;
  gitIgnoreSaveError.value = null;
  const r = await gitIgnoreFileWrite.save({
    // Repo-relative path — the backend resolves it against the
    // worktree passed by the composable.
    path: ".gitignore",
    content,
  });
  if (r.ok) {
    gitIgnoreEditorOpen.value = false;
    showSnackbar(tm(`${GITIGNORE_I18N_PREFIX}.saveSuccess`), "success");
    // .gitignore changes which untracked files appear — refresh the
    // status + diff views in parallel.
    void Promise.all([gitStatus.refresh(), composable.refresh()]);
    return;
  }
  if (r.reason === "aborted") return;
  gitIgnoreSaveError.value = tm(`${GITIGNORE_I18N_PREFIX}.saveError`, {
    reason: r.reason,
  });
}

// The buffer belongs to the old worktree after a switch — close.
watch(selectedWorktree, () => {
  gitIgnoreEditorOpen.value = false;
});
// git-show: per-commit file list (spec 2026-06-25). One composable
// instance shared by every expanded commit in GitLogView; the
// composable maintains a per-SHA cache internally, so re-expanding
// a previously seen commit is an ETag-validated no-op.
const gitShow = useSpcodeGitShow(selectedWorktree);

// 2026-07-18 git-stats heatmap: whole-repo change stats for the
// History tab's GitStatsPanel. Single snapshot per umo|worktree
// (ETag-validated); refresh is lazy — see the dedicated watcher next
// to the polling watcher below.
const gitStats = useSpcodeGitStats(selectedWorktree);

// Spec §3.4 决策 #22/#23:切 worktree 保留,切 project / unload 清空。
const stagedFiles = ref<Set<string>>(new Set<string>());

// 2026-07-09: file-level git history bridge.
//
// The backend already supports `?path=<file>` on GET /spcode/git-log
// (see plugins/astrbot_plugin_spcode_toolkit/tools/webapi/git_log.py
// _qget("path") + `git log -- <path>`), and the frontend composable
// `useSpcodeGitLog` already threads `path` through the request and
// the ETag key. The only missing piece was a UI affordance: the
// file-preview pane has no way to say "show me the history of THIS
// file" without the user manually retyping the path in the History
// tab's filter form. We provide this setter so descendants (today:
// <FileBrowserFilePreview>'s "history" button; tomorrow: maybe a
// right-click menu) can switch the sidebar to the History tab and
// pre-fill the path filter in one call.
//
// We spread the current filter so the user's prior ref/author/since/
// until/n selections are preserved — only the path changes. View
// mode persistence (localStorage) happens automatically via the
// existing `watch(viewMode, ...)` flush:"post" below.
function setLogPathFilter(path: string): void {
  if (!path) return;
  viewMode.value = "history";
  // Preserve the user's current filter shape (ref / author / since
  // / until / n) and only override path. The composable's refresh()
  // replaces (not merges) the filter, so we have to spread here.
  void gitLog.refresh({ ...gitLog.filter.value, path });
}
// String inject key (the sidebar ↔ file-preview pair is the only
// consumer). Using a string (not Symbol) keeps the import surface in
// <FileBrowserFilePreview> trivial: `inject(SET_LOG_PATH_FILTER_KEY)`
// with the same string literal. A Symbol would force an extra shared
// module just to host the constant; not worth it for one consumer.
const SET_LOG_PATH_FILTER_KEY = "spcode:setLogPathFilter";
provide<(path: string) => void>(SET_LOG_PATH_FILTER_KEY, setLogPathFilter);

/**
 * 2026-07-15 history-sha-jump: jump from the per-file history
 * side panel (workspace + document manager) straight to a
 * specific commit in the global Git log. Mirrors `setLogPathFilter`
 * in shape but routes through a fresh inject key because the
 * semantic is different ("jump to THIS commit", not "filter the
 * log by THIS path"). The implementation:
 *
 *   1. Switches `viewMode` to `"history"` so the GitLogView
 *      mounts. Already-persisted via the existing
 *      `watch(viewMode, ...)` so the user lands back here next
 *      time.
 *   2. Pins the log's `ref` filter to the clicked SHA. `git log
 *      <sha>` returns that commit plus its ancestors, which is
 *      exactly what a deep-link to a single commit should show
 *      — the user gets the commit they clicked as the first
 *      row, with its history reachable via "load more". Drop the
 *      per-file panel's `path` filter too: the commit of interest
 *      is not guaranteed to touch the picked file in *this*
 *      revision (it might be a renaming or a non-related history).
 *   3. Stashes the SHA in `focusedCommitSha`, which is forwarded
 *      to <GitLogView> as `focused-commit-sha`. GitLogView owns
 *      the highlight + expansion + scrollIntoView; see its
 *      watcher.
 */
const focusedCommitSha = ref<string | null>(null);
function focusCommit(sha: string): void {
  if (!sha) return;
  viewMode.value = "history";
  focusedCommitSha.value = sha;
  // Preserve the user's optional filter knobs (author / since /
  // until / n) but pin ref+path so the request is scoped to the
  // clicked commit. The explicit assignments after the spread
  // win over anything carried over from `gitLog.filter.value`.
  const { path: _path, ref: _ref, ...rest } = gitLog.filter.value;
  void gitLog.refresh({ ...rest, ref: sha, path: undefined });
}
// Dedicated key: this is a sibling affordance to setLogPathFilter
// and the two are not interchangeable. Both <FileBrowserView> and
// <DocumentManager> consume it via the same string literal.
const FOCUS_COMMIT_KEY = "spcode:focusCommit";
provide<(sha: string) => void>(FOCUS_COMMIT_KEY, focusCommit);

// 2026-07-17: the fullscreen provide/inject bridge (spcode:globalFullscreen
// / innerFullscreen / isAnyFullscreen / toggleInnerFullscreen) was
// removed together with the inner-fullscreen feature — no descendants
// consume these keys anymore.

// Spec §3.3.3:confirm dialog for "Stage all"。
const confirmStageAllOpen = ref(false);
const pendingStageAllCount = ref(0);
// 2026-07-17 git-revert: confirm dialog for the History view's
// per-commit revert action.
const revertDialogOpen = ref(false);
const pendingRevert = ref<{ sha: string; subject: string } | null>(null);
// Symmetric dialog for "Unstage all" — visible only from the staged
// scope where the bulk button's label flips to "取消全部暂存".
const confirmUnstageAllOpen = ref(false);
const pendingUnstageAllCount = ref(0);

// Spec §3.3.4:commit dialog state。
const commitDialogOpen = ref(false);
const commitLastError = ref<{ reason: string; stderr: string } | null>(null);

// ── file-restore (spec §3.2) ───────────────────────────────────────
// Composable instance lives at sidebar level so it can call
// composable.refresh() and reach the snackbar / dialog state.
const fileRestore = useSpcodeFileRestore();
const fileDiscardHunk = useSpcodeFileDiscardHunk();
const restoringFile = ref<string | null>(null);

// Spec §3.2 + restore-refresh-status: after a successful restore
// (single or batch) we must re-fetch BOTH git-diff and git-status in
// parallel. useSpcodeGitDiff does NOT touch git-status, and the
// polling interval is 10s — without an explicit refresh the user
// would see the row linger in the newFilePaths set / stagedCount
// counter for up to 10s after the file is gone. Mirrors the refresh
// pattern used by stage / unstage / commit (8 call sites all use
// the same `Promise.all([composable.refresh(), gitStatus.refresh()])`).
async function refreshDiffAndStatus(): Promise<void> {
  await Promise.all([composable.refresh(), gitStatus.refresh()]);
}

// Confirm dialog state.
const confirmDialogOpen = ref(false);
const confirmTargetPath = ref<string | null>(null);
// 2026-07-15 restore-edge-cases: when the target file is brand-new
// (untracked / from git-status newFile scope), restore = unlink the
// worktree copy, not "discard changes". Surface a different confirm
// message so the user isn't surprised by an implicit delete.
//
// Derived from `confirmTargetPath` + `newFilePaths` rather than a
// standalone `ref` so the message flag is *always* in lock-step with
// the path. A manually-set ref risked a brief render where the
// dialog opened with the new path but the *previous* file's isNew
// flag — perceived as "stacking" two dialogs.
const confirmTargetIsNew = computed<boolean>(
  () =>
    confirmTargetPath.value !== null &&
    newFilePaths.value.has(confirmTargetPath.value),
);

// Bulk-restore state. The handler iterates the captured path list
// one file at a time and aggregates the result into a single
// snackbar. We use a dedicated dialog (rather than reusing the
// single-file `confirmDialogOpen`) so the message can include the
// file count and so a single `false` button click cleanly aborts
// the whole batch.
const confirmRestorePathsOpen = ref(false);
const pendingRestorePaths = ref<string[]>([]);
const isBulkRestoring = ref(false);

// ── Worktree management state (spec 2026-06-27 §2.4) ────────
const createDialogOpen = ref(false);
const removeDialogOpen = ref(false);
const lockDialogOpen = ref(false);
const confirmUnlockOpen = ref(false);
const confirmUnlockPath = ref<string | null>(null);
const lockDialogTarget = ref<{ path: string; branch: string | null } | null>(
  null,
);
const removeDialogTarget = ref<{ path: string; branch: string | null } | null>(
  null,
);
const dirtyCount = ref<number | null>(null);
const isRemoving = ref(false);
const isLocking = ref(false);
const isUnlocking = ref(false);
const isCreating = ref(false);
const lastCreateError = ref<{ reason: string; stderr: string } | null>(null);
const removeForceChecked = ref(false);

// Context menu state (spec 2026-06-27 §2.3). Position is set from
// MouseEvent.clientX/Y in openContextMenu and applied as fixed
// `left/top` styles on the teleported wrapper (see contextMenuStyle).
// The menu DOM lives in <body> via <Teleport>, so `position: fixed`
// coordinates are viewport-relative — exactly what we want for a
// right-click at the cursor.
const contextMenu = ref<{
  open: boolean;
  x: number;
  y: number;
  wt: SpcodeGitWorktree | null;
}>({ open: false, x: 0, y: 0, wt: null });

// Wrapper element ref for outside-click detection. We attach a
// mousedown listener on document in onMounted; if the click target
// isn't inside this element, we close the menu.
const contextMenuEl = ref<HTMLElement | null>(null);

// Edge-clamp the menu so it stays inside the viewport. If the user
// right-clicks near the right/bottom edge, the menu would otherwise
// overflow. We measure after mount via nextTick and adjust left/top.
const contextMenuStyle = ref<Record<string, string>>({});
function positionContextMenu(): void {
  if (!contextMenu.value.open) return;
  const el = contextMenuEl.value;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let left = contextMenu.value.x;
  let top = contextMenu.value.y;
  // Flip horizontally if overflow right edge.
  if (left + rect.width > vw) {
    left = Math.max(4, vw - rect.width - 4);
  }
  // Flip vertically if overflow bottom edge.
  if (top + rect.height > vh) {
    top = Math.max(4, vh - rect.height - 4);
  }
  contextMenuStyle.value = {
    position: "fixed",
    left: `${left}px`,
    top: `${top}px`,
    zIndex: "2400",
  };
}

async function openContextMenu(
  e: MouseEvent,
  wt: SpcodeGitWorktree,
): Promise<void> {
  // Set state in two steps so Vue commits the DOM (the Teleport
  // target) before we measure it in positionContextMenu. Without the
  // first sync write + nextTick, contextMenuEl.value would be null
  // when we read getBoundingClientRect().
  contextMenu.value = { open: false, x: e.clientX, y: e.clientY, wt };
  await nextTick();
  contextMenu.value.open = true;
  await nextTick();
  positionContextMenu();
}

// Close helpers. We attach document-level listeners (see onMounted)
// and dispatch through these so menu items don't need to know about
// the ref shape.
function closeContextMenu(): void {
  contextMenu.value.open = false;
}
function closeContextMenuOnOutside(e: MouseEvent): void {
  if (!contextMenu.value.open) return;
  const el = contextMenuEl.value;
  if (el && e.target instanceof Node && !el.contains(e.target)) {
    closeContextMenu();
  }
}
function closeContextMenuOnEscape(e: KeyboardEvent): void {
  if (e.key === "Escape" && contextMenu.value.open) {
    closeContextMenu();
  }
}

// Snackbar state (success / warning / error). Spec §5.3 / §6.8:stderr
// 单独字段,withStderr reason 携带,模板里 <pre> 块渲染。
interface SnackbarState {
  show: boolean;
  message: string;
  color: "success" | "info" | "warning" | "error";
  stderr?: string;
}
const snackbar = ref<SnackbarState>({
  show: false,
  message: "",
  color: "success",
});

function showSnackbar(
  message: string,
  color: "success" | "info" | "warning" | "error",
  stderr?: string,
): void {
  snackbar.value = { show: true, message, color, stderr };
}

// Maps a restore reason code to a snackbar message + color.
const RESTORE_REASON_I18N_KEYS: Record<
  string,
  { key: string; color: "warning" | "error" }
> = {
  invalid_body: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.invalid_body",
    color: "error",
  },
  missing_file: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.missing_file",
    color: "error",
  },
  feature_disabled: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.feature_disabled",
    color: "error",
  },
  no_project_loaded: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.no_project_loaded",
    color: "error",
  },
  directory_missing: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.directory_missing",
    color: "error",
  },
  not_a_git_repo: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.not_a_git_repo",
    color: "error",
  },
  worktree_invalid: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.worktree_invalid",
    color: "error",
  },
  git_unavailable: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.git_unavailable",
    color: "error",
  },
  path_unsafe: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.path_unsafe",
    color: "error",
  },
  file_not_found: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.file_not_found",
    color: "error",
  },
  not_modified: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.not_modified",
    color: "warning",
  },
  // 2026-07-15 restore-edge-cases: untracked_file 由 file-restore 端点移除
  // —— 端点现在直接 unlink 未跟踪文件作为"撤销新增"路径,前端不再渲染
  // 这个 reason。reason code 仍存在于 file-discard-hunk 路径(useSpcodeFileDiscardHunk
  // 自己的 REASON 集合),不归此 palette 管。
  git_error: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.git_error",
    color: "error",
  },
  network: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.network",
    color: "error",
  },
  unknown: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.unknown",
    color: "error",
  },
};

// 2026-07-17 git-revert: reason palette for the History-view revert
// flow (docs/api/webapi-git-revert-api.md §4). withStderr reasons
// carry actionable git output (conflict details, hook messages) and
// are surfaced in the snackbar's <pre> block.
const REVERT_REASON_I18N_KEYS: Record<
  string,
  { key: string; color: "warning" | "error"; withStderr?: boolean }
> = {
  invalid_body: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.invalid_body",
    color: "error",
  },
  invalid_param: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.invalid_param",
    color: "error",
  },
  feature_disabled: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.feature_disabled",
    color: "error",
  },
  no_project_loaded: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.no_project_loaded",
    color: "error",
  },
  worktree_invalid: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.worktree_invalid",
    color: "error",
  },
  directory_missing: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.directory_missing",
    color: "error",
  },
  not_a_git_repo: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.not_a_git_repo",
    color: "error",
  },
  git_unavailable: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.git_unavailable",
    color: "error",
  },
  commit_not_found: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.commit_not_found",
    color: "error",
  },
  empty_repository: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.empty_repository",
    color: "error",
  },
  worktree_dirty: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.worktree_dirty",
    color: "warning",
  },
  // REVERT_HEAD intermediate state is left behind on conflict — the
  // message tells the user to finish/abort manually in a terminal.
  revert_conflict: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.revert_conflict",
    color: "warning",
    withStderr: true,
  },
  nothing_to_revert: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.nothing_to_revert",
    color: "warning",
  },
  hook_rejected: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.hook_rejected",
    color: "error",
    withStderr: true,
  },
  identity_not_set: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.identity_not_set",
    color: "error",
  },
  nothing_to_commit: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.nothing_to_commit",
    color: "error",
    withStderr: true,
  },
  // Frontend-only code: git refuses merge-commit reverts (no -m
  // support in the endpoint) → git_error whose stderr mentions
  // "is a merge". Mapped to a dedicated message below.
  merge_commit: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.merge_commit",
    color: "error",
  },
  git_error: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.git_error",
    color: "error",
    withStderr: true,
  },
  network: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.network",
    color: "error",
  },
  unknown: {
    key: "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertError.reason.unknown",
    color: "error",
  },
};

// ── Revert commit (History view, 2026-07-17) ─────────────────────
function onLogRevertRequest(commit: { sha: string; subject: string }): void {
  pendingRevert.value = commit;
  revertDialogOpen.value = true;
}

function onCancelRevert(): void {
  revertDialogOpen.value = false;
  pendingRevert.value = null;
}

async function onConfirmRevert(): Promise<void> {
  const target = pendingRevert.value;
  if (!target) return;
  const result = await gitRevert.revert({
    ref: target.sha,
    worktree: selectedWorktree.value,
    umo: spcodeStatus.status.value.umo,
  });
  if (result.ok) {
    revertDialogOpen.value = false;
    pendingRevert.value = null;
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertSuccess", {
        message: result.snapshot.revertMessage,
      }),
      "success",
    );
    // The endpoint created a new HEAD commit — log / status / diff
    // caches are stale. Refresh in parallel; the read endpoints'
    // ETags revalidate server-side so plain refreshes return fresh
    // data (per the endpoint doc §6).
    void Promise.all([
      gitLog.refresh(),
      gitStatus.refresh(),
      composable.refresh(),
    ]);
    return;
  }
  if (result.reason === "aborted") return;
  // Merge commits land in git_error ("is a merge" in stderr) since
  // the endpoint passes no -m; remap to the dedicated message.
  const reason =
    result.reason === "git_error" && /is a merge/i.test(result.stderr ?? "")
      ? "merge_commit"
      : result.reason;
  const meta =
    REVERT_REASON_I18N_KEYS[reason] ?? REVERT_REASON_I18N_KEYS.unknown;
  revertDialogOpen.value = false;
  pendingRevert.value = null;
  showSnackbar(tm(meta.key), meta.color, meta.withStderr ? result.stderr : undefined);
}

const isProjectLoaded = computed(
  () => spcodeStatus.status.value.loaded === true,
);

// Spec 2026-07-16: derived state for the GitRepoInitPrompt slot. All four
// refs/booleans are colocated so the template-binding code in Task 5
// stays compact and obvious.
const isGitRepo = computed(() => gitRepoProbe.state.value.kind === "ok");
const isRepoInitSubmitting = ref(false);
const repoInitLastError = ref<{ reason: string; stderr?: string } | null>(null);
const repoPromptDismissed = ref(false);
const showRepoInitPrompt = computed(
  () =>
    isProjectLoaded.value
    && gitRepoProbe.state.value.kind === "not_a_git_repo"
    && !repoPromptDismissed.value,
);
const showNotGitRepoChip = computed(
  () =>
    isProjectLoaded.value
    && gitRepoProbe.state.value.kind === "not_a_git_repo"
    && repoPromptDismissed.value,
);
// True while a scope-switch request is in flight. Drives the per-pill
// spinner and the disabled state on the *other* two pills, so the
// user can't queue up a second switch before the first resolves.
const isScopeLoading = computed(() => pendingScope.value !== null);

const isFetching = ref(false);
// Template ref to the <FileBrowserView> child so the header refresh
// button can reach its exposed refresh() method when the user is in
// files view. The component is rendered behind v-if="viewMode==='files'",
// so the ref is null while diff view is active — onManualRefresh
// handles the null case explicitly.
// Inline interface (instead of InstanceType<typeof FileBrowserView>)
// because <script setup> components don't auto-export their exposed
// methods to the public type — defineExpose types are local to the
// file that calls it. Mirroring the shape here keeps the consumer
// honest about what it can call.
const fileBrowserRef = ref<{ refresh: () => Promise<void> } | null>(null);
// Mirror of fileBrowserRef for <GitDiffBodyContent>. We need
// `clearSelection` to drop the "selected N files" counter after a
// successful bulk stage/unstage — the child owns the Set (it's a
// UI concern scoped to that component), so the parent reaches in
// via the exposed method instead of duplicating the state here.
// Same `v-if="viewMode==='diff'"` caveat: ref is null in other tabs,
// so callers null-check before invocation.
const gitDiffBodyRef = ref<{ clearSelection: () => void } | null>(null);
async function onManualRefresh(): Promise<void> {
  if (isFetching.value) return;
  isFetching.value = true;
  try {
    // View-mode-aware dispatch (option B): in files view the button
    // reloads the workspace (directory listing + file preview);
    // otherwise it reloads the git diff data. The previous behavior
    // (always reload git diff) was a UX trap in files view — the
    // user could see the spinner but no visible data would change.
    //
    // Worktree list refreshes in PARALLEL regardless of viewMode:
    //   - It's cheap (one porcelain v1 call) so there's no UX cost.
    //   - The worktree tab switcher IS visible across all three
    //     tabs, so leaving it stale would surprise the user
    //     (e.g. they just added a worktree in a terminal and want
    //     to see it in the sidebar immediately).
    // We add it as a side-effect, NOT a replacement, so the
    // view-mode branch keeps its original target.
    const worktreeRefresh = worktreesComposable.refresh();
    if (viewMode.value === "files") {
      await Promise.all([
        fileBrowserRef.value?.refresh() ?? Promise.resolve(),
        worktreeRefresh,
      ]);
    } else {
      await Promise.all([composable.refresh(), worktreeRefresh]);
    }
  } finally {
    isFetching.value = false;
  }
}

// Fetch worktree list once on mount (lightweight, fire-and-forget).
// Spec §3.3: useSpcodeWorktrees does NOT depend on umo.
onMounted(() => {
  void worktreesComposable.refresh();
  // Spec 2026-07-16: initial probe on mount. The composable internally
  // watches `umo`/`directory` and re-probes on project switch, so a
  // single refresh() on mount is enough.
  void gitRepoProbe.refresh();
  // Listen on capture phase so we fire BEFORE any inner click handler
  // that might preventDefault / stopPropagation. mousedown is the
  // natural event for outside-click detection (mirrors what Vuetify
  // v-menu does internally with its overlay).
  document.addEventListener("mousedown", closeContextMenuOnOutside, true);
  document.addEventListener("keydown", closeContextMenuOnEscape, true);
  // Fullscreen cancel handler: bound to document (not window) in
  // bubble phase so the component-local Escape handlers (the file
  // browsers' capture-phase handlers, SearchPanel, etc.) run first.
  // The globalFullscreen guard filters out non-fullscreen cases so
  // other Escape shortcuts keep working unchanged.
  document.addEventListener("keydown", onFullscreenKeyDown);
});

// ── Worktree polling (added 2026-06-25, elecvoid243) ──────────────
// Spec: "当且仅当侧边栏打开时才触发轮询" — the agent can run
// `git worktree add` / `git worktree remove` while the user is
// staring at the sidebar, and the tab switcher must reflect that
// within a reasonable delay. We poll at 30s (the composable's
// DEFAULT_POLL_MS) so the user doesn't see a stale list after the
// agent bootstraps a new worktree.
//
// DECOUPLING NOTE: this watcher is intentionally separate from the
// viewMode-aware polling watcher below. Rationale:
//   - The worktree list powers the tab switcher for ALL three tabs
//     (diff / files / history), not just the diff tab.
//   - The user shouldn't have to switch to the diff tab to "wake
//     up" the worktree refresh — that's a footgun.
//   - Mixing the worktree polling lifecycle into the diff/history
//     branch logic would create cross-concern coupling (a
//     future tab addition would need to remember to start/stop
//     worktree polling, easy to forget).
//
// `immediate: true` covers the "sidebar is open at mount" case
// (which is the common case in this dashboard — the sidebar is
// always mounted, just sometimes closed). For the "starts closed
// then opens" path, modelValue flipping true starts the timer.
//
// isGitRepo is part of the gate: a non-Git project has no worktrees
// to list, so polling 30s for it is pure waste. The watcher below
// (`isGitRepo` race-catch) tears down any timer that already started
// when the probe lands on `not_a_git_repo`.
watch(
  () => props.modelValue,
  (open) => {
    if (open && isGitRepo.value) {
      worktreesComposable.startPolling(30_000);
    } else {
      worktreesComposable.stopPolling();
    }
  },
  { immediate: true },
);

// Spec 2026-07-16: one-shot check on open. The prompt is driven by
// "is the loaded directory a Git repo?", which doesn't change while
// the user is staring at the sidebar. Re-probing every 30s would just
// waste a round-trip. The umo/directory watcher inside the composable
// handles the only case where the answer can change without
// re-opening the sidebar: the user issuing a `/project load` while
// it's open.
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      void gitRepoProbe.refresh();
    }
  },
  { immediate: true },
);

// Race-catch: modelValue→true fires startPolling synchronously, but
// the probe's `not_a_git_repo` resolution lands in a later microtask.
// Without this, a 30s worktree timer would already be ticking by the
// time the probe returns. Teardown all four composables together so
// the gate has a single source of truth.
watch(isGitRepo, (isRepo) => {
  if (isRepo) return;
  worktreesComposable.stopPolling();
  composable.stopPolling();
  gitStatus.stopPolling();
  gitLog.stopPolling();
});

// Spec: polling starts ONLY when the sidebar is open, the user is on
// the Git Diff / History tab, AND the project is actually a Git repo.
// The Files ("workspace") tab never polls — there's no diff data to
// refresh, and pulling it would be wasted network/CPU. Non-Git
// projects never poll at all (no worktrees, no diff, no history) —
// the catch-all `else` branch keeps all three composables stopped.
// We track all three inputs in a single watcher so the polling
// lifecycle has one source of truth.
watch(
  [() => props.modelValue, viewMode, isGitRepo],
  async ([open, mode, isRepo]) => {
    const isDiff = mode === "diff";
    const isHistory = mode === "history";
    if (open && isDiff && isRepo) {
      isFetching.value = true;
      try {
        // Fetch diff + status in parallel. The git-status call is
        // intentionally NOT awaited via `await` in the polling branch
        // (a slow status call should not delay the diff refresh), but
        // here we DO await both so the initial load is consistent
        // before the first render. Fire-and-forget would risk showing
        // an empty "new files" section on first paint.
        await Promise.all([composable.refresh(), gitStatus.refresh()]);
      } finally {
        isFetching.value = false;
      }
      // Re-check conditions after await: the user may have switched
      // tabs, closed the sidebar, or the probe may have flipped to
      // `not_a_git_repo` during the refresh. Starting polling here
      // without re-checking would leak a timer in any of those cases.
      if (
        props.modelValue
        && viewMode.value === "diff"
        && isGitRepo.value
      ) {
        composable.startPolling(10_000);
        // git-status polling rides on the same cadence so the
        // "new files" section stays in sync with diff changes.
        gitStatus.startPolling(10_000);
      }
      gitLog.stopPolling();
    } else if (open && isHistory && isRepo) {
      // History view polls gitLog instead of gitDiff.
      isFetching.value = true;
      try {
        await gitLog.refresh();
      } finally {
        isFetching.value = false;
      }
      if (props.modelValue && viewMode.value === "history" && isGitRepo.value) {
        gitLog.startPolling(10_000);
      }
      composable.stopPolling();
      gitStatus.stopPolling();
    } else {
      composable.stopPolling();
      gitStatus.stopPolling();
      gitLog.stopPolling();
    }
  },
  { immediate: true },
);

// Refresh git-status when the user switches INTO the unstaged view
// (the composable only watches `worktreeRef` for refetch triggers; we
// need scope-driven refresh too). Without this the user could see a
// stale untracked list after toggling between staged/all/unstaged.
watch(
  () => selectedScope.value,
  (scope) => {
    if (scope === "unstaged" && props.modelValue && viewMode.value === "diff") {
      void gitStatus.refresh();
    }
  },
);

// 2026-07-18 git-stats heatmap: lazy-fetch the stats snapshot once
// the panel is (or becomes) visible. Fires on: sidebar open while in
// history view, switching into history view, panel re-expand, and
// worktree switch while visible (the composable keys ETag + previous
// snapshot by umo|worktree, so same-worktree repeats are cheap 304s).
watch(
  [() => props.modelValue, viewMode, isGitRepo, statsOpen, selectedWorktree],
  ([open, mode, isRepo, panelOpen]) => {
    if (open && mode === "history" && isRepo && panelOpen) {
      void gitStats.refresh();
    }
  },
  { immediate: true },
);

// ── Merged view (git-diff + git-status new files) ─────────────────
// For the **unstaged** and **all (vs HEAD)** views we want brand-new
// files (`untracked` + `intent_to_add`) to appear alongside modified
// files in one list, with the new files rendered with a distinct
// color. We achieve this by:
//   1. Building a `newFilePaths` Set from git-status's untracked +
//      intent_to_add entries. The set is the source of truth for
//      "is this row a new file"; the body content consults it.
//   2. When the diff snapshot is `ok`, we splice a synthesized entry
//      for each new file into the snapshot's `files` array so the body
//      iterates a single list. New files use `status: "A"` (matches
//      semantic meaning: "added to project") and carry a stub slice
//      (no diff content available from git-status). The
//      `!existing.has(f.path)` guard inside the merge is what makes
//      the same code safe across both views: `git diff HEAD` (all
//      scope) already returns `intent_to_add` paths, so the splice
//      becomes a no-op for those, while `untracked` paths are added
//      because no native diff command includes them.
//   3. We only skip the merge for the **staged** scope: there,
//      `git diff --cached` already covers everything that could be
//      staged, and an untracked file is by definition not staged.
const EMPTY_PATH_SET: ReadonlySet<string> = new Set<string>();

const newFilePaths = computed<ReadonlySet<string>>(() => {
  if (selectedScope.value === "staged") return EMPTY_PATH_SET;
  const s = gitStatus.state.value;
  if (s.kind !== "ok") return EMPTY_PATH_SET;
  const paths: string[] = [];
  for (const f of s.snapshot.files) {
    if (isNewFileScope(f.scope)) paths.push(f.path);
  }
  return new Set(paths);
});

// ── New-file line counts ────────────────────────────────────────────
// git-status does not return patch data, so the new-file stubs have
// no `additions` count. We compensate by reading each new file via
// /spcode/file-browser (cached, worktree-scoped) and counting lines
// locally. The composable fills `lineCounts.counts.value` reactively
// as fetches complete; until then the row renders "+0 −0" (same as a
// diff row with no slice). See useSpcodeNewFileLineCounts.ts for the
// cache / revalidation strategy. `currentRoot` is defined further
// below for the FileBrowserView — we inline its expression here so
// the composable runs before that declaration.
const lineCounts = useSpcodeNewFileLineCounts(
  newFilePaths,
  computed(() => selectedWorktree.value ?? mainWorktreePath.value ?? ""),
);

/** Build a SpcodeGitDiffFile-shaped stub for an untracked/intent-to-add
 *  entry. No native diff slice is available (git-status does not
 *  return patches), but `useSpcodeNewFileLineCounts` caches the raw
 *  file content per path, so we synthesize a unified-diff slice with
 *  a `@@ -0,0 +1,N @@` header and `+`-prefixed lines. This lets
 *  <DiffPreview> render the file with line numbers, the green
 *  "added" tint, the standard 30-line truncation, and a
 *  "Show all N lines" overflow button — all without a new
 *  component. When the content is not yet fetched (or the file is
 *  binary / too large), `slice` is null and the row shows the
 *  "noContent" placeholder. `status: "A"` keeps the row aligned
 *  with regular "added" diff entries; GitDiffFileItem.vue still
 *  uses the `isNewFile` prop to render a distinct left icon
 *  (mdi-file-plus-outline). */
function newFileStub(f: SpcodeGitStatusFile): SpcodeGitDiffFile {
  const content = lineCounts.contents.value.get(f.path);
  return {
    path: f.path,
    status: "A" as FileStatus,
    additions: lineCounts.counts.value.get(f.path) ?? 0,
    deletions: 0,
    slice: content !== undefined ? buildNewFileSlice(content) : null,
    isBinary: false,
  };
}

/** Build a synthetic unified-diff slice from the raw content of a
 *  brand-new file. Mirrors what `git diff /dev/null <file>` would
 *  emit: one hunk starting at line 1 of the new file, with every
 *  line marked as an addition. The trailing empty line introduced
 *  by a final `\n` is dropped so the hunk header's count matches
 *  the additions badge (which `countLines` already normalizes). */
function buildNewFileSlice(content: string): string {
  // Split on \n; file-browser already normalized \r\n → \n.
  const raw = content.split("\n");
  // Drop the trailing empty element caused by a final newline so
  // the displayed line count matches the +N badge.
  const lines = raw[raw.length - 1] === "" ? raw.slice(0, -1) : raw;
  const header = `@@ -0,0 +1,${lines.length} @@`;
  const body = lines.map((line) => `+${line}`).join("\n");
  return `${header}\n${body}\n`;
}

/**
 * State passed to <GitDiffBodyContent>. In the unstaged view it is the
 * composable's state with new files spliced into `snapshot.files`. In
 * any other scope we pass the composable's state untouched. The error
 * path is also untouched — new-file data should never mask a real
 * git-diff error.
 */
const diffBodyState = computed<GitDiffFetchState>(() => {
  const base = composable.state.value;
  // See `newFilePaths` above for why we skip the merge only for the
  // staged scope. The "all" scope shares the same splice logic as
  // "unstaged" — the `!existing.has` guard inside the loop
  // dedupes `intent_to_add` paths that already arrive from
  // `git diff HEAD`.
  if (selectedScope.value === "staged") return base;
  if (base.kind !== "ok") return base;
  const snapshot: SpcodeGitDiffSnapshot = base.snapshot;
  const statusSnap = gitStatus.state.value;
  if (statusSnap.kind !== "ok") return base;
  const existing = new Set(snapshot.files.map((f) => f.path));
  const stubs: SpcodeGitDiffFile[] = [];
  for (const f of statusSnap.snapshot.files) {
    if (isNewFileScope(f.scope) && !existing.has(f.path)) {
      stubs.push(newFileStub(f));
      existing.add(f.path);
    }
  }
  if (stubs.length === 0) return base;
  return {
    kind: "ok",
    snapshot: {
      ...snapshot,
      files: [...snapshot.files, ...stubs],
    },
  };
});

// Reset selectedWorktree to null (main) when project is unloaded or
// the loaded directory changes — the previous path may no longer be valid.
watch(
  () => spcodeStatus.status.value.loaded,
  (loaded) => {
    if (!loaded) {
      selectedWorktree.value = null;
      emit("update:modelValue", false);
    }
  },
);
watch(
  () => spcodeStatus.status.value.directory,
  () => {
    selectedWorktree.value = null;
  },
);

// Spec 2026-06-20 §3.4: switching worktree is a new working context;
// reset the scope to the default (`unstaged`). Handled in the click
// handler (see ``onWorktreeChange``) rather than a ``selectedWorktree``
// watcher, because the ``directory`` watcher above also writes to
// ``selectedWorktree`` on project switches and we MUST NOT reset the
// user's scope preference in that case (spec §3.4: directory change
// preserves scope).

// Spec 2026-06-20 §2.3: clear the in-flight marker the moment a
// response lands, regardless of which scope the server echoed.
//
// Why unconditional: the previous version gated clearing on
// `s.snapshot.meta.scope === pendingScope.value`. That failed in two
// real scenarios:
//   1. The spcode plugin running v3.0 (pre-scope) returns no
//      `data.scope` field, so `normalizeScope(undefined) === null`
//      and the equality check is `null === 'staged'` → false → the
//      spinner hangs forever even though the body already shows the
//      fresh data.
//   2. A late-arriving response for an already-superseded scope
//      (e.g. user clicked "staged" then "all" before the first
//      request returned) leaves the pill spinning on the older
//      scope value.
//
// The composable still logs a `console.warn` via its drift detector
// when the echoed scope doesn't match what was requested, so
// observability is preserved.
watch(
  () => composable.state.value,
  (s) => {
    if (pendingScope.value === null) return;
    if (s.kind === "ok" || s.kind === "error") {
      pendingScope.value = null;
    }
  },
);

// Spec 2026-06-20 §3.4: clicking a worktree tab is a new working
// context, so reset the scope to default. Done here (not in a
// watcher) so project switches — which also reset selectedWorktree
// via the directory watcher above — do NOT clobber scope.
function onWorktreeChange(path: string | null): void {
  // Spec 2026-07-16: switching worktrees is a new "did the user already
  // dismiss the prompt?" boundary. Reset so a different non-Git
  // worktree re-presents the init flow.
  repoPromptDismissed.value = false;
  selectedWorktree.value = path;
  selectedScope.value = DEFAULT_SCOPE;
  pendingScope.value = null;
}

// ── Worktree management handlers (spec 2026-06-27 §3) ────────

function openCreateDialog(): void {
  // 互斥：开 ADD 关其他
  removeDialogOpen.value = false;
  lockDialogOpen.value = false;
  confirmUnlockOpen.value = false;
  lastCreateError.value = null;
  createDialogOpen.value = true;
}

async function onCreateSubmit(params: WorktreeAddParams): Promise<void> {
  isCreating.value = true;
  lastCreateError.value = null;
  const result = await worktreesComposable.add(params);
  isCreating.value = false;
  if (isAborted(result)) {
    createDialogOpen.value = false;
    return;
  }
  if (result.ok) {
    // spec §7.4: 自动切到新 worktree + 切到 Files 视图
    const newWt = result.snapshot.worktrees.find(
      (w) => w.path === params.path,
    );
    if (newWt) {
      selectedWorktree.value = newWt.isMain ? null : newWt.path;
      viewMode.value = "files";
      fileBrowserCurrentPath.value = newWt.path;
      fileBrowserPreviewPath.value = null;
    }
    createDialogOpen.value = false;
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.create.success", {
        branch: params.branch ?? newWt?.branch ?? "",
      }),
      "success",
    );
  } else {
    // 用 classifyWorktreeReason 走统一错误处理
    const meta = classifyWorktreeReason(result.reason, "add");
    const key = `spcodeProjectLoad.diffSidebar.${meta.i18nKey}`;
    const message = meta.withReason
      ? tm(key, { reason: result.reason })
      : tm(key);
    lastCreateError.value = {
      reason: result.reason,
      stderr: result.stderr ?? "",
    };
    showSnackbar(
      message,
      meta.color,
      meta.withStderr ? result.stderr : undefined,
    );
  }
}

function onLockClick(wt: SpcodeGitWorktree): void {
  contextMenu.value.open = false;
  if (wt.locked) {
    // 直接进入 unlock 流程
    confirmUnlockPath.value = wt.path;
    removeDialogOpen.value = false;
    createDialogOpen.value = false;
    lockDialogOpen.value = false;
    confirmUnlockOpen.value = true;
    return;
  }
  // Lock 流程：弹窗让用户填 reason
  lockDialogTarget.value = { path: wt.path, branch: wt.branch };
  removeDialogOpen.value = false;
  createDialogOpen.value = false;
  confirmUnlockOpen.value = false;
  lockDialogOpen.value = true;
}

async function onLockSubmit(reason: string | null): Promise<void> {
  const target = lockDialogTarget.value;
  if (!target) return;
  isLocking.value = true;
  const params: WorktreeLockParams = {
    path: target.path,
    umo: spcodeStatus.status.value.umo,
  };
  if (reason) params.reason = reason;
  const result = await worktreesComposable.lock(params);
  isLocking.value = false;
  if (isAborted(result)) {
    lockDialogOpen.value = false;
    return;
  }
  if (result.ok) {
    lockDialogOpen.value = false;
    lockDialogTarget.value = null;
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.lock.success", {
        branch: target.branch ?? "",
      }),
      "success",
    );
  } else {
    const meta = classifyWorktreeReason(result.reason, "lock");
    const key = `spcodeProjectLoad.diffSidebar.${meta.i18nKey}`;
    const message = meta.withReason
      ? tm(key, { reason: result.reason })
      : tm(key);
    showSnackbar(
      message,
      meta.color,
      meta.withStderr ? result.stderr : undefined,
    );
  }
}

function onRemoveClick(wt: SpcodeGitWorktree): void {
  contextMenu.value.open = false;
  if (wt.isMain) return; // 双保险
  if (wt.locked) return; // 双保险
  removeDialogTarget.value = { path: wt.path, branch: wt.branch };
  dirtyCount.value = null;
  // Lazy load dirty count from /spcode/git-status
  void loadDirtyFor(wt);
  lockDialogOpen.value = false;
  createDialogOpen.value = false;
  confirmUnlockOpen.value = false;
  removeDialogOpen.value = true;
}

async function loadDirtyFor(wt: SpcodeGitWorktree): Promise<void> {
  const umo = spcodeStatus.status.value.umo;
  if (!umo) return;
  try {
    // Backend body is { status, data: { files, summary: { total } } };
    // axios unwraps to ApiEnvelope<T> (see @/api/v1.ts), so resp.data
    // is the envelope and we read resp.data.data.summary.total for the
    // authoritative dirty file count.
    const resp = await pluginExtensionApi.get<{
      files?: Array<unknown>;
      summary?: { total?: number };
    }>(
      "spcode/git-status",
      { params: { umo, worktree: wt.path } },
    );
    const data = resp.data?.data;
    dirtyCount.value =
      data?.summary?.total ?? data?.files?.length ?? 0;
  } catch {
    dirtyCount.value = null; // 不阻塞 UI
  }
}

async function onConfirmRemove(force: boolean): Promise<void> {
  const target = removeDialogTarget.value;
  if (!target) return;
  isRemoving.value = true;
  const result = await worktreesComposable.remove({
    path: target.path,
    force,
    umo: spcodeStatus.status.value.umo,
  });
  isRemoving.value = false;
  if (isAborted(result)) {
    removeDialogOpen.value = false;
    return;
  }
  if (result.ok) {
    // spec §7.5: 若被删的是当前 worktree,回退到主 worktree
    if (selectedWorktree.value === target.path) {
      selectedWorktree.value = null;
      // projectRoot.value is string|null; coerce to string with final fallback
      fileBrowserCurrentPath.value =
        mainWorktreePath.value ?? projectRoot.value ?? "";
    }
    removeDialogOpen.value = false;
    removeDialogTarget.value = null;
    dirtyCount.value = null;
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.success", {
        branch: target.branch ?? "",
      }),
      "success",
    );
  } else {
    const meta = classifyWorktreeReason(result.reason, "remove");
    const key = `spcodeProjectLoad.diffSidebar.${meta.i18nKey}`;
    const message = meta.withReason
      ? tm(key, { reason: result.reason })
      : tm(key);
    showSnackbar(
      message,
      meta.color,
      meta.withStderr ? result.stderr : undefined,
    );
  }
}

async function onConfirmUnlock(): Promise<void> {
  const path = confirmUnlockPath.value;
  if (!path) return;
  isUnlocking.value = true;
  const result = await worktreesComposable.unlock({
    path,
    umo: spcodeStatus.status.value.umo,
  });
  isUnlocking.value = false;
  if (isAborted(result)) {
    confirmUnlockOpen.value = false;
    return;
  }
  if (result.ok) {
    confirmUnlockOpen.value = false;
    confirmUnlockPath.value = null;
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.success"),
      "success",
    );
  } else {
    const meta = classifyWorktreeReason(result.reason, "unlock");
    const key = `spcodeProjectLoad.diffSidebar.${meta.i18nKey}`;
    const message = meta.withReason
      ? tm(key, { reason: result.reason })
      : tm(key);
    showSnackbar(
      message,
      meta.color,
      meta.withStderr ? result.stderr : undefined,
    );
  }
}

function onCancelUnlock(): void {
  if (isUnlocking.value) return;
  confirmUnlockOpen.value = false;
  confirmUnlockPath.value = null;
}

// Spec 2026-06-20 §3.4: clicking a scope pill updates the ref and
// stamps `pendingScope` so the UI can show a spinner + lock the
// other two pills. The composable's internal watcher re-fires the
// request, so we don't need to call refresh() here.
function onScopeChange(scope: GitDiffScope): void {
  if (scope === selectedScope.value) return;
  selectedScope.value = scope;
  pendingScope.value = scope;
}

// Navigation payload from FileBrowserView: dirPath is the directory
// whose entries appear in the left pane; previewPath is an optional
// file to display in the right pane (null = show directory hint).
// FileBrowserEntryList sends previewPath=null for directory clicks
// and previewPath=file.path for file/symlink clicks.
function onFileBrowserNavigate(payload: {
  dirPath: string;
  previewPath: string | null;
}): void {
  fileBrowserCurrentPath.value = payload.dirPath;
  fileBrowserPreviewPath.value = payload.previewPath;
  // 2026-07-02: clear any pending search-result scroll target.
  // The user is navigating manually, not via a search result;
  // leaving fileSearchScrollToLine set would re-scroll the next
  // file the user opens to the line from a prior search click.
  fileSearchScrollToLine.value = null;
}

// 2026-07-02 sidebar-search: handle a "click this result" from
// SearchPanel (forwards via FileBrowserView). payload.path is
// ABSOLUTE (the search composable joins the worktree root with the
// repo-relative match), payload.line is the 1-indexed match line —
// the preview pane scrolls there.
//
// Side effects:
//   1. fileBrowserPreviewPath = payload.path — FileBrowserView reacts
//      and triggers content fetch + scroll-to-line.
//   2. fileBrowserCurrentPath = dirOf(payload.path) — so the breadcrumb
//      shows the file's directory rather than the file itself, AND so
//      the left pane stays usable as a sibling listing.
//   3. (2026-07-18) closing the search panel moved INTO
//      FileBrowserView's onSearchOpenFile together with the rest of
//      the search UI — the panel REPLACES the file-browser body, so
//      it closes itself before this handler runs. The toolbar input
//      retains the query string, so the user can re-open the search
//      panel with one click on the magnifier.
//   4. fileSearchScrollToLine = payload.line — the 1-based target
//      line. 0 (filename mode) is normalized to null (= no scroll).
//      Propagated down to FileBrowserCodeView, which centers the
//      target line in the code-view scroll container.
function onFileOpen(payload: { path: string; line: number }): void {
  fileBrowserPreviewPath.value = payload.path;
  // POSIX + Windows separator: strip the trailing filename. Use a
  // single regex that matches either separator so the same code
  // works for both *nix and Windows worktree paths.
  const dir = payload.path.replace(/[\\/][^\\/]+$/, "");
  // Guard against degenerate empty dir (root file) and against an
  // unnecessary write if we're already pointing at this directory
  // (would re-trigger the persistCurrentPath debounce + a fetch).
  if (dir && dir !== fileBrowserCurrentPath.value) {
    fileBrowserCurrentPath.value = dir;
  }
  fileSearchScrollToLine.value = payload.line > 0 ? payload.line : null;
}

// Spec §5.3 + §6.4.1: 12 reason → i18n key. Reasons not in the map fall
// through to `error.reason.unknown` (caller passes raw reason to tm()).
const DISCARD_HUNK_REASON_I18N_KEYS: Record<string, string> = {
  patch_check_failed:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.patch_check_failed",
  patch_apply_failed:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.patch_apply_failed",
  patch_too_large:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.patch_too_large",
  patch_malformed:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.patch_malformed",
  not_modified:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.not_modified",
  untracked_file:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.untracked_file",
  multi_file_patch:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.multi_file_patch",
  patch_binary:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.patch_binary",
  no_project_loaded:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.no_project_loaded",
  worktree_invalid:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.worktree_invalid",
  not_a_git_repo:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.not_a_git_repo",
  git_unavailable:
    "spcodeProjectLoad.diffSidebar.discardHunk.error.reason.git_unavailable",
};

function classifySnackbarLevel(
  reason: string,
): "success" | "info" | "warning" | "error" {
  const FATAL = new Set([
    "not_a_git_repo",
    "git_unavailable",
    "feature_disabled",
  ]);
  const RETRY = new Set([
    "patch_apply_failed",
    "patch_check_failed",
    "git_error",
  ]);
  if (FATAL.has(reason)) return "error";
  if (RETRY.has(reason)) return "info";
  return "warning"; // user + config + unknown
}

// Spec §3.2 data flow: GitDiffFileItem -> GitDiffBodyContent -> here.
function onFileRestore(path: string): void {
  // ORDER MATTERS: set the path FIRST, then open the dialog.
  // `confirmTargetIsNew` is a computed derived from `confirmTargetPath`
  // (and `newFilePaths`), so its value is correct as soon as the path
  // is set. Opening the dialog while the path still held the previous
  // file's value would render the old file's message for one frame.
  confirmTargetPath.value = path;
  confirmDialogOpen.value = true;
}

/** Handles the "view file" button on a diff row: switches the sidebar
 *  to the Files tab and navigates to the file's parent directory with
 *  the file opened in the preview pane.
 *
 *  `path` arrives as a repo-relative path from git-diff (e.g.
 *  "dashboard/src/components/chat/GitDiffSidebar.vue"). The
 *  /spcode/file-browser backend requires absolute paths, and
 *  FileBrowserBreadcrumb's `normCurrent.startsWith(normRoot)` guard
 *  returns [] (no segments rendered) when the two don't share a
 *  common prefix — so passing the relative path through verbatim
 *  silently breaks the multi-level breadcrumb and misroutes the
 *  directory listing. Anchor to currentRoot (the active worktree or
 *  project root) before computing the parent. */
function onOpenFile(path: string): void {
  const root = currentRoot.value;
  // No project / worktree resolved yet → nothing to navigate to.
  // Skip silently rather than writing a relative path that would
  // corrupt the persisted currentPath.
  if (!root) return;
  // Detect separator from the root, since `root` comes from the
  // backend (Windows: `\`) and `path` comes from git (POSIX: `/`).
  const sep = root.includes("\\") ? "\\" : "/";
  const cleanRoot = root.replace(/[\\/]+$/, "");
  const cleanPath = path.replace(/^[\\/]+/, "").replace(/\//g, sep);
  const absolute = cleanPath ? `${cleanRoot}${sep}${cleanPath}` : cleanRoot;
  // Parent directory of the absolute path, using the same separator
  // style as the root. Falls back to the root when `path` had no
  // separator (top-level file like "README.md").
  const parent = absolute.includes(sep)
    ? absolute.substring(0, absolute.lastIndexOf(sep))
    : cleanRoot;
  viewMode.value = "files";
  fileBrowserCurrentPath.value = parent;
  fileBrowserPreviewPath.value = absolute;
  // Clear any pending search-result scroll target so the file does not
  // jump to a stale line from a prior search click. Mirrors
  // onFileBrowserNavigate which does the same on manual navigation.
  fileSearchScrollToLine.value = null;
}

function onCancelRestore(): void {
  // Close the dialog FIRST so the v-if-guarded v-card unmounts
  // synchronously — no in-between frame where v-card-text could
  // re-render with the previous file's flag.
  confirmDialogOpen.value = false;
  // Path cleanup happens in a microtask AFTER the close transition
  // begins, so the v-card is already gone (v-if="confirmDialogOpen"
  // unmounts it) by the time `confirmTargetIsNew` would flip to
  // false. The reset is still important for the next open: if we
  // skipped it, the next `onFileRestore` would see a stale path
  // (Vue would still pick the new value, but defensive nulling keeps
  // the state shape tidy).
  void nextTick(() => {
    confirmTargetPath.value = null;
  });
}

async function onConfirmRestore(): Promise<void> {
  const path = confirmTargetPath.value;
  if (!path) return;
  // Same pattern as onCancelRestore: close dialog first, clear path
  // after the next microtask. The v-if guard means no v-card lives
  // across the state change, so the user never sees the wrong
  // message text during the close transition.
  confirmDialogOpen.value = false;
  void nextTick(() => {
    confirmTargetPath.value = null;
  });
  restoringFile.value = path;
  const umo = spcodeStatus.status.value.umo;
  const worktree = selectedWorktree.value;
  const result: RestoreResult = await fileRestore.restore({
    file: path,
    worktree,
    umo,
  });
  restoringFile.value = null;
  // Special-case "aborted" (Chunk 2 review note): no toast, just reset state.
  // This only fires during teardown (pre-mount guard / post-await unmount / axios cancel).
  if (!result.ok && result.reason === "aborted") {
    return;
  }
  if (result.ok) {
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.restore.success", { path }),
      "success",
    );
    // Spec §3.2: success -> immediate refresh so the row disappears.
    await refreshDiffAndStatus();
  } else {
    const mapping =
      RESTORE_REASON_I18N_KEYS[result.reason] ??
      RESTORE_REASON_I18N_KEYS.unknown;
    const message =
      mapping.key ===
      "spcodeProjectLoad.diffSidebar.restore.error.reason.git_error"
        ? tm(mapping.key, { stderr: result.stderr ?? "" })
        : tm(mapping.key);
    showSnackbar(message, mapping.color);
  }
}

// ── Bulk restore (multi-select from GitDiffBodyContent) ────────────
//
// GitDiffBodyContent emits `restore-paths` with the array of currently
// selected paths. We open a dedicated confirmation dialog (showing the
// file count) and, on confirm, iterate one file at a time because the
// file-restore endpoint accepts a single `file` per request. The
// snackbar aggregates the result so the user sees a single toast
// (success / partial / all-failed) rather than N toasts.
function onRestorePaths(paths: string[]): void {
  if (paths.length === 0) return;
  pendingRestorePaths.value = paths.slice();
  confirmRestorePathsOpen.value = true;
}

function onCancelRestorePaths(): void {
  if (isBulkRestoring.value) return;
  confirmRestorePathsOpen.value = false;
  pendingRestorePaths.value = [];
}

async function onConfirmRestorePaths(): Promise<void> {
  const paths = pendingRestorePaths.value;
  if (paths.length === 0) return;
  confirmRestorePathsOpen.value = false;
  // Snapshot the list before clearing state so concurrent scope/worktree
  // switches (which would reset pendingRestorePaths via teardown) cannot
  // shorten the iteration.
  const toRestore = paths.slice();
  pendingRestorePaths.value = [];
  const umo = spcodeStatus.status.value.umo;
  const worktree = selectedWorktree.value;
  isBulkRestoring.value = true;
  let successCount = 0;
  let failedCount = 0;
  let aborted = false;
  try {
    for (const path of toRestore) {
      restoringFile.value = path;
      const result: RestoreResult = await fileRestore.restore({
        file: path,
        worktree,
        umo,
      });
      restoringFile.value = null;
      if (!result.ok) {
        if (result.reason === "aborted") {
          aborted = true;
          break;
        }
        failedCount++;
        continue;
      }
      successCount++;
    }
  } finally {
    restoringFile.value = null;
    isBulkRestoring.value = false;
  }
  // Aborted usually means the component is unmounting or the user
  // switched scope/worktree; skip the snackbar and leave the
  // selection in whatever state it ended up in (the new view will
  // rebuild it from scratch anyway).
  if (aborted) {
    return;
  }
  // Drop the toolbar's "已选 N 个" counter on a full success so the
  // user starts fresh; on partial / all-failed, keep the selection
  // so they can retry without re-ticking every box.
  if (successCount > 0 && failedCount === 0) {
    gitDiffBodyRef.value?.clearSelection();
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.restore.successMultiple", {
        count: successCount,
      }),
      "success",
    );
    await refreshDiffAndStatus();
  } else if (successCount > 0 && failedCount > 0) {
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.restore.successPartial", {
        success: successCount,
        total: toRestore.length,
        failed: failedCount,
      }),
      "warning",
    );
    await refreshDiffAndStatus();
  } else {
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.restore.error.allFailed", {
        count: toRestore.length,
      }),
      "error",
    );
  }
}

// Spec 2026-07-07 §3.3: hunk discard handler. Child (GitDiffFileItem)
// invokes this through the `onDiscardHunk` callback prop with a single
// object arg (matching the DiffPreview prop signature threaded through
// GitDiffFileItem → GitDiffBodyContent). Result drives both the
// snackbar toast and a refresh of the diff so the discarded hunk
// visually disappears. Mirrors the onConfirmRestore success /
// failure / aborted pattern.
async function onDiscardHunk(params: {
  file: string;
  hunkIndex: number;
  patchText: string;
}): Promise<void> {
  const { file, hunkIndex, patchText } = params;
  const umo = spcodeStatus.status.value.umo;
  if (!umo) return;
  const worktree = selectedWorktree.value;
  const result: DiscardHunkResult = await fileDiscardHunk.discard({
    file,
    hunkIndex,
    patchText,
    umo,
    worktree,
  });
  if (!result.ok && result.reason === "aborted") return;
  if (result.ok) {
    const n = result.snapshot.hunksReverted;
    const tmKey =
      n === 1
        ? "spcodeProjectLoad.diffSidebar.discardHunk.success"
        : "spcodeProjectLoad.diffSidebar.discardHunk.successMultiple";
    showSnackbar(tm(tmKey, { hunksReverted: n, file }), "success");
    // Spec §2 decision #7: success → immediate refresh so the hunk disappears.
    await composable.refresh();
  } else {
    const mapping = DISCARD_HUNK_REASON_I18N_KEYS[result.reason];
    const msg = mapping
      ? tm(mapping, { stderr: result.stderr ?? "" })
      : tm("spcodeProjectLoad.diffSidebar.discardHunk.error.reason.unknown", {
          reason: result.reason,
        });
    showSnackbar(msg, classifySnackbarLevel(result.reason));
  }
}

// ── Git workflow handlers (spec 2026-06-24 §3.3) ──────────────────
// All write paths follow the same recipe:
//   1. 调用 composable.{stage,unstage,commit}(params)
//   2. 成功 → 用响应 `files` 覆盖 stagedFiles,refresh diff,toast success
//   3. 失败 → toast (携带 stderr 的 reason 走 <pre> 块),不破坏本地状态
//   4. aborted → 静默(切 worktree / 卸载项目 / 组件卸载)
function isAborted(result: { ok: boolean; reason?: string }): boolean {
  return !result.ok && result.reason === "aborted";
}

function reasonKey(
  endpoint: "stage" | "unstage" | "commit",
  reason: string,
): string {
  // classifyReason 把 reason 字符串归一化到 ReasonMeta.i18nKey(已在
  // parseSpcodeGitWorkflow 暴露)。i18nKey 形如 "error.reason.path_unsafe"。
  const meta = classifyReason(reason, endpoint);
  return `spcodeProjectLoad.diffSidebar.gitWorkflow.${meta.i18nKey}`;
}

function reasonMeta(
  endpoint: "stage" | "unstage" | "commit",
  reason: string,
): { color: "error" | "warning"; withStderr: boolean; withReason: boolean } {
  const meta = classifyReason(reason, endpoint);
  return {
    color: meta.color,
    withStderr: !!meta.withStderr,
    withReason: !!meta.withReason,
  };
}

async function onStageFile(path: string): Promise<void> {
  if (gitStage.isStaging.value.has(path)) return;
  const umo = spcodeStatus.status.value.umo;
  const worktree = selectedWorktree.value;
  const result = await gitStage.stage({ files: [path], worktree, umo });
  if (isAborted(result)) return;
  if (result.ok) {
    // 乐观语义(spec §3.3.1):用响应 `files` 覆盖 stagedFiles。
    stagedFiles.value = new Set(result.snapshot.files);
    // Parallel refresh: git-diff shows the file in the staged view,
    // git-status moves it out of "untracked"/"intent_to_add" so the
    // merged unstaged list drops the new-file stub. Without the
    // second call the user would wait up to 10s for the polling
    // tick to remove the row.
    await Promise.all([composable.refresh(), gitStatus.refresh()]);
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.gitWorkflow.stage.success", { path }),
      "success",
    );
  } else {
    const meta = reasonMeta("stage", result.reason);
    const key = reasonKey("stage", result.reason);
    const message = meta.withReason
      ? tm(key, { reason: result.reason })
      : tm(key);
    showSnackbar(
      message,
      meta.color,
      meta.withStderr ? result.stderr : undefined,
    );
  }
}

// UI #3: bulk-stage handler. Calls gitStage once with the full path
// list (the backend already accepts an array), then mirrors the
// single-file `onStageFile` success path. Error handling is the same:
// reason-keyed i18n message + stderr in the snackbar's <pre> block.
async function onStagePaths(paths: string[]): Promise<void> {
  if (paths.length === 0) return;
  const umo = spcodeStatus.status.value.umo;
  const worktree = selectedWorktree.value;
  const result = await gitStage.stage({ files: paths, worktree, umo });
  if (isAborted(result)) return;
  if (result.ok) {
    stagedFiles.value = new Set(result.snapshot.files);
    // Parallel refresh: git-diff shows the file in the staged view,
    // git-status moves it out of "untracked"/"intent_to_add" so the
    // merged unstaged list drops the new-file stub. Without the
    // second call the user would wait up to 10s for the polling
    // tick to remove the row.
    await Promise.all([composable.refresh(), gitStatus.refresh()]);
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.gitWorkflow.stage.successAll", {
        count: paths.length,
      }),
      "success",
    );
    // Drop the toolbar's "暂存选中的 N 个文件" counter now that the
    // bulk write succeeded. Without this the child keeps holding the
    // file paths in its local selection Set, so the toolbar text
    // stays frozen at the pre-action count and the next click would
    // re-stage already-staged files. Run AFTER refresh so the row
    // removal is visible before the "已暂存 N" toast; failures skip
    // this so the user can retry without re-ticking every checkbox.
    gitDiffBodyRef.value?.clearSelection();
  } else {
    const meta = reasonMeta("stage", result.reason);
    const key = reasonKey("stage", result.reason);
    const message = meta.withReason
      ? tm(key, { reason: result.reason })
      : tm(key);
    showSnackbar(
      message,
      meta.color,
      meta.withStderr ? result.stderr : undefined,
    );
  }
}

async function onUnstageFile(path: string): Promise<void> {
  if (gitUnstage.isUnstaging.value.has(path)) return;
  const umo = spcodeStatus.status.value.umo;
  const worktree = selectedWorktree.value;
  const result = await gitUnstage.unstage({ files: [path], worktree, umo });
  if (isAborted(result)) return;
  if (result.ok) {
    stagedFiles.value = new Set(result.snapshot.files);
    // Parallel refresh: after unstaging, git-status reclassifies the
    // file (intent_to_add / unstaged) and the unstaged diff picks it
    // up; git-status must refresh in lock-step to avoid a stale
    // "Stage all" count and a stale new-file stub set.
    await Promise.all([composable.refresh(), gitStatus.refresh()]);
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.gitWorkflow.unstage.success", { path }),
      "success",
    );
  } else {
    const meta = reasonMeta("unstage", result.reason);
    const key = reasonKey("unstage", result.reason);
    const message = meta.withReason
      ? tm(key, { reason: result.reason })
      : tm(key);
    showSnackbar(
      message,
      meta.color,
      meta.withStderr ? result.stderr : undefined,
    );
  }
}

// Spec §6.7.1:unstagedCount 派生(分 scope)。
// Reads from diffBodyState (not composable.state) so the "Stage all"
// button includes untracked / intent-to-add files that were merged
// in from /spcode/git-status. The merge now runs for both the
// "unstaged" and "all (vs HEAD)" views (see `newFilePaths` above);
// without this the user would see "Stage all (3)" but only 2 diff
// rows get staged, leaving the new file behind. In the "all" view
// the formula becomes `total - stagedFiles.size` where `total`
// also includes the spliced untracked paths, which is the
// correct semantic — they are untracked, therefore unstaged.
const unstagedCount = computed(() => {
  const s = diffBodyState.value;
  if (s.kind !== "ok") return 0;
  const total = s.snapshot.files.length;
  if (selectedScope.value === "staged") return 0;
  if (selectedScope.value === "unstaged") return total;
  // all:total = staged + unstaged(快照的),减去当前 stagedFiles
  return Math.max(0, total - stagedFiles.value.size);
});

// Symmetric counterpart: number of files currently in the index,
// powering both the "取消全部暂存" button's disabled state and the
// commit button's disabled state (see GitCommitBar). Reads the
// authoritative backend count from git-status (which is polled in
// parallel with git-diff in the diff view, regardless of scope), and
// falls back to the local optimistic Set before the first status
// fetch completes so the count is never negative / flicker-y.
const stagedCount = computed(() => {
  const s = gitStatus.state.value;
  if (s.kind === "ok") return s.snapshot.summary.staged;
  return stagedFiles.value.size;
});

function onClickStageAll(): void {
  // 同步计算 pending count(spec §3.3.3 + P1-3 修复)。
  pendingStageAllCount.value = unstagedCount.value;
  confirmStageAllOpen.value = true;
}

function onCancelStageAll(): void {
  confirmStageAllOpen.value = false;
  // pendingStageAllCount 不重置(spec §3.3.3:无副作用)
}

async function onConfirmStageAll(): Promise<void> {
  confirmStageAllOpen.value = false;
  const umo = spcodeStatus.status.value.umo;
  const worktree = selectedWorktree.value;
  const result = await gitStage.stageAll({ worktree, umo });
  if (isAborted(result)) return;
  if (result.ok) {
    stagedFiles.value = new Set(result.snapshot.files);
    // Parallel refresh: "Stage all" affects every unstaged file
    // (modified + untracked); both endpoints must re-classify.
    await Promise.all([composable.refresh(), gitStatus.refresh()]);
    // Snackbar count: use the pre-action count (snapshotted in the
    // dialog at click time), NOT `result.snapshot.stagedCount` —
    // the latter is the POST-action remaining staged count per
    // the spcode API contract, which would be misleading here
    // (e.g. staging 3 files when 2 were already staged would
    // report 5; the user actually staged 3).
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.gitWorkflow.stage.successAll", {
        count: pendingStageAllCount.value,
      }),
      "success",
    );
  } else {
    const meta = reasonMeta("stage", result.reason);
    const key = reasonKey("stage", result.reason);
    const message = meta.withReason
      ? tm(key, { reason: result.reason })
      : tm(key);
    showSnackbar(
      message,
      meta.color,
      meta.withStderr ? result.stderr : undefined,
    );
  }
}

// Mirror of onClickStageAll for the staged scope, where the bar's
// bulk button flips to "取消全部暂存". Counts come from the
// authoritative git-status summary so the user sees the real number
// of files they'll move back to the worktree, not the optimistic
// Set (which lags by one user action on first load).
function onClickUnstageAll(): void {
  pendingUnstageAllCount.value = stagedCount.value;
  confirmUnstageAllOpen.value = true;
}

function onCancelUnstageAll(): void {
  confirmUnstageAllOpen.value = false;
  // pendingUnstageAllCount 不重置(对称 onCancelStageAll)
}

async function onConfirmUnstageAll(): Promise<void> {
  confirmUnstageAllOpen.value = false;
  const umo = spcodeStatus.status.value.umo;
  const worktree = selectedWorktree.value;
  const result = await gitUnstage.unstageAll({ worktree, umo });
  if (isAborted(result)) return;
  if (result.ok) {
    // Mirror onConfirmStageAll: overwrite the optimistic Set with
    // the response, then refresh diff + status in lock-step so the
    // row moves immediately from staged back to unstaged.
    stagedFiles.value = new Set(result.snapshot.files);
    await Promise.all([composable.refresh(), gitStatus.refresh()]);
    // Snackbar count: use the pre-action count from the dialog,
    // NOT `result.snapshot.stagedCount` — that field is the
    // POST-action remaining count, which would always be 0 after
    // unstage-all and read as "已取消暂存 0 个文件" (the bug the
    // user reported). `pendingUnstageAllCount` was captured when
    // the dialog opened, so it matches what the user just unstaged.
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.gitWorkflow.unstage.successAll", {
        count: pendingUnstageAllCount.value,
      }),
      "success",
    );
  } else {
    const meta = reasonMeta("unstage", result.reason);
    const key = reasonKey("unstage", result.reason);
    const message = meta.withReason
      ? tm(key, { reason: result.reason })
      : tm(key);
    showSnackbar(
      message,
      meta.color,
      meta.withStderr ? result.stderr : undefined,
    );
  }
}

// UI #3: bulk-unstage handler. Mirrors onStagePaths.
async function onUnstagePaths(paths: string[]): Promise<void> {
  if (paths.length === 0) return;
  const umo = spcodeStatus.status.value.umo;
  const worktree = selectedWorktree.value;
  const result = await gitUnstage.unstage({ files: paths, worktree, umo });
  if (isAborted(result)) return;
  if (result.ok) {
    stagedFiles.value = new Set(result.snapshot.files);
    await Promise.all([composable.refresh(), gitStatus.refresh()]);
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.gitWorkflow.unstage.successAll", {
        count: paths.length,
      }),
      "success",
    );
    // Symmetric to onStagePaths: the bulk unstage succeeds, the
    // selected rows leave the staged view, and we drop the toolbar's
    // "已选 N" counter so the next click does not re-fire the same
    // unstage on freshly-empty indices.
    gitDiffBodyRef.value?.clearSelection();
  } else {
    const meta = reasonMeta("unstage", result.reason);
    const key = reasonKey("unstage", result.reason);
    const message = meta.withReason
      ? tm(key, { reason: result.reason })
      : tm(key);
    showSnackbar(
      message,
      meta.color,
      meta.withStderr ? result.stderr : undefined,
    );
  }
}

function onClickCommit(): void {
  commitLastError.value = null;
  commitDialogOpen.value = true;
}

function onCancelCommit(): void {
  // commit 在飞行时不允许关闭(防 race)
  if (gitCommit.isCommitting.value) return;
  commitDialogOpen.value = false;
  commitLastError.value = null;
}

// Spec 2026-07-16: handlers for the GitRepoInitPrompt slot. The prompt
// is a single one-shot interaction (confirm or cancel), so neither
// handler takes any meaningful arguments beyond the existing
// composable state.
async function onRepoInitConfirm(): Promise<void> {
  if (!projectRoot.value) return;
  repoInitLastError.value = null;
  isRepoInitSubmitting.value = true;
  // v2.17.1: `force: true` skips the backend's "non-empty directory"
  // guard. Rationale: by the time this prompt is visible, the project
  // has already been loaded into Astrbot - the directory *definitely*
  // exists and almost certainly already has files in it. So "init"
  // here really means "convert this existing project into a
  // Git-managed project", which is exactly the semantics `force=true`
  // unlocks (existing files become untracked, nothing is deleted).
  // Refs: docs/api/v2.17.1-git-init-force-frontend-notice.md §4.
  const result = await gitRepoProbe.gitInit({
    path: projectRoot.value,
    force: true,
  });
  isRepoInitSubmitting.value = false;
  if (result.ok) {
    // Success path: the composable has already transitioned state to
    // `ok` and cleared its cache, so the prompt will unmount itself
    // via the `showRepoInitPrompt` computed. Reset the dismiss flag
    // so re-probing the same project (rare) re-shows the prompt if
    // the user manually nukes .git/ again.
    repoPromptDismissed.value = false;
    return;
  }
  repoInitLastError.value = {
    reason: result.reason,
    ...(result.stderr !== undefined ? { stderr: result.stderr } : {}),
  };
}

function onRepoInitCancel(): void {
  repoPromptDismissed.value = true;
  repoInitLastError.value = null;
}

async function onConfirmCommit(payload: { message: string }): Promise<void> {
  const umo = spcodeStatus.status.value.umo;
  const worktree = selectedWorktree.value;
  // 进入提交前清空 lastError(spec §3.3.4)
  commitLastError.value = null;
  const result = await gitCommit.commit({
    message: payload.message,
    worktree,
    umo,
  });
  if (isAborted(result)) {
    // abort 路径下,onBeforeUnmount 也会关 dialog
    commitDialogOpen.value = false;
    return;
  }
  if (result.ok) {
    // 成功:覆盖 stagedFiles(后端响应),refresh diff+status,可
    // 选 refresh log。git-status 也要刷新:commit 后工作区清空,
    // 文件从 untracked/unstaged/staged 三个集合中全部消失。
    stagedFiles.value = new Set(result.snapshot.files);
    commitDialogOpen.value = false;
    commitLastError.value = null;
    await Promise.all([composable.refresh(), gitStatus.refresh()]);
    if (viewMode.value === "history") {
      await gitLog.refresh();
    }
    const shortSha = (result.snapshot.sha || "").slice(0, 7) || "?";
    showSnackbar(
      tm("spcodeProjectLoad.diffSidebar.gitWorkflow.commit.success", {
        sha: shortSha,
      }),
      "success",
    );
  } else {
    // 失败:保持 dialog 打开,显示 stderr 块(spec §3.3.4 DIALOG_OPEN_KEEP_ERROR)
    const meta = reasonMeta("commit", result.reason);
    const key = reasonKey("commit", result.reason);
    commitLastError.value = {
      reason: result.reason,
      stderr: result.stderr ?? "",
    };
    const message = meta.withReason
      ? tm(key, { reason: result.reason })
      : tm(key);
    showSnackbar(
      message,
      meta.color,
      meta.withStderr ? result.stderr : undefined,
    );
  }
}

// Spec §3.4 决策 #24:切 worktree / 切 umo 时清空 ETag。
// 监听 selectedWorktree 和 umo,变更时调用 gitLog.invalidateEtag()。
watch(selectedWorktree, () => gitLog.invalidateEtag());
watch(
  () => spcodeStatus.status.value.umo,
  (newUmo, oldUmo) => {
    if (newUmo !== oldUmo) {
      gitLog.invalidateEtag();
    }
  },
);

// Spec §3.4 决策 #22:切 worktree 时保留 stagedFiles(本 spec 不重置)。
// 切 project (umo 变更) / 卸载项目 时清空。
watch(
  () => spcodeStatus.status.value.loaded,
  (loaded) => {
    if (!loaded) {
      stagedFiles.value = new Set<string>();
    }
  },
);
watch(
  () => spcodeStatus.status.value.directory,
  () => {
    // 目录变了 → 视作切了项目(decision #23)。
    stagedFiles.value = new Set<string>();
  },
);
// Spec §10 风险 #12:在 confirmStageAllOpen 打开时切 worktree,
// 先关 dialog(避免用户在切 worktree 后看到旧 worktree 的计数)。
// Same risk applies to confirmUnstageAllOpen — both dialogs snapshot
// the previous worktree's staged/unstaged count, so a switch mid-
// dialog would display a stale number after re-open.
watch(selectedWorktree, () => {
  if (confirmStageAllOpen.value) {
    confirmStageAllOpen.value = false;
  }
  if (confirmUnstageAllOpen.value) {
    confirmUnstageAllOpen.value = false;
  }
});

// ── History view wiring (spec 2026-06-24 §3.5) ───────────────────
const logHasMore = computed(() => {
  const s = gitLog.state.value;
  if (s.kind === "ok") return s.snapshot.hasMore;
  if (s.kind === "error" && s.previousSnapshot)
    return s.previousSnapshot.hasMore;
  return false;
});
const logIsLoading = computed(() => gitLog.state.value.kind === "loading");
function onLogApply(filter: LogFilter): void {
  // 用 filter 调用 refresh(spec §6.5.1:filter 变化时 key 自动变化,旧 ETag 不复用)
  void gitLog.refresh(filter);
}
// 2026-07-18 git-stats heatmap: the History-tab manual refresh button
// re-fetches the log AND the stats panel (ETag-validated; cheap 304s
// when nothing changed upstream).
function onLogRefresh(): void {
  void gitLog.refresh();
  void gitStats.refresh();
}
function onLogReset(filter: LogFilter): void {
  // Reset semantics differ from a regular Apply: the URL of the reset
  // request is identical to the very first history-tab load (?ref=HEAD&n=20),
  // so without dropping the ETag the backend returns 304 Not Modified and
  // the client-side 304 branch replays `prevSnapshot` — which was overwritten
  // by the user's most recent filter (e.g. author=alice) and therefore shows
  // the filtered result instead of the reset state. We invalidate only this
  // one tuple's ETag so other filter tuples (author=bob etc.) keep their
  // cache and remain cheap to revisit. forceLoading makes the spinner show
  // even though the previous state was already ok, so the user gets
  // feedback that a refresh is in flight.
  gitLog.invalidateEtagFor(filter);
  void gitLog.refresh(filter, { forceLoading: true });
}
function onLogLoadMore(): void {
  void gitLog.loadMore();
}

onBeforeUnmount(() => {
  onMouseUp();
  composable.dispose();
  gitStatus.dispose();
  fileRestore.dispose();
  fileDiscardHunk.dispose();
  worktreesComposable.dispose();
  // Spec 2026-07-16: abort in-flight probe + init + clear polling
  // interval. Mirrors the worktree composable's dispose pattern.
  gitRepoProbe.dispose();
  gitStage.dispose();
  gitUnstage.dispose();
  gitCommit.dispose();
  gitRevert.dispose();
  gitIgnoreFileWrite.dispose();
  gitLog.dispose();
  // git-show composable holds per-SHA caches + inflight AbortControllers.
  // dispose() aborts in-flight requests and drops the maps; safe to
  // call after gitLog.dispose() since the two are independent.
  gitShow.dispose();
  // git-stats: abort in-flight refresh + clear ETag/snapshot maps.
  gitStats.dispose();
  if (persistCurrentPathTimer) {
    clearTimeout(persistCurrentPathTimer);
    persistCurrentPathTimer = null;
  }
  document.removeEventListener("mousedown", closeContextMenuOnOutside, true);
  document.removeEventListener("keydown", closeContextMenuOnEscape, true);
  document.removeEventListener("keydown", onFullscreenKeyDown);
  // Always restore body overflow on unmount. The watcher above already
  // does this whenever both modes become false; the explicit reset
  // covers the edge case where the sidebar closes while fullscreen is
  // still on (the watcher would otherwise leak the hidden overflow).
  document.body.style.overflow = "";
});

function toggleFile(path: string): void {
  const next = new Set(expandedSet.value);
  if (next.has(path)) next.delete(path);
  else next.add(path);
  expandedSet.value = next;
}

// ── Drag resize ────────────────────────────────────────────────────

const MIN_WIDTH = 320;
const MAX_WIDTH = 1800;
const DEFAULT_WIDTH = 800;

const sidebarWidth = ref(DEFAULT_WIDTH);
const sidebarRef = ref<HTMLElement | null>(null);
let isResizing = false;

function startResize(e: MouseEvent): void {
  e.preventDefault();
  isResizing = true;
  document.body.style.cursor = "ew-resize";
  document.body.style.userSelect = "none";
  document.addEventListener("mousemove", onMouseMove);
  document.addEventListener("mouseup", onMouseUp);
}

function onMouseMove(e: MouseEvent): void {
  if (!isResizing || !sidebarRef.value) return;
  // Use the sidebar's own right edge (not the parent's) as the
  // reference point. The flex layout places any siblings shown to
  // the right beyond `selfRect.right`, so the computed width is
  // automatically reduced by their combined width — same model
  // as ReasoningSidebar.
  const selfRect = sidebarRef.value.getBoundingClientRect();
  const newWidth = selfRect.right - e.clientX;
  sidebarWidth.value = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, newWidth));
}

function onMouseUp(): void {
  if (!isResizing) return;
  isResizing = false;
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  document.removeEventListener("mousemove", onMouseMove);
  document.removeEventListener("mouseup", onMouseUp);
}

const directoryPath = computed(() => {
  const s = composable.state.value;
  if (s.kind === "ok") return s.snapshot.meta.directory;
  if (s.kind === "error" && s.previousSnapshot)
    return s.previousSnapshot.meta.directory;
  return null;
});

const isTruncated = computed(() => {
  const s = composable.state.value;
  if (s.kind === "ok") return s.snapshot.meta.truncated;
  if (s.kind === "error" && s.previousSnapshot)
    return s.previousSnapshot.meta.truncated;
  return false;
});

const truncatedShown = computed(() => {
  const s = composable.state.value;
  if (s.kind === "ok") return s.snapshot.meta.truncatedAtBytes;
  if (s.kind === "error" && s.previousSnapshot)
    return s.previousSnapshot.meta.truncatedAtBytes;
  return 0;
});

const truncatedMax = computed(() => {
  const s = composable.state.value;
  if (s.kind === "ok") return s.snapshot.meta.maxBytes;
  if (s.kind === "error" && s.previousSnapshot)
    return s.previousSnapshot.meta.maxBytes;
  return 0;
});

// Root path for FileBrowserView: the active worktree, then the main
// worktree, then the loaded project's root directory. We pass this
// to FileBrowserView so it can render the breadcrumb. The projectRoot
// fallback ensures non-git projects still get a meaningful root for
// the breadcrumb (and a non-empty path for the file-browser fetch).
const currentRoot = computed<string | null>(() => {
  return selectedWorktree.value ?? mainWorktreePath.value ?? projectRoot.value;
});
</script>

<template>
  <!-- Global fullscreen escape: teleport the sidebar shell to <body>
       only while globalFullscreen is on. When disabled, Teleport is a
       transparent pass-through — the existing chat-panel layout
       (sidebar body → document-manager flex column) is unchanged.
       The .is-fullscreen class on the <aside> drives the fixed
       viewport styles in the scoped CSS below. -->
  <Teleport to="body" :disabled="!globalFullscreen">
    <transition name="slide-left">
      <aside
        v-if="modelValue"
        ref="sidebarRef"
        class="git-diff-sidebar"
        :class="{ resizing: isResizing, 'is-fullscreen': globalFullscreen }"
        :style="{ width: sidebarWidth + 'px' }"
      >
        <div class="git-diff-sidebar-resizer" @mousedown="startResize" />
        <div class="git-diff-sidebar-header">
          <div class="git-diff-sidebar-title-wrap">
            <span class="git-diff-sidebar-title">
              {{
                viewMode === "files"
                  ? tm("spcodeProjectLoad.fileBrowser.title")
                  : tm("spcodeProjectLoad.diffSidebar.title")
              }}
            </span>
            <!-- UI #5: directory path is now shown as a compact breadcrumb-style
               strip directly under the title, with an inline folder icon.
               This keeps the header row uncluttered (title + actions only)
               while still giving the user a visible project root in all
               three view modes (not just diff). -->
          </div>
          <div class="git-diff-sidebar-actions">
            <!-- 2026-07-18: the .gitignore entry moved from this header
                 into GitCommitBar (next to the stage/commit controls)
                 so users notice it as a Git-management setting. -->
            <!-- UI #5: refresh button dropped the `tonal` background and
               dropped to `variant="text"` + `size="small"` so the header
               reads as a lightweight toolbar instead of three chunky
               "circle" buttons. Loading state is preserved (a small
               spinner replaces the icon while the request is in flight). -->
            <v-tooltip location="bottom" :open-delay="200">
              <template #activator="{ props: tipProps }">
                <v-btn
                  v-bind="tipProps"
                  icon
                  size="small"
                  variant="text"
                  :loading="isFetching"
                  @click="onManualRefresh"
                >
                  <v-icon size="18">mdi-restart</v-icon>
                </v-btn>
              </template>
              {{ tm("spcodeProjectLoad.diffSidebar.refreshTooltip") }}
            </v-tooltip>
            <v-btn
              :icon="
                globalFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'
              "
              size="small"
              variant="text"
              :aria-pressed="globalFullscreen"
              :aria-label="
                tm(
                  globalFullscreen
                    ? 'spcodeProjectLoad.documentManager.fullscreen.exit'
                    : 'spcodeProjectLoad.documentManager.fullscreen.enter',
                )
              "
              :title="
                tm(
                  globalFullscreen
                    ? 'spcodeProjectLoad.documentManager.fullscreen.exit'
                    : 'spcodeProjectLoad.documentManager.fullscreen.enter',
                )
              "
              @click="toggleGlobalFullscreen"
            />
            <v-btn
              icon="mdi-close"
              size="small"
              variant="text"
              @click="emit('update:modelValue', false)"
            />
          </div>
        </div>

        <!-- UI #5: a fixed path strip directly under the header. Visible in
           all three view modes so the user always knows which project
           (and which worktree) they are looking at. Two-line layout:
             [folder] <project-root>           (top)
             <worktree> · <branch>             (bottom, only when in a
                                                non-main worktree)
           The strip is muted (low-contrast) so it doesn't compete with
           the title above or the diff content below. -->
        <div
          v-if="currentRoot"
          class="git-diff-sidebar-path-strip"
          :title="currentRoot"
        >
          <div class="git-diff-sidebar-path-line">
            <v-icon size="12" class="git-diff-sidebar-path-icon"
              >mdi-folder-outline</v-icon
            >
            <span class="git-diff-sidebar-path-text">{{ currentRoot }}</span>
          </div>
          <div
            v-if="selectedWorktree && worktreeList.length > 0"
            class="git-diff-sidebar-path-sub"
          >
            {{
              worktreeList.find((w) => w.path === selectedWorktree)?.branch ??
              tm("spcodeProjectLoad.diffSidebar.worktreeTabs.detachedBadge")
            }}
          </div>
        </div>

        <!-- View-mode tab (spec 2026-06-20 §5.2): Files / Diff.
           aria-label is hardcoded (per advisory R2) to avoid adding
           a 31st i18n key — the visible button text already conveys
           the purpose for sighted users. -->
        <div
          v-if="isGitRepo || showNotGitRepoChip"
          class="git-diff-sidebar-view-tabs"
          role="tablist"
          aria-label="Switch view"
        >
          <button
            type="button"
            role="tab"
            :aria-selected="viewMode === 'files'"
            :class="[
              'git-diff-sidebar-view-tab',
              { 'is-active': viewMode === 'files' },
            ]"
            @click="viewMode = 'files'"
          >
            <v-icon size="14">mdi-folder-outline</v-icon>
            <span>{{
              tm("spcodeProjectLoad.fileBrowser.viewMode.files")
            }}</span>
          </button>
          <!-- 2026-07-11 document-manager:Documents 文档管理 sub-tab。 -->
          <button
            type="button"
            role="tab"
            :aria-selected="viewMode === 'docs'"
            :aria-label="tm('spcodeProjectLoad.gitDiffSidebar.tabs.docs')"
            :class="[
              'git-diff-sidebar-view-tab',
              { 'is-active': viewMode === 'docs' },
            ]"
            @click="viewMode = 'docs'"
          >
            <v-icon size="14">mdi-file-document-multiple-outline</v-icon>
            <span>{{ tm("spcodeProjectLoad.gitDiffSidebar.tabs.docs") }}</span>
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="viewMode === 'diff'"
            :class="[
              'git-diff-sidebar-view-tab',
              { 'is-active': viewMode === 'diff' },
            ]"
            @click="viewMode = 'diff'"
          >
            <v-icon size="14">mdi-source-pull</v-icon>
            <span>{{ tm("spcodeProjectLoad.fileBrowser.viewMode.diff") }}</span>
          </button>
          <!-- Spec 2026-06-24 §2 决策 #10:History 是第 3 个 viewMode。 -->
          <button
            type="button"
            role="tab"
            :aria-selected="viewMode === 'history'"
            :aria-label="
              tm('spcodeProjectLoad.diffSidebar.gitWorkflow.history.tabAria')
            "
            :class="[
              'git-diff-sidebar-view-tab',
              { 'is-active': viewMode === 'history' },
            ]"
            @click="viewMode = 'history'"
          >
            <v-icon size="14">mdi-history</v-icon>
            <span>{{
              tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.tab")
            }}</span>
          </button>
        </div>

        <!-- Worktree tabs (visible in BOTH views, spec 2026-06-20 §5.3) -->
        <div
          v-if="hasMultipleWorktrees && (isGitRepo || showNotGitRepoChip)"
          class="git-diff-sidebar-tabs"
          role="tablist"
          :aria-label="
            tm('spcodeProjectLoad.diffSidebar.worktreeTabs.ariaLabel')
          "
        >
          <!-- Section label: clarifies that the buttons below switch
             worktrees (otherwise they look like generic pills with
             no obvious purpose). Anchored to the left of the flex row;
             existing flex-wrap still lets the tabs wrap to a new line
             on narrow widths. -->
          <span class="git-diff-sidebar-tabs-label">
            {{ tm("spcodeProjectLoad.diffSidebar.worktreeTabs.label") }}
          </span>
          <button
            v-for="wt in worktreeList"
            :key="wt.path"
            type="button"
            role="tab"
            :aria-selected="(selectedWorktree ?? mainWorktreePath) === wt.path"
            :class="[
              'git-diff-sidebar-tab',
              {
                'git-diff-sidebar-tab--active':
                  (selectedWorktree ?? mainWorktreePath) === wt.path,
                'git-diff-sidebar-tab--prunable': wt.prunable,
              },
            ]"
            :title="
              wt.prunable
                ? tm('spcodeProjectLoad.diffSidebar.worktreeTabs.prunableTooltip')
                : wt.path
            "
            @click="onWorktreeChange(wt.isMain ? null : wt.path)"
            @contextmenu.prevent="(e) => openContextMenu(e, wt)"
          >
            <v-icon v-if="wt.isMain" size="12" class="git-diff-sidebar-tab-icon"
              >mdi-home</v-icon
            >
            <v-icon
              v-else-if="wt.prunable"
              size="12"
              class="git-diff-sidebar-tab-icon git-diff-sidebar-tab-icon--prunable"
              >mdi-alert</v-icon
            >
            <v-icon
              v-else-if="wt.locked"
              size="12"
              class="git-diff-sidebar-tab-icon"
              >mdi-lock</v-icon
            >
            <span class="git-diff-sidebar-tab-label">
              {{
                wt.branch ??
                (wt.isMain
                  ? tm("spcodeProjectLoad.diffSidebar.worktreeTabs.mainBadge")
                  : wt.headSha.slice(0, 7))
              }}
            </span>
            <span v-if="wt.prunable" class="git-diff-sidebar-tab-badge git-diff-sidebar-tab-badge--prunable">{{
              tm("spcodeProjectLoad.diffSidebar.worktreeTabs.prunableBadge")
            }}</span>
            <span v-else-if="!wt.branch" class="git-diff-sidebar-tab-badge">{{
              tm("spcodeProjectLoad.diffSidebar.worktreeTabs.detachedBadge")
            }}</span>
          </button>
          <!-- Add button (spec 2026-06-27 §2.1) -->
          <button
            type="button"
            class="git-diff-sidebar-tab-add"
            :aria-label="
              tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.addButtonAria')
            "
            :title="tm('spcodeProjectLoad.diffSidebar.worktreeMgmt.addButton')"
            @click="openCreateDialog"
          >
            <v-icon size="14">mdi-plus</v-icon>
          </button>

          <!-- Context menu (spec 2026-06-27 §2.3)
                     Teleported to <body> and positioned with manual
                     `position: fixed` styles so the menu opens exactly at the
                     right-click cursor. Vuetify 3 v-menu's positioning pipeline
                     (position-x/y + connectedLocationStrategy) is unreliable
                     when the activator is a [x, y] tuple instead of an
                     HTMLElement; the menu consistently fell back to the top-
                     left corner of the viewport regardless of cursor position.
                     Manual positioning gives us deterministic behavior and a
                     single source of truth (contextMenuStyle computed). -->
          <Teleport to="body">
            <div
              v-if="contextMenu.open"
              ref="contextMenuEl"
              class="worktree-context-menu"
              :style="contextMenuStyle"
              role="menu"
              :aria-label="
                tm(
                  'spcodeProjectLoad.diffSidebar.worktreeMgmt.contextMenu.ariaLabel',
                )
              "
              @click.stop
              @contextmenu.prevent
            >
              <v-list density="compact">
                <template v-if="contextMenu.wt && !contextMenu.wt.isMain">
                  <!-- Lock/unlock toggle: never disabled. When the worktree
                             is locked this button reads "unlock" and the click
                             opens the unlock confirm dialog; when unlocked it
                             reads "lock" and opens the lock-reason dialog.
                             Disabling it when locked would prevent the very
                             action it represents. -->
                  <v-list-item @click="onLockClick(contextMenu.wt!)">
                    <template #prepend>
                      <v-icon>{{
                        contextMenu.wt.locked
                          ? "mdi-lock-open-variant"
                          : "mdi-lock"
                      }}</v-icon>
                    </template>
                    <v-list-item-title>{{
                      contextMenu.wt.locked
                        ? tm(
                            "spcodeProjectLoad.diffSidebar.worktreeMgmt.contextMenu.unlock",
                          )
                        : tm(
                            "spcodeProjectLoad.diffSidebar.worktreeMgmt.contextMenu.lock",
                          )
                    }}</v-list-item-title>
                  </v-list-item>
                  <!-- Remove: disabled only when locked (a locked worktree
                             must be unlocked before it can be removed). -->
                  <v-list-item
                    :disabled="!!contextMenu.wt.locked"
                    @click="onRemoveClick(contextMenu.wt!)"
                  >
                    <template #prepend>
                      <v-icon color="error">mdi-trash-can-outline</v-icon>
                    </template>
                    <v-list-item-title>{{
                      tm(
                        "spcodeProjectLoad.diffSidebar.worktreeMgmt.contextMenu.remove",
                      )
                    }}</v-list-item-title>
                  </v-list-item>
                </template>
                <template v-else>
                  <v-list-item disabled>
                    <v-list-item-title class="text-caption">
                      {{
                        tm(
                          "spcodeProjectLoad.diffSidebar.worktreeMgmt.contextMenu.mainDisabled",
                        )
                      }}
                    </v-list-item-title>
                  </v-list-item>
                </template>
              </v-list>
            </div>
          </Teleport>
        </div>

        <!-- Diff-only sub-UI: scope bar + truncation warning -->
        <template v-if="viewMode === 'diff'">
          <div
            class="git-diff-sidebar-scope"
            role="tablist"
            :aria-label="tm('spcodeProjectLoad.diffSidebar.scopeBar.ariaLabel')"
          >
            <div class="git-diff-sidebar-scope-pills">
              <button
                v-for="opt in SCOPE_OPTIONS"
                :key="opt.value"
                type="button"
                role="tab"
                :aria-selected="selectedScope === opt.value"
                :aria-label="tm(opt.labelKey)"
                :class="[
                  'git-diff-sidebar-scope-pill',
                  `is-${opt.value}`,
                  { 'is-active': selectedScope === opt.value },
                ]"
                :disabled="
                  !isProjectLoaded ||
                  (isScopeLoading && pendingScope !== opt.value)
                "
                @click="onScopeChange(opt.value)"
              >
                <v-icon size="14" class="git-diff-sidebar-scope-pill-icon">
                  {{ opt.icon }}
                </v-icon>
                <span class="git-diff-sidebar-scope-pill-text">
                  {{ tm(opt.labelKey) }}
                </span>
                <v-progress-circular
                  v-if="isScopeLoading && pendingScope === opt.value"
                  indeterminate
                  :size="12"
                  :width="2"
                  class="git-diff-sidebar-scope-pill-spinner"
                />
              </button>
            </div>
          </div>
          <div v-if="isTruncated" class="git-diff-sidebar-warning">
            {{
              tm("spcodeProjectLoad.diffSidebar.truncated", {
                shown: truncatedShown,
                max: truncatedMax,
              })
            }}
          </div>
        </template>

        <!-- Spec 2026-07-16: GitRepoInitPrompt + dismissed chip slot. The
             prompt occupies the full body area when shown; the chip
             floats above the body in dismissed mode so Files view
             (which does not need Git) stays usable. -->
        <GitRepoInitPrompt
          v-if="showRepoInitPrompt"
          :directory="
            gitRepoProbe.state.value.kind === 'not_a_git_repo'
              ? gitRepoProbe.state.value.directory
              : ''
          "
          :is-submitting="isRepoInitSubmitting"
          :last-error="repoInitLastError"
          @confirm="onRepoInitConfirm"
          @cancel="onRepoInitCancel"
        />
        <div
          v-else-if="showNotGitRepoChip"
          class="git-diff-sidebar-repo-chip"
          role="status"
        >
          <v-icon size="14">mdi-information-outline</v-icon>
          <span>{{ tm("spcodeProjectLoad.diffSidebar.repoInit.dismissedChip") }}</span>
          <button
            type="button"
            class="git-diff-sidebar-repo-chip-action"
            @click="repoPromptDismissed = false"
          >
            {{ tm("spcodeProjectLoad.diffSidebar.repoInit.reopenPrompt") }}
          </button>
        </div>

        <!-- Body: Files / Diff / History -->
        <div class="git-diff-sidebar-body">
          <!-- 2026-07-18 workspace-search-parity: the files-view search
             toolbar moved INTO FileBrowserView (mirroring
             DocumentManager) so it travels with the file-area
             fullscreen Teleport instead of being left behind in the
             sidebar. The body now renders FileBrowserView directly. -->
          <FileBrowserView
            v-if="viewMode === 'files'"
            ref="fileBrowserRef"
            :current-path="fileBrowserCurrentPath"
            :preview-path="fileBrowserPreviewPath"
            :is-dark="!!isDark"
            :root-path="currentRoot"
            :scroll-to-line="fileSearchScrollToLine"
            :umo="spcodeStatus.status.value.umo"
            :worktree="selectedWorktree"
            :git-log="gitLog"
            :git-show="gitShow"
            @navigate="onFileBrowserNavigate"
            @open-file="onFileOpen"
          />
          <GitDiffBodyContent
            v-else-if="viewMode === 'diff'"
            ref="gitDiffBodyRef"
            :state="diffBodyState"
            :expanded="expandedSet"
            :is-dark="!!isDark"
            :on-restore="onFileRestore"
            :selected-scope="selectedScope"
            :on-stage="onStageFile"
            :on-unstage="onUnstageFile"
            :is-staging="gitStage.isStaging"
            :is-unstaging="gitUnstage.isUnstaging"
            :new-file-paths="newFilePaths"
            :on-open-file="onOpenFile"
            :on-discard-hunk="onDiscardHunk"
            :discarding-hunks="fileDiscardHunk.isDiscardingHunk.value"
            @toggle="toggleFile"
            @retry="onManualRefresh"
            @restore="onFileRestore"
            @stage="onStageFile"
            @unstage="onUnstageFile"
            @open-file="onOpenFile"
            @stage-paths="onStagePaths"
            @unstage-paths="onUnstagePaths"
            @restore-paths="onRestorePaths"
          />
          <!-- Spec 2026-06-24 §6.5:History view 渲染 GitLogView。
             Spec 2026-06-25 §3.1:GitLogView 也接收 gitShow 句柄用于
             在 commit 展开时拉取 /spcode/git-show 并渲染变更文件列表。 -->
          <GitLogView
            v-else-if="viewMode === 'history'"
            :state="gitLog.state.value"
            :has-more="logHasMore"
            :is-loading="logIsLoading"
            :git-show="gitShow"
            :focused-commit-sha="focusedCommitSha"
            :git-stats="gitStats"
            v-model:stats-open="statsOpen"
            @apply="onLogApply"
            @reset="onLogReset"
            @load-more="onLogLoadMore"
            @refresh="onLogRefresh"
            @revert="onLogRevertRequest"
          />
          <!-- 2026-07-11 document-manager:Documents 文档管理 sub-tab body。 -->
          <!--
          2026-07-14: pass currentRoot (not projectRoot) to
          DocumentManager so the docs sub-page is rooted at the
          active worktree. The file-browser endpoint
          (/spcode/file-browser) is stateless and resolves
          whatever absolute path we hand it, so feeding it the
          worktree root is what makes the breadcrumb's "项目根"
          segment show the worktree path (e.g.
          F:/repo/.worktrees/feature-x) instead of always
          collapsing back to the main repo root. The docs CRUD
          composable (useSpcodeDocs) already pins writes to
          `:worktree` above, so the listing + writes now agree
          on which worktree is in scope. Mirrors what
          FileBrowserView has been doing for the workspace tab.
        -->
          <DocumentManager
            v-else-if="viewMode === 'docs'"
            :worktree="selectedWorktree"
            :umo="spcodeStatus.status.value.umo"
            :project-root="currentRoot"
            :is-dark="!!isDark"
            :git-log="gitLog"
            :git-show="gitShow"
          />
        </div>

        <!-- Spec §6.7:粘性 commit bar(diff 视图下显示)。
           移动端 spec §10 风险 #10:仍可见,按钮缩窄。 -->
        <GitCommitBar
          v-if="viewMode === 'diff' && isProjectLoaded"
          :staged-count="stagedCount"
          :unstaged-count="unstagedCount"
          :is-staging-all="gitStage.isStagingAll.value"
          :is-unstaging-all="gitUnstage.isUnstagingAll.value"
          :is-committing="gitCommit.isCommitting.value"
          :selected-scope="selectedScope"
          @stage-all="onClickStageAll"
          @unstage-all="onClickUnstageAll"
          @commit="onClickCommit"
          @open-gitignore="onOpenGitIgnoreEditor"
        />

        <!-- Spec §6.3: inline <v-dialog persistent> confirmation.
           Two guards against "stacking" / flicker:
             1. `v-if="confirmDialogOpen"` on v-card so the v-card
                is unmounted SYNCHRONOUSLY the instant the dialog
                starts closing. Without this, v-dialog's close
                transition keeps the v-card alive for several
                frames, during which `confirmTargetIsNew` may
                already have flipped to false and the v-card-text
                re-renders the *old* wording in place — perceived
                as a brief flash of the wrong message.
             2. `:key="confirmTargetPath ?? 'empty'"` on v-card so
                opening the dialog with a different path (or
                reopening after cancel) unmounts the previous
                v-card and mounts a fresh one. Avoids the
                in-place text swap flicker on open. -->
        <v-dialog v-model="confirmDialogOpen" persistent max-width="440">
          <v-card v-if="confirmDialogOpen" :key="confirmTargetPath ?? 'empty'">
            <v-card-title class="text-h6">
              {{ tm("spcodeProjectLoad.diffSidebar.restore.confirmTitle") }}
            </v-card-title>
            <v-card-text>
              {{
                tm(
                  confirmTargetIsNew
                    ? "spcodeProjectLoad.diffSidebar.restore.confirmMessageNewFile"
                    : "spcodeProjectLoad.diffSidebar.restore.confirmMessage",
                  {
                    path: confirmTargetPath ?? "",
                  },
                )
              }}
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="onCancelRestore">{{
                tm("spcodeProjectLoad.diffSidebar.restore.confirmCancel")
              }}</v-btn>
              <v-btn
                variant="flat"
                color="warning"
                :loading="restoringFile !== null"
                @click="onConfirmRestore"
                >{{
                  tm("spcodeProjectLoad.diffSidebar.restore.confirmAction")
                }}</v-btn
              >
            </v-card-actions>
          </v-card>
        </v-dialog>

        <!-- Bulk-restore confirmation: separate dialog so the message
           can include the file count and so a single Cancel cleanly
           aborts the whole batch (the underlying endpoint only
           accepts one file per request, so a partial-restore
           mid-flight would be confusing UX). Tinted `warning` to
           match the single-file dialog and signal irreversibility. -->
        <v-dialog v-model="confirmRestorePathsOpen" persistent max-width="440">
          <v-card>
            <v-card-title class="text-h6">
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.restore.confirmTitleMultiple",
                  { count: pendingRestorePaths.length },
                )
              }}
            </v-card-title>
            <v-card-text>
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.restore.confirmMessageMultiple",
                  { count: pendingRestorePaths.length },
                )
              }}
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn
                variant="text"
                :disabled="isBulkRestoring"
                @click="onCancelRestorePaths"
                >{{
                  tm("spcodeProjectLoad.diffSidebar.restore.confirmCancel")
                }}</v-btn
              >
              <v-btn
                variant="flat"
                color="warning"
                :loading="isBulkRestoring"
                @click="onConfirmRestorePaths"
                >{{
                  tm("spcodeProjectLoad.diffSidebar.restore.confirmAction")
                }}</v-btn
              >
            </v-card-actions>
          </v-card>
        </v-dialog>

        <!-- 2026-07-17 git-revert: History-view revert confirmation.
             The endpoint creates a NEW revert commit (no history
             rewrite) — the hint line spells that out plus the
             clean-worktree prerequisite. -->
        <v-dialog v-model="revertDialogOpen" persistent max-width="440">
          <v-card>
            <v-card-title class="text-h6">
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertConfirmTitle",
                )
              }}
            </v-card-title>
            <v-card-text>
              <div>
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertConfirmMessage",
                    {
                      sha: pendingRevert?.sha.slice(0, 7) ?? "",
                      subject: pendingRevert?.subject ?? "",
                    },
                  )
                }}
              </div>
              <div class="git-diff-sidebar__revert-hint">
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertConfirmHint",
                  )
                }}
              </div>
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="onCancelRevert">
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertConfirmCancel",
                  )
                }}
              </v-btn>
              <v-btn
                variant="flat"
                color="primary"
                :loading="gitRevert.isReverting.value"
                @click="onConfirmRevert"
              >
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.gitWorkflow.history.revertConfirmAction",
                  )
                }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <!-- Spec §6.3: 全部暂存确认弹窗(spec 2026-06-24 §3.3.3 + Q4)。 -->
        <v-dialog v-model="confirmStageAllOpen" persistent max-width="440">
          <v-card>
            <v-card-title class="text-h6">
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.gitWorkflow.stage.stageAll.confirmTitle",
                )
              }}
            </v-card-title>
            <v-card-text>
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.gitWorkflow.stage.stageAll.confirmMessage",
                  { count: pendingStageAllCount },
                )
              }}
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="onCancelStageAll">
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.gitWorkflow.stage.stageAll.confirmCancel",
                  )
                }}
              </v-btn>
              <v-btn
                variant="flat"
                color="primary"
                :loading="gitStage.isStagingAll.value"
                @click="onConfirmStageAll"
              >
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.gitWorkflow.stage.stageAll.confirmAction",
                  )
                }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <!-- Symmetric dialog for the staged scope's "取消全部暂存"
           bulk action. Mirrors confirmStageAllOpen in structure so
           the two flows feel identical from the user's POV — same
           persistent modal, same title/message/cancel/action layout,
           just routed through the unstage endpoint and tinted
           `warning` to signal the index-mutating direction. -->
        <v-dialog v-model="confirmUnstageAllOpen" persistent max-width="440">
          <v-card>
            <v-card-title class="text-h6">
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.gitWorkflow.unstage.unstageAll.confirmTitle",
                )
              }}
            </v-card-title>
            <v-card-text>
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.gitWorkflow.unstage.unstageAll.confirmMessage",
                  { count: pendingUnstageAllCount },
                )
              }}
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn variant="text" @click="onCancelUnstageAll">
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.gitWorkflow.unstage.unstageAll.confirmCancel",
                  )
                }}
              </v-btn>
              <v-btn
                variant="flat"
                color="warning"
                :loading="gitUnstage.isUnstagingAll.value"
                @click="onConfirmUnstageAll"
              >
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.gitWorkflow.unstage.unstageAll.confirmAction",
                  )
                }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <!-- Worktree CREATE dialog (spec 2026-06-27 §2.2.A) -->
        <WorktreeCreateDialog
          v-model="createDialogOpen"
          :is-submitting="isCreating"
          @submit="onCreateSubmit"
          @cancel="createDialogOpen = false"
        />

        <!-- Worktree REMOVE confirm dialog (spec 2026-06-27 §2.2.B) -->
        <v-dialog v-model="removeDialogOpen" persistent max-width="480">
          <v-card>
            <v-card-title class="text-h6">
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.confirmTitle",
                )
              }}
            </v-card-title>
            <v-card-text>
              <p class="mb-2">
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.confirmMessageWithPath",
                    {
                      path: removeDialogTarget?.path ?? "",
                      branch: removeDialogTarget?.branch ?? "",
                    },
                  )
                }}
              </p>
              <p
                v-if="dirtyCount !== null && dirtyCount > 0"
                class="text-caption text-warning mb-2"
              >
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.dirtyHint",
                    { count: dirtyCount },
                  )
                }}
              </p>
              <v-checkbox
                v-if="dirtyCount !== null && dirtyCount > 0"
                v-model="removeForceChecked"
                density="compact"
                :label="
                  tm(
                    'spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.force',
                    {
                      count: dirtyCount,
                    },
                  )
                "
                color="warning"
                hide-details
              />
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn
                variant="text"
                :disabled="isRemoving"
                @click="removeDialogOpen = false"
              >
                {{
                  tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.cancel")
                }}
              </v-btn>
              <v-btn
                variant="flat"
                color="warning"
                :loading="isRemoving"
                @click="onConfirmRemove(removeForceChecked)"
              >
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.worktreeMgmt.remove.confirm",
                  )
                }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <!-- Worktree LOCK dialog (spec 2026-06-27 §2.2.C) -->
        <v-dialog v-model="lockDialogOpen" persistent max-width="480">
          <LockReasonDialogBody
            v-if="lockDialogOpen"
            :target-branch="lockDialogTarget?.branch ?? null"
            :is-locking="isLocking"
            @submit="onLockSubmit"
            @cancel="lockDialogOpen = false"
          />
        </v-dialog>

        <!-- Worktree UNLOCK confirm dialog (spec 2026-06-27 §2.2.D) -->
        <v-dialog v-model="confirmUnlockOpen" persistent max-width="440">
          <v-card>
            <v-card-title class="text-h6">
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.confirmTitle",
                )
              }}
            </v-card-title>
            <v-card-text>
              {{
                tm(
                  "spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.confirmMessage",
                )
              }}
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn
                variant="text"
                :disabled="isUnlocking"
                @click="onCancelUnlock"
              >
                {{
                  tm("spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.cancel")
                }}
              </v-btn>
              <v-btn
                variant="flat"
                color="primary"
                :loading="isUnlocking"
                @click="onConfirmUnlock"
              >
                {{
                  tm(
                    "spcodeProjectLoad.diffSidebar.worktreeMgmt.unlock.confirm",
                  )
                }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>

        <!-- Spec §6.4: 提交弹窗。 -->
        <GitCommitDialog
          v-model="commitDialogOpen"
          :staged-files="Array.from(stagedFiles)"
          :is-committing="gitCommit.isCommitting.value"
          :last-error="commitLastError ?? undefined"
          :umo="spcodeStatus.status.value.umo"
          :worktree="selectedWorktree"
          @confirm="onConfirmCommit"
          @cancel="onCancelCommit"
        />

        <!-- 2026-07-17 gitignore-editor: full-sidebar overlay. Mounted
             as a direct child of the root so position:absolute inset:0
             covers header + body + commit bar alike. -->
        <GitIgnoreEditor
          v-if="gitIgnoreEditorOpen"
          :initial-content="gitIgnoreLoadedContent"
          :is-new-file="gitIgnoreIsNewFile"
          :is-saving="gitIgnoreFileWrite.isSaving.value"
          :save-error="gitIgnoreSaveError"
          :load-error="gitIgnoreLoadError"
          @save="onGitIgnoreSave"
          @cancel="onGitIgnoreCancel"
          @retry="loadGitIgnore"
        />

        <!-- Spec §6.4: result snackbar (扩展:支持 stderr <pre> 块)。 -->
        <v-snackbar
          v-model="snackbar.show"
          :color="snackbar.color"
          :timeout="snackbar.color === 'success' ? 4000 : 6000"
          location="bottom right"
          multi-line
        >
          <div v-if="snackbar.stderr" class="spcode-snackbar-stderr">
            <div class="spcode-snackbar-message">{{ snackbar.message }}</div>
            <pre class="spcode-snackbar-pre">{{ snackbar.stderr }}</pre>
          </div>
          <div v-else>{{ snackbar.message }}</div>
        </v-snackbar>
      </aside>
    </transition>
  </Teleport>
</template>

<style scoped>
/* 2026-07-17 git-revert: secondary hint line inside the revert
   confirmation dialog (explains the new-commit behavior). */
.git-diff-sidebar__revert-hint {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.git-diff-sidebar {
  /* Anchors the .gitignore-editor overlay's absolute inset:0. */
  position: relative;
  width: 420px;
  height: calc(100% - var(--chat-panel-top-offset, 0px));
  margin-top: var(--chat-panel-top-offset, 0px);
  /* Tokens (defined on .chat-ui in Chat.vue) keep borders & backgrounds in
     sync with chat's session list / ReasoningSidebar across light & dark. */
  border-left: 1px solid
    var(--chat-border, rgba(var(--v-theme-on-surface), 0.1));
  background: var(--chat-sidebar-bg, rgb(var(--v-theme-surface)));
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  position: relative;
}

/* Global workspace fullscreen: teleport's destination is fixed and
   fills the viewport. The inline width binding (user-resized sidebar)
   would otherwise cap us at the drag width, so it is overridden with
   !important. The high z-index sits above the chat layout (sidebar
   normally lives inside the chat-panel flex; teleporting to <body>
   removes that stacking context). */
.git-diff-sidebar.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1300;
  width: 100vw !important;
  height: 100vh;
  margin-top: 0;
  border-left: 0;
}

/* ── Drag handle ──────────────────────────────────────────────── */

.git-diff-sidebar-resizer {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--chat-border, rgba(var(--v-theme-on-surface), 0.1));
  cursor: ew-resize;
  z-index: 10;
  transition:
    width 0.15s ease,
    background 0.15s ease;
}

.git-diff-sidebar-resizer:hover,
.git-diff-sidebar-resizer:active {
  width: 6px;
  background: rgba(var(--v-theme-primary), 0.45);
}

/* ── Transition ───────────────────────────────────────────────── */

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.2s ease;
}

.slide-left-enter-from,
.slide-left-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* ── Header ───────────────────────────────────────────────────── */

.git-diff-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px 10px;
  gap: 8px;
}

.git-diff-sidebar-title-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.git-diff-sidebar-title {
  font-size: 15.5px;
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: 0.01em;
  color: rgb(var(--v-theme-on-surface));
}
/* UI #5: removed the inline folder icon + tooltip (`.git-diff-sidebar-dir*`)
   selectors — the project path is now rendered as a dedicated strip
   directly below the header (see .git-diff-sidebar-path-strip). Kept the
   dir selectors as no-op so any external style override (e.g. user
   CSS, devtools experiments) doesn't break the layout. */
.git-diff-sidebar-dir-icon {
  color: var(--chat-section-label, rgba(var(--v-theme-on-surface), 0.54));
}
.git-diff-sidebar-dir {
  font-size: 12px;
  color: var(--chat-muted, rgba(var(--v-theme-on-surface), 0.62));
}
.git-diff-sidebar-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

/* ── Path strip (UI #5) ──────────────────────────────────────────── */

.git-diff-sidebar-path-strip {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 0 14px 10px;
  /* Use chat's main font (no monospace) so the strip reads like
     a breadcrumb / status row, not a code path. */
  user-select: text;
}

.git-diff-sidebar-path-line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.git-diff-sidebar-path-icon {
  color: var(--chat-section-label, rgba(var(--v-theme-on-surface), 0.48));
  flex-shrink: 0;
}

.git-diff-sidebar-path-text {
  font-size: 12px;
  font-weight: 500;
  color: var(--chat-muted, rgba(var(--v-theme-on-surface), 0.62));
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  direction: rtl; /* keep the END (project root) visible on overflow */
  text-align: left;
}

.git-diff-sidebar-path-sub {
  font-size: 11px;
  color: var(--chat-section-label, rgba(var(--v-theme-on-surface), 0.48));
  margin-left: 18px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-feature-settings: "tnum";
}

/* ── View-mode tab (spec 2026-06-20 §5.2) ──────────────────── */
/* Pill-style segmented control. Aligned with chat's session list buttons
   (border-radius: 8px, smooth color transitions, no underlines). */
.git-diff-sidebar-view-tabs {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0 12px 8px;
  padding: 4px;
  border-radius: 10px;
  background: var(
    --chat-session-active-bg,
    rgba(var(--v-theme-on-surface), 0.06)
  );
}
.git-diff-sidebar-view-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 7px;
  border: 0;
  background: transparent;
  color: var(--chat-muted, rgba(var(--v-theme-on-surface), 0.62));
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition:
    background 0.14s ease,
    color 0.14s ease,
    box-shadow 0.14s ease;
}
.git-diff-sidebar-view-tab:hover {
  color: rgb(var(--v-theme-on-surface));
}
.git-diff-sidebar-view-tab.is-active {
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-primary));
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.git-diff-sidebar-view-tab:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

/* ── Scope bar (spec 2026-06-20 §2.1) ──────────────────────── */

.git-diff-sidebar-scope {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  /* Distinct from worktree tabs: a subtle filled strip that visually
     frames the segmented control as one cohesive filter unit. */
  background: rgba(var(--v-theme-on-surface), 0.035);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.git-diff-sidebar-scope-pills {
  display: flex;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.git-diff-sidebar-scope-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid transparent;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  flex: 1;
  min-width: 0;
  transition:
    background 0.12s ease,
    color 0.12s ease,
    border-color 0.12s ease,
    opacity 0.12s ease;
}

.git-diff-sidebar-scope-pill:hover:not(:disabled) {
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgb(var(--v-theme-on-surface));
}

.git-diff-sidebar-scope-pill:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.git-diff-sidebar-scope-pill:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.git-diff-sidebar-scope-pill.is-active {
  font-weight: 500;
}

/* Per-scope accent colors. Use theme tokens so the pills follow
   AstrBot's primary palette instead of hardcoded greens. Material's
   success token is intentionally absent in default Vuetify; we fall
   back to a 4caf50 default that is overridden by any theme that
   defines --v-theme-success. */
.git-diff-sidebar-scope-pill.is-unstaged.is-active {
  color: rgb(var(--v-theme-secondary));
  background: rgba(var(--v-theme-secondary), 0.14);
  border-color: rgba(var(--v-theme-secondary), 0.4);
}
.git-diff-sidebar-scope-pill.is-staged.is-active {
  color: rgb(var(--v-theme-success, #4caf50));
  background: rgba(var(--v-theme-success, #4caf50), 0.14);
  border-color: rgba(var(--v-theme-success, #4caf50), 0.4);
}
.git-diff-sidebar-scope-pill.is-all.is-active {
  color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.14);
  border-color: rgba(var(--v-theme-primary), 0.4);
}

.git-diff-sidebar-scope-pill-icon {
  color: inherit;
  flex-shrink: 0;
}

.git-diff-sidebar-scope-pill-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.git-diff-sidebar-scope-pill-spinner {
  flex-shrink: 0;
}

/* ── Worktree tabs (spec 2026-06-18 §3.4) ──────────────────── */

.git-diff-sidebar-tabs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px 14px 8px;
  border-bottom: 1px solid
    var(--chat-border, rgba(var(--v-theme-on-surface), 0.08));
}

/* Section label: small muted text that anchors the tab row to a
   clear purpose ("these pills switch worktrees"). `flex-shrink: 0`
   keeps it from being squeezed when the tabs wrap on narrow
   widths; when the row wraps, the label stays on its own line. */
.git-diff-sidebar-tabs-label {
  flex-shrink: 0;
  margin-right: 4px;
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--chat-section-label, rgba(var(--v-theme-on-surface), 0.48));
  user-select: none;
}

/* Pill shape, fully aligned with chat's chat-session-active-bg hover.
   Inactive state always shows a 1px hairline so the tab reads as a
   clickable button (a fully transparent outline looks like plain
   text). The border uses the chat-border token — it darkens slightly
   on hover and is replaced by a primary-tinted border on the active
   state. Switching the alpha (rather than toggling border on/off) keeps
   the layout perfectly stable across states. */
.git-diff-sidebar-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--chat-border, rgba(var(--v-theme-on-surface), 0.16));
  background: transparent;
  color: var(--chat-muted, rgba(var(--v-theme-on-surface), 0.62));
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition:
    background 0.14s ease,
    color 0.14s ease,
    border-color 0.14s ease;
  max-width: 180px;
}

.git-diff-sidebar-tab:hover {
  background: var(
    --chat-session-active-bg,
    rgba(var(--v-theme-on-surface), 0.06)
  );
  border-color: rgba(var(--v-theme-on-surface), 0.26);
  color: rgb(var(--v-theme-on-surface));
}

.git-diff-sidebar-tab--active {
  background: rgba(var(--v-theme-primary), 0.12);
  border-color: rgba(var(--v-theme-primary), 0.45);
  color: rgb(var(--v-theme-primary));
  font-weight: 500;
}

.git-diff-sidebar-tab-icon {
  color: inherit;
  flex-shrink: 0;
}

.git-diff-sidebar-tab-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Add button now matches the regular pill geometry (same 999px radius
   and same height), removing the dashed-circle orphan style. */
.git-diff-sidebar-tab-add {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  border: 1px solid var(--chat-border, rgba(var(--v-theme-on-surface), 0.18));
  background: transparent;
  color: var(--chat-muted, rgba(var(--v-theme-on-surface), 0.62));
  cursor: pointer;
  flex-shrink: 0;
  transition:
    background 0.14s ease,
    color 0.14s ease,
    border-color 0.14s ease;
}
.git-diff-sidebar-tab-add:hover {
  background: var(
    --chat-session-active-bg,
    rgba(var(--v-theme-on-surface), 0.06)
  );
  border-color: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-primary));
}
.git-diff-sidebar-tab-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.6);
  flex-shrink: 0;
}
.git-diff-sidebar-tab--prunable {
  border-color: rgba(255, 152, 0, 0.4);
  background: rgba(255, 152, 0, 0.08);
}
.git-diff-sidebar-tab-icon--prunable {
  color: rgb(255, 152, 0);
}
.git-diff-sidebar-tab-badge--prunable {
  background: rgba(255, 152, 0, 0.15);
  color: rgb(255, 152, 0);
}

@media (max-width: 760px) {
  .git-diff-sidebar-tab {
    font-size: 11px;
    padding: 3px 8px;
    max-width: 140px;
  }
  .git-diff-sidebar-tab-label {
    max-width: 90px;
  }
  /* Scope pills collapse to icons-only on narrow screens to keep the
     three pills balanced. Text is hidden because the icon + the
     pill's active color already communicate the choice. */
  .git-diff-sidebar-scope-pill {
    padding: 4px;
  }
  .git-diff-sidebar-scope-pill-text {
    display: none;
  }
}

/* ── Truncation warning ──────────────────────────────────────── */

.git-diff-sidebar-warning {
  padding: 8px 14px;
  background: rgba(255, 193, 7, 0.12);
  color: rgb(255, 152, 0);
  font-size: 12px;
  border-bottom: 1px solid rgba(255, 193, 7, 0.3);
}

/* ── Body ─────────────────────────────────────────────────────── */

.git-diff-sidebar-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 14px 12px;
}

/* ── Snackbar stderr block (spec §6.8) ─────────────────────────── */
.spcode-snackbar-stderr {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.spcode-snackbar-message {
  font-weight: 500;
  margin-bottom: 0;
}
.spcode-snackbar-pre {
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: inherit;
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 11px;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  margin: 0;
}

/* ── Dark mode refinements ──────────────────────────────────── */
/* Match the `.chat-ui.is-dark` token overrides defined in Chat.vue so
   the sidebar visually harmonizes with the rest of chat in dark mode:
   - hairline resizer is half-opacity (less aggressive on dark bg)
   - segmented control sits on the dark "active" surface
   - warning banner drops the harsh yellow border */
.chat-ui.is-dark .git-diff-sidebar-warning {
  background: rgba(255, 152, 0, 0.08);
  color: rgb(255, 167, 38);
  border-bottom-color: rgba(255, 152, 0, 0.25);
}
.chat-ui.is-dark .spcode-snackbar-pre {
  background: rgba(255, 255, 255, 0.06);
}

/* ── Mobile ───────────────────────────────────────────────────── */

@media (max-width: 760px) {
  .git-diff-sidebar {
    position: fixed;
    inset: 0;
    z-index: 1300;
    width: 100vw !important;
    height: 100dvh;
    margin-top: 0;
    border-left: 0;
  }
  .git-diff-sidebar-resizer {
    display: none;
  }
  .git-diff-sidebar-header {
    min-height: 52px;
    padding: calc(10px + env(safe-area-inset-top)) 12px 8px;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.12);
  }
  .git-diff-sidebar-body {
    padding: 0 12px calc(12px + env(safe-area-inset-bottom));
  }
}

/* Context menu wrapper teleported to <body>. The wrapper itself is
   hidden visually; only the inner v-list renders. We give it a small
   minimum width so the menu items have room for icon + text. Scoped
   styles work through Teleport because Vue rewrites the data-v hash
   selector on both sides of the portal. Two-layer elevation (a tight
   ambient blur + a wider drop) mirrors Vuetify elevation-12 and feels
   consistent with chat's menus & snackbars. */
.worktree-context-menu {
  min-width: 180px;
  max-width: 280px;
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  border: 1px solid var(--chat-border, rgba(var(--v-theme-on-surface), 0.08));
  box-shadow:
    0 1px 2px rgba(var(--v-theme-on-surface), 0.06),
    0 8px 24px rgba(0, 0, 0, 0.18);
  overflow: hidden;
}

/* Spec 2026-07-16: dismissed "not a Git project" chip. Floats above
   the body so the Files view (which does not need Git) remains
   usable. Matches the path-strip and view-tab strip's neutral
   surface treatment. */
.git-diff-sidebar-repo-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  font-size: 12px;
}
.git-diff-sidebar-repo-chip-action {
  margin-left: auto;
  background: none;
  border: none;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  font: inherit;
  padding: 0;
}
</style>
