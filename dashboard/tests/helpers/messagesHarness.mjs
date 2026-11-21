import { markRaw, reactive, ref } from "vue";
import { webcrypto } from "node:crypto";
import { loadSource, mountSetup } from "./vueHarness.mjs";

/**
 * Mount useMessages on session "one" with in-memory storage, a stub
 * WebSocket and pending fetch requests.
 *
 * @param {Record<string, unknown>} prefs Options stored for session "one".
 */
export function messagesHarness(prefs = {}) {
  // ChatUI preferences are stored per logged-in user.
  const storage = new Map([["user", "alice"]]);
  const requests = [];
  const sockets = [];
  const localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  const sessionPrefs = loadSource(
    new URL("../../src/utils/chatSessionPrefs.mjs", import.meta.url),
    {},
    { localStorage },
  );
  const choices = loadSource(
    new URL("../../src/composables/useActionRowChoices.ts", import.meta.url),
    {},
    { localStorage },
  );
  for (const [key, value] of Object.entries(prefs)) {
    sessionPrefs.writeChatSessionPref("one", key, value);
  }
  class Socket {
    static OPEN = 1;
    static CONNECTING = 0;
    readyState = 1;
    constructor() {
      // Vue proxies would break the transport's identity checks.
      markRaw(this);
      sockets.push(this);
    }
    send(payload) {
      this.sent = JSON.parse(payload);
    }
    close() {
      this.readyState = 3;
    }
  }
  const api = loadSource(
    new URL("../../src/composables/useMessages.ts", import.meta.url),
    {
      "@/utils/chatSessionPrefs.mjs": sessionPrefs,
      "@/composables/useActionRowChoices": choices,
      "@/i18n/composables": {
        useI18n: () => ({ locale: ref("en-US"), t: (key) => key }),
      },
      "@/api/v1": {
        chatApi: {
          sendStreamUrl: () => "/send",
          regenerateMessageUrl: () => "/regenerate",
          unifiedWebSocketUrl: () => "ws://test.invalid",
        },
        fileApi: {},
      },
      "@/api/http": {
        fetchWithAuth: (url, request) =>
          new Promise((resolve) => requests.push({ url, request, resolve })),
      },
    },
    {
      localStorage,
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
  const send = (transport) =>
    messages.sendMessageStream({
      sessionId: "one",
      messageId: "request",
      parts: [],
      botRecord: bot,
      transport,
    });
  const emit = (payload) =>
    sockets[0].onmessage({
      data: JSON.stringify({ ct: "chat", ...payload, message_id: "request" }),
    });
  return {
    api,
    sessionPrefs,
    choices,
    localStorage,
    storage,
    requests,
    sockets,
    messages,
    bot,
    send,
    emit,
    stop: mounted.stop,
  };
}
