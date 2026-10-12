import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { computed, nextTick, reactive, ref, watch } from "vue";
import { compileStyle, compileTemplate, parse } from "vue/compiler-sfc";

const source = readFileSync(new URL("../src/components/shared/TraceDisplayer.vue", import.meta.url), "utf8");
const { descriptor } = parse(source);
const ast = ts.createSourceFile("trace.js", descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true);

function setup(t) {
  const focused = [];
  const context = vm.createContext({
    computed, nextTick, reactive, ref, watch, tm: (key) => key,
    getPlatformIcon: (name) => name + ".png",
    document: { querySelector: (selector) => ({ scrollIntoView() {}, focus() { focused.push(selector); } }) },
  });
  const names = new Set([
    "events", "selectedSpanId", "searchText", "selectedFilters", "umoNames", "clockNow",
    "eventIndex", "maxItems", "selectedEvent", "normalizedSearch", "filteredEvents", "traceRows", "traceHeaders",
    "processNewTraces", "matchesFilter", "recordSearchText", "timelineRecords", "formatDuration", "selectEvent",
  ]);
  const statements = ast.statements.filter((node) =>
    ts.isFunctionDeclaration(node) ? names.has(node.name?.text) :
      ts.isVariableStatement(node) && names.has(node.declarationList.declarations[0]?.name.getText(ast)),
  );
  assert.equal(statements.length, names.size);
  vm.runInContext(statements.map((node) => node.getText(ast)).join("\n"), context);
  const watcher = ast.statements.find((node) => node.getText(ast).startsWith("watch(filteredEvents,"));
  t.after(vm.runInContext(watcher.getText(ast), context));
  return { focused, ...vm.runInContext("({ events, selectedSpanId, selectedEvent, selectedFilters, traceRows, traceHeaders, clockNow, processNewTraces, selectEvent })", context) };
}

function record(span, action, time, fields = {}) {
  return { span_id: span, record_id: span + ":" + action + ":" + time, action, time, fields };
}

test("history and new traces leave the full-width list unselected", async (t) => {
  const state = setup(t);
  state.processNewTraces([record("first", "event_received", 1, { platform_id: "qq-1", platform_name: "qq_official", message: "Hello" })]);
  await nextTick();
  assert.equal(state.selectedSpanId.value, null);
  assert.equal(state.selectedEvent.value, null);
  assert.equal(state.traceRows.value.length, 1);
  assert.equal(state.traceRows.value[0].event.platform_icon, "qq_official.png");
  state.processNewTraces([record("second", "event_received", 2)]);
  await nextTick();
  assert.equal(state.selectedEvent.value, null);
  assert.equal(state.traceRows.value.length, 2);
});

test("selecting opens details, closing restores row focus, and filtering never auto-selects", async (t) => {
  const state = setup(t);
  state.processNewTraces([record("first", "event_received", 1), record("second", "event_received", 2)]);
  state.selectEvent("first");
  await nextTick();
  assert.equal(state.selectedEvent.value.span_id, "first");
  state.selectedFilters.value = ["errors"];
  await nextTick();
  assert.equal(state.selectedEvent.value, null);
  state.selectedFilters.value = [];
  await nextTick();
  assert.equal(state.selectedEvent.value, null);
  state.selectEvent("second");
  await nextTick();
  state.selectEvent(null);
  await nextTick();
  assert.equal(state.selectedEvent.value, null);
  assert.equal(state.focused[0], '[data-trace-id="second"]');
  state.processNewTraces([record("third", "event_received", 3)]);
  await nextTick();
  assert.equal(state.selectedEvent.value, null);
});

test("Spans pairs operation records and ignores hidden stages without changing message counts", (t) => {
  const state = setup(t);
  state.processNewTraces([
    record("first", "event_received", 1),
    record("first", "handler_start", 2, { kind: "plugin_handler", handler_full_name: "plugin.handler" }),
    record("first", "handler_end", 3, { handler_full_name: "plugin.handler", status: "success" }),
    record("first", "agent_start", 4, { kind: "agent" }),
    record("first", "agent_end", 5, { status: "success" }),
    record("first", "stage_start", 6),
    record("first", "response_ready", 7, { kind: "response" }),
    record("first", "response_sent", 8, { kind: "response" }),
    record("first", "pipeline_end", 9, { status: "success" }),
  ]);
  assert.equal(state.traceRows.value.length, 1);
  assert.equal(state.traceRows.value[0].spans, 5);
  assert.equal(state.traceRows.value[0].event.status, "success");
});

test("duration updates while running or errored-but-active and freezes on completion", (t) => {
  const state = setup(t);
  state.clockNow.value = 10;
  state.processNewTraces([record("first", "event_received", 1)]);
  assert.equal(state.traceRows.value[0].duration, "9.00 s");
  state.clockNow.value = 12;
  assert.equal(state.traceRows.value[0].duration, "11.00 s");
  state.processNewTraces([record("first", "handler_end", 3, { status: "error" })]);
  state.clockNow.value = 13;
  assert.equal(state.traceRows.value[0].duration, "12.00 s");
  state.processNewTraces([record("first", "pipeline_end", 14, { status: "success" })]);
  state.clockNow.value = 30;
  assert.equal(state.traceRows.value[0].duration, "13.00 s");
  assert.equal(state.traceRows.value[0].event.status, "error");
});

