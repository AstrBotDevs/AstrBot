import net from "node:net";
import { enableAutoUnmount } from "@vue/test-utils";
import { afterAll, afterEach, beforeEach, expect, vi } from "vitest";

const nativeConnect = net.Socket.prototype.connect;
const hasDOM = typeof window !== "undefined";
const nativeOpen = globalThis.XMLHttpRequest?.prototype.open;
const isLoopback = (host) => ["localhost", "127.0.0.1", "::1", "[::1]"].includes(host);
const unexpectedNetworkCalls = [];
function blocked(message) {
  unexpectedNetworkCalls.push(message);
  return new Error(message);
}

net.Socket.prototype.connect = function (...args) {
  const first = Array.isArray(args[0]) ? args[0][0] : args[0];
  const options = typeof first === "object" ? first : { port: first, host: args[1] };
  if (!options.path && typeof options.host === "string" && !isLoopback(options.host)) {
    throw blocked(`External socket blocked by frontend tests: ${options.host}`);
  }
  return nativeConnect.apply(this, args);
};
if (nativeOpen)
  XMLHttpRequest.prototype.open = function (method, url) {
    throw blocked(`Unexpected XHR ${method} ${url}: install a transport fixture in this test`);
  };

const denyFetch = () => Promise.reject(blocked("Unexpected fetch: install a transport fixture in this test"));
class DeniedWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  constructor() {
    throw blocked("Unexpected WebSocket: install a transport fixture in this test");
  }
}
class DeniedEventSource {
  constructor() {
    throw blocked("Unexpected EventSource: install a transport fixture in this test");
  }
}

function installBrowserBoundaries() {
  vi.stubEnv("VITE_API_BASE", "");
  for (const key of [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "NODE_USE_ENV_PROXY",
    "GLOBAL_AGENT_HTTP_PROXY",
    "GLOBAL_AGENT_HTTPS_PROXY",
  ])
    vi.stubEnv(key, undefined);
  vi.stubGlobal("fetch", denyFetch);
  vi.stubGlobal("WebSocket", DeniedWebSocket);
  vi.stubGlobal("EventSource", DeniedEventSource);
  if (hasDOM && !window.matchMedia)
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
}
installBrowserBoundaries();
let unmountAll;
enableAutoUnmount((callback) => {
  unmountAll = callback;
});

beforeEach(() => {
  if (hasDOM) {
    localStorage.clear();
    sessionStorage.clear();
    window.history.replaceState({}, "", "/");
  }
  installBrowserBoundaries();
});

afterEach(() => {
  unmountAll();
  if (vi.isFakeTimers()) {
    vi.clearAllTimers();
    vi.useRealTimers();
  }
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  installBrowserBoundaries();
  if (hasDOM) document.body.replaceChildren();
  expect(unexpectedNetworkCalls.splice(0), "Every test must control its network dependencies").toEqual([]);
});

afterAll(() => {
  net.Socket.prototype.connect = nativeConnect;
  if (nativeOpen) XMLHttpRequest.prototype.open = nativeOpen;
});
