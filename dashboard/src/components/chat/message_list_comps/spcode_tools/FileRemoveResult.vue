<template>
    <div class="file-remove-result">
        <!-- 成功 -->
        <div v-if="ok" class="status-row success">
            <v-icon size="14">mdi-trash-can-outline</v-icon>
            <span class="status-text">Deleted {{ data.deleted }} item(s), freed {{ data.freed }}</span>
        </div>

        <!-- 失败 + proposal -->
        <div v-else>
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
            <div v-if="data.options && data.options.length" class="options-block">
                <span class="options-label">Or:</span>
                <code v-for="(opt, i) in data.options" :key="i" class="option-chip">{{ opt }}</code>
            </div>
        </div>

        <!-- 错误详情列表 -->
        <div v-if="data.errors && data.errors.length" class="errors-list">
            <div v-for="(err, i) in data.errors" :key="i" class="error-row">
                <v-icon size="12" class="error-icon">mdi-alert</v-icon>
                <code class="error-path">{{ err.path }}</code>
                <span class="error-reason">{{ err.reason }}</span>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ data: any }>();
const ok = computed(() => !!props.data?.ok);
</script>

<style scoped>
.file-remove-result { font-size: 12px; }
.status-row {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 8px; border-radius: 4px; font-size: 11.5px;
}
.status-row.success { background: rgba(70, 200, 70, 0.08); color: #2da44e; }
.status-row.error   { background: rgba(255, 100, 100, 0.08); color: #cf222e; }
.status-text { font-weight: 500; }
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
.options-block {
    margin-top: 6px; padding: 4px 8px; border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.03);
    display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
}
.options-label {
    font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.5);
    font-style: italic;
}
.option-chip {
    font-family: ui-monospace, monospace; font-size: 10.5px;
    padding: 1px 6px; border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), 0.08);
    color: rgba(var(--v-theme-on-surface), 0.7);
}
.errors-list { margin-top: 6px; }
.error-row {
    display: flex; align-items: baseline; gap: 6px;
    padding: 2px 8px; font-size: 11px;
}
.error-icon { color: #cf222e; flex-shrink: 0; }
.error-path {
    font-family: ui-monospace, monospace; font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.7);
    max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.error-reason {
    color: #cf222e; font-size: 10.5px;
}
</style>
