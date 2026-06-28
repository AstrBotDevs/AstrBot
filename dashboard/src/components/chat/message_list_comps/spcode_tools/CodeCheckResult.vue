<template>
    <div class="code-check-result">
        <!-- 状态徽章 -->
        <div class="status-row" :class="statusClass">
            <v-icon size="14">{{ statusIcon }}</v-icon>
            <span class="status-text">{{ statusText }}</span>
            <span class="linter-chip" v-if="linterLabel">{{ linterLabel }}</span>
        </div>

        <!-- 失败 / 错误场景：proposal 协议字段 -->
        <div v-if="!ok && proposal" class="error-block">
            <div class="proposal-line" v-if="proposal">
                <v-icon size="13" class="proposal-icon">mdi-lightbulb-on-outline</v-icon>
                <span class="proposal-text">{{ proposal }}</span>
            </div>
            <div v-if="errorText" class="error-detail">{{ errorText }}</div>
            <ul v-if="options.length" class="options-list">
                <li v-for="(opt, i) in options" :key="i">{{ opt }}</li>
            </ul>
        </div>

        <!-- merge 模式：分组展示两个工具的结果 -->
        <div v-else-if="isMergeMode" class="merge-block">
            <CodeCheckResultList
                v-if="lintersData.cppcheck"
                title="cppcheck"
                icon="mdi-shield-search"
                :data="lintersData.cppcheck"
            />
            <CodeCheckResultList
                v-if="lintersData.cpplint"
                title="cpplint"
                icon="mdi-text-box-check-outline"
                :data="lintersData.cpplint"
            />
        </div>

        <!-- 干净文件（单 linter 模式） -->
        <div v-else-if="ok && count === 0" class="empty-issues">
            <v-icon size="13">mdi-check-circle-outline</v-icon>
            {{ labels.noIssues || 'No issues' }}
        </div>

        <!-- issues 列表（前 5 条，可点击 +N more 展开全部） -->
        <div v-else-if="displayedIssues.length" class="issues-block" :class="{ 'is-expanded': showAll }">
            <div
                v-for="(iss, i) in displayedIssues"
                :key="i"
                class="issue-row"
                :class="severityClass(iss)"
                @click="toggleIssue(i)"
            >
                <div class="issue-line">
                <CopyableText :value="getLocText(iss)" mode="code" class="issue-loc" />

                <CopyableText v-if="getCode(iss)" :value="getCode(iss)" mode="code" class="issue-code" />

                <CopyableText :value="getMessage(iss)" mode="block" :multiline="true" class="issue-msg" />

                    <v-icon size="14" class="issue-chevron" :class="{ open: openSet[i] }">
                        mdi-chevron-right
                    </v-icon>
                </div>
                <pre v-if="openSet[i] && getContext(iss)" class="issue-context">{{ getContext(iss) }}</pre>
                <pre v-if="openSet[i]" class="issue-detail">{{ JSON.stringify(stripContext(iss), null, 2) }}</pre>
            </div>
            <button
                v-if="count > 5"
                type="button"
                class="more-toggle"
                :aria-expanded="showAll"
                @click="showAll = !showAll"
            >
                <v-icon size="12" class="more-chevron" :class="{ open: showAll }">
                    mdi-chevron-down
                </v-icon>
                <span v-if="!showAll">+{{ count - 5 }} more</span>
                <span v-else>Show less</span>
            </button>
        </div>
    </div>
</template>

<script setup lang="ts">
/**
 * code_check 工具结果展示组件。
 * 取代旧的 SyntaxCheckResult + LintRunnerResult。
 *
 * 数据 schema（来自 tools/code_check.py:check()）：
 *   - ok: bool
 *   - linter: 'ruff' | 'cpplint'
 *   - issues: array
 *   - count: int
 *   - proposal/options/error: proposal 协议字段
 *
 * issues 因 linter 而异：
 *   - ruff:    {code, message, severity, location:{row,column}, fix, url, context?}
 *   - cpplint: {line, message, category, level, context?}
 *
 * Author: ui_spcode_foundation
 * Date: 2026-06-07
 */
