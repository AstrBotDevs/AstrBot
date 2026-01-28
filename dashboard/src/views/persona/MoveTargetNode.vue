<template>
    <BaseMoveTargetNode :folder="folder" :depth="depth" :selected-folder-id="selectedFolderId"
        :disabled-folder-ids="disabledFolderIds" @select="$emit('select', $event)" />
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import BaseMoveTargetNode from '@/components/folder/BaseMoveTargetNode.vue';
import type { FolderTreeNode } from '@/components/folder/types';

export default defineComponent({
    name: 'MoveTargetNode',
    components: {
        BaseMoveTargetNode
    },
    props: {
        folder: {
            type: Object as PropType<FolderTreeNode>,
            required: true
        },
        depth: {
            type: Number,
            default: 0
        },
        selectedFolderId: {
            type: String as PropType<string | null>,
            default: null
        },
        disabledFolderIds: {
            type: Array as PropType<string[]>,
            default: () => []
        }
    },
    emits: ['select']
});
</script>
