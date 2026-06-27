<!-- Spec: docs/superpowers/specs/2026-06-17-chatui-git-diff-sidebar-design.md §4.2.3
     Updated 2026-06-22 — thread 'restore' event for file-restore button
     Updated 2026-06-28 — UI improvements batch:
       #1 directory grouping (collapsible per top-level dir)
       #2 summary bar (totals + dir count at the top)
       #3 expand-all / collapse-all + multi-select + stage/unstage selected
       #4 'all' view partition (staged vs unstaged as two segments)

     Grouping is purely visual: the flat `files` list is still the
     single source of truth, and `expanded` (per-file) is owned by
     the parent. The body content introduces 3 NEW local reactive
     collections (selectedFiles, collapsedGroups, groups) that never
     cross the parent boundary — they reset on viewMode / scope /
     worktree change thanks to the key prop on the <GitDiffBodyContent>
     element in GitDiffSidebar.vue. -->
<script setup lang="ts">
import { computed, ref, watch, type Ref } from "vue";
import type {
  GitDiffFetchState,
  GitDiffScope,
} from "@/composables/useSpcodeGitDiff";
import type { SpcodeGitDiffFile } from "@/composables/parseSpcodeGitDiff";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useModuleI18n } from "@/i18n/composables";
import GitDiffFileItem from "@/components/chat/message_list_comps/GitDiffFileItem.vue";

const { tm } = useModuleI18n("features/chat");

// ── Group / section data model ────────────────────────────────────

/** Top-level "section" rendered in the body. Two flavors:
 *    - kind='stage'  : a staged/unstaged partition (only in `all` scope)
 *    - kind='dir'    : a top-level-directory grouping (all other scopes)
 *  Sections are flat — there's no nesting in the current design.
 *  Each section has its own label, file list, and collapse state. */
interface DiffSection {
  id: string;
  label: string;
  /** Per-section stats: number of files and total +/− lines. */
  fileCount: number;
  additions: number;
  deletions: number;
  files: SpcodeGitDiffFile[];
  /** Visual badge kind: 'staged' / 'unstaged' / 'neutral'. Drives
   *  the small colored dot rendered next to the section label. */
  badgeKind: "staged" | "unstaged" | "neutral";
}

// ── Props & emits ─────────────────────────────────────────────────

const props = defineProps<{
  state: GitDiffFetchState;
  expanded: Set<string>;
  isDark: boolean;
  onRestore?: (path: string) => void;
  // Spec §6.2.3 + §6.2.4: parent (GitDiffSidebar) supplies the
  // scope + reactive Set<string> from useSpcodeGitStage / Unstage.
  // We pre-compute showStage / showUnstage booleans so the file item
  // stays scope-agnostic.
  selectedScope?: GitDiffScope;
  onStage?: (path: string) => void;
  onUnstage?: (path: string) => void;
  isStaging?: Ref<Set<string>>;
  isUnstaging?: Ref<Set<string>>;
  // Paths that should render as "new file" rows (teal accent + "新增
  // 文件" badge) instead of regular diff rows. Populated by GitDiffSidebar
  // from /spcode/git-status (scope=untracked | intent_to_add) when the
  // unstaged view is active. Pass-through prop so the body content stays
  // scope-agnostic (the merge happens at the sidebar level).
  newFilePaths?: ReadonlySet<string>;
  /** Passed through to GitDiffFileItem for the "view file" button. */
  onOpenFile?: (path: string) => void;
}>();
const emit = defineEmits<{
  (e: "toggle", path: string): void;
  (e: "retry"): void;
  (e: "restore", path: string): void;
  (e: "stage", path: string): void;
  (e: "unstage", path: string): void;
  (e: "open-file", path: string): void;
  // UI #3: bulk stage / unstage of multi-selected files. Parent
  // routes to gitStage.stage({ files }) / gitUnstage.unstage({ files })
  // which already accept an array. Emitted with the full path list
  // (NOT deltas) so the parent can refresh stagedFiles with the
  // authoritative server response.
  (e: "stage-paths", paths: string[]): void;
  (e: "unstage-paths", paths: string[]): void;
}>();

