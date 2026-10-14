import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { computed, nextTick, reactive, ref, watch } from "vue";
import { compileStyle, compileTemplate, parse } from "vue/compiler-sfc";

const source = readFileSync(
  new URL("../src/components/shared/TraceDisplayer.vue", import.meta.url),
  "utf8",
);
const { descriptor } = parse(source);
const ast = ts.createSourceFile("trace.js", descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true);
const translations = JSON.parse(readFileSync(
  new URL("../src/i18n/locales/zh-CN/features/trace.json", import.meta.url),
  "utf8",
));
const configTranslations = JSON.parse(readFileSync(
  new URL("../src/i18n/locales/zh-CN/features/config.json", import.meta.url), "utf8",
));

function setup(t, records) {
  const selectedEvent = ref({ records, first_time: 1, last_time: 2 });
  const context = vm.createContext({
    computed, reactive, ref, watch, selectedEvent, clockNow: ref(2),
    plugins: ref({ weather: { display_name: "Weather Forecast" } }),
    configTm(key) {
      const text = key.split(".").reduce((value, part) => value?.[part], configTranslations);
      assert.equal(typeof text, "string", `Missing config translation: ${key}`);
      return text;
    },
    tm(key, params = {}) {
      const text = key.split(".").reduce((value, part) => value?.[part], translations);
      assert.equal(typeof text, "string", `Missing translation: ${key}`);
      return text.replace(/\{(\w+)\}/g, (_, name) => String(params[name]));
    },
  });
  const names = new Set([
    "selectedSpanId", "expandedGroups", "expandedAgents", "expandedDetails", "actionLabels", "selectedStats", "selectedTokenUsage",
    "selectedRecords", "timelineGroups", "timelineRows", "timelineRecords",
    "recordLabel", "recordSubtitle", "formatDuration", "normalizeTracePayload",
  ]);
  const statements = ast.statements.filter((node) =>
    ts.isFunctionDeclaration(node) ? names.has(node.name?.text) :
      ts.isVariableStatement(node) && names.has(node.declarationList.declarations[0]?.name.getText(ast)),
  );
  assert.equal(statements.length, names.size);
  const watcher = ast.statements.find((node) => node.getText(ast).startsWith("watch(selectedSpanId,"));
  vm.runInContext(statements.map((node) => node.getText(ast)).join("\n"), context);
  const stop = vm.runInContext(watcher.getText(ast), context);
  t.after(stop);
  return vm.runInContext("({ selectedEvent, selectedSpanId, selectedStats, selectedTokenUsage, selectedRecords, timelineGroups, timelineRows, expandedGroups, expandedAgents, expandedDetails, recordLabel, recordSubtitle, normalizeTracePayload })", context);
}

function handler(key, category = "listener", fields = {}) {
  return {
    key, action: "handler_start", kind: "plugin_handler", time: 1,
    fields: {
      plugin: "test_plugin", plugin_display_name: "Test Plugin",
      handler: key, handler_full_name: `test_plugin.${key}`,
      handler_category: category, handler_type: "AdapterMessageEvent", ...fields,
    },
  };
}

test("collapse adjacent handlers by category without reordering separated records", (t) => {
  const state = setup(t, [
    { key: "received", action: "event_received", fields: { platform_id: "qq" } },
    handler("first"), handler("second", "listener", { plugin: "another_plugin", plugin_display_name: "Another Plugin" }),
    handler("hook1", "hook"), handler("hook2", "hook"),
    { key: "response", action: "response_sent", kind: "response", fields: { message: "Hello" } },
    handler("last"),
  ]);
  assert.equal(state.timelineGroups.value.length, 5);
  assert.deepEqual(Array.from(state.timelineRows.value, (row) => row.record.key), ["received", "first", "hook1", "response", "last"]);
  const listener = state.timelineRows.value[1];
  assert.equal(listener.expanded, false);
  assert.equal(listener.group.records.length, 2);
  assert.equal(listener.plugins, "Test Plugin, Another Plugin");
  assert.equal(state.recordLabel(listener.record, true), "触发多个插件处理器 (事件监听器)");
  assert.equal(state.recordLabel(state.timelineRows.value[2].record, true), "触发多个插件处理器 (事件钩子)");
  assert.equal(state.selectedStats.value.handlers, 5);
});

