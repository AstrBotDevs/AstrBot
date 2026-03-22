<template>
  <v-breadcrumbs
    :items="breadcrumbItems"
    class="folder-breadcrumb pa-0"
  >
    <template #prepend>
      <v-icon
        size="small"
        class="mr-1"
      >
        mdi-folder-outline
      </v-icon>
    </template>
    <template #item="{ item }">
      <v-breadcrumbs-item
        :disabled="item.disabled"
        :class="{ 'breadcrumb-link': !item.disabled }"
        @click="!item.disabled && handleClick((item as any).folderId)"
      >
        <v-icon
          v-if="(item as any).isRoot"
          size="small"
          class="mr-1"
        >
          mdi-home
        </v-icon>
        {{ item.title }}
      </v-breadcrumbs-item>
    </template>
    <template #divider>
      <v-icon size="small">
        mdi-chevron-right
      </v-icon>
    </template>
  </v-breadcrumbs>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { mapState, mapActions } from 'pinia';
import BaseFolderBreadcrumb from '@/components/folder/BaseFolderBreadcrumb.vue';
import type { FolderTreeNode } from '@/components/folder/types';

interface BreadcrumbItem {
    title: string;
    folderId: string | null;
    disabled: boolean;
    isRoot: boolean;
}

export default defineComponent({
    name: 'FolderBreadcrumb',
    components: { BaseFolderBreadcrumb },
    setup() {
        const { tm } = useModuleI18n('features/persona');
        return { tm };
    },
    computed: {
        ...mapState(usePersonaStore, ['breadcrumbPath', 'currentFolderId']),
        rootName(): string {
            return this.tm('folder.rootFolder');
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
