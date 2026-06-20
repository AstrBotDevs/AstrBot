<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.4 -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { FileBrowserFetchState } from "@/composables/useSpcodeFileBrowser";
import type { SpcodeFileBrowserEntry } from "@/composables/parseSpcodeFileBrowser";

const props = defineProps<{
  state: FileBrowserFetchState;
}>();
const emit = defineEmits<{ (e: "navigate", path: string): void }>();
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

/**
 * Parent path of the currently-viewed file/symlink. When the user
 * opens a file, the directory entries disappear from the left pane
 * (since state becomes "file"). Without an alternative affordance
 * the left pane would be empty and the user would have to use the
 * breadcrumb at the top to navigate back — which is more clicks and
 * less discoverable. This computed powers a single "← parent"
 * affordance shown at the top of the left pane while a file is open.
 */
const currentFilePath = computed<string | null>(() => {
  if (props.state.kind === "file" || props.state.kind === "symlink") {
    return props.state.snapshot.meta.path;
  }
  return null;
});

const parentPath = computed<string | null>(() => {
  const p = currentFilePath.value;
  if (!p) return null;
  const isWindows = p.includes("\\");
  const sep = isWindows ? "\\" : "/";
  const lastSep = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  if (lastSep <= 0) return null;
  return p.slice(0, lastSep);
});

const parentName = computed<string>(() => {
  const p = parentPath.value;
  if (!p) return "/";
  const sep = p.includes("\\") ? "\\" : "/";
  return p.slice(p.lastIndexOf(sep) + 1) || p;
});

function goToParent(): void {
  if (parentPath.value) emit("navigate", parentPath.value);
}

function handleClick(entry: SpcodeFileBrowserEntry): void {
  // Dangling symlink: click does nothing
  if (entry.type === "symlink" && entry.target_exists === false) return;
  emit("navigate", entry.path);
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

    <!-- Back-to-parent affordance: shown when a file/symlink is
         open. The directory entries don't apply anymore (state is
         no longer "directory"), but giving the user a single
         clickable "go up" item keeps the left pane useful and
         discoverable. -->
    <button
      v-if="parentPath"
      type="button"
      class="file-browser-back"
      @click="goToParent"
    >
      <v-icon size="16" color="info">mdi-arrow-up</v-icon>
      <span class="back-label">{{
        tm("spcodeProjectLoad.fileBrowser.entryType.backToParent", { name: parentName })
      }}</span>
    </button>

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
/* Back-to-parent affordance (visible while a file/symlink is open
   in the right pane). Matches the entry-row style for visual
   consistency — same hover background, same row height. */
.file-browser-back {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  margin: 2px 0;
  background: transparent;
  border: none;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-family: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  width: 100%;
  transition: background 0.1s, color 0.1s;
}
.file-browser-back:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
  color: rgba(var(--v-theme-on-surface), 0.95);
}
.back-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
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
  transition: background 0.1s;
}
.file-browser-entry:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
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