/**
 * spcode_toolkit 7 个工具的 mdi 图标常量。
 * Author: ui_spcode_foundation
 * Date: 2026-06-07
 */
export const SPCODE_ICONS: Record<string, string> = {
    code_check: "mdi-shield-check-outline",
    code_index: "mdi-database-cog-outline",
    code_explore: "mdi-graph-outline",
    es_search: "mdi-file-search-outline",
    file_remove: "mdi-trash-can-outline",
    file_diff: "mdi-vector-difference",
    todo_list: "mdi-format-list-checks",
};

/** 返回工具名对应的 mdi 图标；未知工具返回 mdi-wrench。 */
export function getSpcodeIcon(toolName: string): string {
    return SPCODE_ICONS[toolName] ?? "mdi-wrench";
}

/** 7 个工具的合法名称集合。 */
export const SPCODE_TOOL_NAMES: ReadonlySet<string> = new Set(
    Object.keys(SPCODE_ICONS),
);