const spcodeStatus = useSpcodeProjectStatus();
// Spec §6.2.3: scope 派生按钮显隐(项目必须已加载 + scope=unstaged 显示 ↑)
const showStageButton = computed(() => {
  if (!props.onStage) return false;
  if (!spcodeStatus.status.value.loaded) return false;
  if (!spcodeStatus.status.value.umo) return false;
  return props.selectedScope === "unstaged";
});
const showUnstageButton = computed(() => {
  if (!props.onUnstage) return false;
  if (!spcodeStatus.status.value.loaded) return false;
  if (!spcodeStatus.status.value.umo) return false;
  return props.selectedScope === "staged";
});
// UI #3: bulk stage / unstage of selected files is only meaningful
// in the `unstaged` and `staged` scopes (every visible file is by
// definition in the matching state). In the `all` scope we don't
// know which is which without server-side per-file classification,
// so the bulk buttons stay hidden there. Per-file stage/unstage
// remains available on each row via GitDiffFileItem regardless.

function isStagingForPath(path: string): boolean {
  return props.isStaging?.value?.has(path) ?? false;
}
function isUnstagingForPath(path: string): boolean {
  return props.isUnstaging?.value?.has(path) ?? false;
}

const REASON_I18N_KEYS: Record<string, string> = {
  feature_disabled:
    "spcodeProjectLoad.diffSidebar.error.reason.feature_disabled",
  no_project_loaded:
    "spcodeProjectLoad.diffSidebar.error.reason.no_project_loaded",
  directory_missing:
    "spcodeProjectLoad.diffSidebar.error.reason.directory_missing",
  not_a_git_repo: "spcodeProjectLoad.diffSidebar.error.reason.not_a_git_repo",
  git_unavailable: "spcodeProjectLoad.diffSidebar.error.reason.git_unavailable",
  git_error: "spcodeProjectLoad.diffSidebar.error.reason.git_error",
};

function localizedReason(reason: string): string {
  const key = REASON_I18N_KEYS[reason];
  if (key) return tm(key);
  if (reason === "network")
    return tm("spcodeProjectLoad.diffSidebar.error.networkTitle");
  return tm("spcodeProjectLoad.diffSidebar.error.reason.generic", { reason });
}

const errorInfo = computed(() => {
  if (props.state.kind !== "error") return null;
  return {
    reason: props.state.reason,
    hasPrevious: !!props.state.previousSnapshot,
  };
});

const files = computed(() => {
  if (props.state.kind === "ok") return props.state.snapshot.files;
  if (props.state.kind === "error" && props.state.previousSnapshot) {
    return props.state.previousSnapshot.files;
  }
  return [];
});

// ── UI #2: Summary stats ──────────────────────────────────────────

const summary = computed(() => {
  const list = files.value;
  let adds = 0;
  let dels = 0;
  for (const f of list) {
    adds += f.additions;
    dels += f.deletions;
  }
  return {
    fileCount: list.length,
    additions: adds,
    deletions: dels,
    dirCount: uniqueTopLevelDirCount(list),
  };
});

function uniqueTopLevelDirCount(list: SpcodeGitDiffFile[]): number {
  const seen = new Set<string>();
  for (const f of list) seen.add(topLevelDir(f.path));
  return seen.size;
}

function topLevelDir(path: string): string {
  // Top-level directory: the first path segment. Files at the repo
  // root (no '/') get the literal "<root>" bucket so they group
  // together instead of spreading across the "/" bucket.
  const idx = path.indexOf("/");
  if (idx < 0) return "<root>";
  return path.slice(0, idx);
}

// ── UI #1: Directory grouping (and #4: 'all' scope partition) ────

/** The flat `files` list is reshaped into a list of sections, one
 *  per top-level directory, regardless of scope. Each section has
 *  its own collapse state stored in `collapsedGroups`. The `id`
 *  field is stable across re-renders (derived purely from scope +
 *  key) so collapsing/expanding state survives a refresh tick. */
const sections = computed<DiffSection[]>(() => {
  const list = files.value;
  if (list.length === 0) return [];
  // scope can be undefined when the parent hasn't wired it yet;
  // default to "unstaged" so the badge color matches the default state.
  return buildDirectorySections(list, props.selectedScope ?? "unstaged");
});

