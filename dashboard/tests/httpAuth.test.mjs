import assert from "node:assert/strict";
import axios from "axios";
import { beforeEach, expect, onTestFinished, test, vi } from "vitest";
import defaults from "./fixtures/sponsorCatalog.mjs";

// Vitest's jsdom Request adapter spreads RequestInit, losing getter-backed
// method/body fields when the init argument is another Request. Its native
// parent provides the real Fetch implementation used by this transport test.
const requestParent = Object.getPrototypeOf(Request);
const NativeRequest = typeof requestParent.prototype?.clone === "function" ? requestParent : Request;

let http, request, calls, transport;
beforeEach(async () => {
  vi.resetModules();
  vi.stubGlobal("Request", NativeRequest);
  localStorage.setItem("token", "test-dashboard-token");
  localStorage.setItem("astrbot-locale", "zh-CN");
  calls = [];
  transport = vi.fn(async (input, init) => {
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    calls.push({ input, init, headers });
    return Response.json(defaults);
  });
  vi.stubGlobal("fetch", transport);
  http = await import("../src/api/http.ts");
  request = await import("../src/utils/request.ts");
  request.setApiBaseUrl("");
  http.setupHttpClient();
  vi.stubGlobal("fetch", window.fetch);
});

const adapter = async (config) => ({ status: 200, statusText: "OK", headers: {}, data: config.headers, config });

test("sponsor loading uses the real auth wrapper without leaking credentials and writes its cache", async () => {
  const { loadSponsorCatalog, sponsorCatalog } = await import("../src/utils/sponsorCatalog.ts");
  await loadSponsorCatalog();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].input, "https://sponsors.astrbot.app/providers.json");
  assert.equal(calls[0].headers.has("Authorization"), false);
  assert.equal(calls[0].headers.has("Accept-Language"), false);
  assert.equal(calls[0].headers.get("Accept"), "application/json");
  assert.equal(calls[0].init.credentials, "omit");
  assert.equal(sponsorCatalog.value.sponsors.length, 3);
  const cache = JSON.parse(localStorage.getItem("astrbot:sponsor-catalog:v2"));
  assert.equal(cache.catalog.sponsors.length, 3);
  assert.ok(cache.fetchedAt > 0);
  await loadSponsorCatalog();
  assert.equal(calls.length, 1);
});

test("external fetch URL, Request, protocol-relative and different-port destinations receive no automatic credentials", async () => {
  for (const input of [
    "https://example.com/api",
    "//example.com/api",
    "http://localhost:3001/api",
    new URL("https://example.com/api"),
    new Request("https://example.com/api"),
    "/assets/avatar.png",
  ]) {
    await window.fetch(input);
    assert.equal(calls.at(-1).headers.has("Authorization"), false);
    assert.equal(calls.at(-1).headers.has("Accept-Language"), false);
  }
  await window.fetch("https://example.com/api", { headers: { Authorization: "Bearer explicit-third-party-token" } });
  assert.equal(calls.at(-1).headers.get("Authorization"), "Bearer explicit-third-party-token");
});

test("same-origin API fetch and streams retain credentials and caller-supplied headers", async () => {
  for (const input of [
    "/api/v1/config",
    new URL("http://localhost:3000/api/v1/config"),
    new Request("http://localhost:3000/api/v1/chat/send"),
  ]) {
    await window.fetch(input);
    assert.equal(calls.at(-1).headers.get("Authorization"), "Bearer test-dashboard-token");
    assert.equal(calls.at(-1).headers.get("Accept-Language"), "zh-CN");
  }
  await window.fetch("/api/v1/chat/send", {
    headers: {
      Authorization: "Bearer explicit-local-token",
      "Accept-Language": "en-US",
    },
  });
  assert.equal(calls.at(-1).headers.get("Authorization"), "Bearer explicit-local-token");
  assert.equal(calls.at(-1).headers.get("Accept-Language"), "en-US");
  http.setupHttpClient();
  await window.fetch("/api/v1/config");
  assert.equal(calls.length, 5, "installing the wrapper twice must not recurse or duplicate requests");
});

