<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.6 -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  currentPath: string;
  /** Root path; null when project not loaded. */
  rootPath: string | null;
  /**
   * 2026-07-02: pass through the dashboard's dark-mode flag so the
   * path bar can lift its background alpha + border strength in
   * dark theme. Without this, the primary-tint background
   * introduced for the light mode would render as a near-invisible
   * 8%-alpha wash against the dark sidebar.
   */
  isDark?: boolean;
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
  <nav
    v-if="segments.length > 0"
    class="file-browser-breadcrumb"
    :class="{ dark: props.isDark }"
  >
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
/* ── Light mode (default) ─────────────────────────────────────────
   Primary-tint background + 2px matching bottom border. The
   previous 0.08-alpha wash was indistinguishable from the
   surrounding sidebar chrome on most displays (the user
   reported "no effect" after the first iteration), so the
   background is now lifted to 0.15 and the border to 0.4 with
   2px stroke. A 1px subtle drop shadow under the bar gives it
   a "raised card" feel so it reads as a distinct navigation
   surface, not just inline text. Active segment keeps a
   slightly stronger fill so the leaf (the file the user just
   opened) is unambiguous. */
.file-browser-breadcrumb {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  padding: 10px 14px;
  font-size: 12px;
  font-family: ui-monospace, monospace;
  background: rgba(var(--v-theme-primary), 0.15);
  border-bottom: 2px solid rgba(var(--v-theme-primary), 0.4);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
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
  transition:
    background 0.1s ease,
    color 0.1s ease;
}
.breadcrumb-segment:hover {
  background: rgba(var(--v-theme-primary), 0.22);
  color: rgb(var(--v-theme-on-surface));
}
.breadcrumb-segment.is-current {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
  background: rgba(var(--v-theme-primary), 0.22);
  cursor: default;
}
.breadcrumb-sep {
  color: rgba(var(--v-theme-primary), 0.55);
  user-select: none;
}

/* ── Dark mode ────────────────────────────────────────────────────
   Alpha lifted further (0.15 → 0.24) and border strength raised
   (0.4 → 0.55) so the bar still reads as a distinct surface
   against the dark sidebar — at 0.15 the wash disappeared
   entirely into the dark chrome. The inset top + bottom shadow
   pair gives a tactile "inset card" feel that reads well
   against a dark surface. Active segment is bumped to 0.3 so
   the leaf still pops above the other (already near-white)
   segments. */
.file-browser-breadcrumb.dark {
  background: rgba(var(--v-theme-primary), 0.24);
  border-bottom-color: rgba(var(--v-theme-primary), 0.55);
  box-shadow:
    inset 0 1px 0 rgba(0, 0, 0, 0.2),
    inset 0 -1px 0 rgba(0, 0, 0, 0.2);
}
.file-browser-breadcrumb.dark .breadcrumb-segment {
  color: rgba(var(--v-theme-on-surface), 0.82);
}
.file-browser-breadcrumb.dark .breadcrumb-segment:hover {
  background: rgba(var(--v-theme-primary), 0.32);
  color: rgb(var(--v-theme-on-surface));
}
.file-browser-breadcrumb.dark .breadcrumb-segment.is-current {
  color: rgb(var(--v-theme-on-surface));
  background: rgba(var(--v-theme-primary), 0.3);
}
.file-browser-breadcrumb.dark .breadcrumb-sep {
  color: rgba(var(--v-theme-primary), 0.65);
}
</style>
