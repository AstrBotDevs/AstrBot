<template>
    <CodeFormatResult v-if="toolName === 'code_format'" :data="parsedData" :args="args" />
    <CodeCheckResult v-else-if="toolName === 'code_check'" :data="parsedData" :args="args" />
    <CodeIndexResult v-else-if="toolName === 'code_index'" :data="parsedData" />
    <CodeExploreResult v-else-if="toolName === 'code_explore'" :data="parsedData" :args="args" />
    <EsSearchResult v-else-if="toolName === 'es_search'" :data="parsedData" :args="args" />
    <FileRemoveResult v-else-if="toolName === 'astrbot_file_remove'" :data="parsedData" />
    <FileDiffResult v-else-if="toolName === 'astrbot_file_compare'" :data="parsedData" :args="args" />
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
import CodeFormatResult from "./spcode_tools/CodeFormatResult.vue";
import CodeIndexResult from "./spcode_tools/CodeIndexResult.vue";
import CodeExploreResult from "./spcode_tools/CodeExploreResult.vue";
import EsSearchResult from "./spcode_tools/EsSearchResult.vue";
import FileRemoveResult from "./spcode_tools/FileRemoveResult.vue";
import FileDiffResult from "./spcode_tools/FileDiffResult.vue";
import TodoListResult from "./spcode_tools/TodoListResult.vue";

/**
 * spcode_toolkit 工具的渲染分发入口。
 */
const props = defineProps<{
    toolName: string;
    result: string;
    args?: Record<string, any>;
}>();

/** todo_* 工具统一识别。
 *  - v2.12+ 6 个独立工具:create / query / add / update / delete / clear
 *  - 兼容:v2.12 之前 todo_modify、v2.2.0 之前 todo_list
 */
const TODO_TOOL_NAMES: ReadonlySet<string> = new Set([
    "todo_create",
    "todo_query",
    "todo_add",
    "todo_update",
    "todo_delete",
    "todo_clear",
    "todo_modify", // legacy (v2.12 之前)
    "todo_list", // legacy (v2.2.0 之前)
]);
const isTodoTool = computed(() => TODO_TOOL_NAMES.has(props.toolName));

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
