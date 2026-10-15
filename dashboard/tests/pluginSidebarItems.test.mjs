import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as vue from "vue";

async function setup(t, plugins) {
  const locale = vue.ref("zh-CN");
  let mount;
  let requests = 0;
  const modules = {
    vue: { ...vue, onMounted: (callback) => (mount = callback) },
    "@/i18n/composables": { useI18n: () => ({ locale }) },
    "@/api/v1": {
      pluginApi: {
        list: async () => {
          requests++;
          return { data: { status: "ok", data: plugins } };
        },
      },
    },
  };
  for (const path of [
    "utils/pluginI18n.js",
    "composables/usePluginSidebarItems.ts",
  ]) {
    const exports = {};
    const source = readFileSync(
      new URL(`../src/${path}`, import.meta.url),
      "utf8",
    );
    vm.runInNewContext(
      ts.transpileModule(source, {
        compilerOptions: {
          target: ts.ScriptTarget.ES2020,
          module: ts.ModuleKind.CommonJS,
        },
      }).outputText,
      {
        exports,
        require: (id) => {
          assert.ok(id in modules, `Unexpected import: ${id}`);
          return modules[id];
        },
      },
    );
    modules[`@/${path}`] = exports;
    modules[`@/${path.replace(/\.(js|ts)$/, "")}`] = exports;
  }
  const scope = vue.effectScope();
  t.after(() => scope.stop());
  const { usePluginSidebarItems, pluginSidebarState } =
    modules["@/composables/usePluginSidebarItems.ts"];
  const items = scope.run(usePluginSidebarItems);
  await mount();
  await vue.nextTick();
  return { ...items, locale, pluginSidebarState, requests: () => requests };
}

test("switching all supported locales updates names without refetching or changing IDs", async (t) => {
  const names = {
    "zh-CN": "订阅登录",
    "en-US": "Subscription Login",
    "ru-RU": "Вход по подписке",
    "ja-JP": "サブスクリプションログイン",
  };
  const { locale, pluginItems, pluginGroups, requests } = await setup(t, [
    {
      name: "plugin / id",
      display_name: "Original name",
      activated: true,
      pages: ["settings / page", "other"],
      i18n: Object.fromEntries(
        Object.entries(names).map(([key, name]) => [
          key,
          { metadata: { display_name: ` ${name} ` } },
        ]),
      ),
    },
  ]);
  const route = "/plugin-view/plugin%20%2F%20id/settings%20%2F%20page";
  for (const language of [...Object.keys(names), "zh-CN"]) {
    locale.value = language;
    await vue.nextTick();
    const group = pluginGroups.value[0];
    const item = pluginItems.value.children[0];
    assert.equal(group.title, names[language]);
    assert.equal(item.title, names[language]);
    assert.equal(item.pluginInfo.displayName, names[language]);
    assert.equal(group.children[0].pluginInfo.displayName, names[language]);
    assert.equal(group.children[1].pluginInfo.displayName, names[language]);
    assert.equal(group.children[0].title, "settings / page");
    assert.equal(group.value, "plugin:plugin / id");
    assert.equal(item.pluginInfo.id, "plugin / id");
    assert.equal(item.to, route);
    assert.equal(group.children[0].to, route);
    assert.equal(requests(), 1);
  }
});

test("missing and invalid translations fall back to nonempty original names", async (t) => {
  const translations = [undefined, null, "", " \t\n", {}, [], 42, false];
  const originals = ["Original name", undefined, null, "", " \t", {}, []];
  const plugins = [];
  const expected = [];
  for (const display_name of originals) {
    for (const translation of translations) {
      plugins.push({
        name: "plugin-id",
        display_name,
        activated: true,
        pages: ["settings"],
        i18n: { "zh-CN": { metadata: { display_name: translation } } },
      });
      expected.push(
        display_name === "Original name" ? display_name : "plugin-id",
      );
    }
  }
  for (const i18n of [
    undefined,
    null,
    {},
    { "en-US": { metadata: { display_name: "English only" } } },
  ]) {
    plugins.push({
      name: "plugin-id",
      activated: true,
      pages: ["settings"],
      i18n,
    });
    expected.push("plugin-id");
  }
  plugins.push({
    name: "",
    display_name: " ",
    activated: true,
    pages: ["settings"],
  });
  expected.push("Unknown Plugin");
  const { pluginItems, pluginGroups } = await setup(t, plugins);
  expected.forEach((name, index) => {
    const item = pluginItems.value.children[index];
    const group = pluginGroups.value[index];
    assert.equal(item.title, name);
    assert.equal(item.pluginInfo.displayName, name);
    assert.equal(group.title, name);
    assert.equal(group.children[0].pluginInfo.displayName, name);
  });
});

test("page titles keep views before pages priority and existing grouped fallbacks", async (t) => {
  const cases = [
    [" View title ", "Legacy title", "View title"],
    [undefined, " Legacy title ", "Legacy title"],
    [null, "Legacy title", "Legacy title"],
    [undefined, undefined, null],
    [" ", "Legacy title", null],
    [{ title: "Invalid" }, "Legacy title", null],
    [undefined, [], null],
  ];
  const { pluginItems, pluginGroups } = await setup(
    t,
    cases.map(([view, page]) => ({
      name: "plugin-id",
      display_name: "Original name",
      activated: true,
      pages: ["settings"],
      i18n: {
        "zh-CN": {
          metadata: { display_name: "Translated name" },
          views: { settings: { title: view } },
          pages: { settings: { title: page } },
        },
      },
    })),
  );
  cases.forEach(([, , title], index) => {
    const item = pluginItems.value.children[index];
    const group = pluginGroups.value[index];
    assert.equal(item.title, title ?? "Translated name");
    assert.equal(group.children[0].title, title ?? "settings");
    assert.equal(item.pluginInfo.displayName, "Translated name");
    assert.equal(group.title, "Translated name");
  });
});

test("translated page titles update with locale and plugins without i18n remain supported", async (t) => {
  const { locale, pluginItems, pluginGroups, pluginSidebarState } = await setup(
    t,
    [
      {
        name: "plugin-id",
        display_name: "Original name",
        activated: true,
        pages: ["settings"],
        i18n: {
          "zh-CN": {
            metadata: { display_name: "插件" },
            views: { settings: { title: "设置" } },
          },
          "en-US": {
            metadata: { display_name: "Plugin" },
            pages: { settings: { title: "Settings" } },
          },
        },
      },
    ],
  );
  assert.equal(pluginItems.value.children[0].title, "设置");
  locale.value = "en-US";
  await vue.nextTick();
  assert.equal(pluginItems.value.children[0].title, "Settings");
  assert.equal(pluginGroups.value[0].children[0].title, "Settings");
  locale.value = "ja-JP";
  await vue.nextTick();
  assert.equal(pluginItems.value.children[0].title, "Original name");
  assert.equal(pluginGroups.value[0].title, "Original name");
  pluginSidebarState.plugins = [
    { name: "legacy", activated: true, pages: ["settings"] },
    { name: "inactive", activated: false, pages: ["settings"] },
    { name: "no-pages", activated: true, pages: [] },
  ];
  await vue.nextTick();
  assert.equal(pluginItems.value.children.length, 1);
  assert.equal(pluginGroups.value.length, 1);
  assert.equal(pluginItems.value.children[0].title, "legacy");
  assert.equal(pluginGroups.value[0].title, "legacy");
  pluginSidebarState.plugins = [];
  await vue.nextTick();
  assert.equal(pluginItems.value, null);
  assert.equal(pluginGroups.value.length, 0);
});
