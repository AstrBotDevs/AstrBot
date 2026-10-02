import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { test } from "node:test";
import defaults from "./fixtures/sponsorCatalog.mjs";

test("logged-in dashboard requests keep credentials on their configured backend", async (t) => {
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const nativeFetch = globalThis.fetch;
  const requestModuleUrl = new URL("../src/utils/request.ts", import.meta.url).href;
  const hooks = registerHooks({
    resolve(specifier, context, nextResolve) {
      return nextResolve(specifier === "@/utils/request" ? requestModuleUrl : specifier, context);
    },
    load(url, context, nextLoad) {
      const result = nextLoad(url, context);
      if (url !== requestModuleUrl) return result;
      return {
        ...result,
        source: readFileSync(new URL(url), "utf8").replaceAll(
          "import.meta.env",
          '({ VITE_API_BASE: "", BASE_URL: "/" })',
        ),
      };
    },
  });
  t.after(() => {
    hooks.deregister();
    globalThis.fetch = nativeFetch;
    if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
    else delete globalThis.window;
    if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
    else delete globalThis.localStorage;
  });
  const storage = new Map([
    ["token", "test-dashboard-token"],
    ["astrbot-locale", "zh-CN"],
  ]);
  const requests = [];
  const fetchStub = async (input, init) => {
    const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
    requests.push({ input, init, headers });
    return Response.json(defaults);
  };
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: {
      location: new URL("http://localhost:3000/#/providers"),
      fetch: fetchStub,
    },
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    writable: true,
    value: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
  });
  const { setupHttpClient, httpClient, apiV1Client } = await import("../src/api/http.ts");
  const { setApiBaseUrl } = await import("../src/utils/request.ts");
  setupHttpClient();
  globalThis.fetch = window.fetch;

  await t.test("sponsor loading uses the real auth wrapper without leaking a token and writes its cache", async () => {
    const { loadSponsorCatalog, sponsorCatalog } = await import("../src/utils/sponsorCatalog.ts");
    await loadSponsorCatalog();
    assert.equal(requests.length, 1);
    assert.equal(requests[0].input, "https://sponsors.astrbot.app/providers.json");
    assert.equal(requests[0].headers.has("Authorization"), false);
    assert.equal(requests[0].headers.has("Accept-Language"), false);
    assert.equal(requests[0].headers.get("Accept"), "application/json");
    assert.equal(requests[0].init.credentials, "omit");
    assert.equal(sponsorCatalog.value.sponsors.length, 3);
    const cache = JSON.parse(storage.get("astrbot:sponsor-catalog:v2"));
    assert.equal(cache.catalog.sponsors.length, 3);
    assert.ok(cache.fetchedAt > 0);
    await loadSponsorCatalog();
    assert.equal(requests.length, 1);
  });
  await t.test(
    "fetch URL, Request, protocol-relative and different-port destinations do not receive automatic auth",
    async () => {
      for (const input of [
        "https://example.com/api",
        "//example.com/api",
        "http://localhost:3001/api",
        new URL("https://example.com/api"),
        new Request("https://example.com/api"),
      ]) {
        await window.fetch(input);
        assert.equal(requests.at(-1).headers.has("Authorization"), false);
        assert.equal(requests.at(-1).headers.has("Accept-Language"), false);
      }
      await window.fetch("https://example.com/api", {
        headers: { Authorization: "Bearer explicit-third-party-token" },
      });
      assert.equal(requests.at(-1).headers.get("Authorization"), "Bearer explicit-third-party-token");
    },
  );
  await t.test("same-origin fetch and streaming requests retain auth, locale, and explicit headers", async () => {
    for (const input of [
      "/api/v1/config",
      new URL("http://localhost:3000/api/v1/config"),
      new Request("http://localhost:3000/api/v1/chat/send"),
    ]) {
      await window.fetch(input);
      assert.equal(requests.at(-1).headers.get("Authorization"), "Bearer test-dashboard-token");
      assert.equal(requests.at(-1).headers.get("Accept-Language"), "zh-CN");
    }
    await window.fetch("/api/v1/chat/send", {
      headers: {
        Authorization: "Bearer explicit-local-token",
        "Accept-Language": "en-US",
      },
    });
    assert.equal(requests.at(-1).headers.get("Authorization"), "Bearer explicit-local-token");
    assert.equal(requests.at(-1).headers.get("Accept-Language"), "en-US");
  });
  await t.test("a configured remote backend receives auth without leaking it to other origins", async () => {
    const adapter = async (config) => ({ status: 200, statusText: "OK", headers: {}, data: config, config });
    try {
      for (const baseUrl of ["https://backend.example", "https://backend.example/api"]) {
        setApiBaseUrl(baseUrl);
        await window.fetch("/api/v1/config");
        assert.equal(requests.at(-1).input, "https://backend.example/api/v1/config");
        assert.equal(requests.at(-1).headers.get("Authorization"), "Bearer test-dashboard-token");
        assert.equal(requests.at(-1).headers.get("Accept-Language"), "zh-CN");
        const response = await apiV1Client.get("/config", { adapter });
        assert.equal(apiV1Client.getUri(response.data), "https://backend.example/api/v1/config");
        assert.equal(response.data.headers.get("Authorization"), "Bearer test-dashboard-token");
        for (const url of ["http://localhost:3000/api/v1/config", "https://example.com/api"]) {
          await window.fetch(url);
          assert.equal(requests.at(-1).headers.has("Authorization"), false);
          assert.equal(requests.at(-1).headers.has("Accept-Language"), false);
          const external = await httpClient.get(url, { adapter });
          assert.equal(external.data.headers.has("Authorization"), false);
          assert.equal(external.data.headers.has("Accept-Language"), false);
        }
      }
    } finally {
      setApiBaseUrl("");
    }
  });
  await t.test("Axios resolves relative URLs and base URLs before attaching credentials", async () => {
    const adapter = async (config) => ({
      status: 200,
      statusText: "OK",
      headers: {},
      data: config.headers,
      config,
    });
    for (const config of [
      { url: "https://example.com/catalog" },
      { url: "//example.com/catalog" },
      { url: "/catalog", baseURL: "https://example.com" },
      { url: "http://localhost:3001/api" },
    ]) {
      const response = await httpClient.request({ ...config, adapter });
      assert.equal(response.data.has("Authorization"), false);
      assert.equal(response.data.has("Accept-Language"), false);
    }
    for (const client of [httpClient, apiV1Client]) {
      const response = await client.get("/config", { adapter });
      assert.equal(response.data.get("Authorization"), "Bearer test-dashboard-token");
      assert.equal(response.data.get("Accept-Language"), "zh-CN");
    }
    const response = await httpClient.get("https://example.com/api", {
      adapter,
      headers: { Authorization: "Bearer explicit-third-party-token" },
    });
    assert.equal(response.data.get("Authorization"), "Bearer explicit-third-party-token");
  });
});
