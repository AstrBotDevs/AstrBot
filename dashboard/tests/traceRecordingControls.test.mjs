import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { computed, reactive, ref } from "vue";
import { parse } from "vue/compiler-sfc";

const page = parse(readFileSync(new URL("../src/views/TracePage.vue", import.meta.url), "utf8")).descriptor;
const view = parse(readFileSync(new URL("../src/components/shared/TraceDisplayer.vue", import.meta.url), "utf8")).descriptor;

function setup(response = { data: { status: "ok", data: { trace_enable: true } } }) {
  const requests = [];
  const errors = [];
  const ast = ts.createSourceFile("trace.ts", page.scriptSetup.content, ts.ScriptTarget.Latest, true);
  const names = new Set(["traceEnabled", "loading", "fetchTraceSettings", "updateTraceSettings"]);
  const statements = ast.statements.filter((node) =>
    ts.isFunctionDeclaration(node) ? names.has(node.name?.text) :
      ts.isVariableStatement(node) && names.has(node.declarationList.declarations[0]?.name.getText(ast)),
  );
  assert.equal(statements.length, names.size);
  const context = vm.createContext({
    ref, tm: (key) => key, toast: { error: (message) => errors.push(message) }, console: { error() {} },
    traceApi: {
      getSettings: async () => response,
      updateSettings: (payload) => new Promise((resolve, reject) => requests.push({ payload, resolve, reject })),
    },
  });
  vm.runInContext(ts.transpile(statements.map((node) => node.getText(ast)).join("\n")), context);
  return { requests, errors, ...vm.runInContext("({ traceEnabled, loading, fetchTraceSettings, updateTraceSettings })", context) };
}

test("settings load before toggling and respect backend-disabled recording", async () => {
  const state = setup({ data: { status: "ok", data: { trace_enable: false } } });
  assert.equal(state.loading.value, true);
  await state.updateTraceSettings();
  assert.equal(state.requests.length, 0);
  await state.fetchTraceSettings();
  assert.equal(state.traceEnabled.value, false);
  assert.equal(state.loading.value, false);
});

test("toggle changes state only after confirmation and rejects repeated clicks while pending", async () => {
  const state = setup();
  await state.fetchTraceSettings();
  const pause = state.updateTraceSettings();
  assert.equal(state.loading.value, true);
  assert.equal(state.traceEnabled.value, true);
  assert.equal(state.requests[0].payload.trace_enable, false);
  await state.updateTraceSettings();
  assert.equal(state.requests.length, 1);
  state.requests[0].resolve({ data: { status: "ok" } });
  await pause;
  assert.equal(state.traceEnabled.value, false);
  assert.equal(state.loading.value, false);
  const resume = state.updateTraceSettings();
  assert.equal(state.requests[1].payload.trace_enable, true);
  state.requests[1].resolve({ data: { status: "ok" } });
  await resume;
  assert.equal(state.traceEnabled.value, true);
  assert.doesNotMatch(page.template.content, /traceDisplayerKey|:key=|v-switch|trace-hint/);
});

test("business and network failures keep the previous state and report an error", async () => {
  const state = setup();
  await state.fetchTraceSettings();
  let pending = state.updateTraceSettings();
  state.requests[0].resolve({ data: { status: "error" } });
  await pending;
  assert.equal(state.traceEnabled.value, true);
  assert.equal(state.loading.value, false);
  pending = state.updateTraceSettings();
  state.requests[1].reject(new Error("offline"));
  await pending;
  assert.equal(state.traceEnabled.value, true);
  assert.equal(state.loading.value, false);
  assert.deepEqual(state.errors, ["controls.updateFailed", "controls.updateFailed"]);
});

test("failed settings loading unlocks the control and gives feedback", async () => {
  const state = setup({ data: { status: "error" } });
  await state.fetchTraceSettings();
  assert.equal(state.loading.value, false);
  assert.deepEqual(state.errors, ["controls.loadFailed"]);
});

test("recording button reads Start, Pause, or Connecting without a status dot", () => {
  const ast = ts.createSourceFile("trace.js", view.scriptSetup.content, ts.ScriptTarget.Latest, true);
  const definition = ast.statements.find((node) => ts.isVariableStatement(node) &&
    node.declarationList.declarations[0]?.name.getText(ast) === "recordingLabel");
  const props = reactive({ recordingEnabled: true });
  const connected = ref(false);
  const labels = { "controls.start": "启动", "controls.pauseButton": "暂停", connecting: "连接中" };
  const context = vm.createContext({ props, connected, computed, tm: (key) => labels[key] });
  vm.runInContext(definition.getText(ast), context);
  const label = vm.runInContext("recordingLabel", context);
  assert.equal(label.value, "连接中");
  connected.value = true;
  assert.equal(label.value, "暂停");
  props.recordingEnabled = false;
  assert.equal(label.value, "启动");
  connected.value = false;
  assert.equal(label.value, "启动");
  assert.doesNotMatch(view.template.content, /live-dot|trace-count/);
});

test("toolbar has matching icon-and-text buttons, fluid input, and an embedded record count", () => {
  const toolbar = view.template.content.split('<div class="trace-workspace">')[0];
  const buttons = Array.from(toolbar.matchAll(/<v-btn\b[\s\S]*?<\/v-btn>/g), (match) => match[0]);
  assert.equal(buttons.length, 3);
  for (const button of buttons) assert.match(button, /variant="tonal"/);
  assert.match(buttons[0], /<v-icon/);
  assert.match(buttons[0], /tm\("filters.button"\)/);
  assert.match(buttons[1], /<component/);
  assert.match(buttons[1], /recordingLabel/);
  assert.match(buttons[2], /<RefreshCw/);
  assert.match(buttons[2], /tm\("refresh"\)/);
  assert.match(buttons[1], /:loading="recordingBusy"/);
  assert.match(buttons[1], /:disabled="recordingBusy"/);
  assert.match(toolbar, /tm\('search', \{ count: totalRecords \}\)/);
  const searchStyle = view.styles[0].content.match(/\.trace-search\s*\{([^}]+)\}/)[1];
  assert.match(searchStyle, /flex:\s*1/);
  assert.match(searchStyle, /height:\s*36px/);
  assert.doesNotMatch(searchStyle, /max-width/);
  const buttonStyle = view.styles[0].content.match(/\.trace-explorer-toolbar :deep\(\.v-btn\) \{([^}]+)\}/)[1];
  assert.match(buttonStyle, /height:\s*36px/);
  assert.match(buttonStyle, /background:\s*var\(--trace-control-background\)/);
  assert.match(searchStyle, /background:\s*var\(--trace-control-background\)/);
  assert.match(view.styles[0].content, /\.v-btn__underlay\) \{ display: none; \}/);
});
