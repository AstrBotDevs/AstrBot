import { createPinia, setActivePinia } from "pinia";
import { beforeEach, expect, test, vi } from "vitest";
import { useCommonStore } from "@/stores/common";
import { useCommonStore as javascriptStore } from "../src/stores/common.js";
import { useCommonStore as typescriptStore } from "../src/stores/common.ts";

const api = vi.hoisted(() => ({ market: vi.fn(), version: vi.fn(), startTime: vi.fn() }));
vi.mock("@/api/v1", () => ({ pluginApi: { market: api.market }, statsApi: api }));
vi.mock("@/utils/request", () => ({ resolveApiUrl: (path) => path }));
const ok = (data) => ({ data: { status: "ok", data } });

beforeEach(() => {
  setActivePinia(createPinia());
  for (const method of Object.values(api)) method.mockReset();
});

test("JavaScript, TypeScript, and application imports share one complete store", async () => {
  expect(javascriptStore).toBe(typescriptStore);
  expect(useCommonStore).toBe(typescriptStore);
  const store = useCommonStore();
  expect(javascriptStore()).toBe(store);
  expect(typeof store.createEventSource).toBe("function");
  api.version.mockResolvedValue(ok({ version: "v4.25.0", dashboard_version: "2026.11" }));
  expect(await store.fetchAstrBotVersion()).toBe("4.25.0");
  expect(store.dashboardVersion).toBe("2026.11");
  expect(await typescriptStore().fetchAstrBotVersion()).toBe("4.25.0");
  expect(api.version).toHaveBeenCalledTimes(1);
  api.version.mockResolvedValueOnce(ok({ version: "V4.26.0" }));
  expect(await store.fetchAstrBotVersion(true)).toBe("4.26.0");
  expect(store.dashboardVersion).toBe("");
});

test("custom registry caches stay isolated and preserve market metadata", async () => {
  const store = useCommonStore();
  api.market.mockResolvedValueOnce(
    ok({
      $meta: { page: 1 },
      alpha: {
        name: "alpha",
        author: "author",
        download_count: "12.8",
        support_platforms: null,
        support_platform: ["discord"],
        i18n: { en: { title: "Alpha" } },
        custom_field: "retained",
      },
    }),
  );
  const first = await store.getPluginCollections(false, " https://registry.example/ ");
  expect(api.market).toHaveBeenLastCalledWith({
    force_refresh: undefined,
    custom_registry: "https://registry.example",
  });
  expect(first).toHaveLength(1);
  expect(first[0]).toMatchObject({
    name: "alpha",
    market_plugin_id: "author/alpha",
    download_count: 12,
    support_platforms: ["discord"],
    custom_field: "retained",
    i18n: { en: { title: "Alpha" } },
  });
  expect(await store.getPluginCollections(false, "https://registry.example")).toEqual(first);
  expect(api.market).toHaveBeenCalledTimes(1);
  api.market.mockResolvedValueOnce(ok({ beta: { name: "beta" } }));
  const defaults = await store.getPluginCollections();
  expect(defaults.map((plugin) => plugin.name)).toEqual(["beta"]);
  expect(store.pluginMarketData.map((plugin) => plugin.name)).toEqual(["beta"]);
  expect(await store.getPluginCollections(false, "https://registry.example")).toEqual(first);
  api.market.mockRejectedValueOnce(new Error("registry unavailable"));
  await expect(store.getPluginCollections(true, "https://registry.example")).rejects.toThrow("registry unavailable");
  expect(await store.getPluginCollections(false, "https://registry.example")).toEqual(first);
});

test("start-time values are numeric and malformed responses never look like a restart", async () => {
  const store = useCommonStore();
  api.startTime.mockResolvedValueOnce(ok({ start_time: "1700000000" }));
  expect(await store.fetchStartTime()).toBe(1700000000);
  expect(store.getStartTime()).toBe(1700000000);
  expect(api.startTime).toHaveBeenCalledTimes(1);
  api.startTime.mockResolvedValueOnce(ok({ start_time: "invalid" }));
  expect(await store.fetchStartTime()).toBe(-1);
});

test("a custom registry named constructor loads and caches its empty result", async () => {
  const store = useCommonStore();
  // A hydrated cache can have the ordinary object prototype.
  store.pluginMarketDataBySource = {};
  api.market.mockResolvedValueOnce(ok({}));

  expect(await store.getPluginCollections(false, "constructor")).toEqual([]);
  expect(api.market).toHaveBeenCalledExactlyOnceWith({
    force_refresh: undefined,
    custom_registry: "constructor",
  });
  expect(await store.getPluginCollections(false, "constructor")).toEqual([]);
  expect(api.market).toHaveBeenCalledTimes(1);
});

test("a malformed registry cache is replaced with the fetched plugin list", async () => {
  const store = useCommonStore();
  store.pluginMarketDataBySource.custom = { stale: true };
  api.market.mockResolvedValueOnce(ok({ alpha: { name: "alpha" } }));

  const plugins = await store.getPluginCollections(false, "custom");
  expect(plugins.map((plugin) => plugin.name)).toEqual(["alpha"]);
  expect(store.pluginMarketDataBySource.custom).toEqual(plugins);
  expect(await store.getPluginCollections(false, "custom")).toEqual(plugins);
  expect(api.market).toHaveBeenCalledTimes(1);
});