test("expansion keeps all handler details and stays open when new records arrive", async (t) => {
  const state = setup(t, [handler("first"), handler("second")]);
  const key = state.timelineGroups.value[0].key;
  state.expandedGroups.add(key);
  assert.deepEqual(Array.from(state.timelineRows.value, (row) => row.key), ["first:group", "first", "second"]);
  assert.equal(state.timelineRows.value[1].nested, true);
  assert.equal(state.timelineRows.value[1].record.fields.handler_full_name, "test_plugin.first");
  state.selectedEvent.value.records.push(handler("third"));
  assert.equal(state.timelineRows.value[0].expanded, true);
  assert.equal(state.timelineRows.value.length, 4);
  state.expandedGroups.delete(key);
  assert.equal(state.timelineRows.value.length, 1);
  state.expandedGroups.add(key);
  state.selectedSpanId.value = "another-message";
  await nextTick();
  assert.equal(state.expandedGroups.size, 0);
});

test("collapsed groups expose errors and preserve actual handler and response counts", (t) => {
  const state = setup(t, [
    handler("first"),
    { key: "first:end", action: "handler_end", fields: { handler_full_name: "test_plugin.first", status: "error", error: "Handler failed", duration_ms: 12 } },
    handler("second"),
    { key: "response1", action: "response_sent", kind: "response", fields: { message: "First response" } },
    { key: "response2", action: "response_sent", kind: "response", fields: { message: "Second response" } },
  ]);
  assert.equal(state.timelineRows.value.length, 2);
  assert.equal(state.timelineRows.value[0].errors, 1);
  assert.equal(state.timelineRows.value[0].group.records[0].fields.error, "Handler failed");
  assert.equal(state.selectedStats.value.handlers, 2);
  assert.equal(state.selectedStats.value.responses, 2);
  assert.equal(state.recordLabel(state.timelineRows.value[1].record, true), "发送多个响应");
  state.expandedGroups.add(state.timelineRows.value[1].group.key);
  assert.equal(state.timelineRows.value[2].record.fields.message, "First response");
  assert.equal(state.timelineRows.value[3].record.fields.message, "Second response");
});

test("empty and singleton timelines do not create group headers", (t) => {
  const state = setup(t, []);
  assert.equal(state.timelineRows.value.length, 0);
  state.selectedEvent.value.records.push(handler("single", "command"));
  assert.equal(state.timelineRows.value.length, 1);
  assert.equal(state.timelineRows.value[0].group, undefined);
  assert.equal(state.recordLabel(state.timelineRows.value[0].record), "触发插件处理器 (指令/指令组)");
});

test("chips reuse profile runner names and classify responses by their sending owner", (t) => {
  const state = setup(t, [
    { key: "agent1", action: "agent_start", kind: "agent", fields: { runner_type: "local" } },
    { key: "agent2", action: "agent_start", kind: "agent", fields: { runner_type: "dify" } },
    { key: "system", action: "response_sent", kind: "response", fields: { source: "core" } },
    { key: "legacy", action: "response_sent", kind: "response", fields: { source: "agent" } },
    { key: "plugin", action: "response_sent", kind: "response", fields: { source: "plugin:weather" } },
  ]);
  const rows = state.timelineRows.value;
  assert.deepEqual(Array.from(rows[0].metadata), ["执行方式：AstrBot 内置 AI", "执行方式：Dify"]);
  assert.deepEqual(Array.from(rows[1].metadata), ["系统发送", "插件发送：Weather Forecast"]);
  assert.equal(state.recordSubtitle({ action: "agent_start", fields: { runner_type: "custom_runner" } }), "custom_runner");
  assert.equal(state.recordSubtitle({ action: "response_sent", fields: { source: "unknown" } }), "来源未知");
  assert.equal(state.recordSubtitle({ action: "response_sent", fields: { source: "plugin:uninstalled" } }), "插件发送：uninstalled");
});

