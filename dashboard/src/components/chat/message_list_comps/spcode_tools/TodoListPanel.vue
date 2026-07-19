<template>
    <div class="todo-list-panel">
        <!-- 进度条 -->
        <div class="progress-bar">
            <div
                class="progress-segment done"
                :style="{ width: progressWidths.done }"
                :title="`${stats?.done || 0} done`"
            ></div>
            <div
                class="progress-segment in-progress"
                :style="{ width: progressWidths.inProgress }"
                :title="`${stats?.in_progress || 0} in progress`"
            ></div>
            <div
                class="progress-segment pending"
                :style="{ width: progressWidths.pending }"
                :title="`${stats?.pending || 0} pending`"
            ></div>
            <div
                class="progress-segment cancelled"
                :style="{ width: progressWidths.cancelled }"
                :title="`${stats?.cancelled || 0} cancelled`"
            ></div>
        </div>

        <!-- 标题 -->
        <div class="list-header">
            <v-icon size="14">mdi-format-list-checks</v-icon>
            <span class="list-title">{{ list?.title || 'Todo List' }}</span>
        </div>

        <!-- 批量折叠 / 展开工具栏(collapsible 模式才有意义) -->
        <div v-if="collapsible" class="bulk-toggle-row">
            <button
                type="button"
                class="bulk-toggle-btn"
                :disabled="!hasExpandableItems"
                @click="expandAll"
            >
                <v-icon size="12">mdi-unfold-more-horizontal</v-icon>
                <span>Expand all</span>
            </button>
            <button
                type="button"
                class="bulk-toggle-btn"
                :disabled="!hasExpandableItems"
                @click="collapseAll"
            >
                <v-icon size="12">mdi-unfold-less-horizontal</v-icon>
                <span>Collapse all</span>
            </button>
        </div>

        <!-- Items -->
        <div class="items-list">
            <div
                v-for="item in list?.items || []"
                :key="item.id"
                class="todo-item"
                :class="[
                    'status-' + item.status,
                    { 'has-notes': item.notes, 'is-clickable': collapsible && hasNotes(item) },
                ]"
                @click="collapsible && hasNotes(item) ? toggle(item.id) : null"
            >
                <v-icon
                    v-if="collapsible"
                    size="12"
                    class="item-chevron"
                    :class="{ 'is-expanded': isExpanded(item.id) }"
                >
                    mdi-chevron-right
                </v-icon>
                <v-icon
                    size="13"
                    class="item-check"
                >
                    {{ statusIcon(item.status) }}
                </v-icon>
                <span class="item-id">({{ item.id }})</span>
                <span class="item-title">{{ item.title }}</span>
                <v-icon
                    v-if="item.attention"
                    size="11"
                    class="attention-icon"
                    title="Needs attention"
                >
                    mdi-alert-circle
                </v-icon>
                <span
                    v-if="item.notes && showNotes(item)"
                    class="item-notes"
                >{{ item.notes }}</span>
            </div>
        </div>

        <!-- 底部统计 -->
        <div class="stats-footer">
            {{ stats?.done || 0 }}/{{ stats?.effective_total || 0 }} complete
            ({{ stats?.progress_pct || 0 }}%)
            <template v-if="stats?.in_progress">
                · {{ stats.in_progress }} in progress
            </template>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";

/**
 * TodoListPanel — 复用组件：渲染 todo_list 工具回传的完整列表视图（进度条 + items + 统计）。
 *
 * 原实现在 TodoListResult.vue 中,因侧边栏也需要同一份视图,故抽离为独立组件。
 * 接受的是已经剥离 envelope 后的 {list, stats, attention_items},由调用方保证。
 *
 * collapsible: 侧边栏等"实时监控"场景下,默认折叠每条 item,只露出状态/标题/ID,
 * 点击行(或 chevron)展开 notes。配合上方的 Expand all / Collapse all
 * 按钮可批量切换。TodoListResult(工具结果回显)继续走 false,行为不变。
 */
const props = withDefaults(
    defineProps<{
        list: any;
        stats: any;
        attentionItems?: number[];
        collapsible?: boolean;
    }>(),
    {
        attentionItems: () => [],
        collapsible: false,
    },
);

/** 已展开的 item id 集合。仅在 collapsible=true 时使用。 */
const expandedIds = ref<Set<string | number>>(new Set());

/** 切到新会话/新 list 时清空展开状态,避免过期 id 残留。 */
watch(
    () => props.list,
    () => {
        expandedIds.value = new Set();
    },
);

/** 单条 item 的 notes 是否存在(决定是否可折叠,以及是否显示 chevron)。 */
function hasNotes(item: any): boolean {
    return Boolean(item && item.notes);
}

function isExpanded(id: string | number): boolean {
    return expandedIds.value.has(id);
}

function toggle(id: string | number): void {
    // 复制后再 set,避免直接 mutate ref 内部值
    const next = new Set(expandedIds.value);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    expandedIds.value = next;
}

