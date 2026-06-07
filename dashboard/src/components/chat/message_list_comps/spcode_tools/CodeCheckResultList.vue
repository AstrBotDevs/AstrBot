<template>
    <div class="linter-section" :class="{ 'is-unavailable': !data?.available }">
        <!-- Section header: icon + 工具名 + 计数徽章 -->
        <div class="section-header">
            <v-icon size="13">{{ icon }}</v-icon>
            <span class="section-title">{{ title }}</span>
            <span v-if="data?.available" class="section-count">{{ data.count ?? 0 }}</span>
            <span v-else class="section-unavailable">N/A</span>
        </div>

        <!-- 工具不可用 -->
        <div v-if="!data?.available" class="unavailable-block">
            <v-icon size="12">mdi-package-variant-remove</v-icon>
            <span>{{ data?.error || "工具不可用" }}</span>
        </div>

        <!-- 干净 -->
        <div v-else-if="data.ok && (data.count ?? 0) === 0" class="empty-block">
            <v-icon size="12">mdi-check-circle-outline</v-icon>
            <span>No issues</span>
        </div>

        <!-- issues 列表 -->
        <div v-else-if="displayedIssues.length" class="issues-block" :class="{ 'is-expanded': showAll }">
            <div
                v-for="(iss, i) in displayedIssues"
                :key="i"
                class="issue-row"
                :class="severityClass(iss)"
                @click="toggleIssue(i)"
            >
                <div class="issue-line">
                    <span class="issue-loc">{{ getLocText(iss) }}</span>
                    <span v-if="getCode(iss)" class="issue-code">{{ getCode(iss) }}</span>
                    <span class="issue-msg">{{ getMessage(iss) }}</span>
                    <v-icon size="14" class="issue-chevron" :class="{ open: openSet[i] }">
                        mdi-chevron-right
                    </v-icon>
                </div>
                <pre v-if="openSet[i] && getContext(iss)" class="issue-context">{{ getContext(iss) }}</pre>
                <pre v-if="openSet[i]" class="issue-detail">{{ JSON.stringify(stripContext(iss), null, 2) }}</pre>
            </div>
            <button
                v-if="(data.count ?? 0) > COLLAPSED_LIMIT"
                type="button"
                class="more-toggle"
                :aria-expanded="showAll"
                @click="showAll = !showAll"
            >
                <v-icon size="12" class="more-chevron" :class="{ open: showAll }">
                    mdi-chevron-down
                </v-icon>
                <span v-if="!showAll">+{{ data.count - COLLAPSED_LIMIT }} more</span>
                <span v-else>Show less</span>
            </button>
        </div>
    </div>
</template>

<script setup lang="ts">
/**
 * code_check merge 模式的子组件：渲染单个工具的 issues 列表。
 *
 * 接收 _extract_linter_block() 包装后的 block dict：
 *   {
 *     available: bool,
 *     ok: bool,
 *     issues: array,
 *     count: int,
 *     error: string,
 *     _linter: 'cppcheck' | 'cpplint',
 *   }
 *
 * Author: ui_spcode_foundation
 * Date: 2026-06-07
 */
import { computed, reactive, ref } from "vue";

const COLLAPSED_LIMIT = 5;

const props = defineProps<{
    title: string;
    icon: string;
    data: any;
}>();

const showAll = ref(false);
const openSet = reactive<Record<number, boolean>>({});

const displayedIssues = computed<any[]>(() => {
    const issues = props.data?.issues || [];
    return showAll.value ? issues : issues.slice(0, COLLAPSED_LIMIT);
});

function toggleIssue(i: number) {
    openSet[i] = !openSet[i];
}

// ── 字段归一化：ruff / cpplint / cppcheck 的 schema 不同 ────────

function getLoc(iss: any): { line: number; col: number } {
    // ruff 风格：location: {row, column}
    if (iss.location?.row !== undefined && iss.location.row !== null) {
        return { line: iss.location.row, col: iss.location.column ?? 0 };
    }
    // cpplint / cppcheck 风格：line 直接平铺
    if (iss.line !== undefined && iss.line !== null) {
        return { line: iss.line, col: iss.col ?? 0 };
    }
    return { line: Number.NaN, col: 0 };
}

function getLocText(iss: any): string {
    const { line, col } = getLoc(iss);
    if (Number.isNaN(line)) return "L?";
    return col > 0 ? `L${line}:${col}` : `L${line}`;
}

function getCode(iss: any): string {
    // ruff: code (E501/W292)
    // cpplint: category (whitespace/line_length)
    // cppcheck: id (mismatchAllocDealloc)
    return iss.code || iss.category || iss.id || "";
}

function getMessage(iss: any): string {
    return iss.message || "";
}

function getContext(iss: any): string {
    if (!iss.context || !Array.isArray(iss.context)) return "";
    return iss.context.join("\n");
}

function stripContext(iss: any): any {
    const { context, _linter, ...rest } = iss;
    return rest;
}