test("Agent folding follows span ancestry, keeps responses visible, and preserves interleaved branches", (t) => {
  const state = setup(t, [
    { key: "received", action: "event_received", operation_span_id: "root", parent_span_id: null, time: 1, fields: {} },
    { key: "agent", action: "agent_start", operation_span_id: "agent", parent_span_id: "root", time: 1.01, kind: "agent", fields: {} },
    { key: "persona", action: "sel_persona", owner_span_id: "agent", time: 1.02, fields: {} },
    { ...handler("inner"), operation_span_id: "plugin", parent_span_id: "agent", time: 1.03, fields: { ...handler("inner").fields, status: "error" } },
    { key: "tool", action: "agent_tool_call", operation_span_id: "tool", parent_span_id: "plugin", time: 1.04, fields: {} },
    { ...handler("other"), operation_span_id: "other", parent_span_id: "root", time: 1.05 },
    { key: "tool-result", action: "agent_tool_result", owner_span_id: "tool", time: 1.06, fields: {} },
    { key: "response", action: "response_sent", kind: "response", owner_span_id: "agent", time: 1.07, fields: { message: "Reply", source: "core" } },
    { key: "model-done", action: "astr_agent_complete", owner_span_id: "agent", time: 1.08, fields: {} },
    { key: "agent:end", action: "agent_end", operation_span_id: "agent", parent_span_id: "root", time: 1.09, fields: { status: "success", duration_ms: 80 } },
    { key: "done", action: "pipeline_end", operation_span_id: "root", parent_span_id: null, time: 1.1, fields: {} },
  ]);
  assert.deepEqual(Array.from(state.timelineRows.value, (row) => row.record.key), ["received", "agent", "other", "response", "done"]);
  const agent = state.timelineRows.value[1];
  assert.equal(agent.agentId, "agent");
  assert.equal(agent.expanded, false);
  assert.equal(agent.errors, 1);
  assert.equal(agent.record.fields.duration_ms, 80);
  assert.equal(state.selectedStats.value.handlers, 2);
  assert.equal(state.selectedStats.value.responses, 1);
  state.expandedAgents.add("agent");
  assert.deepEqual(Array.from(state.timelineRows.value, (row) => row.record.key), [
    "received", "agent", "inner", "tool", "other", "tool-result", "response", "model-done", "done",
  ]);
  assert.equal(state.timelineRows.value.find((row) => row.record.key === "tool-result").depth, 1);
  assert.equal(state.timelineRows.value.find((row) => row.record.key === "other").depth, 0);
  assert.equal(state.timelineRows.value.find((row) => row.record.key === "response").depth, 0);
});

test("nested and concurrent Agents fold independently, without grouping distinct spans", (t) => {
  const state = setup(t, [
    { key: "outer", action: "agent_start", operation_span_id: "outer", parent_span_id: "root", fields: {} },
    { key: "inner", action: "agent_start", operation_span_id: "inner", parent_span_id: "outer", fields: {} },
    { key: "parallel", action: "agent_start", operation_span_id: "parallel", parent_span_id: "root", fields: {} },
    { key: "nested-event", action: "astr_agent_prepare", owner_span_id: "inner", fields: {} },
    { key: "parallel-event", action: "astr_agent_prepare", owner_span_id: "parallel", fields: {} },
  ]);
  assert.deepEqual(Array.from(state.timelineRows.value, (row) => row.record.key), ["outer", "parallel"]);
  state.expandedAgents.add("outer");
  assert.deepEqual(Array.from(state.timelineRows.value, (row) => row.record.key), ["outer", "inner", "parallel"]);
  state.expandedAgents.add("inner");
  state.expandedAgents.add("parallel");
  assert.deepEqual(Array.from(state.timelineRows.value, (row) => row.record.key), ["outer", "inner", "parallel", "nested-event", "parallel-event"]);
  assert.equal(state.timelineRows.value.find((row) => row.record.key === "nested-event").depth, 2);
});

