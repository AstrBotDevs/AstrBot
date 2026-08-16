<template>
  <div class="persona-manager">
    <!-- 移动端顶部导航 -->
    <div class="mobile-nav d-md-none mb-4">
      <FolderBreadcrumb />
    </div>

    <div class="manager-layout">
      <!-- 左侧边栏 - 仅桌面端显示 -->
      <div class="sidebar d-none d-md-block">
        <div
          class="sidebar-header d-flex justify-space-between align-center mb-3"
        >
          <h3 class="text-h6">{{ tm('folder.sidebarTitle') }}</h3>
          <v-btn
            icon="mdi-folder-plus"
            variant="text"
            size="small"
            :title="tm('folder.createButton')"
            @click="showCreateFolderDialog = true"
          />
        </div>
        <FolderTree
          @move-folder="openMoveFolderDialog"
          @success="showSuccess"
          @error="showError"
          @persona-dropped="handlePersonaDropped"
        />
      </div>

      <!-- 主内容区 -->
      <div class="main-content">
        <!-- 顶部工具栏 -->
        <div
          class="toolbar d-flex flex-wrap justify-space-between align-center mb-4 ga-2"
        >
          <!-- 面包屑 - 仅桌面端显示 -->
          <div class="d-none d-md-block">
            <FolderBreadcrumb />
          </div>

          <!-- 操作按钮组 -->
          <div class="d-flex ga-2">
            <v-btn
              variant="outlined"
              prepend-icon="mdi-upload"
              rounded="md"
              @click="triggerImport"
            >
              {{ tm('buttons.import') }}
            </v-btn>
            <v-btn
              color="primary"
              variant="tonal"
              prepend-icon="mdi-plus"
              rounded="md"
              @click="openCreatePersonaDialog"
            >
              {{ tm('buttons.create') }}
            </v-btn>
            <input
              ref="importFileInput"
              type="file"
              accept="application/json,.json"
              hidden
              @change="handleImportFile"
            />
            <v-btn
              variant="outlined"
              prepend-icon="mdi-folder-plus"
              rounded="md"
              @click="showCreateFolderDialog = true"
            >
              {{ tm('folder.createButton') }}
            </v-btn>
          </div>
        </div>

        <!-- 加载状态 - 只有加载超过阈值才显示骨架屏 -->
        <v-fade-transition>
          <div v-if="showSkeleton" class="loading-container">
            <v-row>
              <v-col v-for="n in 6" :key="n" cols="12" sm="6" lg="6" xl="4">
                <v-skeleton-loader type="card" rounded="md" />
              </v-col>
            </v-row>
          </div>
        </v-fade-transition>

        <!-- 内容区域 -->
        <div v-if="!loading">
          <!-- 子文件夹区域 -->
          <div v-if="currentFolders.length > 0" class="folders-section mb-6">
            <h3 class="text-subtitle-1 font-weight-medium mb-3">
              <v-icon size="small" class="mr-1">mdi-folder</v-icon>
              {{ tm('folder.foldersTitle') }} ({{ currentFolders.length }})
            </h3>
            <v-row>
              <v-col
                v-for="folder in currentFolders"
                :key="folder.folder_id"
                cols="12"
                sm="6"
                lg="6"
                xl="4"
              >
                <FolderCard
                  :folder="folder"
                  @click="personaStore.navigateToFolder(folder.folder_id)"
                  @open="personaStore.navigateToFolder(folder.folder_id)"
                  @rename="openRenameFolderDialog(folder)"
                  @move="openMoveFolderDialog(folder)"
                  @delete="confirmDeleteFolder(folder)"
                  @persona-dropped="handlePersonaDropped"
                />
              </v-col>
            </v-row>
          </div>

          <!-- Persona 区域 -->
          <div v-if="currentPersonas.length > 0" class="personas-section">
            <h3 class="text-subtitle-1 font-weight-medium mb-3">
              <v-icon size="small" class="mr-1">mdi-account-heart</v-icon>
              {{ tm('persona.personasTitle') }} ({{ currentPersonas.length }})
            </h3>
            <v-row>
              <v-col
                v-for="persona in currentPersonas"
                :key="persona.persona_id"
                cols="12"
                sm="6"
                lg="6"
                xl="4"
              >
                <PersonaCard
                  :persona="persona"
                  @view="viewPersona(persona)"
                  @edit="editPersona(persona)"
                  @move="openMovePersonaDialog(persona)"
                  @delete="confirmDeletePersona(persona)"
                  @export="handlePersonaExport"
                />
              </v-col>
            </v-row>
          </div>

          <!-- 空状态 -->
          <div
            v-if="currentFolders.length === 0 && currentPersonas.length === 0"
            class="empty-state"
          >
            <v-card class="text-center pa-8" elevation="0">
              <v-icon size="64" color="on-surface-variant" class="mb-4"
                >mdi-folder-open-outline</v-icon
              >
              <h3 class="text-h5 mb-2">{{ tm('empty.folderEmpty') }}</h3>
              <p class="text-body-1 text-medium-emphasis mb-4">
                {{ tm('empty.folderEmptyDescription') }}
              </p>
              <div class="d-flex justify-center ga-2">
                <v-btn
                  color="primary"
                  variant="tonal"
                  prepend-icon="mdi-plus"
                  @click="openCreatePersonaDialog"
                >
                  {{ tm('buttons.create') }}
                </v-btn>
                <v-btn
                  variant="outlined"
                  prepend-icon="mdi-folder-plus"
                  @click="showCreateFolderDialog = true"
                >
                  {{ tm('folder.createButton') }}
                </v-btn>
              </div>
            </v-card>
          </div>
        </div>
      </div>
    </div>

    <!-- 创建/编辑 Persona 对话框 -->
    <PersonaForm
      v-model="showPersonaDialog"
      :editing-persona="editingPersona ?? undefined"
      :current-folder-id="currentFolderId ?? undefined"
      :current-folder-name="currentFolderName ?? undefined"
      @saved="handlePersonaSaved"
      @deleted="handlePersonaDeleted"
      @error="showError"
    />

    <!-- 查看 Persona 详情对话框 -->
    <v-dialog v-model="showViewDialog" max-width="700px" scrollable>
      <v-card v-if="viewingPersona" class="persona-preview-dialog__card">
        <v-card-title class="d-flex justify-space-between align-center">
          <span class="text-h5">{{ viewingPersona.persona_id }}</span>
          <div class="d-flex align-center ga-1">
            <v-btn
              color="primary"
              variant="tonal"
              size="small"
              prepend-icon="mdi-pencil"
              @click="openEditFromViewDialog"
            >
              {{ tm('buttons.edit') }}
            </v-btn>
            <v-btn
              icon="mdi-close"
              variant="text"
              @click="showViewDialog = false"
            />
          </div>
        </v-card-title>

        <v-card-text class="persona-preview-dialog__content">
          <div class="mb-4">
            <h4 class="text-h6 mb-2">{{ tm('form.systemPrompt') }}</h4>
            <pre class="system-prompt-content">{{
              viewingPersona.system_prompt
            }}</pre>
          </div>

          <div v-if="viewingPersona.custom_error_message" class="mb-4">
            <h4 class="text-h6 mb-2">{{ tm('form.customErrorMessage') }}</h4>
            <pre class="system-prompt-content">{{
              viewingPersona.custom_error_message
            }}</pre>
          </div>

          <div
            v-if="
              viewingPersona.begin_dialogs &&
              viewingPersona.begin_dialogs.length > 0
            "
            class="mb-4"
          >
            <h4 class="text-h6 mb-2">{{ tm('form.presetDialogs') }}</h4>
            <div
              v-for="(dialog, index) in viewingPersona.begin_dialogs"
              :key="index"
              class="mb-2"
            >
              <v-chip
                :color="index % 2 === 0 ? 'primary' : 'secondary'"
                variant="tonal"
                size="small"
                class="mb-1"
              >
                {{
                  index % 2 === 0
                    ? tm('form.userMessage')
                    : tm('form.assistantMessage')
                }}
              </v-chip>
              <div class="dialog-content ml-2">{{ dialog }}</div>
            </div>
          </div>

          <div class="mb-4">
            <h4 class="text-h6 mb-2">{{ tm('form.tools') }}</h4>
            <div
              v-if="viewingPersona.tools === null"
              class="text-body-2 text-medium-emphasis"
            >
              <v-chip
                size="small"
                color="success"
                variant="tonal"
                prepend-icon="mdi-check-all"
              >
                {{ tm('form.allToolsAvailable') }}
              </v-chip>
            </div>
            <div
              v-else-if="
                viewingPersona.tools && viewingPersona.tools.length > 0
              "
              class="d-flex flex-wrap ga-1"
            >
              <v-chip
                v-for="toolName in viewingPersona.tools"
                :key="toolName"
                size="small"
                color="primary"
                variant="tonal"
              >
                {{ toolName }}
              </v-chip>
            </div>
            <div v-else class="text-body-2 text-medium-emphasis">
              {{ tm('form.noToolsSelected') }}
            </div>
          </div>

          <div class="mb-4">
            <h4 class="text-h6 mb-2">{{ tm('form.skills') }}</h4>
            <div
              v-if="viewingPersona.skills === null"
              class="text-body-2 text-medium-emphasis"
            >
              <v-chip
                size="small"
                color="success"
                variant="tonal"
                prepend-icon="mdi-check-all"
              >
                {{ tm('form.allSkillsAvailable') }}
              </v-chip>
            </div>
            <div
              v-else-if="
                viewingPersona.skills && viewingPersona.skills.length > 0
              "
              class="d-flex flex-wrap ga-1"
            >
              <v-chip
                v-for="skillName in viewingPersona.skills"
                :key="skillName"
                size="small"
                color="primary"
                variant="tonal"
              >
                {{ skillName }}
              </v-chip>
            </div>
            <div v-else class="text-body-2 text-medium-emphasis">
              {{ tm('form.noSkillsSelected') }}
            </div>
          </div>

          <div class="text-caption text-medium-emphasis">
            <div>
              {{ tm('labels.createdAt') }}:
              {{ formatDate(viewingPersona.created_at) }}
            </div>
            <div v-if="viewingPersona.updated_at">
              {{ tm('labels.updatedAt') }}:
              {{ formatDate(viewingPersona.updated_at) }}
            </div>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 创建文件夹对话框 -->
    <CreateFolderDialog
      v-model="showCreateFolderDialog"
      :parent-folder-id="currentFolderId"
      @created="showSuccess"
      @error="showError"
    />

    <!-- 重命名文件夹对话框 -->
    <v-dialog v-model="showRenameFolderDialog" max-width="400px">
      <v-card>
        <v-card-title>{{ tm('folder.renameDialog.title') }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="renameFolderData.name"
            :label="tm('folder.form.name')"
            :rules="[(v) => !!v || tm('folder.validation.nameRequired')]"
            variant="outlined"
            density="comfortable"
            autofocus
            @keyup.enter="submitRenameFolder"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showRenameFolderDialog = false">
            {{ tm('buttons.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="renameLoading"
            :disabled="!renameFolderData.name"
            @click="submitRenameFolder"
          >
            {{ tm('buttons.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 移动对话框 -->
    <MoveToFolderDialog
      v-model="showMoveDialog"
      :item-type="moveDialogType"
      :item="moveDialogItem"
      @moved="showSuccess"
      @error="showError"
    />

    <!-- 删除文件夹确认对话框 -->
    <v-dialog v-model="showDeleteFolderDialog" max-width="450px">
      <v-card>
        <v-card-title class="text-error">
          <v-icon class="mr-2" color="error">mdi-alert</v-icon>
          {{ tm('folder.deleteDialog.title') }}
        </v-card-title>
        <v-card-text>
          <p>
            {{
              tm('folder.deleteDialog.message', {
                name: deleteFolderData?.name ?? '',
              })
            }}
          </p>
          <p class="text-warning mt-2">
            <v-icon size="small" class="mr-1">mdi-information</v-icon>
            {{ tm('folder.deleteDialog.warning') }}
          </p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showDeleteFolderDialog = false">
            {{ tm('buttons.cancel') }}
          </v-btn>
          <v-btn
            color="error"
            variant="flat"
            :loading="deleteLoading"
            @click="submitDeleteFolder"
          >
            {{ tm('buttons.delete') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar
      v-model="showMessage"
      :timeout="3000"
      elevation="4"
      :color="messageType"
      location="top"
    >
      {{ message }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { personaApi } from '@/api/v1';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { storeToRefs } from 'pinia';

import FolderTree from './FolderTree.vue';
import FolderBreadcrumb from './FolderBreadcrumb.vue';
import FolderCard from './FolderCard.vue';
import PersonaCard from './PersonaCard.vue';
import PersonaForm from '@/components/shared/PersonaForm.vue';
import CreateFolderDialog from './CreateFolderDialog.vue';
import MoveToFolderDialog from './MoveToFolderDialog.vue';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';

import type { Folder, FolderTreeNode } from '@/components/folder/types';
import type { Persona as StorePersona } from '@/stores/personaStore';

type MoveDialogType = 'persona' | 'folder';
type SnackbarType = 'success' | 'error';

const { tm } = useModuleI18n('features/persona');
const confirmDialog = useConfirmDialog();
const personaStore = usePersonaStore();
const {
  folderTree,
  currentFolderId,
  currentFolders,
  currentPersonas,
  loading,
} = storeToRefs(personaStore);

const showPersonaDialog = ref(false);
const importFileInput = ref<HTMLInputElement | null>(null);
const showViewDialog = ref(false);
const editingPersona = ref<StorePersona | null>(null);
const viewingPersona = ref<StorePersona | null>(null);

const showCreateFolderDialog = ref(false);
const showRenameFolderDialog = ref(false);
const showDeleteFolderDialog = ref(false);
const renameFolderData = ref<{ folder: Folder | null; name: string }>({
  folder: null,
  name: '',
});
const deleteFolderData = ref<Folder | null>(null);
const renameLoading = ref(false);
const deleteLoading = ref(false);

const showMoveDialog = ref(false);
const moveDialogType = ref<MoveDialogType>('persona');
const moveDialogItem = ref<StorePersona | Folder | null>(null);

const showMessage = ref(false);
const message = ref('');
const messageType = ref<SnackbarType>('success');

const showSkeleton = ref(false);
const skeletonTimer = ref<ReturnType<typeof setTimeout> | null>(null);

const currentFolderName = computed(() => {
  if (!currentFolderId.value) {
    return null;
  }

  const findName = (nodes: FolderTreeNode[], id: string): string | null => {
    for (const node of nodes) {
      if (node.folder_id === id) {
        return node.name;
      }
      if (node.children.length > 0) {
        const found = findName(node.children, id);
        if (found) {
          return found;
        }
      }
    }
    return null;
  };

  return findName(folderTree.value, currentFolderId.value);
});

watch(
  loading,
  (newVal) => {
    if (newVal) {
      skeletonTimer.value = setTimeout(() => {
        if (loading.value) {
          showSkeleton.value = true;
        }
      }, 150);
      return;
    }

    if (skeletonTimer.value) {
      clearTimeout(skeletonTimer.value);
      skeletonTimer.value = null;
    }
    showSkeleton.value = false;
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (skeletonTimer.value) {
    clearTimeout(skeletonTimer.value);
  }
});

onMounted(async () => {
  await initialize();
});

async function initialize() {
  await Promise.all([
    personaStore.loadFolderTree(),
    personaStore.navigateToFolder(null),
  ]);
}

function openCreatePersonaDialog() {
  editingPersona.value = null;
  showPersonaDialog.value = true;
}

function handlePersonaExport(exportMessage: string, isError: boolean) {
  if (isError) {
    showError(exportMessage);
    return;
  }
  showSuccess(exportMessage);
}

function triggerImport() {
  if (importFileInput.value) {
    importFileInput.value.value = '';
    importFileInput.value.click();
  }
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;

  try {
    const data: unknown = JSON.parse(await file.text());
    if (!data || typeof data !== 'object' || !('system_prompt' in data)) {
      showError(tm('messages.importMissingPrompt'));
      return;
    }
    const imported = data as {
      persona_id?: unknown;
      system_prompt?: unknown;
      begin_dialogs?: unknown;
    };
    if (typeof imported.system_prompt !== 'string' || !imported.system_prompt) {
      showError(tm('messages.importMissingPrompt'));
      return;
    }

    const response = await personaApi.list();
    const existingIds = new Set(
      response.data.status === 'ok'
        ? (response.data.data || []).map((persona) => persona.persona_id)
        : [],
    );
    const baseId =
      typeof imported.persona_id === 'string' && imported.persona_id
        ? imported.persona_id
        : 'imported_persona';
    let personaId = baseId;
    let suffix = 1;
    while (existingIds.has(personaId)) {
      personaId = `${baseId}_imported${suffix === 1 ? '' : `_${suffix}`}`;
      suffix += 1;
    }

    const createResponse = await personaApi.create({
      persona_id: personaId,
      system_prompt: imported.system_prompt,
      begin_dialogs: Array.isArray(imported.begin_dialogs)
        ? imported.begin_dialogs.filter(
            (item): item is string => typeof item === 'string',
          )
        : [],
      tools: null,
      skills: null,
      folder_id: currentFolderId.value,
    });
    if (createResponse.data.status !== 'ok') {
      throw new Error(
        createResponse.data.message || tm('messages.importError'),
      );
    }
    await personaStore.refreshCurrentFolder();
    if (personaId !== baseId) {
      showSuccess(tm('messages.importIdExists', { id: personaId }));
    } else {
      showSuccess(tm('messages.importSuccess'));
    }
  } catch (error) {
    if (error instanceof SyntaxError) {
      showError(tm('messages.importFormatError'));
      return;
    }
    console.error('Failed to import persona:', error);
    showError(resolveErrorMessage(error, tm('messages.importError')));
  }
}

function editPersona(persona: StorePersona) {
  editingPersona.value = persona;
  showPersonaDialog.value = true;
}

function viewPersona(persona: StorePersona) {
  viewingPersona.value = persona;
  showViewDialog.value = true;
}

function openEditFromViewDialog() {
  if (!viewingPersona.value) {
    return;
  }
  editingPersona.value = viewingPersona.value;
  showViewDialog.value = false;
  showPersonaDialog.value = true;
}

function handlePersonaSaved(successMessage: string) {
  showSuccess(successMessage);
  void personaStore.refreshCurrentFolder();
}

function handlePersonaDeleted(successMessage: string) {
  showSuccess(successMessage);
  void personaStore.refreshCurrentFolder();
}

async function confirmDeletePersona(persona: StorePersona) {
  if (
    !(await askForConfirmationDialog(
      tm('messages.deleteConfirm', { id: persona.persona_id }),
      confirmDialog,
    ))
  ) {
    return;
  }

  try {
    await personaStore.deletePersona(persona.persona_id);
    showSuccess(tm('messages.deleteSuccess'));
  } catch (error) {
    showError(resolveErrorMessage(error, tm('messages.deleteError')));
  }
}

function openMovePersonaDialog(persona: StorePersona) {
  moveDialogType.value = 'persona';
  moveDialogItem.value = persona;
  showMoveDialog.value = true;
}

async function handlePersonaDropped({
  persona_id,
  target_folder_id,
}: {
  persona_id: string;
  target_folder_id: string | null;
}) {
  try {
    await personaStore.movePersonaToFolder(persona_id, target_folder_id);
    showSuccess(tm('persona.messages.moveSuccess'));
    await personaStore.navigateToFolder(target_folder_id);
  } catch (error) {
    showError(resolveErrorMessage(error, tm('persona.messages.moveError')));
  }
}

function openRenameFolderDialog(folder: Folder) {
  renameFolderData.value = { folder, name: folder.name };
  showRenameFolderDialog.value = true;
}

async function submitRenameFolder() {
  if (!renameFolderData.value.name || !renameFolderData.value.folder) {
    return;
  }

  renameLoading.value = true;
  try {
    await personaStore.updateFolder({
      folder_id: renameFolderData.value.folder.folder_id,
      name: renameFolderData.value.name,
    });
    showSuccess(tm('folder.messages.renameSuccess'));
    showRenameFolderDialog.value = false;
  } catch (error) {
    showError(resolveErrorMessage(error, tm('folder.messages.renameError')));
  } finally {
    renameLoading.value = false;
  }
}

function openMoveFolderDialog(folder: Folder) {
  moveDialogType.value = 'folder';
  moveDialogItem.value = folder;
  showMoveDialog.value = true;
}

function confirmDeleteFolder(folder: Folder) {
  deleteFolderData.value = folder;
  showDeleteFolderDialog.value = true;
}

async function submitDeleteFolder() {
  if (!deleteFolderData.value) {
    return;
  }

  deleteLoading.value = true;
  try {
    await personaStore.deleteFolder(deleteFolderData.value.folder_id);
    showSuccess(tm('folder.messages.deleteSuccess'));
    showDeleteFolderDialog.value = false;
  } catch (error) {
    showError(resolveErrorMessage(error, tm('folder.messages.deleteError')));
  } finally {
    deleteLoading.value = false;
  }
}

function formatDate(dateString: string | undefined | null): string {
  if (!dateString) {
    return '';
  }
  return new Date(dateString).toLocaleString();
}

function showSuccess(successMessage: string) {
  message.value = successMessage;
  messageType.value = 'success';
  showMessage.value = true;
}

function showError(errorMessage: string) {
  message.value = errorMessage;
  messageType.value = 'error';
  showMessage.value = true;
}
</script>

<style scoped>
.persona-manager {
  height: 100%;
}

.manager-layout {
  display: flex;
  gap: 24px;
  height: 100%;
}

.sidebar {
  width: 280px;
  flex-shrink: 0;
  padding-right: 16px;
  height: fit-content;
  max-height: calc(100vh - 200px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.main-content {
  flex: 1;
  min-width: 0;
}

.persona-preview-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 860px);
}

.persona-preview-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.system-prompt-content {
  max-height: 400px;
  overflow: auto;
  padding: 12px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(var(--v-theme-surface-variant), 0.3);
}

.dialog-content {
  background-color: rgba(var(--v-theme-surface-variant), 0.3);
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.4;
  margin-bottom: 8px;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 960px) {
  .manager-layout {
    flex-direction: column;
  }

  .sidebar {
    display: none;
  }
}
</style>
