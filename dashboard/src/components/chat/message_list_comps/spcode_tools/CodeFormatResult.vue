<!--
  CodeFormatResult
  ─────────────────────────────────────────────────────────────────────
  Renders the result of spcode plugin's `code_format` tool.

  State matrix (ok × changed × check):
    ok=false                    → red status row, plain error text
    ok=true,  changed=false     → blue status row, "Already formatted"
    ok=true,  changed=true, check=true   → yellow "Preview" + DiffPreview
    ok=true,  changed=true, check=false  → green "Formatted"  + DiffPreview

  数据契约:父级 SpcodeToolResultView.parsedData 已自动剥离
  {ok:true, data:{...}} envelope,失败/带 proposal 的透传场景也正确透传。
  因此 props.data 可直接当作原始 dict 使用。

  Author: elecvoid243
  Date: 2026-07-01
-->
<template>
    <div class="code-format-result">
        <!-- ── 统一状态行(4 色变体) ── -->
        <div class="status-row" :class="statusClass">
            <v-icon size="14">{{ statusIcon }}</v-icon>
            <!-- 带文件路径时用 CopyableText 包装,支持 hover 复制;无路径时降级为纯文本 -->
            <CopyableText
                v-if="filePath"
                :value="filePath"
                :display-value="statusText"
                mode="code"
                class="status-text"
            />
            <span v-else class="status-text">{{ statusText }}</span>

            <!-- 工具名 chip:Python · ruff / C++ · astyle 等 -->
            <span v-if="formatterChip" class="linter-chip">{{ formatterChip }}</span>
            <!-- 模式 chip:preview / write -->
            <span v-if="ok && formatterChip" class="linter-chip">{{ modeChip }}</span>
        </div>

        <!-- ── 有差异:复用 DiffPreview 渲染 unified diff ── -->
        <DiffPreview
            v-if="ok && changed && diffSummary"
            :content="diffSummary"
            :file-path="filePath"
            :summary="diffSummaryHeader"
            :is-dark="isDark"
            :max-lines="25"
            :collapsible="true"
        />

        <!-- ── 无差异:轻量"已符合"补充条 ── -->
        <div v-else-if="ok && !changed" class="empty-issues">
            <v-icon size="13">mdi-check-circle-outline</v-icon>
            <span>{{ emptyConformText }}</span>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CopyableText from "../__shared__/CopyableText.vue";
import DiffPreview from "../DiffPreview.vue";

const props = defineProps<{
    /** 工具返回的解析后数据(已剥 envelope)。 */
    data: any;
    /** 工具调用参数,用于读取 filepath 等展示用字段。 */
    args?: Record<string, any>;
    /** 当前主题;透传给 DiffPreview 以便其选择 dark/light diff 配色。 */
    isDark?: boolean;
}>();

// ── 原始字段读取 ─────────────────────────────────────────────

const ok = computed(() => !!props.data?.ok);
const errorText = computed(() => props.data?.error || "Failed");

const formatter = computed(() => props.data?.formatter || "");
const isCheckMode = computed(() => !!props.data?.check);
const changed = computed(() => !!props.data?.changed);
const diffSummary = computed(() => props.data?.diff_summary || "");

const filePath = computed(() => props.args?.filepath || "");

/** 取文件名(basename),兼容 Windows 反斜杠与 POSIX 正斜杠。
 *
 * Returns:
 *     文件 basename;若 filePath 为空则返回空串。
 */
const fileName = computed(() => {
    const p = filePath.value;
    if (!p) return "";
    const parts = p.split(/[\\/]/).filter(Boolean);
    return parts[parts.length - 1] || p;
});

// ── 复合状态(决定 status row 的 class / 图标 / 文案) ─────

const statusClass = computed(() => {
    if (!ok.value) return "error";
    if (!changed.value) return "info";
    return isCheckMode.value ? "warn" : "success";
});

const statusIcon = computed(() => {
    if (!ok.value) return "mdi-alert-circle";
    if (!changed.value) return "mdi-check-circle-outline";
    return isCheckMode.value ? "mdi-eye-outline" : "mdi-check-circle";
});

