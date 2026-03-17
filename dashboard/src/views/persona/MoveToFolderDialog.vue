<template>
    <v-dialog v-model="showDialog" max-width="500px" persistent>
        <v-card>
            <v-card-title>
                <v-icon class="mr-2">mdi-folder-move</v-icon>
                {{ tm('moveDialog.title') }}
            </v-card-title>
            <v-card-text>
                <p class="text-body-2 text-medium-emphasis mb-4">
                    {{ tm('moveDialog.description', { name: itemName }) }}
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
                            <v-list-item-title>{{ tm('folder.rootFolder') }}</v-list-item-title>
                        </v-list-item>

                        <!-- 文件夹树 -->
                        <template v-if="!treeLoading">
                            <MoveTargetNode v-for="folder in availableFolders" :key="folder.folder_id" :folder="folder"
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
                    {{ tm('buttons.cancel') }}
                </v-btn>
                <v-btn color="primary" variant="flat" @click="submitMove" :loading="loading">
                    {{ tm('buttons.move') }}
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { mapState, mapActions } from 'pinia';
import MoveTargetNode from './MoveTargetNode.vue';
import { collectFolderAndChildrenIds } from '@/components/folder/useFolderManager';
import type { FolderTreeNode } from '@/components/folder/types';

interface PersonaItem {
    persona_id: string;
    folder_id?: string | null;
    [key: string]: any;
}

interface FolderItem {
    folder_id: string;
    name: string;
    parent_id?: string | null;
    [key: string]: any;
}

export default defineComponent({
    name: 'MoveToFolderDialog',
    components: {
        MoveTargetNode
    },
    props: {
        modelValue: {
            type: Boolean,
            default: false
        },
        itemType: {
            type: String as PropType<'persona' | 'folder'>,
            required: true
        },
        item: {
            type: Object as PropType<PersonaItem | FolderItem | null>,
            default: null
        }
    },
    emits: ['update:modelValue', 'moved', 'error'],
    setup() {
        const { tm } = useModuleI18n('features/persona');
        return { tm };
    },
    data() {
        return {
            selectedFolderId: null as string | null,
            loading: false
        };
    },
    computed: {
        ...mapState(usePersonaStore, ['folderTree', 'treeLoading']),

        showDialog: {
            get(): boolean {
                return this.modelValue;
            },
            set(value: boolean) {
                this.$emit('update:modelValue', value);
            }
        },

        itemName(): string {
            if (!this.item) return '';
            return this.itemType === 'persona' 
                ? (this.item as PersonaItem).persona_id 
                : (this.item as FolderItem).name;
        },

        // 禁用的文件夹 ID（不能移动到自己或子文件夹）
        disabledFolderIds(): string[] {
            if (this.itemType !== 'folder' || !this.item) return [];
            return collectFolderAndChildrenIds(
                this.folderTree as FolderTreeNode[], 
                (this.item as FolderItem).folder_id
            );
        },

        // 过滤掉禁用的文件夹
        availableFolders(): FolderTreeNode[] {
            return this.folderTree as FolderTreeNode[];
        }
    },
    watch: {
        modelValue(newValue: boolean) {
            if (newValue) {
                // 初始化选中为当前所在文件夹
                if (this.item) {
                    this.selectedFolderId = this.itemType === 'persona' 
                        ? (this.item as PersonaItem).folder_id ?? null
                        : (this.item as FolderItem).parent_id ?? null;
                }
            }
        }
    },
    methods: {
        ...mapActions(usePersonaStore, ['movePersonaToFolder', 'moveFolderToFolder']),

        selectFolder(folderId: string | null) {
            // 检查是否禁用
            if (folderId && this.disabledFolderIds.includes(folderId)) return;
            this.selectedFolderId = folderId;
        },

        closeDialog() {
            this.showDialog = false;
        },

        async submitMove() {
            if (!this.item) return;

            this.loading = true;
            try {
                if (this.itemType === 'persona') {
                    await this.movePersonaToFolder(
                        (this.item as PersonaItem).persona_id, 
                        this.selectedFolderId
                    );
                } else {
                    await this.moveFolderToFolder(
                        (this.item as FolderItem).folder_id, 
                        this.selectedFolderId
                    );
                }
                this.$emit('moved', this.tm('moveDialog.success'));
                this.closeDialog();
            } catch (error: any) {
                this.$emit('error', error.message || this.tm('moveDialog.error'));
            } finally {
                this.loading = false;
            }
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
