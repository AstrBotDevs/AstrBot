<template>
  <div class="folder-item-selector">
    <!-- 触发按钮区域 -->
    <div class="d-flex align-center justify-space-between">
      <span v-if="!modelValue" class="folder-item-selector__empty-label">
        {{ labels.notSelected || '未选择' }}
      </span>
      <span v-else>
        {{ displayValue }}
      </span>
      <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
        {{ labels.buttonText || '选择...' }}
      </v-btn>
    </div>

    <!-- 选择对话框 -->
    <v-dialog
      v-model="dialog"
      :max-width="isCompactLayout ? '96vw' : '1000px'"
      :min-width="isCompactLayout ? undefined : '800px'"
    >
      <v-card class="app-dialog selector-dialog-card">
        <v-card-title
          class="dialog-title d-flex align-center"
          :class="isCompactLayout ? 'py-3 px-4' : 'py-4 px-5'"
        >
          <v-icon class="mr-3" color="primary">mdi-account-circle</v-icon>
          <span>{{ labels.dialogTitle || '选择项目' }}</span>
        </v-card-title>

        <v-divider />

        <v-card-text class="pa-0 selector-content">
          <div class="selector-layout">
            <!-- 左侧文件夹树 -->
            <div v-if="!isCompactLayout" class="folder-sidebar">
              <div class="sidebar-header pa-3 pb-2">
                <span
                  class="text-caption text-medium-emphasis font-weight-medium"
                >
                  <v-icon size="small" class="mr-1">mdi-folder-multiple</v-icon>
                  文件夹
                </span>
              </div>
              <v-list
                density="compact"
                nav
                class="tree-list pa-2"
                bg-color="transparent"
              >
                <!-- 根目录 -->
                <v-list-item
                  :active="currentFolderId === null"
                  rounded="md"
                  class="mb-1 root-item"
                  @click="navigateToFolder(null)"
                >
                  <template #prepend>
                    <v-icon
                      size="20"
                      :color="currentFolderId === null ? 'primary' : ''"
                      >mdi-home</v-icon
                    >
                  </template>
                  <v-list-item-title class="text-body-2">{{
                    labels.rootFolder || '根目录'
                  }}</v-list-item-title>
                </v-list-item>

                <!-- 文件夹树 -->
                <template v-if="!treeLoading">
                  <BaseMoveTargetNode
                    v-for="folder in folderTree"
                    :key="folder.folder_id"
                    :folder="folder"
                    :depth="0"
                    :selected-folder-id="currentFolderId"
                    :disabled-folder-ids="[]"
                    @select="navigateToFolder"
                  />
                </template>

                <div v-if="treeLoading" class="text-center pa-4">
                  <v-progress-circular
                    indeterminate
                    size="20"
                    color="primary"
                  />
                </div>
              </v-list>
            </div>

            <!-- 右侧项目列表 -->
            <div class="items-panel">
              <div v-if="isCompactLayout" class="mobile-folder-bar px-4 py-2">
                <v-btn
                  icon="mdi-arrow-left"
                  size="small"
                  variant="text"
                  :disabled="currentFolderId === null"
                  @click="navigateToParentFolder"
                />
                <v-btn
                  size="small"
                  variant="tonal"
                  color="primary"
                  prepend-icon="mdi-home"
                  @click="navigateToFolder(null)"
                >
                  {{ labels.rootFolder || '根目录' }}
                </v-btn>
                <span
                  class="text-caption text-medium-emphasis text-truncate mobile-folder-label"
                >
                  {{ currentFolderLabel }}
                </span>
              </div>

              <v-divider v-if="isCompactLayout" />

              <!-- 面包屑导航 -->
              <div class="breadcrumb-bar px-4 py-3">
                <v-breadcrumbs
                  :items="breadcrumbItems"
                  density="compact"
                  class="pa-0"
                >
                  <template #item="{ item }">
                    <v-breadcrumbs-item
                      :disabled="toBreadcrumbItem(item).disabled"
                      :class="{
                        'breadcrumb-link': !toBreadcrumbItem(item).disabled,
                      }"
                      @click="
                        !toBreadcrumbItem(item).disabled &&
                        navigateToFolder(toBreadcrumbItem(item).folderId)
                      "
                    >
                      <v-icon
                        v-if="toBreadcrumbItem(item).isRoot"
                        size="small"
                        class="mr-1"
                        >mdi-home</v-icon
                      >
                      {{ toBreadcrumbItem(item).title }}
                    </v-breadcrumbs-item>
                  </template>
                  <template #divider>
                    <v-icon size="small" color="on-surface-variant"
                      >mdi-chevron-right</v-icon
                    >
                  </template>
                </v-breadcrumbs>
              </div>

              <v-divider />

              <!-- 项目列表 -->
              <div class="items-list">
                <v-progress-linear
                  v-if="itemsLoading"
                  indeterminate
                  color="primary"
                  height="2"
                ></v-progress-linear>

                <!-- 子文件夹 -->
                <v-list
                  v-if="!itemsLoading"
                  lines="two"
                  class="pa-3 items-content"
                >
                  <template v-if="currentSubFolders.length > 0">
                    <div
                      class="section-label text-caption text-medium-emphasis mb-2 px-2"
                    >
                      子文件夹
                    </div>
                    <v-list-item
                      v-for="folder in currentSubFolders"
                      :key="'folder-' + folder.folder_id"
                      rounded="md"
                      class="mb-1 folder-item"
                      @click="navigateToFolder(folder.folder_id)"
                    >
                      <template #prepend>
                        <v-avatar
                          size="36"
                          color="amber-lighten-4"
                          class="mr-3"
                        >
                          <v-icon color="amber-darken-2" size="20"
                            >mdi-folder</v-icon
                          >
                        </v-avatar>
                      </template>
                      <v-list-item-title class="font-weight-medium">{{
                        folder.name
                      }}</v-list-item-title>
                      <template #append>
                        <v-icon size="20" color="on-surface-variant"
                          >mdi-chevron-right</v-icon
                        >
                      </template>
                    </v-list-item>
                  </template>

                  <!-- 项目列表 -->
                  <template v-if="currentItems.length > 0">
                    <div
                      class="section-label text-caption text-medium-emphasis mb-2 px-2"
                      :class="{ 'mt-4': currentSubFolders.length > 0 }"
                    >
                      可选项目
                    </div>
                    <v-list-item
                      v-for="item in currentItems"
                      :key="'item-' + getItemId(item)"
                      :value="getItemId(item)"
                      :active="selectedItemId === getItemId(item)"
                      rounded="md"
                      class="mb-1 persona-item"
                      :class="{
                        'selected-item': selectedItemId === getItemId(item),
                      }"
                      @click="selectItem(item)"
                    >
                      <template #prepend>
                        <v-avatar
                          size="36"
                          :color="
                            selectedItemId === getItemId(item)
                              ? 'primary-lighten-4'
                              : 'grey-lighten-3'
                          "
                          class="mr-3"
                        >
                          <v-icon
                            :color="
                              selectedItemId === getItemId(item)
                                ? 'primary'
                                : 'grey-darken-1'
                            "
                            size="20"
                            >mdi-account</v-icon
                          >
                        </v-avatar>
                      </template>
                      <v-list-item-title class="font-weight-medium">{{
                        getItemName(item)
                      }}</v-list-item-title>
                      <v-list-item-subtitle
                        v-if="getItemDescription(item)"
                        class="text-truncate"
                      >
                        {{ truncateText(getItemDescription(item), 80) }}
                      </v-list-item-subtitle>

                      <template #append>
                        <div class="d-flex align-center ga-1">
                          <v-btn
                            v-if="showEditButton && !isDefaultItem(item)"
                            icon="mdi-pencil"
                            size="small"
                            variant="text"
                            :title="labels.editButton || 'Edit'"
                            @click.stop="handleEditItem(item)"
                          />
                          <v-icon
                            v-if="selectedItemId === getItemId(item)"
                            color="primary"
                            size="22"
                            >mdi-check-circle</v-icon
                          >
                        </div>
                      </template>
                    </v-list-item>
                  </template>

                  <!-- 空状态 -->
                  <div
                    v-if="
                      currentSubFolders.length === 0 &&
                      currentItems.length === 0
                    "
                    class="empty-state text-center py-12"
                  >
                    <v-icon size="64" color="on-surface-variant"
                      >mdi-folder-open-outline</v-icon
                    >
                    <p class="text-grey mt-4 text-body-2">
                      {{
                        labels.emptyFolder || labels.noItems || '此文件夹为空'
                      }}
                    </p>
                  </div>
                </v-list>
              </div>
            </div>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4">
          <v-btn
            v-if="showCreateButton"
            variant="text"
            color="primary"
            prepend-icon="mdi-plus"
            @click="emit('create')"
          >
            {{ labels.createButton || '新建' }}
          </v-btn>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="cancelSelection">{{
            labels.cancelButton || '取消'
          }}</v-btn>
          <v-btn
            color="primary"
            :disabled="!selectedItemId"
            @click="confirmSelection"
          >
            {{ labels.confirmButton || '确认' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useDisplay } from 'vuetify';
import BaseMoveTargetNode from './BaseMoveTargetNode.vue';
import type {
  BreadcrumbItem,
  FolderTreeNode,
  FolderItemSelectorLabels,
  SelectableItem,
} from './types';

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    folderTree?: FolderTreeNode[];
    items?: SelectableItem[];
    treeLoading?: boolean;
    itemsLoading?: boolean;
    labels?: Partial<FolderItemSelectorLabels>;
    showCreateButton?: boolean;
    showEditButton?: boolean;
    defaultItem?: SelectableItem | null;
    itemIdField?: string;
    itemNameField?: string;
    itemDescriptionField?: string;
    displayValueFormatter?: ((value: string) => string) | null;
  }>(),
  {
    modelValue: '',
    folderTree: () => [],
    items: () => [],
    treeLoading: false,
    itemsLoading: false,
    labels: () => ({}),
    showCreateButton: false,
    showEditButton: false,
    defaultItem: null,
    itemIdField: 'id',
    itemNameField: 'name',
    itemDescriptionField: 'description',
    displayValueFormatter: null,
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: string];
  navigate: [folderId: string | null];
  create: [];
  edit: [item: SelectableItem];
}>();

