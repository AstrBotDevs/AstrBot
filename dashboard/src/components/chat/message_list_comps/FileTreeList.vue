<!-- Author: elecvoid243, 2026-07-12
     Spec: docs/superpowers/specs/2026-07-11-document-manager-design.md §3.1
     Reusable directory-tree component: breadcrumb + entry list.
     Reused by both FileBrowserView (workspace) and DocumentTreePanel
     (docs root). All tree-related local state (resize, collapse)
     stays in the parent. -->
<script setup lang="ts">
import { computed } from "vue";
import type { FileBrowserFetchState } from "@/composables/useSpcodeFileBrowser";
import type { SpcodeFileBrowserEntry } from "@/composables/parseSpcodeFileBrowser";
import FileBrowserBreadcrumb from "./FileBrowserBreadcrumb.vue";
import FileBrowserEntryList from "./FileBrowserEntryList.vue";

const props = defineProps<{
  state: FileBrowserFetchState;
  /** File currently being previewed (highlight in the list). */
  selectedPath: string | null;
  /** Absolute root of the workspace; null = project not loaded. */
  rootPath: string | null;
  /** When set, breadcrumb leaf uses the file icon (else folder). */
  previewPath: string | null;
  isDark: boolean;
  /**
   * Toggle the breadcrumb rendering. Default true (matches the
   * reused-in-tree-panel case). FileBrowserView uses two instances:
   * one above the split (breadcrumb only, :breadcrumb="true") and
   * one inside the left pane (entry-list only, :breadcrumb="false").
   * Minimal-viable interpretation of the brief's interface summary
   * (which listed `breadcrumb: boolean` but whose literal template
   * code elided the prop) — keeps the original layout without
   * duplicating the breadcrumb in two visible positions.
   */
  breadcrumb?: boolean;
  /**
   * Forwarded straight to FileBrowserEntryList. See that
   * component for the matching semantics. Undefined by default
   * so the workspace tab's FileBrowserView keeps its
   * "show everything" behaviour unchanged.
   */
  allowedExtensions?: string[];
}>();

const emit = defineEmits<{
  (e: "navigate", entry: SpcodeFileBrowserEntry): void;
  (e: "breadcrumb-navigate", path: string): void;
}>();

const showBreadcrumb = computed(
  () => (props.breadcrumb ?? true) && !!props.rootPath,
);
</script>

<template>
  <div class="file-tree-list">
    <FileBrowserBreadcrumb
      v-if="showBreadcrumb"
      :current-path="previewPath ?? (state.kind === 'directory' ? state.snapshot.meta.path : '')"
      :root-path="rootPath"
      :preview-path="previewPath"
      :is-dark="isDark"
      @navigate="emit('breadcrumb-navigate', $event)"
    />
    <FileBrowserEntryList
      :state="state"
      :selected-path="selectedPath"
      :allowed-extensions="allowedExtensions"
      @navigate="emit('navigate', $event)"
    />
  </div>
</template>

<style scoped>
.file-tree-list {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}
</style>
