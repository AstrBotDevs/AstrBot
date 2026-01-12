<template>
    <v-breadcrumbs :items="breadcrumbItems" class="folder-breadcrumb pa-0">
        <template v-slot:prepend>
            <v-icon size="small" class="mr-1">mdi-folder-outline</v-icon>
        </template>
        <template v-slot:item="{ item }">
            <v-breadcrumbs-item :disabled="item.disabled" @click="!item.disabled && handleClick(item.folderId)"
                :class="{ 'breadcrumb-link': !item.disabled }">
                <v-icon v-if="item.isRoot" size="small" class="mr-1">mdi-home</v-icon>
                {{ item.title }}
            </v-breadcrumbs-item>
        </template>
        <template v-slot:divider>
            <v-icon size="small">mdi-chevron-right</v-icon>
        </template>
    </v-breadcrumbs>
</template>

<script>
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { mapState, mapActions } from 'pinia';

export default {
    name: 'FolderBreadcrumb',
    setup() {
        const { tm } = useModuleI18n('features/persona');
        return { tm };
    },
    computed: {
        ...mapState(usePersonaStore, ['breadcrumbPath', 'currentFolderId']),

        breadcrumbItems() {
            const items = [
                {
                    title: this.tm('folder.rootFolder'),
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
        ...mapActions(usePersonaStore, ['navigateToFolder']),

        handleClick(folderId) {
            this.navigateToFolder(folderId);
        }
    }
};
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
