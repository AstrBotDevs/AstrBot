<template>
  <div class="folder-item-selector">
    <!-- 触发按钮区域 -->
    <div class="d-flex align-center justify-space-between">
      <span v-if="!modelValue" class="text-medium-emphasis">
        {{ labels.notSelected || "未选择" }}
      </span>
      <span v-else>
        {{ displayValue }}
      </span>
      <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
        {{ labels.buttonText || "选择..." }}
      </v-btn>
    </div>

    <!-- 选择对话框 -->
    <v-dialog
      v-model="dialog"
      :max-width="isCompactLayout ? '96vw' : '1000px'"
      :min-width="isCompactLayout ? undefined : '800px'"
    >
      <v-card class="selector-dialog-card">
        <v-card-title class="selector-dialog-title text-h3">
          {{ labels.dialogTitle || "选择项目" }}
        </v-card-title>

        <v-card-text class="pa-0 selector-content">
          <div class="selector-layout">
            <!-- 左侧文件夹树 -->
            <div v-if="!isCompactLayout && hasFolders" class="folder-sidebar">
              <div
                class="sidebar-header d-flex align-center justify-space-between"
              >
                <span>文件夹</span>
              </div>
              <div class="tree-list">
                <!-- 根目录 -->
                <button
                  type="button"
                  class="folder-tree-root"
                  :class="{
                    'folder-tree-root--active': currentFolderId === null,
                  }"
                  @click="navigateToFolder(null)"
                >
                  <span>{{ labels.rootFolder || "根目录" }}</span>
                </button>

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
                  <v-progress-circular indeterminate size="20" color="grey" />
                </div>
              </div>
            </div>

            <!-- 右侧项目列表 -->
            <div class="items-panel">
              <div
                v-if="isCompactLayout && hasFolders"
                class="mobile-folder-bar px-4 py-2"
              >
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
                  prepend-icon="mdi-home-outline"
                  @click="navigateToFolder(null)"
                >
                  {{ labels.rootFolder || "根目录" }}
                </v-btn>
                <span
                  class="text-caption text-medium-emphasis text-truncate mobile-folder-label"
                >
                  {{ currentFolderLabel }}
                </span>
              </div>

              <!-- 面包屑导航 -->
              <div v-if="hasFolders" class="breadcrumb-bar px-4 py-3">
                <v-breadcrumbs
                  :items="breadcrumbItems"
                  density="compact"
                  class="pa-0"
                >
                  <template v-slot:item="{ item }">
                    <v-breadcrumbs-item
                      :disabled="(item as any).disabled"
                      @click="
                        !(item as any).disabled &&
                          navigateToFolder((item as any).folderId)
                      "
                      :class="{ 'breadcrumb-link': !(item as any).disabled }"
                    >
                      {{ item.title }}
                    </v-breadcrumbs-item>
                  </template>
                  <template v-slot:divider>
                    <v-icon size="small" color="grey">mdi-chevron-right</v-icon>
                  </template>
                </v-breadcrumbs>
              </div>

              <!-- 项目列表 -->
              <div class="items-list">
                <v-progress-linear
                  v-if="itemsLoading"
                  indeterminate
                  color="grey"
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
                      @click="navigateToFolder(folder.folder_id)"
                      rounded="md"
                      class="mb-1 folder-item"
                    >
                      <template v-slot:prepend>
                        <v-icon size="18" class="item-leading-icon"
                          >mdi-folder-outline</v-icon
                        >
                      </template>
                      <v-list-item-title class="font-weight-medium">{{
                        folder.name
                      }}</v-list-item-title>
                      <template v-slot:append>
                        <v-icon size="20" color="grey"
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
                      @click="selectItem(item)"
                      rounded="md"
                      class="mb-1 persona-item"
                      :class="{
                        'selected-item': selectedItemId === getItemId(item),
                      }"
                    >
                      <v-list-item-title class="font-weight-medium">{{
                        getItemName(item)
                      }}</v-list-item-title>
                      <v-list-item-subtitle
                        v-if="getItemDescription(item)"
                        class="text-truncate"
                      >
                        {{ truncateText(getItemDescription(item), 80) }}
                      </v-list-item-subtitle>

                      <template v-slot:append>
                        <div class="d-flex align-center ga-1">
                          <v-btn
                            v-if="showEditButton && !isDefaultItem(item)"
                            icon="mdi-pencil"
                            size="small"
                            variant="text"
                            @click.stop="handleEditItem(item)"
                            :title="labels.editButton || 'Edit'"
                          />
                          <v-icon
                            v-if="selectedItemId === getItemId(item)"
                            size="18"
                            >mdi-check</v-icon
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
                    <v-icon size="64" color="grey-lighten-2"
                      >mdi-folder-open-outline</v-icon
                    >
                    <p class="text-grey mt-4 text-body-2">
                      {{
                        labels.emptyFolder || labels.noItems || "此文件夹为空"
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
            prepend-icon="mdi-plus"
            @click="$emit('create')"
          >
            {{ labels.createButton || "新建" }}
          </v-btn>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="cancelSelection">{{
            labels.cancelButton || "取消"
          }}</v-btn>
          <v-btn
            variant="tonal"
            @click="confirmSelection"
            :disabled="!selectedItemId"
          >
            {{ labels.confirmButton || "确认" }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from "vue";
import BaseMoveTargetNode from "./BaseMoveTargetNode.vue";
import type {
  FolderTreeNode,
  FolderItemSelectorLabels,
  SelectableItem,
} from "./types";

export default defineComponent({
  name: "BaseFolderItemSelector",
  components: {
    BaseMoveTargetNode,
  },
  props: {
    modelValue: {
      type: String,
      default: "",
    },
    // 文件夹树数据
    folderTree: {
      type: Array as PropType<FolderTreeNode[]>,
      default: () => [],
    },
    // 当前项目列表
    items: {
      type: Array as PropType<SelectableItem[]>,
      default: () => [],
    },
    // 加载状态
    treeLoading: {
      type: Boolean,
      default: false,
    },
    itemsLoading: {
      type: Boolean,
      default: false,
    },
    // 标签配置
    labels: {
      type: Object as PropType<Partial<FolderItemSelectorLabels>>,
      default: () => ({}),
    },
    // 是否显示创建按钮
    showCreateButton: {
      type: Boolean,
      default: false,
    },
    // 是否显示编辑按钮
    showEditButton: {
      type: Boolean,
      default: false,
    },
    // 默认项（如 "默认人格"）
    defaultItem: {
      type: Object as PropType<SelectableItem | null>,
      default: null,
    },
    // 项目字段映射
    itemIdField: {
      type: String,
      default: "id",
    },
    itemNameField: {
      type: String,
      default: "name",
    },
    itemDescriptionField: {
      type: String,
      default: "description",
    },
    // 显示值的格式化函数（用于显示选中项的名称）
    displayValueFormatter: {
      type: Function as unknown as PropType<((value: string) => string) | null>,
      default: null,
    },
  },
  emits: ["update:modelValue", "navigate", "create", "edit"],
  data() {
    return {
      dialog: false,
      selectedItemId: "" as string,
      currentFolderId: null as string | null,
      breadcrumbPath: [] as FolderTreeNode[],
    };
  },
  computed: {
    isCompactLayout(): boolean {
      return this.$vuetify.display.smAndDown;
    },

    hasFolders(): boolean {
      return this.folderTree.length > 0;
    },

    currentFolderLabel(): string {
      if (this.currentFolderId === null) {
        return this.labels.rootFolder || "根目录";
      }
      const currentFolder = this.breadcrumbPath[this.breadcrumbPath.length - 1];
      return currentFolder?.name || this.labels.rootFolder || "根目录";
    },

    displayValue(): string {
      if (this.displayValueFormatter) {
        return this.displayValueFormatter(this.modelValue);
      }
      // 如果是默认项
      if (
        this.defaultItem &&
        this.modelValue === this.getItemId(this.defaultItem)
      ) {
        return this.labels.defaultItem || this.getItemName(this.defaultItem);
      }
      return this.modelValue;
    },

    currentItems(): SelectableItem[] {
      const items: SelectableItem[] = [];
      const defaultItemId = this.defaultItem
        ? this.getItemId(this.defaultItem)
        : null;

      // 如果在根目录且有默认项，添加到列表开头
      if (this.currentFolderId === null && this.defaultItem) {
        items.push(this.defaultItem);
      }

      // 添加当前文件夹的项目
      items.push(
        ...this.items.filter((item) => this.getItemId(item) !== defaultItemId),
      );

      return items;
    },

    currentSubFolders(): FolderTreeNode[] {
      if (this.currentFolderId === null) {
        return this.folderTree;
      }
      const folder = this.findFolderInTree(this.currentFolderId);
      return folder?.children || [];
    },

    breadcrumbItems(): any[] {
      const items: any[] = [
        {
          title: this.labels.rootFolder || "根目录",
          folderId: null,
          disabled: this.currentFolderId === null,
          isRoot: true,
        },
      ];

      this.breadcrumbPath.forEach((folder, index) => {
        items.push({
          title: folder.name,
          folderId: folder.folder_id,
          disabled: index === this.breadcrumbPath.length - 1,
          isRoot: false,
        });
      });

      return items;
    },
  },
  methods: {
    getItemId(item: SelectableItem): string {
      return String(item[this.itemIdField] || item.id || "");
    },

    getItemName(item: SelectableItem): string {
      return String(item[this.itemNameField] || item.name || "");
    },

    getItemDescription(item: SelectableItem): string {
      return String(item[this.itemDescriptionField] || item.description || "");
    },

    truncateText(text: string, maxLength: number): string {
      if (!text) return "";
      return text.length > maxLength
        ? text.substring(0, maxLength) + "..."
        : text;
    },

    openDialog() {
      this.selectedItemId = this.modelValue || "";
      this.currentFolderId = null;
      this.breadcrumbPath = [];
      this.dialog = true;
      this.$emit("navigate", null);
    },

    navigateToFolder(folderId: string | null) {
      this.currentFolderId = folderId;
      this.updateBreadcrumb(folderId);
      this.$emit("navigate", folderId);
    },

    navigateToParentFolder() {
      if (this.currentFolderId === null) {
        return;
      }

      if (this.breadcrumbPath.length <= 1) {
        this.navigateToFolder(null);
        return;
      }

      const parent = this.breadcrumbPath[this.breadcrumbPath.length - 2];
      this.navigateToFolder(parent?.folder_id ?? null);
    },

    findFolderInTree(folderId: string): FolderTreeNode | null {
      const findNode = (nodes: FolderTreeNode[]): FolderTreeNode | null => {
        for (const node of nodes) {
          if (node.folder_id === folderId) {
            return node;
          }
          if (node.children && node.children.length > 0) {
            const found = findNode(node.children);
            if (found) return found;
          }
        }
        return null;
      };
      return findNode(this.folderTree);
    },

    findPathToFolder(folderId: string): FolderTreeNode[] {
      const findPath = (
        nodes: FolderTreeNode[],
        path: FolderTreeNode[],
      ): FolderTreeNode[] | null => {
        for (const node of nodes) {
          if (node.folder_id === folderId) {
            return [...path, node];
          }
          if (node.children && node.children.length > 0) {
            const result = findPath(node.children, [...path, node]);
            if (result) return result;
          }
        }
        return null;
      };
      return findPath(this.folderTree, []) || [];
    },

    updateBreadcrumb(folderId: string | null) {
      if (folderId === null) {
        this.breadcrumbPath = [];
      } else {
        this.breadcrumbPath = this.findPathToFolder(folderId);
      }
    },

    selectItem(item: SelectableItem) {
      this.selectedItemId = this.getItemId(item);
    },

    confirmSelection() {
      this.$emit("update:modelValue", this.selectedItemId);
      this.dialog = false;
    },

    cancelSelection() {
      this.selectedItemId = this.modelValue || "";
      this.dialog = false;
    },

    isDefaultItem(item: SelectableItem): boolean {
      if (this.defaultItem === null) {
        return false;
      }
      return this.getItemId(item) === this.getItemId(this.defaultItem);
    },

    handleEditItem(item: SelectableItem) {
      this.$emit("edit", item);
    },
  },
});
</script>

<style scoped>
.selector-dialog-card {
  border-radius: 12px;
  overflow: hidden;
}

.selector-dialog-title {
  min-height: auto;
  padding: 20px 24px 12px;
  font-weight: 600;
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
  width: 232px;
  margin: 8px 0 8px 24px;
  overflow-y: auto;
  flex-shrink: 0;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.sidebar-header {
  padding: 12px 16px 6px;
  color: rgba(var(--v-theme-on-surface), 0.52);
  font-size: 0.72rem;
  font-weight: 500;
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
  min-height: 44px;
  display: flex;
  align-items: center;
  color: rgba(var(--v-theme-on-surface), 0.58);
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
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px 8px 10px;
}

.folder-tree-root {
  display: flex;
  align-items: center;
  width: 100%;
  height: 30px;
  padding: 0 16px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  text-align: left;
}

.folder-tree-root:hover,
.folder-tree-root--active {
  background: rgba(var(--v-theme-on-surface), 0.07);
}

.section-label {
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-size: 0.7rem;
}

.breadcrumb-link {
  cursor: pointer;
}

.folder-item {
  min-height: 44px;
  transition: background-color 0.15s ease;
}

.folder-item:hover {
  background-color: rgba(var(--v-theme-on-surface), 0.05);
}

.persona-item {
  min-height: 52px;
  transition: background-color 0.15s ease;
}

.persona-item:hover {
  background-color: rgba(var(--v-theme-on-surface), 0.035);
}

.persona-item.selected-item {
  background-color: rgba(var(--v-theme-on-surface), 0.055);
}

.persona-item :deep(.v-list-item__overlay) {
  opacity: 0 !important;
}

.item-leading-icon {
  margin-inline-end: 12px;
  color: rgba(var(--v-theme-on-surface), 0.58);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.selector-dialog-card :deep(.v-btn--variant-tonal) {
  background: rgba(var(--v-theme-on-surface), 0.07);
  color: rgb(var(--v-theme-on-surface));
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
