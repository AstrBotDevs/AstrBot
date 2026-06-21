<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.4
     Updated 2026-06-21 — drop "back to parent" affordance; instead the
     parent directory stays mounted in this pane (driven by the
     dirComposable in FileBrowserView) and the currently-previewed file
     is highlighted via `selected-path`. -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { FileBrowserFetchState } from "@/composables/useSpcodeFileBrowser";
import type { SpcodeFileBrowserEntry } from "@/composables/parseSpcodeFileBrowser";

const props = defineProps<{
  state: FileBrowserFetchState;
  /** Path of the file currently being previewed in the right pane;
   *  used to highlight the matching entry in this list. */
  selectedPath: string | null;
}>();
// Emit the full entry (not just the path) so the parent can inspect
// `entry.type` and route correctly:
//   - directory: navigate to that directory, clear preview
//   - file / symlink: navigate to its parent, preview the path
// Emitting only the path would force the parent to re-look-up the
// entry by path from the current directory snapshot, which is racy
// if the snapshot changes between the click and the handler.
const emit = defineEmits<{ (e: "navigate", entry: SpcodeFileBrowserEntry): void }>();
const { tm } = useModuleI18n("features/chat");

const TYPE_ICONS: Record<SpcodeFileBrowserEntry["type"], { icon: string; color: string }> = {
  directory: { icon: "mdi-folder-outline", color: "info" },
  file: { icon: "mdi-file-document-outline", color: "grey" },
  symlink: { icon: "mdi-link-variant", color: "info" },
};

const entries = computed<SpcodeFileBrowserEntry[]>(() => {
  if (props.state.kind === "directory") return props.state.snapshot.entries;
  return [];
});

const truncated = computed<boolean>(() => {
  return props.state.kind === "directory" && props.state.snapshot.meta.truncated;
});

function handleClick(entry: SpcodeFileBrowserEntry): void {
  // Dangling symlink: click does nothing
  if (entry.type === "symlink" && entry.target_exists === false) return;
  emit("navigate", entry);
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}
</script>

<template>
  <div class="file-browser-entry-list">
    <div v-if="truncated" class="entry-list-warning">
      {{ tm("spcodeProjectLoad.fileBrowser.truncated") }}
    </div>

    <div v-if="entries.length === 0 && state.kind === 'directory'" class="file-browser-empty-dir">
      <v-icon size="24" color="grey">mdi-folder-open-outline</v-icon>
      <span>{{ tm("spcodeProjectLoad.fileBrowser.empty") }}</span>
    </div>

    <ul v-else-if="entries.length > 0" class="file-browser-entries">
      <li
        v-for="entry in entries"
        :key="entry.path"
        class="file-browser-entry"
        :class="{
          'is-symlink': entry.type === 'symlink',
          'is-dangling': entry.type === 'symlink' && entry.target_exists === false,
          'is-selected': entry.path === selectedPath,
        }"
        @click="handleClick(entry)"
      >
        <v-icon
          :icon="TYPE_ICONS[entry.type].icon"
          :color="TYPE_ICONS[entry.type].color"
          size="16"
        />
        <span class="entry-name">{{ entry.name }}</span>
        <span v-if="entry.type === 'symlink' && entry.target" class="entry-symlink-target">
          → {{ entry.target }}
        </span>
        <span class="entry-size">{{ formatSize(entry.size) }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.file-browser-entry-list {
  /* Width is now driven by FileBrowserView's draggable divider
     (sets `width` via inline style on .file-browser-pane-left, which
     this root element inherits as its wrapping class). We just
     need the internal scroll behavior + column flex. */
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
}
.entry-list-warning {
  padding: 8px 14px;
  font-size: 11.5px;
  color: rgba(var(--v-theme-warning), 1);
  background: rgba(var(--v-theme-warning), 0.08);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.file-browser-empty-dir {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 13px;
}
.file-browser-entries {
  list-style: none;
  margin: 0;
  padding: 4px 0;
}
.file-browser-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 14px;
  cursor: pointer;
  font-size: 12.5px;
  transition: background 0.1s, color 0.1s;
}
.file-browser-entry:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
/* Selected entry: the file currently being previewed in the right
   pane. Uses a subtle primary tint so it stays distinct from the
   hover state but doesn't compete with the file content's syntax
   highlighting. `is-selected` wins over `is-symlink` background
   because we want the selection cue to remain visible. */
.file-browser-entry.is-selected {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgba(var(--v-theme-on-surface), 0.95);
  font-weight: 500;
}
.file-browser-entry.is-selected:hover {
  background: rgba(var(--v-theme-primary), 0.18);
}
.file-browser-entry.is-selected::before {
  /* Thin accent bar on the left edge to make the selection obvious
     even when the file name is short and the row is wide. */
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: rgb(var(--v-theme-primary));
}
.file-browser-entries {
  position: relative; /* anchor for the ::before accent bar */
}
.file-browser-entry.is-dangling {
  opacity: 0.5;
  cursor: not-allowed;
}
.entry-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: ui-monospace, monospace;
}
.entry-symlink-target {
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 10.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 120px;
}
.entry-size {
  color: rgba(var(--v-theme-on-surface), 0.4);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
</style>
