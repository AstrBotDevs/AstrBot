<!-- Author: elecvoid243, 2026-06-18
     Updated 2026-06-18 — worktree switcher (docs/superpowers/specs/2026-06-18-git-worktree-switcher-design.md)
     Updated 2026-06-20 — scope switcher (docs/superpowers/specs/2026-06-20-git-diff-scope-switcher-design.md)
     Layout mirrors ReasoningSidebar.vue so resizing the sidebar takes
     space from .chat-main (flex sibling) instead of overlaying it. -->
<script setup lang="ts">
import { ref, watch, onBeforeUnmount, computed, onMounted } from "vue";
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
import { useSpcodeWorktrees } from "@/composables/useSpcodeWorktrees";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import {
  useSpcodeFileRestore,
  type RestoreResult,
} from "@/composables/useSpcodeFileRestore";
import { useSpcodeGitStage } from "@/composables/useSpcodeGitStage";
import { useSpcodeGitUnstage } from "@/composables/useSpcodeGitUnstage";
import { useSpcodeGitCommit } from "@/composables/useSpcodeGitCommit";
import { useSpcodeGitLog, type LogFilter } from "@/composables/useSpcodeGitLog";
import { useSpcodeGitShow } from "@/composables/useSpcodeGitShow";
import { useSpcodeNewFileLineCounts } from "@/composables/useSpcodeNewFileLineCounts";
import { classifyReason } from "@/composables/parseSpcodeGitWorkflow";
import { useModuleI18n } from "@/i18n/composables";
import GitDiffBodyContent from "@/components/chat/message_list_comps/GitDiffBodyContent.vue";
import FileBrowserView from "@/components/chat/message_list_comps/FileBrowserView.vue";
import GitCommitBar from "@/components/chat/message_list_comps/GitCommitBar.vue";
import GitCommitDialog from "@/components/chat/message_list_comps/GitCommitDialog.vue";
import GitLogView from "@/components/chat/message_list_comps/GitLogView.vue";
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

function loadViewMode(): "files" | "diff" | "history" {
  const v = safeGetItem(STORAGE_KEYS.viewMode);
  // Spec §2 决策 #10:History 是第 3 个 viewMode,持久化时同样支持。
  if (v === "files" || v === "diff" || v === "history") return v;
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
// Default: "files" per spec §2 decision #10 (the more general view;
// first-time users likely want to "see what's in the project").
const viewMode = ref<"files" | "diff" | "history">(loadViewMode());
const fileBrowserCurrentPath = ref<string>(loadFileBrowserCurrentPath());
// fileBrowserPreviewPath is the file (if any) currently shown in the
// right pane. It is intentionally NOT persisted: when the user reloads
// the page we want the directory listing (persisted via currentPath),
// not an auto-reopened file. Cleared on worktree / project switches,
// breadcrumb clicks, and any directory navigation.
const fileBrowserPreviewPath = ref<string | null>(null);

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
const worktreeList = computed(() => {
  const s = worktreesComposable.state.value;
  if (s.kind !== "ok") return [];
  return s.snapshot.worktrees;
});
const hasMultipleWorktrees = computed(() => worktreeList.value.length > 1);
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
const projectRoot = computed(
  () => spcodeStatus.status.value.directory,
);

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
// git-show: per-commit file list (spec 2026-06-25). One composable
// instance shared by every expanded commit in GitLogView; the
// composable maintains a per-SHA cache internally, so re-expanding
// a previously seen commit is an ETag-validated no-op.
const gitShow = useSpcodeGitShow(selectedWorktree);

// Spec §3.4 决策 #22/#23:切 worktree 保留,切 project / unload 清空。
const stagedFiles = ref<Set<string>>(new Set<string>());

// Spec §3.3.3:confirm dialog for "Stage all"。
const confirmStageAllOpen = ref(false);
const pendingStageAllCount = ref(0);
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
const restoringFile = ref<string | null>(null);

// Confirm dialog state.
const confirmDialogOpen = ref(false);
const confirmTargetPath = ref<string | null>(null);

// Snackbar state (success / warning / error). Spec §5.3 / §6.8:stderr
// 单独字段,withStderr reason 携带,模板里 <pre> 块渲染。
interface SnackbarState {
  show: boolean;
  message: string;
  color: "success" | "warning" | "error";
  stderr?: string;
}
const snackbar = ref<SnackbarState>({
  show: false,
  message: "",
  color: "success",
});

function showSnackbar(
  message: string,
  color: "success" | "warning" | "error",
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
  untracked_file: {
    key: "spcodeProjectLoad.diffSidebar.restore.error.reason.untracked_file",
    color: "warning",
  },
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

const isProjectLoaded = computed(
  () => spcodeStatus.status.value.loaded === true,
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
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      worktreesComposable.startPolling(30_000);
    } else {
      worktreesComposable.stopPolling();
    }
  },
  { immediate: true },
);

