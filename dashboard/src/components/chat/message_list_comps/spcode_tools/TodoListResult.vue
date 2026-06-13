<template>
    <div class="todo-list-result">
        <!--
          v2.2.0: 旧 todo_list 工具被拆为 4 个独立工具。
          本组件按 (toolName, args.mode, data 字段) 联合推断渲染分支。
          旧 todo_list 工具的"data.item_id" / "data.item" 字段路径仍保留,只
          是当 toolName 不是 todo_list 时,优先级让位给新工具的字段。
        -->

        <!-- A) todo_create / 旧 list(创建) -->
        <template v-if="actionType === 'create'">
            <div class="status-row success">
                <v-icon size="14">mdi-check-circle</v-icon>
                <span class="status-text">
                    List created: {{ data.list_title || args?.title || 'Untitled' }}
                </span>
                <span class="count-chip">{{ data.item_count }} items</span>
            </div>
            <div v-if="data.previous_item_count > 0" class="overwrite-note">
                ⚠ Overwrote previous list ({{ data.previous_item_count }} items)
            </div>
        </template>

        <!-- B) todo_modify(mode='add') / 旧 add -->
        <template v-else-if="actionType === 'add'">
            <div class="status-row success">
                <v-icon size="14">mdi-check-circle</v-icon>
                <span class="status-text">
                    {{ formatItemIds(data.item_ids, 'added') }}
                </span>
                <span
                    v-if="firstItem && firstItem.status"
                    class="count-chip"
                >
                    {{ firstItem.status }}
                </span>
            </div>
            <pre
                v-if="data.items && data.items.length"
                class="item-detail"
            >{{ formatItems(data.items) }}</pre>
        </template>

        <!-- C) todo_modify(mode='update') / 旧 update -->
        <template v-else-if="actionType === 'update'">
            <div class="status-row success">
                <v-icon size="14">mdi-check-circle</v-icon>
                <span class="status-text">
                    {{ formatItemIds(data.item_ids, 'updated') }}
                </span>
                <span
                    v-if="firstItem && firstItem.status"
                    class="count-chip"
                >
                    {{ firstItem.status }}
                </span>
            </div>
            <pre
                v-if="data.items && data.items.length"
                class="item-detail"
            >{{ formatItems(data.items) }}</pre>
        </template>

        <!-- D) todo_modify(mode='delete') / 旧 delete -->
        <template v-else-if="actionType === 'delete'">
            <div class="status-row success">
                <v-icon size="14">mdi-check-circle</v-icon>
                <span class="status-text">
                    Deleted {{ data.deleted }} item(s)
                    <template v-if="data.item_ids && data.item_ids.length">
                        · #{{ data.item_ids.join(', #') }}
                    </template>
                </span>
                <span
                    v-if="data.item_count !== undefined"
                    class="count-chip"
                >
                    {{ data.item_count }} remaining
                </span>
            </div>
        </template>

        <!-- E) todo_clear / 旧 clear(整 list 删) -->
        <template v-else-if="actionType === 'clear'">
            <div class="status-row success">
                <v-icon size="14">mdi-check-circle</v-icon>
                <span class="status-text">List cleared</span>
            </div>
        </template>

        <!-- F) todo_query / 旧 query → 只展示列表,无状态条 -->
        <template v-else-if="actionType === 'query'">
            <div v-if="data.list" class="query-header">
                <v-icon size="14">mdi-format-list-checks</v-icon>
                <span class="query-title">
                    {{ data.list.title || 'Todo List' }}
                </span>
            </div>
        </template>

        <!-- G) 失败 / proposal -->
        <template v-else-if="actionType === 'error'">
            <div class="status-row error">
                <v-icon size="14">mdi-alert-circle</v-icon>
                <span class="status-text">{{ data.error || 'Failed' }}</span>
            </div>
            <div v-if="data.proposal" class="proposal-block">
                <div class="proposal-label">
                    <v-icon size="12">mdi-lightbulb-outline</v-icon>
                    Suggestion
                </div>
                <div class="proposal-text">{{ data.proposal }}</div>
            </div>
        </template>

        <!--
          完整列表视图:
            - create / add / update / query :  后端总会回传 data.list
            - delete(单条)                  :  删单条后 list 还在,后端会回传
            - clear / error                 :  不展示
        -->
        <div v-if="showFullList" class="full-list-section">
            <TodoListPanel
                :list="data.list"
                :stats="data.stats"
                :attention-items="data.attention_items"
            />
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import TodoListPanel from "./TodoListPanel.vue";

/**
 * 渲染 todo_create / todo_query / todo_modify / todo_clear / (legacy)todo_list
 * 5 个工具的返回结果。父组件 (SpcodeToolResultView) 负责按 toolName 分发。
 *
 * actionType 推断优先级:
 *   1) 工具名(新工具最稳)         : toolName 决定
 *   2) args.mode (todo_modify 拆) : 进一步区分 add/update/delete
 *   3) data 字段形状(老 todo_list): 兜底,保持历史会话可读
 *
 * @author elecvoid243 / 2026-06-14
 */

