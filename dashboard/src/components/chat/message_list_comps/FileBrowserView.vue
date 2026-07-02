<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.3
     Updated 2026-06-21 — draggable divider + split dir/preview composables
     so the left pane keeps showing the parent directory while the right
     pane previews a file inside it. -->
<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeFileBrowser } from "@/composables/useSpcodeFileBrowser";
import type { SpcodeFileBrowserEntry } from "@/composables/parseSpcodeFileBrowser";
import FileBrowserBreadcrumb from "./FileBrowserBreadcrumb.vue";
import FileBrowserEntryList from "./FileBrowserEntryList.vue";
import FileBrowserFilePreview from "./FileBrowserFilePreview.vue";
import SearchPanel from "./SearchPanel.vue";

const props = defineProps<{
  /** Directory whose entries are shown in the left pane. */
  currentPath: string;
  /** File path to preview in the right pane; null = show hint. */
  previewPath: string | null;
  isDark?: boolean;
  /** Current worktree root (parent computes: selectedWorktree ?? mainWorktreePath). null = project not loaded. */
  rootPath: string | null;
  /** When true, the search panel is mounted at the top of the view and replaces the file tree. */
  searchOpen?: boolean;
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
  (e: "update:searchOpen", v: boolean): void;
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

// Breadcrumb path: when previewing a file, show the FILE'S path so
// the user can see "root / src / file.ts" in the breadcrumb instead
// of just "root / src". When browsing a directory, show currentPath.
const breadcrumbPath = computed<string>(
  () => props.previewPath ?? props.currentPath,
);

/** Compute the parent directory of a path (POSIX + Windows separators). */
function parentOf(p: string): string {
  const isWindows = p.includes("\\");
  const lastSep = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  if (lastSep <= 0) return isWindows ? "\\" : "/";
  return p.slice(0, lastSep);
}

function onEntryNavigate(entry: SpcodeFileBrowserEntry): void {
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

function onBreadcrumbNavigate(path: string): void {
  // Clicking a breadcrumb segment always clears the preview — the
  // user is moving up the tree, not asking to keep the file open.
  emit("navigate", { dirPath: path, previewPath: null });
}

function onPreviewTargetNavigate(resolvedTarget: string): void {
  // Symlink "go to target": treat as a file click so the right pane
  // previews it; if the target is actually a directory, the
  // previewComposable will land on a directory state and the user
  // can then click the entry in the right pane to navigate into it.
  emit("navigate", {
    dirPath: parentOf(resolvedTarget),
    previewPath: resolvedTarget,
  });
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
const MIN_PERCENT = 15;
const MAX_PERCENT = 70;
const DEFAULT_PERCENT = 40;

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

onBeforeUnmount(() => {
  // If user is mid-drag when the sidebar unmounts, release cleanly.
  if (isResizing.value) onMouseUp();
  // Release BOTH composables. Without this, an AbortController
  // stays alive across re-mounts (e.g. toggling viewMode files ↔
  // diff), and the in-flight request can still write to a stale
  // `state` ref.
  dirComposable.dispose();
  previewComposable.dispose();
});
</script>

<template>
  <div class="file-browser-view">
    <SearchPanel
      v-if="props.searchOpen"
      :model-value="props.searchOpen"
      :worktree="props.worktree ?? null"
      :umo="props.umo ?? null"
      @update:model-value="emit('update:searchOpen', $event)"
      @open-file="emit('open-file', $event)"
    />
    <template v-if="!props.searchOpen">
      <div v-if="!spcodeStatus.status.value.loaded" class="file-browser-empty">
        <v-icon size="36" color="grey">mdi-folder-open-outline</v-icon>
        <span class="empty-text">{{
          tm("spcodeProjectLoad.fileBrowser.placeholder")
        }}</span>
      </div>

      <template v-else>
        <FileBrowserBreadcrumb
          :current-path="breadcrumbPath"
          :root-path="rootPath"
          @navigate="onBreadcrumbNavigate"
        />

        <div
          ref="bodyRef"
          class="file-browser-body"
          :class="{
            resizing: isResizing,
            'left-collapsed': isLeftPaneCollapsed,
          }"
        >
          <!-- Expand handle: only when collapsed. Placed FIRST in DOM
               order so it sits at the leftmost position in the flex
               row. Click to restore the left pane at its previous
               width (leftPanePercent ref is preserved across collapse). -->
          <button
            v-if="isLeftPaneCollapsed"
            type="button"
            class="file-browser-expand-handle"
            :title="tm('spcodeProjectLoad.fileBrowser.pane.expand')"
            :aria-label="tm('spcodeProjectLoad.fileBrowser.pane.expand')"
            @click="isLeftPaneCollapsed = false"
          >
            <v-icon size="16">mdi-chevron-double-right</v-icon>
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
            <FileBrowserEntryList
              :state="dirComposable.state.value"
              :selected-path="previewPath"
              @navigate="onEntryNavigate"
            />
            <button
              v-if="previewPath"
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
          <FileBrowserFilePreview
            v-if="previewPath"
            class="file-browser-pane-right"
            :style="
              isLeftPaneCollapsed ? {} : { width: 100 - leftPanePercent + '%' }
            "
            :state="previewComposable.state.value"
            :is-dark="!!isDark"
            :scroll-to-line="props.scrollToLine ?? null"
            @navigate-target="onPreviewTargetNavigate"
            @retry="() => previewComposable.refresh()"
          />
          <div
            v-else
            class="file-browser-pane-right file-browser-preview-empty"
            :style="
              isLeftPaneCollapsed ? {} : { width: 100 - leftPanePercent + '%' }
            "
          >
            <v-icon size="32" color="grey">mdi-folder-open-outline</v-icon>
            <span class="preview-hint">
              {{ tm("spcodeProjectLoad.fileBrowser.preview.selectFromLeft") }}
            </span>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.file-browser-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
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
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
/* Smooth width transition for collapse / expand. Suppressed during
   drag (`.resizing`) so mousemove updates don't lag behind the
   cursor. Also covers the divider + expand handle so the layout
   shifts as a single unit. */
.file-browser-pane-left,
.file-browser-pane-right,
.file-browser-divider,
.file-browser-expand-handle {
  transition:
    width 0.2s ease,
    flex-basis 0.2s ease,
    padding 0.2s ease;
}
.file-browser-body.resizing .file-browser-pane-left,
.file-browser-body.resizing .file-browser-pane-right,
.file-browser-body.resizing .file-browser-divider,
.file-browser-body.resizing .file-browser-expand-handle {
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
/* Expand handle: thin vertical strip at the leftmost edge of the
   body when the left pane is collapsed. Mirrors the divider's
   hover treatment so the affordance is discoverable. 24px gives
   a generous click target without being obtrusive. */
.file-browser-expand-handle {
  flex: 0 0 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.5);
  cursor: pointer;
  padding: 0;
  transition:
    background 0.1s ease,
    color 0.1s ease,
    border-color 0.1s ease;
}
.file-browser-expand-handle:hover,
.file-browser-expand-handle:focus-visible {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
  border-right-color: rgba(var(--v-theme-primary), 0.4);
  outline: none;
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
  /* On mobile, the collapse button is redundant (the user can
     already scroll the entry list out of view by scrolling the
     pane). Hide it to save vertical space. */
  .file-browser-collapse-btn,
  .file-browser-expand-handle {
    display: none;
  }
}
</style>
