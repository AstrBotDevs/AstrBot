<template>
  <div class="data-files-page">
    <div class="data-files-header">
      <div>
        <h1 class="text-h2 mb-1">{{ t('core.navigation.dataFiles') }}</h1>
        <p class="text-body-2 text-medium-emphasis mb-0">
          {{ tm('description') }}
        </p>
      </div>
      <div class="d-flex ga-2 align-center">
        <v-text-field
          v-model="searchQuery"
          :label="tm('search')"
          prepend-inner-icon="mdi-magnify"
          density="compact"
          variant="outlined"
          hide-details
          clearable
          @keyup.enter="runSearch"
        />
        <v-btn
          icon="mdi-refresh"
          variant="text"
          :aria-label="tm('refresh')"
          @click="refresh"
        />
        <v-btn
          icon="mdi-file-plus-outline"
          variant="text"
          :aria-label="tm('newFile')"
          @click="openCreate('file')"
        />
        <v-btn
          icon="mdi-folder-plus-outline"
          variant="text"
          :aria-label="tm('newDirectory')"
          @click="openCreate('directory')"
        />
        <v-btn
          icon="mdi-upload"
          variant="text"
          :aria-label="tm('upload')"
          @click="uploadInput?.click()"
        />
        <input
          ref="uploadInput"
          type="file"
          class="d-none"
          @change="uploadFile"
        />
      </div>
    </div>

    <v-card class="data-files-card" variant="outlined">
      <aside class="data-files-tree" :aria-label="tm('tree')">
        <div class="tree-title">
          <v-icon icon="mdi-folder-open-outline" size="18" /> data/
        </div>
        <v-progress-linear v-if="treeLoading" indeterminate height="2" />
        <v-alert v-if="treeError" type="error" density="compact" class="ma-2">{{
          treeError
        }}</v-alert>
        <div
          v-if="!treeLoading && !rootEntries.length"
          class="pa-4 text-medium-emphasis"
        >
          {{ tm('empty') }}
        </div>
        <template v-for="entry in visibleEntries" :key="entry.path">
          <button
            class="tree-entry"
            :class="{ active: selectedPath === entry.path }"
            type="button"
            :aria-label="entry.path"
            :data-depth="Math.min(entryDepth(entry), 12)"
            @click="activateEntry(entry)"
          >
            <v-icon :icon="iconFor(entry)" size="18" class="mr-1" />
            <span class="text-truncate">{{ entry.name }}</span>
            <v-icon
              v-if="entry.protected"
              icon="mdi-shield-outline"
              size="14"
              class="ml-auto"
            />
            <v-icon
              v-else-if="!entry.writable && entry.type === 'file'"
              icon="mdi-lock-outline"
              size="14"
              class="ml-auto"
            />
          </button>
        </template>
        <div v-if="searchResults.length" class="search-results">
          <div class="text-caption text-medium-emphasis px-3 pt-3">
            {{ tm('search') }}
          </div>
          <button
            v-for="entry in searchResults"
            :key="entry.path"
            type="button"
            class="tree-entry"
            @click="openEntry(entry)"
          >
            <v-icon :icon="iconFor(entry)" size="18" class="mr-1" />{{
              entry.path
            }}
          </button>
        </div>
      </aside>

      <main class="data-files-editor">
        <div v-if="!selectedEntry" class="empty-editor text-medium-emphasis">
          {{ tm('empty') }}
        </div>
        <template v-else>
          <div class="editor-toolbar">
            <span
              class="text-body-2 text-truncate"
              :title="selectedEntry.path"
              >{{ selectedEntry.path }}</span
            >
            <v-chip v-if="dirty" size="small" color="warning" variant="tonal"
              >●</v-chip
            >
            <v-chip
              v-if="!selectedEntry.writable"
              size="small"
              variant="tonal"
              >{{ tm('readonly') }}</v-chip
            >
            <v-btn
              v-if="selectedEntry.type === 'file' && selectedEntry.downloadable"
              icon="mdi-download"
              variant="text"
              size="small"
              :aria-label="tm('download')"
              @click="downloadEntry"
            />
            <v-btn
              v-if="selectedEntry.deletable"
              icon="mdi-delete-outline"
              variant="text"
              size="small"
              :aria-label="tm('delete')"
              @click="
                deleteRecursive = false;
                deleteDialog = true;
              "
            />
            <v-btn
              v-if="selectedEntry.writable || selectedEntry.deletable"
              icon="mdi-file-move-outline"
              variant="text"
              size="small"
              :aria-label="tm('rename')"
              @click="openRename"
            />
            <v-btn
              v-if="dirty && selectedEntry.writable"
              size="small"
              color="primary"
              :loading="saving"
              @click="save"
              >{{ tm('save') }}</v-btn
            >
          </div>
          <v-alert
            v-if="editorError"
            type="error"
            density="compact"
            class="ma-2"
            >{{ editorError }}</v-alert
          >
          <div
            v-if="editorReady && isTextEntry(selectedEntry) && content !== null"
            class="editor-container"
          >
            <VueMonacoEditor
              v-model:value="content"
              :language="selectedEntry.language || 'plaintext'"
              :theme="editorTheme"
              :options="editorOptions"
              @change="dirty = true"
            />
          </div>
          <div
            v-else-if="isTextEntry(selectedEntry) && content !== null"
            class="editor-loading text-medium-emphasis"
          >
            {{ tm('loading') }}
          </div>
          <div v-else class="binary-state pa-6">
            <v-icon :icon="iconFor(selectedEntry)" size="48" class="mb-3" />
            <img
              v-if="previewKind === 'image' && previewUrl"
              :src="previewUrl"
              :alt="selectedEntry.name"
              class="binary-preview-image"
            />
            <audio
              v-else-if="previewKind === 'audio' && previewUrl"
              :src="previewUrl"
              controls
              class="binary-preview-audio"
            />
            <div class="text-h6">
              {{
                selectedEntry.category === 'database'
                  ? tm('database')
                  : tm('binary')
              }}
            </div>
            <div class="text-body-2 text-medium-emphasis">
              {{ selectedEntry.size }} bytes
            </div>
          </div>
        </template>
      </main>
    </v-card>

    <v-dialog v-model="createDialog" max-width="460">
      <v-card>
        <v-card-title>{{
          createType === 'file' ? tm('newFile') : tm('newDirectory')
        }}</v-card-title>
        <v-card-text
          ><v-text-field
            v-model="createPath"
            :label="tm('path')"
            autofocus
            @keyup.enter="createEntry"
        /></v-card-text>
        <v-card-actions
          ><v-spacer /><v-btn variant="text" @click="createDialog = false">{{
            tm('reload')
          }}</v-btn
          ><v-btn color="primary" @click="createEntry">{{
            tm('save')
          }}</v-btn></v-card-actions
        >
      </v-card>
    </v-dialog>
    <v-dialog v-model="unsavedDialog" max-width="420">
      <v-card
        ><v-card-title>{{ tm('conflict') }}</v-card-title
        ><v-card-text>{{
          tm(conflictOpen ? 'conflict' : 'unsaved')
        }}</v-card-text
        ><v-card-actions
          ><v-spacer /><v-btn variant="text" @click="keepLocal">{{
            tm('keepLocal')
          }}</v-btn
          ><v-btn color="primary" @click="confirmLeave">{{
            tm('reload')
          }}</v-btn></v-card-actions
        ></v-card
      >
    </v-dialog>
    <v-dialog v-model="deleteDialog" max-width="420">
      <v-card
        ><v-card-title>{{ tm('delete') }}</v-card-title
        ><v-card-text>
          <div>{{ selectedEntry?.path }}</div>
          <v-checkbox
            v-if="selectedEntry?.type === 'directory'"
            v-model="deleteRecursive"
            :label="tm('recursiveDelete')"
            density="compact"
            hide-details
          /> </v-card-text
        ><v-card-actions
          ><v-spacer /><v-btn variant="text" @click="deleteDialog = false">{{
            tm('keepLocal')
          }}</v-btn
          ><v-btn color="error" @click="deleteEntry">{{
            tm('delete')
          }}</v-btn></v-card-actions
        ></v-card
      >
    </v-dialog>
    <v-dialog v-model="renameDialog" max-width="460">
      <v-card
        ><v-card-title>{{ tm('rename') }}</v-card-title
        ><v-card-text
          ><v-text-field
            v-model="renamePath"
            :label="tm('path')"
            autofocus
            @keyup.enter="renameEntry" /></v-card-text
        ><v-card-actions
          ><v-spacer /><v-btn variant="text" @click="renameDialog = false">{{
            tm('keepLocal')
          }}</v-btn
          ><v-btn color="primary" @click="renameEntry">{{
            tm('save')
          }}</v-btn></v-card-actions
        ></v-card
      >
    </v-dialog>
    <v-snackbar v-model="toastOpen" :color="toastColor">{{
      toastMessage
    }}</v-snackbar>
    <DashboardStepUpDialog
      v-model="stepUpDialogOpen"
      :loading="stepUpLoading"
      :error-message="stepUpErrorMessage"
      @confirm="submitStepUp"
      @cancel="cancelStepUp"
    />
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue';
import {
  onBeforeRouteLeave,
  useRoute,
  useRouter,
  type RouteLocationRaw,
} from 'vue-router';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor';
import '@/utils/monacoLoader';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { dataFilesApi, type DataFileEntry } from '@/api/v1';
import { useCustomizerStore } from '@/stores/customizer';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { stepUpHeaders } from '@/utils/stepUp';

