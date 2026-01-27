<template>
    <div class="persona-manager">
        <!-- 移动端顶部导航 -->
        <div class="mobile-nav d-md-none mb-4">
            <FolderBreadcrumb />
        </div>

        <div class="manager-layout">
            <!-- 左侧边栏 - 仅桌面端显示 -->
            <div class="sidebar d-none d-md-block">
                <div class="sidebar-header d-flex justify-space-between align-center mb-3">
                    <h3 class="text-h6">{{ tm('folder.sidebarTitle') }}</h3>
                    <v-btn icon="mdi-folder-plus" variant="text" size="small" @click="showCreateFolderDialog = true"
                        :title="tm('folder.createButton')" />
                </div>
                <FolderTree @move-folder="openMoveFolderDialog" @success="showSuccess" @error="showError"
                    @persona-dropped="handlePersonaDropped" />
            </div>

            <!-- 主内容区 -->
            <div class="main-content">
                <!-- 顶部工具栏 -->
                <div class="toolbar d-flex flex-wrap justify-space-between align-center mb-4 ga-2">
                    <!-- 面包屑 - 仅桌面端显示 -->
                    <div class="d-none d-md-block">
                        <FolderBreadcrumb />
                    </div>

                    <!-- 操作按钮组 -->
                    <div class="d-flex ga-2">
                        <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openCreatePersonaDialog"
                            rounded="lg">
                            {{ tm('buttons.create') }}
                        </v-btn>
                        <v-btn variant="outlined" prepend-icon="mdi-folder-plus" @click="showCreateFolderDialog = true"
                            rounded="lg">
                            {{ tm('folder.createButton') }}
                        </v-btn>
                    </div>
                </div>

                <!-- 加载状态 - 只有加载超过阈值才显示骨架屏 -->
                <v-fade-transition>
                    <div v-if="showSkeleton" class="loading-container">
                        <v-row>
                            <v-col v-for="n in 6" :key="n" cols="12" sm="6" lg="4" xl="3">
                                <v-skeleton-loader type="card" rounded="lg" />
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
                            <v-col v-for="folder in currentFolders" :key="folder.folder_id" cols="12" sm="6" lg="4"
                                xl="3">
                                <FolderCard :folder="folder" @click="navigateToFolder(folder.folder_id)"
                                    @open="navigateToFolder(folder.folder_id)" @rename="openRenameFolderDialog(folder)"
                                    @move="openMoveFolderDialog(folder)" @delete="confirmDeleteFolder(folder)"
                                    @persona-dropped="handlePersonaDropped" />
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
                            <v-col v-for="persona in currentPersonas" :key="persona.persona_id" cols="12" sm="6" lg="4"
                                xl="3">
                                <PersonaCard :persona="persona" @view="viewPersona(persona)"
                                    @edit="editPersona(persona)" @move="openMovePersonaDialog(persona)"
                                    @delete="confirmDeletePersona(persona)" />
                            </v-col>
                        </v-row>
                    </div>

                    <!-- 空状态 -->
                    <div v-if="currentFolders.length === 0 && currentPersonas.length === 0" class="empty-state">
                        <v-card class="text-center pa-8" elevation="0">
                            <v-icon size="64" color="grey-lighten-1" class="mb-4">mdi-folder-open-outline</v-icon>
                            <h3 class="text-h5 mb-2">{{ tm('empty.folderEmpty') }}</h3>
                            <p class="text-body-1 text-medium-emphasis mb-4">{{ tm('empty.folderEmptyDescription') }}</p>
                            <div class="d-flex justify-center ga-2">
                                <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus"
                                    @click="openCreatePersonaDialog">
                                    {{ tm('buttons.create') }}
                                </v-btn>
                                <v-btn variant="outlined" prepend-icon="mdi-folder-plus"
                                    @click="showCreateFolderDialog = true">
                                    {{ tm('folder.createButton') }}
                                </v-btn>
                            </div>
                        </v-card>
                    </div>
                </div>
            </div>
        </div>

        <!-- 创建/编辑 Persona 对话框 -->
        <PersonaForm v-model="showPersonaDialog" :editing-persona="editingPersona ?? undefined"
            :current-folder-id="currentFolderId ?? undefined" :current-folder-name="currentFolderName ?? undefined"
            @saved="handlePersonaSaved" @error="showError" />

        <!-- 查看 Persona 详情对话框 -->
        <v-dialog v-model="showViewDialog" max-width="700px">
            <v-card v-if="viewingPersona">
                <v-card-title class="d-flex justify-space-between align-center">
                    <span class="text-h5">{{ viewingPersona.persona_id }}</span>
                    <v-btn icon="mdi-close" variant="text" @click="showViewDialog = false" />
                </v-card-title>

                <v-card-text>
                    <div class="mb-4">
                        <h4 class="text-h6 mb-2">{{ tm('form.systemPrompt') }}</h4>
                        <pre class="system-prompt-content">{{ viewingPersona.system_prompt }}</pre>
                    </div>

                    <div v-if="viewingPersona.begin_dialogs && viewingPersona.begin_dialogs.length > 0" class="mb-4">
                        <h4 class="text-h6 mb-2">{{ tm('form.presetDialogs') }}</h4>
                        <div v-for="(dialog, index) in viewingPersona.begin_dialogs" :key="index" class="mb-2">
                            <v-chip :color="index % 2 === 0 ? 'primary' : 'secondary'" variant="tonal" size="small"
                                class="mb-1">
                                {{ index % 2 === 0 ? tm('form.userMessage') : tm('form.assistantMessage') }}
                            </v-chip>
                            <div class="dialog-content ml-2">{{ dialog }}</div>
                        </div>
                    </div>

                    <div class="mb-4">
                        <h4 class="text-h6 mb-2">{{ tm('form.tools') }}</h4>
                        <div v-if="viewingPersona.tools === null" class="text-body-2 text-medium-emphasis">
                            <v-chip size="small" color="success" variant="tonal" prepend-icon="mdi-check-all">
                                {{ tm('form.allToolsAvailable') }}
                            </v-chip>
                        </div>
                        <div v-else-if="viewingPersona.tools && viewingPersona.tools.length > 0"
                            class="d-flex flex-wrap ga-1">
                            <v-chip v-for="toolName in viewingPersona.tools" :key="toolName" size="small"
                                color="primary" variant="tonal">
                                {{ toolName }}
                            </v-chip>
                        </div>
                        <div v-else class="text-body-2 text-medium-emphasis">
                            {{ tm('form.noToolsSelected') }}
                        </div>
                    </div>

                    <div class="mb-4">
                        <h4 class="text-h6 mb-2">{{ tm('form.skills') }}</h4>
                        <div v-if="viewingPersona.skills === null" class="text-body-2 text-medium-emphasis">
                            <v-chip size="small" color="success" variant="tonal" prepend-icon="mdi-check-all">
                                {{ tm('form.allSkillsAvailable') }}
                            </v-chip>
                        </div>
                        <div v-else-if="viewingPersona.skills && viewingPersona.skills.length > 0"
                            class="d-flex flex-wrap ga-1">
                            <v-chip v-for="skillName in viewingPersona.skills" :key="skillName" size="small"
                                color="primary" variant="tonal">
                                {{ skillName }}
                            </v-chip>
                        </div>
                        <div v-else class="text-body-2 text-medium-emphasis">
                            {{ tm('form.noSkillsSelected') }}
                        </div>
                    </div>

                    <div class="text-caption text-medium-emphasis">
                        <div>{{ tm('labels.createdAt') }}: {{ formatDate(viewingPersona.created_at) }}</div>
                        <div v-if="viewingPersona.updated_at">{{ tm('labels.updatedAt') }}:
                            {{ formatDate(viewingPersona.updated_at) }}</div>
                    </div>
                </v-card-text>
            </v-card>
        </v-dialog>

        <!-- 创建文件夹对话框 -->
        <CreateFolderDialog v-model="showCreateFolderDialog" :parent-folder-id="currentFolderId"
            @created="showSuccess" @error="showError" />

        <!-- 重命名文件夹对话框 -->
        <v-dialog v-model="showRenameFolderDialog" max-width="400px">
            <v-card>
                <v-card-title>{{ tm('folder.renameDialog.title') }}</v-card-title>
                <v-card-text>
                    <v-text-field v-model="renameFolderData.name" :label="tm('folder.form.name')"
                        :rules="[v => !!v || tm('folder.validation.nameRequired')]" variant="outlined"
                        density="comfortable" autofocus @keyup.enter="submitRenameFolder" />
                </v-card-text>
                <v-card-actions>
                    <v-spacer />
                    <v-btn variant="text" @click="showRenameFolderDialog = false">
                        {{ tm('buttons.cancel') }}
                    </v-btn>
                    <v-btn color="primary" variant="flat" @click="submitRenameFolder" :loading="renameLoading"
                        :disabled="!renameFolderData.name">
                        {{ tm('buttons.save') }}
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <!-- 移动对话框 -->
        <MoveToFolderDialog v-model="showMoveDialog" :item-type="moveDialogType" :item="moveDialogItem"
            @moved="showSuccess" @error="showError" />

        <!-- 删除文件夹确认对话框 -->
        <v-dialog v-model="showDeleteFolderDialog" max-width="450px">
            <v-card>
                <v-card-title class="text-error">
                    <v-icon class="mr-2" color="error">mdi-alert</v-icon>
                    {{ tm('folder.deleteDialog.title') }}
                </v-card-title>
                <v-card-text>
                    <p>{{ tm('folder.deleteDialog.message', { name: deleteFolderData?.name ?? '' }) }}</p>
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
                    <v-btn color="error" variant="flat" @click="submitDeleteFolder" :loading="deleteLoading">
                        {{ tm('buttons.delete') }}
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <!-- 消息提示 -->
        <v-snackbar :timeout="3000" elevation="24" :color="messageType" v-model="showMessage" location="top">
            {{ message }}
        </v-snackbar>
    </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { mapState, mapActions } from 'pinia';