const statusText = computed(() => {
    if (!ok.value) return errorText.value;
    const fn = fileName.value;
    if (!changed.value) {
        return fn ? `${fn} already formatted` : "Already formatted";
    }
    const action = isCheckMode.value ? "Preview" : "Formatted";
    return fn ? `${action}: ${fn}` : action;
});

/** DiffPreview summary 字段:一行简短描述,展示在 diff header。
 *
 * Returns:
 *     "Preview diff (ruff)" / "Applied diff (astyle)" 等。
 */
const diffSummaryHeader = computed(() => {
    if (!ok.value) return "";
    const fmt = formatter.value || "formatter";
    return isCheckMode.value
        ? `Preview diff (${fmt})`
        : `Applied diff (${fmt})`;
});

// ── 工具名 chip ──

const formatterChip = computed(() => {
    if (!formatter.value) return "";
    if (formatter.value === "ruff") return "Python · ruff";
    if (formatter.value === "astyle") return `${detectLang(filePath.value)} · astyle`;
    return formatter.value;
});

const modeChip = computed(() => (isCheckMode.value ? "preview" : "write"));

const emptyConformText = computed(() => {
    const fn = fileName.value;
    const fmt = formatter.value || "formatter";
    return fn
        ? `${fn} already conforms to ${fmt} format`
        : `Already conforms to ${fmt} format`;
});

// ── helpers ──

/** 根据文件后缀推断语言标签,用于 astyle chip 展示。
 *
 * Args:
 *     filepath: 源文件路径;可为空。
 *
 * Returns:
 *     人类可读的语言标签,如 "C++" / "C" / "Java" / "JS" / "C#"。
 */
function detectLang(filepath?: string): string {
    if (!filepath) return "C/C++";
    const lower = filepath.toLowerCase();
    if (lower.endsWith(".h") || lower.endsWith(".hpp") || lower.endsWith(".hxx")) {
        return "C/C++";
    }
    if (lower.endsWith(".cpp") || lower.endsWith(".cc") || lower.endsWith(".cxx")) {
        return "C++";
    }
    if (lower.endsWith(".c")) return "C";
    if (lower.endsWith(".java")) return "Java";
    if (
        lower.endsWith(".js") ||
        lower.endsWith(".jsx") ||
        lower.endsWith(".mjs") ||
        lower.endsWith(".cjs")
    ) {
        return "JS";
    }
    if (lower.endsWith(".cs")) return "C#";
    return "C/C++";
}
</script>

<style scoped>
.code-format-result { font-size: 12px; }

/* ── 状态行 ── 沿用 CodeCheckResult 的 4 色变体(.info 为新增蓝色,借自 FileDiffResult) */
.status-row {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 8px; border-radius: 4px; font-size: 11.5px;
}
.status-row.success { background: rgba(70, 200, 70, 0.08); color: #2da44e; }
.status-row.error   { background: rgba(255, 100, 100, 0.08); color: #cf222e; }
.status-row.warn    { background: rgba(255, 180, 0, 0.10); color: #b58400; }
.status-row.info    { background: rgba(0, 100, 200, 0.08); color: #1565c0; }

.status-text {
    font-weight: 500;
    flex: 1; min-width: 0;
    word-break: break-word;
}
.linter-chip {
    margin-left: auto;
    padding: 1px 6px; border-radius: 3px;
    background: rgba(var(--v-theme-on-surface), 0.06);
    font-family: ui-monospace, monospace; font-size: 10.5px;
    color: rgba(var(--v-theme-on-surface), 0.6);
}
/* 第二枚 chip 不再 margin-left:auto,贴着第一枚 */
.linter-chip + .linter-chip { margin-left: 4px; }

/* ── 无差异补充条 ── 复用 CodeCheckResult.empty-issues 风格 */
.empty-issues {
    margin-top: 6px; padding: 6px 10px; border-radius: 4px;
    background: rgba(70, 200, 70, 0.06); color: #2da44e;
    font-size: 11.5px;
    display: flex; align-items: center; gap: 6px;
}
</style>
