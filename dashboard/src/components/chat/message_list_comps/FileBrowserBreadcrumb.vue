<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.6 -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  currentPath: string;
  /** Root path; null when project not loaded. */
  rootPath: string | null;
}>();
const emit = defineEmits<{ (e: "navigate", path: string): void }>();
const { tm } = useModuleI18n("features/chat");

interface Segment {
  name: string;
  path: string;
  isRoot: boolean;
}

// Split currentPath into clickable segments. root segment is special
// (label = "Project root" / "项目根" / "Корень проекта").
const segments = computed<Segment[]>(() => {
  if (!props.currentPath || !props.rootPath) return [];
  const sep = props.currentPath.includes("\\") ? "\\" : "/";
  const normCurrent = props.currentPath.replace(/\\/g, "/");
  const normRoot = props.rootPath.replace(/\\/g, "/").replace(/\/$/, "");

  // Compute relative path from root
  let relative: string;
  if (normCurrent === normRoot) {
    relative = "";
  } else if (normCurrent.startsWith(normRoot + "/")) {
    relative = normCurrent.slice(normRoot.length + 1);
  } else {
    return [];  // currentPath is outside root; render nothing
  }

  const parts = relative.split("/").filter(Boolean);
  const result: Segment[] = [
    { name: tm("spcodeProjectLoad.fileBrowser.breadcrumbRoot"), path: normRoot, isRoot: true },
  ];
  let acc = normRoot;
  for (const p of parts) {
    acc += "/" + p;
    result.push({ name: p, path: acc, isRoot: false });
  }
  return result;
});
</script>

<template>
  <nav v-if="segments.length > 0" class="file-browser-breadcrumb">
    <template v-for="(seg, i) in segments" :key="seg.path">
      <button
        type="button"
        class="breadcrumb-segment"
        :class="{ 'is-current': i === segments.length - 1 }"
        :title="seg.path"
        @click="emit('navigate', seg.path)"
      >
        {{ seg.name }}
      </button>
      <span v-if="i < segments.length - 1" class="breadcrumb-sep">/</span>
    </template>
  </nav>
</template>

<style scoped>
.file-browser-breadcrumb {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  padding: 8px 14px;
  font-size: 12px;
  font-family: ui-monospace, monospace;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.4);
}
.breadcrumb-segment {
  background: none;
  border: none;
  padding: 2px 6px;
  border-radius: 4px;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-family: inherit;
  font-size: inherit;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.breadcrumb-segment:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), 0.9);
}
.breadcrumb-segment.is-current {
  color: rgba(var(--v-theme-on-surface), 0.95);
  font-weight: 500;
  cursor: default;
}
.breadcrumb-sep {
  color: rgba(var(--v-theme-on-surface), 0.3);
  user-select: none;
}
</style>