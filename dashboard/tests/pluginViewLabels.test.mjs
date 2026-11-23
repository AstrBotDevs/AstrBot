import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const locale = { value: "en-US" };
const source = readFileSync(
  new URL("../src/utils/pluginI18n.js", import.meta.url),
  "utf8",
);
const context = vm.createContext({ useI18n: () => ({ locale }) });
vm.runInContext(
  source
    .replace(/^import .*;$/gm, "")
    .replace(/export function /g, "function "),
  context,
);
const { resolvePluginViewText, usePluginI18n } = context;
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
  assert.equal(
    resolvePluginViewText(i18n, "en-US", page, "title"),
    "Context usage",
  );
  assert.equal(
    resolvePluginViewText(i18n, "en-US", page, "description"),
    "Legacy description",
  );
  assert.equal(
    resolvePluginViewText(i18n, "fr-FR", page, "title"),
    "上下文用量",
  );
  assert.equal(
    resolvePluginViewText({}, "en-US", page, "title"),
    "Default title",
  );
  assert.equal(
    resolvePluginViewText({}, "en-US", page, "description"),
    "Default description",
  );
  assert.equal(
    resolvePluginViewText({}, "en-US", { name: "context" }, "title"),
    "context",
  );
  assert.equal(
    resolvePluginViewText({}, "en-US", { name: "context" }, "description"),
    "",
  );
});

test("blank or invalid translations do not replace metadata defaults", () => {
  const broken = {
    "en-US": { views: { context: { title: "  ", description: 42 } } },
  };
  assert.equal(
    resolvePluginViewText(broken, "en-US", page, "title"),
    "Default title",
  );
  assert.equal(
    resolvePluginViewText(broken, "en-US", page, "description"),
    "Default description",
  );
});

test("page labels react to locale changes and resolve metadata by view name", () => {
  const plugin = { i18n, views: [page] };
  const labels = usePluginI18n();
  locale.value = "en-US";
  assert.equal(labels.pluginViewTitle(plugin, "context"), "Context usage");
  locale.value = "zh-CN";
  assert.equal(labels.pluginViewTitle(plugin, page), "上下文用量");
  assert.equal(
    labels.pluginViewDescription({ views: [page] }, "context"),
    "Default description",
  );
});
