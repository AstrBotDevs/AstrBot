<template>
    <div class="folder-tree">
        <!-- 搜索框 -->
        <v-text-field v-model="searchQuery" :placeholder="tm('folder.searchPlaceholder')" prepend-inner-icon="mdi-magnify"
            variant="outlined" density="compact" hide-details clearable class="mb-3" />

        <!-- 根目录节点 -->
        <v-list density="compact" nav class="tree-list" bg-color="transparent">
            <v-list-item :active="currentFolderId === null" @click="handleFolderClick(null)" rounded="lg"
                :class="['root-item', { 'drag-over': isRootDragOver }]"
                @dragover.prevent="handleRootDragOver" @dragleave="handleRootDragLeave" @drop.prevent="handleRootDrop">
                <template v-slot:prepend>
                    <v-icon>mdi-home</v-icon>
                </template>
                <v-list-item-title>{{ tm('folder.rootFolder') }}</v-list-item-title>
            </v-list-item>

            <!-- 文件夹树 -->
            <template v-if="!treeLoading">
                <FolderTreeNode v-for="folder in filteredFolderTree" :key="folder.folder_id" :folder="folder"
                    :depth="0" :current-folder-id="currentFolderId" :search-query="searchQuery"
                    @folder-click="handleFolderClick" @folder-context-menu="handleContextMenu"
                    @persona-dropped="$emit('persona-dropped', $event)" />
            </template>

            <!-- 加载状态 -->
            <div v-if="treeLoading" class="text-center pa-4">
                <v-progress-circular indeterminate size="24" />
            </div>

            <!-- 空状态 -->
            <div v-if="!treeLoading && folderTree.length === 0" class="text-center pa-4 text-medium-emphasis">
                <v-icon size="32" class="mb-2">mdi-folder-outline</v-icon>
                <div class="text-body-2">{{ tm('folder.noFolders') }}</div>
            </div>
        </v-list>

        <!-- 右键菜单 -->
        <v-menu v-model="contextMenu.show" :target="contextMenu.target as any" location="end" :close-on-content-click="true">
            <v-list density="compact">
                <v-list-item @click="openFolder">
                    <template v-slot:prepend>
                        <v-icon size="small">mdi-folder-open</v-icon>
                    </template>
                    <v-list-item-title>{{ tm('folder.contextMenu.open') }}</v-list-item-title>
                </v-list-item>
                <v-list-item @click="renameFolder">
                    <template v-slot:prepend>
                        <v-icon size="small">mdi-pencil</v-icon>
                    </template>
                    <v-list-item-title>{{ tm('folder.contextMenu.rename') }}</v-list-item-title>
                </v-list-item>
                <v-list-item @click="$emit('move-folder', contextMenu.folder)">
                    <template v-slot:prepend>
                        <v-icon size="small">mdi-folder-move</v-icon>
                    </template>
                    <v-list-item-title>{{ tm('folder.contextMenu.moveTo') }}</v-list-item-title>
                </v-list-item>
                <v-divider class="my-1" />
                <v-list-item @click="confirmDeleteFolder" class="text-error">
                    <template v-slot:prepend>
                        <v-icon size="small" color="error">mdi-delete</v-icon>
                    </template>
                    <v-list-item-title>{{ tm('folder.contextMenu.delete') }}</v-list-item-title>
                </v-list-item>
            </v-list>
        </v-menu>

        <!-- 重命名对话框 -->
        <v-dialog v-model="renameDialog.show" max-width="400px" persistent>
            <v-card>
                <v-card-title>{{ tm('folder.renameDialog.title') }}</v-card-title>
                <v-card-text>
                    <v-text-field v-model="renameDialog.name" :label="tm('folder.form.name')"
                        :rules="[v => !!v || tm('folder.validation.nameRequired')]" variant="outlined"
                        density="comfortable" autofocus @keyup.enter="submitRename" />
                </v-card-text>
                <v-card-actions>
                    <v-spacer />
                    <v-btn variant="text" @click="renameDialog.show = false">
                        {{ tm('buttons.cancel') }}
                    </v-btn>
                    <v-btn color="primary" variant="flat" @click="submitRename" :loading="renameDialog.loading"
                        :disabled="!renameDialog.name">
                        {{ tm('buttons.save') }}
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

        <!-- 删除确认对话框 -->
        <v-dialog v-model="deleteDialog.show" max-width="450px">
            <v-card>
                <v-card-title class="text-error">
                    <v-icon class="mr-2" color="error">mdi-alert</v-icon>
                    {{ tm('folder.deleteDialog.title') }}
                </v-card-title>
                <v-card-text>
                    <p>{{ tm('folder.deleteDialog.message', { name: deleteDialog.folder?.name ?? '' }) }}</p>
                    <p class="text-warning mt-2">
                        <v-icon size="small" class="mr-1">mdi-information</v-icon>
                        {{ tm('folder.deleteDialog.warning') }}
                    </p>
                </v-card-text>
                <v-card-actions>
                    <v-spacer />
                    <v-btn variant="text" @click="deleteDialog.show = false">
                        {{ tm('buttons.cancel') }}
                    </v-btn>
                    <v-btn color="error" variant="flat" @click="submitDelete" :loading="deleteDialog.loading">
                        {{ tm('buttons.delete') }}
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
    </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { mapState, mapActions } from 'pinia';