test("Agent expansion survives incoming descendants and resets with detail/group state on selection changes", async (t) => {
  const state = setup(t, [{ key: "agent", action: "agent_start", operation_span_id: "agent", parent_span_id: "root", fields: {} }]);
  state.expandedAgents.add("agent");
  state.expandedDetails.add("agent");
  state.selectedEvent.value.records.push({ key: "new-event", action: "astr_agent_prepare", owner_span_id: "agent", fields: {} });
  assert.equal(state.timelineRows.value[0].expanded, true);
  assert.equal(state.timelineRows.value.length, 2);
  state.selectedSpanId.value = "other-trace";
  await nextTick();
  assert.equal(state.expandedAgents.size, 0);
  assert.equal(state.expandedDetails.size, 0);
  assert.equal(state.timelineRows.value.length, 1);
});

test("canonical span events retain their owning span for Agent folding", (t) => {
  const state = setup(t, []);
  const normalized = state.normalizeTracePayload({
    trace: { trace_id: "trace", root_span_id: "root", state: "completed", attributes: {}, start_time_unix_nano: "1000000000" },
    spans: [
      { span_id: "root", parent_span_id: null, start_time_unix_nano: "1000000000", attributes: {} },
      { span_id: "agent", parent_span_id: "root", start_time_unix_nano: "1100000000", attributes: { "astrbot.kind": "agent" } },
      { span_id: "plugin", parent_span_id: "agent", start_time_unix_nano: "1200000000",
        attributes: { "astrbot.kind": "plugin_handler", "astrbot.handler_category": "hook" },
        events: [{ event_id: "event", span_id: "plugin", name: "astr_agent_prepare", time_unix_nano: "1300000000", attributes: {} }] },
    ],
  });
  assert.equal(normalized.records.find((record) => record.record_id === "event").owner_span_id, "plugin");
  state.selectedEvent.value.records = normalized.records.sort((a, b) => a.time - b.time).map((record) => ({ ...record, key: record.record_id }));
  assert.equal(state.timelineRows.value.length, 2);
  state.expandedAgents.add("agent");
  assert.equal(state.timelineRows.value.length, 4);
});

test("token card uses the latest cumulative snapshot per Agent and includes cached input once", (t) => {
  const state = setup(t, [
    { action: "astr_agent_complete", owner_span_id: "agent-a", fields: { stats: { token_usage: { input_other: 50, input_cached: 10, output: 20 } } } },
    { action: "astr_agent_complete", owner_span_id: "agent-a", fields: { stats: { token_usage: { input_other: 100, input_cached: 40, output: 30 } } } },
    { action: "astr_agent_complete", owner_span_id: "agent-b", fields: { stats: { token_usage: { input_other: 10, input_cached: 5, output: 15 } } } },
    { action: "handler_start", kind: "plugin_handler", fields: { stats: { token_usage: { input_other: 999, input_cached: 999, output: 999 } } } },
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(state.selectedTokenUsage.value)), { total: 200, input: 155, output: 45, cached: 45 });
});

test("missing or invalid usage is not represented as a reported zero", (t) => {
  const state = setup(t, []);
  assert.equal(state.selectedTokenUsage.value, null);
  state.selectedEvent.value.records.push({ action: "astr_agent_complete", fields: { stats: { token_usage: { input_other: 0, input_cached: 0, output: 0 } } } });
  assert.equal(state.selectedTokenUsage.value, null);
  state.selectedEvent.value.records.push({ action: "astr_agent_complete", fields: { stats: { token_usage: { input_other: -1, input_cached: 0, output: 12 } } } });
  assert.equal(state.selectedTokenUsage.value, null);
  state.selectedEvent.value.records.push({ action: "astr_agent_complete", fields: { stats: { token_usage: { input_other: 8, input_cached: 2, output: 5 } } } });
  assert.equal(state.selectedTokenUsage.value.total, 15);
});

