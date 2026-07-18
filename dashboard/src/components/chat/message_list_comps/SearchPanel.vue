<!--
  Author: elecvoid243, 2026-07-02
  SearchPanel — in-sidebar search results UI with Filename / Content
  mode toggle. Spec: docs/superpowers/specs/2026-07-02-sidebar-search-design.md §4.4

  2026-07-02 revision: adds the mode toggle (Filename default → /spcode/
  file-name-search, Content → /spcode/file-search) and branches result
  rendering on the discriminated SearchResult union.

  2026-07-02 revision (toolbar input): the search <input> moved out of
  this component into the GitDiffSidebar toolbar (next to the search
  toggle button). The shared `query` ref + 300ms debounce now live in
  useSpcodeFileSearch, so this component only owns the mode toggle,
  status line, and result list. Closing the panel is still driven
  from here (Esc on a result row → composable's close() + emit
  update:modelValue false); the input's own Esc handler lives in
  GitDiffSidebar.

  Notes vs. the brief template:
  - Project pins vue@3.3.4, so `useTemplateRef` (Vue 3.5+) is unavailable;
    fall back to the established `ref<HTMLInputElement | null>(null)` pattern.
  - `useModuleI18n().tm()` is typed as (key, params?) — no `missing` option.
    The error-reason label is built by errorReasonLabel(), which tries the
    per-reason key and falls back to the raw reason string when missing.
    T8 adds the per-reason keys; until then the raw reason is shown.
-->
<script setup lang="ts">
import {
  useSpcodeFileSearch,
  type SearchResult,
  type SearchMode,
} from "@/composables/useSpcodeFileSearch";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps<{
  modelValue: boolean;
  worktree: string | null;
  umo: string | null;
  /**
   * 2026-07-17 docs-search: optional repo-relative directory scope
   * forwarded to the backend as path_filter (e.g. the docs root when
   * embedded in DocumentManager). Omit/null = search the whole
   * worktree (existing workspace behaviour).
   */
  pathFilter?: string | null;
}>();
const emit = defineEmits<{
  "update:modelValue": [v: boolean];
  "open-file": [p: { path: string; line: number }];
}>();

const { tm } = useModuleI18n("features/chat");
// 2026-07-02 toolbar input: `query` is now shared with the toolbar
// input. We still kick off a programmatic search() at mount with the
// current props (umo/worktree) so the debounce watcher has a valid
// routing context for any later keystroke. The actual typing lives
// in the toolbar input; this component no longer owns an <input>.
// `close()` is the one-call reset that Esc on a result row triggers.
const { state, mode, search, setMode, close } = useSpcodeFileSearch();
// Seed the composable's last-umo/last-worktree cache so the debounce
// watcher can re-fire search() with the right routing context after
// the user edits the toolbar input. The pattern argument is empty
// (the watcher short-circuits empty patterns to idle), so this is
// a context-priming call only — no network request fires.
void search({
  umo: props.umo,
  worktree: props.worktree,
  pattern: "",
  pathFilter: props.pathFilter ?? undefined,
});

function onClose(): void {
  // 2026-07-02 toolbar input: clear the shared query + state via the
  // composable's close(), then tell the parent to collapse the panel.
  // (We no longer own the debounce timer or inputRef — both live
  // elsewhere now.)
  close();
  emit("update:modelValue", false);
}

function onModeChange(newMode: SearchMode | undefined): void {
  if (!newMode || newMode === mode.value) return;
  setMode(newMode);
  // The setMode() call already cancels in-flight + resets state to
  // idle. The current query stays in the input; the debounce watcher
  // will NOT re-fire unless the user edits the query (by design —
  // we don't want a stale pattern to silently re-search on toggle).
}

function onResultClick(r: SearchResult): void {
  // Filename mode has no line number; open at line 0 (the preview
  // pane treats 0 as "scroll to top" / "no highlight").
  const line = r.mode === "content" ? r.line : 0;
  emit("open-file", { path: r.path, line });
}

function onKeydown(e: KeyboardEvent): void {
  // 2026-07-02 toolbar input: Escape on a search result row still
  // closes the panel (focus may have drifted from the toolbar input
  // to a result after a click). The toolbar input's own Esc handler
  // stopPropagation-prevents this branch from running when focus is
  // on the input itself.
  if (e.key === "Escape") {
    e.stopPropagation();
    onClose();
  }
}

// Try the per-reason i18n key (added in T8); fall back to the raw reason
// string when the key is missing so the UI stays useful during development.
function errorReasonLabel(reason: string): string {
  const translated = tm(`spcodeProjectLoad.diffSidebar.search.error.${reason}`);
  if (translated.startsWith("[MISSING:")) return reason;
  return translated;
}

// formatSize — human-readable byte count. Matches the spec example
// format ("567 B", "1.2 KB", "3.4 MB"). Directories always pass 0
// (and we hide the size segment for them in the result row), so the
// "0 B" branch is not user-visible in practice.
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

