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

    <div v-if="entries.length === 0 && state.kind === 'directory'" class="file-browser-empty-dir">
      <v-icon size="24" color="grey">mdi-folder-open-outline</v-icon>
      <span>{{ tm("spcodeProjectLoad.fileBrowser.empty") }}</span>
    </div>

    <ul v-else class="file-browser-entries">
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
  flex: 0 0 40%;
  min-width: 140px;
  overflow-y: auto;
  overflow-x: hidden;
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.08);
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