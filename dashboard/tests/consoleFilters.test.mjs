import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { parse } from "vue/compiler-sfc";

function setup(document = {}, globals = {}) {
  const source = readFileSync(new URL("../src/components/shared/ConsoleDisplayer.vue", import.meta.url), "utf8");
  const { descriptor } = parse(source);
  const ast = ts.createSourceFile("console.js", descriptor.script.content, ts.ScriptTarget.Latest, true);
  const definition = ast.statements.find(ts.isExportAssignment);
  const context = vm.createContext({ document, translateConsole: (key) => key, ...globals });
  const component = vm.runInContext(`(${definition.expression.getText(ast)})`, context);
  const state = Object.assign(component.data(), component.methods, {
    hideUserChat: false, $refs: {}, $emit() {},
  });
  return { component, state };
}

test("log filters intersect level, source, plugin, platform, category, and keyword", () => {
  const { state } = setup();
  const log = { level: "INFO", data: "\u001b[1;36mWeather updated\u001b[0m", source: "plugin", plugin_name: "weather", platform_id: "qq", category: "system" };
  state.selectedSource = "plugin";
  state.selectedPlugin = "weather";
  state.selectedPlatform = "qq";
  state.searchKeyword = "WEATHER";
  state.hideUserChat = true;
  assert.equal(state.isLogVisible(log), true);
  for (const changed of [
    { source: "core" }, { plugin_name: "other" }, { platform_id: "telegram" },
    { category: "user_chat" }, { data: "Unrelated message" }, { level: "TRACE" },
  ]) assert.equal(state.isLogVisible({ ...log, ...changed }), false);
  state.resetFilters();
  state.searchKeyword = "";
  state.hideUserChat = false;
  state.selectedPlatform = "__unscoped__";
  assert.equal(state.isLogVisible({ level: "INFO", data: "Legacy log" }), true);
  assert.equal(state.isLogVisible(log), false);
});

test("a plugin-scoped console shows only that plugin's logs under the other filters", () => {
  const { state } = setup();
  state.pluginName = "weather";
  const log = { level: "INFO", data: "Weather updated", source: "plugin", plugin_name: "weather" };
  assert.equal(state.isLogVisible(log), true);
  for (const changed of [
    { plugin_name: "other" }, { plugin_name: null, source: "core" }, { plugin_name: undefined },
  ]) assert.equal(state.isLogVisible({ ...log, ...changed }), false);
  // The scope cannot be widened by the in-console plugin filter.
  state.selectedPlugin = "other";
  assert.equal(state.isLogVisible({ ...log, plugin_name: "other" }), false);
  assert.equal(state.isLogVisible(log), false);
  state.selectedPlugin = null;
  state.selectedLevels = [3];
  assert.equal(state.isLogVisible(log), false);
});

test("plugin options prefer display names and keep stable IDs as values and subtitles", () => {
  const { component, state } = setup();
  state.localLogCache = [
    { plugin_name: "weather" }, { plugin_name: "weather" }, { plugin_name: "unknown" },
  ];
  state.pluginDisplayNames = { weather: "Weather Forecast" };
  const options = component.computed.pluginOptions.call(state);
  assert.equal(options.length, 2);
  const weather = options.find((item) => item.value === "weather");
  assert.equal(weather.title, "Weather Forecast");
  assert.equal(weather.subtitle, "weather");
  assert.equal(options.find((item) => item.value === "unknown").title, "unknown");
});

test("plugin options come from the retained log cache, not the installed plugin list", () => {
  const { component, state } = setup();
  // Installed plugins known only by display name must not create options.
  state.pluginDisplayNames = { weather: "Weather Forecast" };
  assert.equal(component.computed.pluginOptions.call(state).length, 0);
  // A plugin that is no longer installed but still has cached logs remains selectable.
  state.localLogCache = [{ plugin_name: "uninstalled" }];
  const options = component.computed.pluginOptions.call(state);
  assert.equal(options.length, 1);
  assert.equal(options[0].value, "uninstalled");
  assert.equal(options[0].title, "uninstalled");
});

