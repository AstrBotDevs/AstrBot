/**
 * 插件置顶偏好同步逻辑。
 *
 * 该模块不依赖 Vue，只负责处理本地 localStorage 列表与后端列表的归一化与冲突决策，
 * 便于在 node --test 中单元测试。
 */

import { normalizePinnedExtensions } from "./extensionPreferenceStorage.mjs";

export { normalizePinnedExtensions };

/**
 * 根据后端列表与本地列表决定最终应展示的置顶顺序。
 *
 * 规则：
 * - 后端已有偏好记录时，以后端为准，即使列表为空也不迁移；
 * - 后端没有偏好记录且本地有旧列表时，使用本地列表，并触发一次性迁移；
 * - 两者都为空时，结果为空数组，不迁移。
 *
 * @param {Object} options
 * @param {string[]} options.localNames 从 localStorage 读取的本地列表（已归一化）。
 * @param {string[]} options.remoteNames 从后端拉取的列表（已归一化）。
 * @param {boolean} [options.preferenceExists] 后端是否存在置顶偏好记录。
 * @returns {{ names: string[]; shouldMigrate: boolean; migrateNames?: string[] }}
 */
export const resolvePinnedExtensionNames = ({
  localNames,
  remoteNames,
  preferenceExists,
}) => {
  const normalizedRemote = normalizePinnedExtensions(remoteNames);
  const normalizedLocal = normalizePinnedExtensions(localNames);

  if (preferenceExists === true || normalizedRemote.length > 0) {
    return { names: normalizedRemote, shouldMigrate: false };
  }

  if (preferenceExists === false && normalizedLocal.length > 0) {
    return {
      names: normalizedLocal,
      shouldMigrate: true,
      migrateNames: normalizedLocal,
    };
  }

  return { names: [], shouldMigrate: false };
};