function buildDirectorySections(
  list: SpcodeGitDiffFile[],
  scope: GitDiffScope,
): DiffSection[] {
  // Bucket files by top-level dir, preserving the original order
  // (so directories that appear earlier in the diff show up first
  // in the section list — matches the existing flat list ordering).
  const buckets: { [key: string]: SpcodeGitDiffFile[] } = {};
  for (const f of list) {
    const dir = topLevelDir(f.path);
    (buckets[dir] ??= []).push(f);
  }
  const out: DiffSection[] = [];
  for (const dir of Object.keys(buckets)) {
    const slice = buckets[dir];
    let adds = 0;
    let dels = 0;
    for (const f of slice) {
      adds += f.additions;
      dels += f.deletions;
    }
    out.push({
      id: `dir:${dir}`,
      label: dir === "<root>" ? tm("spcodeProjectLoad.diffPreview.group.root") : dir,
      fileCount: slice.length,
      additions: adds,
      deletions: dels,
      files: slice,
      badgeKind:
        scope === "staged"
          ? "staged"
          : scope === "all"
            ? "neutral"
            : "unstaged",
    });
  }
  return out;
}

// ── UI #1: per-section collapse state ─────────────────────────────

const collapsedGroups = ref<Set<string>>(new Set());

function toggleGroup(id: string): void {
  const next = new Set(collapsedGroups.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  collapsedGroups.value = next;
}

function expandAll(): void {
  collapsedGroups.value = new Set();
  // Also expand every file row by emitting toggle for collapsed files.
  for (const f of files.value) {
    if (!props.expanded.has(f.path)) emit("toggle", f.path);
  }
}

function collapseAll(): void {
  collapsedGroups.value = new Set(sections.value.map((s) => s.id));
  // Also collapse every file row by emitting toggle for expanded files.
  for (const f of files.value) {
    if (props.expanded.has(f.path)) emit("toggle", f.path);
  }
}

// ── UI #3: multi-select state ─────────────────────────────────────

const selectedFiles = ref<Set<string>>(new Set());

function toggleSelect(path: string, next: boolean): void {
  const updated = new Set(selectedFiles.value);
  if (next) updated.add(path);
  else updated.delete(path);
  selectedFiles.value = updated;
}

function clearSelection(): void {
  if (selectedFiles.value.size === 0) return;
  selectedFiles.value = new Set();
}

// Reset selection whenever the scope changes (so checking files in
// the unstaged view doesn't carry over when the user switches to
// the staged view, where the same paths are no longer visible).
// We DON'T reset on worktree / project changes here because the
// parent re-mounts the component (via key=), which clears the ref.
watch(
  () => props.selectedScope,
  () => {
    selectedFiles.value = new Set();
  },
);

// Bulk stage / unstage of selected files: in the `unstaged` /
// `staged` scopes every visible file is in the matching state,
// so we pass the full selection through to the parent's bulk
// endpoint. The `all` scope hides these buttons entirely.
function onClickStageSelected(): void {
  const paths = Array.from(selectedFiles.value);
  if (paths.length === 0) return;
  emit("stage-paths", paths);
}
function onClickUnstageSelected(): void {
  const paths = Array.from(selectedFiles.value);
  if (paths.length === 0) return;
  emit("unstage-paths", paths);
}

function toggleGroupSelect(section: DiffSection, next: boolean): void {
  const updated = new Set(selectedFiles.value);
  for (const f of section.files) {
    if (next) updated.add(f.path);
    else updated.delete(f.path);
  }
  selectedFiles.value = updated;
}

function isSectionFullySelected(section: DiffSection): boolean {
  for (const f of section.files) {
    if (!selectedFiles.value.has(f.path)) return false;
  }
  return section.files.length > 0;
}

function isSectionPartiallySelected(section: DiffSection): boolean {
  let any = false;
  let all = true;
  for (const f of section.files) {
    if (selectedFiles.value.has(f.path)) any = true;
    else all = false;
    if (any && !all) return true;
  }
  return any && !all;
}
</script>

<template>
  <!-- Branch 1: loading -->
  <div v-if="state.kind === 'loading'" class="git-diff-center">
    <v-progress-circular indeterminate :size="32" />
    <span class="git-diff-center-text">{{
      tm("spcodeProjectLoad.diffSidebar.loading")
    }}</span>
  </div>

  <!-- Branch 2: error with no previous -->
  <div
    v-else-if="state.kind === 'error' && !state.previousSnapshot && errorInfo"
    class="git-diff-center"
  >
    <v-icon size="36" color="error">mdi-alert-circle-outline</v-icon>
    <div class="git-diff-error-title">
      {{ tm("spcodeProjectLoad.diffSidebar.error.loadFailedTitle") }}
    </div>
    <div class="git-diff-error-detail">
      {{ localizedReason(errorInfo.reason) }}
    </div>
    <v-btn size="small" color="primary" @click="emit('retry')">
      {{ tm("spcodeProjectLoad.diffSidebar.error.retry") }}
    </v-btn>
  </div>

  <!-- Branch 3 & 4: success (or success with stale error) -->
  <template
    v-else-if="
      state.kind === 'ok' || (state.kind === 'error' && state.previousSnapshot)
    "
  >
    <div v-if="files.length === 0" class="git-diff-center">
      <v-icon size="36" color="grey">mdi-check-circle-outline</v-icon>
      <span class="git-diff-center-text">{{
        tm("spcodeProjectLoad.diffSidebar.empty")
      }}</span>
    </div>

    <!-- UI #2: summary bar. Always rendered when there are files,
         so the user sees the overall magnitude of the diff without
         scrolling. Two-line layout on narrow viewports collapses
         via the .git-diff-summary-line flex-wrap. -->
    <div v-if="files.length > 0" class="git-diff-summary">
      <div class="git-diff-summary-line">
        <span class="git-diff-summary-count">
          {{
            tm("spcodeProjectLoad.diffPreview.summary.fileCount", {
              count: summary.fileCount,
              dirs: summary.dirCount,
            })
          }}
        </span>
        <span class="git-diff-summary-stats">
          <span class="git-diff-summary-add">+{{ summary.additions }}</span>
          <span class="git-diff-summary-del">−{{ summary.deletions }}</span>
        </span>
      </div>
    </div>

    <!-- UI #3: toolbar. Expand / collapse all + (when something is
         selected) the count + bulk stage / unstage buttons. Renders
         even when no items are selected so the user can find the
         "expand all" affordance. -->
    <div v-if="files.length > 0" class="git-diff-toolbar">
      <div class="git-diff-toolbar-group">
        <button
          type="button"
          class="git-diff-toolbar-btn"
          :title="tm('spcodeProjectLoad.diffPreview.toolbar.expandAll')"
          :aria-label="tm('spcodeProjectLoad.diffPreview.toolbar.expandAll')"
          @click="expandAll"
        >
          <v-icon size="14">mdi-unfold-more-horizontal</v-icon>
          <span>{{ tm("spcodeProjectLoad.diffPreview.toolbar.expandAll") }}</span>
        </button>
        <button
          type="button"
          class="git-diff-toolbar-btn"
          :title="tm('spcodeProjectLoad.diffPreview.toolbar.collapseAll')"
          :aria-label="tm('spcodeProjectLoad.diffPreview.toolbar.collapseAll')"
          @click="collapseAll"
        >
          <v-icon size="14">mdi-unfold-less-horizontal</v-icon>
          <span>{{ tm("spcodeProjectLoad.diffPreview.toolbar.collapseAll") }}</span>
        </button>
      </div>
      <div v-if="selectedFiles.size > 0" class="git-diff-toolbar-group">
        <span class="git-diff-toolbar-selected">
          {{
            tm("spcodeProjectLoad.diffPreview.toolbar.selectedCount", {
              count: selectedFiles.size,
            })
          }}
        </span>
        <button
          v-if="showStageButton"
          type="button"
          class="git-diff-toolbar-btn is-stage"
          :disabled="selectedFiles.size === 0"
          @click="onClickStageSelected"
        >
          <v-icon size="14">mdi-arrow-up-bold-circle-outline</v-icon>
          <span>{{
            tm("spcodeProjectLoad.diffPreview.toolbar.stageSelected", {
              count: selectedFiles.size,
            })
          }}</span>
        </button>
        <button
          v-if="showUnstageButton"
          type="button"
          class="git-diff-toolbar-btn is-unstage"
          :disabled="selectedFiles.size === 0"
          @click="onClickUnstageSelected"
        >
          <v-icon size="14">mdi-arrow-down-bold-circle-outline</v-icon>
          <span>{{
            tm("spcodeProjectLoad.diffPreview.toolbar.unstageSelected", {
              count: selectedFiles.size,
            })
          }}</span>
        </button>
        <button
          type="button"
          class="git-diff-toolbar-btn"
          :title="tm('spcodeProjectLoad.diffPreview.toolbar.clearSelection')"
          :aria-label="tm('spcodeProjectLoad.diffPreview.toolbar.clearSelection')"
          @click="clearSelection"
        >
          <v-icon size="14">mdi-close</v-icon>
        </button>
      </div>
    </div>

    <!-- UI #1: sections (top-level directory groups). Each section
         is a collapsible block; the header includes a per-section
         "select all" checkbox so the user can bulk-select within a
         group without using the toolbar's stage-selected action. -->
    <div
      v-for="section in sections"
      :key="section.id"
      class="git-diff-section is-dir"
      :class="[
        `is-${section.badgeKind}`,
        { 'is-collapsed': collapsedGroups.has(section.id) },
      ]"
    >
      <button
        type="button"
        class="git-diff-section-header"
        :aria-expanded="!collapsedGroups.has(section.id)"
        @click="toggleGroup(section.id)"
      >
        <v-icon
          size="14"
          class="git-diff-section-chevron"
          :class="{ expanded: !collapsedGroups.has(section.id) }"
        >
          mdi-chevron-right
        </v-icon>
        <!-- Section-level "select all" checkbox. Indeterminate state
             when some (but not all) files in the section are selected.
             Renders a real <input> so a11y is native (vs. our
             aria-checked button used in the file row). -->
        <span
          v-if="(showStageButton || showUnstageButton) && section.files.length > 0"
          class="git-diff-section-check"
          @click.stop
        >
          <input
            type="checkbox"
            :checked="isSectionFullySelected(section)"
            :indeterminate.prop="isSectionPartiallySelected(section)"
            :aria-label="
              tm('spcodeProjectLoad.diffPreview.toolbar.selectAllInGroup', { label: section.label })
            "
            @change="
              toggleGroupSelect(
                section,
                ($event.target as HTMLInputElement).checked,
              )
            "
          />
        </span>
        <span class="git-diff-section-dot" :class="`is-${section.badgeKind}`" />
        <span class="git-diff-section-label">{{ section.label }}</span>
        <span class="git-diff-section-meta">
          <span class="git-diff-section-count">{{ section.fileCount }}</span>
          <span class="git-diff-section-stats">
            <span class="git-diff-add">+{{ section.additions }}</span>
            <span class="git-diff-del">−{{ section.deletions }}</span>
          </span>
        </span>
      </button>
      <div v-show="!collapsedGroups.has(section.id)" class="git-diff-section-body">
        <GitDiffFileItem
          v-for="f in section.files"
          :key="f.path + ':' + f.status"
          :file="f"
          :expanded="expanded.has(f.path)"
          :is-dark="isDark"
          :on-restore="onRestore"
          :show-stage="showStageButton"
          :show-unstage="showUnstageButton"
          :on-stage="onStage"
          :on-unstage="onUnstage"
          :is-staging="isStagingForPath(f.path)"
          :is-unstaging="isUnstagingForPath(f.path)"
          :is-new-file="newFilePaths?.has(f.path) ?? false"
          :on-open-file="onOpenFile"
          :selectable="showStageButton || showUnstageButton"
          :is-selected="selectedFiles.has(f.path)"
          :selectable-aria-label="
            tm('spcodeProjectLoad.diffPreview.toolbar.selectFile', { path: f.path })
          "
          @toggle="emit('toggle', f.path)"
          @restore="emit('restore', $event)"
          @stage="emit('stage', $event)"
          @unstage="emit('unstage', $event)"
          @open-file="emit('open-file', $event)"
          @select="toggleSelect(f.path, $event)"
        />
      </div>
    </div>

    <div v-if="state.kind === 'error' && errorInfo" class="git-diff-banner-error">
      <span>{{ localizedReason(errorInfo.reason) }}</span>
      <button class="git-diff-banner-retry" @click="emit('retry')">
        {{ tm("spcodeProjectLoad.diffSidebar.error.retry") }}
      </button>
    </div>
  </template>

  <!-- Branch 5: idle (initial state, no fetch yet) -->
  <div v-else class="git-diff-center">
    <span class="git-diff-center-text">{{
      tm("spcodeProjectLoad.diffSidebar.loading")
    }}</span>
  </div>
