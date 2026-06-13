<template>
    <!-- DEBUG: 临时诊断 toolName 实际值（修复后可移除） -->
    <div
        v-if="showDebug"
        style="padding:2px 6px;margin-bottom:4px;background:rgba(255,180,0,0.15);border-left:2px solid #b58400;font-family:ui-monospace,monospace;font-size:10.5px;color:#b58400"
    >
        [SpcodeToolResultView] toolName={{ JSON.stringify(toolName) }} matched={{ matchedKey ?? "NONE" }}
    </div>
    <CodeCheckResult v-if="toolName === 'code_check'" :data="parsedData" :args="args" />
    <CodeIndexResult v-else-if="toolName === 'code_index'" :data="parsedData" />
    <CodeExploreResult v-else-if="toolName === 'code_explore'" :data="parsedData" :args="args" />
    <EsSearchResult v-else-if="toolName === 'es_search'" :data="parsedData" :args="args" />
    <FileRemoveResult v-else-if="toolName === 'astrbot_file_remove'" :data="parsedData" />
    <FileDiffResult v-else-if="toolName === 'astrbot_file_compare'" :data="parsedData" :args="args" />
    <!--
      v2.2.0: 旧的 todo_list 工具被拆分为 todo_create / todo_query / todo_modify / todo_clear 4 个工具。
      全部路由到 TodoListResult,由它根据 toolName + args.mode 决定渲染哪种结果。
      旧 `todo_list` 保留以兼容老会话历史。
    -->
    <TodoListResult
      v-else-if="isTodoTool"
      :data="parsedData"
      :args="args"
      :tool-name="toolName"
    />
    <pre v-else class="result-raw">{{ formattedResult }}</pre>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CodeCheckResult from "./spcode_tools/CodeCheckResult.vue";
import CodeIndexResult from "./spcode_tools/CodeIndexResult.vue";
import CodeExploreResult from "./spcode_tools/CodeExploreResult.vue";
import EsSearchResult from "./spcode_tools/EsSearchResult.vue";
import FileRemoveResult from "./spcode_tools/FileRemoveResult.vue";
import FileDiffResult from "./spcode_tools/FileDiffResult.vue";
import TodoListResult from "./spcode_tools/TodoListResult.vue";

/**
 * spcode_toolkit 工具的渲染分发入口。
 * v2.2.0 起共 11 个工具(7 原有 + 4 拆分的 todo_*);todo_list 老条目保留兼容。
 * 由 ToolResultView.vue 在 fallback 之前调用。
 */
const props = defineProps<{
    toolName: string;
    result: string;
    args?: Record<string, any>;
}>();

// DEBUG: 临时计算实际匹配的 key + 控制台日志
const TODO_TOOL_NAMES = new Set([
    "todo_create",
    "todo_query",
    "todo_modify",
    "todo_clear",
    "todo_list", // 兼容老历史
]);
const KNOWN_KEYS = [
    "code_check",
    "code_index",
    "code_explore",
    "es_search",
    "astrbot_file_remove",
    "astrbot_file_compare",
    "todo_create",
    "todo_query",
    "todo_modify",
    "todo_clear",
    "todo_list",
] as const;

/** 拆分的 4 个 todo_* 工具 + 老 todo_list 统一识别。 */
const isTodoTool = computed(() => TODO_TOOL_NAMES.has(props.toolName));
const matchedKey = computed(() => {
    if (!props.toolName) return null;
    const m = KNOWN_KEYS.find((k) => k === props.toolName);
    if (!m) {
        // eslint-disable-next-line no-console
        console.warn(
            "[SpcodeToolResultView] toolName not in known spcode set:",
            JSON.stringify(props.toolName),
            "len=",
            props.toolName.length,
            "charCodes=",
            [...props.toolName].map((c) => c.charCodeAt(0)).join(","),
        );
    }
    return m ?? null;
});
// DEBUG: 用 URL hash 控制是否显示诊断条（?spcode_debug=1）
const showDebug = computed(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("spcode_debug") === "1";
});

/** 解析 result JSON 字符串为对象，自动剥离 spcode 插件 unwrap() 加的 envelope。
 *
 * spcode 工具的 Python unwrap() 包装成功结果为 `{"ok": true, "data": {...}}`。
 * 失败结果或带 proposal/options 的结果不会被包装。
 * 子组件期望的是 unwrap 前的原始数据，所以这里做一次透明剥离。
 */
const parsedData = computed<any>(() => {
    if (!props.result) return {};
    let parsed: any;
    try {
        parsed = JSON.parse(props.result);
    } catch {
        return {};
    }
    if (!parsed || typeof parsed !== "object") return parsed;
    // 剥离外层 envelope: {ok: true, data: {...}} → {...}
    if (parsed.ok === true && parsed.data && typeof parsed.data === "object") {
        return parsed.data;
    }
    return parsed;
});

const formattedResult = computed(() => {
    if (!props.result) return "";
    try {
        return JSON.stringify(JSON.parse(props.result), null, 2);
    } catch {
        return props.result;
    }
});
</script>

<style scoped>
.result-raw {
    margin: 0;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11.5px;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 300px;
    overflow-y: auto;
    color: rgba(var(--v-theme-on-surface), 0.8);
}
</style>
