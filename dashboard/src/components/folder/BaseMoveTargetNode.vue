<template>
  <div class="base-move-target-node">
    <v-list-item
      :active="selectedFolderId === folder.folder_id"
      :disabled="isDisabled"
      rounded="md"
      :style="{ paddingLeft: `${(depth + 1) * 16}px` }"
      class="folder-item"
      @click.stop="!isDisabled && emit('select', folder.folder_id)"
    >
      <template #prepend>
        <v-btn
          v-if="hasChildren"
          icon
          variant="text"
          size="x-small"
          class="expand-btn"
          :disabled="isDisabled"
          @click.stop="toggleExpand"
        >
          <v-icon size="16">{{
            isExpanded ? 'mdi-chevron-down' : 'mdi-chevron-right'
          }}</v-icon>
        </v-btn>
        <div v-else class="expand-placeholder"></div>
        <v-icon
          :color="
            isDisabled
              ? 'grey'
              : selectedFolderId === folder.folder_id
                ? 'primary'
                : ''
          "
        >
          {{ isExpanded ? 'mdi-folder-open' : 'mdi-folder' }}
        </v-icon>
      </template>
      <v-list-item-title class="text-truncate">{{
        folder.name
      }}</v-list-item-title>
    </v-list-item>

    <!-- 子文件夹 -->
    <v-expand-transition>
      <div v-show="isExpanded && hasChildren">
        <BaseMoveTargetNode
          v-for="child in folder.children"
          :key="child.folder_id"
          :folder="child"
          :depth="depth + 1"
          :selected-folder-id="selectedFolderId"
          :disabled-folder-ids="disabledFolderIds"
          @select="emit('select', $event)"
        />
      </div>
    </v-expand-transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { FolderTreeNode } from './types';

const props = withDefaults(
  defineProps<{
    folder: FolderTreeNode;
    depth?: number;
    selectedFolderId?: string | null;
    disabledFolderIds?: string[];
  }>(),
  {
    depth: 0,
    selectedFolderId: null,
    disabledFolderIds: () => [],
  },
);

const emit = defineEmits<{
  select: [folderId: string];
}>();

const isExpanded = ref(true);

const hasChildren = computed(() => props.folder.children.length > 0);
const isDisabled = computed(() =>
  props.disabledFolderIds.includes(props.folder.folder_id),
);

function toggleExpand() {
  isExpanded.value = !isExpanded.value;
}
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
