<template>
    <div class="code-index-result">
        <div class="status-row success">
            <v-icon size="14">mdi-check-circle</v-icon>
            <span class="status-text">{{ data.summary || 'Indexed' }}</span>
        </div>

        <div v-if="stats" class="stats-grid">
            <div class="stat-cell">
                <span class="stat-num">{{ stats.files }}</span>
                <span class="stat-label">files</span>
            </div>
            <div class="stat-cell">
                <span class="stat-num">{{ stats.symbols }}</span>
                <span class="stat-label">symbols</span>
            </div>
            <div class="stat-cell">
                <span class="stat-num">{{ stats.edges }}</span>
                <span class="stat-label">edges</span>
            </div>
            <div v-if="stats.skipped" class="stat-cell warn">
                <span class="stat-num">{{ stats.skipped }}</span>
                <span class="stat-label">skipped</span>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ data: any }>();
const stats = computed(() => props.data?.stats || null);
</script>

<style scoped>
.code-index-result { font-size: 12px; }
.status-row {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 8px; border-radius: 4px; font-size: 11.5px;
}
.status-row.success { background: rgba(70, 200, 70, 0.08); color: #2da44e; }
.status-text { font-weight: 500; }
.stats-grid {
    margin-top: 6px;
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px;
}
.stat-cell {
    padding: 6px 8px; border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.04);
    display: flex; flex-direction: column; align-items: center; gap: 2px;
}
.stat-cell.warn { background: rgba(255, 180, 0, 0.08); }
.stat-num {
    font-family: ui-monospace, monospace; font-size: 16px; font-weight: 600;
    color: rgba(var(--v-theme-on-surface), 0.85);
}
.stat-cell.warn .stat-num { color: #b58400; }
.stat-label {
    font-size: 10.5px; color: rgba(var(--v-theme-on-surface), 0.5);
    text-transform: uppercase; letter-spacing: 0.3px;
}
</style>
