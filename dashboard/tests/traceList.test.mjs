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
  const historyRequests = [];
  const detailRequests = [];
  const context = vm.createContext({
    computed, nextTick, reactive, ref, watch, tm: (key) => key,
    getPlatformIcon: (name) => name + ".png",
    console: { error() {} },
    traceApi: {
      history: (options) => new Promise((resolve, reject) => historyRequests.push({ options, resolve, reject })),
      detail: (id) => new Promise((resolve, reject) => detailRequests.push({ id, resolve, reject })),
    },
    pluginApi: { list: async () => ({ data: { data: [] } }) },
    sessionApi: { activeUmos: async () => ({ data: { data: { umo_infos: [] } } }) },
    document: { querySelector: (selector) => ({ scrollIntoView() {}, focus() { focused.push(selector); } }) },
  });
  const names = new Set([
    "events", "selectedSpanId", "searchText", "selectedFilters", "umoNames", "clockNow",
    "eventIndex", "maxItems", "selectedEvent", "normalizedSearch", "filteredEvents", "traceRows", "traceHeaders",
    "processNewTraces", "normalizeTracePayload", "matchesFilter", "recordSearchText", "timelineRecords", "formatDuration", "selectEvent",
    "fetchTraceHistory", "loadTraceDetail", "historyBusy", "detailBusy", "historyError", "detailError",
    "totalRecords", "historyPage", "pageSize", "storageWarning", "metadataLoaded", "historyRequest", "detailRequest", "plugins", "loading",
  ]);
  const statements = ast.statements.filter((node) =>
    ts.isFunctionDeclaration(node) ? names.has(node.name?.text) :
      ts.isVariableStatement(node) && names.has(node.declarationList.declarations[0]?.name.getText(ast)),
  );
  assert.equal(statements.length, names.size);
  vm.runInContext(statements.map((node) => node.getText(ast)).join("\n"), context);
  const watcher = ast.statements.find((node) => node.getText(ast).startsWith("watch(filteredEvents,"));
  t.after(vm.runInContext(watcher.getText(ast), context));
  return { focused, historyRequests, detailRequests, ...vm.runInContext("({ events, selectedSpanId, selectedEvent, selectedFilters, traceRows, traceHeaders, clockNow, processNewTraces, selectEvent, searchText, fetchTraceHistory, loadTraceDetail, totalRecords, historyPage, pageSize, historyBusy, detailBusy, historyError, detailError })", context) };
}

function record(span, action, time, fields = {}) {
  return { span_id: span, record_id: span + ":" + action + ":" + time, action, time, fields };
}

function canonical(id, stamp = "2000000000", completed = true) {
  return {
    trace_id: id, root_span_id: id.slice(0, 16), name: "message",
    start_time_unix_nano: "1000000000", updated_time_unix_nano: stamp,
    end_time_unix_nano: completed ? stamp : null,
    state: completed ? "completed" : "running", has_errors: false,
    has_models: true, has_plugins: true, span_count: 3,
    attributes: { "astrbot.message_outline": "Hello", "astrbot.plugins": "Weather" },
  };
}

test("canonical live updates keep summaries only and count real spans, not events", async (t) => {
  const state = setup(t);
  const trace = canonical("a".repeat(32));
  state.processNewTraces([{ trace, event: { event_id: "reply", name: "response_sent", time_unix_nano: "2000000000", attributes: { "astrbot.message": "Reply" } } }]);
  assert.equal(state.events.value[0].records.length, 0);
  assert.equal(state.traceRows.value[0].spans, 3);
  assert.equal(state.events.value[0].completed, true);
  state.processNewTraces([{ trace: canonical(trace.trace_id, "1500000000", false) }]);
  assert.equal(state.events.value[0].completed, true);
  state.selectEvent(trace.trace_id);
  state.detailRequests[0].resolve({ data: { status: "ok", data: {
    trace, spans: [{
      trace_id: trace.trace_id, span_id: trace.root_span_id, parent_span_id: null,
      start_time_unix_nano: "1000000000", end_time_unix_nano: "2000000000",
      status: { code: 1 }, attributes: {},
      events: [{ event_id: "reply", name: "response_sent", time_unix_nano: "2000000000", attributes: { "astrbot.message": "Reply" } }],
    }],
  } } });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(state.events.value[0].records.length, 3);
  assert.equal(state.traceRows.value[0].spans, 3);
  state.selectEvent(null);
  assert.equal(state.events.value[0].records.length, 0);
});

