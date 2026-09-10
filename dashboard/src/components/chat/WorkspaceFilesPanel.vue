<template>
  <transition name="chat-panel">
    <aside
      v-if="modelValue"
      class="workspace-files-panel chat-side-panel"
      :class="{ 'has-preview': openFiles.length }"
      :aria-label="tm('workspaceFiles.title')"
    >
      <header class="workspace-tabs-header">
        <div
          ref="tabList"
          class="workspace-tabs"
          role="tablist"
          :aria-label="tm('workspaceFiles.openTabs')"
          @keydown="handleTabKeydown"
        >
          <button
            class="workspace-tab workspace-files-tab"
            type="button"
            role="tab"
            :aria-selected="!selectedFilePath"
            :tabindex="selectedFilePath ? -1 : 0"
            @click="
              clearPreview();
              treeCollapsed = false;
            "
          >
            <FolderOpen :size="16" />
            <span>{{ tm("workspaceFiles.title") }}</span>
          </button>
          <div
            v-for="file in openFiles"
            :key="file.path"
            class="workspace-file-tab"
            :class="{
              active: selectedFilePath === file.path,
              'is-preview': previewFilePath === file.path,
            }"
          >
            <button
              class="workspace-tab"
              type="button"
              role="tab"
              :title="file.path"
              :aria-selected="selectedFilePath === file.path"
              :tabindex="selectedFilePath === file.path ? 0 : -1"
              @click="openEntry(file)"
              @dblclick="pinPreview(file.path)"
            >
              <FileText :size="15" />
              <span>{{ file.name }}</span>
            </button>
            <button
              type="button"
              class="workspace-tab-close"
              :aria-label="tm('workspaceFiles.closeTab', { name: file.name })"
              @click="closeFile(file.path)"
            >
              <X :size="13" />
            </button>
          </div>
        </div>
        <v-btn
          icon
          size="x-small"
          variant="text"
          :title="tm('workspaceFiles.close')"
          :aria-label="tm('workspaceFiles.close')"
          @click="close"
          ><X :size="17"
        /></v-btn>
      </header>

      <div class="workspace-path-bar">
        <div
          class="workspace-breadcrumbs"
          :title="selectedFilePath || projectTitle"
        >
          <span v-if="projectTitle" class="workspace-project-name">{{
            projectTitle
          }}</span>
          <template
            v-for="(part, index) in selectedFilePath.split('/').filter(Boolean)"
            :key="index"
          >
            <ChevronRight v-if="projectTitle || index" :size="12" />
            <span
              :class="{
                'is-filename': index === selectedFilePath.split('/').length - 1,
              }"
              >{{ part }}</span
            >
          </template>
        </div>
        <div class="workspace-preview-actions">
          <v-btn
            v-if="selectedFilePath"
            icon
            size="x-small"
            variant="text"
            :loading="fileDownloading"
            :title="tm('workspaceFiles.download')"
            :aria-label="tm('workspaceFiles.download')"
            @click="downloadSelectedFile"
            ><Download :size="16"
          /></v-btn>
          <v-btn
            v-if="selectedFilePath"
            icon
            size="x-small"
            variant="text"
            :title="tm('workspaceFiles.dialogPreview')"
            :aria-label="tm('workspaceFiles.dialogPreview')"
            @click="
              pinPreview();
              previewDialog = true;
            "
            ><Maximize2 :size="15"
          /></v-btn>
          <v-btn
            v-if="openFiles.length"
            icon
            size="x-small"
            variant="text"
            :aria-expanded="!treeCollapsed"
            :title="
              tm(
                treeCollapsed
                  ? 'workspaceFiles.showTree'
                  : 'workspaceFiles.hideTree',
              )
            "
            :aria-label="
              tm(
                treeCollapsed
                  ? 'workspaceFiles.showTree'
                  : 'workspaceFiles.hideTree',
              )
            "
            @click="treeCollapsed = !treeCollapsed"
          >
            <PanelRightOpen v-if="treeCollapsed" :size="17" /><PanelRightClose
              v-else
              :size="17"
            />
          </v-btn>
        </div>
      </div>

      <div class="workspace-body">
        <section
          v-if="openFiles.length"
          class="workspace-preview"
          role="tabpanel"
          tabindex="0"
          :aria-label="selectedFilePath || tm('workspaceFiles.title')"
          @pointerdown="pinPreview()"
          @wheel.passive="pinPreview()"
          @keydown="pinPreview()"
        >
          <div v-if="!selectedFilePath" class="workspace-preview-empty">
            <Files :size="32" :stroke-width="1.25" />
            <span>{{ tm("workspaceFiles.selectFile") }}</span>
          </div>
          <div v-else-if="fileLoading" class="workspace-preview-state">
            <v-progress-circular indeterminate size="24" width="2" />
          </div>
          <div
            v-else-if="fileError"
            class="workspace-preview-state"
            role="alert"
          >
            {{ fileError }}
          </div>
          <WorkspacePdfPreview
            v-else-if="pdfFile && !previewDialog"
            v-model:page="pdfPage"
            v-model:zoom="pdfZoom"
            :file="pdfFile"
          />
          <div v-else-if="!pdfFile" class="workspace-code-view">
            <pre class="workspace-line-numbers" aria-hidden="true">{{
              lineNumbers
            }}</pre>
            <pre
              class="workspace-preview-content"
            ><code>{{ fileContent }}</code></pre>
          </div>
        </section>

        <button
          v-if="openFiles.length && !treeCollapsed"
          class="workspace-tree-scrim"
          type="button"
          :aria-label="tm('workspaceFiles.hideTree')"
          @click="treeCollapsed = true"
        />
        <section
          v-show="!treeCollapsed || !openFiles.length"
          class="workspace-tree-pane"
          :aria-label="tm('workspaceFiles.title')"
        >
          <div class="workspace-tree-toolbar">
            <div class="workspace-filter">
              <Search :size="15" />
              <input
                v-model="filterQuery"
                type="search"
                :placeholder="tm('workspaceFiles.filter')"
                :aria-label="tm('workspaceFiles.filter')"
              />
              <button
                v-if="filterQuery"
                type="button"
                :aria-label="tm('workspaceFiles.clearFilter')"
                @click="filterQuery = ''"
              >
                <X :size="13" />
              </button>
            </div>
            <v-btn
              icon
              size="x-small"
              variant="text"
              :loading="rootLoading"
              :title="tm('workspaceFiles.refresh')"
              :aria-label="tm('workspaceFiles.refresh')"
              @click="refreshTree"
              ><RotateCw :size="15"
            /></v-btn>
          </div>
          <v-alert
            v-if="treeError"
            class="workspace-error"
            density="compact"
            type="error"
            variant="tonal"
            >{{ treeError }}</v-alert
          >
          <div class="workspace-tree">
            <div
              v-if="rootLoading && !rootEntries.length"
              class="workspace-state"
            >
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
                :style="{ paddingLeft: `${8 + depth * 16}px` }"
                type="button"
                :title="entry.path"
                :aria-expanded="
                  entry.type === 'directory'
                    ? Boolean(entry.expanded)
                    : undefined
                "
                @click="openEntry(entry)"
                @dblclick="entry.type === 'file' && pinPreview(entry.path)"
              >
                <span class="workspace-tree-chevron">
                  <v-progress-circular
                    v-if="entry.loading"
                    indeterminate
                    size="13"
                    width="2"
                  />
                  <ChevronDown
                    v-else-if="entry.type === 'directory' && entry.expanded"
                    :size="14"
                  />
                  <ChevronRight
                    v-else-if="entry.type === 'directory'"
                    :size="14"
                  />
                </span>
                <FolderOpen
                  v-if="entry.type === 'directory' && entry.expanded"
                  :size="16"
                  class="workspace-folder-icon"
                />
                <Folder
                  v-else-if="entry.type === 'directory'"
                  :size="16"
                  class="workspace-folder-icon"
                />
                <FileText v-else :size="15" class="workspace-file-icon" />
                <span class="workspace-tree-name">{{ entry.name }}</span>
                <span
                  v-if="entry.type === 'file'"
                  class="workspace-tree-size"
                  >{{ formatSize(entry.size) }}</span
                >
              </button>
            </template>
          </div>
        </section>
      </div>

      <v-dialog
        v-model="previewDialog"
        max-width="1200"
        width="calc(100% - 32px)"
      >
        <v-card class="workspace-dialog-preview">
          <v-card-title
            class="text-h3 pa-4 pb-0 pl-6 workspace-dialog-preview-header"
          >
            <span class="workspace-preview-path" :title="selectedFilePath">{{
              selectedFilePath.split("/").pop()
            }}</span>
            <div class="workspace-preview-actions">
              <v-btn
                icon
                variant="text"
                :title="tm('workspaceFiles.download')"
                :aria-label="tm('workspaceFiles.download')"
                :loading="fileDownloading"
                @click="downloadSelectedFile"
                ><Download :size="18"
              /></v-btn>
              <v-btn
                icon
                variant="text"
                :title="tm('workspaceFiles.closeDialogPreview')"
                :aria-label="tm('workspaceFiles.closeDialogPreview')"
                @click="previewDialog = false"
                ><X :size="20"
              /></v-btn>
            </div>
          </v-card-title>
          <div v-if="fileLoading" class="workspace-preview-state">
            <v-progress-circular indeterminate size="28" width="2" />
          </div>
          <div v-else-if="fileError" class="workspace-preview-state">
            {{ fileError }}
          </div>
          <WorkspacePdfPreview
            v-else-if="pdfFile && previewDialog"
            v-model:page="pdfPage"
            v-model:zoom="pdfZoom"
            :file="pdfFile"
          />
          <div v-else-if="!pdfFile" class="workspace-code-view">
            <pre class="workspace-line-numbers" aria-hidden="true">{{
              lineNumbers
            }}</pre>
            <pre
              class="workspace-preview-content"
            ><code>{{ fileContent }}</code></pre>
          </div>
        </v-card>
      </v-dialog>
    </aside>
  </transition>
