/**
 * 通用文件夹管理 Composable
 * 
 * 提供文件夹管理的核心逻辑，可以被不同的业务模块复用
 */
import { ref, computed, reactive, type Ref, type ComputedRef } from 'vue';
import type {
  Folder,
  FolderTreeNode,
  FolderOperations,
  CreateFolderData,
  UpdateFolderData,
  BreadcrumbItem,
} from './types';

export interface UseFolderManagerOptions {
  // 文件夹操作实现
  operations: FolderOperations;
  
  // 根目录显示名称
  rootFolderName?: string;
  
  // 是否自动加载
  autoLoad?: boolean;
}

export interface UseFolderManagerReturn {
  // 状态
  folderTree: Ref<FolderTreeNode[]>;
  currentFolderId: Ref<string | null>;
  currentFolders: Ref<Folder[]>;
  breadcrumbPath: Ref<FolderTreeNode[]>;
  expandedFolderIds: Ref<string[]>;
  loading: Ref<boolean>;
  treeLoading: Ref<boolean>;
  
  // 计算属性
  currentFolderName: ComputedRef<string>;
  breadcrumbItems: ComputedRef<BreadcrumbItem[]>;
  
  // 方法
  loadFolderTree: () => Promise<void>;
  navigateToFolder: (folderId: string | null) => Promise<void>;
  refreshCurrentFolder: () => Promise<void>;
  
  createFolder: (data: CreateFolderData) => Promise<Folder>;
  updateFolder: (data: UpdateFolderData) => Promise<void>;
  deleteFolder: (folderId: string) => Promise<void>;
  moveFolder: (folderId: string, targetParentId: string | null) => Promise<void>;
  
  toggleFolderExpansion: (folderId: string) => void;
  setFolderExpansion: (folderId: string, expanded: boolean) => void;
  
  findFolderInTree: (folderId: string) => FolderTreeNode | null;
  findPathToFolder: (folderId: string) => FolderTreeNode[];
  
  filterTreeBySearch: (query: string) => FolderTreeNode[];
}

/**
 * 创建文件夹管理 composable
 */
