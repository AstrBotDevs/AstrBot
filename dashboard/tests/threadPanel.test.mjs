import assert from "node:assert/strict";
import test from "node:test";
import { ref } from "vue";
import { webcrypto } from "node:crypto";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";
import { messagesHarness } from "./helpers/messagesHarness.mjs";

function harness({ parent = {}, thread = {} } = {}) {
  const messages = messagesHarness();
  for (const [key, value] of Object.entries(parent))
    messages.sessionPrefs.writeChatSessionPref("parent", key, value);
  for (const [key, value] of Object.entries(thread))
    messages.sessionPrefs.writeChatSessionPref("child", key, value);
  const requests = [];
  const component = loadSource(
    new URL("../src/components/chat/ThreadPanel.vue", import.meta.url),
    {
      "@/utils/chatSessionPrefs.mjs": messages.sessionPrefs,
      "@/composables/useActionRowChoices": messages.choices,
      "@/components/chat/chatPanelTransition.css": {},
      "@/api/v1": {
        chatApi: {
          getThread: async () => ({ data: { data: { history: [] } } }),
          sendThreadMessageUrl: (id) => `/thread/${id}`,
        },
      },
      "@/api/http": {
        fetchWithAuth: (url, request) =>
          new Promise((resolve) => requests.push({ url, request, resolve })),
      },
      "@/composables/useMessages": messages.api,
      "@/i18n/composables": {
        useModuleI18n: () => ({ tm: (key) => key }),
        useI18n: () => ({ locale: ref("en") }),
      },
      "@/components/chat/ChatMessageList.vue": {},
    },
    { crypto: webcrypto, AbortController, TextDecoder },
  ).default;
  const h = mountSetup(component, {
    modelValue: true,
    thread: { thread_id: "child", parent_session_id: "parent" },
    isDark: false,
    getProviderSelection: () => ({ providerId: "p", modelName: "m" }),
  });
  const closed = () => ({
    ok: true,
    body: new ReadableStream({ start: (controller) => controller.close() }),
  });
  const send = async (text = "hello") => {
    h.state.draft = text;
    const sent = h.state.send();
    const request = requests.at(-1);
    request.resolve(closed());
    await sent;
    return JSON.parse(request.request.body);
  };
  return {
    ...h,
    messages,
    requests,
    closed,
    send,
    stop() {
      h.stop();
      messages.stop();
    },
  };
}

test("a thread starts from the parent's options and permission mode", async () => {
  const h = harness({
    parent: { reasoning_effort: "high", permission_mode: "workspace" },
  });
  try {
    const body = await h.send();
    assert.equal(body.reasoning_effort, "high");
    assert.equal(body.permission_mode, "workspace");
  } finally {
    h.stop();
  }
});

test("allow for this conversation in a thread switches only the thread", async () => {
  const h = harness({ parent: { permission_mode: "workspace" } });
  try {
    h.state.approvalPermissionMode = "full";
    assert.equal(
      h.messages.sessionPrefs.readChatSessionPrefs("child").permission_mode,
      "full",
    );
    assert.equal(
      h.messages.sessionPrefs.readChatSessionPrefs("parent").permission_mode,
      "workspace",
    );
    assert.equal((await h.send()).permission_mode, "full");
  } finally {
    h.stop();
  }
});

test("a thread's own stored mode wins over the parent's", async () => {
  const h = harness({
    parent: { permission_mode: "workspace" },
    thread: { permission_mode: "full" },
  });
  try {
    assert.equal((await h.send()).permission_mode, "full");
  } finally {
    h.stop();
  }
});

test("an approval callback is sent while the thread reply still streams", async () => {
  const h = harness();
  try {
    h.state.draft = "hello";
    const sent = h.state.send();
    const clicked = h.state.handleButtonClick({
      message: { id: "card" },
      callbackData: "approve",
    });
    assert.equal(h.requests.length, 2);
    h.requests[1].resolve(h.closed());
    await clicked;
    assert.equal(h.state.sending, true);
    h.requests[0].resolve(h.closed());
    await sent;
    assert.equal(
      JSON.parse(h.requests[1].request.body).message[0].callback_data,
      "approve",
    );
  } finally {
    h.stop();
  }
});

test("an undelivered thread callback unlocks its card", async () => {
  const h = harness();
  try {
    h.messages.choices.rememberChosenCallback("approve");
    const clicked = h.state.handleButtonClick({
      message: { id: "card" },
      callbackData: "approve",
    });
    h.requests[0].resolve({ ok: false, status: 500 });
    await clicked;
    assert.equal(
      h.messages.choices.chosenCallbacks.value.includes("approve"),
      false,
    );
  } finally {
    h.stop();
  }
});

test("thread approval results update cards and unfinished calls become unknown", () => {
  const h = harness();
  try {
    const bot = { content: { type: "bot", message: [] } };
    const emit = (payload) => h.state.processPayload(bot, undefined, payload);
    emit({
      type: "plain",
      chain_type: "tool_call",
      data: { id: "call", name: "write" },
    });
    emit({ type: "actionrow", data: { tool_call_id: "call", buttons: [] } });
    const call = bot.content.message[0].tool_calls[0];
    assert.equal(call.phase, "awaiting_approval");
    emit({
      type: "plain",
      chain_type: "approval_result",
      data: JSON.stringify({ tool_call_id: "call", outcome: "approved" }),
    });
    assert.equal(bot.content.message[1].outcome, "approved");
    assert.equal(bot.content.message.length, 2);
    assert.equal(call.phase, undefined);
    emit({ type: "end" });
    assert.equal(call.phase, "unknown");
  } finally {
    h.stop();
  }
});