test("history replaces numbered pages and ignores a superseded search response", async (t) => {
  const state = setup(t);
  const first = state.fetchTraceHistory();
  await new Promise((resolve) => setImmediate(resolve));
  state.historyRequests[0].resolve({ data: { status: "ok", data: {
    traces: [canonical("a".repeat(32))], total: 51, cursor: "next", storage: {},
  } } });
  await first;
  assert.equal(state.totalRecords.value, 51);
  state.historyPage.value = 2;
  const more = state.fetchTraceHistory();
  assert.equal(state.historyRequests[1].options.page, 2);
  assert.equal(state.historyRequests[1].options.limit, 50);
  state.historyRequests[1].resolve({ data: { status: "ok", data: {
    traces: [canonical("b".repeat(32))], total: 51, cursor: null, storage: {},
  } } });
  await more;
  assert.equal(state.events.value.length, 1);
  const oldRequest = state.fetchTraceHistory();
  state.searchText.value = "New";
  const newRequest = state.fetchTraceHistory();
  state.historyRequests[3].resolve({ data: { status: "ok", data: { traces: [], total: 0, cursor: null } } });
  await newRequest;
  state.historyRequests[2].resolve({ data: { status: "ok", data: { traces: [canonical("c".repeat(32))], total: 500 } } });
  await oldRequest;
  assert.equal(state.totalRecords.value, 0);
  assert.equal(state.events.value.length, 0);
  assert.equal(state.historyBusy.value, false);
});

test("late detail responses cannot reopen a closed inspector or another trace", async (t) => {
  const state = setup(t);
  const a = canonical("a".repeat(32));
  const b = canonical("b".repeat(32));
  state.processNewTraces([{ trace: a }, { trace: b }]);
  state.selectEvent(a.trace_id);
  state.selectEvent(b.trace_id);
  state.detailRequests[1].resolve({ data: { status: "ok", data: { trace: b, spans: [] } } });
  await new Promise((resolve) => setImmediate(resolve));
  state.detailRequests[0].resolve({ data: { status: "ok", data: { trace: a, spans: [] } } });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(state.selectedEvent.value.span_id, b.trace_id);
  assert.equal(state.detailBusy.value, false);
  state.selectEvent(null);
  assert.equal(state.selectedEvent.value, null);
  assert.equal(state.events.value.find((event) => event.span_id === a.trace_id).records.length, 0);
});

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
  assert.match(descriptor.template.content, /<v-data-table-server/);
  assert.match(descriptor.template.content, /:items-per-page="pageSize"/);
  assert.match(descriptor.template.content, /:page="historyPage"/);
  assert.match(descriptor.template.content, /:items-length="totalRecords"/);
  assert.doesNotMatch(descriptor.template.content, /hide-default-footer|history.loadMore/);
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

test("table uses compact 13px text while density, spacing, and hover use Vuetify defaults", () => {
  const table = descriptor.template.content.match(/<v-data-table[\s\S]*?>/)[0];
  assert.match(table, /\s+hover\s/);
  assert.doesNotMatch(table, /density=/);
  assert.doesNotMatch(descriptor.styles[0].content, /:deep\(table|table-layout:\s*fixed|\.trace-list-row:hover/);
  const tableStyle = descriptor.styles[0].content.match(/\.trace-list-table\s*\{([^}]+)\}/)[1];
  assert.match(descriptor.styles[0].content, /\.trace-list\s*\{[^}]*isolation:\s*isolate/);
  assert.doesNotMatch(tableStyle, /font-size|padding|font-family/);
  assert.match(descriptor.styles[0].content, /:deep\(th\), \.trace-list-table :deep\(td\) \{ font-size: 13px;/);
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
