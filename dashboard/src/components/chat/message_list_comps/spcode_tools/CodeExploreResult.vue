<template>
    <div class="code-explore-result">
        <!-- A) no_index -->
        <template v-if="!data.ok || data.error === 'no_index'">
            <div class="status-row warn">
                <v-icon size="14">mdi-information-outline</v-icon>
                <span class="status-text">{{ data.summary || 'No index. Run code_index first.' }}</span>
            </div>
        </template>

        <!-- B) symbol_search / D) explore: symbol list -->
        <template v-else-if="data.query_type === 'symbol_search' || data.query_type === 'explore'">
            <div class="status-row" :class="data.found ? 'success' : 'warn'">
                <v-icon size="14">{{ data.found ? 'mdi-check-circle' : 'mdi-magnify' }}</v-icon>
                <span class="status-text">{{ data.summary }}</span>
                <span class="qt-chip">{{ data.query_type }}</span>
            </div>
            <div v-if="data.symbols && data.symbols.length" class="symbol-list">
                <div
                    v-for="(sym, i) in data.symbols"
                    :key="i"
                    class="symbol-card"
                    @click="toggleSymbol(i)"
                >
                    <div class="symbol-header">
                        <span class="symbol-kind" :class="kindClass(sym.kind)">{{ sym.kind || 'sym' }}</span>
                        <CopyableText :value="sym.name" mode="inline" class="symbol-name" />
                        <CopyableText v-if="sym.file" :value="`${sym.file}:${sym.line}`" mode="code" class="symbol-loc" />

                    </div>
                    <pre v-if="sym.signature && openSet[i]" class="symbol-sig">{{ sym.signature }}</pre>
                    <pre v-if="sym.source && openSet[i]" class="symbol-src">{{ sym.source }}</pre>
                    <div v-if="data.callers && data.callers[sym.name] && openSet[i]" class="callers-block">
                        <span class="callers-label">Callers:</span>
                        <CopyableText

                            v-for="c in data.callers[sym.name]"

                            :key="c"

                            :value="c"

                            mode="code"

                            class="caller-chip"

                        />

                    </div>
                </div>
            </div>
        </template>

        <!-- C) trace (path) -->
        <template v-else-if="data.query_type === 'trace' && data.path">
            <div class="status-row success">
                <v-icon size="14">mdi-graph-outline</v-icon>
                <span class="status-text">{{ data.summary }}</span>
            </div>
            <div class="trace-path">
                <template v-for="(node, i) in data.path" :key="i">
                    <span class="trace-node">{{ node }}</span>
                    <v-icon v-if="i < data.path.length - 1" size="14" class="trace-arrow">mdi-arrow-right</v-icon>
                </template>
            </div>
        </template>

        <!-- 其他 fallback -->
        <template v-else>
            <div class="status-row" :class="data.found ? 'success' : 'warn'">
                <v-icon size="14">{{ data.found ? 'mdi-check-circle' : 'mdi-alert-circle' }}</v-icon>
                <span class="status-text">{{ data.summary || JSON.stringify(data) }}</span>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { reactive } from "vue";
import CopyableText from "../__shared__/CopyableText.vue";

interface CodeExploreSymbol {
    kind?: string;
    name: string;
    file?: string;
    line?: number;
    signature?: string;
    source?: string;
}

interface CodeExploreData {
    ok?: boolean;
    error?: string;
    summary?: string;
    query_type?: string;
    found?: boolean;
    symbols?: CodeExploreSymbol[];
    path?: string[];
    callers?: Record<string, string[]>;
}

const props = defineProps<{ data: CodeExploreData; args?: any }>();
const openSet = reactive<Record<number, boolean>>({});

function toggleSymbol(i: number) {
    openSet[i] = !openSet[i];
}

function kindClass(kind: string | undefined) {
    if (kind === "class") return "kind-class";
    if (kind === "method") return "kind-method";
    if (kind === "function") return "kind-function";
    return "kind-default";
}
</script>

<style scoped>
.code-explore-result { font-size: 12px; }
.status-row {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 8px; border-radius: 4px; font-size: 11.5px;
}
.status-row.success { background: rgba(70, 200, 70, 0.08); color: #2da44e; }
.status-row.warn    { background: rgba(255, 180, 0, 0.08); color: #b58400; }
.status-row.error   { background: rgba(255, 100, 100, 0.08); color: #cf222e; }
.status-text { font-weight: 500; flex: 1; min-width: 0; }
.qt-chip {
    padding: 1px 6px; border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), 0.06);
    font-family: ui-monospace, monospace; font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.6);
}
.symbol-list { margin-top: 6px; }
.symbol-card {
    padding: 4px 8px; border-radius: 4px; margin-bottom: 3px;
    background: rgba(var(--v-theme-on-surface), 0.03);
    border-left: 2px solid rgba(0, 100, 200, 0.3);
    cursor: pointer; transition: background 0.15s;
}
.symbol-card:hover { background: rgba(var(--v-theme-on-surface), 0.06); }
.symbol-header { display: flex; align-items: baseline; gap: 8px; }
.symbol-kind {
    padding: 0 5px; border-radius: 2px; font-size: 10px;
    font-family: ui-monospace, monospace; text-transform: uppercase;
    font-weight: 600;
}
.kind-class   { background: rgba(255, 100, 200, 0.15); color: #c2185b; }
.kind-method  { background: rgba(100, 200, 100, 0.15); color: #2e7d32; }
.kind-function{ background: rgba(100, 150, 255, 0.15); color: #1565c0; }
.kind-default { background: rgba(var(--v-theme-on-surface), 0.08); color: rgba(var(--v-theme-on-surface), 0.6); }
.symbol-name {
    font-family: ui-monospace, monospace; font-size: 12px;
    font-weight: 600; color: rgba(var(--v-theme-on-surface), 0.85);
}
.symbol-loc {
    font-family: ui-monospace, monospace; font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.45);
    margin-left: auto;
}
.symbol-sig, .symbol-src {
    margin: 4px 0 0; padding: 4px 6px;
    background: rgba(var(--v-theme-on-surface), 0.05); border-radius: 3px;
    font-family: ui-monospace, monospace; font-size: 11px; line-height: 1.55;
    white-space: pre-wrap; max-height: 200px; overflow-y: auto;
    color: rgba(var(--v-theme-on-surface), 0.75);
}
.callers-block { margin-top: 4px; display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.callers-label { font-size: 10.5px; color: rgba(var(--v-theme-on-surface), 0.5); }
.caller-chip {
    font-family: ui-monospace, monospace; font-size: 10.5px;
    padding: 0 4px; border-radius: 2px;
    background: rgba(var(--v-theme-on-surface), 0.06);
    color: rgba(var(--v-theme-on-surface), 0.7);
}
.trace-path {
    margin-top: 6px; padding: 6px 8px; border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.04);
    display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
    font-family: ui-monospace, monospace; font-size: 11.5px;
}
.trace-node {
    padding: 1px 6px; border-radius: 3px;
    background: rgba(0, 100, 200, 0.1); color: #1565c0;
}
.trace-arrow { color: rgba(var(--v-theme-on-surface), 0.4); }
</style>
