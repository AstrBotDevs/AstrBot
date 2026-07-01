/**
 * spcode_toolkit 工具的 mdi 图标常量。
 *
 * todo 工具演进:
 *   - v2.2.0:把 todo_list 拆为 4 个独立工具 (create / query / modify / clear)
 *   - v2.12:把 todo_modify 进一步拆为 add / update / delete 3 个独立工具
 * 现在共 6 个 todo_* 工具,各自分配了语义化图标:
 *   - todo_create :  mdi-format-list-checks   (新建清单)
 *   - todo_query  :  mdi-format-list-checks   (读取清单)
 *   - todo_add    :  mdi-plus-circle-outline  (追加 item)
 *   - todo_update :  mdi-pencil-outline       (更新 item)
 *   - todo_delete :  mdi-trash-can-outline    (删除 item)
 *   - todo_clear  :  mdi-format-list-checks   (清空整个 list)
 *
 * 旧条目 `todo_list` / `todo_modify` 保留以兼容老会话历史记录中的工具名。
 *
 * Author: ui_spcode_foundation
 * Date: 2026-06-07 (revised 2026-06-14, fixed 2026-06-18, refactored 2026-06-23)
 */
export const SPCODE_ICONS: Record<string, string> = {
    code_check: "mdi-shield-check-outline",
    code_format: "mdi-format-paint",
    code_index: "mdi-database-cog-outline",
    code_explore: "mdi-graph-outline",
    es_search: "mdi-file-search-outline",
    // 必须使用后端注册的全名(`main.py` 中 FileRemoveTool.name /
    // FileDiffTool.name),否则 SPCODE_TOOL_NAMES 集合里没有它们,
    // ToolResultView.isSpcodeTool 检查会失败,结果回退到
    // `<pre class="result-raw">` 原始 JSON,看不到样式化结果卡。
    astrbot_file_remove: "mdi-trash-can-outline",
    astrbot_file_compare: "mdi-vector-difference",
    // v2.12 拆分后的 6 个 todo 工具
    todo_create: "mdi-format-list-checks",
    todo_query: "mdi-format-list-checks",
    todo_add: "mdi-plus-circle-outline",
    todo_update: "mdi-pencil-outline",
    todo_delete: "mdi-trash-can-outline",
    todo_clear: "mdi-format-list-checks",
    // 兼容老历史(v2.12 之前的 modify、v2.2.0 之前的 list)
    todo_modify: "mdi-format-list-checks",
    todo_list: "mdi-format-list-checks",
};

/** 返回工具名对应的 mdi 图标；未知工具返回 mdi-wrench。 */
export function getSpcodeIcon(toolName: string): string {
    return SPCODE_ICONS[toolName] ?? "mdi-wrench";
}

/** spcode 工具的合法名称集合
 *  - v2.12+ 6 个 todo_* 工具(create / query / add / update / delete / clear)
 *  - legacy:todo_modify(v2.12 之前)、todo_list(v2.2.0 之前)
 */
export const SPCODE_TOOL_NAMES: ReadonlySet<string> = new Set(
    Object.keys(SPCODE_ICONS),
);
