<template>
    <div class="file-diff-result">
        <!-- 相同文件：仅显示状态徽章 -->
        <div v-if="identical" class="status-row success">
            <v-icon size="14">mdi-check-circle</v-icon>
            <span class="status-text">Files are identical</span>
        </div>

        <!-- 有差异：复用现有 DiffPreview 渲染 -->
        <template v-else>
            <div class="status-row info">
                <v-icon size="14">mdi-vector-difference</v-icon>
                <span class="status-text">
                    {{ data.added || 0 }} addition(s), {{ data.removed || 0 }} removal(s)
                </span>
                <span v-if="data.total_changes !== undefined" class="changes-chip">
                    {{ data.total_changes }} changes
                </span>
            </div>
            <DiffPreview
                :content="data.diff || ''"
                :file-path="filePathCombined"
                :summary="summaryText"
                :is-dark="isDark"
                :max-lines="25"
                :collapsible="false"
            />
        </template>
    </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import DiffPreview from "../DiffPreview.vue";

const props = defineProps<{
    data: any;
    isDark?: boolean;
}>();

const identical = computed(() => !!props.data?.identical);
const filePathCombined = computed(() => {
    const a = props.data?.file_a || "";
    const b = props.data?.file_b || "";
    if (a && b) return `${a} → ${b}`;
    return a || b || "";
});
const summaryText = computed(() => {
    if (identical.value) return "Files are identical";
    return `+${props.data?.added || 0} −${props.data?.removed || 0}`;
});
</script>

<style scoped>
.file-diff-result { font-size: 12px; }
.status-row {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 8px; border-radius: 4px; font-size: 11.5px;
    margin-bottom: 6px;
}
.status-row.success { background: rgba(70, 200, 70, 0.08); color: #2da44e; }
.status-row.info    { background: rgba(0, 100, 200, 0.08); color: #1565c0; }
.status-text { font-weight: 500; }
.changes-chip {
    margin-left: auto;
    padding: 1px 6px; border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), 0.06);
    font-family: ui-monospace, monospace; font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.6);
}
</style>