const { smAndDown } = useDisplay();

const dialog = ref(false);
const selectedItemId = ref('');
const currentFolderId = ref<string | null>(null);
const breadcrumbPath = ref<FolderTreeNode[]>([]);

const isCompactLayout = computed(() => smAndDown.value);

const currentFolderLabel = computed(() => {
  if (currentFolderId.value === null) {
    return props.labels.rootFolder || '根目录';
  }

  const currentFolder = breadcrumbPath.value.at(-1);
  return currentFolder?.name || props.labels.rootFolder || '根目录';
});

const displayValue = computed(() => {
  if (props.displayValueFormatter) {
    return props.displayValueFormatter(props.modelValue);
  }

  if (props.defaultItem && props.modelValue === getItemId(props.defaultItem)) {
    return props.labels.defaultItem || getItemName(props.defaultItem);
  }

  return props.modelValue;
});

const currentItems = computed<SelectableItem[]>(() => {
  const items: SelectableItem[] = [];

  if (currentFolderId.value === null && props.defaultItem) {
    items.push(props.defaultItem);
  }

  items.push(...props.items);
  return items;
});

const currentSubFolders = computed<FolderTreeNode[]>(() => {
  if (currentFolderId.value === null) {
    return props.folderTree;
  }

  return findFolderInTree(currentFolderId.value)?.children || [];
});