const { t } = useI18n();
const { tm } = useModuleI18n('features/data-files');
const route = useRoute();
const router = useRouter();
const customizer = useCustomizerStore();
const rootEntries = ref<DataFileEntry[]>([]);
const entriesByDir = ref<Record<string, DataFileEntry[]>>({});
const expandedPaths = ref(new Set<string>());
const selectedEntry = ref<DataFileEntry | null>(null);
const selectedPath = ref('');
const activeDirectory = ref('');
const content = ref<string | null>(null);
const editorReady = ref(false);
const etag = ref('');
const dirty = ref(false);
const saving = ref(false);
const treeLoading = ref(false);
const treeError = ref('');
const editorError = ref('');
const searchQuery = ref('');
const searchResults = ref<DataFileEntry[]>([]);
const uploadInput = ref<HTMLInputElement | null>(null);
const createDialog = ref(false);
const createType = ref<'file' | 'directory'>('file');
const createPath = ref('');
const unsavedDialog = ref(false);
const conflictOpen = ref(false);
const deleteDialog = ref(false);
const deleteRecursive = ref(false);
const renameDialog = ref(false);
const renamePath = ref('');
const pendingEntry = ref<DataFileEntry | null>(null);
const pendingRoute = ref<RouteLocationRaw | null>(null);
const toastOpen = ref(false);
const toastMessage = ref('');
const toastColor = ref<'success' | 'error'>('success');
const previewUrl = ref('');
const previewKind = ref<'image' | 'audio' | null>(null);
const {
  dialogOpen: stepUpDialogOpen,
  loading: stepUpLoading,
  errorMessage: stepUpErrorMessage,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

const editorTheme = computed(() =>
  customizer.isDark ? 'vs-dark' : 'vs-light',
);
const editorOptions = computed(() => ({
  automaticLayout: true,
  fontSize: 13,
  lineNumbers: 'on' as const,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  tabSize: 2,
  wordWrap: 'on' as const,
  readOnly: !selectedEntry.value?.writable,
}));
const visibleEntries = computed(() => {
  const result: DataFileEntry[] = [];
  const append = (entries: DataFileEntry[]) =>
    void entries.forEach((entry) => {
      result.push(entry);
      if (entry.type === 'directory' && expandedPaths.value.has(entry.path))
        append(entriesByDir.value[entry.path] || []);
    });
  append(rootEntries.value);
  return result;
});
function entryDepth(entry: DataFileEntry) {
  return entry.path.split('/').length - 1;
}

function iconFor(entry: DataFileEntry) {
  if (entry.type === 'directory') return 'mdi-folder-outline';
  if (entry.type === 'symlink') return 'mdi-link-variant';
  if (entry.category === 'database') return 'mdi-database-outline';
  if (entry.category === 'binary') return 'mdi-file-outline';
  return 'mdi-file-document-outline';
}
function isTextEntry(entry: DataFileEntry) {
  return (
    entry.type === 'file' &&
    entry.readable &&
    (entry.category === 'text' ||
      (entry.category === 'system' && entry.language !== null))
  );
}

async function refresh() {
  treeLoading.value = true;
  treeError.value = '';
  try {
    const response = await dataFilesApi.tree('');
    rootEntries.value = response.data.data.entries;
    entriesByDir.value[''] = rootEntries.value;
    expandedPaths.value = new Set();
  } catch {
    treeError.value = tm('error');
  } finally {
    treeLoading.value = false;
  }
}

async function activateEntry(entry: DataFileEntry) {
  if (entry.type === 'directory') {
    activeDirectory.value = entry.path;
    if (expandedPaths.value.has(entry.path))
      expandedPaths.value.delete(entry.path);
    else {
      expandedPaths.value.add(entry.path);
      if (!entriesByDir.value[entry.path]) {
        try {
          const response = await dataFilesApi.tree(entry.path);
          entriesByDir.value[entry.path] = response.data.data.entries;
        } catch {
          editorError.value = tm('error');
        }
      }
    }
    expandedPaths.value = new Set(expandedPaths.value);
    return;
  }
  if (dirty.value) {
    pendingEntry.value = entry;
    unsavedDialog.value = true;
    return;
  }
  void openEntry(entry);
}

async function openEntry(entry: DataFileEntry) {
  clearPreview();
  selectedEntry.value = entry;
  selectedPath.value = entry.path;
  activeDirectory.value = entry.path.includes('/')
    ? entry.path.slice(0, entry.path.lastIndexOf('/'))
    : '';
  editorError.value = '';
  content.value = null;
  dirty.value = false;
  await router.replace({ path: '/data', query: { path: entry.path } });
  if (!isTextEntry(entry)) {
    await loadBinaryPreview(entry);
    return;
  }
  try {
    const response = await dataFilesApi.content(entry.path);
    content.value = response.data.data.content;
    etag.value = response.data.data.etag;
    selectedEntry.value = { ...entry, writable: response.data.data.writable };
  } catch {
    editorError.value = tm('error');
  }
}

function clearPreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
  previewUrl.value = '';
  previewKind.value = null;
}

