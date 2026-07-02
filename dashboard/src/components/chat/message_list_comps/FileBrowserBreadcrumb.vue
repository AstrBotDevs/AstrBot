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
//
// 2026-07-02 revision: case-insensitive root match on Windows, plus a
// "render the basename anyway" fallback when currentPath is outside
// the root. The previous strict equality check left the breadcrumb
// completely hidden when the search-result absolute path and the
// worktree root disagreed by even one case character (very common on
// Windows where the worktree path can be "C:/work/Repo" and the
// search result path can be "c:/work/repo/astrabot/cli/main.py" —
// different drive case). Hiding the breadcrumb was unacceptable
// because the user lost path navigation entirely, so we now render
// the basename as a single segment in that case (and still emit
// `navigate(currentPath)` so clicking it scrolls the file browser
// back to that directory).
function buildSegments(current: string, root: string | null): Segment[] {
  if (!current) return [];
  const normCurrent = current.replace(/\\/g, "/");

  // Basename fallback (used both for the "no root" case and for the
  // "current is outside root" case). Centralised so the two code
  // paths stay in sync.
  const basenameFallback = (): Segment[] => {
    const parts = normCurrent.split("/").filter(Boolean);
    if (parts.length === 0) return [];
    const basename = parts[parts.length - 1];
    return [{ name: basename, path: normCurrent, isRoot: false }];
  };

  if (!root) return basenameFallback();

  const normRoot = root.replace(/\\/g, "/").replace(/\/$/, "");
  // Case-insensitive comparison on Windows where the drive letter or
  // path segments can differ in case between the worktree root and
  // the absolute path returned by the search backend.
  const ci = (a: string, b: string): boolean =>
    a === b || a.toLowerCase() === b.toLowerCase();

  if (ci(normCurrent, normRoot)) {
    return [
      {
        name: tm("spcodeProjectLoad.fileBrowser.breadcrumbRoot"),
        path: normRoot,
        isRoot: true,
      },
    ];
  }
  if (ci(normCurrent.slice(0, normRoot.length + 1), normRoot + "/")) {
    const relative = normCurrent.slice(normRoot.length + 1);
    const parts = relative.split("/").filter(Boolean);
    const result: Segment[] = [
      {
        name: tm("spcodeProjectLoad.fileBrowser.breadcrumbRoot"),
        path: normRoot,
        isRoot: true,
      },
    ];
    let acc = normRoot;
    for (const p of parts) {
      acc += "/" + p;
      result.push({ name: p, path: acc, isRoot: false });
    }
    return result;
  }
  // currentPath is outside root (or the root comparison still failed
  // despite case-folding — e.g. UNC vs drive-letter, or a symlink
  // boundary). Fall back to the basename so the user always sees
  // SOMETHING and can click it to re-anchor the file browser on
  // this path.
  return basenameFallback();
}

const segments = computed<Segment[]>(() => {
  return buildSegments(props.currentPath, props.rootPath);
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
