<template>
    <div class="base-folder-tree-node">
        <v-list-item :active="currentFolderId === folder.folder_id" @click.stop="$emit('folder-click', folder.folder_id)"
            @contextmenu.prevent="handleContextMenu" rounded="lg" :style="{ paddingLeft: `${(depth + 1) * 16}px` }"
            :class="['folder-item', { 'drag-over': isDragOver }]"
            @dragover.prevent="handleDragOver" @dragleave="handleDragLeave" @drop.prevent="handleDrop">
            <template v-slot:prepend>
                <v-btn v-if="hasChildren" icon variant="text" size="x-small" @click.stop="toggleExpand"
                    class="expand-btn">
                    <v-icon size="16">{{ isExpanded ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
                </v-btn>
                <div v-else class="expand-placeholder"></div>
                <v-icon :color="currentFolderId === folder.folder_id ? 'primary' : ''">
                    {{ isExpanded ? 'mdi-folder-open' : 'mdi-folder' }}
                </v-icon>
            </template>
            <v-list-item-title class="text-truncate">{{ folder.name }}</v-list-item-title>
        </v-list-item>

        <!-- 子文件夹 -->
        <v-expand-transition>
            <div v-show="isExpanded && hasChildren">
                <BaseFolderTreeNode v-for="child in folder.children" :key="child.folder_id" :folder="child" :depth="depth + 1"
                    :current-folder-id="currentFolderId" :search-query="searchQuery"
                    :expanded-folder-ids="expandedFolderIds" :accept-drop-types="acceptDropTypes"
                    @folder-click="$emit('folder-click', $event)"
                    @folder-context-menu="$emit('folder-context-menu', $event)"
                    @item-dropped="$emit('item-dropped', $event)"
                    @toggle-expansion="$emit('toggle-expansion', $event)"
                    @set-expansion="$emit('set-expansion', $event)" />
            </div>
        </v-expand-transition>
    </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import type { FolderTreeNode } from './types';

export default defineComponent({
    name: 'BaseFolderTreeNode',
    props: {
        folder: {
            type: Object as PropType<FolderTreeNode>,
            required: true
        },
        depth: {
            type: Number,
            default: 0
        },
        currentFolderId: {
            type: String as PropType<string | null>,
            default: null
        },
        searchQuery: {
            type: String,
            default: ''
        },
        expandedFolderIds: {
            type: Array as PropType<string[]>,
            default: () => []
        },
        acceptDropTypes: {
            type: Array as PropType<string[]>,
            default: () => []
        }
    },
    emits: ['folder-click', 'folder-context-menu', 'item-dropped', 'toggle-expansion', 'set-expansion'],
    data() {
        return {
            isDragOver: false
        };
    },
    computed: {
        hasChildren(): boolean {
            return this.folder.children && this.folder.children.length > 0;
        },
        isExpanded(): boolean {
            return this.expandedFolderIds.includes(this.folder.folder_id);
        }
    },
    watch: {
        searchQuery: {
            immediate: true,
            handler(newQuery: string) {
                // 搜索时自动展开匹配的节点
                if (newQuery && this.hasChildren) {
                    this.$emit('set-expansion', { folderId: this.folder.folder_id, expanded: true });
                }
            }
        }
    },
    methods: {
        toggleExpand() {
            this.$emit('toggle-expansion', this.folder.folder_id);
        },
        handleContextMenu(event: MouseEvent) {
            this.$emit('folder-context-menu', { event, folder: this.folder });
        },
        handleDragOver(event: DragEvent) {
            if (!event.dataTransfer) return;
            event.dataTransfer.dropEffect = 'move';
            this.isDragOver = true;
        },
        handleDragLeave() {
            this.isDragOver = false;
        },
        handleDrop(event: DragEvent) {
            this.isDragOver = false;
            if (!event.dataTransfer) return;
            
            try {
                const data = JSON.parse(event.dataTransfer.getData('application/json'));
                if (this.acceptDropTypes.length === 0 || this.acceptDropTypes.includes(data.type)) {
                    this.$emit('item-dropped', {
                        item_id: data.id || data.persona_id || data.item_id,
                        item_type: data.type,
                        target_folder_id: this.folder.folder_id,
                        source_data: data
                    });
                }
            } catch (e) {
                console.error('Failed to parse drop data:', e);
            }
        }
    }
});
</script>

<style scoped>
.base-folder-tree-node {
    width: 100%;
}

.folder-item {
    min-height: 36px;
    transition: all 0.2s ease;
}

.folder-item.drag-over {
    background-color: rgba(var(--v-theme-primary), 0.15);
    border: 2px dashed rgb(var(--v-theme-primary));
    border-radius: 8px;
}

.expand-btn {
    margin-right: 4px;
}

.expand-placeholder {
    width: 28px;
    flex-shrink: 0;
}
</style>