</template>

<style scoped>
/* ── Summary bar (UI #2) ─────────────────────────────────────── */

.git-diff-summary {
  padding: 8px 14px 6px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.git-diff-summary-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  flex-wrap: wrap;
}

.git-diff-summary-count {
  color: rgba(var(--v-theme-on-surface), 0.65);
  font-weight: 500;
}

.git-diff-summary-stats {
  display: inline-flex;
  gap: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11.5px;
}

.git-diff-summary-add {
  color: rgb(46, 160, 67);
}
.git-diff-summary-del {
  color: rgb(248, 81, 73);
}

/* ── Toolbar (UI #3) ─────────────────────────────────────────── */

.git-diff-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  padding: 6px 14px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  background: rgba(var(--v-theme-on-surface), 0.02);
}

.git-diff-toolbar-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.git-diff-toolbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  font-family: inherit;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: pointer;
  transition:
    background 0.12s ease,
    color 0.12s ease,
    border-color 0.12s ease;
}

.git-diff-toolbar-btn:hover:not(:disabled) {
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgb(var(--v-theme-on-surface));
}

.git-diff-toolbar-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 1px;
}

.git-diff-toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.git-diff-toolbar-btn.is-stage {
  color: rgb(var(--v-theme-secondary));
}
.git-diff-toolbar-btn.is-stage:hover:not(:disabled) {
  background: rgba(var(--v-theme-secondary), 0.1);
}
.git-diff-toolbar-btn.is-unstage {
  color: rgb(255, 152, 0);
}
.git-diff-toolbar-btn.is-unstage:hover:not(:disabled) {
  background: rgba(255, 152, 0, 0.1);
}

