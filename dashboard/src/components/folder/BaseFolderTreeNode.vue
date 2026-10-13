<template>
  <div class="base-folder-tree-node">
    <div
      @click.stop="$emit('folder-click', folder.folder_id)"
      @contextmenu.prevent="handleContextMenu"
      :style="{ paddingLeft: `${depth * 14 + 4}px` }"
      :class="[
        'folder-item',
        {
          'folder-item--active': currentFolderId === folder.folder_id,
          'drag-over': isDragOver,
        },
      ]"
      @dragover.prevent="handleDragOver"
      @dragleave="handleDragLeave"
      @drop.prevent="handleDrop"
    >
      <button
        v-if="hasChildren"
        type="button"
        class="expand-btn"
        @click.stop="toggleExpand"
      >
        <v-icon size="14">{{
          isExpanded ? "mdi-chevron-down" : "mdi-chevron-right"
        }}</v-icon>
      </button>
      <span v-else class="expand-placeholder"></span>
      <v-icon size="17" class="folder-icon">
        {{ isExpanded ? "mdi-folder-open-outline" : "mdi-folder-outline" }}
      </v-icon>
      <span class="folder-name text-truncate">{{ folder.name }}</span>
    </div>

    <!-- 子文件夹 -->
    <v-expand-transition>
      <div v-show="isExpanded && hasChildren" class="child-nodes">
        <BaseFolderTreeNode
          v-for="child in folder.children"
          :key="child.folder_id"
          :folder="child"
          :depth="depth + 1"
          :current-folder-id="currentFolderId"
          :search-query="searchQuery"
          :expanded-folder-ids="expandedFolderIds"
          :accept-drop-types="acceptDropTypes"
          @folder-click="$emit('folder-click', $event)"
          @folder-context-menu="$emit('folder-context-menu', $event)"
          @item-dropped="$emit('item-dropped', $event)"
          @toggle-expansion="$emit('toggle-expansion', $event)"
          @set-expansion="$emit('set-expansion', $event)"
        />
      </div>
    </v-expand-transition>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from "vue";
import type { FolderTreeNode } from "./types";

export default defineComponent({
  name: "BaseFolderTreeNode",
  props: {
    folder: {
      type: Object as PropType<FolderTreeNode>,
      required: true,
    },
    depth: {
      type: Number,
      default: 0,
    },
    currentFolderId: {
      type: String as PropType<string | null>,
      default: null,
    },
    searchQuery: {
      type: String,
      default: "",
    },
    expandedFolderIds: {
      type: Array as PropType<string[]>,
      default: () => [],
    },
    acceptDropTypes: {
      type: Array as PropType<string[]>,
      default: () => [],
    },
  },
  emits: [
    "folder-click",
    "folder-context-menu",
    "item-dropped",
    "toggle-expansion",
    "set-expansion",
  ],
  data() {
    return {
      isDragOver: false,
    };
  },
  computed: {
    hasChildren(): boolean {
      return this.folder.children && this.folder.children.length > 0;
    },
    isExpanded(): boolean {
      return this.expandedFolderIds.includes(this.folder.folder_id);
    },
  },
  watch: {
    searchQuery: {
      immediate: true,
      handler(newQuery: string) {
        // 搜索时自动展开匹配的节点
        if (newQuery && this.hasChildren) {
          this.$emit("set-expansion", {
            folderId: this.folder.folder_id,
            expanded: true,
          });
        }
      },
    },
  },
  methods: {
    toggleExpand() {
      this.$emit("toggle-expansion", this.folder.folder_id);
    },
    handleContextMenu(event: MouseEvent) {
      this.$emit("folder-context-menu", { event, folder: this.folder });
    },
    handleDragOver(event: DragEvent) {
      if (!event.dataTransfer) return;
      event.dataTransfer.dropEffect = "move";
      this.isDragOver = true;
    },
    handleDragLeave() {
      this.isDragOver = false;
    },
    handleDrop(event: DragEvent) {
      this.isDragOver = false;
      if (!event.dataTransfer) return;

      try {
        const data = JSON.parse(event.dataTransfer.getData("application/json"));
        if (
          this.acceptDropTypes.length === 0 ||
          this.acceptDropTypes.includes(data.type)
        ) {
          this.$emit("item-dropped", {
            item_id: data.id || data.persona_id || data.item_id,
            item_type: data.type,
            target_folder_id: this.folder.folder_id,
            source_data: data,
          });
        }
      } catch (e) {
        console.error("Failed to parse drop data:", e);
      }
    },
  },
});
</script>

<style scoped>
.base-folder-tree-node {
  width: 100%;
}

.child-nodes {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 4px;
}

.folder-item {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 32px;
  padding-right: 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: none;
}

.folder-item:hover,
.folder-item--active {
  background: rgba(var(--v-theme-on-surface), 0.045);
}

.folder-item.drag-over {
  background-color: rgba(var(--v-theme-on-surface), 0.09);
  outline: 1px dashed rgba(var(--v-theme-on-surface), 0.4);
}

.expand-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.expand-placeholder {
  width: 22px;
  flex-shrink: 0;
}

.folder-icon {
  margin-right: 8px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}

.folder-name {
  min-width: 0;
  flex: 1;
}
</style>