type ActionType =
    | "create"
    | "query"
    | "add"
    | "update"
    | "delete"
    | "clear"
    | "error";

const props = defineProps<{
    data: any;
    args?: any;
    /** 来自 SpcodeToolResultView 透传的工具名(可省略,省略时走 data 兜底) */
    toolName?: string;
}>();

const actionType = computed<ActionType>(() => {
    if (!props.data) return "error";
    const tn = props.toolName;
    const mode = props.args?.mode;

    // 1) 新工具:按 toolName 优先
    if (tn === "todo_create") return "create";
    if (tn === "todo_query") return "query";
    if (tn === "todo_clear") return "clear";
    if (tn === "todo_modify") {
        // add / update / delete 通过 args.mode 区分
        // (后端在 modify() 中也是用同一 args.mode 分发的)
        if (mode === "add" || mode === "update" || mode === "delete") return mode;
        // 兜底:从 data 字段反推
        if (props.data.deleted !== undefined) return "delete";
        // args.item 列表存在 → add(批量)
        if (Array.isArray(props.args?.items)) return "add";
        return "update";
    }

    // 2) 旧 todo_list:按 data 字段形状推断
    //    顺序很重要 — create/add/update 都会附带 list+stats,必须先用各自特有
    //    字段先匹配,query 兜底匹配 data.list.items。
    if (props.data.list_title !== undefined) return "create";
    if (props.data.deleted === "list") return "clear";
    if (props.data.deleted !== undefined) return "delete";
    if (props.data.item_id !== undefined) {
        return props.args?.item ? "add" : "update";
    }
    if (props.data.list && props.data.list.items) return "query";

    return "error";
});

/** 是否展示完整列表视图(进度条 + items + 统计)。 */
const showFullList = computed<boolean>(() => {
    if (!props.data?.list?.items) return false;
    const t = actionType.value;
    return (
        t === "create"
        || t === "add"
        || t === "update"
        || t === "query"
        || t === "delete"
    );
});

/** 渲染 item_ids 列表成 "Item #1, #2, #3 added" 这种紧凑文案。 */
function formatItemIds(ids: any, verb: string): string {
    if (Array.isArray(ids) && ids.length) {
        const label = ids.length === 1 ? "Item" : "Items";
        return `${label} #${ids.join(", #")} ${verb}`;
    }
    if (typeof ids === "number") return `Item #${ids} ${verb}`;
    return `${verb}`;
}

/** 渲染单个 item 的简洁文本(只用于单条展示场景)。 */
function formatItem(it: any): string {
    return `(${it.id}) [${it.status}] ${it.title}${it.notes ? "\n   notes: " + it.notes : ""}`;
}

/** 渲染多条 item 的紧凑列表。 */
function formatItems(items: any[]): string {
    return items.map((it) => formatItem(it)).join("\n");
}

const firstItem = computed<any>(() => {
    if (Array.isArray(props.data?.items) && props.data.items.length) {
        return props.data.items[0];
    }
    return null;
});
</script>

<style scoped>
.todo-list-result {
    font-size: 12px;
    /* 确保 block 元素填满父容器，避免上层 flex 收缩导致内容变窄 */
    width: 100%;
    box-sizing: border-box;
}
.full-list-section {
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px dashed rgba(var(--v-theme-on-surface), 0.08);
    width: 100%;
    box-sizing: border-box;
}
.status-row {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 8px; border-radius: 4px; font-size: 11.5px;
}
.status-row.success { background: rgba(70, 200, 70, 0.08); color: #2da44e; }
.status-row.error   { background: rgba(255, 100, 100, 0.08); color: #cf222e; }
.status-text { font-weight: 500; }
.count-chip {
    margin-left: auto;
    padding: 1px 6px; border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), 0.06);
    font-family: ui-monospace, monospace; font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.6);
}
.overwrite-note {
    margin-top: 4px; padding: 4px 8px; border-radius: 4px;
    background: rgba(255, 180, 0, 0.08); color: #b58400;
    font-size: 11px;
}
.item-detail {
    margin-top: 4px; padding: 4px 8px; border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.04);
    font-family: ui-monospace, monospace; font-size: 11px;
    white-space: pre-wrap;
}
.query-header {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 8px; border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.04);
    font-size: 12px; font-weight: 600;
    color: rgba(var(--v-theme-on-surface), 0.75);
}
.query-title {
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    min-width: 0;
}

/* Proposal */
.proposal-block {
    margin-top: 6px; padding: 6px 10px; border-radius: 4px;
    background: rgba(255, 180, 0, 0.06);
    border-left: 2px solid #b58400;
}
.proposal-label {
    display: flex; align-items: center; gap: 4px;
    font-size: 10.5px; font-weight: 600;
    color: #b58400; text-transform: uppercase; letter-spacing: 0.3px;
    margin-bottom: 3px;
}
.proposal-text {
    font-size: 11.5px; line-height: 1.5;
    color: rgba(var(--v-theme-on-surface), 0.8);
}
</style>
