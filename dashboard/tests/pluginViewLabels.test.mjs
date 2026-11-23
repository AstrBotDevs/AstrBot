import assert from "node:assert/strict";
import { test } from "vitest";
import { initI18n, useI18n } from "../src/i18n/composables.ts";
import { resolvePluginViewText, usePluginI18n } from "../src/utils/pluginI18n.js";

const page = {
  name: "context",
  title: "Default title",
  description: "Default description",
};
const i18n = {
  "en-US": {
    views: { context: { title: "Context usage" } },
    pages: {
      context: { title: "Legacy title", description: "Legacy description" },
    },
  },
  "zh-CN": { views: { context: { title: "上下文用量" } } },
};

test("view labels prefer current translations, including legacy descriptions, field by field", () => {
  assert.equal(resolvePluginViewText(i18n, "en-US", page, "title"), "Context usage");
  assert.equal(resolvePluginViewText(i18n, "en-US", page, "description"), "Legacy description");
  assert.equal(resolvePluginViewText(i18n, "fr-FR", page, "title"), "上下文用量");
  assert.equal(resolvePluginViewText({}, "en-US", page, "title"), "Default title");
  assert.equal(resolvePluginViewText({}, "en-US", page, "description"), "Default description");
  assert.equal(resolvePluginViewText({}, "en-US", { name: "context" }, "title"), "context");
  assert.equal(resolvePluginViewText({}, "en-US", { name: "context" }, "description"), "");
});

test("blank or invalid translations do not replace metadata defaults", () => {
  const broken = {
    "en-US": { views: { context: { title: "  ", description: 42 } } },
  };
  assert.equal(resolvePluginViewText(broken, "en-US", page, "title"), "Default title");
  assert.equal(resolvePluginViewText(broken, "en-US", page, "description"), "Default description");
});

test("page labels react to locale changes and resolve metadata by view name", async () => {
  const plugin = { i18n, views: [page] };
  const labels = usePluginI18n();
  await initI18n("en-US");
  assert.equal(labels.pluginViewTitle(plugin, "context"), "Context usage");
  await useI18n().setLocale("zh-CN");
  assert.equal(labels.pluginViewTitle(plugin, page), "上下文用量");
  assert.equal(labels.pluginViewDescription({ views: [page] }, "context"), "Default description");
});

test("locale switching updates the document, persisted preference and the reload event exactly once", async () => {
  await initI18n("en-US");
  const observed = [];
  const listener = (event) => observed.push(event.detail.locale);
  window.addEventListener("astrbot-locale-changed", listener);
  try {
    const i18n = useI18n();
    for (const locale of ["zh-CN", "ru-RU", "ja-JP", "en-US"]) {
      await i18n.setLocale(locale);
      assert.equal(i18n.locale.value, locale);
      assert.equal(document.documentElement.lang, locale);
      assert.equal(localStorage.getItem("astrbot-locale"), locale);
      assert.equal(i18n.isLoaded.value, true);
      assert.equal(observed.at(-1), locale);
      const count = observed.length;
      await i18n.setLocale(locale);
      assert.equal(observed.length, count, "setting the same locale must not trigger duplicate reloads");
    }
    assert.deepEqual(observed, ["zh-CN", "ru-RU", "ja-JP", "en-US"]);
  } finally {
    window.removeEventListener("astrbot-locale-changed", listener);
  }
});