// Spec: polling starts ONLY when the sidebar is open AND the user is
// viewing the Git Diff tab. The Files ("workspace") tab never polls —
// there's no diff data to refresh, and pulling it would be wasted
// network/CPU. History tab has its own 10s polling on useSpcodeGitLog.
// We track both inputs in a single watcher so the polling lifecycle
// has one source of truth.
watch(
  [() => props.modelValue, viewMode],
  async ([open, mode]) => {
    const isDiff = mode === "diff";
    const isHistory = mode === "history";
    if (open && isDiff) {
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
      // tabs or closed the sidebar during the refresh. Starting
      // polling here without re-checking would leak a timer after
      // a tab switch (e.g. diff → files) or after the sidebar closes.
      if (props.modelValue && viewMode.value === "diff") {
        composable.startPolling(10_000);
        // git-status polling rides on the same cadence so the
        // "new files" section stays in sync with diff changes.
        gitStatus.startPolling(10_000);
      }
      gitLog.stopPolling();
    } else if (open && isHistory) {
      // History view polls gitLog instead of gitDiff.
      isFetching.value = true;
      try {
        await gitLog.refresh();
      } finally {
        isFetching.value = false;
      }
      if (props.modelValue && viewMode.value === "history") {
        gitLog.startPolling(10_000);
      }
      composable.stopPolling();
      gitStatus.stopPolling();
      gitLog.stopPolling();
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
  selectedWorktree.value = path;
  selectedScope.value = DEFAULT_SCOPE;
  pendingScope.value = null;
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
}

// Spec §3.2 data flow: GitDiffFileItem -> GitDiffBodyContent -> here.
function onFileRestore(path: string): void {
  confirmTargetPath.value = path;
  confirmDialogOpen.value = true;
}

function onCancelRestore(): void {
  confirmDialogOpen.value = false;
  confirmTargetPath.value = null;
}

async function onConfirmRestore(): Promise<void> {
  const path = confirmTargetPath.value;
  if (!path) return;
  confirmDialogOpen.value = false;
  confirmTargetPath.value = null;
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
    await composable.refresh();
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
function onLogLoadMore(): void {
  void gitLog.loadMore();
}

onBeforeUnmount(() => {
  onMouseUp();
  composable.dispose();
  gitStatus.dispose();
  fileRestore.dispose();
  worktreesComposable.dispose();
  gitStage.dispose();
  gitUnstage.dispose();
  gitCommit.dispose();
  gitLog.dispose();
  // git-show composable holds per-SHA caches + inflight AbortControllers.
  // dispose() aborts in-flight requests and drops the maps; safe to
  // call after gitLog.dispose() since the two are independent.
  gitShow.dispose();
  if (persistCurrentPathTimer) {
    clearTimeout(persistCurrentPathTimer);
    persistCurrentPathTimer = null;
  }
});

function toggleFile(path: string): void {
  const next = new Set(expandedSet.value);
  if (next.has(path)) next.delete(path);
  else next.add(path);
  expandedSet.value = next;
}

// ── Drag resize ────────────────────────────────────────────────────

const MIN_WIDTH = 320;
const MAX_WIDTH = 1200;
const DEFAULT_WIDTH = 420;

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
  // Sidebar sits on the right side of the flex parent (.chat-ui).
  // Distance from the parent's right edge to the cursor equals the
  // new width. Dragging the cursor left therefore grows the sidebar
  // and squeezes the chat panel — same model as ReasoningSidebar.
  const parent = sidebarRef.value.parentElement;
  if (!parent) return;
  const newWidth = parent.getBoundingClientRect().right - e.clientX;
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
  <transition name="slide-left">
    <aside
      v-if="modelValue"
      ref="sidebarRef"
      class="git-diff-sidebar"
      :class="{ resizing: isResizing }"
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
          <v-tooltip
            v-if="viewMode === 'diff' && directoryPath"
            location="bottom"
            :open-delay="200"
          >
            <template #activator="{ props: tipProps }">
              <v-icon
                v-bind="tipProps"
                size="14"
                class="git-diff-sidebar-dir-icon"
                >mdi-folder-outline</v-icon
              >
            </template>
            <span class="git-diff-sidebar-dir">{{ directoryPath }}</span>
          </v-tooltip>
        </div>
        <div class="git-diff-sidebar-actions">
          <!-- Tooltip wraps the button (NOT the other way around).
               v-tooltip inside v-btn with activator="parent" is a
               known Vuetify-3 anti-pattern that interferes with the
               button's internal icon slot — the icon then fails to
               render and only the tonal background "circle" remains
               visible. Using #activator + v-bind="tipProps" is the
               standard pattern across this codebase (see
               GitDiffChip.vue). mdi-restart reads as a more elegant
               single-arc refresh glyph than mdi-refresh's chunky
               stem; semantics ("do it again from scratch") are
               appropriate for both view modes. -->
          <v-tooltip location="bottom" :open-delay="200">
            <template #activator="{ props: tipProps }">
              <v-btn
                v-bind="tipProps"
                icon
                size="small"
                variant="tonal"
                color="primary"
                :loading="isFetching"
                @click="onManualRefresh"
              >
                <v-icon size="18">mdi-restart</v-icon>
              </v-btn>
            </template>
            {{ tm("spcodeProjectLoad.diffSidebar.refreshTooltip") }}
          </v-tooltip>
          <v-btn
            icon="mdi-close"
            size="small"
            variant="text"
            @click="emit('update:modelValue', false)"
          />
        </div>
      </div>

      <!-- View-mode tab (spec 2026-06-20 §5.2): Files / Diff.
           aria-label is hardcoded (per advisory R2) to avoid adding
           a 31st i18n key — the visible button text already conveys
           the purpose for sighted users. -->
      <div
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
          <span>{{ tm("spcodeProjectLoad.fileBrowser.viewMode.files") }}</span>
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
        v-if="hasMultipleWorktrees"
        class="git-diff-sidebar-tabs"
        role="tablist"
        :aria-label="tm('spcodeProjectLoad.diffSidebar.worktreeTabs.ariaLabel')"
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
            },
          ]"
          :title="wt.path"
          @click="onWorktreeChange(wt.isMain ? null : wt.path)"
        >
          <v-icon v-if="wt.isMain" size="12" class="git-diff-sidebar-tab-icon"
            >mdi-home</v-icon
          >
          <span class="git-diff-sidebar-tab-label">
            {{
              wt.branch ??
              (wt.isMain
                ? tm("spcodeProjectLoad.diffSidebar.worktreeTabs.mainBadge")
                : wt.headSha.slice(0, 7))
            }}
          </span>
          <span v-if="!wt.branch" class="git-diff-sidebar-tab-badge">{{
            tm("spcodeProjectLoad.diffSidebar.worktreeTabs.detachedBadge")
          }}</span>
        </button>
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

      <!-- Body: Files / Diff / History -->
      <div class="git-diff-sidebar-body">
        <FileBrowserView
          v-if="viewMode === 'files'"
          ref="fileBrowserRef"
          :current-path="fileBrowserCurrentPath"
          :preview-path="fileBrowserPreviewPath"
          :is-dark="!!isDark"
          :root-path="currentRoot"
          @navigate="onFileBrowserNavigate"
        />
        <GitDiffBodyContent
          v-else-if="viewMode === 'diff'"
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
          @toggle="toggleFile"
          @retry="onManualRefresh"
          @restore="onFileRestore"
          @stage="onStageFile"
          @unstage="onUnstageFile"
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
          @apply="onLogApply"
          @load-more="onLogLoadMore"
          @refresh="() => gitLog.refresh()"
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
      />

      <!-- Spec §6.3: inline <v-dialog persistent> confirmation. -->
      <v-dialog v-model="confirmDialogOpen" persistent max-width="440">
        <v-card>
          <v-card-title class="text-h6">
            {{ tm("spcodeProjectLoad.diffSidebar.restore.confirmTitle") }}
          </v-card-title>
          <v-card-text>
            {{
              tm("spcodeProjectLoad.diffSidebar.restore.confirmMessage", {
                path: confirmTargetPath ?? "",
              })
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

      <!-- Spec §6.4: 提交弹窗。 -->
      <GitCommitDialog
        v-model="commitDialogOpen"
        :staged-files="Array.from(stagedFiles)"
        :is-committing="gitCommit.isCommitting.value"
        :last-error="commitLastError ?? undefined"
        @confirm="onConfirmCommit"
        @cancel="onCancelCommit"
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
</template>

<style scoped>
.git-diff-sidebar {
  width: 420px;
  height: 100%;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  position: relative;
}

/* ── Drag handle ──────────────────────────────────────────────── */

.git-diff-sidebar-resizer {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: ew-resize;
  z-index: 10;
  transition: background 0.15s ease;
}

.git-diff-sidebar-resizer:hover,
.git-diff-sidebar-resizer:active {
  background: rgba(var(--v-theme-primary), 0.2);
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
  padding: 14px 16px 8px;
}

.git-diff-sidebar-title-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}
.git-diff-sidebar-title {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
}
.git-diff-sidebar-dir-icon {
  color: rgba(var(--v-theme-on-surface), 0.54);
}
.git-diff-sidebar-dir {
  font-family: monospace;
  font-size: 12px;
}
.git-diff-sidebar-actions {
  display: flex;
  gap: 4px;
}

/* ── View-mode tab (spec 2026-06-20 §5.2) ──────────────────── */

.git-diff-sidebar-view-tabs {
  display: flex;
  gap: 0;
  padding: 0 14px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.git-diff-sidebar-view-tab {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 12.5px;
  font-family: inherit;
  cursor: pointer;
  margin-bottom: -1px;
  transition:
    color 0.12s ease,
    border-color 0.12s ease;
}
.git-diff-sidebar-view-tab:hover {
  color: rgba(var(--v-theme-on-surface), 0.85);
}
.git-diff-sidebar-view-tab.is-active {
  color: rgb(var(--v-theme-primary));
  border-bottom-color: rgb(var(--v-theme-primary));
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

/* Per-scope accent colors (visual gradient: blue → green → purple,
   suggesting "coverage broadens left-to-right"). */
.git-diff-sidebar-scope-pill.is-unstaged.is-active {
  color: rgb(var(--v-theme-secondary));
  background: rgba(var(--v-theme-secondary), 0.14);
  border-color: rgba(var(--v-theme-secondary), 0.4);
}
.git-diff-sidebar-scope-pill.is-staged.is-active {
  color: rgb(76, 175, 80);
  background: rgba(76, 175, 80, 0.14);
  border-color: rgba(76, 175, 80, 0.4);
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
  gap: 6px 4px;
  padding: 8px 14px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
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
  color: rgba(var(--v-theme-on-surface), 0.55);
  user-select: none;
}

.git-diff-sidebar-tab {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.18);
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition:
    background 0.12s ease,
    color 0.12s ease,
    border-color 0.12s ease;
  max-width: 180px;
}

.git-diff-sidebar-tab:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
  color: rgb(var(--v-theme-on-surface));
}

.git-diff-sidebar-tab--active {
  background: rgba(var(--v-theme-primary), 0.12);
  border-color: rgba(var(--v-theme-primary), 0.4);
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

.git-diff-sidebar-tab-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.6);
  flex-shrink: 0;
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
  padding: 8px 16px;
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
  background: rgba(0, 0, 0, 0.2);
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

/* ── Mobile ───────────────────────────────────────────────────── */

@media (max-width: 760px) {
  .git-diff-sidebar {
    position: fixed;
    inset: 0;
    z-index: 1300;
    width: 100vw !important;
    height: 100dvh;
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
</style>
