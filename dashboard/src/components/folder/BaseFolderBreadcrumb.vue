<template>
    <v-breadcrumbs :items="computedItems" class="base-folder-breadcrumb pa-0">
        <template v-slot:prepend>
            <v-icon size="small" class="mr-1">mdi-folder-outline</v-icon>
        </template>
        <template v-slot:item="{ item }">
            <v-breadcrumbs-item :disabled="(item as any).disabled" @click="!(item as any).disabled && handleClick((item as any).folderId)"
                :class="{ 'breadcrumb-link': !(item as any).disabled }">
                <v-icon v-if="(item as any).isRoot" size="small" class="mr-1">mdi-home</v-icon>
                {{ (item as any).title }}
            </v-breadcrumbs-item>
        </template>
        <template v-slot:divider>
            <v-icon size="small">mdi-chevron-right</v-icon>
        </template>
    </v-breadcrumbs>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import type { BreadcrumbItem, FolderTreeNode } from './types';

export default defineComponent({
    name: 'BaseFolderBreadcrumb',
    props: {
        breadcrumbPath: {
            type: Array as PropType<FolderTreeNode[]>,
            required: true
        },
        currentFolderId: {
            type: String as PropType<string | null>,
            default: null
        },
        rootFolderName: {
            type: String,
            default: '根目录'
        }
    },
    emits: ['navigate'],
    computed: {
        computedItems(): BreadcrumbItem[] {
            const items: BreadcrumbItem[] = [
                {
                    title: this.rootFolderName,
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
        handleClick(folderId: string | null) {
            this.$emit('navigate', folderId);
        }
    }
});
</script>

<style scoped>
.base-folder-breadcrumb {
    font-size: 14px;
}

.breadcrumb-link {
    cursor: pointer;
    transition: color 0.2s;
}

.breadcrumb-link:hover {
    color: rgb(var(--v-theme-primary));
}
</style>