.git-diff-toolbar-selected {
  font-size: 11.5px;
  color: rgb(var(--v-theme-primary));
  font-weight: 500;
  padding: 0 4px;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  margin-left: 4px;
}

/* ── Section / directory group (UI #1, UI #4) ─────────────────── */

.git-diff-section {
  /* Sections are visually flat blocks: only the header separates
     one from the next. The body is just a list of file rows. */
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}
.git-diff-section:last-of-type {
  border-bottom: 0;
}

.git-diff-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 14px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.75);
  background: rgba(var(--v-theme-on-surface), 0.025);
  border: 0;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  cursor: pointer;
  text-align: left;
  user-select: none;
  transition: background 0.12s ease;
}

.git-diff-section-header:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.git-diff-section-header:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}

.git-diff-section-chevron {
  color: rgba(var(--v-theme-on-surface), 0.5);
  flex-shrink: 0;
  transition: transform 0.15s ease;
}
.git-diff-section-chevron.expanded {
  transform: rotate(90deg);
}

.git-diff-section-check {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}
.git-diff-section-check input {
  cursor: pointer;
  width: 14px;
  height: 14px;
  margin: 0;
  accent-color: rgb(var(--v-theme-primary));
}

.git-diff-section-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.git-diff-section-dot.is-staged {
  background: rgba(76, 175, 80, 0.85);
}
.git-diff-section-dot.is-unstaged {
  background: rgba(var(--v-theme-secondary), 0.85);
}
.git-diff-section-dot.is-neutral {
  background: rgba(var(--v-theme-on-surface), 0.35);
}