</template>

<script setup lang="ts">
import "@/components/chat/chatPanelTransition.css";
import {
  computed,
  defineAsyncComponent,
  nextTick,
  onBeforeUnmount,
  ref,
  shallowRef,
  watch,
} from "vue";
import {
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Files,
  Folder,
  FolderOpen,
  Maximize2,
  PanelRightClose,
  PanelRightOpen,
  RotateCw,
  Search,
  X,
} from "@lucide/vue";
import { chatApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";

const WorkspacePdfPreview = defineAsyncComponent(
  () => import("./WorkspacePdfPreview.vue"),
);
const PDF_PREVIEW_MAX_BYTES = 50 * 1024 * 1024;

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
const openFiles = ref<WorkspaceEntry[]>([]);
const previewFilePath = ref("");
const tabList = ref<HTMLElement | null>(null);
const treeCollapsed = ref(false);
const fileContent = ref("");
const lineNumbers = computed(() =>
  fileContent.value
    .split("\n")
    .map((_, index) => index + 1)
    .join("\n"),
);
const pdfFile = shallowRef<Blob | null>(null);
const pdfPage = ref(1);
const pdfZoom = ref(1);
let fileAbort: AbortController | undefined;
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
    if (!open || !projectId) {
      clearPreview();
      openFiles.value = [];
      previewFilePath.value = "";
      treeCollapsed.value = false;
      return;
    }
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

onBeforeUnmount(clearPreview);

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
  openFiles.value = [];
  previewFilePath.value = "";
  treeCollapsed.value = false;
  clearPreview();
}

