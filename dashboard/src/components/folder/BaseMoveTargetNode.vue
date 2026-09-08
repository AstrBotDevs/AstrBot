<template>
  <div class="base-move-target-node">
    <button
      type="button"
      class="folder-tree-row"
      :class="{
        'folder-tree-row--active': selectedFolderId === folder.folder_id,
      }"
      :disabled="isDisabled"
      :style="{ paddingLeft: `${8 + depth * 18}px` }"
      @click.stop="!isDisabled && $emit('select', folder.folder_id)"
    >
      <span class="folder-tree-chevron" @click="handleChevronClick">
        <v-icon v-if="hasChildren" size="16">
          {{ isExpanded ? "mdi-chevron-down" : "mdi-chevron-right" }}
        </v-icon>
      </span>
      <v-icon size="17" class="folder-tree-icon">
        {{
          isExpanded && hasChildren
            ? "mdi-folder-open-outline"
            : "mdi-folder-outline"
        }}
      </v-icon>
      <span class="folder-tree-name">{{ folder.name }}</span>
    </button>

    <!-- 子文件夹 -->
    <div v-show="isExpanded && hasChildren">
      <BaseMoveTargetNode
        v-for="child in folder.children"
        :key="child.folder_id"
        :folder="child"
        :depth="depth + 1"
        :selected-folder-id="selectedFolderId"
        :disabled-folder-ids="disabledFolderIds"
        @select="$emit('select', $event)"
      />
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from "vue";
import type { FolderTreeNode } from "./types";

export default defineComponent({
  name: "BaseMoveTargetNode",
  props: {
    folder: {
      type: Object as PropType<FolderTreeNode>,
      required: true,
    },
    depth: {
      type: Number,
      default: 0,
    },
    selectedFolderId: {
      type: String as PropType<string | null>,
      default: null,
    },
    disabledFolderIds: {
      type: Array as PropType<string[]>,
      default: () => [],
    },
  },
  emits: ["select"],
  data() {
    return {
      isExpanded: true,
    };
  },
  computed: {
    hasChildren(): boolean {
      return this.folder.children && this.folder.children.length > 0;
    },
    isDisabled(): boolean {
      return this.disabledFolderIds.includes(this.folder.folder_id);
    },
  },
  methods: {
    handleChevronClick(event: MouseEvent) {
      if (!this.hasChildren) return;
      event.stopPropagation();
      this.toggleExpand();
    },
    toggleExpand() {
      this.isExpanded = !this.isExpanded;
    },
  },
});
</script>

<style scoped>
.base-move-target-node {
  width: 100%;
}

.folder-tree-row {
  display: flex;
  align-items: center;
  width: 100%;
  height: 30px;
  padding-right: 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  gap: 6px;
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.folder-tree-row:hover,
.folder-tree-row--active {
  background: rgba(var(--v-theme-on-surface), 0.07);
}

.folder-tree-row:disabled {
  cursor: default;
  opacity: 0.4;
}

.folder-tree-chevron {
  display: grid;
  place-items: center;
  width: 16px;
  height: 18px;
  flex: 0 0 16px;
  color: rgba(var(--v-theme-on-surface), 0.58);
}

.folder-tree-icon {
  flex: 0 0 auto;
  color: rgba(var(--v-theme-on-surface), 0.58);
}

.folder-tree-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
