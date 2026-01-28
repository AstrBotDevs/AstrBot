# 通用文件夹管理组件库

这是一个可复用的文件夹管理 UI 组件库，提供了完整的文件夹树、面包屑导航、拖放操作等功能。可用于管理各种类型的项目，如 Persona、模板、知识库等。

## 组件列表

| 组件 | 说明 |
|------|------|
| `BaseFolderTree` | 文件夹树组件，支持搜索、展开/折叠、右键菜单、拖放 |
| `BaseFolderTreeNode` | 文件夹树节点组件（内部使用） |
| `BaseFolderCard` | 文件夹卡片组件，用于网格布局展示 |
| `BaseFolderBreadcrumb` | 面包屑导航组件 |
| `BaseCreateFolderDialog` | 创建文件夹对话框 |
| `BaseMoveToFolderDialog` | 移动项目到文件夹对话框 |
| `BaseMoveTargetNode` | 移动对话框中的目标文件夹节点（内部使用） |

## Composable

### `useFolderManager`

提供文件夹管理的核心逻辑，包括状态管理、导航、CRUD 操作等。

```typescript
import { useFolderManager } from '@/components/folder';

const {
  // 状态
  folderTree,
  currentFolderId,
  currentFolders,
  breadcrumbPath,
  expandedFolderIds,
  loading,
  treeLoading,
  
  // 计算属性
  currentFolderName,
  breadcrumbItems,
  
  // 方法
  loadFolderTree,
  navigateToFolder,
  refreshCurrentFolder,
  createFolder,
  updateFolder,
  deleteFolder,
  moveFolder,
  toggleFolderExpansion,
  setFolderExpansion,
  findFolderInTree,
  findPathToFolder,
  filterTreeBySearch,
} = useFolderManager({
  operations: {
    loadFolderTree: async () => {
      const response = await axios.get('/api/your-module/folder/tree');
      return response.data.data;
    },
    loadSubFolders: async (parentId) => {
      const response = await axios.get('/api/your-module/folder/list', {
        params: { parent_id: parentId ?? '' }
      });
      return response.data.data;
    },
    createFolder: async (data) => {
      const response = await axios.post('/api/your-module/folder/create', data);
      return response.data.data.folder;
    },
    updateFolder: async (data) => {
      await axios.post('/api/your-module/folder/update', data);
    },
    deleteFolder: async (folderId) => {
      await axios.post('/api/your-module/folder/delete', { folder_id: folderId });
    },
  },
  rootFolderName: '根目录',
  autoLoad: true,
});
```

## 使用示例

### 基础用法

