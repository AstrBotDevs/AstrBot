<template>
    <BaseFolderTreeNode :folder="folder" :depth="depth" :current-folder-id="currentFolderId"
        :search-query="searchQuery" :expanded-folder-ids="expandedFolderIds" :accept-drop-types="['persona']"
        @folder-click="$emit('folder-click', $event)"
        @folder-context-menu="handleContextMenu"
        @item-dropped="handleItemDropped"
        @toggle-expansion="toggleFolderExpansion"
        @set-expansion="handleSetExpansion" />
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import { usePersonaStore } from '@/stores/personaStore';
import { mapState, mapActions } from 'pinia';
import BaseFolderTreeNode from '@/components/folder/BaseFolderTreeNode.vue';
import type { FolderTreeNode as FolderTreeNodeType } from '@/components/folder/types';

export default defineComponent({
    name: 'FolderTreeNode',
    components: {
        BaseFolderTreeNode
    },
    props: {
        folder: {
            type: Object as PropType<FolderTreeNodeType>,
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
        }
    },
    emits: ['folder-click', 'folder-context-menu', 'persona-dropped'],
    computed: {
        ...mapState(usePersonaStore, ['expandedFolderIds'])
    },
    methods: {
        ...mapActions(usePersonaStore, ['toggleFolderExpansion', 'setFolderExpansion']),

        handleContextMenu(event: { event: MouseEvent; folder: FolderTreeNodeType }) {
            this.$emit('folder-context-menu', event);
        },

        handleItemDropped(data: { item_id: string; item_type: string; target_folder_id: string | null; source_data: any }) {
            if (data.item_type === 'persona') {
                this.$emit('persona-dropped', {
                    persona_id: data.item_id,
                    target_folder_id: data.target_folder_id
                });
            }
        },

        handleSetExpansion(data: { folderId: string; expanded: boolean }) {
            this.setFolderExpansion(data.folderId, data.expanded);
        }
    }
});
</script>
