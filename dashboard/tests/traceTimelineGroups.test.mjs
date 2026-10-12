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
    "selectedSpanId", "expandedGroups", "actionLabels", "selectedStats",
    "selectedRecords", "timelineGroups", "timelineRows", "timelineRecords",
    "recordLabel", "recordSubtitle", "formatDuration",
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
  return vm.runInContext("({ selectedEvent, selectedSpanId, selectedStats, selectedRecords, timelineGroups, timelineRows, expandedGroups, recordLabel, recordSubtitle })", context);
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

test("group template and stacked icon styles compile, and all locales include group labels", () => {
  const template = compileTemplate({ source: descriptor.template.content, filename: "TraceDisplayer.vue", id: "trace-groups" });
  assert.deepEqual(template.errors, []);
  const styles = compileStyle({ source: descriptor.styles[0].content, filename: "TraceDisplayer.vue", id: "trace-groups", scoped: true });
  assert.deepEqual(styles.errors, []);
  assert.match(descriptor.template.content, /:aria-expanded="row.expanded"/);
  assert.match(descriptor.template.content, /row.group.records.slice\(0, 3\)/);
  assert.match(descriptor.template.content, /<v-chip[^>]*timeline-metadata-chip/);
  for (const locale of ["en-US", "ja-JP", "ru-RU"]) {
    const data = JSON.parse(readFileSync(new URL(`../src/i18n/locales/${locale}/features/trace.json`, import.meta.url), "utf8").replace(/^\uFEFF/, ""));
    assert.deepEqual(Object.keys(data.groups).sort(), Object.keys(translations.groups).sort());
    assert.deepEqual(Object.keys(data.chips).sort(), Object.keys(translations.chips).sort());
    assert.deepEqual(Object.keys(data.columns).sort(), Object.keys(translations.columns).sort());
  }
});
