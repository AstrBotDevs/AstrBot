import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { parse } from "vue/compiler-sfc";

function setup(document = {}) {
  const source = readFileSync(new URL("../src/components/shared/ConsoleDisplayer.vue", import.meta.url), "utf8");
  const { descriptor } = parse(source);
  const ast = ts.createSourceFile("console.js", descriptor.script.content, ts.ScriptTarget.Latest, true);
  const definition = ast.statements.find(ts.isExportAssignment);
  const context = vm.createContext({ document, translateConsole: (key) => key });
  const component = vm.runInContext(`(${definition.expression.getText(ast)})`, context);
  const state = Object.assign(component.data(), component.methods, {
    hideUserChat: false, $emit() {},
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