.git-diff-section-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.git-diff-section-meta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  flex-shrink: 0;
}

.git-diff-section-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.07);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 10.5px;
}

.git-diff-section-stats {
  display: inline-flex;
  gap: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.git-diff-section-stats .git-diff-add {
  color: rgb(46, 160, 67);
}
.git-diff-section-stats .git-diff-del {
  color: rgb(248, 81, 73);
}

.git-diff-section-body {
  /* Inner file rows are rendered exactly as in the old flat layout;
     the section is just a visual wrapper. */
}

/* Sections in the `staged` scope get a small green left-border tint
   so the user can tell at a glance which scope they're in. Other
   scopes use the dot in the header as their visual cue. */
.git-diff-section.is-dir.is-staged {
  border-left: 2px solid rgba(76, 175, 80, 0.45);
}

/* ── Centered / loading / error states (unchanged) ──────────── */

.git-diff-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  text-align: center;
}

.git-diff-center-text {
  font-size: 13px;
}

.git-diff-error-title {
  font-size: 14px;
  font-weight: 600;
  color: rgb(var(--v-theme-error));
}
.git-diff-error-detail {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.git-diff-banner-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 14px;
  font-size: 12px;
  background: rgba(var(--v-theme-error), 0.08);
  color: rgb(var(--v-theme-error));
  border-top: 1px solid rgba(var(--v-theme-error), 0.2);
}

.git-diff-banner-retry {
  background: none;
  border: 0;
  color: inherit;
  font: inherit;
  text-decoration: underline;
  cursor: pointer;
}
</style>
