<template>
  <div class="base-folder-tree">
    <!-- 搜索框 -->
    <v-text-field
      v-model="searchQuery"
      :placeholder="mergedLabels.searchPlaceholder"
      prepend-inner-icon="mdi-magnify"
      variant="outlined"
      density="compact"
      hide-details
      clearable
      class="mb-3"
    />

    <!-- 根目录节点 -->
    <v-list density="compact" nav class="tree-list" bg-color="transparent">
      <v-list-item
        :active="currentFolderId === null"
        rounded="md"
        :class="['root-item', { 'drag-over': isRootDragOver }]"
        @click="handleFolderClick(null)"
        @dragover.prevent="handleRootDragOver"
        @dragleave="handleRootDragLeave"
        @drop.prevent="handleRootDrop"
      >
        <template #prepend>
          <v-icon>mdi-home</v-icon>
        </template>
        <v-list-item-title>{{ mergedLabels.rootFolder }}</v-list-item-title>
      </v-list-item>

      <!-- 文件夹树 -->
      <template v-if="!treeLoading">
        <BaseFolderTreeNode
          v-for="folder in filteredFolderTree"
          :key="folder.folder_id"
          :folder="folder"
          :depth="0"
          :current-folder-id="currentFolderId"
          :search-query="searchQuery"
          :expanded-folder-ids="expandedFolderIds"
          :accept-drop-types="acceptDropTypes"
          @folder-click="handleFolderClick"
          @folder-context-menu="handleContextMenu"
          @item-dropped="emit('item-dropped', $event)"
          @toggle-expansion="emit('toggle-expansion', $event)"
          @set-expansion="emit('set-expansion', $event)"
        />
      </template>

      <!-- 加载状态 -->
      <div v-if="treeLoading" class="text-center pa-4">
        <v-progress-circular indeterminate size="24" />
      </div>

      <!-- 空状态 -->
      <div
        v-if="!treeLoading && folderTree.length === 0"
        class="text-center pa-4 text-medium-emphasis"
      >
        <v-icon size="32" class="mb-2">mdi-folder-outline</v-icon>
        <div class="text-body-2">{{ mergedLabels.noFolders }}</div>
      </div>
    </v-list>

    <!-- 右键菜单 -->
    <v-menu
      v-model="contextMenu.show"
      :target="contextMenuTarget"
      location="end"
      :close-on-content-click="true"
    >
      <v-list density="compact">
        <v-list-item @click="openFolder">
          <template #prepend>
            <v-icon size="small">mdi-folder-open</v-icon>
          </template>
          <v-list-item-title>{{
            mergedLabels.contextMenu.open
          }}</v-list-item-title>
        </v-list-item>
        <v-list-item @click="renameFolder">
          <template #prepend>
            <v-icon size="small">mdi-pencil</v-icon>
          </template>
          <v-list-item-title>{{
            mergedLabels.contextMenu.rename
          }}</v-list-item-title>
        </v-list-item>
        <v-list-item @click="moveFolder">
          <template #prepend>
            <v-icon size="small">mdi-folder-move</v-icon>
          </template>
          <v-list-item-title>{{
            mergedLabels.contextMenu.moveTo
          }}</v-list-item-title>
        </v-list-item>
        <v-divider class="my-1" />
        <v-list-item class="text-error" @click="deleteFolder">
          <template #prepend>
            <v-icon size="small" color="error">mdi-delete</v-icon>
          </template>
          <v-list-item-title>{{
            mergedLabels.contextMenu.delete
          }}</v-list-item-title>
        </v-list-item>
      </v-list>
    </v-menu>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import type { Folder, FolderTreeNode, ContextMenuEvent } from './types';
import BaseFolderTreeNode from './BaseFolderTreeNode.vue';

interface DefaultLabels {
  searchPlaceholder: string;
  rootFolder: string;
  noFolders: string;
  contextMenu: {
    open: string;
    rename: string;
    moveTo: string;
    delete: string;
  };
}