// i18n key prefix shared by the count text — the plural form differs
// between Filename ("{count} file(s)") and Content ("{count} match(es)").
function countKey(m: SearchMode): string {
  return m === "filename"
    ? "spcodeProjectLoad.diffSidebar.search.filenameResultCount"
    : "spcodeProjectLoad.diffSidebar.search.resultCount";
}
</script>

<template>
  <div v-if="modelValue" class="search-panel" @keydown="onKeydown">
    <!-- The search <input> + close button used to live here. They now
         live in the hosting file browser's own search toolbar
         (FileBrowserView / DocumentManager), so the input is always
         visible above the panel — and travels with the file-area
         fullscreen Teleport. The mode toggle, status line, and result
         list stay below. -->

    <div class="search-panel-mode-row">
      <span class="search-panel-mode-label text-caption text-medium-emphasis">
        {{ tm("spcodeProjectLoad.diffSidebar.search.modeLabel") }}
      </span>
      <v-btn-toggle
        :model-value="mode"
        mandatory
        density="compact"
        divided
        hide-details
        class="search-panel-mode-toggle"
        @update:model-value="onModeChange"
      >
        <v-btn size="x-small" value="filename">
          {{ tm("spcodeProjectLoad.diffSidebar.search.modeFilename") }}
        </v-btn>
        <v-btn size="x-small" value="content">
          {{ tm("spcodeProjectLoad.diffSidebar.search.modeContent") }}
        </v-btn>
      </v-btn-toggle>
    </div>

    <div class="search-panel-status">
      <template v-if="state.kind === 'idle'">
        <span class="text-caption text-medium-emphasis">
          {{ tm("spcodeProjectLoad.diffSidebar.search.hint") }}
        </span>
      </template>
      <template v-else-if="state.kind === 'loading'">
        <span class="text-caption text-medium-emphasis">
          {{ tm("spcodeProjectLoad.diffSidebar.search.searching") }}
        </span>
        <v-icon
          v-if="state.kind === 'loading'"
          size="14"
          class="search-panel-spinner"
        >
          mdi-loading
        </v-icon>
      </template>
      <template v-else-if="state.kind === 'ok'">
        <span class="text-caption">
          {{ tm(countKey(mode), { count: state.results.length }) }}
        </span>
        <span v-if="state.truncated" class="text-caption text-warning">
          {{ tm("spcodeProjectLoad.diffSidebar.search.truncated") }}
        </span>
      </template>
      <template v-else-if="state.kind === 'error'">
        <span class="text-caption text-error">
          {{ errorReasonLabel(state.reason) }}
        </span>
      </template>
    </div>

    <ul
      v-if="state.kind === 'ok' && state.results.length"
      class="search-panel-results"
    >
      <li
        v-for="(r, i) in state.results"
        :key="i"
        class="search-panel-result"
        @click="onResultClick(r)"
      >
        <template v-if="r.mode === 'filename'">
          <div class="search-panel-result-path">{{ r.path }}</div>
          <div class="search-panel-result-meta">
            {{ r.name }} ·
            {{ tm("spcodeProjectLoad.diffSidebar.search.fileType") }}:
            {{ tm("spcodeProjectLoad.diffSidebar.search." + r.type) }}
            <template v-if="r.type === 'file'">
              · {{ formatSize(r.size) }}
            </template>
          </div>
        </template>
        <template v-else>
          <div class="search-panel-result-path">
            {{ r.path }}:{{ r.line }}:{{ r.column }}
          </div>
          <pre class="search-panel-result-snippet">{{ r.snippet }}</pre>
        </template>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.search-panel {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 50%;
  overflow: hidden;
}
/* 2026-07-02 toolbar input: the .search-panel-input-row /
   .search-panel-input classes were removed when the <input> moved
   to the GitDiffSidebar toolbar (see SearchPanel.vue revision note
   in the <script setup> header). The .search-panel-mode-row and
   below remain in active use. */
.search-panel-mode-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.search-panel-mode-label {
  white-space: nowrap;
}
.search-panel-mode-toggle {
  /* v-btn-toggle is a wrapper that lays out its v-btn children as a
     segmented control. We rely on the divided + mandatory props for
     the visual "selected" state and don't override the colors. */
}
.search-panel-status {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 18px;
  flex-wrap: wrap;
}
.search-panel-results {
  list-style: none;
  padding: 0;
  margin: 0;
  overflow-y: auto;
  flex: 1;
}
.search-panel-result {
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
}
.search-panel-result:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}
.search-panel-result-path {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
.search-panel-result-snippet {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 12px;
  margin: 2px 0 0 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: rgb(var(--v-theme-on-surface));
}
.search-panel-result-meta {
  font-size: 11px;
  margin: 2px 0 0 0;
  color: rgba(var(--v-theme-on-surface), 0.6);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.search-panel-spinner {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
