import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as vue from "vue";

async function setup(t, plugins) {
  // Keep real Vue reactivity and source modules; stub API and component mounting.
  plugins = plugins.map((plugin) => ({
    name: "plugin-id",
    display_name: "Original name",
    activated: true,
    pages: ["settings"],
    ...plugin,
  }));
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
    modules[`@/${path.replace(/\.(js|ts)$/, "")}`] = exports;
  }
  const scope = vue.effectScope();
  t.after(() => scope.stop());
  const { usePluginSidebarItems } =
    modules["@/composables/usePluginSidebarItems"];
  const items = scope.run(usePluginSidebarItems);
  await mount();
  await vue.nextTick();
  return { ...items, locale, requests: () => requests };
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
      pages: ["settings / page", "other"],
      i18n: Object.fromEntries(
        Object.entries(names).map(([key, name]) => [
          key,
          {
            metadata: { display_name: ` ${name} ` },
            views: { other: { title: `${name} settings` } },
          },
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
    assert.equal(group.children[1].title, `${names[language]} settings`);
    assert.equal(group.children[0].title, "settings / page");
    assert.equal(group.value, "plugin:plugin / id");
    assert.equal(item.pluginInfo.id, "plugin / id");
    assert.equal(item.to, route);
    assert.equal(group.children[0].to, route);
    assert.equal(requests(), 1);
  }
});

test("missing and invalid translations fall back to nonempty original names", async (t) => {
  const cases = [
    ...[undefined, null, "", " \t\n", {}, [], 42, false].map((value) => [
      { i18n: { "zh-CN": { metadata: { display_name: value } } } },
      "Original name",
    ]),
    [{}, "Original name"],
    [{ i18n: null }, "Original name"],
    [{ i18n: {} }, "Original name"],
    [
      { i18n: { "en-US": { metadata: { display_name: "English only" } } } },
      "Original name",
    ],
    ...[undefined, null, "", " \t", {}].map((display_name) => [
      { display_name },
      "plugin-id",
    ]),
    [{ name: "", display_name: " " }, "Unknown Plugin"],
  ];
  const plugins = cases.map(([plugin]) => plugin);
  const { pluginItems, pluginGroups } = await setup(t, plugins);
  cases.forEach(([, name], index) => {
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
