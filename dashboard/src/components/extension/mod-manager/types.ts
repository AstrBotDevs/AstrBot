export interface ApiResponse<T> {
  status: 'ok' | 'error' | string
  message?: string | null
  data: T
}

// 插件 Handler 信息（来自 /api/plugin/get 的 handlers 数组）
// 参考 astrbot/dashboard/routes/plugin.py:get_plugin_handlers_info()
export interface PluginHandlerInfo {
  event_type: string
  event_type_h: string
  handler_full_name: string
  handler_name: string
  desc: string
  cmd?: string
  type?: string
  sub_command?: string
  has_admin?: boolean
}

// 插件摘要信息（来自 /api/plugin/get）
// 参考 astrbot/dashboard/routes/plugin.py:get_plugins()
export interface PluginSummary {
  name: string
  display_name?: string | null
  repo: string
  author: string
  desc: string
  version: string
  reserved: boolean
  activated: boolean

  // 后端字段（注意拼写错误）
  online_vesion?: string

  // 前端计算写入
  online_version?: string
  has_update?: boolean

  handlers: PluginHandlerInfo[]
  logo?: string | null
}

// 命令冲突组（来自 /api/commands/conflicts）
// 参考 astrbot/core/star/command_management.py:list_command_conflicts()
export interface ConflictHandler {
  handler_full_name: string
  plugin: string
  current_name: string
}

export interface CommandConflictGroup {
  conflict_key: string
  handlers: ConflictHandler[]
}

// 冲突统计（用于左侧列表徽标）
export interface ConflictStats {
  byPlugin: Map<string, { count: number; keys: Set<string> }>
  total: number
}

// 配置缓存条目
export interface PluginConfigCacheEntry {
  metadata: Record<string, any>
  config: Record<string, any>
  fetchedAt: number
  inFlight?: Promise<void>
}

// 配置缓存 API
export interface PluginConfigCacheApi {
  get(pluginName: string): PluginConfigCacheEntry | undefined
  prefetch(pluginName: string): Promise<void>
  getOrFetch(pluginName: string): Promise<PluginConfigCacheEntry>
  updateConfig(pluginName: string, config: Record<string, any>): Promise<void>
  invalidate(pluginName: string): void
  isStale(pluginName: string): boolean
}

// 视图模式
export type InstalledViewMode = 'mod' | 'legacy'

// 插件面板 Tab
export type PluginPanelTab = 'info' | 'config' | 'behavior' | 'overview' | 'changelog'