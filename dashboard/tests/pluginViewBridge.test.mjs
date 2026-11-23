import assert from "node:assert/strict";
import { onTestFinished, test, vi } from "vitest";

let disposePrevious;
async function setupBridge(target = "chat_message") {
  disposePrevious?.();
  vi.resetModules();
  const sent = [];
  const listeners = [];
  let resize;
  let bodyHeight = 410;
  let uuid = 0;
  const parent = window.parent;
  const nativeAdd = window.addEventListener.bind(window);
  const nativeRemove = window.removeEventListener.bind(window);
  const add = vi.spyOn(window, "addEventListener").mockImplementation((name, handler, options) => {
    listeners.push([name, handler, options]);
    nativeAdd(name, handler, options);
  });
  const post = vi.spyOn(parent, "postMessage").mockImplementation((message) => sent.push(message));
  vi.spyOn(document.body, "getBoundingClientRect").mockImplementation(() => ({ height: bodyHeight }));
  vi.spyOn(crypto, "randomUUID").mockImplementation(() => `click-${++uuid}`);
  document.body.style.margin = "0px 0px 8px";
  document.documentElement.removeAttribute("style");
  document.documentElement.removeAttribute("data-theme");
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback) {
        resize = callback;
      }
      observe(element) {
        assert.equal(element, document.body);
      }
      disconnect() {}
    },
  );
  await import("../../astrbot/dashboard/plugin_page_bridge.js");
  let disposed = false;
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    for (const args of listeners) nativeRemove(...args);
    add.mockRestore();
    post.mockRestore();
    delete window.AstrBotPluginView;
    delete window.AstrBotPluginPage;
    document.documentElement.removeAttribute("style");
    document.documentElement.removeAttribute("data-theme");
    document.body.removeAttribute("style");
  };
  disposePrevious = dispose;
  onTestFinished(dispose);
  const context = {
    target,
    locale: "en-US",
    isDark: false,
    themeColors: { primary: "#336699", primaryText: "#111111", border: "#dddddd" },
    ...(target !== "plugin_page" ? { view: { id: "reading", revision: 1, data: { count: 0 } } } : {}),
  };
  return {
    bridge: window.AstrBotPluginView,
    window,
    parent,
    context,
    sent,
    dispose,
    styles: { get: (key) => document.documentElement.style.getPropertyValue(key) || undefined },
    attributes: { get: (key) => document.documentElement.getAttribute(key) ?? undefined },
    deliver(message, origin = window.location.origin, sender = parent) {
      window.dispatchEvent(
        new MessageEvent("message", {
          source: sender === parent ? parent : null,
          origin,
          data: {
            channel: "astrbot-plugin-page",
            ...(target !== "plugin_page" ? { session: "host-session" } : {}),
            ...message,
          },
        }),
      );
    },
    resize(height) {
      bodyHeight = height;
      resize();
    },
  };
}

