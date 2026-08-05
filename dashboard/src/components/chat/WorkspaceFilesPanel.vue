<template>
  <transition name="workspace-panel-slide">
    <aside v-if="modelValue" class="workspace-files-panel">
      <div class="workspace-toolbar">
        <div class="workspace-filter">
          <Search :size="17" />
          <input
            v-model="filterQuery"
            type="search"
            :placeholder="tm('workspaceFiles.filter')"
          />
          <button
            v-if="filterQuery"
            type="button"
            :aria-label="tm('workspaceFiles.clearFilter')"
            @click="filterQuery = ''"
          >
            <X :size="15" />
          </button>
        </div>
        <div class="workspace-files-actions">
          <v-btn
            icon
            size="small"
            variant="text"
            :title="tm('workspaceFiles.refresh')"
            :loading="rootLoading"
            @click="refreshTree"
          >
            <RotateCw :size="17" />
          </v-btn>
          <v-btn
            icon
            size="small"
            variant="text"
            :title="tm('workspaceFiles.close')"
            @click="close"
          >
            <X :size="18" />
          </v-btn>
        </div>
      </div>

      <v-alert
        v-if="treeError"
        class="workspace-error"
        density="compact"
        type="error"
        variant="tonal"
      >
        {{ treeError }}
      </v-alert>

      <div
        class="workspace-tree"
        :class="{ 'workspace-tree--with-preview': selectedFilePath }"
      >
        <div v-if="rootLoading && !rootEntries.length" class="workspace-state">
          <v-progress-circular indeterminate size="24" width="2" />
        </div>
        <div v-else-if="!visibleEntries.length" class="workspace-state">
          {{
            filterQuery
              ? tm("workspaceFiles.noMatches")
              : tm("workspaceFiles.empty")
          }}
        </div>
        <template v-else>
          <button
            v-for="{ entry, depth } in visibleEntries"
            :key="entry.path"
            class="workspace-tree-row"
            :class="{
              'workspace-tree-row--active': selectedFilePath === entry.path,
            }"
            :style="{ paddingLeft: `${10 + depth * 18}px` }"
            type="button"
            :title="entry.path"
            @click="openEntry(entry)"
          >
            <span class="workspace-tree-chevron">
              <v-progress-circular
                v-if="entry.loading"
                indeterminate
                size="14"
                width="2"
              />
              <ChevronDown
                v-else-if="entry.type === 'directory' && entry.expanded"
                :size="16"
              />
              <ChevronRight v-else-if="entry.type === 'directory'" :size="16" />
            </span>
            <FolderOpen
              v-if="entry.type === 'directory' && entry.expanded"
              :size="17"
              class="workspace-folder-icon"
            />
            <Folder
              v-else-if="entry.type === 'directory'"
              :size="17"
              class="workspace-folder-icon"
            />
            <FileText v-else :size="16" class="workspace-file-icon" />
            <span class="workspace-tree-name">{{ entry.name }}</span>
            <span v-if="entry.type === 'file'" class="workspace-tree-size">
              {{ formatSize(entry.size) }}
            </span>
          </button>
        </template>
      </div>

      <section v-if="selectedFilePath" class="workspace-preview">
        <header class="workspace-preview-header">
          <div class="workspace-preview-path" :title="selectedFilePath">
            {{ selectedFilePath }}
          </div>
          <div class="workspace-preview-actions">
            <v-btn
              icon
              size="x-small"
              variant="text"
              :title="tm('workspaceFiles.download')"
              :loading="fileDownloading"
              @click="downloadSelectedFile"
            >
              <Download :size="16" />
            </v-btn>
            <v-btn
              icon
              size="x-small"
              variant="text"
              :title="tm('workspaceFiles.dialogPreview')"
              @click="previewDialog = true"
            >
              <Maximize2 :size="15" />
            </v-btn>
            <v-btn
              icon
              size="x-small"
              variant="text"
              :title="tm('workspaceFiles.closePreview')"
              @click="clearPreview"
            >
              <X :size="16" />
            </v-btn>
          </div>
        </header>
        <div v-if="fileLoading" class="workspace-preview-state">
          <v-progress-circular indeterminate size="24" width="2" />
        </div>
        <div v-else-if="fileError" class="workspace-preview-state">
          {{ fileError }}
        </div>
        <pre
          v-else
          class="workspace-preview-content"
        ><code>{{ fileContent }}</code></pre>
      </section>

      <v-dialog v-model="previewDialog" max-width="1000" width="calc(100% - 32px)">
        <v-card class="workspace-dialog-preview">
          <header class="workspace-dialog-preview-header">
            <div class="workspace-preview-path" :title="selectedFilePath">
              {{ selectedFilePath }}
            </div>
            <div class="workspace-preview-actions">
              <v-btn
                icon
                variant="text"
                :title="tm('workspaceFiles.download')"
                :loading="fileDownloading"
                @click="downloadSelectedFile"
              >
                <Download :size="18" />
              </v-btn>
              <v-btn
                icon
                variant="text"
                :title="tm('workspaceFiles.closeDialogPreview')"
                @click="previewDialog = false"
              >
                <X :size="20" />
              </v-btn>
            </div>
          </header>
          <div v-if="fileLoading" class="workspace-preview-state">
            <v-progress-circular indeterminate size="28" width="2" />
          </div>
          <div v-else-if="fileError" class="workspace-preview-state">
            {{ fileError }}
          </div>
          <pre
            v-else
            class="workspace-preview-content workspace-dialog-preview-content"
          ><code>{{ fileContent }}</code></pre>
        </v-card>
      </v-dialog>
    </aside>
  </transition>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Folder,
  FolderOpen,
  Maximize2,
  RotateCw,
  Search,
  X,
} from "@lucide/vue";
import { chatApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";

interface WorkspaceEntry {
  name: string;
  path: string;
  type: "directory" | "file";
  size: number;
  readable: boolean;
  children?: WorkspaceEntry[];
  expanded?: boolean;
  loading?: boolean;
}

const props = defineProps<{
  modelValue: boolean;
  projectId: string;
  projectTitle?: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const { tm } = useModuleI18n("features/chat");
const rootEntries = ref<WorkspaceEntry[]>([]);
const loadedProjectId = ref("");
const rootLoading = ref(false);
const treeError = ref("");
const filterQuery = ref("");
const selectedFilePath = ref("");
const fileContent = ref("");
const fileLoading = ref(false);
const fileError = ref("");
const fileDownloading = ref(false);
const previewDialog = ref(false);
const treeGeneration = ref(0);
const fileGeneration = ref(0);

const visibleEntries = computed(() => {
  const query = filterQuery.value.trim().toLocaleLowerCase();
  const flattened: Array<{ entry: WorkspaceEntry; depth: number }> = [];

  const visit = (entries: WorkspaceEntry[], depth: number) => {
    entries.forEach((entry) => {
      if (
        !query ||
        entry.type === "directory" ||
        entry.name.toLocaleLowerCase().includes(query)
      ) {
        flattened.push({ entry, depth });
      }
      if (entry.type === "directory" && entry.expanded && entry.children) {
        visit(entry.children, depth + 1);
      }
    });
  };

  visit(rootEntries.value, 0);
  return flattened;
});

watch(
  () => [props.modelValue, props.projectId] as const,
  async ([open, projectId], previous) => {
    if (!open || !projectId) return;
    const previousProjectId = previous?.[1];
    if (
      projectId !== previousProjectId ||
      loadedProjectId.value !== projectId
    ) {
      resetPanel();
      await loadDirectory("");
    }
  },
  { immediate: true },
);

function close() {
  emit("update:modelValue", false);
}

function resetPanel() {
  treeGeneration.value += 1;
  rootEntries.value = [];
  loadedProjectId.value = "";
  rootLoading.value = false;
  treeError.value = "";
  filterQuery.value = "";
  clearPreview();
}

function clearPreview() {
  fileGeneration.value += 1;
  previewDialog.value = false;
  selectedFilePath.value = "";
  fileContent.value = "";
  fileError.value = "";
  fileLoading.value = false;
}

async function refreshTree() {
  resetPanel();
  if (props.projectId) {
    await loadDirectory("");
  }
}

async function loadDirectory(path: string, parent?: WorkspaceEntry) {
  if (!props.projectId || rootLoading.value || parent?.loading) return;
  const projectId = props.projectId;
  const generation = treeGeneration.value;
  if (parent) {
    parent.loading = true;
  } else {
    rootLoading.value = true;
  }
  treeError.value = "";
  try {
    const response = await chatApi.listProjectWorkspaceFiles(projectId, path);
    if (generation !== treeGeneration.value || projectId !== props.projectId) {
      return;
    }
    if (response.data?.status !== "ok") {
      throw new Error(
        response.data?.message || tm("workspaceFiles.loadFailed"),
      );
    }
    const entries = (
      (response.data?.data?.entries || []) as WorkspaceEntry[]
    ).map((entry) => ({ ...entry }));
    if (parent) {
      parent.children = entries;
    } else {
      rootEntries.value = entries;
      loadedProjectId.value = projectId;
    }
  } catch (error) {
    if (generation !== treeGeneration.value || projectId !== props.projectId) {
      return;
    }
    treeError.value =
      (error as any)?.response?.data?.message ||
      (error as Error)?.message ||
      tm("workspaceFiles.loadFailed");
    if (parent) {
      parent.expanded = false;
    }
  } finally {
    if (generation === treeGeneration.value && projectId === props.projectId) {
      if (parent) {
        parent.loading = false;
      } else {
        rootLoading.value = false;
      }
    }
  }
}

async function openEntry(entry: WorkspaceEntry) {
  if (entry.type === "directory") {
    entry.expanded = !entry.expanded;
    if (entry.expanded && !entry.children) {
      await loadDirectory(entry.path, entry);
    }
    return;
  }

  selectedFilePath.value = entry.path;
  fileContent.value = "";
  fileError.value = "";
  fileLoading.value = false;
  fileGeneration.value += 1;
  const generation = fileGeneration.value;
  const projectId = props.projectId;
  if (!entry.readable) {
    fileError.value = tm("workspaceFiles.tooLarge");
    return;
  }

  fileLoading.value = true;
  try {
    const response = await chatApi.getProjectWorkspaceFile(
      projectId,
      entry.path,
    );
    if (generation !== fileGeneration.value || projectId !== props.projectId) {
      return;
    }
    if (response.data?.status !== "ok") {
      throw new Error(
        response.data?.message || tm("workspaceFiles.previewFailed"),
      );
    }
    fileContent.value = response.data?.data?.content || "";
  } catch (error) {
    if (generation !== fileGeneration.value || projectId !== props.projectId) {
      return;
    }
    fileError.value =
      (error as any)?.response?.data?.message ||
      (error as Error)?.message ||
      tm("workspaceFiles.previewFailed");
  } finally {
    if (generation === fileGeneration.value && projectId === props.projectId) {
      fileLoading.value = false;
    }
  }
}

async function downloadSelectedFile() {
  if (
    !props.projectId ||
    !selectedFilePath.value ||
    fileDownloading.value
  ) {
    return;
  }
  fileDownloading.value = true;
  try {
    const response = await chatApi.downloadProjectWorkspaceFile(
      props.projectId,
      selectedFilePath.value,
    );
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = selectedFilePath.value.split("/").pop() || "download";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  } catch {
    fileError.value = tm("workspaceFiles.downloadFailed");
  } finally {
    fileDownloading.value = false;
  }
}

function formatSize(size: number) {
  if (!Number.isFinite(size) || size < 1024) return `${size || 0} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 102.4) / 10} KB`;
  return `${Math.round(size / (1024 * 102.4)) / 10} MB`;
}
</script>

<style scoped>
.workspace-files-panel {
  width: clamp(340px, 29vw, 440px);
  height: calc(100% - var(--chat-panel-top-offset, 0px));
  margin-top: var(--chat-panel-top-offset, 0px);
  border-left: 1px solid var(--chat-border, rgba(var(--v-border-color), 0.14));
  background: var(--chat-page-bg, rgb(var(--v-theme-surface)));
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  flex-direction: column;
  flex: 0 0 auto;
  min-width: 0;
}

.workspace-panel-slide-enter-active,
.workspace-panel-slide-leave-active {
  transition:
    transform 0.2s ease,
    opacity 0.2s ease;
}

.workspace-panel-slide-enter-from,
.workspace-panel-slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.workspace-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.workspace-toolbar {
  min-height: 52px;
  padding: 8px 8px 8px 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.workspace-files-actions {
  min-width: 0;
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 2px;
}

.workspace-filter {
  height: 36px;
  min-width: 0;
  flex: 1;
  padding: 0 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  border-radius: 9px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(var(--v-theme-on-surface), 0.52);
}

.workspace-filter:focus-within {
  border-color: rgba(var(--v-theme-on-surface), 0.32);
}

.workspace-filter input {
  min-width: 0;
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  font: inherit;
  font-size: 13px;
}

.workspace-filter input::-webkit-search-cancel-button {
  display: none;
}

.workspace-filter button {
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: inherit;
  display: grid;
  place-items: center;
  cursor: pointer;
}

.workspace-filter button:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.workspace-error {
  margin: 0 12px 8px;
  font-size: 12px;
}

.workspace-tree {
  min-height: 0;
  flex: 1 1 auto;
  overflow: auto;
  padding: 2px 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.workspace-tree--with-preview {
  flex: 0 1 42%;
  min-height: 140px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
}

.workspace-state,
.workspace-preview-state {
  min-height: 110px;
  padding: 20px;
  display: grid;
  place-items: center;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 13px;
  text-align: center;
}

.workspace-tree-row {
  width: 100%;
  height: 30px;
  padding-right: 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  text-align: left;
}

.workspace-tree-row:hover,
.workspace-tree-row--active {
  background: rgba(var(--v-theme-on-surface), 0.07);
}

.workspace-tree-chevron {
  width: 16px;
  height: 18px;
  flex: 0 0 16px;
  display: grid;
  place-items: center;
  color: rgba(var(--v-theme-on-surface), 0.58);
}

.workspace-folder-icon {
  flex: 0 0 auto;
  color: #d5a84a;
}

.workspace-file-icon {
  flex: 0 0 auto;
  color: rgba(var(--v-theme-on-surface), 0.58);
}

.workspace-tree-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-tree-size {
  flex: 0 0 auto;
  color: rgba(var(--v-theme-on-surface), 0.42);
  font-size: 10px;
}

.workspace-preview {
  min-height: 0;
  flex: 1 1 58%;
  display: flex;
  flex-direction: column;
}

.workspace-preview-header {
  min-height: 40px;
  padding: 4px 8px 4px 14px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.workspace-preview-path {
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-preview-actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 2px;
}

.workspace-preview-state {
  flex: 1;
}

.workspace-preview-content {
  min-height: 0;
  flex: 1;
  margin: 0;
  overflow: auto;
  padding: 12px 14px 20px;
  background: rgba(var(--v-theme-on-surface), 0.025);
  color: rgb(var(--v-theme-on-surface));
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.55;
  tab-size: 2;
  white-space: pre;
}

.workspace-dialog-preview {
  height: min(78vh, 760px);
  background: var(--chat-page-bg, rgb(var(--v-theme-surface)));
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  flex-direction: column;
}

.workspace-dialog-preview-header {
  min-height: 56px;
  padding: 6px 10px 6px 20px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.workspace-dialog-preview-content {
  padding: 20px 24px 32px;
}

@media (max-width: 760px) {
  .workspace-files-panel {
    position: fixed;
    inset: 0;
    z-index: 1300;
    width: 100vw;
    height: 100dvh;
    margin-top: 0;
    border-left: 0;
  }

  .workspace-toolbar {
    min-height: calc(52px + env(safe-area-inset-top));
    padding: calc(8px + env(safe-area-inset-top)) 8px 8px 12px;
    border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  }

  .workspace-tree--with-preview {
    min-height: 160px;
  }
}
</style>