const defaultLabels: DefaultLabels = {
  searchPlaceholder: '搜索文件夹...',
  rootFolder: '根目录',
  noFolders: '暂无文件夹',
  contextMenu: {
    open: '打开',
    rename: '重命名',
    moveTo: '移动到...',
    delete: '删除',
  },
};

type DropPayload = {
  id?: string;
  item_id?: string;
  persona_id?: string;
  type?: string;
};

const props = withDefaults(
  defineProps<{
    folderTree: FolderTreeNode[];
    currentFolderId?: string | null;
    expandedFolderIds?: string[];
    treeLoading?: boolean;
    acceptDropTypes?: string[];
    labels?: Partial<DefaultLabels>;
  }>(),
  {
    currentFolderId: null,
    expandedFolderIds: () => [],
    treeLoading: false,
    acceptDropTypes: () => [],
    labels: () => ({}),
  },
);

const emit = defineEmits<{
  'folder-click': [folderId: string | null];
  'rename-folder': [folder: Folder];
  'move-folder': [folder: Folder];
  'delete-folder': [folder: Folder];
  'item-dropped': [
    payload: {
      item_id: string;
      item_type: string;
      target_folder_id: string | null;
      source_data: DropPayload;
    },
  ];
  'toggle-expansion': [folderId: string];
  'set-expansion': [payload: { folderId: string; expanded: boolean }];
}>();

const searchQuery = ref('');
const isRootDragOver = ref(false);
const contextMenu = reactive<{
  show: boolean;
  target: [number, number] | null;
  folder: Folder | null;
}>({
  show: false,
  target: null,
  folder: null,
});

const mergedLabels = computed<DefaultLabels>(() => ({
  ...defaultLabels,
  ...props.labels,
  contextMenu: {
    ...defaultLabels.contextMenu,
    ...(props.labels?.contextMenu ?? {}),
  },
}));

const contextMenuTarget = computed(() => contextMenu.target ?? undefined);

const filteredFolderTree = computed(() => {
  if (!searchQuery.value) {
    return props.folderTree;
  }
  return filterTreeBySearch(props.folderTree, searchQuery.value.toLowerCase());
});

function filterTreeBySearch(
  nodes: FolderTreeNode[],
  query: string,
): FolderTreeNode[] {
  return nodes
    .filter((node) => {
      const matches = node.name.toLowerCase().includes(query);
      const childMatches = filterTreeBySearch(node.children, query);
      return matches || childMatches.length > 0;
    })
    .map((node) => ({
      ...node,
      children: filterTreeBySearch(node.children, query),
    }));
}

function handleFolderClick(folderId: string | null) {
  emit('folder-click', folderId);
}

function handleRootDragOver(event: DragEvent) {
  if (!event.dataTransfer) {
    return;
  }
  event.dataTransfer.dropEffect = 'move';
  isRootDragOver.value = true;
}

function handleRootDragLeave() {
  isRootDragOver.value = false;
}

function handleRootDrop(event: DragEvent) {
  isRootDragOver.value = false;
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
      target_folder_id: null,
      source_data: data,
    });
  } catch (error) {
    console.error('Failed to parse drop data:', error);
  }
}

function handleContextMenu(eventData: ContextMenuEvent) {
  contextMenu.target = [eventData.event.clientX, eventData.event.clientY];
  contextMenu.folder = eventData.folder;
  contextMenu.show = true;
}

function openFolder() {
  if (contextMenu.folder) {
    emit('folder-click', contextMenu.folder.folder_id);
  }
}

function renameFolder() {
  if (contextMenu.folder) {
    emit('rename-folder', contextMenu.folder);
  }
}

function moveFolder() {
  if (contextMenu.folder) {
    emit('move-folder', contextMenu.folder);
  }
}

function deleteFolder() {
  if (contextMenu.folder) {
    emit('delete-folder', contextMenu.folder);
  }
}
</script>

<style scoped>
.base-folder-tree {
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