```vue
<template>
  <div class="folder-manager">
    <!-- 侧边栏 -->
    <div class="sidebar">
      <BaseFolderTree
        :folder-tree="folderTree"
        :current-folder-id="currentFolderId"
        :expanded-folder-ids="expandedFolderIds"
        :tree-loading="treeLoading"
        :accept-drop-types="['item']"
        :labels="treeLabels"
        @folder-click="navigateToFolder"
        @rename-folder="handleRenameFolder"
        @move-folder="handleMoveFolder"
        @delete-folder="handleDeleteFolder"
        @item-dropped="handleItemDropped"
        @toggle-expansion="toggleFolderExpansion"
      />
    </div>
    
    <!-- 主内容区 -->
    <div class="main-content">
      <!-- 面包屑 -->
      <BaseFolderBreadcrumb
        :breadcrumb-path="breadcrumbPath"
        :current-folder-id="currentFolderId"
        root-folder-name="根目录"
        @navigate="navigateToFolder"
      />
      
      <!-- 文件夹卡片 -->
      <v-row>
        <v-col v-for="folder in currentFolders" :key="folder.folder_id" cols="3">
          <BaseFolderCard
            :folder="folder"
            :accept-drop-types="['item']"
            :labels="cardLabels"
            @click="navigateToFolder(folder.folder_id)"
            @open="navigateToFolder(folder.folder_id)"
            @rename="handleRenameFolder(folder)"
            @move="handleMoveFolder(folder)"
            @delete="handleDeleteFolder(folder)"
            @item-dropped="handleItemDropped"
          />
        </v-col>
      </v-row>
    </div>
    
    <!-- 创建文件夹对话框 -->
    <BaseCreateFolderDialog
      v-model="showCreateDialog"
      :parent-folder-id="currentFolderId"
      :labels="createDialogLabels"
      @create="handleCreateFolder"
    />
    
    <!-- 移动对话框 -->
    <BaseMoveToFolderDialog
      v-model="showMoveDialog"
      :folder-tree="folderTree"
      :tree-loading="treeLoading"
      :current-folder-id="movingFolder?.folder_id"
      :item-current-folder-id="movingFolder?.parent_id"
      :is-moving-folder="true"
      :labels="moveDialogLabels"
      @move="handleMove"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import {
  BaseFolderTree,
  BaseFolderCard,
  BaseFolderBreadcrumb,
  BaseCreateFolderDialog,
  BaseMoveToFolderDialog,
  useFolderManager,
} from '@/components/folder';

const folderManager = useFolderManager({
  operations: {
    // ... 实现你的 API 调用
  },
});

const {
  folderTree,
  currentFolderId,
  currentFolders,
  breadcrumbPath,
  expandedFolderIds,
  treeLoading,
  navigateToFolder,
  toggleFolderExpansion,
  createFolder,
} = folderManager;

const showCreateDialog = ref(false);
const showMoveDialog = ref(false);
const movingFolder = ref(null);

// 自定义标签
const treeLabels = {
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

const cardLabels = {
  open: '打开',
  rename: '重命名',
  moveTo: '移动到...',
  delete: '删除',
};

const createDialogLabels = {
  title: '创建文件夹',
  nameLabel: '名称',
  descriptionLabel: '描述',
  nameRequired: '请输入名称',
  cancelButton: '取消',
  createButton: '创建',
};

// 处理函数
async function handleCreateFolder(data) {
  await createFolder(data);
  showCreateDialog.value = false;
}

function handleRenameFolder(folder) {
  // 打开重命名对话框
}

function handleMoveFolder(folder) {
  movingFolder.value = folder;
  showMoveDialog.value = true;
}

function handleDeleteFolder(folder) {
  // 确认并删除
}

function handleItemDropped({ item_id, item_type, target_folder_id }) {
  // 处理拖放
}

async function handleMove(targetFolderId) {
  // 执行移动
  showMoveDialog.value = false;
}
</script>
```

## 类型定义

```typescript
// 文件夹基础接口
interface Folder {
  folder_id: string;
  name: string;
  parent_id: string | null;
  description?: string | null;
  sort_order?: number;
  created_at?: string;
  updated_at?: string;
}

// 文件夹树节点接口
interface FolderTreeNode extends Folder {
  children: FolderTreeNode[];
}

// 拖放事件数据
interface DropEventData {
  item_id: string;
  item_type: string;
  target_folder_id: string | null;
  source_data?: any;
}

// 创建文件夹数据
interface CreateFolderData {
  name: string;
  parent_id?: string | null;
  description?: string;
}
```

## 国际化支持

所有组件都支持通过 `labels` prop 自定义文本，方便集成到不同的国际化方案中：

```vue
<BaseFolderTree
  :labels="{
    searchPlaceholder: t('folder.search'),
    rootFolder: t('folder.root'),
    noFolders: t('folder.empty'),
    contextMenu: {
      open: t('folder.menu.open'),
      rename: t('folder.menu.rename'),
      moveTo: t('folder.menu.move'),
      delete: t('folder.menu.delete'),
    },
  }"
/>
```

## 拖放支持

组件内置了拖放支持，可以通过 `acceptDropTypes` 指定接受的拖放类型：

```vue
<!-- 只接受 'persona' 类型的拖放 -->
<BaseFolderTree
  :accept-drop-types="['persona']"
  @item-dropped="handleDrop"
/>

<!-- 拖放事件处理 -->
<script setup>
function handleDrop({ item_id, item_type, target_folder_id, source_data }) {
  if (item_type === 'persona') {
    // 移动 persona 到目标文件夹
    movePersonaToFolder(item_id, target_folder_id);
  }
}
</script>
```

## 与 Pinia Store 集成

如果你更喜欢使用 Pinia Store 管理状态，可以参考现有的 `personaStore.ts` 实现：

```typescript
// stores/myFolderStore.ts
import { defineStore } from 'pinia';
import type { FolderTreeNode, Folder } from '@/components/folder';

export const useMyFolderStore = defineStore('myFolder', {
  state: () => ({
    folderTree: [] as FolderTreeNode[],
    currentFolderId: null as string | null,
    currentFolders: [] as Folder[],
    // ...
  }),
  
  actions: {
    async loadFolderTree() {
      // ...
    },
    // ...
  },
});
```
