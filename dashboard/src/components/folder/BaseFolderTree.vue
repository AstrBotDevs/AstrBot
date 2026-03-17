<template>
    <div class="base-folder-tree">
        <!-- 搜索框 -->
        <v-text-field v-model="searchQuery" :placeholder="labels.searchPlaceholder" prepend-inner-icon="mdi-magnify"
            variant="outlined" density="compact" hide-details clearable class="mb-3" />

        <!-- 根目录节点 -->
        <v-list density="compact" nav class="tree-list" bg-color="transparent">
            <v-list-item :active="currentFolderId === null" @click="handleFolderClick(null)" rounded="lg"
                :class="['root-item', { 'drag-over': isRootDragOver }]"
                @dragover.prevent="handleRootDragOver" @dragleave="handleRootDragLeave" @drop.prevent="handleRootDrop">
                <template v-slot:prepend>
                    <v-icon>mdi-home</v-icon>
                </template>
                <v-list-item-title>{{ labels.rootFolder }}</v-list-item-title>
            </v-list-item>

            <!-- 文件夹树 -->
            <template v-if="!treeLoading">
                <BaseFolderTreeNode v-for="folder in filteredFolderTree" :key="folder.folder_id" :folder="folder"
                    :depth="0" :current-folder-id="currentFolderId" :search-query="searchQuery"
                    :expanded-folder-ids="expandedFolderIds" :accept-drop-types="acceptDropTypes"
                    @folder-click="handleFolderClick" @folder-context-menu="handleContextMenu"
                    @item-dropped="$emit('item-dropped', $event)"
                    @toggle-expansion="$emit('toggle-expansion', $event)"
                    @set-expansion="$emit('set-expansion', $event)" />
            </template>

            <!-- 加载状态 -->
            <div v-if="treeLoading" class="text-center pa-4">
                <v-progress-circular indeterminate size="24" />
            </div>

            <!-- 空状态 -->
            <div v-if="!treeLoading && folderTree.length === 0" class="text-center pa-4 text-medium-emphasis">
                <v-icon size="32" class="mb-2">mdi-folder-outline</v-icon>
                <div class="text-body-2">{{ labels.noFolders }}</div>
            </div>
        </v-list>

        <!-- 右键菜单 -->
        <v-menu v-model="contextMenu.show" :target="contextMenu.target as any" location="end" :close-on-content-click="true">
            <v-list density="compact">
                <v-list-item @click="openFolder">
                    <template v-slot:prepend>
                        <v-icon size="small">mdi-folder-open</v-icon>
                    </template>
                    <v-list-item-title>{{ mergedLabels.contextMenu.open }}</v-list-item-title>
                </v-list-item>
                <v-list-item @click="$emit('rename-folder', contextMenu.folder)">
                    <template v-slot:prepend>
                        <v-icon size="small">mdi-pencil</v-icon>
                    </template>
                    <v-list-item-title>{{ mergedLabels.contextMenu.rename }}</v-list-item-title>
                </v-list-item>
                <v-list-item @click="$emit('move-folder', contextMenu.folder)">
                    <template v-slot:prepend>
                        <v-icon size="small">mdi-folder-move</v-icon>
                    </template>
                    <v-list-item-title>{{ mergedLabels.contextMenu.moveTo }}</v-list-item-title>
                </v-list-item>
                <v-divider class="my-1" />
                <v-list-item @click="$emit('delete-folder', contextMenu.folder)" class="text-error">
                    <template v-slot:prepend>
                        <v-icon size="small" color="error">mdi-delete</v-icon>
                    </template>
                    <v-list-item-title>{{ mergedLabels.contextMenu.delete }}</v-list-item-title>
                </v-list-item>
            </v-list>
        </v-menu>
    </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import type { FolderTreeNode, ContextMenuEvent } from './types';
import BaseFolderTreeNode from './BaseFolderTreeNode.vue';

interface ContextMenuState {
    show: boolean;
    target: [number, number] | null;
    folder: FolderTreeNode | null;
}

interface Folder {
    folder_id: string;
    name: string;
    parent_id: string | null;
    description?: string | null;
    sort_order?: number;
    created_at?: string;
    updated_at?: string;
}

interface DefaultLabels {
    searchPlaceholder: string;
    rootFolder: string;
    noFolders: string;
    contextMenu: {
        open: string;
        rename: string;
        moveTo: string;
        delete: string;
    };
}

const defaultLabels: DefaultLabels = {
    searchPlaceholder: '搜索文件夹...',
    rootFolder: '根目录',
    noFolders: '暂无文件夹',
    contextMenu: {
        open: '打开',
        rename: '重命名',
        moveTo: '移动到...',
        delete: '删除'
    }
};

export default defineComponent({
    name: 'BaseFolderTree',
    components: {
        BaseFolderTreeNode
    },
    props: {
        folderTree: {
            type: Array as PropType<FolderTreeNode[]>,
            required: true
        },
        currentFolderId: {
            type: String as PropType<string | null>,
            default: null
        },
        expandedFolderIds: {
            type: Array as PropType<string[]>,
            default: () => []
        },
        treeLoading: {
            type: Boolean,
            default: false
        },
        acceptDropTypes: {
            type: Array as PropType<string[]>,
            default: () => []
        },
        labels: {
            type: Object as PropType<Partial<DefaultLabels>>,
            default: () => ({})
        }
    },
    emits: [
        'folder-click',
        'rename-folder',
        'move-folder',
        'delete-folder',
        'item-dropped',
        'toggle-expansion',
        'set-expansion'
    ],
    data() {
        return {
            searchQuery: '',
            isRootDragOver: false,
            contextMenu: {
                show: false,
                target: null,
                folder: null
            } as ContextMenuState
        };
    },
    computed: {
        mergedLabels(): DefaultLabels {
            return {
                ...defaultLabels,
                ...this.labels,
                contextMenu: {
                    ...defaultLabels.contextMenu,
                    ...(this.labels?.contextMenu || {})
                }
            };
        },
        filteredFolderTree(): FolderTreeNode[] {
            if (!this.searchQuery) {
                return this.folderTree;
            }
            const query = this.searchQuery.toLowerCase();
            return this.filterTreeBySearch(this.folderTree, query);
        }
    },
    methods: {
        filterTreeBySearch(nodes: FolderTreeNode[], query: string): FolderTreeNode[] {
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
            this.$emit('folder-click', folderId);
        },

        handleRootDragOver(event: DragEvent) {
            if (!event.dataTransfer) return;
            event.dataTransfer.dropEffect = 'move';
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
                if (this.acceptDropTypes.length === 0 || this.acceptDropTypes.includes(data.type)) {
                    this.$emit('item-dropped', {
                        item_id: data.id || data.persona_id || data.item_id,
                        item_type: data.type,
                        target_folder_id: null,
                        source_data: data
                    });
                }
            } catch (e) {
                console.error('Failed to parse drop data:', e);
            }
        },

        handleContextMenu(eventData: ContextMenuEvent) {
            const { event, folder } = eventData;
            this.contextMenu.target = [event.clientX, event.clientY];
            this.contextMenu.folder = folder as FolderTreeNode;
            this.contextMenu.show = true;
        },

        openFolder() {
            if (this.contextMenu.folder) {
                this.$emit('folder-click', this.contextMenu.folder.folder_id);
            }
        }
    }
});
</script>

<style scoped>
.base-folder-tree {
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
