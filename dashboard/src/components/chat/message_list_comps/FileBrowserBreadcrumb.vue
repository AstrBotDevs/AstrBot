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
   * 2026-07-09: passed through from the file-browser's `previewPath`
   * so the leaf segment can pick the right icon. When `previewPath`
   * is non-null, the leaf represents the file being previewed and
   * renders a document icon; otherwise the leaf is the directory the
   * user is browsing and renders a folder icon to match its parents.
   */
  previewPath?: string | null;
  /**
   * 2026-07-02: pass through the dashboard's dark-mode flag so the
   * path bar's separator + hover tones map correctly to dark theme.
   */
  isDark?: boolean;
}>();
const emit = defineEmits<{ (e: "navigate", path: string): void }>();
const { tm } = useModuleI18n("features/chat");

// 2026-07-09: leaf is "the file currently being previewed" only when
// the caller has a non-null previewPath. In all other cases the leaf
// is just another folder the user is browsing through, so it shares
// the parent folder icon and only changes its color (no border, no
// background, no bold — those treatments all proved visually heavy
// during the 2026-07-08 / 2026-07-09 iterations).
const leafIsFile = computed<boolean>(() => !!props.previewPath);

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
      <!--
        2026-07-09 redesign — macOS Finder Path Bar style:
        - parents are real <button>s (clickable, focusable, keyboard
          accessible); their icon disambiguates "this is a folder you
          can navigate into"
        - the leaf is a plain <span> (no button affordance; it is
          the user's "current location" and clicking it would be a
          no-op, so we don't pretend it can be clicked)
        - the chevron `›` separates segments; rotated 0deg (already
          points right in the chosen glyph) and styled muted
        - when there is only one segment and it IS the root, the
          leaf still gets the file-vs-folder icon distinction via
          previewPath; the breadcrumb simply renders the root alone
      -->
      <button
        v-if="i < segments.length - 1"
        type="button"
        class="breadcrumb-segment"
        :title="seg.path"
        @click="emit('navigate', seg.path)"
      >
        <v-icon :size="13" class="breadcrumb-segment-icon">{{
          seg.isRoot ? "mdi-folder" : "mdi-folder-outline"
        }}</v-icon>
        <span class="breadcrumb-segment-name">{{ seg.name }}</span>
      </button>
      <span v-else class="breadcrumb-leaf" :title="seg.path">
        <v-icon :size="13" class="breadcrumb-leaf-icon">{{
          leafIsFile
            ? "mdi-file-document-outline"
            : seg.isRoot
            ? "mdi-folder"
            : "mdi-folder-outline"
        }}</v-icon>
        <span class="breadcrumb-leaf-name">{{ seg.name }}</span>
      </span>
      <span
        v-if="i < segments.length - 1"
        class="breadcrumb-sep"
        aria-hidden="true"
        >›</span
      >
    </template>
  </nav>
</template>

<style scoped>
/* ── 2026-07-09 redesign — macOS Finder Path Bar ──────────────────
   Three prior iterations (background wash, primary bottom-border,
   then 3px left-accent + 8% wash) all left the leaf feeling
   visually heavy in this sidebar. This rewrite drops the chrome
   entirely: the bar is just a hairline divider with system-font
   text, folder/file icons, and a muted chevron. The leaf is
   emphasized purely through color + medium weight — no background
   fill, no border, no shadow. The result reads as a flat
   navigation strip rather than a card or banner. */
.file-browser-breadcrumb {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1px;
  padding: 9px 12px;
  font-size: 12.5px;
  font-family: inherit;
  line-height: 1.4;
  /* No background. A single 1px hairline below separates the
     bar from the file tree beneath; using the same chat-border
     token as the sidebar chrome keeps the visual rhythm aligned. */
  border-bottom: 1px solid
    var(--chat-border, rgba(var(--v-theme-on-surface), 0.08));
  /* The bar can wrap on narrow widths (420px sidebar + deep path);
     align the wrapped rows consistently. */
  row-gap: 2px;
}

/* Clickable parent: a quiet button that becomes obvious on hover
   through a primary-tinted 8% wash. The icon inherits the text
   color so the entire row tints together on hover (not just the
   text). max-width + ellipsis prevents a single deep folder name
   from blowing out the layout. */
.breadcrumb-segment {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 200px;
  padding: 3px 8px;
  background: transparent;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  color: rgba(var(--v-theme-on-surface), 0.62);
  transition:
    background 0.12s ease,
    color 0.12s ease;
  overflow: hidden;
}
.breadcrumb-segment:hover {
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
}
.breadcrumb-segment:focus-visible {
  outline: 2px solid rgba(var(--v-theme-primary), 0.45);
  outline-offset: 1px;
}
.breadcrumb-segment-icon {
  color: rgba(var(--v-theme-on-surface), 0.45);
  flex-shrink: 0;
  transition: color 0.12s ease;
}
.breadcrumb-segment:hover .breadcrumb-segment-icon {
  color: rgb(var(--v-theme-primary));
}
.breadcrumb-segment-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* Leaf ("you are here"): plain <span> so the cursor never lies
   about it being clickable, and the text is selectable for
   copy-to-clipboard. Visual emphasis is just primary color +
   medium weight — no fill, no border, no shadow. */
.breadcrumb-leaf {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 240px;
  padding: 3px 6px;
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  font-weight: 500;
  color: rgb(var(--v-theme-primary));
  user-select: text;
  overflow: hidden;
}
.breadcrumb-leaf-icon {
  color: rgb(var(--v-theme-primary));
  flex-shrink: 0;
  /* Slight opacity dip on the icon (vs. the text) so the
     filename is the most prominent thing in the leaf. */
  opacity: 0.85;
}
.breadcrumb-leaf-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* Chevron separator. `›` is a single glyph that already points
   right, so no transform needed. Color stays low-contrast so
   the user's eye flows past the separators to the segments. */
.breadcrumb-sep {
  color: rgba(var(--v-theme-on-surface), 0.28);
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
  user-select: none;
  flex-shrink: 0;
  /* Visual baseline alignment with the icon-cap of the segments.
     13px icons sit slightly above the text baseline; nudge the
     chevron down 1px to match. */
  position: relative;
  top: 1px;
}

/* ── Dark mode ────────────────────────────────────────────────────
   The base colors (text and hairline) already inherit correctly
   from the v-theme variables, so dark mode only needs to bump
   the segment-icon alpha and the hover wash a touch lighter so
   the affordance reads on the dark surface. */
.file-browser-breadcrumb.dark .breadcrumb-segment {
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.file-browser-breadcrumb.dark .breadcrumb-segment:hover {
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-primary));
}
.file-browser-breadcrumb.dark .breadcrumb-segment-icon {
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.file-browser-breadcrumb.dark
  .breadcrumb-segment:hover
  .breadcrumb-segment-icon {
  color: rgb(var(--v-theme-primary));
}
.file-browser-breadcrumb.dark .breadcrumb-sep {
  color: rgba(var(--v-theme-on-surface), 0.35);
}
</style>