const breadcrumbItems = computed<BreadcrumbItem[]>(() => {
  const items: BreadcrumbItem[] = [
    {
      title: props.labels.rootFolder || '根目录',
      folderId: null,
      disabled: currentFolderId.value === null,
      isRoot: true,
    },
  ];

  breadcrumbPath.value.forEach((folder, index) => {
    items.push({
      title: folder.name,
      folderId: folder.folder_id,
      disabled: index === breadcrumbPath.value.length - 1,
      isRoot: false,
    });
  });

  return items;
});

function normalizeTextValue(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value);
  }
  return '';
}

function getItemFieldValue(
  item: SelectableItem,
  primaryField: string,
  fallbackField: keyof SelectableItem,
): string {
  return (
    normalizeTextValue(item[primaryField]) ||
    normalizeTextValue(item[fallbackField])
  );
}

function toBreadcrumbItem(item: unknown): BreadcrumbItem {
  return item as BreadcrumbItem;
}

function getItemId(item: SelectableItem): string {
  return getItemFieldValue(item, props.itemIdField, 'id');
}

function getItemName(item: SelectableItem): string {
  return getItemFieldValue(item, props.itemNameField, 'name');
}

function getItemDescription(item: SelectableItem): string {
  return getItemFieldValue(item, props.itemDescriptionField, 'description');
}

function truncateText(text: string, maxLength: number): string {
  if (!text) {
    return '';
  }

  return text.length > maxLength ? `${text.substring(0, maxLength)}...` : text;
}

function openDialog() {
  selectedItemId.value = props.modelValue;
  currentFolderId.value = null;
  breadcrumbPath.value = [];
  dialog.value = true;
  emit('navigate', null);
}

function navigateToFolder(folderId: string | null) {
  currentFolderId.value = folderId;
  updateBreadcrumb(folderId);
  emit('navigate', folderId);
}