function onKeyDown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    void save();
  }
}

interface DataFilesApiError {
  response?: {
    status?: number;
    data?: {
      data?: {
        requires_step_up?: boolean;
      };
    };
  };
}

function asDataFilesApiError(error: unknown): DataFilesApiError {
  return error && typeof error === 'object' ? error : {};
}

function errorStatus(error: unknown) {
  // Equivalent to checking error?.response?.status === 409 without trusting
  // an untyped third-party error object.
  return asDataFilesApiError(error).response?.status;
}

function requiresStepUp(error: unknown) {
  return (
    asDataFilesApiError(error).response?.data?.data?.requires_step_up === true
  );
}

async function loadBinaryPreview(entry: DataFileEntry) {
  const mime = entry.mime_type || '';
  let kind: 'image' | 'audio' | null = null;
  if (mime.startsWith('image/') && mime !== 'image/svg+xml') kind = 'image';
  else if (mime.startsWith('audio/')) kind = 'audio';
  if (!kind || !entry.downloadable) return;
  try {
    const response = await downloadWithStepUp(entry);
    previewUrl.value = URL.createObjectURL(response.data);
    previewKind.value = kind;
  } catch {
    editorError.value = tm('error');
  }
}

async function downloadWithStepUp(entry: DataFileEntry) {
  try {
    return await dataFilesApi.download(entry.path);
  } catch (error: unknown) {
    if (!requiresStepUp(error)) throw error;
    const token = await requestStepUp({
      action: 'filesystem.manage',
      resourceType: 'filesystem',
      resourceId: entry.path,
    });
    if (!token) throw error;
    return dataFilesApi.download(entry.path, {
      headers: stepUpHeaders(token),
    });
  }
}

