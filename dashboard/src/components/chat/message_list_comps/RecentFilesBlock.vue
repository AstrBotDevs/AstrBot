<!--
  Author: elecvoid243, 2026-07-20
  RecentFilesBlock: collapsed-by-default panel for the Files view.

  Spec: docs/superpowers/specs/2026-07-20-recent-files-design.md §5
-->
<script setup lang="ts">
import { computed, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { RecentEntry } from "@/composables/useRecentFiles";

const props = withDefaults(
  defineProps<{
    entries: RecentEntry[];
    currentRoot: string;
  }>(),
  { entries: () => [] },
);

defineEmits<{
  (e: "select", payload: { path: string }): void;
  (e: "remove", payload: { path: string }): void;
  (e: "clear"): void;
}>();

const { tm } = useModuleI18n("features/chat");

// Default: collapsed. Not persisted across sessions (spec §5.3).
const expanded = ref(false);
function toggle(): void {
  expanded.value = !expanded.value;
}

const MAX_DISPLAYED = 5;
const displayedEntries = computed<RecentEntry[]>(() =>
  props.entries.slice(0, MAX_DISPLAYED),
);
const overflow = computed<number>(() =>
  Math.max(0, props.entries.length - MAX_DISPLAYED),
);

function basename(p: string): string {
  const sep = p.includes("\\") ? "\\" : "/";
  const idx = p.lastIndexOf(sep);
  return idx === -1 ? p : p.slice(idx + 1);
}

function dirOf(p: string): string {
  const sep = p.includes("\\") ? "\\" : "/";
  const idx = p.lastIndexOf(sep);
  return idx === -1 ? "" : p.slice(0, idx);
}
</script>

<template>
  <section class="recent-files-block">
    <button
      type="button"
      class="recent-files-header"
      :aria-expanded="expanded"
      data-test="recent-files-header"
      @click="toggle"
    >
      <v-icon size="16" class="recent-files-header-icon">
        mdi-clock-outline
      </v-icon>
      <span class="recent-files-header-text">
        {{
          tm(
            "spcodeProjectLoad.fileBrowser.recentFiles.titleWithCount",
            { count: props.entries.length },
          )
        }}
      </span>
      <v-icon size="16" class="recent-files-header-chevron">
        {{ expanded ? "mdi-chevron-up" : "mdi-chevron-down" }}
      </v-icon>
    </button>

    <div
      v-show="expanded"
      class="recent-files-body"
      data-test="recent-files-body"
    >
      <div
        v-if="props.entries.length > 0"
        class="recent-files-list"
      >
        <button
          type="button"
          class="recent-files-clear"
          data-test="recent-clear"
          @click.stop="$emit('clear')"
        >
          {{ tm("spcodeProjectLoad.fileBrowser.recentFiles.clear") }}
        </button>

        <div
          v-for="entry in displayedEntries"
          :key="entry.path"
          class="recent-files-row"
          data-test="recent-row"
          role="button"
          tabindex="0"
          @click="$emit('select', { path: entry.path })"
          @keyup.enter="$emit('select', { path: entry.path })"
        >
          <v-icon size="14" class="recent-files-row-icon">
            mdi-file-outline
          </v-icon>
          <span class="recent-files-row-main" :title="entry.path">
            {{ basename(entry.path) }}
          </span>
          <span class="recent-files-row-sub">
            {{ dirOf(entry.path) }}
          </span>
          <button
            type="button"
            class="recent-files-remove"
            data-test="recent-remove"
            :title="
              tm(
                'spcodeProjectLoad.fileBrowser.recentFiles.removeTooltip',
              )
            "
            @click.stop="$emit('remove', { path: entry.path })"
          >
            <v-icon size="14">mdi-close</v-icon>
          </button>
        </div>

        <div
          v-if="overflow > 0"
          class="recent-files-more"
          data-test="recent-files-more"
        >
          +{{ overflow }} more →
        </div>
      </div>

      <div
        v-else
        class="recent-files-empty"
        data-test="recent-files-empty"
      >
        {{ tm("spcodeProjectLoad.fileBrowser.recentFiles.empty") }}
      </div>
    </div>
  </section>
</template>

<style scoped>
.recent-files-block {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.recent-files-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  background: transparent;
  border: none;
  cursor: pointer;
  font: inherit;
  color: inherit;
  text-align: left;
}
.recent-files-header:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.recent-files-header-text {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}
.recent-files-header-chevron {
  opacity: 0.6;
}
.recent-files-body {
  padding: 4px 0 8px 12px;
}
.recent-files-list {
  display: flex;
  flex-direction: column;
}
.recent-files-clear {
  align-self: flex-end;
  margin-right: 12px;
  margin-bottom: 4px;
  background: transparent;
  border: none;
  color: rgba(var(--v-theme-primary), 0.85);
  cursor: pointer;
  font-size: 12px;
}
.recent-files-clear:hover {
  text-decoration: underline;
}
.recent-files-row {
  display: grid;
  grid-template-columns: 18px 1fr auto auto;
  align-items: center;
  gap: 6px;
  padding: 4px 12px 4px 0;
  cursor: pointer;
}
.recent-files-row:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}
.recent-files-row-icon {
  opacity: 0.6;
}
.recent-files-row-main {
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.recent-files-row-sub {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 90px;
}
.recent-files-remove {
  background: transparent;
  border: none;
  cursor: pointer;
  opacity: 0;
  color: inherit;
}
.recent-files-row:hover .recent-files-remove,
.recent-files-remove:focus {
  opacity: 0.7;
}
.recent-files-remove:hover {
  opacity: 1;
}
.recent-files-more {
  padding: 4px 12px;
  font-size: 12px;
  color: rgba(var(--v-theme-primary), 0.85);
}
.recent-files-empty {
  text-align: center;
  padding: 12px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-size: 12px;
}
</style>
