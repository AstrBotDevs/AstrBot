<template>
    <div class="folder-tree-node">
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
                <FolderTreeNode v-for="child in folder.children" :key="child.folder_id" :folder="child" :depth="depth + 1"
                    :current-folder-id="currentFolderId" :search-query="searchQuery"
                    @folder-click="$emit('folder-click', $event)"
                    @folder-context-menu="$emit('folder-context-menu', $event.event, $event.folder)"
                    @persona-dropped="$emit('persona-dropped', $event)" />
            </div>
        </v-expand-transition>
    </div>
</template>

<script>
import { usePersonaStore } from '@/stores/personaStore';
import { mapState, mapActions } from 'pinia';

export default {
    name: 'FolderTreeNode',
    props: {
        folder: {
            type: Object,
            required: true
        },
        depth: {
            type: Number,
            default: 0
        },
        currentFolderId: {
            type: String,
            default: null
        },
        searchQuery: {
            type: String,
            default: ''
        }
    },
    emits: ['folder-click', 'folder-context-menu', 'persona-dropped'],
    data() {
        return {
            isDragOver: false
        };
    },
    computed: {
        ...mapState(usePersonaStore, ['expandedFolderIds']),
        hasChildren() {
            return this.folder.children && this.folder.children.length > 0;
        },
        isExpanded() {
            return this.expandedFolderIds.includes(this.folder.folder_id);
        }
    },
    watch: {
        searchQuery: {
            immediate: true,
            handler(newQuery) {
                // 搜索时自动展开匹配的节点
                if (newQuery && this.hasChildren) {
                    this.setFolderExpansion(this.folder.folder_id, true);
                }
            }
        }
    },
    methods: {
        ...mapActions(usePersonaStore, ['toggleFolderExpansion', 'setFolderExpansion']),
        toggleExpand() {
            this.toggleFolderExpansion(this.folder.folder_id);
        },
        handleContextMenu(event) {
            this.$emit('folder-context-menu', { event, folder: this.folder });
        },
        handleDragOver(event) {
            event.dataTransfer.dropEffect = 'move';
            this.isDragOver = true;
        },
        handleDragLeave() {
            this.isDragOver = false;
        },
        handleDrop(event) {
            this.isDragOver = false;
            try {
                const data = JSON.parse(event.dataTransfer.getData('application/json'));
                if (data.type === 'persona') {
                    this.$emit('persona-dropped', {
                        persona_id: data.persona_id,
                        target_folder_id: this.folder.folder_id
                    });
                }
            } catch (e) {
                console.error('Failed to parse drop data:', e);
            }
        }
    }
};
</script>

<style scoped>
.folder-tree-node {
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
