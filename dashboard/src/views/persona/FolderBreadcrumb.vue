<template>
  <BaseFolderBreadcrumb
    :breadcrumb-path="breadcrumbPath"
    :current-folder-id="currentFolderId"
    :root-folder-name="rootName"
    :labels="{ rootFolder: tm('folder.rootFolder') }"
    class="folder-breadcrumb pa-0"
    @navigate="handleClick"
  />
</template>

<script lang="ts">
import { defineComponent } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { usePersonaStore } from "@/stores/personaStore";
import { mapState, mapActions } from "pinia";
import BaseFolderBreadcrumb from "@/components/folder/BaseFolderBreadcrumb.vue";
import type { FolderTreeNode } from "@/components/folder/types";

interface BreadcrumbItem {
  title: string;
  folderId: string | null;
  disabled: boolean;
  isRoot: boolean;
}

export default defineComponent({
  name: "FolderBreadcrumb",
  components: { BaseFolderBreadcrumb },
  setup() {
    const { tm } = useModuleI18n("features/persona");
    return { tm };
  },
  computed: {
    ...mapState(usePersonaStore, ["breadcrumbPath", "currentFolderId"]),
    rootName(): string {
      return this.tm("folder.rootFolder");
    },
  },
  methods: {
    ...mapActions(usePersonaStore, ["navigateToFolder"]),

    handleClick(folderId: string | null) {
      this.navigateToFolder(folderId);
    },
  },
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
