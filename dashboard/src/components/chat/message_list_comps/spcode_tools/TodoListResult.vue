<template>
    <div class="todo-list-result">
        <!-- A) create -->
        <template v-if="actionType === 'create'">
            <div class="status-row success">
                <v-icon size="14">mdi-check-circle</v-icon>
                <span class="status-text">List created: {{ data.list_title || args?.title }}</span>
                <span class="count-chip">{{ data.item_count }} items</span>
            </div>
            <div v-if="data.previous_item_count > 0" class="overwrite-note">
                ⚠ Overwrote previous list ({{ data.previous_item_count }} items)
            </div>
        </template>

        <!-- B) add / update -->
        <template v-else-if="actionType === 'add' || actionType === 'update'">
            <div class="status-row success">
                <v-icon size="14">mdi-check-circle</v-icon>
                <span class="status-text">
                    Item #{{ data.item_id }}
                    {{ actionType === 'add' ? 'added' : 'updated' }}
                </span>
                <span v-if="data.item" class="count-chip">
                    {{ data.item.status || 'pending' }}
                </span>
            </div>
            <pre v-if="data.item" class="item-detail">{{ formatItem(data.item) }}</pre>
        </template>

        <!-- C) delete / clear -->
        <template v-else-if="actionType === 'delete' || actionType === 'clear'">
            <div class="status-row success">
                <v-icon size="14">mdi-check-circle</v-icon>
                <span class="status-text">
                    {{ data.deleted === 'list' ? 'List cleared' : `Deleted ${data.deleted} item(s)` }}
                </span>
                <span v-if="data.item_count !== undefined" class="count-chip">
                    {{ data.item_count }} remaining
                </span>
            </div>
        </template>

        <!-- E) 失败 -->
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

        <!-- 完整列表视图:create / add / update / query 后端都会回传 data.list -->
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

const props = defineProps<{ data: any; args?: any }>();

/** 根据后端返回 data 的结构推断 action 类型。
 *
 * 优先级顺序很重要：create/add/update 成功后后端会回传完整 list + stats，
 * 因此必须先用 create/add/update 各自特有的字段（list_title / item_id /
 * deleted）先匹配，query 兜底匹配 data.list.items，否则会被错归为 query。
 */
const actionType = computed<string>(() => {
    if (!props.data) return "error";
    if (props.data.list_title !== undefined) return "create";
    if (props.data.deleted === "list") return "clear";
    if (props.data.deleted !== undefined) return "delete";
    if (props.data.item_id !== undefined) {
        return props.args?.item ? "add" : "update";
    }
    if (props.data.list && props.data.list.items) return "query";
    return "error";
});

/** 是否展示完整列表视图（进度条 + items + 统计）。
 *
 * 包含完整列表的 action：
 *   - create / add / update：后端 create/add/update 总会附带 data.list
 *   - query：后端 query 总是返回 data.list
 *   - delete（删单条）：后端 delete(item_id>0) 附带 data.list（删整个 list 的
 *     clear() 不附带，因此仍然不会展示）
 * 不展示的 action：clear（整个 list 已删）、error。
 */
const showFullList = computed<boolean>(() => {
    if (!props.data?.list?.items) return false;
    const t = actionType.value;
    return t === "create"
        || t === "add"
        || t === "update"
        || t === "query"
        || t === "delete";
});

function formatItem(it: any): string {
    return `(${it.id}) [${it.status}] ${it.title}${it.notes ? '\n   notes: ' + it.notes : ''}`;
}
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