function navigateToParentFolder() {
  if (currentFolderId.value === null) {
    return;
  }

  if (breadcrumbPath.value.length <= 1) {
    navigateToFolder(null);
    return;
  }

  const parent = breadcrumbPath.value.at(-2);
  navigateToFolder(parent?.folder_id ?? null);
}

function findFolderInTree(folderId: string): FolderTreeNode | null {
  const findNode = (nodes: FolderTreeNode[]): FolderTreeNode | null => {
    for (const node of nodes) {
      if (node.folder_id === folderId) {
        return node;
      }
      if (node.children.length > 0) {
        const found = findNode(node.children);
        if (found) {
          return found;
        }
      }
    }
    return null;
  };

  return findNode(props.folderTree);
}

function findPathToFolder(folderId: string): FolderTreeNode[] {
  const findPath = (
    nodes: FolderTreeNode[],
    path: FolderTreeNode[],
  ): FolderTreeNode[] | null => {
    for (const node of nodes) {
      if (node.folder_id === folderId) {
        return [...path, node];
      }
      if (node.children.length > 0) {
        const result = findPath(node.children, [...path, node]);
        if (result) {
          return result;
        }
      }
    }
    return null;
  };

  return findPath(props.folderTree, []) || [];
}

function updateBreadcrumb(folderId: string | null) {
  breadcrumbPath.value = folderId === null ? [] : findPathToFolder(folderId);
}

function selectItem(item: SelectableItem) {
  selectedItemId.value = getItemId(item);
}

function confirmSelection() {
  emit('update:modelValue', selectedItemId.value);
  dialog.value = false;
}

function cancelSelection() {
  selectedItemId.value = props.modelValue;
  dialog.value = false;
}

function isDefaultItem(item: SelectableItem): boolean {
  if (props.defaultItem === null) {
    return false;
  }

  return getItemId(item) === getItemId(props.defaultItem);
}

function handleEditItem(item: SelectableItem) {
  emit('edit', item);
}
</script>

<style scoped>
.folder-item-selector__empty-label {
  color: rgb(var(--v-theme-on-surface));
}

.selector-dialog-card {
  border-radius: 12px;
  overflow: hidden;
}

.dialog-title {
  font-size: 1.25rem;
  font-weight: 500;
}

.selector-layout {
  display: flex;
  height: 100%;
  min-width: 0;
}

.selector-content {
  height: 600px;
  max-height: 80vh;
  overflow: hidden;
}

.folder-sidebar {
  width: 280px;
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  overflow-y: auto;
  flex-shrink: 0;
  background-color: transparent;
}

.sidebar-header {
  border-bottom: 1px solid rgba(var(--v-border-color), 0.5);
}

.items-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background-color: rgb(var(--v-theme-surface));
}

.breadcrumb-bar {
  background-color: transparent;
  min-height: 56px;
  display: flex;
  align-items: center;
}

.items-list {
  flex: 1;
  overflow-y: auto;
}

.items-content {
  background-color: transparent;
  min-width: 0;
}

.mobile-folder-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mobile-folder-label {
  min-width: 0;
  flex: 1;
}

.tree-list {
  padding: 0;
}

.section-label {
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-size: 0.7rem;
}

.breadcrumb-link {
  cursor: pointer;
  transition: color 0.2s;
}

.breadcrumb-link:hover {
  color: rgb(var(--v-theme-primary));
}

.root-item {
  margin-bottom: 4px;
}

.folder-item {
  transition: all 0.15s ease;
}

.folder-item:hover {
  background-color: rgba(var(--v-theme-primary), 0.06);
}

.persona-item {
  transition: all 0.15s ease;
  border: 1px solid transparent;
}

.persona-item:hover {
  background-color: rgba(var(--v-theme-primary), 0.04);
}

.persona-item.selected-item {
  background-color: rgba(var(--v-theme-primary), 0.08);
  border-color: rgba(var(--v-theme-primary), 0.3);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.v-list-item {
  transition: all 0.15s ease;
}

.v-list-item:hover {
  background-color: rgba(var(--v-theme-primary), 0.04);
}

.v-list-item.v-list-item--active {
  background-color: rgba(var(--v-theme-primary), 0.08);
}

@media (max-width: 960px) {
  .selector-layout {
    flex-direction: column;
    height: auto;
    max-height: none;
  }

  .selector-content {
    max-height: 76vh;
  }

  .items-list {
    min-height: 0;
  }

  .breadcrumb-bar {
    overflow-x: auto;
  }

  .breadcrumb-bar :deep(.v-breadcrumbs) {
    flex-wrap: nowrap;
    min-width: max-content;
  }
}
</style>
