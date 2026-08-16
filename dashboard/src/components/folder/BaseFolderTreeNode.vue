<template>
  <div class="base-folder-tree-node">
    <v-list-item
      :active="currentFolderId === folder.folder_id"
      rounded="md"
      :style="{ paddingLeft: `${(depth + 1) * 16}px` }"
      :class="['folder-item', { 'drag-over': isDragOver }]"
      @click.stop="emit('folder-click', folder.folder_id)"
      @contextmenu.prevent="handleContextMenu"
      @dragover.prevent="handleDragOver"
      @dragleave="handleDragLeave"
      @drop.prevent="handleDrop"
    >
      <template #prepend>
        <v-btn
          v-if="hasChildren"
          icon
          variant="text"
          size="x-small"
          class="expand-btn"
          @click.stop="toggleExpand"
        >
          <v-icon size="16">{{
            isExpanded ? 'mdi-chevron-down' : 'mdi-chevron-right'
          }}</v-icon>
        </v-btn>
        <div v-else class="expand-placeholder"></div>
        <v-icon :color="currentFolderId === folder.folder_id ? 'primary' : ''">
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
        <BaseFolderTreeNode
          v-for="child in folder.children"
          :key="child.folder_id"
          :folder="child"
          :depth="depth + 1"
          :current-folder-id="currentFolderId"
          :search-query="searchQuery"
          :expanded-folder-ids="expandedFolderIds"
          :accept-drop-types="acceptDropTypes"
          @folder-click="emit('folder-click', $event)"
          @folder-context-menu="emit('folder-context-menu', $event)"
          @item-dropped="emit('item-dropped', $event)"
          @toggle-expansion="emit('toggle-expansion', $event)"
          @set-expansion="emit('set-expansion', $event)"
        />
      </div>
    </v-expand-transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { FolderTreeNode } from './types';

type DropPayload = {
  id?: string;
  item_id?: string;
  persona_id?: string;
  type?: string;
};

const props = withDefaults(
  defineProps<{
    folder: FolderTreeNode;
    depth?: number;
    currentFolderId?: string | null;
    searchQuery?: string;
    expandedFolderIds?: string[];
    acceptDropTypes?: string[];
  }>(),
  {
    depth: 0,
    currentFolderId: null,
    searchQuery: '',
    expandedFolderIds: () => [],
    acceptDropTypes: () => [],
  },
);

const emit = defineEmits<{
  'folder-click': [folderId: string];
  'folder-context-menu': [
    payload: { event: MouseEvent; folder: FolderTreeNode },
  ];
  'item-dropped': [
    payload: {
      item_id: string;
      item_type: string;
      target_folder_id: string;
      source_data: DropPayload;
    },
  ];
  'toggle-expansion': [folderId: string];
  'set-expansion': [payload: { folderId: string; expanded: boolean }];
}>();

const isDragOver = ref(false);

const hasChildren = computed(() => props.folder.children.length > 0);
const isExpanded = computed(() =>
  props.expandedFolderIds.includes(props.folder.folder_id),
);

watch(
  () => props.searchQuery,
  (newQuery) => {
    if (newQuery && hasChildren.value) {
      emit('set-expansion', {
        folderId: props.folder.folder_id,
        expanded: true,
      });
    }
  },
  { immediate: true },
);

function toggleExpand() {
  emit('toggle-expansion', props.folder.folder_id);
}

function handleContextMenu(event: MouseEvent) {
  emit('folder-context-menu', { event, folder: props.folder });
}

function handleDragOver(event: DragEvent) {
  if (!event.dataTransfer) {
    return;
  }
  event.dataTransfer.dropEffect = 'move';
  isDragOver.value = true;
}

function handleDragLeave() {
  isDragOver.value = false;
}

function handleDrop(event: DragEvent) {
  isDragOver.value = false;
  if (!event.dataTransfer) {
    return;
  }

  try {
    const data = JSON.parse(
      event.dataTransfer.getData('application/json'),
    ) as DropPayload;
    const itemType = data.type;
    const itemId = data.id ?? data.persona_id ?? data.item_id;
    if (
      !itemType ||
      !itemId ||
      (props.acceptDropTypes.length > 0 &&
        !props.acceptDropTypes.includes(itemType))
    ) {
      return;
    }
    emit('item-dropped', {
      item_id: itemId,
      item_type: itemType,
      target_folder_id: props.folder.folder_id,
      source_data: data,
    });
  } catch (error) {
    console.error('Failed to parse drop data:', error);
  }
}
</script>

<style scoped>
.base-folder-tree-node {
  width: 100%;
}

.folder-item {
  min-height: 36px;
  transition: all 0.2s ease;
}

.folder-item.drag-over {
  background-color: rgba(var(--v-theme-primary), 0.15);
  border: 2px dashed rgb(var(--v-theme-primary));
  border-radius: 8px;
}

.expand-btn {
  margin-right: 4px;
}

.expand-placeholder {
  width: 28px;
  flex-shrink: 0;
}
</style>