import { computed, reactive, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import CodeCheckResultList from "./CodeCheckResultList.vue";
import CopyableText from "../__shared__/CopyableText.vue";

// 折叠态下显示的 issue 数；展开时显示全部
const COLLAPSED_LIMIT = 5;
// 展开态下的最大可视高度（issues 过多时加滚动条）
const EXPANDED_MAX_HEIGHT = "400px";

const props = defineProps<{ data: any; args?: { filepath?: string; linter?: string } }>();

const { tm } = useModuleI18n("features/chat");
const labels = computed(() => (tm("actions.spcodeTool.labels") as any) || {});

const ok = computed(() => !!props.data?.ok);
const linterName = computed(() => props.data?.linter || props.args?.linter || "");

// merge 模式：data.linters 存在（cppcheck+cpplint 分组结果）
const isMergeMode = computed(() => {
    return (
        linterName.value === "merge" &&
        props.data?.linters &&
        typeof props.data.linters === "object"
    );
});
const lintersData = computed(() => props.data?.linters || {});

// 总 issue 数：单 linter 模式从顶层 count 取；merge 模式从 linters.* 求和
const count = computed(() => {
    if (isMergeMode.value) {
        const cpp = lintersData.value.cppcheck?.count ?? 0;
        const cp = lintersData.value.cpplint?.count ?? 0;
        return cpp + cp;
    }
    return Number(props.data?.count ?? 0);
});
const proposal = computed(() => props.data?.proposal || "");
const errorText = computed(() => props.data?.error || "");
const options = computed<string[]>(() => props.data?.options || []);

const linterLabel = computed(() => {
    const lang = detectLang(props.args?.filepath);
    if (linterName.value === "ruff") return `Python · ruff`;
    if (linterName.value === "cppcheck") return `${lang} · cppcheck`;
    if (linterName.value === "cpplint") return `${lang} · cpplint`;
    if (linterName.value === "merge") {
        // merge 模式 chip 显示每个工具的计数
        const cpp = lintersData.value.cppcheck;
        const cp = lintersData.value.cpplint;
        const cppStr = cpp?.available ? (cpp.count ?? 0) : "N/A";
        const cpStr = cp?.available ? (cp.count ?? 0) : "N/A";
        return `cppcheck ${cppStr} + cpplint ${cpStr}`;
    }
    return linterName.value || "";
});

const statusClass = computed(() => {
    if (!ok.value) return "error";
    if (count.value === 0) return "success";
    return "warn";
});

const statusIcon = computed(() => {
    if (!ok.value) return "mdi-alert-circle";
    if (count.value === 0) return "mdi-check-circle";
    return "mdi-alert";
});

const statusText = computed(() => {
    const file = props.args?.filepath || "";
    if (!ok.value) {
        return errorText.value || proposal.value || "Failed";
    }
    if (isMergeMode.value) {
        // merge 模式：展示两个工具的合并概况
        const cpp = lintersData.value.cppcheck;
        const cp = lintersData.value.cpplint;
        const totalCount = count.value;
        if (totalCount === 0) {
            return file
                ? `OK · ${file}`
                : "cppcheck + cpplint 都通过";
        }
        const cppStr = cpp?.count ?? 0;
        const cpStr = cp?.count ?? 0;
        return `${totalCount} issues (${cppStr}+${cpStr})${file ? ` · ${file}` : ""}`;
    }
    if (count.value === 0) {
        return file ? `OK · ${file}` : (labels.value.ok || "OK");
    }
    return `${count.value} issues${file ? ` · ${file}` : ""}`;
});

// 是否展开查看全部 issues（默认折叠，只显示前 N 条；点击 +N more 切换）
const showAll = ref(false);

const displayedIssues = computed<any[]>(() => {
    const issues = props.data?.issues || [];
    return showAll.value ? issues : issues.slice(0, COLLAPSED_LIMIT);
});

const openSet = reactive<Record<number, boolean>>({});

function toggleIssue(i: number) {
    openSet[i] = !openSet[i];
}

// ── 字段归一化：ruff 与 cpplint 的 schema 不同 ────────

function getLoc(iss: any): { line: number; col: number } {
    // ruff 风格：location: {row, column}
    if (iss.location?.row !== undefined && iss.location.row !== null) {
        return { line: iss.location.row, col: iss.location.column ?? 0 };
    }
    // cpplint 风格：line 直接平铺
    if (iss.line !== undefined && iss.line !== null) {
        return { line: iss.line, col: 0 };
    }
    // 真正没有位置信息时用 NaN 哨兵（区分 cpplint 整文件级 line=0 的合法值）
    return { line: Number.NaN, col: 0 };
}

function getLocText(iss: any): string {
    const { line, col } = getLoc(iss);
    if (Number.isNaN(line)) return "L?";
    // line=0 是 cpplint 整文件级 issue 的合法值（如 legal/copyright），正常显示为 L0
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
    // 展开 JSON 详情时去掉 context 字段（已在独立区块显示）
    const { context, ...rest } = iss;
    return rest;
}

function severityClass(iss: any): string {
    // ruff: severity='error' | 'warning' | 'info'
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

function detectLang(filepath?: string): string {
    if (!filepath) return "C/C++";
    const lower = filepath.toLowerCase();
    if (lower.endsWith(".h") || lower.endsWith(".hpp") || lower.endsWith(".hxx")) return "C/C++ Header";
    if (lower.endsWith(".cpp") || lower.endsWith(".cc") || lower.endsWith(".cxx")) return "C++";
    if (lower.endsWith(".c")) return "C";
    if (lower.endsWith(".py")) return "Python";
    return "C/C++";
}
</script>

<style scoped>
.code-check-result { font-size: 12px; }
.status-row {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 8px; border-radius: 4px; font-size: 11.5px;
}
.status-row.success { background: rgba(70, 200, 70, 0.08); color: #2da44e; }
.status-row.error   { background: rgba(255, 100, 100, 0.08); color: #cf222e; }
.status-row.warn    { background: rgba(255, 180, 0, 0.10); color: #b58400; }
.status-text { font-weight: 500; }
.linter-chip {
    margin-left: auto;
    padding: 1px 6px; border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), 0.06);
    font-family: ui-monospace, monospace; font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.6);
}

/* 错误/失败块 */
.error-block {
    margin-top: 6px; padding: 8px 10px;
    background: rgba(207, 34, 46, 0.05);
    border-left: 2px solid #cf222e;
    border-radius: 0 4px 4px 0;
}
.proposal-line {
    display: flex; align-items: baseline; gap: 6px;
    font-size: 11.5px; color: rgba(var(--v-theme-on-surface), 0.85);
}
.proposal-icon { color: #b58400; flex-shrink: 0; }
.proposal-text { font-weight: 500; }
.error-detail {
    margin-top: 4px; font-size: 11px;
    font-family: ui-monospace, monospace;
    color: rgba(var(--v-theme-on-surface), 0.65);
    word-break: break-all;
}
.options-list {
    margin: 6px 0 0; padding: 0; list-style: none;
    font-size: 11px; color: rgba(var(--v-theme-on-surface), 0.65);
}
.options-list li {
    padding: 2px 0 2px 12px; position: relative;
}
.options-list li::before {
    content: "→"; position: absolute; left: 0; color: rgba(var(--v-theme-on-surface), 0.4);
}

/* 干净文件 */
.empty-issues {
    margin-top: 6px; padding: 6px 10px; border-radius: 4px;
    background: rgba(70, 200, 70, 0.06); color: #2da44e;
    font-size: 11.5px;
    display: flex; align-items: center; gap: 6px;
}

/* issues 列表 */
.issues-block { margin-top: 6px; }
.issues-block.is-expanded {
    max-height: v-bind(EXPANDED_MAX_HEIGHT);
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
.more-chevron.open {
    transform: rotate(180deg);
}
</style>
