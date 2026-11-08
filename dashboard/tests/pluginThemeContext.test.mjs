import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { compileScript, parse } from "vue/compiler-sfc";
import { createVuetify } from "vuetify";
import {
  computed,
  effectScope,
  nextTick,
  reactive,
  ref,
  toRaw,
  watch,
} from "vue";

const viewSource = readFileSync(
  new URL("../src/views/PluginViewPage.vue", import.meta.url),
  "utf8",
);
const compiled = compileScript(parse(viewSource).descriptor, {
  id: "plugin-theme-test",
})
  .content.replace(/^import[\s\S]*?from ["'][^"']+["'];?\r?$/gm, "")
  .replace("export default", "const component =");

function createView() {
  const messages = [];
  const customizer = reactive({
    uiTheme: "PurpleTheme",
    get isDark() {
      return this.uiTheme === "PurpleThemeDark";
    },
  });
  const scope = effectScope();
  const theme = scope.run(
    () =>
      createVuetify({
        theme: {
          defaultTheme: "PurpleTheme",
          themes: {
            PurpleTheme: {
              dark: false,
              colors: { primary: "#3c96ca", secondary: "#2f86bd" },
            },
            PurpleThemeDark: {
              dark: true,
              colors: { primary: "#5ba4d4", secondary: "#4a95c4" },
            },
          },
        },
      }).theme,
  );
  const light = theme.themes.value.PurpleTheme;
  const dark = theme.themes.value.PurpleThemeDark;
  scope.run(() =>
    watch(
      () => customizer.uiTheme,
      (name) => {
        theme.global.name.value = name;
      },
      { flush: "sync" },
    ),
  );
  const component = vm.runInNewContext(`${compiled}; component`, {
    axios: {},
    computed,
    ref,
    toRaw,
    watch,
    URL,
    onMounted() {},
    onBeforeUnmount() {},
    useRoute: () => ({ params: { pluginName: "demo", pageName: "view" } }),
    useTheme: () => theme,
    useCustomizerStore: () => customizer,
    useModuleI18n: () => ({ tm: (key) => key }),
    usePluginI18n: () => ({
      locale: ref("en-US"),
      pluginName: (item) => item.name,
      pluginViewTitle: () => "Demo",
    }),
    pluginApi: {
      get: async () => ({ data: { data: { name: "demo", activated: true } } }),
      page: async () => ({
        data: { data: { name: "view", content_path: "/demo/" } },
      }),
    },
    fetchWithAuth() {},
    window: { location: { origin: "https://astrbot.test" } },
  });
  const view = scope.run(() => component.setup({}, { expose() {} }));
  view.iframeRef.value = {
    contentWindow: {
      postMessage: (message, origin) => messages.push({ message, origin }),
    },
  };
  return { view, messages, customizer, light, dark, scope };
}

test("plugin context sends effective colors on load, edits, theme switches and resets", async () => {
  const { view, messages, customizer, light, dark, scope } = createView();
  try {
    await new Promise((resolve) => setImmediate(resolve));
    view.handleIframeLoad();
    const context = () => messages.at(-1).message.context;
    assert.equal(context().isDark, false);
    assert.deepEqual(
      { ...context().themeColors },
      { primary: "#3c96ca", secondary: "#2f86bd" },
    );
    light.colors.primary = "#ff8844";
    await nextTick();
    assert.equal(context().themeColors.primary, "#ff8844");
    light.colors.secondary = "#8877ee";
    await nextTick();
    assert.equal(context().themeColors.secondary, "#8877ee");
    customizer.uiTheme = "PurpleThemeDark";
    await nextTick();
    assert.equal(context().isDark, true);
    assert.deepEqual(
      { ...context().themeColors },
      { primary: dark.colors.primary, secondary: dark.colors.secondary },
    );
    dark.colors.primary = "#5ba4d4";
    dark.colors.secondary = "#4a95c4";
    customizer.uiTheme = "PurpleTheme";
    light.colors.primary = "#3c96ca";
    light.colors.secondary = "#2f86bd";
    await nextTick();
    assert.deepEqual(
      { ...context().themeColors },
      { primary: "#3c96ca", secondary: "#2f86bd" },
    );
    assert.equal(messages[0].message.context.themeColors.primary, "#3c96ca");
    assert.match(view.iframeSrc.value, /theme=light/);
    const count = messages.length;
    scope.stop();
    light.colors.primary = "#111111";
    await nextTick();
    assert.equal(messages.length, count);
  } finally {
    scope.stop();
  }
});

test("existing bridge forwards optional theme colors through onContext without changing legacy contexts", async () => {
  let receive;
  const parent = { postMessage() {} };
  const attributes = {};
  const window = {
    location: { origin: "null" },
    parent,
    addEventListener(_event, listener) {
      receive = listener;
    },
  };
  vm.runInNewContext(
    readFileSync(
      new URL("../../astrbot/dashboard/plugin_page_bridge.js", import.meta.url),
      "utf8",
    ),
    {
      window,
      document: {
        documentElement: {
          setAttribute: (key, value) => {
            attributes[key] = value;
          },
        },
      },
      console,
    },
  );
  const bridge = window.AstrBotPluginPage;
  assert.equal(bridge, window.AstrBotPluginView);
  bridge.__setInitialContext({ isDark: false, pluginName: "demo" });
  assert.equal((await bridge.ready()).themeColors, undefined);
  const observed = [];
  const off = bridge.onContext((context) => observed.push(context));
  const update = {
    isDark: true,
    themeColors: { primary: "#123456", secondary: "#abcdef" },
  };
  const event = {
    source: parent,
    origin: "https://astrbot.test",
    data: { channel: "astrbot-plugin-page", kind: "context", context: update },
  };
  receive({ ...event, source: {} });
  assert.equal(observed.length, 1);
  receive(event);
  assert.equal(observed.length, 2);
  assert.deepEqual(bridge.getContext().themeColors, update.themeColors);
  assert.equal(attributes["data-theme"], "dark");
  assert.equal(bridge.getContext().pluginName, "demo");
  off();
  receive({ ...event, data: { ...event.data, context: { isDark: false } } });
  assert.equal(observed.length, 2);
});