test("Axios resolves relative paths and bases before attaching API credentials", async () => {
  for (const config of [
    { url: "https://example.com/catalog" },
    { url: "//example.com/catalog" },
    { url: "/catalog", baseURL: "https://example.com" },
    { url: "http://localhost:3001/api" },
    { url: "/assets/config.json" },
  ]) {
    const response = await http.httpClient.request({ ...config, adapter });
    assert.equal(response.data.has("Authorization"), false);
    assert.equal(response.data.has("Accept-Language"), false);
  }
  for (const [client, path] of [
    [http.httpClient, "/api/v1/config"],
    [http.apiV1Client, "/config"],
  ]) {
    const response = await client.get(path, { adapter });
    assert.equal(response.data.get("Authorization"), "Bearer test-dashboard-token");
    assert.equal(response.data.get("Accept-Language"), "zh-CN");
  }
  const response = await http.httpClient.get("https://example.com/api", {
    adapter,
    headers: { Authorization: "Bearer explicit-third-party-token" },
  });
  assert.equal(response.data.get("Authorization"), "Bearer explicit-third-party-token");
});

test("configured API base is shared by fetch, Axios and websocket URLs without duplicating /api", async () => {
  request.setApiBaseUrl("https://backend.example/prefix/api/");
  const target = "https://backend.example/prefix/api/v1/chat/send";
  assert.equal(request.resolveApiUrl("/api/v1/chat/send"), target);
  assert.equal(
    request.resolveWebSocketUrl("/api/v1/chat/ws", { token: "a b" }),
    "wss://backend.example/prefix/api/v1/chat/ws?token=a+b",
  );
  const original = new Request("http://localhost:3000/api/v1/chat/send", { method: "POST", body: "payload" });
  await window.fetch(original);
  assert.equal(calls[0].input.url, target);
  assert.equal(calls[0].input.method, "POST");
  assert.equal(await calls[0].input.text(), "payload");
  assert.equal(calls[0].headers.get("Authorization"), "Bearer test-dashboard-token");
  for (const [client, path] of [
    [http.httpClient, "/api/v1/config"],
    [http.apiV1Client, "/config"],
  ]) {
    const response = await client.get(path, { adapter });
    assert.equal(axios.getUri(response.config), "https://backend.example/prefix/api/v1/config");
    assert.equal(response.data.get("Authorization"), "Bearer test-dashboard-token");
  }
  for (const url of [
    "https://backend.example/prefix/api-evil/config",
    "https://backend.example/other/api/config",
    "https://other.example/prefix/api/v1/config",
  ]) {
    await window.fetch(url);
    assert.equal(calls.at(-1).headers.has("Authorization"), false);
  }
});

const loginKeys = ["user", "token", "change_pwd_hint", "md5_pwd_hint", "legacy_pwd_hint", "password_upgrade_required"];
function rejectWith(status, data = {}) {
  return async (config) => {
    const response = { status, statusText: String(status), headers: {}, config, data };
    throw new axios.AxiosError("request failed", "ERR_BAD_REQUEST", config, undefined, response);
  };
}

for (const base of ["", "https://backend.example/prefix/api"]) {
  test(`API 401 clears login state and redirects for base ${base || "same origin"}`, async () => {
    request.setApiBaseUrl(base);
    for (const key of loginKeys) localStorage.setItem(key, "present");
    await assert.rejects(http.apiV1Client.get("/config", { adapter: rejectWith(401) }));
    for (const key of loginKeys) assert.equal(localStorage.getItem(key), null);
    assert.equal(window.location.hash, "#/auth/login");
  });
}