function severityClass(iss: any): string {
    // ruff: severity='error' | 'warning' | 'info'
    // cppcheck: severity='error' | 'warning' | 'style' | 'performance' | 'portability'
    // cpplint: level 1-5（5 最高）
    const sev = (iss.severity || "").toLowerCase();
    if (sev === "error") return "issue-error";
    if (sev === "warning") return "issue-warn";
    const lvl = iss.level;
    if (typeof lvl === "number") {
        return lvl >= 4 ? "issue-error" : "issue-warn";
    }
    return "issue-warn";
}
</script>

<style scoped>
.linter-section {
    margin-top: 6px;
    padding: 6px 8px;
    border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.02);
    border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.linter-section + .linter-section { margin-top: 4px; }
.linter-section.is-unavailable {
    background: rgba(var(--v-theme-on-surface), 0.03);
    opacity: 0.7;
}

.section-header {
    display: flex; align-items: center; gap: 6px;
    font-size: 11.5px; font-weight: 500;
    color: rgba(var(--v-theme-on-surface), 0.7);
}
.section-title {
    font-family: ui-monospace, monospace;
    text-transform: lowercase;
}
.section-count {
    margin-left: auto;
    padding: 1px 6px; border-radius: 8px;
    background: rgba(var(--v-theme-primary), 0.12);
    color: rgb(var(--v-theme-primary));
    font-size: 10.5px; font-weight: 600;
    min-width: 18px; text-align: center;
}
.section-unavailable {
    margin-left: auto;
    padding: 1px 6px; border-radius: 8px;
    background: rgba(var(--v-theme-on-surface), 0.08);
    color: rgba(var(--v-theme-on-surface), 0.5);
    font-size: 10.5px;
}

.unavailable-block,
.empty-block {
    display: flex; align-items: center; gap: 6px;
    margin-top: 4px; padding: 4px 8px;
    border-radius: 3px;
    font-size: 11px;
}
.unavailable-block {
    background: rgba(var(--v-theme-on-surface), 0.04);
    color: rgba(var(--v-theme-on-surface), 0.55);
    font-style: italic;
}
.empty-block {
    background: rgba(70, 200, 70, 0.06);
    color: #2da44e;
}

.issues-block { margin-top: 4px; }
.issues-block.is-expanded {
    max-height: 400px;
    overflow-y: auto;
}
.issue-row {
    border-left: 2px solid rgba(255, 100, 100, 0.4);
    padding: 3px 8px; margin-bottom: 2px;
    background: rgba(var(--v-theme-on-surface), 0.03);
    border-radius: 0 4px 4px 0; cursor: pointer;
    transition: background 0.15s;
}
.issue-row:hover { background: rgba(var(--v-theme-on-surface), 0.06); }
.issue-row.issue-error { border-left-color: rgba(207, 34, 46, 0.6); }
.issue-row.issue-warn  { border-left-color: rgba(181, 132, 0, 0.6); }
.issue-line { display: flex; align-items: baseline; gap: 8px; font-size: 11.5px; }
.issue-loc {
    font-family: ui-monospace, monospace; font-weight: 600;
    color: #cf222e; min-width: 50px;
}
.issue-row.issue-warn .issue-loc { color: #b58400; }
.issue-code {
    font-family: ui-monospace, monospace; font-size: 10.5px;
    padding: 0 4px; border-radius: 2px;
    background: rgba(var(--v-theme-on-surface), 0.06);
    color: rgba(var(--v-theme-on-surface), 0.6);
}
.issue-msg {
    color: rgba(var(--v-theme-on-surface), 0.8);
    flex: 1; min-width: 0; word-break: break-word;
}
.issue-chevron { color: rgba(var(--v-theme-on-surface), 0.4); transition: transform 0.2s; }
.issue-chevron.open { transform: rotate(90deg); }
.issue-context {
    margin: 4px 0 0; padding: 4px 8px;
    background: rgba(var(--v-theme-on-surface), 0.04); border-radius: 3px;
    font-family: ui-monospace, monospace; font-size: 11px; line-height: 1.55;
    color: rgba(var(--v-theme-on-surface), 0.75);
    white-space: pre-wrap; word-break: break-all;
    max-height: 200px; overflow-y: auto;
}
.issue-detail {
    margin: 4px 0 0; padding: 4px 8px;
    background: rgba(var(--v-theme-on-surface), 0.05); border-radius: 3px;
    font-family: ui-monospace, monospace; font-size: 11px;
    white-space: pre-wrap; max-height: 200px; overflow-y: auto;
}
.more-toggle {
    display: flex; align-items: center; gap: 4px;
    margin-top: 4px; padding: 4px 8px; width: 100%;
    background: transparent;
    border: 1px dashed rgba(var(--v-theme-on-surface), 0.12);
    border-radius: 4px;
    font-size: 11px; font-style: italic;
    color: rgba(var(--v-theme-on-surface), 0.55);
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.more-toggle:hover {
    background: rgba(var(--v-theme-on-surface), 0.04);
    border-color: rgba(var(--v-theme-on-surface), 0.22);
    color: rgba(var(--v-theme-on-surface), 0.8);
}
.more-toggle:focus-visible {
    outline: 2px solid rgba(var(--v-theme-primary), 0.4);
    outline-offset: 1px;
}
.more-chevron {
    transition: transform 0.2s;
    color: rgba(var(--v-theme-on-surface), 0.4);
}
.more-chevron.open { transform: rotate(180deg); }
</style>
