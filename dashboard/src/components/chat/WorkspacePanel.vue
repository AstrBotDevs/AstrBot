<template>
  <transition name="slide-left">
    <aside v-if="modelValue" class="workspace-panel">
      <div class="workspace-panel-header">
        <div class="workspace-panel-title">{{ tm("workspace.title") }}</div>
        <div class="workspace-panel-actions">
          <v-btn
            icon="mdi-refresh"
            size="small"
            variant="text"
            :title="tm('workspace.refresh')"
            :loading="loading"
            @click="loadFiles(currentPath)"
          />
          <v-btn icon="mdi-close" size="small" variant="text" @click="close" />
        </div>
      </div>

      <div v-if="breadcrumbs.length" class="workspace-breadcrumb">
        <template v-for="crumb in breadcrumbs" :key="crumb.path">
          <v-icon v-if="crumb.path !== breadcrumbs[0].path" size="14">
            mdi-chevron-right
          </v-icon>
          <button
            type="button"
            class="breadcrumb-item"
            @click="loadFiles(crumb.path)"
          >
            {{ crumb.name }}
          </button>
        </template>
      </div>

      <div class="workspace-body">
        <div class="workspace-content">
          <div v-if="loading" class="workspace-state">
            <v-progress-circular indeterminate size="24" width="2" />
          </div>

          <div v-else-if="error" class="workspace-state workspace-error">
            {{ error }}
          </div>

          <div v-else-if="!entries.length" class="workspace-state">
            {{ tm("workspace.empty") }}
          </div>

          <div v-else class="workspace-list">
            <button
              v-if="currentPath"
              type="button"
              class="workspace-row"
              @click="loadFiles(parentPath)"
            >
              <v-icon size="18">mdi-arrow-up</v-icon>
              <span class="workspace-name">..</span>
            </button>
            <button
              v-for="entry in entries"
              :key="entry.path"
              type="button"
              class="workspace-row"
              :class="{ active: selectedFile?.path === entry.path }"
              :disabled="entry.type === 'file' && !entry.previewable"
              @click="openEntry(entry)"
            >
              <v-icon size="18">
                {{
                  entry.type === "directory"
                    ? "mdi-folder-outline"
                    : "mdi-file-document-outline"
                }}
              </v-icon>
              <span class="workspace-name">{{ entry.name }}</span>
              <span v-if="entry.type === 'file'" class="workspace-size">
                {{ formatSize(entry.size) }}
              </span>
            </button>
          </div>
        </div>

        <section class="workspace-preview">
          <div class="preview-header">
            <div class="preview-title">
              {{ selectedFile?.name || tm("workspace.preview") }}
            </div>
            <v-progress-circular
              v-if="previewLoading"
              indeterminate
              size="18"
              width="2"
            />
          </div>
          <pre v-if="previewContent" class="preview-body">{{ previewContent }}</pre>
          <div v-else class="preview-empty">
            {{ tm("workspace.selectFile") }}
          </div>
        </section>
      </div>
    </aside>
  </transition>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import axios from "axios";
import { useModuleI18n } from "@/i18n/composables";

type WorkspaceEntry = {
  name: string;
  path: string;
  type: "directory" | "file";
  size: number | null;
  previewable: boolean;
};

const props = defineProps<{
  modelValue: boolean;
  sessionId: string | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
}>();

const { tm } = useModuleI18n("features/chat");
const currentPath = ref("");
const entries = ref<WorkspaceEntry[]>([]);
const loading = ref(false);
const error = ref("");
const selectedFile = ref<WorkspaceEntry | null>(null);
const previewContent = ref("");
const previewLoading = ref(false);

const breadcrumbs = computed(() => {
  if (!currentPath.value) return [];
  const parts = currentPath.value.split("/").filter(Boolean);
  return parts.map((name, index) => ({
    name,
    path: parts.slice(0, index + 1).join("/"),
  }));
});

const parentPath = computed(() => {
  const parts = currentPath.value.split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
});

watch(
  () => [props.modelValue, props.sessionId],
  ([open, sessionId]) => {
    if (open && sessionId) {
      currentPath.value = "";
      selectedFile.value = null;
      previewContent.value = "";
      loadFiles(currentPath.value);
    }
  },
  { immediate: true },
);

function close() {
  emit("update:modelValue", false);
}

