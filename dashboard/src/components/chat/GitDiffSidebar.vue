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
} from "@/composables/useSpcodeGitDiff";
import { useSpcodeWorktrees } from "@/composables/useSpcodeWorktrees";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeFileRestore, type RestoreResult } from "@/composables/useSpcodeFileRestore";
import { useModuleI18n } from "@/i18n/composables";
import GitDiffBodyContent from "@/components/chat/message_list_comps/GitDiffBodyContent.vue";
import FileBrowserView from "@/components/chat/message_list_comps/FileBrowserView.vue";
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
  fileBrowserCurrentPath: "astrbot.spcode.gitDiffSidebar.fileBrowserCurrentPath",
  selectedWorktree: "astrbot.spcode.gitDiffSidebar.selectedWorktree",
  selectedScope: "astrbot.spcode.gitDiffSidebar.selectedScope",
} as const;

function safeGetItem(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function safeSetItem(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* no-op */ }
}

function loadViewMode(): "files" | "diff" {
  const v = safeGetItem(STORAGE_KEYS.viewMode);
  return v === "files" || v === "diff" ? v : "files";
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
function validateCurrentPath(persisted: string | null, root: string | null): string {
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
// "files" shows <FileBrowserView>; "diff" shows <GitDiffBodyContent>.
// Default: "files" per spec §2 decision #10 (the more general view;
// first-time users likely want to "see what's in the project").
const viewMode = ref<"files" | "diff">(loadViewMode());
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

// Persist viewMode / selectedScope / selectedWorktree on every change.
// fileBrowserCurrentPath uses persistCurrentPath (300ms debounce).
watch(viewMode, (v) => safeSetItem(STORAGE_KEYS.viewMode, v), { flush: "post" });
watch(
  selectedScope,
  (v) => safeSetItem(STORAGE_KEYS.selectedScope, v),
  { flush: "post" },
);
watch(
  selectedWorktree,
  (v) => safeSetItem(
    STORAGE_KEYS.selectedWorktree,
    v === null ? "null" : v,
  ),
  { flush: "post" },
);

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
    // Validate selectedWorktree
    if (selectedWorktree.value && !wtList.some((w) => w.path === selectedWorktree.value)) {
      selectedWorktree.value = null;
    }
    // Validate currentPath against the (possibly new) root
    const root = selectedWorktree.value
      ?? wtList.find((w) => w.isMain)?.path
      ?? null;
    const validated = validateCurrentPath(fileBrowserCurrentPath.value, root);
    if (fileBrowserCurrentPath.value !== validated) {
      fileBrowserCurrentPath.value = validated;
    }
    // Preview path is transient and almost certainly invalid in a new
    // worktree context; clear it so the right pane shows the
    // "select from left" hint instead of a stale file.
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
watch(
  selectedWorktree,
  (newVal) => {
    const root = newVal ?? mainWorktreePath.value;
    if (root && fileBrowserCurrentPath.value !== root) {
      fileBrowserCurrentPath.value = root;
      persistCurrentPath(root);
    }
    fileBrowserPreviewPath.value = null;
  },
);

// Persist currentPath (debounced 300ms, spec §5.1 line 1357-1361).
// Empty path is skipped — we don't want to overwrite a valid persisted
// value with an empty string during the brief interval before the
// worktree-list watcher fires.
watch(
  fileBrowserCurrentPath,
  (newPath) => { if (newPath) persistCurrentPath(newPath); },
);

const composable = useSpcodeGitDiff(selectedWorktree, selectedScope);
const spcodeStatus = useSpcodeProjectStatus();
const expandedSet = ref<Set<string>>(new Set());

// ── file-restore (spec §3.2) ───────────────────────────────────────
// Composable instance lives at sidebar level so it can call
// composable.refresh() and reach the snackbar / dialog state.
const fileRestore = useSpcodeFileRestore();
const restoringFile = ref<string | null>(null);

// Confirm dialog state.
const confirmDialogOpen = ref(false);
const confirmTargetPath = ref<string | null>(null);

// Snackbar state (success / warning / error).
interface SnackbarState {
  show: boolean;
  message: string;
  color: "success" | "warning" | "error";
}
const snackbar = ref<SnackbarState>({ show: false, message: "", color: "success" });

// Maps a restore reason code to a snackbar message + color.
const RESTORE_REASON_I18N_KEYS: Record<string, { key: string; color: "warning" | "error" }> = {
  invalid_body: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.invalid_body", color: "error" },
  missing_file: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.missing_file", color: "error" },
  feature_disabled: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.feature_disabled", color: "error" },
  no_project_loaded: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.no_project_loaded", color: "error" },
  directory_missing: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.directory_missing", color: "error" },
  not_a_git_repo: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.not_a_git_repo", color: "error" },
  worktree_invalid: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.worktree_invalid", color: "error" },
  git_unavailable: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.git_unavailable", color: "error" },
  path_unsafe: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.path_unsafe", color: "error" },
  file_not_found: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.file_not_found", color: "error" },
  not_modified: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.not_modified", color: "warning" },
  untracked_file: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.untracked_file", color: "warning" },
  git_error: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.git_error", color: "error" },
  network: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.network", color: "error" },
  unknown: { key: "spcodeProjectLoad.diffSidebar.restore.error.reason.unknown", color: "error" },
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
    // reloads the workspace (directory listing + file preview); in
    // diff view it reloads the git diff data. The previous behavior
    // (always reload git diff) was a UX trap in files view — the
    // user could see the spinner but no visible data would change.
    if (viewMode.value === "files") {
      await fileBrowserRef.value?.refresh();
    } else {
      await composable.refresh();
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

// Spec: polling starts ONLY when the sidebar is open AND the user is
// viewing the Git Diff tab. The Files ("workspace") tab never polls —
// there's no diff data to refresh, and pulling it would be wasted
// network/CPU. We track both inputs in a single watcher so the
// polling lifecycle has one source of truth.
watch(
  [() => props.modelValue, viewMode],
  async ([open, mode]) => {
    const shouldPoll = open && mode === "diff";
    if (shouldPoll) {
      isFetching.value = true;
      try {
        await composable.refresh();
      } finally {
        isFetching.value = false;
      }
      // Re-check conditions after await: the user may have switched
      // tabs or closed the sidebar during the refresh. Starting
      // polling here without re-checking would leak a timer after
      // a tab switch (e.g. diff → files) or after the sidebar closes.
      if (props.modelValue && viewMode.value === "diff") {
        composable.startPolling(10_000);
      }
    } else {
      composable.stopPolling();
    }
  },
  { immediate: true },
);

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
  const result: RestoreResult = await fileRestore.restore({ file: path, worktree, umo });
  restoringFile.value = null;
  // Special-case "aborted" (Chunk 2 review note): no toast, just reset state.
  // This only fires during teardown (pre-mount guard / post-await unmount / axios cancel).
  if (!result.ok && result.reason === "aborted") {
    return;
  }
  if (result.ok) {
    snackbar.value = {
      show: true,
      message: tm("spcodeProjectLoad.diffSidebar.restore.success", { path }),
      color: "success",
    };
    // Spec §3.2: success -> immediate refresh so the row disappears.
    await composable.refresh();
  } else {
    const mapping = RESTORE_REASON_I18N_KEYS[result.reason] ?? RESTORE_REASON_I18N_KEYS.unknown;
    const message = mapping.key === "spcodeProjectLoad.diffSidebar.restore.error.reason.git_error"
      ? tm(mapping.key, { stderr: result.stderr ?? "" })
      : tm(mapping.key);
    snackbar.value = { show: true, message, color: mapping.color };
  }
}

onBeforeUnmount(() => {
  onMouseUp();
  composable.dispose();
  fileRestore.dispose();
  worktreesComposable.dispose();
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

// Root path for FileBrowserView: the active worktree (or main if none).
// We pass this to FileBrowserView so it can render the breadcrumb.
const currentRoot = computed<string | null>(() => {
  return selectedWorktree.value ?? mainWorktreePath.value;
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
            {{ viewMode === "files"
              ? tm("spcodeProjectLoad.fileBrowser.title")
              : tm("spcodeProjectLoad.diffSidebar.title") }}
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
                !isProjectLoaded || (isScopeLoading && pendingScope !== opt.value)
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

      <!-- Body: Files view OR Diff view -->
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
                  v-else
                  :state="composable.state.value"
                  :expanded="expandedSet"
                  :is-dark="!!isDark"
                  :on-restore="onFileRestore"
                  @toggle="toggleFile"
                  @retry="onManualRefresh"
                  @restore="onFileRestore"
                />
              </div>

              <!-- Spec §6.3: inline <v-dialog persistent> confirmation. -->
              <v-dialog
                v-model="confirmDialogOpen"
                persistent
                max-width="440"
              >
                <v-card>
                  <v-card-title class="text-h6">
                    {{ tm("spcodeProjectLoad.diffSidebar.restore.confirmTitle") }}
                  </v-card-title>
                  <v-card-text>
                    {{ tm("spcodeProjectLoad.diffSidebar.restore.confirmMessage", { path: confirmTargetPath ?? "" }) }}
                  </v-card-text>
                  <v-card-actions>
                    <v-spacer />
                    <v-btn
                      variant="text"
                      @click="onCancelRestore"
                    >{{ tm("spcodeProjectLoad.diffSidebar.restore.confirmCancel") }}</v-btn>
                    <v-btn
                      variant="flat"
                      color="warning"
                      :loading="restoringFile !== null"
                      @click="onConfirmRestore"
                    >{{ tm("spcodeProjectLoad.diffSidebar.restore.confirmAction") }}</v-btn>
                  </v-card-actions>
                </v-card>
              </v-dialog>

              <!-- Spec §6.4: result snackbar. -->
              <v-snackbar
                v-model="snackbar.show"
                :color="snackbar.color"
                :timeout="snackbar.color === 'success' ? 4000 : 6000"
                location="bottom right"
              >
                {{ snackbar.message }}
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
