import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { computed, nextTick, reactive, ref, watch } from "vue";
import { parse } from "vue/compiler-sfc";

const source = readFileSync(new URL("../src/components/shared/TraceDisplayer.vue", import.meta.url), "utf8");
const { descriptor } = parse(source);
const ast = ts.createSourceFile("trace.js", descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true);

function setup(t) {
  const focused = [];
  const context = vm.createContext({
    computed, nextTick, reactive, ref, watch,
    getPlatformIcon: (name) => name + ".png",
    document: { querySelector: (selector) => ({ scrollIntoView() {}, focus() { focused.push(selector); } }) },
  });
  const names = new Set([
    "events", "selectedSpanId", "searchText", "selectedFilters", "umoNames", "clockNow",
    "eventIndex", "maxItems", "selectedEvent", "normalizedSearch", "filteredEvents", "traceRows",
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
  return { focused, ...vm.runInContext("({ events, selectedSpanId, selectedEvent, selectedFilters, traceRows, clockNow, processNewTraces, selectEvent })", context) };
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

test("list columns follow the requested order and the inspector has an explicit close action", () => {
  const header = descriptor.template.content.match(/<thead>([\s\S]*?)<\/thead>/)[1];
  const columns = Array.from(header.matchAll(/<th\b[^>]*>(.*?)<\/th>/gs), (match) => match[1]);
  assert.deepEqual(columns, [
    '{{ tm("columns.status") }}', '{{ tm("columns.platform") }}', '{{ tm("columns.timestamp") }}',
    '{{ tm("columns.duration") }}', '{{ tm("columns.message") }}', "UMO", '{{ tm("columns.sender") }}', "Spans",
  ]);
  assert.match(descriptor.template.content, /<main v-if="selectedEvent"/);
  assert.match(descriptor.template.content, /tm\('closeDetails'\)/);
  assert.match(descriptor.template.content, /@keydown.enter="selectEvent\(event.span_id\)"/);
  assert.match(descriptor.scriptSetup.content, /clearInterval\(durationTimer.value\)/);
});
