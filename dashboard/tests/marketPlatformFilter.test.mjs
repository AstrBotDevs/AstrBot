import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as vue from "vue";
import * as pluginSearch from "../src/utils/pluginSearch.js";

const require = createRequire(import.meta.url);
const source = readFileSync(new URL("../src/views/extension/useExtensionPage.js", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function setup(t, plugins = []) {
  const route = vue.reactive({ hash: "", meta: { extensionTab: "market" } });
  const imports = {
    vue: { ...vue, onMounted() {}, onUnmounted() {} },
    "vue-router": { useRoute: () => route, useRouter: () => ({}) },
    "@/api/v1": {},
    "@/composables/usePluginSidebarItems": {},
    "@/i18n/composables": {
      useI18n: () => ({ t: (key) => key }),
      useModuleI18n: () => ({ tm: (key) => key }),
    },
    "@/stores/common": { useCommonStore: () => ({}) },
    "@/utils/errorUtils": {},
    "@/utils/hashRouteTabs.mjs": {},
    "@/utils/platformUtils": { getPlatformDisplayName: (id) => id },
    "@/utils/pluginSearch": pluginSearch,
  };
  const context = vm.createContext({
    exports: {},
    require: (id) => imports[id] ?? require(id),
    window: { addEventListener() {} },
    setTimeout,
    clearTimeout,
  });
  vm.runInContext(compiled, context);
  const scope = vue.effectScope();
  t.after(() => scope.stop());
  const state = scope.run(() => context.exports.useExtensionPage("market"));
  state.pluginMarketData.value = plugins;
  return state;
}

const fixture = [
  { name: "qq", category: "tools", support_platforms: ["qq_official"], stars: 2 },
  { name: "both", category: "tools", support_platforms: ["telegram", "discord"], stars: 5 },
  { name: "telegram", category: "other", support_platforms: ["telegram"], stars: 1 },
  { name: "missing", category: "tools" },
  { name: "empty", support_platforms: [] },
  { name: "invalid", support_platforms: "telegram" },
  { name: "blank", support_platforms: [null, 3, " "] },
];

const names = (items) => Array.from(items, (plugin) => plugin.name);

test("no selection preserves the complete market; multiple platforms use OR", (t) => {
  const state = setup(t, fixture);
  assert.deepEqual(names(state.filteredMarketPlugins.value), names(fixture));
  state.marketPlatformFilter.value = ["qq_official", "discord"];
  assert.deepEqual(names(state.filteredMarketPlugins.value), ["qq", "both"]);
  state.marketPlatformFilter.value = [];
  assert.deepEqual(names(state.filteredMarketPlugins.value), names(fixture));
});

test("undeclared metadata is selectable independently or alongside a platform", (t) => {
  const state = setup(t, fixture);
  state.marketPlatformFilter.value = ["__undeclared__"];
  assert.deepEqual(names(state.filteredMarketPlugins.value), ["missing", "empty", "invalid", "blank"]);
  state.marketPlatformFilter.value.push("qq_official");
  assert.deepEqual(names(state.filteredMarketPlugins.value), ["qq", "missing", "empty", "invalid", "blank"]);
  state.marketPlatformFilter.value = ["telegram"];
  assert.deepEqual(names(state.filteredMarketPlugins.value), ["both", "telegram"]);
});

test("options and matching normalize legacy declarations and retain community platforms", (t) => {
  const state = setup(t, [
    { name: "aliases", support_platforms: [" OneBot ", "aiocqhttp(OneBot v11)", "FEISHU", "lark", "weixin_official_accounts"] },
    { name: "community", support_platforms: [" custom_adapter ", "custom_adapter"] },
  ]);
  assert.deepEqual(Array.from(state.marketPlatformItems.value, (item) => item.value), [
    "__undeclared__", "aiocqhttp", "custom_adapter", "lark", "weixin_official_account",
  ]);
  for (const platform of ["aiocqhttp", "lark", "weixin_official_account"]) {
    state.marketPlatformFilter.value = [platform];
    assert.deepEqual(names(state.filteredMarketPlugins.value), ["aliases"]);
  }
  state.marketPlatformFilter.value = ["custom_adapter"];
  assert.deepEqual(names(state.filteredMarketPlugins.value), ["community"]);
});

test("platform, category and real text search intersect before sorting and recommendations", (t) => {
  const state = setup(t, [
    { name: "first", desc: "天气", category: "tools", support_platforms: ["telegram"], stars: 2 },
    { name: "second", desc: "天气", category: "tools", support_platforms: ["telegram"], stars: 10 },
    { name: "other-platform", desc: "天气", category: "tools", support_platforms: ["qq_official"] },
    { name: "other-category", desc: "天气", category: "other", support_platforms: ["telegram"] },
    { name: "other-text", desc: "Music", category: "tools", support_platforms: ["telegram"] },
  ]);
  state.marketPlatformFilter.value = ["telegram"];
  state.marketCategoryFilter.value = "tools";
  state.debouncedMarketSearch.value = "tianqi";
  state.sortBy.value = "stars";
  state.randomPluginNames.value = [state.getMarketPluginKey(state.pluginMarketData.value[2])];
  assert.deepEqual(names(state.sortedPlugins.value), ["second", "first"]);
  assert.deepEqual(names(state.randomPlugins.value), ["first", "second"]);
  state.debouncedMarketSearch.value = "absent";
  assert.equal(state.paginatedPlugins.value.length, 0);
  assert.equal(state.totalPages.value, 0);
  assert.equal(state.randomPlugins.value.length, 0);
});

test("filter changes reset pagination, including selections mutated in place", async (t) => {
  const state = setup(t, Array.from({ length: 20 }, (_, i) => ({
    name: `plugin-${i}`, support_platforms: [i % 2 ? "telegram" : "qq_official"],
  })));
  await vue.nextTick();
  state.currentPage.value = 3;
  state.marketPlatformFilter.value = ["telegram"];
  await vue.nextTick();
  assert.equal(state.currentPage.value, 1);
  assert.equal(state.totalPages.value, 2);
  assert.equal(state.paginatedPlugins.value.length, 9);
  state.currentPage.value = 2;
  state.marketPlatformFilter.value.push("qq_official");
  await vue.nextTick();
  assert.equal(state.currentPage.value, 1);
  assert.equal(state.totalPages.value, 3);
});

test("source changes clear platform selections and rebuild options from the new data", async (t) => {
  const state = setup(t, fixture);
  state.marketPlatformFilter.value = ["qq_official"];
  state.selectedSource.value = "https://example.com/registry.json";
  state.pluginMarketData.value = [{ name: "custom", support_platforms: ["custom_adapter"] }];
  await vue.nextTick();
  assert.equal(state.marketPlatformFilter.value.length, 0);
  assert.deepEqual(names(state.filteredMarketPlugins.value), ["custom"]);
  assert.deepEqual(Array.from(state.marketPlatformItems.value, (item) => item.value), ["__undeclared__", "custom_adapter"]);
});

test("installed metadata backfill updates platform options and matching", (t) => {
  const state = setup(t, [{ name: "local", repo: "https://github.com/example/local" }]);
  state.marketPlatformFilter.value = ["telegram"];
  assert.equal(state.filteredMarketPlugins.value.length, 0);
  state.extension_data.data = [{ name: "local", repo: "https://github.com/example/local", support_platforms: ["telegram"] }];
  state.checkAlreadyInstalled();
  assert.deepEqual(names(state.filteredMarketPlugins.value), ["local"]);
  assert.ok(state.marketPlatformItems.value.some((item) => item.value === "telegram"));
});