import FolderTree from './FolderTree.vue';
import FolderBreadcrumb from './FolderBreadcrumb.vue';
import FolderCard from './FolderCard.vue';
import PersonaCard from './PersonaCard.vue';
import PersonaForm from '@/components/shared/PersonaForm.vue';
import CreateFolderDialog from './CreateFolderDialog.vue';
import MoveToFolderDialog from './MoveToFolderDialog.vue';

import type { Folder, FolderTreeNode } from '@/components/folder/types';

interface Persona {
    persona_id: string;
    system_prompt: string;
    begin_dialogs?: string[] | null;
    tools?: string[] | null;
    skills?: string[] | null;
    created_at?: string;
    updated_at?: string;
    folder_id?: string | null;
    [key: string]: any;
}

interface RenameFolderData {
    folder: Folder | null;
    name: string;
}

export default defineComponent({
    name: 'PersonaManager',
    components: {
        FolderTree,
        FolderBreadcrumb,
        FolderCard,
        PersonaCard,
        PersonaForm,
        CreateFolderDialog,
        MoveToFolderDialog
    },
    setup() {
        const { t } = useI18n();
        const { tm } = useModuleI18n('features/persona');
        return { t, tm };
    },
    data() {
        return {
            // Persona 相关
            showPersonaDialog: false,
            showViewDialog: false,
            editingPersona: null as Persona | null,
            viewingPersona: null as Persona | null,

            // 文件夹相关
            showCreateFolderDialog: false,
            showRenameFolderDialog: false,
            showDeleteFolderDialog: false,
            renameFolderData: { folder: null, name: '' } as RenameFolderData,
            deleteFolderData: null as Folder | null,
            renameLoading: false,
            deleteLoading: false,

            // 移动对话框
            showMoveDialog: false,
            moveDialogType: 'persona' as 'persona' | 'folder',
            moveDialogItem: null as Persona | Folder | null,

            // 消息提示
            showMessage: false,
            message: '',
            messageType: 'success' as 'success' | 'error',

            // 骨架屏延迟显示控制
            showSkeleton: false,
            skeletonTimer: null as ReturnType<typeof setTimeout> | null
        };
    },
    computed: {
        ...mapState(usePersonaStore, ['folderTree', 'currentFolderId', 'currentFolders', 'currentPersonas', 'loading']),
        currentFolderName(): string | null {
            if (!this.currentFolderId) {
                return null; // 根目录，PersonaForm 会使用 tm('form.rootFolder')
            }
            // 递归查找文件夹名称
            const findName = (nodes: FolderTreeNode[], id: string): string | null => {
                for (const node of nodes) {
                    if (node.folder_id === id) {
                        return node.name;
                    }
                    if (node.children && node.children.length > 0) {
                        const found = findName(node.children, id);
                        if (found) return found;
                    }
                }
                return null;
            };
            return findName(this.folderTree, this.currentFolderId);
        }
    },
    watch: {
        // 监听 loading 状态变化，实现延迟显示骨架屏
        loading: {
            handler(newVal: boolean) {
                if (newVal) {
                    // 加载开始时，延迟 150ms 后才显示骨架屏
                    // 如果加载在 150ms 内完成，则不显示骨架屏，避免闪烁
                    this.skeletonTimer = setTimeout(() => {
                        if (this.loading) {
                            this.showSkeleton = true;
                        }
                    }, 150);
                } else {
                    // 加载结束，立即隐藏骨架屏并清除定时器
                    if (this.skeletonTimer) {
                        clearTimeout(this.skeletonTimer);
                        this.skeletonTimer = null;
                    }
                    this.showSkeleton = false;
                }
            },
            immediate: true
        }
    },
    beforeUnmount() {
        // 组件卸载时清除定时器
        if (this.skeletonTimer) {
            clearTimeout(this.skeletonTimer);
        }
    },
    async mounted() {
        await this.initialize();
    },
    methods: {
        ...mapActions(usePersonaStore, ['loadFolderTree', 'navigateToFolder', 'updateFolder', 'deleteFolder', 'deletePersona', 'refreshCurrentFolder', 'movePersonaToFolder']),

        async initialize() {
            await Promise.all([
                this.loadFolderTree(),
                this.navigateToFolder(null)
            ]);
        },

        // Persona 操作
        openCreatePersonaDialog() {
            this.editingPersona = null;
            this.showPersonaDialog = true;
        },

        editPersona(persona: Persona) {
            this.editingPersona = persona;
            this.showPersonaDialog = true;
        },

        viewPersona(persona: Persona) {
            this.viewingPersona = persona;
            this.showViewDialog = true;
        },

        handlePersonaSaved(message: string) {
            this.showSuccess(message);
            this.refreshCurrentFolder();
        },

        async confirmDeletePersona(persona: Persona) {
            if (!confirm(this.tm('messages.deleteConfirm', { id: persona.persona_id }))) {
                return;
            }

            try {
                await this.deletePersona(persona.persona_id);
                this.showSuccess(this.tm('messages.deleteSuccess'));
            } catch (error: any) {
                this.showError(error.message || this.tm('messages.deleteError'));
            }
        },

        openMovePersonaDialog(persona: Persona) {
            this.moveDialogType = 'persona';
            this.moveDialogItem = persona;
            this.showMoveDialog = true;
        },

        async handlePersonaDropped({ persona_id, target_folder_id }: { persona_id: string; target_folder_id: string | null }) {
            try {
                await this.movePersonaToFolder(persona_id, target_folder_id);
                this.showSuccess(this.tm('persona.messages.moveSuccess'));
                // Navigate to the target folder
                await this.navigateToFolder(target_folder_id);
            } catch (error: any) {
                this.showError(error.message || this.tm('persona.messages.moveError'));
            }
        },

        // 文件夹操作
        openRenameFolderDialog(folder: Folder) {
            this.renameFolderData = { folder, name: folder.name };
            this.showRenameFolderDialog = true;
        },

        async submitRenameFolder() {
            if (!this.renameFolderData.name || !this.renameFolderData.folder) return;

            this.renameLoading = true;
            try {
                await this.updateFolder({
                    folder_id: this.renameFolderData.folder.folder_id,
                    name: this.renameFolderData.name
                });
                this.showSuccess(this.tm('folder.messages.renameSuccess'));
                this.showRenameFolderDialog = false;
            } catch (error: any) {
                this.showError(error.message || this.tm('folder.messages.renameError'));
            } finally {
                this.renameLoading = false;
            }
        },

        openMoveFolderDialog(folder: Folder) {
            this.moveDialogType = 'folder';
            this.moveDialogItem = folder;
            this.showMoveDialog = true;
        },

        confirmDeleteFolder(folder: Folder) {
            this.deleteFolderData = folder;
            this.showDeleteFolderDialog = true;
        },

        async submitDeleteFolder() {
            if (!this.deleteFolderData) return;

            this.deleteLoading = true;
            try {
                await this.deleteFolder(this.deleteFolderData.folder_id);
                this.showSuccess(this.tm('folder.messages.deleteSuccess'));
                this.showDeleteFolderDialog = false;
            } catch (error: any) {
                this.showError(error.message || this.tm('folder.messages.deleteError'));
            } finally {
                this.deleteLoading = false;
            }
        },

        // 辅助方法
        formatDate(dateString: string | undefined | null): string {
            if (!dateString) return '';
            return new Date(dateString).toLocaleString();
        },

        showSuccess(message: string) {
            this.message = message;
            this.messageType = 'success';
            this.showMessage = true;
        },

        showError(message: string) {
            this.message = message;
            this.messageType = 'error';
            this.showMessage = true;
        }
    }
});
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
