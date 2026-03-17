/**
 * 通用文件夹管理组件库
 * 
 * 提供可复用的文件夹管理 UI 组件，适用于各种需要文件夹组织功能的场景
 * 如：persona 管理、模板管理、知识库管理等
 * 
 * 使用示例:
 * ```vue
 * <script setup>
 * import {
 *   BaseFolderTree,
 *   BaseFolderCard,
 *   BaseFolderBreadcrumb,
 *   BaseCreateFolderDialog,
 *   BaseMoveToFolderDialog,
 *   useFolderManager
 * } from '@/components/folder';
 * 
 * const folderManager = useFolderManager({
 *   operations: {
 *     loadFolderTree: async () => { ... },
 *     loadSubFolders: async (parentId) => { ... },
 *     createFolder: async (data) => { ... },
 *     updateFolder: async (data) => { ... },
 *     deleteFolder: async (folderId) => { ... },
 *   }
 * });
 * </script>
 * ```
 */

// 类型导出
export * from './types';

// Composable 导出
export { useFolderManager, collectFolderAndChildrenIds } from './useFolderManager';
export type { UseFolderManagerOptions, UseFolderManagerReturn } from './useFolderManager';

// 组件导出
export { default as BaseFolderTree } from './BaseFolderTree.vue';
export { default as BaseFolderTreeNode } from './BaseFolderTreeNode.vue';
export { default as BaseFolderCard } from './BaseFolderCard.vue';
export { default as BaseFolderBreadcrumb } from './BaseFolderBreadcrumb.vue';
export { default as BaseCreateFolderDialog } from './BaseCreateFolderDialog.vue';
export { default as BaseMoveToFolderDialog } from './BaseMoveToFolderDialog.vue';
export { default as BaseMoveTargetNode } from './BaseMoveTargetNode.vue';
