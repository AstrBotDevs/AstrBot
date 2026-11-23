import assert from "node:assert/strict";
import { test } from "vitest";
import { transformItems } from "vuetify/lib/composables/list-items.mjs";
import ConfigItemRenderer from "../src/components/shared/ConfigItemRenderer.vue";
import { mergeDynamicTranslations } from "../src/i18n/composables.ts";
import { mountDashboard } from "./helpers/components.mjs";

async function loadSelectItems({ props = {}, translations = {}, pluginTranslations = {} } = {}) {
  const pluginI18n = { "en-US": { config: { [props.configKey || "mode"]: pluginTranslations } } };
  const { wrapper } = await mountDashboard(ConfigItemRenderer, {
    props: { ...props, ...(props.pluginName ? { pluginI18n } : {}) },
  });
  const field = {};
  for (const [key, value] of Object.entries(translations)) {
    const parts = key.split(".");
    let target = field;
    for (const part of parts.slice(0, -1)) target = target[part] ||= {};
    target[parts.at(-1)] = value;
  }
  mergeDynamicTranslations("features.config-metadata", { "en-US": field });
  return (metadata) => wrapper.vm.getSelectItems(metadata);
}

test("displays labels and subtitles while preserving option values", async () => {
  const getItems = await loadSelectItems();
  const items = getItems({
    options: ["serpapi", "deepseek"],
    labels: ["SerpApi", "DeepSeek Search API"],
    subtitles: ["Google web, images, scholar, and finance search", "Official search API"],
  });
  const transformed = transformItems(
    {
      itemTitle: "title",
      itemValue: "value",
      itemProps: "props",
      itemChildren: "children",
    },
    items,
  );

  assert.equal(transformed[0].title, "SerpApi");
  assert.equal(transformed[0].props.subtitle, "Google web, images, scholar, and finance search");
  assert.equal(transformed[1].props.subtitle, "Official search API");
  assert.deepEqual(
    Array.from(transformed, (item) => item.value),
    ["serpapi", "deepseek"],
  );
});

test("allows subtitles without labels and tolerates omitted or empty entries", async () => {
  const getItems = await loadSelectItems();
  const items = getItems({ options: [0, false, "third"], subtitles: ["First option", ""] });

  assert.equal(items[0].title, 0);
  assert.equal(items[0].value, 0);
  assert.equal(items[0].props.subtitle, "First option");
  assert.equal(items[1].value, false);
  assert.equal(items[1].props.subtitle, "");
  assert.equal(items[2].props.subtitle, undefined);
});

test("resolves core translation keys for both labels and subtitles", async () => {
  const getItems = await loadSelectItems({
    translations: {
      "field.labels": ["Translated title"],
      "field.subtitles": ["Translated subtitle"],
    },
  });
  const items = getItems({
    options: ["value"],
    labels: "field.labels",
    subtitles: "field.subtitles",
  });

  assert.equal(items[0].title, "Translated title");
  assert.equal(items[0].props.subtitle, "Translated subtitle");
});

test("uses plugin translations and falls back to schema subtitles when absent", async () => {
  const props = { pluginName: "example", configKey: "mode", pluginI18n: { "en-US": {} } };
  const metadata = { options: ["fast"], labels: ["Fast"], subtitles: ["Schema subtitle"] };
  const getTranslated = await loadSelectItems({
    props,
    pluginTranslations: {
      labels: ["Translated title"],
      subtitles: ["Plugin subtitle"],
    },
  });
  const getFallback = await loadSelectItems({ props, pluginTranslations: { labels: ["Translated title"] } });

  assert.equal(getTranslated(metadata)[0].props.subtitle, "Plugin subtitle");
  assert.equal(getFallback(metadata)[0].props.subtitle, "Schema subtitle");
});

test("keeps plain options unchanged and ignores missing or malformed subtitles", async () => {
  const getItems = await loadSelectItems();
  const options = ["first", "second"];

  assert.equal(getItems({ options }), options);
  assert.equal(getItems({ options, subtitles: "missing.key" }), options);
  assert.equal(getItems({ options, subtitles: { first: "Invalid" } }), options);
  const labeled = getItems({ options, labels: ["First"] });
  assert.equal(labeled[0].title, "First");
  assert.equal(labeled[1].title, "second");
  assert.equal(labeled[0].props.subtitle, undefined);
});
