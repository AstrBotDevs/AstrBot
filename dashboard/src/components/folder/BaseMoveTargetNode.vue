<template>
    <div class="base-move-target-node">
        <v-list-item :active="selectedFolderId === folder.folder_id" :disabled="isDisabled"
            @click.stop="!isDisabled && $emit('select', folder.folder_id)" rounded="lg"
            :style="{ paddingLeft: `${(depth + 1) * 16}px` }" class="folder-item">
            <template v-slot:prepend>
                <v-btn v-if="hasChildren" icon variant="text" size="x-small" @click.stop="toggleExpand"
                    class="expand-btn" :disabled="isDisabled">
                    <v-icon size="16">{{ isExpanded ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
                </v-btn>
                <div v-else class="expand-placeholder"></div>
                <v-icon :color="isDisabled ? 'grey' : (selectedFolderId === folder.folder_id ? 'primary' : '')">
                    {{ isExpanded ? 'mdi-folder-open' : 'mdi-folder' }}
                </v-icon>
            </template>
            <v-list-item-title class="text-truncate">{{ folder.name }}</v-list-item-title>
        </v-list-item>

        <!-- 子文件夹 -->
        <v-expand-transition>
            <div v-show="isExpanded && hasChildren">
                <BaseMoveTargetNode v-for="child in folder.children" :key="child.folder_id" :folder="child" :depth="depth + 1"
                    :selected-folder-id="selectedFolderId" :disabled-folder-ids="disabledFolderIds"
                    @select="$emit('select', $event)" />
            </div>
        </v-expand-transition>
    </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import type { FolderTreeNode } from './types';

export default defineComponent({
    name: 'BaseMoveTargetNode',
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
    emits: ['select'],
    data() {
        return {
            isExpanded: true
        };
    },
    computed: {
        hasChildren(): boolean {
            return this.folder.children && this.folder.children.length > 0;
        },
        isDisabled(): boolean {
            return this.disabledFolderIds.includes(this.folder.folder_id);
        }
    },
    methods: {
        toggleExpand() {
            this.isExpanded = !this.isExpanded;
        }
    }
});
</script>

<style scoped>
.base-move-target-node {
    width: 100%;
}

.folder-item {
    min-height: 36px;
}

.expand-btn {
    margin-right: 4px;
}

.expand-placeholder {
    width: 28px;
    flex-shrink: 0;
}
</style>
