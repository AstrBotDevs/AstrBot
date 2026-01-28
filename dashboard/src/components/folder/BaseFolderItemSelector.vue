<template>
    <div class="folder-item-selector">
        <!-- 触发按钮区域 -->
        <div class="d-flex align-center justify-space-between">
            <span v-if="!modelValue" style="color: rgb(var(--v-theme-primaryText));">
                {{ labels.notSelected || '未选择' }}
            </span>
            <span v-else>
                {{ displayValue }}
            </span>
            <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
                {{ labels.buttonText || '选择...' }}
            </v-btn>
        </div>

        <!-- 选择对话框 -->
        <v-dialog v-model="dialog" max-width="1000px" min-width="800px">
            <v-card class="selector-dialog-card">
                <v-card-title class="dialog-title d-flex align-center py-4 px-5">
                    <v-icon class="mr-3" color="primary">mdi-account-circle</v-icon>
                    <span>{{ labels.dialogTitle || '选择项目' }}</span>
                </v-card-title>

                <v-divider />

                <v-card-text class="pa-0" style="height: 600px; max-height: 80vh; overflow: hidden;">
                    <div class="selector-layout">
                        <!-- 左侧文件夹树 -->
                        <div class="folder-sidebar">
                            <div class="sidebar-header pa-3 pb-2">
                                <span class="text-caption text-medium-emphasis font-weight-medium">
                                    <v-icon size="small" class="mr-1">mdi-folder-multiple</v-icon>
                                    文件夹
                                </span>
                            </div>
                            <v-list density="compact" nav class="tree-list pa-2" bg-color="transparent">
                                <!-- 根目录 -->
                                <v-list-item :active="currentFolderId === null" @click="navigateToFolder(null)"
                                    rounded="lg" class="mb-1 root-item">
                                    <template v-slot:prepend>
                                        <v-icon size="20" :color="currentFolderId === null ? 'primary' : ''">mdi-home</v-icon>
                                    </template>
                                    <v-list-item-title class="text-body-2">{{ labels.rootFolder || '根目录' }}</v-list-item-title>
                                </v-list-item>

                                <!-- 文件夹树 -->
                                <template v-if="!treeLoading">
                                    <BaseMoveTargetNode v-for="folder in folderTree" :key="folder.folder_id"
                                        :folder="folder" :depth="0" :selected-folder-id="currentFolderId"
                                        :disabled-folder-ids="[]" @select="navigateToFolder" />
                                </template>

                                <div v-if="treeLoading" class="text-center pa-4">
                                    <v-progress-circular indeterminate size="20" color="primary" />
                                </div>
                            </v-list>
                        </div>

                        <!-- 右侧项目列表 -->
                        <div class="items-panel">
                            <!-- 面包屑导航 -->
                            <div class="breadcrumb-bar px-4 py-3">
                                <v-breadcrumbs :items="breadcrumbItems" density="compact" class="pa-0">
                                    <template v-slot:item="{ item }">
                                        <v-breadcrumbs-item :disabled="(item as any).disabled"
                                            @click="!(item as any).disabled && navigateToFolder((item as any).folderId)"
                                            :class="{ 'breadcrumb-link': !(item as any).disabled }">
                                            <v-icon v-if="(item as any).isRoot" size="small"
                                                class="mr-1">mdi-home</v-icon>
                                            {{ item.title }}
                                        </v-breadcrumbs-item>
                                    </template>
                                    <template v-slot:divider>
                                        <v-icon size="small" color="grey">mdi-chevron-right</v-icon>
                                    </template>
                                </v-breadcrumbs>
                            </div>

                            <v-divider />

                            <!-- 项目列表 -->
                            <div class="items-list">
                                <v-progress-linear v-if="itemsLoading" indeterminate
                                    color="primary" height="2"></v-progress-linear>

                                <!-- 子文件夹 -->
                                <v-list v-if="!itemsLoading" lines="two" class="pa-3 items-content">
                                    <template v-if="currentSubFolders.length > 0">
                                        <div class="section-label text-caption text-medium-emphasis mb-2 px-2">子文件夹</div>
                                        <v-list-item v-for="folder in currentSubFolders" :key="'folder-' + folder.folder_id"
                                            @click="navigateToFolder(folder.folder_id)" rounded="lg" class="mb-1 folder-item">
                                            <template v-slot:prepend>
                                                <v-avatar size="36" color="amber-lighten-4" class="mr-3">
                                                    <v-icon color="amber-darken-2" size="20">mdi-folder</v-icon>
                                                </v-avatar>
                                            </template>
                                            <v-list-item-title class="font-weight-medium">{{ folder.name }}</v-list-item-title>
                                            <template v-slot:append>
                                                <v-icon size="20" color="grey">mdi-chevron-right</v-icon>
                                            </template>
                                        </v-list-item>
                                    </template>

                                    <!-- 项目列表 -->
                                    <template v-if="currentItems.length > 0">
                                        <div class="section-label text-caption text-medium-emphasis mb-2 px-2" :class="{ 'mt-4': currentSubFolders.length > 0 }">可选项目</div>
                                        <v-list-item v-for="item in currentItems" :key="'item-' + getItemId(item)"
                                            :value="getItemId(item)" @click="selectItem(item)"
                                            :active="selectedItemId === getItemId(item)" rounded="lg" class="mb-1 persona-item"
                                            :class="{ 'selected-item': selectedItemId === getItemId(item) }">
                                            <template v-slot:prepend>
                                                <v-avatar size="36" :color="selectedItemId === getItemId(item) ? 'primary-lighten-4' : 'grey-lighten-3'" class="mr-3">
                                                    <v-icon :color="selectedItemId === getItemId(item) ? 'primary' : 'grey-darken-1'" size="20">mdi-account</v-icon>
                                                </v-avatar>
                                            </template>
                                            <v-list-item-title class="font-weight-medium">{{ getItemName(item) }}</v-list-item-title>
                                            <v-list-item-subtitle v-if="getItemDescription(item)" class="text-truncate">
                                                {{ truncateText(getItemDescription(item), 80) }}
                                            </v-list-item-subtitle>

                                            <template v-slot:append>
                                                <v-icon v-if="selectedItemId === getItemId(item)"
                                                    color="primary" size="22">mdi-check-circle</v-icon>
                                            </template>
                                        </v-list-item>
                                    </template>

                                    <!-- 空状态 -->
                                    <div v-if="currentSubFolders.length === 0 && currentItems.length === 0"
                                        class="empty-state text-center py-12">
                                        <v-icon size="64" color="grey-lighten-2">mdi-folder-open-outline</v-icon>
                                        <p class="text-grey mt-4 text-body-2">{{ labels.emptyFolder || labels.noItems || '此文件夹为空' }}</p>
                                    </div>
                                </v-list>
                            </div>
                        </div>
                    </div>
                </v-card-text>

                <v-card-actions class="pa-4">
                    <v-btn v-if="showCreateButton" variant="text" color="primary" prepend-icon="mdi-plus"
                        @click="$emit('create')">
                        {{ labels.createButton || '新建' }}
                    </v-btn>
                    <v-spacer></v-spacer>
                    <v-btn variant="text" @click="cancelSelection">{{ labels.cancelButton || '取消' }}</v-btn>
                    <v-btn color="primary" @click="confirmSelection" :disabled="!selectedItemId">
                        {{ labels.confirmButton || '确认' }}
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
    </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import BaseMoveTargetNode from './BaseMoveTargetNode.vue';
