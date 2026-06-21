<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.3
     Updated 2026-06-21 — draggable divider + split dir/preview composables
     so the left pane keeps showing the parent directory while the right
     pane previews a file inside it. -->
<script setup lang="ts">
import { computed, ref, onBeforeUnmount } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeFileBrowser } from "@/composables/useSpcodeFileBrowser";
import type { SpcodeFileBrowserEntry } from "@/composables/parseSpcodeFileBrowser";
import FileBrowserBreadcrumb from "./FileBrowserBreadcrumb.vue";
import FileBrowserEntryList from "./FileBrowserEntryList.vue";
import FileBrowserFilePreview from "./FileBrowserFilePreview.vue";

const props = defineProps<{
  /** Directory whose entries are shown in the left pane. */
  currentPath: string;
  /** File path to preview in the right pane; null = show hint. */
  previewPath: string | null;
  isDark?: boolean;
  /** Current worktree root (parent computes: selectedWorktree ?? mainWorktreePath). null = project not loaded. */
  rootPath: string | null;
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
  (e: "navigate", payload: { dirPath: string; previewPath: string | null }): void;
}>();

const { tm } = useModuleI18n("features/chat");
const spcodeStatus = useSpcodeProjectStatus();

// Two independent composables so the directory listing stays in the
// left pane while the right pane shows a different (file) path.
// `dirComposable` always fetches `currentPath`; `previewComposable`
// only fetches when `previewPath` is non-empty (its watch has an
// empty-path short-circuit to avoid spurious path_not_found errors).
const dirComposable = useSpcodeFileBrowser(
  computed(() => props.currentPath),
);
const previewComposable = useSpcodeFileBrowser(
  computed(() => props.previewPath ?? ""),
);

// Breadcrumb path: when previewing a file, show the FILE'S path so
// the user can see "root / src / file.ts" in the breadcrumb instead
// of just "root / src". When browsing a directory, show currentPath.
const breadcrumbPath = computed<string>(() => props.previewPath ?? props.currentPath);

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
    emit("navigate", { dirPath: parentOf(entry.path), previewPath: entry.path });
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
  emit("navigate", { dirPath: parentOf(resolvedTarget), previewPath: resolvedTarget });
}

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
    <div v-if="!spcodeStatus.status.value.loaded" class="file-browser-empty">
      <v-icon size="36" color="grey">mdi-folder-open-outline</v-icon>
      <span class="empty-text">{{ tm("spcodeProjectLoad.fileBrowser.placeholder") }}</span>
    </div>

    <template v-else>
      <FileBrowserBreadcrumb
        :current-path="breadcrumbPath"
        :root-path="rootPath"
        @navigate="onBreadcrumbNavigate"
      />

      <div ref="bodyRef" class="file-browser-body" :class="{ resizing: isResizing }">
        <FileBrowserEntryList
          class="file-browser-pane-left"
          :style="{ width: leftPanePercent + '%' }"
          :state="dirComposable.state.value"
          :selected-path="previewPath"
          @navigate="onEntryNavigate"
        />

        <div
          class="file-browser-divider"
          role="separator"
          aria-orientation="vertical"
          :aria-valuenow="Math.round(leftPanePercent)"
          aria-valuemin="15"
          aria-valuemax="70"
          @mousedown="startResize"
        />

        <!-- Right pane: render the live preview only when a file is
             being previewed. When previewPath is null we show a
             static "select from left" hint instead — the
             previewComposable stays in idle state (its watch skips
             empty paths) and there's nothing useful to display. -->
        <FileBrowserFilePreview
          v-if="previewPath"
          class="file-browser-pane-right"
          :style="{ width: 100 - leftPanePercent + '%' }"
          :state="previewComposable.state.value"
          :is-dark="!!isDark"
          @navigate-target="onPreviewTargetNavigate"
          @retry="() => previewComposable.refresh()"
        />
        <div
          v-else
          class="file-browser-pane-right file-browser-preview-empty"
          :style="{ width: 100 - leftPanePercent + '%' }"
        >
          <v-icon size="32" color="grey">mdi-folder-open-outline</v-icon>
          <span class="preview-hint">
            {{ tm("spcodeProjectLoad.fileBrowser.preview.selectFromLeft") }}
          </span>
        </div>
      </div>
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
   resize handler so :style overrides any default flex-basis. */
.file-browser-pane-left {
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
  transition: background 0.15s ease, border-color 0.15s ease;
}
.file-browser-divider:hover,
.file-browser-divider:active {
  background: rgba(var(--v-theme-primary), 0.18);
  border-left-color: rgba(var(--v-theme-primary), 0.5);
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
.empty-text { font-size: 14px; }

/* Mobile: stack the two panes vertically. The divider becomes a
   thin horizontal bar; on touch devices there's no drag, so the
   hit target stays 6px high. */
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
}
</style>