import FolderTreeNode from './FolderTreeNode.vue';
import type { FolderTreeNode as FolderTreeNodeType } from '@/components/folder/types';

interface ContextMenuState {
    show: boolean;
    target: [number, number] | null;
    folder: FolderTreeNodeType | null;
}

interface RenameDialogState {
    show: boolean;
    folder: FolderTreeNodeType | null;
    name: string;
    loading: boolean;
}

interface DeleteDialogState {
    show: boolean;
    folder: FolderTreeNodeType | null;
    loading: boolean;
}

export default defineComponent({
    name: 'FolderTree',
    components: {
        FolderTreeNode
    },
    emits: ['move-folder', 'error', 'success', 'persona-dropped'],
    setup() {
        const { tm } = useModuleI18n('features/persona');
        return { tm };
    },
    data() {
        return {
            searchQuery: '',
            isRootDragOver: false,
            contextMenu: {
                show: false,
                target: null,
                folder: null
            } as ContextMenuState,
            renameDialog: {
                show: false,
                folder: null,
                name: '',
                loading: false
            } as RenameDialogState,
            deleteDialog: {
                show: false,
                folder: null,
                loading: false
            } as DeleteDialogState
        };
    },
    computed: {
        ...mapState(usePersonaStore, ['folderTree', 'currentFolderId', 'treeLoading']),

        filteredFolderTree(): FolderTreeNodeType[] {
            if (!this.searchQuery) {
                return this.folderTree as FolderTreeNodeType[];
            }
            const query = this.searchQuery.toLowerCase();
            return this.filterTreeBySearch(this.folderTree as FolderTreeNodeType[], query);
        }
    },
    methods: {
        ...mapActions(usePersonaStore, ['navigateToFolder', 'updateFolder', 'deleteFolder']),

        filterTreeBySearch(nodes: FolderTreeNodeType[], query: string): FolderTreeNodeType[] {
            return nodes.filter(node => {
                const matches = node.name.toLowerCase().includes(query);
                const childMatches = this.filterTreeBySearch(node.children || [], query);
                return matches || childMatches.length > 0;
            }).map(node => ({
                ...node,
                children: this.filterTreeBySearch(node.children || [], query)
            }));
        },

        handleFolderClick(folderId: string | null) {
            this.navigateToFolder(folderId);
        },

        handleRootDragOver(event: DragEvent) {
            if (event.dataTransfer) {
                event.dataTransfer.dropEffect = 'move';
            }
            this.isRootDragOver = true;
        },

        handleRootDragLeave() {
            this.isRootDragOver = false;
        },

        handleRootDrop(event: DragEvent) {
            this.isRootDragOver = false;
            if (!event.dataTransfer) return;
            
            try {
                const data = JSON.parse(event.dataTransfer.getData('application/json'));
                if (data.type === 'persona') {
                    this.$emit('persona-dropped', {
                        persona_id: data.persona_id,
                        target_folder_id: null
                    });
                }
            } catch (e) {
                console.error('Failed to parse drop data:', e);
            }
        },

        handleContextMenu(eventData: { event: MouseEvent; folder: FolderTreeNodeType }) {
            this.contextMenu.target = [eventData.event.clientX, eventData.event.clientY];
            this.contextMenu.folder = eventData.folder;
            this.contextMenu.show = true;
        },

        openFolder() {
            if (this.contextMenu.folder) {
                this.navigateToFolder(this.contextMenu.folder.folder_id);
            }
        },

        renameFolder() {
            if (this.contextMenu.folder) {
                this.renameDialog.folder = this.contextMenu.folder;
                this.renameDialog.name = this.contextMenu.folder.name;
                this.renameDialog.show = true;
            }
        },

        async submitRename() {
            if (!this.renameDialog.name || !this.renameDialog.folder) return;

            this.renameDialog.loading = true;
            try {
                await this.updateFolder({
                    folder_id: this.renameDialog.folder.folder_id,
                    name: this.renameDialog.name
                });
                this.$emit('success', this.tm('folder.messages.renameSuccess'));
                this.renameDialog.show = false;
            } catch (error: any) {
                this.$emit('error', error.message || this.tm('folder.messages.renameError'));
            } finally {
                this.renameDialog.loading = false;
            }
        },

        confirmDeleteFolder() {
            if (this.contextMenu.folder) {
                this.deleteDialog.folder = this.contextMenu.folder;
                this.deleteDialog.show = true;
            }
        },

        async submitDelete() {
            if (!this.deleteDialog.folder) return;

            this.deleteDialog.loading = true;
            try {
                await this.deleteFolder(this.deleteDialog.folder.folder_id);
                this.$emit('success', this.tm('folder.messages.deleteSuccess'));
                this.deleteDialog.show = false;
            } catch (error: any) {
                this.$emit('error', error.message || this.tm('folder.messages.deleteError'));
            } finally {
                this.deleteDialog.loading = false;
            }
        }
    }
});
</script>

<style scoped>
.folder-tree {
    height: 100%;
    display: flex;
    flex-direction: column;
}

.tree-list {
    flex: 1;
    overflow-y: auto;
}

.root-item {
    margin-bottom: 4px;
    transition: all 0.2s ease;
}

.root-item.drag-over {
    background-color: rgba(var(--v-theme-primary), 0.15);
    border: 2px dashed rgb(var(--v-theme-primary));
    border-radius: 8px;
}
</style>
