<script setup lang="ts">
// Author: elecvoid243
// Date: 2026-06-25
// Spec: docs/superpowers/specs/2026-06-25-git-show-design.md §3.4
//
// Per-file patch panel rendered inline below a file row in
// GitLogView. Switches between five states based on the
// ``GitShowFileFetchState`` from useSpcodeGitShow:
//
//   idle     → no-op (parent should not render this state)
//   loading  → centered spinner
//   error    → reason text + Retry button (re-fetches on click)
//   ok + is_binary           → "binary file" fallback
//   ok + status="unknown"    → "no diff" fallback (path not in this ref)
//   ok + patch !== null      → DiffPreview with the unified diff
//
// The component is purely presentational: it does not own any
// network state. The parent composable (passed via props) owns the
// cache, the in-flight controller and the ETag. This keeps the
// panel testable in isolation and avoids prop-drilling handlers.

import { computed } from "vue";
import { useCustomizerStore } from "@/stores/customizer";
import { useModuleI18n } from "@/i18n/composables";
import type { GitShowFileFetchState } from "@/composables/useSpcodeGitShow";
import type { GitShowFileView } from "@/composables/parseSpcodeGitShow";
import DiffPreview from "./DiffPreview.vue";

const { tm } = useModuleI18n("features/chat");
// v3.9 (2026-06-25, elecvoid243): read `isDark` from the customizer
// store's getter (the same one Chat.vue / ChatInput use). Reading it
// in place rather than accepting a prop avoids one layer of
// prop-drilling and matches how the rest of the dashboard resolves
// the active theme. An optional `isDark` prop is still accepted for
// callers that want to override (e.g. tests or preview tooling) —
// when provided it wins.
const customizer = useCustomizerStore();
const isDarkFromStore = computed(() => customizer.isDark);

const props = defineProps<{
  /** Commit SHA (for keys / i18n context; the parent owns the state). */
  sha: string;
  /** File path inside the commit (the parent already validates this). */
  path: string;
  /** Per-(sha, path) state from the composable. */
  state: GitShowFileFetchState;
  /** Cached patch view. null when the parent has not fetched yet. */
  data: GitShowFileView | null;
  /**
   * Forwarded to `<DiffPreview :is-dark>` so the unified diff uses
   * the high-contrast add/del palette in dark mode. v3.9 (2026-06-25,
   * elecvoid243): GitLogView was previously passing nothing, so
   * DiffPreview always rendered in its light palette — invisible add/
   * del backgrounds in dark mode. The git-diff sidebar path
   * (GitDiffFileItem) already does this; we just plug the same
   * channel into the history view.
   */
  isDark?: boolean;
}>();

const emit = defineEmits<{
  (e: "retry"): void;
}>();

// Derived boolean flags for the template. `isBinary` and
// `status === "unknown"` both yield a non-diff fallback, so we
// surface a single `fallback` reason to the template.
const isLoading = computed(() => props.state.kind === "loading");
const errorReason = computed(() =>
  props.state.kind === "error" ? props.state.reason : null,
);
const okView = computed(() =>
  props.state.kind === "ok" ? props.state.data : null,
);

// Decide which fallback to show. Binary is its own message; unknown
// (path not in this ref, e.g. user passed a typo) gets a separate
// placeholder so the UI does not look like a generic "no data" page.
const fallbackKind = computed<"binary" | "unknown" | null>(() => {
  const v = okView.value;
  if (!v) return null;
  if (v.isBinary) return "binary";
  if (v.status === "unknown" || v.patch === null) return "unknown";
  return null;
});
</script>

<template>
  <div class="file-patch-panel" :data-sha="sha" :data-path="path">
    <!-- loading: spinner + label. Centered to match the surrounding
         file row height so the panel does not visually jump. -->
    <div v-if="isLoading" class="file-patch-panel-loading" role="status">
      <v-progress-circular indeterminate size="18" width="2" />
      <span class="file-patch-panel-loading-text">
        {{
          tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.loadingPatch")
        }}
      </span>
    </div>

    <!-- error: reason + retry. The reason is rendered via the same
         error.reason.* key the rest of the sidebar uses, so the user
         sees consistent messages (e.g. "Network error"). -->
    <div v-else-if="errorReason" class="file-patch-panel-error" role="alert">
      <span class="file-patch-panel-error-text">
        {{
          tm(
            `spcodeProjectLoad.diffSidebar.gitWorkflow.error.reason.${errorReason}`,
            { reason: errorReason },
          )
        }}
      </span>
      <button class="file-patch-panel-retry" @click="emit('retry')">
        {{ tm("spcodeProjectLoad.diffSidebar.error.retry") }}
      </button>
    </div>

    <!-- binary / unknown: a single placeholder. Two distinct
         messages so the user can tell "this file is binary"
         apart from "this path was not in the commit". -->
    <div
      v-else-if="fallbackKind === 'binary'"
      class="file-patch-panel-fallback"
    >
      <v-icon size="16" class="file-patch-panel-fallback-icon">
        mdi-file-document-outline
      </v-icon>
      <span>
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.binaryFile") }}
      </span>
    </div>
    <div
      v-else-if="fallbackKind === 'unknown'"
      class="file-patch-panel-fallback"
    >
      <v-icon size="16" class="file-patch-panel-fallback-icon">
        mdi-alert-circle-outline
      </v-icon>
      <span>
        {{ tm("spcodeProjectLoad.diffSidebar.gitWorkflow.history.emptyPatch") }}
      </span>
    </div>

    <!-- ok: render the unified diff. We always pass `filePath` so
         DiffPreview's header (when present) shows the full path. -->
    <div
      v-else-if="okView && okView.patch !== null"
      class="file-patch-panel-diff"
    >
      <DiffPreview
        :content="okView.patch"
        :file-path="okView.path"
        :max-lines="200"
        :max-chars="20000"
        :collapsible="true"
        :is-dark="isDark ?? isDarkFromStore"
      />
    </div>
  </div>
</template>

<style scoped>
.file-patch-panel {
  /* Nested under the file row, so we tighten padding/margin and
     let the parent's "git-log-files-item" handle its own borders. */
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 8px 8px 28px; /* left indent = 14px icon + 14px badge */
  background: rgba(127, 127, 127, 0.04);
  border-bottom: 1px solid rgba(127, 127, 127, 0.12);
}

.file-patch-panel-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: rgba(127, 127, 127, 0.9);
}
.file-patch-panel-loading-text {
  white-space: nowrap;
}

.file-patch-panel-error {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: rgb(var(--v-theme-error));
}
.file-patch-panel-error-text {
  flex: 1 1 auto;
  min-width: 0;
  word-break: break-word;
}
.file-patch-panel-retry {
  flex: 0 0 auto;
  background: transparent;
  border: 1px solid currentColor;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 12px;
  color: inherit;
  cursor: pointer;
}
.file-patch-panel-retry:hover {
  background: rgba(127, 127, 127, 0.08);
}

.file-patch-panel-fallback {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: rgba(127, 127, 127, 0.9);
  font-style: italic;
}
.file-patch-panel-fallback-icon {
  flex: 0 0 auto;
  opacity: 0.75;
}

.file-patch-panel-diff {
  /* DiffPreview is self-contained; we just need to neutralize the
     outer padding the file row would otherwise inherit. */
  margin: 0;
  padding: 0;
}
</style>
