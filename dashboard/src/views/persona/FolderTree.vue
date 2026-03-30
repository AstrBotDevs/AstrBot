<template>
  <div class="folder-tree">
    <BaseFolderTree
      :folder-tree="folderTree"
      :current-folder-id="currentFolderId"
      :expanded-folder-ids="expandedFolderIds"
      :tree-loading="treeLoading"
      :accept-drop-types="['persona']"
      :labels="{
        searchPlaceholder: tm('folder.searchPlaceholder'),
        rootFolder: tm('folder.rootFolder'),
        noFolders: tm('folder.noFolders'),
        contextMenu: {
          open: tm('folder.contextMenu.open'),
          rename: tm('folder.contextMenu.rename'),
          moveTo: tm('folder.contextMenu.moveTo'),
          delete: tm('folder.contextMenu.delete'),
        },
      }"
      @folder-click="handleFolderClick"
      @rename-folder="onRenameFolder"
      @move-folder="$emit('move-folder', $event)"
      @delete-folder="onDeleteFolder"
      @item-dropped="onItemDropped"
      @toggle-expansion="toggleFolderExpansion"
      @set-expansion="setFolderExpansion"
    />

    <!-- 重命名对话框 -->
    <v-dialog v-model="renameDialog.show" max-width="400px" persistent>
      <v-card>
        <v-card-title>{{ tm("folder.renameDialog.title") }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="renameDialog.name"
            :label="tm('folder.form.name')"
            :rules="[(v) => !!v || tm('folder.validation.nameRequired')]"
            variant="outlined"
            density="comfortable"
            autofocus
            @keyup.enter="submitRename"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="renameDialog.show = false">
            {{ tm("buttons.cancel") }}
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="renameDialog.loading"
            :disabled="!renameDialog.name"
            @click="submitRename"
          >
            {{ tm("buttons.save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="deleteDialog.show" max-width="450px">
      <v-card>
        <v-card-title class="text-error">
          <v-icon class="mr-2" color="error"> mdi-alert </v-icon>
          {{ tm("folder.deleteDialog.title") }}
        </v-card-title>
        <v-card-text>
          <p>
            {{
              tm("folder.deleteDialog.message", {
                name: deleteDialog.folder?.name ?? "",
              })
            }}
          </p>
          <p class="text-warning mt-2">
            <v-icon size="small" class="mr-1"> mdi-information </v-icon>
            {{ tm("folder.deleteDialog.warning") }}
          </p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog.show = false">
            {{ tm("buttons.cancel") }}
          </v-btn>
          <v-btn
            color="error"
            variant="flat"
            :loading="deleteDialog.loading"
            @click="submitDelete"
          >
            {{ tm("buttons.delete") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script lang="ts">
import { defineComponent } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { usePersonaStore } from "@/stores/personaStore";
import { mapState, mapActions } from "pinia";
import BaseFolderTree from "@/components/folder/BaseFolderTree.vue";
import type { FolderTreeNode as FolderTreeNodeType } from "@/components/folder/types";

interface ContextMenuState {
  show: boolean;
  target: [number, number] | null;
  folder: FolderTreeNodeType | null;
}

interface RenameDialogState {
  show: boolean;
  folder: FolderTreeNodeType | null;
  name: string;
  loading: boolean;
}

interface DeleteDialogState {
  show: boolean;
  folder: FolderTreeNodeType | null;
  loading: boolean;
}

export default defineComponent({
  name: "FolderTree",
  components: {
    BaseFolderTree,
  },
  emits: ["move-folder", "error", "success", "persona-dropped"],
  setup() {
    const { tm } = useModuleI18n("features/persona");
    return { tm };
  },
  data() {
    return {
      searchQuery: "",
      isRootDragOver: false,
      contextMenu: {
        show: false,
        target: null,
        folder: null,
      } as ContextMenuState,
      renameDialog: {
        show: false,
        folder: null,
        name: "",
        loading: false,
      } as RenameDialogState,
      deleteDialog: {
        show: false,
        folder: null,
        loading: false,
      } as DeleteDialogState,
    };
  },
  computed: {
    ...mapState(usePersonaStore, [
      "folderTree",
      "currentFolderId",
      "treeLoading",
      "expandedFolderIds",
    ]),

    filteredFolderTree(): FolderTreeNodeType[] {
      if (!this.searchQuery) {
        return this.folderTree as FolderTreeNodeType[];
      }
      const query = this.searchQuery.toLowerCase();
      return this.filterTreeBySearch(
        this.folderTree as FolderTreeNodeType[],
        query,
      );
    },
  },
  methods: {
    ...mapActions(usePersonaStore, [
      "navigateToFolder",
      "updateFolder",
      "deleteFolder",
      "toggleFolderExpansion",
      "setFolderExpansion",
    ]),
    filterTreeBySearch(
      nodes: FolderTreeNodeType[],
      query: string,
    ): FolderTreeNodeType[] {
      return nodes
        .filter((node) => {
          const matches = node.name.toLowerCase().includes(query);
          const childMatches = this.filterTreeBySearch(
            node.children || [],
            query,
          );
          return matches || childMatches.length > 0;
        })
        .map((node) => ({
          ...node,
          children: this.filterTreeBySearch(node.children || [], query),
        }));
    },

    handleFolderClick(folderId: string | null) {
      this.navigateToFolder(folderId);
    },

    // rename event from BaseFolderTree
    onRenameFolder(folder: FolderTreeNodeType) {
      this.renameDialog.folder = folder;
      this.renameDialog.name = folder.name;
      this.renameDialog.show = true;
    },

    // delete event from BaseFolderTree
    onDeleteFolder(folder: FolderTreeNodeType) {
      this.deleteDialog.folder = folder;
      this.deleteDialog.show = true;
    },

    onItemDropped(data: {
      item_id: string;
      item_type: string;
      target_folder_id: string | null;
      source_data?: any;
    }) {
      if (data.item_type === "persona") {
        this.$emit("persona-dropped", {
          persona_id: data.item_id,
          target_folder_id: data.target_folder_id,
        });
      }
    },

    async submitRename() {
      if (!this.renameDialog.name || !this.renameDialog.folder) return;

      this.renameDialog.loading = true;
      try {
        await this.updateFolder({
          folder_id: this.renameDialog.folder.folder_id,
          name: this.renameDialog.name,
        });
        this.$emit("success", this.tm("folder.messages.renameSuccess"));
        this.renameDialog.show = false;
      } catch (error: any) {
        this.$emit(
          "error",
          error.message || this.tm("folder.messages.renameError"),
        );
      } finally {
        this.renameDialog.loading = false;
      }
    },

    async submitDelete() {
      if (!this.deleteDialog.folder) return;

      this.deleteDialog.loading = true;
      try {
        await this.deleteFolder(this.deleteDialog.folder.folder_id);
        this.$emit("success", this.tm("folder.messages.deleteSuccess"));
        this.deleteDialog.show = false;
      } catch (error: any) {
        this.$emit(
          "error",
          error.message || this.tm("folder.messages.deleteError"),
        );
      } finally {
        this.deleteDialog.loading = false;
      }
    },
  },
});
</script>

<style scoped>
.folder-tree {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.tree-list {
  flex: 1;
  overflow-y: auto;
}

.root-item {
  margin-bottom: 4px;
  transition: all 0.2s ease;
}

.root-item.drag-over {
  background-color: rgba(var(--v-theme-primary), 0.15);
  border: 2px dashed rgb(var(--v-theme-primary));
  border-radius: 8px;
}
</style>