test("new logs follow the bottom without interrupting reading older entries", () => {
  const term = {
    scrollHeight: 1000, scrollTop: 900, clientHeight: 100, entries: [],
    appendChild(fragment) {
      this.entries.push(...fragment.childNodes);
      this.scrollHeight += fragment.childNodes.length * 100;
    },
  };
  const { state } = setup({
    getElementById: () => term,
    createDocumentFragment: () => ({ childNodes: [], appendChild(node) { this.childNodes.push(node); } }),
  });
  state.$refs.term = term;
  state.buildLogElement = (log) => log;
  state.processNewLogs([{ time: 1, level: "INFO", data: "First log" }]);
  assert.equal(term.scrollTop, term.scrollHeight);
  term.scrollTop = 200;
  state.processNewLogs([{ time: 2, level: "INFO", data: "Second log" }]);
  assert.equal(term.scrollTop, 200);
  state.processNewLogs([{ time: 2, level: "INFO", data: "Second log" }]);
  assert.equal(state.localLogCache.length, 2);
  assert.equal(term.entries.length, 2);
});

test("console instances render only into their own log containers", () => {
  const sharedTerm = { entries: [], appendChild(fragment) { this.entries.push(...fragment.childNodes); } };
  const document = {
    getElementById: () => sharedTerm,
    createDocumentFragment: () => ({ childNodes: [], appendChild(node) { this.childNodes.push(node); } }),
  };
  const first = setup(document).state;
  const second = setup(document).state;
  first.$refs.term = sharedTerm;
  second.$refs.term = { ...sharedTerm, entries: [] };
  const log = { time: 1, level: "INFO", data: "Message received" };
  for (const state of [first, second]) {
    state.buildLogElement = (item) => item;
    state.processNewLogs([{ ...log }]);
  }
  assert.equal(first.$refs.term.entries.length, 1);
  assert.equal(second.$refs.term.entries.length, 1);
});

for (const pendingMethod of ["fetchLogHistory", "fetchPluginDisplayNames"]) {
  test(`unmounting during ${pendingMethod} does not open a log stream`, async () => {
    let finishRequest;
    let requestStarted;
    const pendingRequest = new Promise((resolve) => { requestStarted = resolve; });
    let connections = 0;
    let listeners = 0;
    const { component, state } = setup({
      addEventListener() { listeners++; },
      removeEventListener() {},
    });
    state.workspaceMode = true;
    state.fetchLogHistory = async () => {};
    state.fetchPluginDisplayNames = async () => {};
    state[pendingMethod] = () => new Promise((resolve) => {
      finishRequest = resolve;
      requestStarted();
    });
    state.connectSSE = () => { connections++; };
    const mounting = component.mounted.call(state);
    await pendingRequest;
    component.beforeUnmount.call(state);
    finishRequest();
    await mounting;
    assert.equal(connections, 0);
    assert.equal(listeners, 0);
  });
}

test("a history response that arrives after unmount is ignored", async () => {
  let finishRequest;
  const { component, state } = setup({ removeEventListener() {} }, {
    logApi: { history: () => new Promise((resolve) => { finishRequest = resolve; }) },
  });
  const fetching = state.fetchLogHistory();
  component.beforeUnmount.call(state);
  finishRequest({ data: { data: { logs: [{ time: 1, level: "INFO", data: "Late log" }] } } });
  await fetching;
  assert.equal(state.localLogCache.length, 0);
});

test("a pending reconnect cannot open a stream after unmount", async () => {
  let connections = 0;
  let retry;
  let finishRequest;
  const { component, state } = setup({ removeEventListener() {} }, {
    console: { log() {}, warn() {} },
    localStorage: { getItem: () => null },
    logApi: { liveUrl: () => "/logs" },
    setTimeout(callback) { retry = callback; return 1; },
    clearTimeout() {},
    EventSourcePolyfill: function () { connections++; this.close = () => {}; },
  });
  state.connectSSE();
  state.eventSource.onerror({});
  state.fetchLogHistory = () => new Promise((resolve) => { finishRequest = resolve; });
  const reconnecting = retry();
  component.beforeUnmount.call(state);
  finishRequest();
  await reconnecting;
  assert.equal(connections, 1);
  assert.equal(state.eventSource, null);
});
