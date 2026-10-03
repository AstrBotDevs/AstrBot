import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { compileScript, compileTemplate, parse } from "vue/compiler-sfc";

const MARKET_TAB_FILE = new URL(
  "../src/views/extension/MarketPluginsTab.vue",
  import.meta.url,
);

test("marketplace view controls compile against setup state bindings", async () => {
  const source = await readFile(MARKET_TAB_FILE, "utf8");
  const filename = MARKET_TAB_FILE.pathname;
  const parsed = parse(source, { filename });

  assert.deepEqual(parsed.errors, []);
  assert.ok(parsed.descriptor.template);

  const script = compileScript(parsed.descriptor, { id: "market-plugins-tab" });
  const template = compileTemplate({
    id: "market-plugins-tab",
    filename,
    source: parsed.descriptor.template.content,
    compilerOptions: { bindingMetadata: script.bindings },
  });

  assert.deepEqual(template.errors, []);

  const setupBindings = [
    "marketIsListView",
    "marketPluginHeaders",
    "marketItemsPerPage",
    "marketItemsPerPageOptions",
    "getMarketPluginKey",
    "formatMarketUpdatedAt",
  ];
  for (const binding of setupBindings) {
    assert.ok(
      script.bindings[binding],
      `${binding} must be defined by script setup`,
    );
    assert.match(template.code, new RegExp(`\\$setup\\.${binding}\\b`));
    assert.doesNotMatch(template.code, new RegExp(`_ctx\\.${binding}\\b`));
  }

  assert.equal(script.bindings.PluginPlatformChip, "setup-const");
  assert.match(template.code, /\$setup\["PluginPlatformChip"\]/);
});