function confirmLeave() {
  unsavedDialog.value = false;
  conflictOpen.value = false;
  dirty.value = false;
  if (pendingEntry.value) {
    const entry = pendingEntry.value;
    pendingEntry.value = null;
    void openEntry(entry);
  }
  if (pendingRoute.value) {
    const target = pendingRoute.value;
    pendingRoute.value = null;
    void router.push(target);
  }
}
function keepLocal() {
  unsavedDialog.value = false;
  conflictOpen.value = false;
  pendingEntry.value = null;
  pendingRoute.value = null;
}
async function save() {
  if (!selectedEntry.value || content.value === null || !etag.value) return;
  saving.value = true;
  editorError.value = '';
  try {
    const response = await dataFilesApi.save(
      selectedEntry.value.path,
      content.value,
      etag.value,
    );
    etag.value = response.data.data.etag;
    dirty.value = false;
    toastMessage.value = tm('saved');
    toastColor.value = 'success';
    toastOpen.value = true;
  } catch (error: unknown) {
    if (errorStatus(error) === 409) {
      pendingEntry.value = selectedEntry.value;
      conflictOpen.value = true;
      unsavedDialog.value = true;
    } else if (requiresStepUp(error)) {
      const token = await requestStepUp({
        action: 'filesystem.manage',
        resourceType: 'filesystem',
        resourceId: selectedEntry.value.path,
      });
      if (token) {
        try {
          const response = await dataFilesApi.save(
            selectedEntry.value.path,
            content.value,
            etag.value,
            { headers: stepUpHeaders(token) },
          );
          etag.value = response.data.data.etag;
          dirty.value = false;
          toastMessage.value = tm('saved');
          toastColor.value = 'success';
          toastOpen.value = true;
        } catch (retryError: unknown) {
          if (errorStatus(retryError) === 409) {
            pendingEntry.value = selectedEntry.value;
            conflictOpen.value = true;
            unsavedDialog.value = true;
          } else {
            editorError.value = tm('error');
          }
        }
      }
    } else editorError.value = tm('error');
  } finally {
    saving.value = false;
  }
}
function openCreate(type: 'file' | 'directory') {
  createType.value = type;
  createPath.value = '';
  createDialog.value = true;
}
async function createEntry() {
  if (!createPath.value) return;
  const parentPath = createPath.value.includes('/')
    ? createPath.value.slice(0, createPath.value.lastIndexOf('/'))
    : '';
  try {
    await dataFilesApi.create(createPath.value, createType.value);
    createDialog.value = false;
    await refresh();
  } catch (error: unknown) {
    if (requiresStepUp(error)) {
      const token = await requestStepUp({
        action: 'filesystem.manage',
        resourceType: 'filesystem',
        resourceId: parentPath || 'collection',
      });
      if (token) {
        await dataFilesApi.create(createPath.value, createType.value, '', {
          headers: stepUpHeaders(token),
        });
        createDialog.value = false;
        await refresh();
      }
    } else {
      editorError.value = tm('error');
    }
  }
}
function currentDirectory() {
  return activeDirectory.value;
}
async function uploadFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  const directory = currentDirectory();
  const target = directory ? `${directory}/${file.name}` : file.name;
  try {
    await dataFilesApi.upload(target, file);
    await refresh();
  } catch (error: unknown) {
    if (requiresStepUp(error)) {
      const token = await requestStepUp({
        action: 'filesystem.manage',
        resourceType: 'filesystem',
        resourceId: directory || 'collection',
      });
      if (token) {
        await dataFilesApi.upload(target, file, {
          headers: stepUpHeaders(token),
        });
        await refresh();
      }
    } else {
      editorError.value = tm('error');
    }
  } finally {
    if (uploadInput.value) uploadInput.value.value = '';
  }
}
function onBeforeUnload(event: BeforeUnloadEvent) {
  if (!dirty.value) return;
  event.preventDefault();
  event.returnValue = '';
}

