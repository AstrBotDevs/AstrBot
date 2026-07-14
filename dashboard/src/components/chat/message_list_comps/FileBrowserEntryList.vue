<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.4
     Updated 2026-06-21 — drop "back to parent" affordance; instead the
     parent directory stays mounted in this pane (driven by the
     dirComposable in FileBrowserView) and the currently-previewed file
     is highlighted via `selected-path`. -->
<script setup lang="ts">
import {
  computed,
  ref,
  watch,
  onMounted,
  onBeforeUnmount,
  nextTick,
} from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { FileBrowserFetchState } from "@/composables/useSpcodeFileBrowser";
import type { SpcodeFileBrowserEntry } from "@/composables/parseSpcodeFileBrowser";

const props = defineProps<{
  state: FileBrowserFetchState;
  /** Path of the file currently being previewed in the right pane;
   *  used to highlight the matching entry in this list. */
  selectedPath: string | null;
  /**
   * When set, only files whose extension (case-insensitive,
   * including the leading dot) appears in this list are shown.
   * Directories are always shown regardless — the tree needs
   * them for navigation. Omit or pass an empty array to show
   * every file (workspace / generic browser mode).
   *
   * Used by DocumentTreePanel to restrict the docs sub-page to
   * `.md` / `.txt` (the formats the doc manager edits); the
   * workspace FileBrowserView leaves this unset so the user
   * still sees every file in the repo.
   */
  allowedExtensions?: string[];
}>();
// Emit the full entry (not just the path) so the parent can inspect
// `entry.type` and route correctly:
//   - directory: navigate to that directory, clear preview
//   - file / symlink: navigate to its parent, preview the path
// Emitting only the path would force the parent to re-look-up the
// entry by path from the current directory snapshot, which is racy
// if the snapshot changes between the click and the handler.
const emit = defineEmits<{
  (e: "navigate", entry: SpcodeFileBrowserEntry): void;
}>();
const { tm } = useModuleI18n("features/chat");

const TYPE_ICONS: Record<
  SpcodeFileBrowserEntry["type"],
  { icon: string; color: string }
> = {
  directory: { icon: "mdi-folder-outline", color: "info" },
  file: { icon: "mdi-file-document-outline", color: "grey" },
  symlink: { icon: "mdi-link-variant", color: "info" },
};

const entries = computed<SpcodeFileBrowserEntry[]>(() => {
  if (props.state.kind !== "directory") return [];
  const all = props.state.snapshot.entries;
  const filter = props.allowedExtensions;
  // No filter configured (or an explicitly empty list) → show
  // every entry, including all files. Used by the workspace
  // FileBrowserView, which must surface every file in the repo.
  if (!filter || filter.length === 0) return all;
  const normalized = filter.map((e) => e.toLowerCase());
  return all.filter((entry) => {
    // Directories are always shown so the user can still drill
    // into subfolders. Symlinks are kept too — the existing
    // dangling-symlink CSS already covers the "broken target"
    // case, and following the symlink would require an extra
    // round-trip to determine the target's file type, which is
    // out of scope here.
    if (entry.type !== "file") return true;
    const dot = entry.name.lastIndexOf(".");
    if (dot < 0) return false;
    return normalized.includes(entry.name.slice(dot).toLowerCase());
  });
});