function pinPreview(path = selectedFilePath.value) {
  if (previewFilePath.value === path) previewFilePath.value = "";
}

async function closeFile(path: string) {
  const index = openFiles.value.findIndex((file) => file.path === path);
  if (index < 0) return;
  openFiles.value.splice(index, 1);
  if (previewFilePath.value === path) previewFilePath.value = "";
  if (selectedFilePath.value === path) {
    const next = openFiles.value[Math.min(index, openFiles.value.length - 1)];
    if (next) await openEntry(next);
    else clearPreview();
  }
  if (!openFiles.value.length) treeCollapsed.value = false;
}

function handleTabKeydown(event: KeyboardEvent) {
  if ((event.target as HTMLElement).getAttribute("role") !== "tab") return;
  const tabs = Array.from(
    (event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>(
      '[role="tab"]',
    ),
  );
  const current = tabs.indexOf(event.target as HTMLButtonElement);
  let index = current;
  if (event.key === "ArrowRight") index = (current + 1) % tabs.length;
  else if (event.key === "ArrowLeft")
    index = (current - 1 + tabs.length) % tabs.length;
  else if (event.key === "Home") index = 0;
  else if (event.key === "End") index = tabs.length - 1;
  else return;
  event.preventDefault();
  tabs[index]?.focus();
  tabs[index]?.click();
}

function clearPreview() {
  fileAbort?.abort();
  fileAbort = undefined;
  fileGeneration.value += 1;
  previewDialog.value = false;
  selectedFilePath.value = "";
  fileContent.value = "";
  pdfFile.value = null;
  pdfPage.value = 1;
  pdfZoom.value = 1;
  fileError.value = "";
  fileLoading.value = false;
}

async function refreshTree() {
  treeGeneration.value += 1;
  rootEntries.value = [];
  rootLoading.value = false;
  treeError.value = "";
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

  if (selectedFilePath.value === entry.path && !fileError.value) return;
  if (!openFiles.value.some((file) => file.path === entry.path)) {
    const previewIndex = openFiles.value.findIndex(
      (file) => file.path === previewFilePath.value,
    );
    if (previewIndex >= 0)
      openFiles.value.splice(previewIndex, 1, { ...entry });
    else openFiles.value.push({ ...entry });
    previewFilePath.value = entry.path;
  }
  clearPreview();
  selectedFilePath.value = entry.path;
  if (window.matchMedia("(max-width: 760px)").matches)
    treeCollapsed.value = true;
  void nextTick(() => {
    tabList.value
      ?.querySelector('[role="tab"][aria-selected="true"]')
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  });
  const generation = fileGeneration.value;
  const projectId = props.projectId;
  const isPdf = entry.path.toLowerCase().endsWith(".pdf");
  if (isPdf ? entry.size > PDF_PREVIEW_MAX_BYTES : !entry.readable) {
    fileError.value = tm(
      isPdf ? "workspaceFiles.pdf.tooLarge" : "workspaceFiles.tooLarge",
    );
    return;
  }

  fileLoading.value = true;
  try {
    if (isPdf) {
      fileAbort = new AbortController();
      const response = await chatApi.downloadProjectWorkspaceFile(
        projectId,
        entry.path,
        fileAbort.signal,
      );
      if (generation !== fileGeneration.value || projectId !== props.projectId)
        return;
      if (response.data.size > PDF_PREVIEW_MAX_BYTES) {
        throw new Error(tm("workspaceFiles.pdf.tooLarge"));
      }
      pdfFile.value = response.data;
      return;
    }
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
  if (!props.projectId || !selectedFilePath.value || fileDownloading.value) {
    return;
  }
  pinPreview();
  const projectId = props.projectId;
  const path = selectedFilePath.value;
  fileDownloading.value = true;
  try {
    const response = await chatApi.downloadProjectWorkspaceFile(
      projectId,
      path,
    );
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = path.split("/").pop() || "download";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  } catch {
    if (props.projectId === projectId && selectedFilePath.value === path) {
      fileError.value = tm("workspaceFiles.downloadFailed");
    }
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
  --chat-side-panel-width: 320px;
  width: var(--chat-side-panel-width);
  height: calc(100% - var(--chat-panel-top-offset, 0px));
  margin-top: var(--chat-panel-top-offset, 0px);
  border-left: 1px solid var(--chat-border, rgba(var(--v-border-color), 0.14));
  background: var(--chat-page-bg, rgb(var(--v-theme-surface)));
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  flex-direction: column;
  flex: 0 0 auto;
  min-width: 0;
  overflow: hidden;
}
.workspace-files-panel.has-preview {
  --chat-side-panel-width: min(52vw, 820px);
}
.workspace-tabs-header {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 48px;
  padding: 0 10px 0 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.workspace-tabs {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  gap: 4px;
  overflow-x: auto;
  scrollbar-width: thin;
  padding: 6px 0;
}
.workspace-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
}
.workspace-tab svg {
  flex-shrink: 0;
}
.workspace-tab span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.workspace-files-tab {
  flex: 0 0 auto;
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--chat-page-bg, rgb(var(--v-theme-surface)));
}
.workspace-file-tab {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  max-width: 200px;
  border-radius: 8px;
  padding-right: 5px;
}
.workspace-file-tab .workspace-tab {
  flex: 1;
  padding-right: 6px;
}
.workspace-file-tab.is-preview .workspace-tab span {
  font-style: italic;
}
.workspace-file-tab.active,
.workspace-files-tab[aria-selected="true"] {
  background: rgba(var(--v-theme-on-surface), 0.07);
}
.workspace-tab[aria-selected="true"] {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 600;
}
.workspace-file-tab:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
}
.workspace-tab-close {
  display: grid;
  place-items: center;
  flex: 0 0 22px;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.4);
  cursor: pointer;
}
.workspace-tab-close:hover {
  background: rgba(var(--v-theme-on-surface), 0.1);
  color: rgb(var(--v-theme-on-surface));
}
.workspace-tab:focus-visible,
.workspace-tab-close:focus-visible,
.workspace-tree-row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.workspace-path-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 43px;
  padding: 4px 10px 4px 16px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.workspace-breadcrumbs {
  display: flex;
  align-items: center;
  gap: 5px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), 0.45);
}
.workspace-breadcrumbs span {
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 0 1 auto;
  min-width: 24px;
}
.workspace-breadcrumbs svg {
  flex-shrink: 0;
}
.workspace-breadcrumbs .is-filename {
  color: rgb(var(--v-theme-on-surface));
  flex-shrink: 0;
  max-width: 65%;
}
.workspace-preview-actions {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 2px;
}
.workspace-body {
  display: flex;
  position: relative;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}