onBeforeRouteLeave((to) => {
  if (!dirty.value) return true;
  pendingRoute.value = to;
  unsavedDialog.value = true;
  return false;
});

onMounted(async () => {
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('beforeunload', onBeforeUnload);
  await refresh();
  const path = typeof route.query.path === 'string' ? route.query.path : '';
  if (path) {
    try {
      const response = await dataFilesApi.metadata(path);
      await openEntry(response.data.data);
    } catch {
      editorError.value = tm('error');
      await router.replace({ path: '/data' });
    }
  }
  // Let the page stylesheet and Vuetify layout settle before Monaco measures
  // its container to avoid a forced-layout flash on the first editor mount.
  await nextTick();
  await new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => void resolve()));
  });
  editorReady.value = true;
});
function openRename() {
  if (!selectedEntry.value) return;
  renamePath.value = selectedEntry.value.path;
  renameDialog.value = true;
}
async function renameEntry() {
  if (
    !selectedEntry.value ||
    !renamePath.value ||
    renamePath.value === selectedEntry.value.path
  )
    return;
  try {
    const response = await dataFilesApi.move(
      selectedEntry.value.path,
      renamePath.value,
    );
    const moved = response.data.data as DataFileEntry;
    selectedEntry.value = { ...selectedEntry.value, ...moved };
    selectedPath.value = moved.path;
    activeDirectory.value = moved.path.includes('/')
      ? moved.path.slice(0, moved.path.lastIndexOf('/'))
      : '';
    await router.replace({ path: '/data', query: { path: moved.path } });
    renameDialog.value = false;
    await refresh();
  } catch (error: unknown) {
    if (requiresStepUp(error)) {
      const token = await requestStepUp({
        action: 'filesystem.manage',
        resourceType: 'filesystem',
        resourceId: selectedEntry.value.path,
      });
      if (token) {
        const response = await dataFilesApi.move(
          selectedEntry.value.path,
          renamePath.value,
          {
            headers: stepUpHeaders(token),
          },
        );
        const moved = response.data.data as DataFileEntry;
        selectedEntry.value = { ...selectedEntry.value, ...moved };
        selectedPath.value = moved.path;
        activeDirectory.value = moved.path.includes('/')
          ? moved.path.slice(0, moved.path.lastIndexOf('/'))
          : '';
        await router.replace({ path: '/data', query: { path: moved.path } });
        renameDialog.value = false;
        await refresh();
      }
    } else editorError.value = tm('error');
  }
}
async function deleteEntry() {
  const entry = selectedEntry.value;
  if (!entry) return;
  try {
    await dataFilesApi.remove(entry.path, deleteRecursive.value);
    deleteDialog.value = false;
    selectedEntry.value = null;
    content.value = null;
    await refresh();
  } catch (error: unknown) {
    if (requiresStepUp(error)) {
      const token = await requestStepUp({
        action: 'filesystem.manage',
        resourceType: 'filesystem',
        resourceId: entry.path,
      });
      if (token) {
        await dataFilesApi.remove(entry.path, deleteRecursive.value, {
          headers: stepUpHeaders(token),
        });
        deleteDialog.value = false;
        selectedEntry.value = null;
        content.value = null;
        await refresh();
      }
    } else editorError.value = tm('error');
  }
}
async function runSearch() {
  if (!searchQuery.value) {
    searchResults.value = [];
    return;
  }
  try {
    const response = await dataFilesApi.search(searchQuery.value);
    searchResults.value = response.data.data.results;
  } catch {
    editorError.value = tm('error');
  }
}
async function downloadEntry() {
  if (!selectedEntry.value) return;
  try {
    const response = await downloadWithStepUp(selectedEntry.value);
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = selectedEntry.value.name;
    link.click();
    URL.revokeObjectURL(url);
  } catch {
    editorError.value = tm('error');
  }
}

