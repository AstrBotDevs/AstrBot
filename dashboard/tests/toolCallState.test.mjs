import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";
import { markRaw, nextTick, reactive, ref } from "vue";
import { loadSource, mountSetup, mountTemplate } from "./helpers/vueHarness.mjs";

function loadToolCallCard(timers) {
  return loadSource(
    new URL(
      "../src/components/chat/message_list_comps/ToolCallCard.vue",
      import.meta.url,
    ),
    { "@/i18n/composables": { useModuleI18n: () => ({ tm: (key) => key }) } },
    {
      setInterval: (fn) => {
        timers.add(fn);
        return fn;
      },
      clearInterval: (fn) => timers.delete(fn),
    },
    true,
  ).default;
}

function messagesHarness() {
  const sockets = [];
  class Socket {
    static OPEN = 1;
    static CONNECTING = 0;
    readyState = 1;
    constructor() {
      markRaw(this);
      sockets.push(this);
    }
    send() {}
    close() {
      this.readyState = 3;
    }
  }
  const storage = new Map();
  const api = loadSource(
    new URL("../src/composables/useMessages.ts", import.meta.url),
    {
      "@/i18n/composables": {
        useI18n: () => ({ locale: ref("en-US"), t: (key) => key }),
      },
      "@/api/v1": {
        chatApi: { unifiedWebSocketUrl: () => "ws://test.invalid" },
        fileApi: {},
      },
      "@/api/http": { fetchWithAuth: () => new Promise(() => {}) },
      "@/utils/chatViews": {
        streamViewAction() {},
        viewActionKey: Symbol("viewAction"),
      },
    },
    {
      localStorage: {
        getItem: (key) => storage.get(key) ?? null,
        setItem: (key, value) => storage.set(key, value),
        removeItem: (key) => storage.delete(key),
      },
      WebSocket: Socket,
      AbortController,
      TextDecoder,
      URL,
      crypto: webcrypto,
    },
  );
  let messages;
  const mounted = mountSetup({
    setup() {
      messages = api.useMessages({ currentSessionId: ref("one") });
      return {};
    },
  });
  messages.loadedSessions.one = true;
  const bot = reactive({
    id: 2,
    turn_id: "turn",
    content: { type: "bot", message: [] },
  });
  messages.messagesBySession.one = [bot];
  messages.sendMessageStream({
    sessionId: "one",
    messageId: "request",
    parts: [],
    botRecord: bot,
    transport: "websocket",
  });
  const emit = (payload) =>
    sockets[0].onmessage({
      data: JSON.stringify({ ct: "chat", ...payload, message_id: "request" }),
    });
  return { api, bot, emit, stop: mounted.stop };
}

test("a turn ending before a call returns marks only that call interrupted", async () => {
  const h = messagesHarness();
  try {
    for (const call of [
      { id: "done", name: "read", ts: 1 },
      { id: "open", name: "shell", ts: 2 },
    ]) {
      await h.emit({ type: "plain", chain_type: "tool_call", data: JSON.stringify(call) });
    }
    await h.emit({
      type: "plain",
      chain_type: "tool_call_result",
      data: JSON.stringify({ id: "done", result: "ok", ts: 3 }),
    });
    await h.emit({ type: "end", data: "" });
    const calls = h.bot.content.message.flatMap((part) => part.tool_calls || []);
    assert.deepEqual(
      calls.map((call) => [call.id, call.phase]),
      [
        ["done", undefined],
        ["open", "unknown"],
      ],
    );
  } finally {
    h.stop();
  }
});

test("a late result clears the interrupted mark", () => {
  const h = messagesHarness();
  try {
    h.api.upsertToolCall(h.bot, { id: "tool", phase: "unknown" });
    h.api.finishToolCall(h.bot, { id: "tool", result: "done", ts: 10 });
    const call = h.bot.content.message[0].tool_calls[0];
    assert.equal(call.finished_ts, 10);
    assert.equal(call.phase, undefined);
  } finally {
    h.stop();
  }
});

test("the elapsed timer follows running, interrupted and finished states", async () => {
  const timers = new Set();
  const call = reactive({ name: "shell", ts: 1 });
  const h = mountTemplate(loadToolCallCard(timers), {
    toolCall: call,
    initialExpanded: true,
  });
  const text = () =>
    h
      .findAll((node) => node.type === "text")
      .map((node) => node.text)
      .join(" ");
  try {
    assert.equal(timers.size, 1);
    call.phase = "unknown";
    await nextTick();
    assert.equal(timers.size, 0);
    assert.match(text(), /toolStatus\.interrupted/);
    call.phase = undefined;
    await nextTick();
    assert.equal(timers.size, 1);
    call.finished_ts = 2;
    await nextTick();
    assert.equal(timers.size, 0);
    assert.doesNotMatch(text(), /toolStatus\.interrupted/);
  } finally {
    h.stop();
  }
  assert.equal(timers.size, 0);
});