async function loadFiles(path: string) {
  if (!props.sessionId) {
    entries.value = [];
    error.value = tm("workspace.noSession");
    return;
  }

  loading.value = true;
  error.value = "";
  try {
    const response = await axios.get("/api/chat/workspace/list_files", {
      params: {
        session_id: props.sessionId,
        path,
      },
    });
    if (response.data?.status !== "ok") {
      throw new Error(response.data?.message || tm("workspace.loadFailed"));
    }
    currentPath.value = response.data.data?.path || "";
    entries.value = response.data.data?.entries || [];
  } catch (err) {
    error.value = axios.isAxiosError(err)
      ? err.response?.data?.message || err.message
      : String((err as Error)?.message || err);
    entries.value = [];
  } finally {
    loading.value = false;
  }
}

async function openEntry(entry: WorkspaceEntry) {
  if (entry.type === "directory") {
    await loadFiles(entry.path);
    return;
  }
  if (entry.previewable) {
    await previewFile(entry);
  }
}

async function previewFile(entry: WorkspaceEntry) {
  if (!props.sessionId) return;
  selectedFile.value = entry;
  previewLoading.value = true;
  previewContent.value = "";
  try {
    const response = await axios.get("/api/chat/workspace/download_file", {
      params: {
        session_id: props.sessionId,
        path: entry.path,
      },
    });
    if (response.data?.status !== "ok") {
      throw new Error(response.data?.message || tm("workspace.previewFailed"));
    }
    previewContent.value = response.data.data?.content || "";
  } catch (err) {
    previewContent.value = axios.isAxiosError(err)
      ? err.response?.data?.message || err.message
      : String((err as Error)?.message || err);
  } finally {
    previewLoading.value = false;
  }
}

function formatSize(size: number | null) {
  if (size == null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
</script>

<style scoped>
.workspace-panel {
  width: min(480px, 56vw);
  height: 100%;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.2s ease;
}

.slide-left-enter-from,
.slide-left-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.workspace-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 8px;
}

.workspace-panel-title {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
}

.workspace-panel-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.workspace-breadcrumb {
  display: flex;
  align-items: center;
  gap: 4px;
  min-height: 34px;
  padding: 0 16px 8px;
  overflow-x: auto;
  color: rgba(var(--v-theme-on-surface), 0.62);
  white-space: nowrap;
}

.breadcrumb-item {
  border: 0;
  padding: 3px 4px;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.breadcrumb-item:hover {
  color: rgb(var(--v-theme-on-surface));
}

.workspace-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(170px, 38%) minmax(260px, 1fr);
  border-top: 1px solid rgba(var(--v-border-color), 0.1);
}

.workspace-content {
  min-height: 0;
  overflow-y: auto;
  padding: 10px;
  border-right: 1px solid rgba(var(--v-border-color), 0.14);
}

.workspace-state {
  min-height: 110px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 13px;
  text-align: center;
}

.workspace-error {
  color: rgb(var(--v-theme-error));
}

.workspace-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.workspace-row {
  width: 100%;
  min-height: 36px;
  border: 0;
  border-radius: 8px;
  padding: 0 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.workspace-row:hover,
.workspace-row.active {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.workspace-row:disabled {
  cursor: default;
  opacity: 0.5;
}

.workspace-row:disabled:hover {
  background: transparent;
}

.workspace-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.workspace-size {
  flex-shrink: 0;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 12px;
}

.workspace-preview {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.preview-header {
  min-height: 42px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.preview-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
}

.preview-body {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 0 12px 12px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  color: rgba(var(--v-theme-on-surface), 0.84);
  font-size: 12px;
  line-height: 1.55;
}

.preview-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 13px;
  text-align: center;
}

@media (max-width: 760px) {
  .workspace-panel {
    position: fixed;
    inset: 0;
    z-index: 1300;
    width: 100vw;
    height: 100dvh;
    border-left: 0;
  }

  .workspace-row {
    margin-top: 8px;
  }

  .workspace-panel-header {
    min-height: 52px;
    padding: calc(10px + env(safe-area-inset-top)) 12px 8px;
    border-bottom: 1px solid rgba(var(--v-border-color), 0.12);
  }

  .workspace-breadcrumb {
    padding: 8px 12px;
  }

  .workspace-body {
    display: flex;
    flex-direction: column;
    border-top: 0;
    gap: 8px;
  }

  .workspace-content {
    flex: 1 1 0;
    padding: 0 8px;
    border-right: 0;
  }

  .workspace-preview {
    flex: 0 0 42%;
    min-height: 180px;
    border-top: 1px solid rgba(var(--v-border-color), 0.14);
    margin-top: 0;
  }
}
</style>