export function useFolderManager(options: UseFolderManagerOptions): UseFolderManagerReturn {
  const { operations, rootFolderName = '根目录', autoLoad = false } = options;
  
  // 状态
  const folderTree = ref<FolderTreeNode[]>([]);
  const currentFolderId = ref<string | null>(null);
  const currentFolders = ref<Folder[]>([]);
  const breadcrumbPath = ref<FolderTreeNode[]>([]);
  const expandedFolderIds = ref<string[]>([]);
  const loading = ref(false);
  const treeLoading = ref(false);
  
  // 计算属性
  const currentFolderName = computed(() => {
    if (breadcrumbPath.value.length === 0) {
      return rootFolderName;
    }
    return breadcrumbPath.value[breadcrumbPath.value.length - 1]?.name || rootFolderName;
  });
  
  const breadcrumbItems = computed((): BreadcrumbItem[] => {
    const items: BreadcrumbItem[] = [
      {
        title: rootFolderName,
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
  
  // 内部方法
  const findPathToFolderInternal = (
    nodes: FolderTreeNode[],
    targetId: string,
    path: FolderTreeNode[] = []
  ): FolderTreeNode[] | null => {
    for (const node of nodes) {
      if (node.folder_id === targetId) {
        return [...path, node];
      }
      if (node.children && node.children.length > 0) {
        const result = findPathToFolderInternal(node.children, targetId, [...path, node]);
        if (result) return result;
      }
    }
    return null;
  };
  
  const updateBreadcrumb = (folderId: string | null): void => {
    if (folderId === null) {
      breadcrumbPath.value = [];
      return;
    }
    
    const path = findPathToFolderInternal(folderTree.value, folderId);
    breadcrumbPath.value = path || [];
  };
  
  // 公开方法
  const loadFolderTree = async (): Promise<void> => {
    treeLoading.value = true;
    try {
      folderTree.value = await operations.loadFolderTree();
    } finally {
      treeLoading.value = false;
    }
  };
  
  const navigateToFolder = async (folderId: string | null): Promise<void> => {
    loading.value = true;
    try {
      currentFolderId.value = folderId;
      currentFolders.value = await operations.loadSubFolders(folderId);
      updateBreadcrumb(folderId);
    } finally {
      loading.value = false;
    }
  };
  
  const refreshCurrentFolder = async (): Promise<void> => {
    await navigateToFolder(currentFolderId.value);
  };
  
  const createFolder = async (data: CreateFolderData): Promise<Folder> => {
    const folder = await operations.createFolder({
      ...data,
      parent_id: data.parent_id ?? currentFolderId.value,
    });
    
    await Promise.all([refreshCurrentFolder(), loadFolderTree()]);
    
    return folder;
  };
  
  const updateFolder = async (data: UpdateFolderData): Promise<void> => {
    await operations.updateFolder(data);
    await Promise.all([refreshCurrentFolder(), loadFolderTree()]);
  };
  
  const deleteFolder = async (folderId: string): Promise<void> => {
    await operations.deleteFolder(folderId);
    await Promise.all([refreshCurrentFolder(), loadFolderTree()]);
  };
  
  const moveFolder = async (folderId: string, targetParentId: string | null): Promise<void> => {
    if (operations.moveFolder) {
      await operations.moveFolder(folderId, targetParentId);
    } else {
      // 如果没有专门的移动方法，使用更新方法
      await operations.updateFolder({
        folder_id: folderId,
        parent_id: targetParentId,
      });
    }
    await Promise.all([refreshCurrentFolder(), loadFolderTree()]);
  };
  
  const toggleFolderExpansion = (folderId: string): void => {
    const index = expandedFolderIds.value.indexOf(folderId);
    if (index === -1) {
      expandedFolderIds.value.push(folderId);
    } else {
      expandedFolderIds.value.splice(index, 1);
    }
  };
  
  const setFolderExpansion = (folderId: string, expanded: boolean): void => {
    const index = expandedFolderIds.value.indexOf(folderId);
    if (expanded && index === -1) {
      expandedFolderIds.value.push(folderId);
    } else if (!expanded && index !== -1) {
      expandedFolderIds.value.splice(index, 1);
    }
  };
  
  const findFolderInTree = (folderId: string): FolderTreeNode | null => {
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
    return findNode(folderTree.value);
  };
  
  const findPathToFolder = (folderId: string): FolderTreeNode[] => {
    return findPathToFolderInternal(folderTree.value, folderId) || [];
  };
  
  const filterTreeBySearch = (query: string): FolderTreeNode[] => {
    if (!query) return folderTree.value;
    
    const lowerQuery = query.toLowerCase();
    
    const filterNodes = (nodes: FolderTreeNode[]): FolderTreeNode[] => {
      return nodes
        .filter((node) => {
          const matches = node.name.toLowerCase().includes(lowerQuery);
          const childMatches = filterNodes(node.children || []);
          return matches || childMatches.length > 0;
        })
        .map((node) => ({
          ...node,
          children: filterNodes(node.children || []),
        }));
    };
    
    return filterNodes(folderTree.value);
  };
  
  // 自动加载
  if (autoLoad) {
    loadFolderTree();
    navigateToFolder(null);
  }
  
  return {
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
  };
}

/**
 * 收集文件夹及其所有子文件夹的 ID
 * 用于禁用移动对话框中不能选择的目标
 */
export function collectFolderAndChildrenIds(
  folderTree: FolderTreeNode[],
  folderId: string
): string[] {
  const ids: string[] = [folderId];
  
  const collectChildIds = (nodes: FolderTreeNode[]): boolean => {
    for (const node of nodes) {
      if (node.folder_id === folderId) {
        const collectAllChildren = (children: FolderTreeNode[]) => {
          for (const child of children) {
            ids.push(child.folder_id);
            if (child.children) {
              collectAllChildren(child.children);
            }
          }
        };
        if (node.children) {
          collectAllChildren(node.children);
        }
        return true;
      }
      if (node.children && collectChildIds(node.children)) {
        return true;
      }
    }
    return false;
  };
  
  collectChildIds(folderTree);
  return ids;
}

export default useFolderManager;