test("Vuetify datatable keeps the requested columns and explicit detail selection", (t) => {
  const state = setup(t);
  assert.deepEqual(Array.from(state.traceHeaders.value, (header) => header.title), [
    "columns.status", "columns.platform", "columns.timestamp",
    "columns.duration", "columns.message", "UMO", "columns.sender", "Spans",
  ]);
  const platformHeader = state.traceHeaders.value.find((header) => header.key === "platform");
  assert.equal(platformHeader.width, 112);
  assert.equal(platformHeader.minWidth, 112);
  assert.equal(platformHeader.headerProps.class, "text-no-wrap");
  const zh = JSON.parse(readFileSync(new URL("../src/i18n/locales/zh-CN/features/trace.json", import.meta.url), "utf8"));
  assert.equal(zh.columns.duration, "时长");
  assert.match(descriptor.template.content, /<v-data-table/);
  assert.match(descriptor.template.content, /item-value="event.span_id"/);
  assert.match(descriptor.template.content, /:items-per-page="-1"/);
  assert.match(descriptor.template.content, /hide-default-footer/);
  assert.doesNotMatch(descriptor.template.content, /#item=/);
  for (const key of ["status", "platform", "timestamp", "duration", "message", "umo", "sender", "spans"]) {
    assert.match(descriptor.template.content, new RegExp("#item\\." + key + "="));
  }
  assert.match(descriptor.template.content, /@click:row="\(_, \{ item \}\) => selectEvent\(item.event.span_id\)"/);
  assert.match(descriptor.template.content, /<main v-if="selectedEvent"/);
  assert.match(descriptor.template.content, /tm\('closeDetails'\)/);
  assert.match(descriptor.scriptSetup.content, /clearInterval\(durationTimer.value\)/);
});

test("native table rows retain trace identity, selection, and keyboard activation", () => {
  const selections = [];
  const expression = descriptor.template.content.match(/:row-props="([\s\S]*?)"/)[1];
  const rowProps = vm.runInNewContext("(" + expression + ")", {
    selectedSpanId: "first",
    selectEvent: (id) => selections.push(id),
  });
  const props = rowProps({ item: { event: { span_id: "first" } } });
  assert.equal(props["data-trace-id"], "first");
  assert.equal(props["aria-selected"], true);
  assert.equal(props.class.selected, true);
  assert.equal(props.tabindex, 0);
  let prevented = 0;
  for (const key of ["Enter", " ", "ArrowDown"]) {
    props.onKeydown({ key, preventDefault() { prevented++; } });
  }
  assert.deepEqual(selections, ["first", "first"]);
  assert.equal(prevented, 2);
  assert.equal(rowProps({ item: { event: { span_id: "second" } } }).class.selected, false);
});

test("table typography, density, spacing, and hover use Vuetify defaults", () => {
  const table = descriptor.template.content.match(/<v-data-table[\s\S]*?>/)[0];
  assert.match(table, /\s+hover\s/);
  assert.doesNotMatch(table, /density=/);
  assert.doesNotMatch(descriptor.styles[0].content, /:deep\(table|table-layout:\s*fixed|\.trace-list-row:hover/);
  const tableStyle = descriptor.styles[0].content.match(/\.trace-list-table\s*\{([^}]+)\}/)[1];
  assert.doesNotMatch(tableStyle, /font-size|padding|font-family/);
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: "TraceDisplayer.vue", id: "trace-native" }).errors, []);
  assert.deepEqual(compileStyle({ source: descriptor.styles[0].content, filename: "TraceDisplayer.vue", id: "trace-native", scoped: true }).errors, []);
});

test("trace tab stays flat without outer cards or a tinted list container", () => {
  const page = parse(readFileSync(new URL("../src/views/TracePage.vue", import.meta.url), "utf8")).descriptor;
  assert.doesNotMatch(page.template.content, /trace-card/);
  assert.doesNotMatch(page.styles[0].content, /--trace-card|\.trace-card/);
  const explorer = descriptor.styles[0].content.match(/\.trace-explorer\s*\{([^}]+)\}/)[1];
  assert.match(explorer, /background:\s*transparent/);
  assert.match(explorer, /border:\s*0/);
  assert.match(explorer, /border-radius:\s*0/);
  assert.deepEqual(compileTemplate({ source: page.template.content, filename: "TracePage.vue", id: "trace-flat" }).errors, []);
  assert.deepEqual(compileStyle({ source: page.styles[0].content, filename: "TracePage.vue", id: "trace-flat", scoped: true }).errors, []);
});
