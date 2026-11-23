import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { test, vi } from "vitest";
import { logApi, pluginApi } from "../src/api/v1.ts";
import ConsoleDisplayer from "../src/components/shared/ConsoleDisplayer.vue";
import request from "../src/utils/request.ts";
import { mountDashboard } from "./helpers/components.mjs";

const streamState = vi.hoisted(() => ({ instances: [] }));
vi.mock("event-source-polyfill", () => ({
  EventSourcePolyfill: class {
    constructor(url, options) {
      this.url = url;
      this.options = options;
      this.closed = false;
      streamState.instances.push(this);
    }
    close() {
      this.closed = true;
    }
  },
}));

const historyResponse = () => ({ data: { status: "ok", data: { logs: [] } } });
const pluginResponse = () => ({ data: { status: "ok", data: [] } });
async function setup({
  history = vi.fn(async () => historyResponse()),
  plugins = vi.fn(async () => pluginResponse()),
  settle = true,
} = {}) {
  vi.spyOn(logApi, "history").mockImplementation(history);
  vi.spyOn(pluginApi, "list").mockImplementation(plugins);
  vi.spyOn(request, "get").mockImplementation((url) => {
    if (url === "/api/log-history") return history();
    throw new Error(`Unexpected console request: ${url}`);
  });
  const app = await mountDashboard(ConsoleDisplayer, { props: { workspaceMode: true } });
  if (settle) await flushPromises();
  return { ...app, state: app.vm, history, plugins };
}

test("log filters intersect level, source, plugin, platform, category, and keyword", async () => {
  const { state, wrapper } = await setup();
  const log = {
    level: "INFO",
    data: "\u001b[1;36mWeather updated\u001b[0m",
    source: "plugin",
    plugin_name: "weather",
    platform_id: "qq",
    category: "system",
  };
  await wrapper.setData({
    selectedSource: "plugin",
    selectedPlugin: "weather",
    selectedPlatform: "qq",
    searchKeyword: "WEATHER",
  });
  await wrapper.setProps({ hideUserChat: true });
  assert.equal(state.isLogVisible(log), true);
  for (const changed of [
    { source: "core" },
    { plugin_name: "other" },
    { platform_id: "telegram" },
    { category: "user_chat" },
    { data: "Unrelated message" },
    { level: "TRACE" },
  ]) {
    assert.equal(state.isLogVisible({ ...log, ...changed }), false, JSON.stringify(changed));
  }
  state.resetFilters();
  assert.equal(wrapper.emitted("update:hideUserChat").at(-1)[0], false);
  await wrapper.setProps({ hideUserChat: false });
  await wrapper.setData({ searchKeyword: "", selectedPlatform: "__unscoped__" });
  assert.equal(state.isLogVisible({ level: "INFO", data: "Legacy log" }), true);
  assert.equal(state.isLogVisible(log), false);
});

test("plugin options prefer display names and keep stable IDs as values and subtitles", async () => {
  const { state, wrapper } = await setup();
  await wrapper.setData({
    localLogCache: [{ plugin_name: "weather" }, { plugin_name: "weather" }, { plugin_name: "unknown" }],
    pluginDisplayNames: { weather: "Weather Forecast" },
  });
  const options = state.pluginOptions;
  assert.equal(options.length, 2);
  const weather = options.find((item) => item.value === "weather");
  assert.equal(weather.title, "Weather Forecast");
  assert.equal(weather.subtitle, "weather");
  assert.equal(options.find((item) => item.value === "unknown").title, "unknown");
});

test("plugin options come from the retained log cache, not the installed plugin list", async () => {
  const { state, wrapper } = await setup();
  await wrapper.setData({ pluginDisplayNames: { weather: "Weather Forecast" } });
  assert.equal(state.pluginOptions.length, 0);
  await wrapper.setData({ localLogCache: [{ plugin_name: "uninstalled" }] });
  assert.equal(state.pluginOptions.length, 1);
  assert.equal(state.pluginOptions[0].value, "uninstalled");
  assert.equal(state.pluginOptions[0].title, "uninstalled");
});

test("new logs follow the bottom without interrupting reading older entries", async () => {
  const { state, wrapper } = await setup();
  const term = wrapper.get(".console-term").element;
  Object.defineProperties(term, {
    scrollHeight: { configurable: true, get: () => 1000 + term.childElementCount * 100 },
    clientHeight: { configurable: true, value: 100 },
  });
  term.scrollTop = 900;
  state.processNewLogs([{ time: 1, level: "INFO", data: "First log" }]);
  assert.equal(term.scrollTop, term.scrollHeight);
  assert.equal(term.children[0].textContent, "First log");
  term.scrollTop = 200;
  state.processNewLogs([{ time: 2, level: "INFO", data: "Second log" }]);
  assert.equal(term.scrollTop, 200);
  state.processNewLogs([{ time: 2, level: "INFO", data: "Second log" }]);
  assert.equal(state.localLogCache.length, 2);
  assert.equal(term.children.length, 2);
});

test("console instances render only into their own log containers", async () => {
  const first = await setup();
  const second = await setup();
  const log = { time: 1, level: "INFO", data: "Message received" };
  first.state.processNewLogs([{ ...log }]);
  second.state.processNewLogs([{ ...log }]);
  const firstTerm = first.wrapper.get(".console-term").element;
  const secondTerm = second.wrapper.get(".console-term").element;
  assert.notEqual(firstTerm, secondTerm);
  assert.equal(firstTerm.children.length, 1);
  assert.equal(secondTerm.children.length, 1);
  assert.equal(firstTerm.textContent, log.data);
  assert.equal(secondTerm.textContent, log.data);
});

for (const pendingMethod of ["fetchLogHistory", "fetchPluginDisplayNames"]) {
  test(`unmounting during ${pendingMethod} does not open a log stream`, async () => {
    const before = streamState.instances.length;
    let finishRequest;
    const pending = new Promise((resolve) => {
      finishRequest = resolve;
    });
    const addListener = vi.spyOn(document, "addEventListener");
    const { wrapper } = await setup({
      ...(pendingMethod === "fetchLogHistory" ? { history: vi.fn(() => pending) } : { plugins: vi.fn(() => pending) }),
      settle: false,
    });
    await flushPromises();
    wrapper.unmount();
    finishRequest(pendingMethod === "fetchLogHistory" ? historyResponse() : pluginResponse());
    await flushPromises();
    assert.equal(streamState.instances.length, before);
    assert.equal(addListener.mock.calls.filter(([name]) => name === "fullscreenchange").length, 0);
  });
}

test("a pending reconnect cannot open a stream after unmount", async () => {
  const { wrapper, state, history } = await setup();
  const before = streamState.instances.length;
  const connection = streamState.instances.at(-1);
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  let finishRequest;
  history.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishRequest = resolve;
      }),
  );
  connection.onerror({});
  assert.equal(connection.closed, true);
  vi.advanceTimersByTime(1000);
  assert.equal(typeof finishRequest, "function");
  wrapper.unmount();
  finishRequest(historyResponse());
  await flushPromises();
  assert.equal(streamState.instances.length, before);
  assert.equal(state.eventSource, null);
  assert.equal(vi.getTimerCount(), 0);
});