import type { FolderTreeNode, FolderItemSelectorLabels, SelectableItem } from './types';

export default defineComponent({
    name: 'BaseFolderItemSelector',
    components: {
        BaseMoveTargetNode
    },
    props: {
        modelValue: {
            type: String,
            default: ''
        },
        // 文件夹树数据
        folderTree: {
            type: Array as PropType<FolderTreeNode[]>,
            default: () => []
        },
        // 当前项目列表
        items: {
            type: Array as PropType<SelectableItem[]>,
            default: () => []
        },
        // 加载状态
        treeLoading: {
            type: Boolean,
            default: false
        },
        itemsLoading: {
            type: Boolean,
            default: false
        },
        // 标签配置
        labels: {
            type: Object as PropType<Partial<FolderItemSelectorLabels>>,
            default: () => ({})
        },
        // 是否显示创建按钮
        showCreateButton: {
            type: Boolean,
            default: false
        },
        // 默认项（如 "默认人格"）
        defaultItem: {
            type: Object as PropType<SelectableItem | null>,
            default: null
        },
        // 项目字段映射
        itemIdField: {
            type: String,
            default: 'id'
        },
        itemNameField: {
            type: String,
            default: 'name'
        },
        itemDescriptionField: {
            type: String,
            default: 'description'
        },
        // 显示值的格式化函数（用于显示选中项的名称）
        displayValueFormatter: {
            type: Function as unknown as PropType<((value: string) => string) | null>,
            default: null
        }
    },
    emits: ['update:modelValue', 'navigate', 'create'],
    data() {
        return {
            dialog: false,
            selectedItemId: '' as string,
            currentFolderId: null as string | null,
            breadcrumbPath: [] as FolderTreeNode[]
        };
    },
    computed: {
        displayValue(): string {
            if (this.displayValueFormatter) {
                return this.displayValueFormatter(this.modelValue);
            }
            // 如果是默认项
            if (this.defaultItem && this.modelValue === this.getItemId(this.defaultItem)) {
                return this.labels.defaultItem || this.getItemName(this.defaultItem);
            }
            return this.modelValue;
        },

        currentItems(): SelectableItem[] {
            const items: SelectableItem[] = [];

            // 如果在根目录且有默认项，添加到列表开头
            if (this.currentFolderId === null && this.defaultItem) {
                items.push(this.defaultItem);
            }

            // 添加当前文件夹的项目
            items.push(...this.items);

            return items;
        },

        currentSubFolders(): FolderTreeNode[] {
            if (this.currentFolderId === null) {
                return this.folderTree;
            }
            const folder = this.findFolderInTree(this.currentFolderId);
            return folder?.children || [];
        },

        breadcrumbItems(): any[] {
            const items: any[] = [
                {
                    title: this.labels.rootFolder || '根目录',
                    folderId: null,
                    disabled: this.currentFolderId === null,
                    isRoot: true
                }
            ];

            this.breadcrumbPath.forEach((folder, index) => {
                items.push({
                    title: folder.name,
                    folderId: folder.folder_id,
                    disabled: index === this.breadcrumbPath.length - 1,
                    isRoot: false
                });
            });

            return items;
        }
    },
    methods: {
        getItemId(item: SelectableItem): string {
            return String(item[this.itemIdField] || item.id || '');
        },

        getItemName(item: SelectableItem): string {
            return String(item[this.itemNameField] || item.name || '');
        },

        getItemDescription(item: SelectableItem): string {
            return String(item[this.itemDescriptionField] || item.description || '');
        },

        truncateText(text: string, maxLength: number): string {
            if (!text) return '';
            return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
        },

        openDialog() {
            this.selectedItemId = this.modelValue || '';
            this.currentFolderId = null;
            this.breadcrumbPath = [];
            this.dialog = true;
            this.$emit('navigate', null);
        },

        navigateToFolder(folderId: string | null) {
            this.currentFolderId = folderId;
            this.updateBreadcrumb(folderId);
            this.$emit('navigate', folderId);
        },

        findFolderInTree(folderId: string): FolderTreeNode | null {
            const findNode = (nodes: FolderTreeNode[]): FolderTreeNode | null => {
                for (const node of nodes) {
                    if (node.folder_id === folderId) {
                        return node;
                    }
                    if (node.children && node.children.length > 0) {
                        const found = findNode(node.children);
                        if (found) return found;
                    }
                }
                return null;
            };
            return findNode(this.folderTree);
        },

        findPathToFolder(folderId: string): FolderTreeNode[] {
            const findPath = (nodes: FolderTreeNode[], path: FolderTreeNode[]): FolderTreeNode[] | null => {
                for (const node of nodes) {
                    if (node.folder_id === folderId) {
                        return [...path, node];
                    }
                    if (node.children && node.children.length > 0) {
                        const result = findPath(node.children, [...path, node]);
                        if (result) return result;
                    }
                }
                return null;
            };
            return findPath(this.folderTree, []) || [];
        },

        updateBreadcrumb(folderId: string | null) {
            if (folderId === null) {
                this.breadcrumbPath = [];
            } else {
                this.breadcrumbPath = this.findPathToFolder(folderId);
            }
        },

        selectItem(item: SelectableItem) {
            this.selectedItemId = this.getItemId(item);
        },

        confirmSelection() {
            this.$emit('update:modelValue', this.selectedItemId);
            this.dialog = false;
        },

        cancelSelection() {
            this.selectedItemId = this.modelValue || '';
            this.dialog = false;
        }
    }
});
</script>

