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

        <!-- Items -->
        <div class="items-list">
            <div
                v-for="item in list?.items || []"
                :key="item.id"
                class="todo-item"
                :class="['status-' + item.status, { 'has-notes': item.notes }]"
            >
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
                    v-if="item.notes"
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
import { computed } from "vue";

/**
 * TodoListPanel — 复用组件：渲染 todo_list 工具回传的完整列表视图（进度条 + items + 统计）。
 *
 * 原实现在 TodoListResult.vue 中,因侧边栏也需要同一份视图,故抽离为独立组件。
 * 接受的是已经剥离 envelope 后的 {list, stats, attention_items},由调用方保证。
 */
const props = defineProps<{
    list: any;
    stats: any;
    attentionItems?: number[];
}>();

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
