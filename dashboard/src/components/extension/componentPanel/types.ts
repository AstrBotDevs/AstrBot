/**
 * 指令管理模块 - 类型定义
 */

/** 指令项接口 */
export interface CommandItem {
  handler_full_name: string;
  handler_name: string;
  plugin: string;
  plugin_display_name: string | null;
  module_path: string;
  description: string;
  type: CommandType;
  parent_signature: string;
  parent_group_handler: string;
  original_command: string;
  current_fragment: string;
  effective_command: string;
  aliases: string[];
  permission: PermissionType;
  enabled: boolean;
  is_group: boolean;
  has_conflict: boolean;
  reserved: boolean;
  priority?: number;
  sub_commands: CommandItem[];
}

/** 指令类型 */
export type CommandType = 'command' | 'group' | 'sub_command';

/** 权限类型 */
export type PermissionType = 'admin' | 'everyone' | 'member';

/** 指令摘要统计 */
export interface CommandSummary {
  disabled: number;
  conflicts: number;
}

/** 过滤器状态 */
export interface FilterState {
  searchQuery: string;
  pluginFilter: string;
  permissionFilter: string;
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

/** MCP/函数工具参数定义 */
export interface ToolParameter {
  type?: string;
  description?: string;
}

/** MCP/函数工具对象 */
export interface ToolItem {
  name: string;
  description: string;
  active: boolean;
  parameters?: {
    properties?: Record<string, ToolParameter>;
  };
  origin?: string;
  origin_name?: string;
}