for (const [path, data] of [
  ["/api/auth/login", {}],
  ["/api/auth/setup", {}],
  ["/api/auth/setup-status", {}],
  ["/api/v1/auth/login", {}],
  ["/api/v1/auth/setup", {}],
  ["/api/v1/auth/setup-status", {}],
  ["/api/v1/config", { data: { totp_required: true } }],
  ["https://external.example/api/v1/config", {}],
]) {
  test(`401 challenge or external response preserves credentials: ${path}`, async () => {
    for (const key of loginKeys) localStorage.setItem(key, "present");
    window.location.hash = "#/providers";
    await assert.rejects(http.httpClient.get(path, { adapter: rejectWith(401, data) }));
    for (const key of loginKeys) assert.equal(localStorage.getItem(key), "present");
    assert.equal(window.location.hash, "#/providers");
  });
}

test("rate limit response preserves the server message", async () => {
  await expect(
    http.httpClient.get("/api/v1/config", { adapter: rejectWith(429, { message: "Try later" }) }),
  ).rejects.toBe("Try later");
});

test("root-relative API deployment bases remain same-origin across clients and transports", async () => {
  assert.equal(request.setApiBaseUrl("/proxy/api/"), "/proxy/api");
  assert.equal(request.getApiBaseUrlValidationError("/proxy/api"), "");
  assert.equal(request.resolveApiUrl("/api/v1/config"), "/proxy/api/v1/config");
  assert.equal(request.resolveWebSocketUrl("/api/v1/chat/ws"), "ws://localhost:3000/proxy/api/v1/chat/ws");
  await window.fetch("/api/v1/chat/send");
  assert.equal(calls[0].input, "/proxy/api/v1/chat/send");
  assert.equal(calls[0].headers.get("Authorization"), "Bearer test-dashboard-token");
  const response = await http.apiV1Client.get("/config", { adapter });
  assert.equal(axios.getUri(response.config), "/proxy/api/v1/config");
  assert.equal(response.data.get("Authorization"), "Bearer test-dashboard-token");
});

test("API base validation rejects unsupported schemes and malformed protocol-relative input", () => {
  for (const value of ["ftp://example.com/api", "javascript:alert(1)", "data:text/html,hello", "//example.com/api"]) {
    assert.notEqual(request.getApiBaseUrlValidationError(value), "", value);
  }
  assert.equal(request.normalizeConfiguredApiBaseUrl("backend.example/api/"), "https://backend.example/api");
  assert.equal(request.normalizeConfiguredApiBaseUrl("localhost:5000/api/"), "https://localhost:5000/api");
  assert.equal(request.normalizeConfiguredApiBaseUrl("ftp://example.com/api"), "ftp://example.com/api");
});

for (const base of ["https://backend.example/prefix/api", "/proxy/api"]) {
  test(`generated chat/provider/plugin facade calls use the configured authenticated Axios client: ${base}`, async () => {
    request.setApiBaseUrl(base);
    const originalAdapter = http.httpClient.defaults.adapter;
    const captured = [];
    http.httpClient.defaults.adapter = async (config) => {
      captured.push(config);
      return { status: 200, statusText: "OK", headers: {}, config, data: { status: "ok", data: [] } };
    };
    onTestFinished(() => {
      http.httpClient.defaults.adapter = originalAdapter;
    });
    const { chatApi, providerApi, pluginApi } = await import("../src/api/v1.ts");
    for (const result of [
      await chatApi.getSession("session-1", { page: 2, page_size: 50 }),
      await providerApi.listByProviderType("speech_to_text"),
      await pluginApi.list(),
    ])
      assert.equal(result.data.status, "ok");
    assert.equal(captured.length, 3);
    const selectedRoot = new URL(request.resolveApiUrl("/api/"), window.location.href);
    for (const config of captured) {
      const target = new URL(axios.getUri(config), window.location.href);
      assert.equal(target.origin, selectedRoot.origin);
      assert.equal(target.pathname.startsWith(selectedRoot.pathname), true);
      assert.equal(config.headers.get("Authorization"), "Bearer test-dashboard-token");
      assert.equal(config.headers.get("Accept-Language"), "zh-CN");
    }
    const history = new URL(axios.getUri(captured[0]), window.location.href);
    assert.equal(history.searchParams.get("page"), "2");
    assert.equal(history.searchParams.get("page_size"), "50");
  });
}
