<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.3
     Updated 2026-06-21 — draggable divider for left/right panes. -->
<script setup lang="ts">
import { computed, ref, onBeforeUnmount } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeFileBrowser } from "@/composables/useSpcodeFileBrowser";
import FileBrowserBreadcrumb from "./FileBrowserBreadcrumb.vue";
import FileBrowserEntryList from "./FileBrowserEntryList.vue";
import FileBrowserFilePreview from "./FileBrowserFilePreview.vue";

const props = defineProps<{
  currentPath: string;
  isDark?: boolean;
  /** Current worktree root (parent computes: selectedWorktree ?? mainWorktreePath). null = project not loaded. */
  rootPath: string | null;
}>();
const emit = defineEmits<{ (e: "navigate", path: string): void }>();

const { tm } = useModuleI18n("features/chat");
const spcodeStatus = useSpcodeProjectStatus();

const fileBrowserComposable = useSpcodeFileBrowser(
  computed(() => props.currentPath),
);

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
        :current-path="currentPath"
        :root-path="rootPath"
        @navigate="(p) => emit('navigate', p)"
      />

      <div ref="bodyRef" class="file-browser-body" :class="{ resizing: isResizing }">
              <FileBrowserEntryList
                class="file-browser-pane-left"
                :style="{ width: leftPanePercent + '%' }"
                :state="fileBrowserComposable.state.value"
                @navigate="(p) => emit('navigate', p)"
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

              <FileBrowserFilePreview
                class="file-browser-pane-right"
                :style="{ width: 100 - leftPanePercent + '%' }"
                :state="fileBrowserComposable.state.value"
                :is-dark="!!isDark"
                @navigate-target="(p) => emit('navigate', p)"
                @retry="() => fileBrowserComposable.refresh()"
              />
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