test("canonical span kinds drive call transitions and nanosecond timestamps determine duration", (t) => {
  const state = setup(t, []);
  const normalize = (attributes) => state.normalizeTracePayload({
    trace: { trace_id: "trace", root_span_id: "root", state: "completed", attributes: {}, start_time_unix_nano: "1791909368256084000" },
    spans: [{ span_id: "call", parent_span_id: "root", start_time_unix_nano: "1791909368256084000", end_time_unix_nano: "1791909368264126000", status: { code: 1 }, attributes }],
  }).records;
  for (const [kind, start, end] of [["plugin_handler", "handler_start", "handler_end"], ["agent", "agent_start", "agent_end"], ["tool", "agent_tool_call", "agent_tool_result"]]) {
    const records = normalize({ "astrbot.kind": kind, "astrbot.handler_type": "AdapterMessageEvent" });
    assert.deepEqual(Array.from(records, (record) => record.action), [start, end]);
    assert.equal(records[1].fields.duration_ms, 8.042);
    assert.equal(records[0].fields.handler_type, "AdapterMessageEvent");
    assert.equal(records[0].fields.action, undefined);
    assert.equal(records[0].fields.end_action, undefined);
  }
  const oldTool = normalize({ "astrbot.action": "agent_tool_call", "astrbot.end_action": "agent_tool_result", "astrbot.duration_ms": 999 });
  assert.equal(oldTool[0].action, "agent_tool_call");
  assert.equal(oldTool[1].action, "agent_tool_result");
  assert.equal(oldTool[1].fields.duration_ms, 8.042);
});

test("missing parents and cyclic span links cannot hang the timeline or hide unrelated records", (t) => {
  const state = setup(t, [
    { key: "missing", action: "astr_agent_prepare", owner_span_id: "absent", fields: {} },
    { key: "cycle", action: "agent_start", operation_span_id: "cycle", parent_span_id: "cycle", fields: {} },
    { ...handler("plugin"), operation_span_id: "plugin", parent_span_id: "plugin" },
  ]);
  assert.deepEqual(Array.from(state.timelineRows.value, (row) => row.record.key), ["missing", "cycle", "plugin"]);
});

test("group template and stacked icon styles compile, and all locales include group labels", () => {
  assert.equal(translations.compact.pluginHandler, "调用插件");
  assert.match(descriptor.template.content, /selectedTokenUsage.total >= 1000000/);
  assert.match(descriptor.template.content, /toFixed\(2\) \+ " M"/);
  assert.match(descriptor.template.content, /toFixed\(2\) \+ " k"/);
  assert.match(descriptor.template.content, /v-if="record.fields.handler_type && record.fields.handler_type !== 'AdapterMessageEvent'"/);
  const template = compileTemplate({ source: descriptor.template.content, filename: "TraceDisplayer.vue", id: "trace-groups" });
  assert.deepEqual(template.errors, []);
  const styles = compileStyle({ source: descriptor.styles[0].content, filename: "TraceDisplayer.vue", id: "trace-groups", scoped: true });
  assert.deepEqual(styles.errors, []);
  assert.match(descriptor.template.content, /:aria-expanded="row.expanded"/);
  assert.match(descriptor.template.content, /row.group.records.slice\(0, 3\)/);
  assert.match(descriptor.template.content, /<v-chip[^>]*timeline-metadata-chip/);
  assert.match(descriptor.template.content, /expandedAgents.delete\(row.agentId\)/);
  assert.match(descriptor.template.content, /timeline-row-toggle/);
  assert.doesNotMatch(descriptor.template.content, /timeline-group-expansion|tm\("details"\)/);
  assert.match(descriptor.template.content, /<time :title="formatTime\(row.record.time\)">\+\{\{ formatDuration/);
  assert.doesNotMatch(descriptor.template.content.match(/<div class="trace-timeline">[\s\S]*?<\/main>/)[0], /color="primary"/);
  for (const locale of ["en-US", "ja-JP", "ru-RU"]) {
    const data = JSON.parse(readFileSync(new URL(`../src/i18n/locales/${locale}/features/trace.json`, import.meta.url), "utf8").replace(/^\uFEFF/, ""));
    assert.deepEqual(Object.keys(data.groups).sort(), Object.keys(translations.groups).sort());
    assert.deepEqual(Object.keys(data.chips).sort(), Object.keys(translations.chips).sort());
    assert.deepEqual(Object.keys(data.columns).sort(), Object.keys(translations.columns).sort());
    assert.deepEqual(Object.keys(data.compact).sort(), Object.keys(translations.compact).sort());
  }
});
