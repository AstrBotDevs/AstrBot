/**
 * spcode_toolkit 工具的 mdi 图标常量。
 *
 * v2.2.0 起,原来的 todo_list 工具被拆分为 4 个独立工具:
 *   - todo_create :  新建一个 todo list
 *   - todo_query  :  读取当前 todo list
 *   - todo_modify :  add / update / delete 三合一
 *   - todo_clear  :  删整个 list(文件 unlink)
 * 它们共享同一个 mdi 图标,统一在 UI 上以"列表"语义呈现。
 *
 * 旧条目 `todo_list` 保留以兼容老会话历史记录中的工具名。
 *
 * Author: ui_spcode_foundation
 * Date: 2026-06-07 (revised 2026-06-14, fixed 2026-06-18)
 */
export const SPCODE_ICONS: Record<string, string> = {
    code_check: "mdi-shield-check-outline",
    code_index: "mdi-database-cog-outline",
    code_explore: "mdi-graph-outline",
    es_search: "mdi-file-search-outline",
    // 必须使用后端注册的全名(`main.py` 中 FileRemoveTool.name /
    // FileDiffTool.name),否则 SPCODE_TOOL_NAMES 集合里没有它们,
    // ToolResultView.isSpcodeTool 检查会失败,结果回退到
    // `<pre class="result-raw">` 原始 JSON,看不到样式化结果卡。
    astrbot_file_remove: "mdi-trash-can-outline",
    astrbot_file_compare: "mdi-vector-difference",
    // 拆分的 4 个 todo 工具共享同一图标
    todo_create: "mdi-format-list-checks",
    todo_query: "mdi-format-list-checks",
    todo_modify: "mdi-format-list-checks",
    todo_clear: "mdi-format-list-checks",
    // 兼容老历史
    todo_list: "mdi-format-list-checks",
};

/** 返回工具名对应的 mdi 图标；未知工具返回 mdi-wrench。 */
export function getSpcodeIcon(toolName: string): string {
    return SPCODE_ICONS[toolName] ?? "mdi-wrench";
}

/** spcode 工具的合法名称集合(含拆分后的 4 个 todo_* + 旧 todo_list 兼容项)。 */
export const SPCODE_TOOL_NAMES: ReadonlySet<string> = new Set(
    Object.keys(SPCODE_ICONS),
);
