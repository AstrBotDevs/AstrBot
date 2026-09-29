import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as vue from "vue";

function setup() {
  const sources = [];
  const requests = [];
  const cleanups = [];
  class EventSource {
    constructor(url) {
      this.url = url;
      sources.push(this);
    }
    close() {
      this.closed = true;
    }
  }
  const api = {
    sessionEventsUrl: (id) => `/sessions/${id}/events`,
    sendStreamUrl: () => "/chat",
    getSession: (id) =>
      new Promise((resolve) => requests.push({ id, resolve })),
  };
  const module = { exports: {} };
  const source = readFileSync(
    new URL("../src/composables/useMessages.ts", import.meta.url),
    "utf8",
  );
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  vm.runInNewContext(output, {
    exports: module.exports,
    require: (name) =>
      ({
        vue: { ...vue, onBeforeUnmount: (fn) => cleanups.push(fn) },
        "event-source-polyfill": { EventSourcePolyfill: EventSource },
        "@/api/v1": { chatApi: api, fileApi: {} },
        "@/api/http": { fetchWithAuth: () => new Promise(() => {}) },
      })[name],
    localStorage: { getItem: () => "token" },
    AbortController,
    console,
    URL,
    setTimeout,
    clearTimeout,
  });
  const current = vue.ref("one");
  const scope = vue.effectScope();
  const messages = scope.run(() =>
    module.exports.useMessages({ currentSessionId: current }),
  );
  messages.loadedSessions.one = true;
  const resolve = (index, ids) =>
    requests[index].resolve({
      data: {
        status: "ok",
        data: {
          history: ids.map((id) => ({
            id,
            content: {
              type: "bot",
              message: [{ type: "plain", text: "reminder" }],
            },
          })),
          page: 1,
          page_size: 50,
          total: ids.length,
          has_more: false,
        },
      },
    });
  return {
    sources,
    requests,
    messages,
    current,
    resolve,
    stop: () => {
      scope.stop();
      cleanups.forEach((fn) => fn());
    },
  };
}

test("history notifications coalesce requests and retain previously loaded pages", async () => {
  const h = setup();
  try {
    h.messages.messagesBySession.one = [{ id: 1, content: { message: [] } }];
    h.messages.paginationBySession.one = {
      page: 2,
      page_size: 50,
      total: 60,
      has_more: true,
    };
    const refresh = h.sources[0].onmessage();
    await h.sources[0].onmessage();
    assert.equal(h.requests.length, 1);
    h.resolve(0, [50, 51]);
    await new Promise(setImmediate);
    assert.equal(
      h.requests.length,
      2,
      "a notification during refresh must trigger another read",
    );
    h.resolve(1, [50, 51, 52]);
    await refresh;
    assert.deepEqual(
      Array.from(h.messages.messagesBySession.one, (r) => r.id),
      [1, 50, 51, 52],
    );
  } finally {
    h.stop();
  }
  assert.equal(h.sources[0].closed, true);
});

test("manual history loading pauses notifications without leaving the spinner stuck", async () => {
  const h = setup();
  try {
    const load = h.messages.loadSessionMessages("one");
    assert.equal(h.sources[0].closed, true);
    await h.sources[0].onmessage();
    assert.equal(h.requests.length, 1);
    h.resolve(0, [1]);
    await load;
    assert.equal(h.messages.loadingMessages.value, false);
    assert.equal(h.sources.length, 2);
    const refresh = h.sources[1].onmessage();
    h.resolve(1, [1, 2]);
    await refresh;
    assert.equal(
      h.sources.length,
      2,
      "replacing pagination state must not reconnect in a loop",
    );
  } finally {
    h.stop();
  }
});

test("switching sessions discards an in-flight history refresh", async () => {
  const h = setup();
  try {
    const refresh = h.sources[0].onmessage();
    h.current.value = "two";
    h.messages.loadedSessions.two = true;
    assert.equal(h.sources[0].closed, true);
    assert.equal(h.sources[1].url, "/sessions/two/events");
    h.resolve(0, [1]);
    await refresh;
    assert.equal(h.messages.messagesBySession.one, undefined);
    assert.equal(h.messages.messagesBySession.two, undefined);
  } finally {
    h.stop();
  }
});

test("starting a chat run prevents stale history from overwriting the live exchange", async () => {
  const h = setup();
  try {
    const refresh = h.sources[0].onmessage();
    const parts = [{ type: "plain", text: "hello" }];
    const exchange = h.messages.createLocalExchange({
      sessionId: "one",
      messageId: "turn",
      parts,
    });
    h.messages.sendMessageStream({
      sessionId: "one",
      messageId: "turn",
      parts,
      transport: "sse",
      ...exchange,
    });
    assert.equal(h.sources[0].closed, true);
    h.resolve(0, [99]);
    await refresh;
    assert.ok(
      h.messages.messagesBySession.one.some((r) => r.id === "local-user-turn"),
    );
    assert.ok(!h.messages.messagesBySession.one.some((r) => r.id === 99));
  } finally {
    h.stop();
  }
});