/** collapsible 模式下 notes 才会显示;否则维持旧行为(总显示)。 */
function showNotes(item: any): boolean {
    return !props.collapsible || isExpanded(item.id);
}

const expandableItems = computed(() =>
    (props.list?.items || []).filter((it: any) => hasNotes(it)),
);
const hasExpandableItems = computed(() => expandableItems.value.length > 0);

function expandAll(): void {
    expandedIds.value = new Set(expandableItems.value.map((it: any) => it.id));
}

function collapseAll(): void {
    expandedIds.value = new Set();
}

function statusIcon(s: string): string {
    if (s === "done") return "mdi-check-circle";
    if (s === "in_progress") return "mdi-progress-clock";
    if (s === "cancelled") return "mdi-close-circle";
    return "mdi-circle-outline";
}

/** 把状态计数换算成进度条 segment 的宽度百分比（0%–100%）。 */
function pctWidth(count: number | undefined, total: number | undefined): string {
    if (!count || count <= 0 || !total || total <= 0) return "0%";
    const pct = (count / total) * 100;
    // 浮点累加可能让 4 段总和略超 100%,clamp 一下避免溢出
    return `${Math.min(pct, 100)}%`;
}

const progressWidths = computed(() => {
    const stats = props.stats;
    if (!stats) {
        return { done: "0%", inProgress: "0%", pending: "0%", cancelled: "0%" };
    }
    const total = stats.total ?? 0;
    return {
        done: pctWidth(stats.done, total),
        inProgress: pctWidth(stats.in_progress, total),
        pending: pctWidth(stats.pending, total),
        cancelled: pctWidth(stats.cancelled, total),
    };
});
</script>

<style scoped>
.todo-list-panel {
    font-size: 12px;
    width: 100%;
    box-sizing: border-box;
}

/* Progress bar */
.progress-bar {
    display: flex;
    height: 6px;
    border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), 0.06);
    overflow: hidden;
    margin-bottom: 8px;
    width: 100%;
    box-sizing: border-box;
}
.progress-segment {
    transition: width 0.3s ease;
    min-width: 0;
    flex-shrink: 1;
}
.progress-segment.done { background: #2da44e; }
.progress-segment.in-progress { background: #b58400; }
.progress-segment.pending { background: rgba(0, 100, 200, 0.4); }
.progress-segment.cancelled { background: rgba(var(--v-theme-on-surface), 0.2); }

/* List */
.list-header {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 4px 0 6px;
    font-size: 12px;
    font-weight: 600;
    color: rgba(var(--v-theme-on-surface), 0.8);
}
.items-list {
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.todo-item {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 6px;
    padding: 4px 8px;
    border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.03);
    font-size: 11.5px;
    user-select: none;
}
.todo-item.is-clickable {
    cursor: pointer;
    transition: background 0.12s ease;
}
.todo-item.is-clickable:hover {
    background: rgba(var(--v-theme-on-surface), 0.06);
}

/* 批量展开/折叠工具栏 */
.bulk-toggle-row {
    display: flex;
    justify-content: flex-end;
    gap: 6px;
    margin: 2px 0 6px;
}
.bulk-toggle-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    font-size: 11px;
    line-height: 1.4;
    color: rgba(var(--v-theme-on-surface), 0.65);
    background: transparent;
    border: 1px solid rgba(var(--v-border-color), 0.16);
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.bulk-toggle-btn:hover:not(:disabled) {
    background: rgba(var(--v-theme-on-surface), 0.06);
    color: rgba(var(--v-theme-on-surface), 0.85);
    border-color: rgba(var(--v-border-color), 0.32);
}
.bulk-toggle-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
}

/* Chevron 旋转 */
.item-chevron {
    color: rgba(var(--v-theme-on-surface), 0.4);
    transition: transform 0.18s ease;
    flex-shrink: 0;
}
.item-chevron.is-expanded {
    transform: rotate(90deg);
    color: rgba(var(--v-theme-on-surface), 0.7);
}
.status-done .item-check { color: #2da44e; }
.status-in_progress .item-check { color: #b58400; }
.status-cancelled .item-check { color: rgba(var(--v-theme-on-surface), 0.3); }
.status-cancelled .item-title {
    text-decoration: line-through;
    opacity: 0.6;
}
.status-pending .item-check { color: rgba(var(--v-theme-on-surface), 0.3); }
.item-id {
    font-family: ui-monospace, monospace;
    font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.5);
}
.item-title {
    flex: 1;
    min-width: 0;
    color: rgba(var(--v-theme-on-surface), 0.85);
}
.attention-icon { color: #b58400; }
.item-notes {
    flex-basis: 100%;
    padding-left: 20px;
    font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.5);
    font-style: italic;
}
.has-notes { padding-bottom: 4px; }
.stats-footer {
    margin-top: 8px;
    padding: 4px 8px;
    font-size: 11px;
    color: rgba(var(--v-theme-on-surface), 0.55);
    font-style: italic;
}
</style>
