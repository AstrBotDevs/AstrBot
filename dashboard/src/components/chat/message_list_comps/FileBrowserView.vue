<!-- Author: elecvoid243, 2026-06-20
     Spec: docs/superpowers/specs/2026-06-20-git-diff-sidebar-file-browser-design.md §4.3 -->
<script setup lang="ts">
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { useSpcodeProjectStatus } from "@/composables/useSpcodeProjectStatus";
import { useSpcodeFileBrowser } from "@/composables/useSpcodeFileBrowser";
import FileBrowserBreadcrumb from "./FileBrowserBreadcrumb.vue";
import FileBrowserEntryList from "./FileBrowserEntryList.vue";
import FileBrowserFilePreview from "./FileBrowserFilePreview.vue";

const props = defineProps<{
  currentPath: string;
  isDark?: boolean;
  /** Current worktree root (parent computes: selectedWorktree ?? mainWorktreePath). null = project not loaded. */
  rootPath: string | null;
}>();
const emit = defineEmits<{ (e: "navigate", path: string): void }>();

const { tm } = useModuleI18n("features/chat");
const spcodeStatus = useSpcodeProjectStatus();

const fileBrowserComposable = useSpcodeFileBrowser(
  computed(() => props.currentPath),
);
</script>

<template>
  <div class="file-browser-view">
    <div v-if="!spcodeStatus.status.value.loaded" class="file-browser-empty">
      <v-icon size="36" color="grey">mdi-folder-open-outline</v-icon>
      <span class="empty-text">{{ tm("spcodeProjectLoad.fileBrowser.placeholder") }}</span>
    </div>

    <template v-else>
      <FileBrowserBreadcrumb
        :current-path="currentPath"
        :root-path="rootPath"
        @navigate="(p) => emit('navigate', p)"
      />

      <div class="file-browser-body">
        <FileBrowserEntryList
          :state="fileBrowserComposable.state.value"
          @navigate="(p) => emit('navigate', p)"
        />

        <div class="file-browser-divider" />

        <FileBrowserFilePreview
          :state="fileBrowserComposable.state.value"
          :is-dark="!!isDark"
          @navigate-target="(p) => emit('navigate', p)"
          @retry="() => fileBrowserComposable.refresh()"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.file-browser-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.file-browser-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.file-browser-divider {
  width: 1px;
  background: rgba(var(--v-theme-on-surface), 0.1);
  flex-shrink: 0;
}
.file-browser-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px 16px;
  min-height: 200px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.empty-text { font-size: 14px; }

/* Mobile: stack the two panes vertically. */
@media (max-width: 760px) {
  .file-browser-body {
    flex-direction: column;
  }
  .file-browser-divider {
    width: auto;
    height: 1px;
  }
  :deep(.file-browser-entry-list) {
    flex: 0 0 auto;
    max-height: 40vh;
    min-width: 0;
  }
  :deep(.file-browser-preview) {
    flex: 1 1 auto;
  }
}
</style>