for (const target of ["chat_message", "chat_workbench", "chat_workbench_with_launcher", "plugin_page"]) {
  test(`${target} shares context, automatic CSS tokens, and live theme updates`, async () => {
    const env = await setupBridge(target);
    assert.equal(env.sent[0].kind, "ready");
    assert.equal(env.window.AstrBotPluginPage, env.bridge);
    assert.equal(env.window.astrbot, undefined);
    const ready = env.bridge.ready();
    env.deliver({ kind: "context", context: env.context });
    assert.equal((await ready).target, target);
    const revisions = [];
    if (target !== "plugin_page") {
      env.bridge.view.subscribe((view) => revisions.push(view.revision));
    }
    assert.equal(env.attributes.get("data-theme"), "light");
    assert.equal(env.styles.get("color-scheme"), "light");
    assert.equal(env.styles.get("--astrbot-color-primary"), "#336699");
    assert.equal(env.styles.get("--astrbot-color-text"), "#111111");
    assert.equal(env.styles.get("background"), undefined);
    const changes = [];
    const off = env.bridge.onContext((context) => changes.push(context.isDark));
    env.deliver({
      kind: "context",
      context: {
        isDark: true,
        themeColors: {
          primary: "#99bbdd",
          primaryText: "#eeeeee",
          border: "#333333",
          background: "#161616",
          surface: "#242424",
          "on-primary": "#000000",
        },
      },
    });
    assert.deepEqual(changes, [false, true]);
    assert.equal(env.attributes.get("data-theme"), "dark");
    assert.equal(env.styles.get("color-scheme"), "dark");
    assert.equal(env.styles.get("--astrbot-color-primary"), "#99bbdd");
    assert.equal(env.styles.get("--astrbot-color-text"), "#eeeeee");
    assert.equal(env.styles.get("--astrbot-color-background"), "#161616");
    assert.equal(env.styles.get("--astrbot-color-border"), "#333333");
    // A custom palette can change without changing light/dark mode.
    env.deliver({
      kind: "context",
      context: { themeColors: { primary: "#aabbcc" } },
    });
    assert.equal(env.styles.get("--astrbot-color-primary"), "#aabbcc");
    assert.equal(env.styles.get("--astrbot-color-text"), "#e8eaed");
    off();
    env.deliver({ kind: "context", context: { isDark: false } });
    assert.equal(env.styles.get("color-scheme"), "light");
    assert.deepEqual(changes, [false, true, true]);
    assert.deepEqual(revisions, target !== "plugin_page" ? [1] : []);
  });
}

test("chat actions use the shared request protocol and apply snapshots before settling", async () => {
  const env = await setupBridge();
  env.deliver({ kind: "context", context: env.context });
  await env.bridge.ready();
  const revisions = [];
  env.bridge.view.subscribe((view) => {
    revisions.push(view.revision);
    view.data.count = 999;
  });
  assert.equal(env.bridge.getContext().view.data.count, 0);
  const pending = env.bridge.view.action("demo:increment", { amount: 1 });
  await Promise.resolve();
  const request = env.sent.at(-1);
  assert.equal(request.action, "view:action");
  assert.equal(request.input.expected_revision, 1);
  assert.equal(request.session, "host-session");
  await assert.rejects(env.bridge.view.action("demo:increment"), {
    code: "ACTION_IN_PROGRESS",
  });
  for (const delivery of [
    () =>
      env.deliver(
        {
          kind: "response",
          requestId: request.requestId,
          ok: true,
          snapshot: { revision: 99, data: {} },
        },
        "https://evil.test",
      ),
    () => env.deliver({ kind: "response", requestId: request.requestId, ok: true }, window.location.origin, {}),
    () =>
      env.deliver({
        kind: "response",
        session: "wrong",
        requestId: request.requestId,
        ok: true,
      }),
  ])
    delivery();
  assert.deepEqual(revisions, [1]);
  env.deliver({
    kind: "response",
    requestId: request.requestId,
    ok: true,
    snapshot: { id: "reading", revision: 2, data: { count: 1 } },
  });
  await pending;
  assert.deepEqual(revisions, [1, 2]);
  env.deliver({
    kind: "context",
    context: { view: env.context.view, isDark: true },
  });
  assert.deepEqual(revisions, [1, 2]);
  assert.equal(env.attributes.get("data-theme"), "dark");
  const conflict = env.bridge.view.action("demo:increment");
  await Promise.resolve();
  env.deliver({
    kind: "response",
    requestId: env.sent.at(-1).requestId,
    ok: false,
    snapshot: { id: "reading", revision: 3, data: { count: 2 } },
    error: { code: "REVISION_CONFLICT", message: "Reloaded" },
  });
  await assert.rejects(conflict, { code: "REVISION_CONFLICT" });
  assert.deepEqual(revisions, [1, 2, 3]);
  await assert.rejects(env.bridge.apiGet("private"), {
    code: "UNSUPPORTED_CAPABILITY",
  });
});