.workspace-preview {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.workspace-tree-pane {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  min-width: 0;
  background: var(--chat-page-bg, rgb(var(--v-theme-surface)));
}
.has-preview .workspace-tree-pane {
  flex: 0 0 clamp(180px, 15vw, 220px);
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.workspace-tree-toolbar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 10px 6px 8px 10px;
}
.workspace-filter {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  gap: 7px;
  height: 34px;
  padding: 0 9px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 8px;
  color: rgba(var(--v-theme-on-surface), 0.4);
}
.workspace-filter:focus-within {
  border-color: rgba(var(--v-theme-on-surface), 0.3);
}
.workspace-filter input {
  width: 0;
  min-width: 0;
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  font: inherit;
  font-size: 12px;
}
.workspace-filter input::-webkit-search-cancel-button {
  display: none;
}
.workspace-filter button {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 4px;
  color: inherit;
  background: transparent;
  cursor: pointer;
}
.workspace-error {
  margin: 0 10px 8px;
  font-size: 12px;
}
.workspace-tree {
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: 0 8px 12px;
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
.workspace-preview-state {
  flex: 1;
}
.workspace-preview-empty {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 24px;
  text-align: center;
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.35);
}
.workspace-tree-row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 30px;
  margin: 1px 0;
  padding-right: 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}