const truncated = computed<boolean>(() => {
  return (
    props.state.kind === "directory" && props.state.snapshot.meta.truncated
  );
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

// ── Truncation detection for full-name tooltip ───────────────────
// 2026-07-09: with the default split ratio reduced to 3:7 (see
// FileBrowserView), the file-list pane is narrower, so long file
// names get ellipsized more often. To avoid forcing the user to
// widen the pane or rename the file, we show a v-tooltip with the
// full name — but ONLY when the visible text is actually being
// clipped. Showing the tooltip for non-truncated rows would be
// redundant noise (the user hovers, sees the same text they were
// already looking at).
//
// Implementation: a single ResizeObserver watches every
// `.file-browser-entry`; on each notification we walk the rows
// and rebuild a Set of paths whose `.entry-name` overflows
// (`scrollWidth > clientWidth`). The observer is throttled to a
// single rAF tick because the resize event from the draggable
// divider fires on every mousemove.
//
// 2026-07-09b — bug fix: the previous version only ran detection
// inside `onMounted`, which is too early — `props.state` is
// typically `'loading'` at mount time, so the DOM has zero
// `.file-browser-entry` elements to observe. The empty Set then
// made every `:disabled="!isTruncated(path)"` evaluate to true,
// silently killing the tooltip on every row. We now (1) watch
// `entries` and re-run detection + re-attach the observer when
// the row set changes, and (2) fall back to "always show the
// tooltip" for the very first frame if detection has not yet
// produced any data, so the user is never left without feedback.
const truncatedPaths = ref<Set<string>>(new Set());
let resizeObserver: ResizeObserver | null = null;
let rafId: number | null = null;
let hasDetectedOnce = false;

function detectTruncation(): void {
  // Find every row currently mounted and check whether its name
  // element actually overflows. We rely on the DOM rather than a
  // per-row ref map because (a) Vue would otherwise need a ref
  // per v-for iteration, and (b) ResizeObserver hands us the live
  // element directly so the data is always in sync.
  const next = new Set<string>();
  const rows = document.querySelectorAll<HTMLElement>(".file-browser-entry");
  rows.forEach((row) => {
    const nameEl = row.querySelector<HTMLElement>(".entry-name");
    if (!nameEl) return;
    // +1 fudge factor: clientWidth is rounded down so a 1px
    // sub-pixel difference between scrollWidth/clientWidth is
    // not real overflow.
    if (nameEl.scrollWidth > nameEl.clientWidth + 1) {
      const path = row.dataset.path;
      if (path) next.add(path);
    }
  });
  truncatedPaths.value = next;
  hasDetectedOnce = true;
}

function scheduleDetect(): void {
  // Coalesce multiple ResizeObserver notifications within a single
  // frame into one DOM walk.
  if (rafId !== null) return;
  rafId = requestAnimationFrame(() => {
    rafId = null;
    detectTruncation();
  });
}

function attachObserver(): void {
  // Lazy-create the observer once. Subsequent calls just
  // subscribe the (possibly new) rows; observe() is idempotent
  // so re-subscribing already-observed elements is harmless.
  if (!resizeObserver) {
    resizeObserver = new ResizeObserver(scheduleDetect);
  }
  document
    .querySelectorAll<HTMLElement>(".file-browser-entry")
    .forEach((el) => {
      resizeObserver!.observe(el);
    });
}

function isTruncated(path: string): boolean {
  // The :disabled binding on v-tooltip must be FALSE (i.e.
  // isTruncated true) for the tooltip to open. Before the first
  // detection completes, we don't yet know which rows are
  // truncated, but the user has been hovering and seeing nothing
  // for the whole session — that feels broken. Show the tooltip
  // for every row in that grace period, then let detection
  // narrow it down on the next frame.
  if (!hasDetectedOnce) return true;
  return truncatedPaths.value.has(path);
}

// Re-detect whenever the row set changes. `flush: "post"` waits
// for Vue to commit the DOM before we measure, so the new
// `.file-browser-entry` elements are present in the layout.
// The watcher fires for the initial entries-load (loading →
// directory) AND for any subsequent navigation.
watch(
  entries,
  async () => {
    await nextTick();
    detectTruncation();
    attachObserver();
  },
  { flush: "post" },
);

onMounted(async () => {
  // Best-effort initial detection. If the rows are already in
  // the DOM by mount time (synchronous initial state), this
  // works; if not, the `watch(entries, ...)` above will run
  // detection as soon as the data lands.
  await nextTick();
  detectTruncation();
  attachObserver();
});

onBeforeUnmount(() => {
  if (rafId !== null) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
  resizeObserver?.disconnect();
  resizeObserver = null;
});
</script>

<template>
  <div class="file-browser-entry-list">
    <div v-if="truncated" class="entry-list-warning">
      {{ tm("spcodeProjectLoad.fileBrowser.truncated") }}
    </div>

    <div
      v-if="entries.length === 0 && state.kind === 'directory'"
      class="file-browser-empty-dir"
    >
      <v-icon size="24" color="grey">mdi-folder-open-outline</v-icon>
      <span>{{ tm("spcodeProjectLoad.fileBrowser.empty") }}</span>
    </div>

    <ul v-else-if="entries.length > 0" class="file-browser-entries">
      <li
        v-for="entry in entries"
        :key="entry.path"
        class="file-browser-entry-row"
      >
        <!--
          2026-07-09b bug fix: the previous structure used
          `activator="parent"` on a <v-tooltip> placed directly
          inside a v-for. In Vuetify 3 that activator resolves
          against the v-tooltip's Vue parent component ($el),
          which for every v-for iteration is the SAME root
          `<div class="file-browser-entry-list">` — so all
          tooltips shared one (non-functional) activator. The
          explicit `#activator` slot pattern below binds the
          tooltip to a single dedicated <div> in each iteration,
          which is the documented reliable form for v-for.

          The <div class="file-browser-entry"> also receives the
          click handler now (was previously on the outer <li>),
          so hover + click land on the same element. The outer
          <li> is a pure structural wrapper for the v-for.
        -->
        <v-tooltip
          location="end"
          :open-delay="300"
          :disabled="!isTruncated(entry.path)"
        >
          <template #activator="{ props: tipProps }">
            <div
              v-bind="tipProps"
              :data-path="entry.path"
              class="file-browser-entry"
              :class="{
                'is-symlink': entry.type === 'symlink',
                'is-dangling':
                  entry.type === 'symlink' && entry.target_exists === false,
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
              <span
                v-if="entry.type === 'symlink' && entry.target"
                class="entry-symlink-target"
              >
                → {{ entry.target }}
              </span>
              <span class="entry-size">{{ formatSize(entry.size) }}</span>
            </div>
          </template>
          <span class="file-browser-entry-tooltip">{{ entry.name }}</span>
        </v-tooltip>
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
  transition:
    background 0.1s,
    color 0.1s;
  /* 2026-07-09b: position the row so the `::before` accent
     bar in `.file-browser-entry.is-selected::below` anchors
     to THIS row, not to the nearest other positioned
     ancestor (the <ul>). Without this rule the bar would
     stretch across the full file list height instead of
     just the selected row. */
  position: relative;
}
/* Hover: matches the subtle hover we've used across the
   chat-ui for unselected, non-symlink rows. */
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
  /* Thin accent bar on the left edge to make the selection
     obvious even when the file name is short and the row is
     wide. Without `position: relative` on the row (added above),
     this `::before` would anchor to the <ul> and stretch the
     full list height instead of the single row. */
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: rgb(var(--v-theme-primary));
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

/* 2026-07-09: v-tooltip body styling for truncated-filename hints.
   The overlay content lives in a teleport portal, so its styles
   must be non-scoped — we use :deep() to pierce the scoped
   boundary. The tooltip inherits the entry-name monospace look so
   the user sees the same font as the truncated list, and uses
   word-break: break-all so very long names (without spaces) wrap
   instead of pushing the tooltip off-screen. */
:deep(.file-browser-entry-tooltip) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11.5px;
  font-weight: 500;
  /* Long single-token names (no separator chars) still wrap. The
     default "normal" would let the tooltip balloon to whatever
     width the name needs. */
  word-break: break-all;
  max-width: 360px;
  display: inline-block;
}
</style>