watch(
  () => route.query.path,
  async (value) => {
    if (!value || selectedPath.value === value) return;
    const match = rootEntries.value.find((entry) => entry.path === value);
    if (match) await openEntry(match);
  },
);
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown);
  window.removeEventListener('beforeunload', onBeforeUnload);
  clearPreview();
});
</script>

<style scoped>
.data-files-page {
  max-width: 1600px;
  margin: 0 auto;
  padding: 24px;
  width: 100%;
}
.data-files-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}
.data-files-card {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  height: min(620px, calc(100vh - 180px));
  min-height: 420px;
  overflow: hidden;
}
.data-files-tree {
  min-height: 0;
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  overflow-y: auto;
}
.tree-title {
  padding: 12px 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}
.tree-entry {
  width: 100%;
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 5px 12px;
  text-align: left;
  color: inherit;
  background: transparent;
  border: 0;
  cursor: pointer;
}
.tree-entry[data-depth='1'] {
  padding-left: 28px;
}
.tree-entry[data-depth='2'] {
  padding-left: 44px;
}
.tree-entry[data-depth='3'] {
  padding-left: 60px;
}
.tree-entry[data-depth='4'] {
  padding-left: 76px;
}
.tree-entry[data-depth='5'] {
  padding-left: 92px;
}
.tree-entry[data-depth='6'] {
  padding-left: 108px;
}
.tree-entry[data-depth='7'] {
  padding-left: 124px;
}
.tree-entry[data-depth='8'] {
  padding-left: 140px;
}
.tree-entry[data-depth='9'] {
  padding-left: 156px;
}
.tree-entry[data-depth='10'] {
  padding-left: 172px;
}
.tree-entry[data-depth='11'] {
  padding-left: 188px;
}
.tree-entry[data-depth='12'] {
  padding-left: 204px;
}
.tree-entry:hover,
.tree-entry:focus-visible {
  background: rgba(var(--v-theme-on-surface), 0.06);
  outline: none;
}
.tree-entry.active {
  background: rgba(var(--v-theme-primary), 0.12);
}
.data-files-editor {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.editor-toolbar {
  min-height: 48px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}
.editor-container {
  flex: 1;
  min-height: 0;
}
.editor-loading {
  flex: 1;
  min-height: 0;
  display: grid;
  place-items: center;
}
.editor-container :deep(.monaco-editor) {
  border-radius: 10px;
}
.empty-editor,
.binary-state {
  margin: auto;
  text-align: center;
}
.binary-preview-image {
  display: block;
  max-width: min(100%, 640px);
  max-height: 360px;
  margin: 0 auto 16px;
  object-fit: contain;
}
.binary-preview-audio {
  display: block;
  width: min(100%, 480px);
  margin: 0 auto 16px;
}
@media (max-width: 768px) {
  .data-files-page {
    padding: 16px;
  }
  .data-files-header {
    flex-wrap: wrap;
  }
  .data-files-card {
    height: calc(100vh - 170px);
    min-height: 420px;
    grid-template-columns: 1fr;
    grid-template-rows: 220px minmax(0, 1fr);
  }
  .data-files-tree {
    max-height: none;
    border-right: 0;
    border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  }
}
</style>
