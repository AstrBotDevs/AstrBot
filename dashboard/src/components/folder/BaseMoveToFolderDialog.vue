<template>
    <v-dialog v-model="showDialog" max-width="500px" persistent>
        <v-card>
            <v-card-title>
                <v-icon class="mr-2">mdi-folder-move</v-icon>
                {{ labels.title }}
            </v-card-title>
            <v-card-text>
                <p class="text-body-2 text-medium-emphasis mb-4">
                    {{ labels.description }}
                </p>

                <!-- 文件夹选择树 -->
                <div class="folder-select-tree">
                    <v-list density="compact" nav class="tree-list">
                        <!-- 根目录选项 -->
                        <v-list-item :active="selectedFolderId === null" @click="selectFolder(null)" rounded="lg"
                            class="mb-1">
                            <template v-slot:prepend>
                                <v-icon>mdi-home</v-icon>
                            </template>
                            <v-list-item-title>{{ labels.rootFolder }}</v-list-item-title>
                        </v-list-item>

                        <!-- 文件夹树 -->
                        <template v-if="!treeLoading">
                            <BaseMoveTargetNode v-for="folder in folderTree" :key="folder.folder_id" :folder="folder"
                                :depth="0" :selected-folder-id="selectedFolderId" :disabled-folder-ids="disabledFolderIds"
                                @select="selectFolder" />
                        </template>

                        <!-- 加载状态 -->
                        <div v-if="treeLoading" class="text-center pa-4">
                            <v-progress-circular indeterminate size="24" />
                        </div>
                    </v-list>
                </div>
            </v-card-text>
            <v-card-actions>
                <v-spacer />
                <v-btn variant="text" @click="closeDialog">
                    {{ labels.cancelButton }}
                </v-btn>
                <v-btn color="primary" variant="flat" @click="submitMove" :loading="loading">
                    {{ labels.moveButton }}
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import type { FolderTreeNode } from './types';
import BaseMoveTargetNode from './BaseMoveTargetNode.vue';
import { collectFolderAndChildrenIds } from './useFolderManager';

interface DefaultLabels {
    title: string;
    description: string;
    rootFolder: string;
    cancelButton: string;
    moveButton: string;
}

const defaultLabels: DefaultLabels = {
    title: '移动到文件夹',
    description: '选择目标文件夹',
    rootFolder: '根目录',
    cancelButton: '取消',
    moveButton: '移动'
};

export default defineComponent({
    name: 'BaseMoveToFolderDialog',
    components: {
        BaseMoveTargetNode
    },
    props: {
        modelValue: {
            type: Boolean,
            default: false
        },
        folderTree: {
            type: Array as PropType<FolderTreeNode[]>,
            required: true
        },
        treeLoading: {
            type: Boolean,
            default: false
        },
        // 当移动的是文件夹时，需要传入当前文件夹 ID 以禁用自身和子文件夹
        currentFolderId: {
            type: String as PropType<string | null>,
            default: null
        },
        // 项目当前所在的文件夹 ID（用于初始化选择）
        itemCurrentFolderId: {
            type: String as PropType<string | null>,
            default: null
        },
        // 是否是移动文件夹（如果是，需要禁用自身和子文件夹）
        isMovingFolder: {
            type: Boolean,
            default: false
        },
        labels: {
            type: Object as PropType<Partial<DefaultLabels>>,
            default: () => ({})
        }
    },
    emits: ['update:modelValue', 'move'],
    data() {
        return {
            selectedFolderId: null as string | null,
            loading: false
        };
    },
    computed: {
        showDialog: {
            get(): boolean {
                return this.modelValue;
            },
            set(value: boolean) {
                this.$emit('update:modelValue', value);
            }
        },
        mergedLabels(): DefaultLabels {
            return { ...defaultLabels, ...this.labels };
        },
        // 禁用的文件夹 ID（不能移动到自己或子文件夹）
        disabledFolderIds(): string[] {
            if (!this.isMovingFolder || !this.currentFolderId) return [];
            return collectFolderAndChildrenIds(this.folderTree, this.currentFolderId);
        }
    },
    watch: {
        modelValue(newValue: boolean) {
            if (newValue) {
                // 初始化选中为当前所在文件夹
                this.selectedFolderId = this.itemCurrentFolderId;
            }
        }
    },
    methods: {
        selectFolder(folderId: string | null) {
            // 检查是否禁用
            if (folderId && this.disabledFolderIds.includes(folderId)) return;
            this.selectedFolderId = folderId;
        },

        closeDialog() {
            this.showDialog = false;
        },

        submitMove() {
            this.$emit('move', this.selectedFolderId);
        },

        setLoading(value: boolean) {
            this.loading = value;
        }
    }
});
</script>

<style scoped>
.folder-select-tree {
    max-height: 400px;
    overflow-y: auto;
    border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    border-radius: 8px;
}

.tree-list {
    padding: 8px;
}
</style>