.workspace-tree-row:hover,
.workspace-tree-row--active {
  background: rgba(var(--v-theme-on-surface), 0.065);
}
.workspace-tree-chevron {
  display: grid;
  place-items: center;
  flex: 0 0 14px;
  color: rgba(var(--v-theme-on-surface), 0.4);
}
.workspace-folder-icon {
  flex-shrink: 0;
  color: #bc995e;
}
.workspace-file-icon {
  flex-shrink: 0;
  color: rgba(var(--v-theme-on-surface), 0.45);
}
.workspace-tree-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.workspace-tree-size {
  flex-shrink: 0;
  font-size: 10px;
  color: rgba(var(--v-theme-on-surface), 0.3);
}
.workspace-code-view {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.workspace-preview-content,
.workspace-line-numbers {
  margin: 0;
  padding: 16px 18px 24px 12px;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.75;
  tab-size: 2;
  white-space: pre;
}
.workspace-preview-content {
  min-width: 0;
  flex: 1;
}
.workspace-line-numbers {
  position: sticky;
  left: 0;
  padding-left: 16px;
  padding-right: 10px;
  color: rgba(var(--v-theme-on-surface), 0.28);
  background: var(--chat-page-bg, rgb(var(--v-theme-surface)));
  text-align: right;
  user-select: none;
}
.workspace-tree-scrim {
  display: none;
}
.workspace-dialog-preview {
  display: flex;
  flex-direction: column;
  height: min(86vh, 1000px);
  background: var(--chat-page-bg, rgb(var(--v-theme-surface)));
  color: rgb(var(--v-theme-on-surface));
}
.workspace-dialog-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.workspace-preview-path {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
}
@media (min-width: 761px) and (max-width: 1100px) {
  .workspace-files-panel.has-preview {
    position: absolute;
    right: 0;
    z-index: 20;
    --chat-side-panel-width: min(72vw, 720px);
    box-shadow: -12px 0 36px #0002;
  }
}
@media (max-width: 760px) {
  .workspace-files-panel,
  .workspace-files-panel.has-preview {
    position: fixed;
    inset: 0;
    z-index: 1300;
    --chat-side-panel-width: 100vw;
    height: 100dvh;
    margin-top: 0;
    border-left: 0;
  }
  .workspace-tabs-header {
    padding-top: env(safe-area-inset-top);
    min-height: calc(48px + env(safe-area-inset-top));
  }
  .has-preview .workspace-tree-pane {
    position: absolute;
    inset: 0 0 0 auto;
    z-index: 2;
    width: min(280px, 85%);
    box-shadow: -8px 0 24px #0002;
  }
  .workspace-tree-scrim {
    display: block;
    position: absolute;
    inset: 0;
    z-index: 1;
    border: 0;
    background: #0003;
  }
  .workspace-body {
    padding-bottom: env(safe-area-inset-bottom);
  }
  .workspace-file-tab {
    max-width: 160px;
  }
}
</style>