test("existing plugin APIs, SSE, alias, and bootstrap context remain supported", async () => {
  const env = await setupBridge("plugin_page");
  env.bridge.__setInitialContext(env.context);
  assert.equal((await env.bridge.ready()).target, "plugin_page");
  env.deliver({ kind: "context", context: env.context });
  const result = env.bridge.apiPost("settings/save", { enabled: true });
  assert.equal(env.sent.at(-1).action, "api:post");
  env.deliver({
    kind: "response",
    requestId: env.sent.at(-1).requestId,
    ok: true,
    data: { saved: true },
  });
  assert.equal((await result).saved, true);
  const failed = env.bridge.apiGet("fail");
  env.deliver({
    kind: "response",
    requestId: env.sent.at(-1).requestId,
    ok: false,
    error: "Old host error",
  });
  await assert.rejects(failed, { message: "Old host error" });
  const events = [];
  const subscription = env.bridge.subscribeSSE("events", {
    onMessage: (event) => events.push(event.parsed),
  });
  const request = env.sent.at(-1);
  env.deliver({ kind: "response", requestId: request.requestId, ok: true });
  const subscriptionId = await subscription;
  env.deliver({ kind: "sse_message", subscriptionId, data: '{"count":1}' });
  assert.deepEqual(JSON.parse(JSON.stringify(events)), [{ count: 1 }]);
  await assert.rejects(env.bridge.view.action("demo:increment"), {
    code: "UNSUPPORTED_CAPABILITY",
  });
});

test("chat views report growth and shrinkage without duplicate resize messages", async () => {
  const env = await setupBridge();
  env.deliver({ kind: "context", context: env.context });
  await env.bridge.ready();
  env.resize(410);
  env.resize(410);
  env.resize(560);
  env.resize(200);
  assert.deepEqual(
    env.sent.filter((message) => message.kind === "resize").map((message) => message.height),
    [418, 568, 208],
  );
});

test("launcher views receive session changes and use plugin APIs without a message snapshot", async () => {
  const harness = await setupBridge("plugin_page");
  harness.context.target = "chat_workbench_with_launcher";
  harness.context.sessionId = "session-one";
  harness.deliver({ kind: "context", context: harness.context });
  await harness.bridge.ready();
  assert.equal(harness.bridge.getContext().sessionId, "session-one");
  const result = harness.bridge.apiGet("usage", { session_id: "session-one" });
  const request = harness.sent.at(-1);
  assert.equal(request.action, "api:get");
  harness.deliver({ kind: "response", requestId: request.requestId, ok: true, data: { count: 1 } });
  assert.equal((await result).count, 1);
  await assert.rejects(harness.bridge.view.action("run"), { code: "UNSUPPORTED_CAPABILITY" });
  harness.deliver({ kind: "context", context: { sessionId: "session-two" } });
  assert.equal(harness.bridge.getContext().sessionId, "session-two");
});

test("with-launcher views use actions only when opened with a message snapshot", async () => {
  const message = await setupBridge("chat_workbench_with_launcher");
  message.deliver({ kind: "context", context: message.context });
  await message.bridge.ready();
  const action = message.bridge.view.action("demo:increment", { amount: 1 });
  await Promise.resolve();
  const request = message.sent.at(-1);
  assert.equal(request.action, "view:action");
  message.deliver({ kind: "response", requestId: request.requestId, ok: true });
  await action;
  await assert.rejects(message.bridge.apiGet("usage"), { code: "UNSUPPORTED_CAPABILITY" });
  await assert.rejects(message.bridge.chat.send("hello"), { code: "UNSUPPORTED_CAPABILITY" });

  const resident = await setupBridge("plugin_page");
  resident.context.target = "chat_workbench_with_launcher";
  resident.context.sessionId = "session-one";
  resident.deliver({ kind: "context", context: resident.context });
  await resident.bridge.ready();
  for (const method of ["fill", "send"]) {
    const result = resident.bridge.chat[method]("hello");
    await Promise.resolve();
    const request = resident.sent.at(-1);
    assert.equal(request.action, `chat:${method}`);
    assert.equal(request.sessionId, "session-one");
    resident.deliver({ kind: "response", requestId: request.requestId, ok: true, data: { sessionId: "session-one" } });
    assert.equal((await result).sessionId, "session-one");
  }
});
