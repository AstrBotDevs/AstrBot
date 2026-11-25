import assert from "node:assert/strict";
import test from "node:test";
import { createMemoryHistory, createRouter } from "vue-router";
import {
  getPluginInstallReturnUrl,
  parsePluginInstallLink,
} from "../src/utils/pluginInstallLink.mjs";

test("market links use an exact plugin ID and optionally a custom source", () => {
  const market_plugin_id = "alice/astrbot_plugin_weather";
  assert.deepEqual(parsePluginInstallLink({ market_plugin_id }), {
    pluginId: market_plugin_id,
    registryUrl: null,
  });
  assert.deepEqual(
    parsePluginInstallLink({
      market_plugin_id,
      registry_url: "https://market.example/plugins.json?channel=stable",
    }),
    {
      pluginId: market_plugin_id,
      registryUrl: "https://market.example/plugins.json?channel=stable",
    },
  );
});

test("invalid or ambiguous links do not produce an install target", () => {
  const market_plugin_id = "alice/plugin";
  const install_url = "https://github.com/alice/plugin";
  for (const query of [
    { install_url, market_plugin_id },
    { registry_url: "https://market.example/plugins.json" },
    { market_plugin_id: [market_plugin_id, "bob/plugin"] },
    { market_plugin_id, registry_url: null },
    { market_plugin_id, registry_url: "http://market.example/plugins.json" },
    { install_url: "https://market.example/plugin.zip" },
  ]) {
    assert.ok(parsePluginInstallLink(query).error);
  }
  assert.deepEqual(parsePluginInstallLink({ install_url }), {
    repository: install_url,
  });
});

test("auth redirects preserve encoded market parameters and stay inside the plugin page", () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/extension/plugins", component: {} },
      { path: "/auth/login", component: {} },
      { path: "/auth/setup", component: {} },
    ],
  });
  const query = {
    market_plugin_id: "alice/plugin",
    registry_url: "https://market.example/plugins.json?channel=stable&key=1",
  };
  const redirect = router.resolve({
    path: "/extension/plugins",
    query,
  }).fullPath;
  const login = router.resolve({ path: "/auth/login", query: { redirect } });
  const setup = router.resolve({ path: "/auth/setup", query: login.query });
  assert.deepEqual(
    router.resolve(getPluginInstallReturnUrl(router, setup.query.redirect))
      .query,
    query,
  );
  assert.equal(
    getPluginInstallReturnUrl(router, "//market.example/extension/plugins"),
    undefined,
  );
  assert.equal(
    getPluginInstallReturnUrl(router, "/extension/plugins"),
    undefined,
  );
});