<style scoped>
.selector-dialog-card {
    border-radius: 12px;
    overflow: hidden;
}

.dialog-title {
    font-size: 1.25rem;
    font-weight: 500;
}

.selector-layout {
    display: flex;
    height: 100%;
}

.folder-sidebar {
    width: 280px;
    border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    overflow-y: auto;
    flex-shrink: 0;
    background-color: transparent;
}

.sidebar-header {
    border-bottom: 1px solid rgba(var(--v-border-color), 0.5);
}

.items-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    background-color: rgb(var(--v-theme-surface));
}

.breadcrumb-bar {
    background-color: transparent;
    min-height: 56px;
    display: flex;
    align-items: center;
}

.items-list {
    flex: 1;
    overflow-y: auto;
}

.items-content {
    background-color: transparent;
}

.tree-list {
    padding: 0;
}

.section-label {
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-size: 0.7rem;
}

.breadcrumb-link {
    cursor: pointer;
    transition: color 0.2s;
}

.breadcrumb-link:hover {
    color: rgb(var(--v-theme-primary));
}

.root-item {
    margin-bottom: 4px;
}

.folder-item {
    transition: all 0.15s ease;
}

.folder-item:hover {
    background-color: rgba(var(--v-theme-primary), 0.06);
}

.persona-item {
    transition: all 0.15s ease;
    border: 1px solid transparent;
}

.persona-item:hover {
    background-color: rgba(var(--v-theme-primary), 0.04);
}

.persona-item.selected-item {
    background-color: rgba(var(--v-theme-primary), 0.08);
    border-color: rgba(var(--v-theme-primary), 0.3);
}

.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 200px;
}

.v-list-item {
    transition: all 0.15s ease;
}

.v-list-item:hover {
    background-color: rgba(var(--v-theme-primary), 0.04);
}

.v-list-item.v-list-item--active {
    background-color: rgba(var(--v-theme-primary), 0.08);
}

@media (max-width: 600px) {
    .selector-layout {
        flex-direction: column;
        height: auto;
        max-height: 500px;
    }

    .folder-sidebar {
        width: 100%;
        border-right: none;
        border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
        max-height: 150px;
    }

    .items-list {
        max-height: 300px;
    }
}
</style>
