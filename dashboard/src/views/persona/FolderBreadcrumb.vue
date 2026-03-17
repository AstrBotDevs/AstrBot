<template>
    <v-breadcrumbs :items="breadcrumbItems" class="folder-breadcrumb pa-0">
        <template v-slot:prepend>
            <v-icon size="small" class="mr-1">mdi-folder-outline</v-icon>
        </template>
        <template v-slot:item="{ item }">
            <v-breadcrumbs-item :disabled="item.disabled" @click="!item.disabled && handleClick((item as any).folderId)"
                :class="{ 'breadcrumb-link': !item.disabled }">
                <v-icon v-if="(item as any).isRoot" size="small" class="mr-1">mdi-home</v-icon>
                {{ item.title }}
            </v-breadcrumbs-item>
        </template>
        <template v-slot:divider>
            <v-icon size="small">mdi-chevron-right</v-icon>
        </template>
    </v-breadcrumbs>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { mapState, mapActions } from 'pinia';
import type { FolderTreeNode } from '@/components/folder/types';

interface BreadcrumbItem {
    title: string;
    folderId: string | null;
    disabled: boolean;
    isRoot: boolean;
}

export default defineComponent({
    name: 'FolderBreadcrumb',
    setup() {
        const { tm } = useModuleI18n('features/persona');
        return { tm };
    },
    computed: {
        ...mapState(usePersonaStore, ['breadcrumbPath', 'currentFolderId']),

        breadcrumbItems(): BreadcrumbItem[] {
            const items: BreadcrumbItem[] = [
                {
                    title: this.tm('folder.rootFolder'),
                    folderId: null,
                    disabled: this.currentFolderId === null,
                    isRoot: true
                }
            ];

            (this.breadcrumbPath as FolderTreeNode[]).forEach((folder, index) => {
                items.push({
                    title: folder.name,
                    folderId: folder.folder_id,
                    disabled: index === (this.breadcrumbPath as FolderTreeNode[]).length - 1,
                    isRoot: false
                });
            });

            return items;
        }
    },
    methods: {
        ...mapActions(usePersonaStore, ['navigateToFolder']),

        handleClick(folderId: string | null) {
            this.navigateToFolder(folderId);
        }
    }
});
</script>

<style scoped>
.folder-breadcrumb {
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
