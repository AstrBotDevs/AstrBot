<template>
    <div class="es-search-result">
        <div class="status-row success">
            <v-icon size="14">mdi-file-search-outline</v-icon>
            <span class="status-text">Found {{ data.count || 0 }} files</span>
            <span v-if="data.engine" class="engine-chip">engine: {{ data.engine }}</span>
        </div>
        <div v-if="data.items && data.items.length" class="items-list">
            <div
                v-for="(item, i) in displayedItems"
                :key="i"
                class="item-row"
                @click="toggleItem(i)"
            >
                <div class="item-line">
                    <v-icon size="13" class="item-icon">mdi-file-outline</v-icon>
                    <CopyableText :value="item.name" mode="inline" class="item-name" />
                    <CopyableText v-if="item.path" :value="item.path" mode="code" class="item-path" />

                    <span v-if="item.size !== undefined" class="item-size">{{ humanSize(item.size) }}</span>
                </div>
                <pre v-if="item.full && openSet[i]" class="item-full">{{ item.full }}</pre>
            </div>
            <div
                v-if="data.items.length > 8"
                class="more-note"
                role="button"
                @click="showAll = !showAll"
            >
                <template v-if="showAll">Show fewer</template>
                <template v-else>+{{ data.items.length - 8 }} more (total {{ data.count }})</template>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import CopyableText from "../__shared__/CopyableText.vue";

interface EsSearchItem {
    name: string;
    path?: string;
    size?: number;
    full?: string;
}

interface EsSearchData {
    count?: number;
    engine?: string;
    items?: EsSearchItem[];
}

const props = defineProps<{ data: EsSearchData; args?: any }>();
const openSet = reactive<Record<number, boolean>>({});
// When true, render every matched file; otherwise only the first 8.
// Toggled from the footer link so users can expand/collapse the trimmed tail.
const showAll = ref(false);

const displayedItems = computed(() => {
    const items = props.data?.items || [];
    return showAll.value ? items : items.slice(0, 8);
});

function toggleItem(i: number) {
    openSet[i] = !openSet[i];
}

function humanSize(n: number): string {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
    return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}
</script>

<style scoped>
.es-search-result { font-size: 12px; }
.status-row {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 8px; border-radius: 4px; font-size: 11.5px;
}
.status-row.success { background: rgba(70, 200, 70, 0.08); color: #2da44e; }
.status-text { font-weight: 500; }
.engine-chip {
    margin-left: auto;
    padding: 1px 6px; border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), 0.06);
    font-family: ui-monospace, monospace; font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.6);
}
.items-list { margin-top: 6px; }
.item-row {
    padding: 3px 8px; border-radius: 4px; margin-bottom: 2px;
    background: rgba(var(--v-theme-on-surface), 0.03);
    cursor: pointer; transition: background 0.15s;
}
.item-row:hover { background: rgba(var(--v-theme-on-surface), 0.06); }
.item-line { display: flex; align-items: baseline; gap: 8px; }
.item-icon { color: rgba(0, 100, 200, 0.6); flex-shrink: 0; }
.item-name {
    font-family: ui-monospace, monospace; font-size: 11.5px;
    font-weight: 500; color: rgba(var(--v-theme-on-surface), 0.85);
}
.item-path {
    font-family: ui-monospace, monospace; font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.45);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    flex: 1; min-width: 0;
}
.item-size {
    font-family: ui-monospace, monospace; font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.5); flex-shrink: 0;
}
.item-full {
    margin: 4px 0 0; padding: 4px 6px;
    background: rgba(var(--v-theme-on-surface), 0.05); border-radius: 3px;
    font-family: ui-monospace, monospace; font-size: 10.5px;
    white-space: pre-wrap; word-break: break-all;
    color: rgba(var(--v-theme-on-surface), 0.7);
}
.more-note {
    margin-top: 4px; padding: 2px 8px;
    font-size: 11px; font-style: italic;
    color: rgba(var(--v-theme-on-surface), 0.45);
    cursor: pointer;
    user-select: none;
    border-radius: 3px;
    transition: color 0.15s, background 0.15s;
}
.more-note:hover {
    color: rgba(var(--v-theme-on-surface), 0.7);
    background: rgba(var(--v-theme-on-surface), 0.04);
}
</style>
