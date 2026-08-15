/**
 * 指令管理模块 - 类型定义
 */

import type { CommandItem } from '@/domain/commands';

/** 指令摘要统计 */
export interface CommandSummary {
  disabled: number;
  conflicts: number;
}

/** 工具摘要统计 */
export interface ToolSummary {
  total: number;
  active: number;
  inactive: number;
}

/** 过滤器状态 */
export interface FilterState {
  searchQuery: string;
  pluginFilter: string;
  actionFilter: string;
  statusFilter: string;
  typeFilter: string;
  showSystemPlugins: boolean;
}

/** 重命名对话框状态 */
export interface RenameDialogState {
  show: boolean;
  command: CommandItem | null;
  newName: string;
  aliases: string[];
  loading: boolean;
}

/** 详情对话框状态 */
export interface DetailsDialogState {
  show: boolean;
  command: CommandItem | null;
}

/** Toast 消息状态 */
export interface SnackbarState {
  show: boolean;
  message: string;
  color: string;
}

/** 类型信息展示 */
export interface TypeInfo {
  text: string;
  color: string;
  icon: string;
}

/** 状态信息展示 */
export interface StatusInfo {
  text: string;
  color: string;
  variant: 'flat' | 'outlined' | 'text' | 'elevated' | 'tonal' | 'plain';
}
