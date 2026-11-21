import assert from "node:assert/strict";
import test from "node:test";
import { webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { effectScope, nextTick, ref, watch } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";
const prefs = loadSource(
  new URL("../src/utils/chatSessionPrefs.mjs", import.meta.url),
);

// Run one top-level statement of Chat.vue's script, picked by `pick`, with
// `context` as its globals (Chat.vue is too large to mount here).
function runChatStatement(pick, context) {
  const source = readFileSync(
    new URL("../src/components/chat/Chat.vue", import.meta.url),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile("chat.ts", source, ts.ScriptTarget.Latest, true);
  const found = ast.statements.filter((node) => pick(node, node.getText(ast)));
  assert.equal(found.length, 1);
  vm.runInNewContext(ts.transpile(found[0].getText(ast)), context);
  return context;
}

// The module runs in its own realm: compare plain copies.
const same = (actual, expected) =>
  assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected);

// ChatUI preferences are stored per logged-in user.
function memoryStorage() {
  const map = new Map([["user", "alice"]]);
  return {
    map,
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => map.set(key, value),
    removeItem: (key) => map.delete(key),
  };
}

const storedSessions = (storage) =>
  JSON.parse(storage.map.get("astrbot.chat.preferences")).users.alice.sessions;

test("options live in the session's ChatUI preferences and empty values are removed", () => {
  const storage = memoryStorage();
  prefs.writeChatSessionPref("s1", "permission_mode", "workspace", storage);
  prefs.writeChatSessionPref("s2", "permission_mode", "full", storage);
  same(prefs.readChatSessionPrefs("s1", storage), {
    permission_mode: "workspace",
  });
  assert.deepEqual(storedSessions(storage).s1, {
    options: { permission_mode: "workspace" },
  });

  prefs.writeChatSessionPref("s1", "permission_mode", "", storage);
  same(prefs.readChatSessionPrefs("s1", storage), {});
  // An option switched off (false) is removed rather than stored.
  prefs.writeChatSessionPref("s1", "flag", true, storage);
  prefs.writeChatSessionPref("s1", "flag", false, storage);
  same(prefs.readChatSessionPrefs("s1", storage), {});
  assert.deepEqual(storedSessions(storage).s1, {});

  prefs.clearChatSessionPrefs("s2", storage);
  same(prefs.readChatSessionPrefs("s2", storage), {});
});

test("a new conversation has no options and nothing is written for it", () => {
  const storage = memoryStorage();
  prefs.writeChatSessionPref("", "permission_mode", "workspace", storage);
  assert.equal(storage.map.size, 1);
  same(prefs.readChatSessionPrefs("", storage), {});
});

test("corrupted or unavailable storage falls back to no options", () => {
  const storage = memoryStorage();
  for (const raw of ["not json", "[1]", "null", "3"]) {
    storage.map.set("astrbot.chat.preferences", raw);
    same(prefs.readChatSessionPrefs("s1", storage), {});
  }
  const broken = {
    getItem() {
      throw new Error("blocked");
    },
    setItem() {
      throw new Error("blocked");
    },
    removeItem() {
      throw new Error("blocked");
    },
  };
  same(prefs.readChatSessionPrefs("s1", broken), {});
  prefs.writeChatSessionPref("s1", "permission_mode", "workspace", broken);
  prefs.clearChatSessionPrefs("s1", broken);
});

function loadSessions(storage, chatApi) {
  return loadSource(
    new URL("../src/composables/useSessions.ts", import.meta.url),
    {
      "vue-router": { useRouter: () => ({ push() {} }) },
      "@/utils/chatSessionPrefs.mjs": {
        clearChatSessionPrefs: (id) => prefs.clearChatSessionPrefs(id, storage),
      },
      "@/api/v1": {
        chatApi: {
          listSessions: async () => ({
            data: {
              status: "ok",
              data: { sessions: [], total: 0, page_size: 30 },
            },
          }),
          ...chatApi,
        },
        configRouteApi: {},
      },
      "@/utils/chatConfigBinding": {},
    },
    { localStorage: storage, console: { error() {} } },
  ).useSessions();
}

test("deleting sessions forgets only their options", async () => {
  const storage = memoryStorage();
  for (const id of ["gone", "keep", "busy"])
    prefs.writeChatSessionPref(id, "permission_mode", "workspace", storage);
  const sessions = loadSessions(storage, {
    deleteSession: async () => ({}),
    batchDeleteSessions: async () => ({
      data: {
        status: "ok",
        data: {
          deleted_count: 1,
          failed_count: 1,
          failed_items: [{ session_id: "busy", reason: "running" }],
        },
      },
    }),
  });
  await sessions.deleteSession("gone");
  await sessions.batchDeleteSessions(["keep", "busy"]);
  same(prefs.readChatSessionPrefs("gone", storage), {});
  same(prefs.readChatSessionPrefs("keep", storage), {});
  same(prefs.readChatSessionPrefs("busy", storage), {
    permission_mode: "workspace",
  });
});

test("a refused delete keeps the conversation and its options", async () => {
  const storage = memoryStorage();
  prefs.writeChatSessionPref("kept", "permission_mode", "workspace", storage);
  const sessions = loadSessions(storage, {
    deleteSession: async () => ({
      data: { status: "error", message: "running" },
    }),
  });
  sessions.currSessionId.value = "kept";
  await sessions.deleteSession("kept");
  same(prefs.readChatSessionPrefs("kept", storage), {
    permission_mode: "workspace",
  });
  assert.equal(sessions.currSessionId.value, "kept");
});

test("batch-deleting the current conversation leaves it", async () => {
  const storage = memoryStorage();
  prefs.writeChatSessionPref("current", "permission_mode", "workspace", storage);
  const sessions = loadSessions(storage, {
    batchDeleteSessions: async () => ({
      data: {
        status: "ok",
        data: { deleted_count: 1, failed_count: 0, failed_items: [] },
      },
    }),
  });
  sessions.currSessionId.value = "current";
  const result = await sessions.batchDeleteSessions(["current"]);
  assert.equal(result.currentSessionDeleted, true);
  // An empty current session makes Chat.vue reset the active options (see
  // "deleteSession resets the permission mode to its default").
  assert.equal(sessions.currSessionId.value, "");
  same(prefs.readChatSessionPrefs("current", storage), {});
});

test("a thread sends the options of the conversation it belongs to", async () => {
  const storage = memoryStorage();
  prefs.writeChatSessionPref("parent", "permission_mode", "workspace", storage);
  const requests = [];
  const component = loadSource(
    new URL("../src/components/chat/ThreadPanel.vue", import.meta.url),
    {
      "@/utils/chatSessionPrefs.mjs": {
        readChatSessionPrefs: (id) => prefs.readChatSessionPrefs(id, storage),
      },
      "@/composables/useActionRowChoices": {},
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
      "@/composables/useMessages": {
        buildChatRequestFlags: () => ({}),
        normalizeMessageParts: () => [],
        extractReasoningText: () => "",
      },
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
  try {
    await new Promise((resolve) => setImmediate(resolve));
    h.state.draft = "hello";
    void h.state.send();
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(JSON.parse(requests[0].request.body).permission_mode, "workspace");
  } finally {
    h.stop();
  }
});

for (const action of ["newChat", "deleteSession"]) {
  test(`${action} resets the permission mode to its default`, async () => {
    const storage = memoryStorage();
    const sessions = loadSource(
      new URL("../src/composables/useSessions.ts", import.meta.url),
      {
        "vue-router": { useRouter: () => ({ push() {} }) },
        "@/utils/chatSessionPrefs.mjs": {
          clearChatSessionPrefs: (id) =>
            prefs.clearChatSessionPrefs(id, storage),
        },
        "@/api/v1": {
          chatApi: {
            deleteSession: async () => ({}),
            listSessions: async () => ({
              data: {
                status: "ok",
                data: { sessions: [], total: 0, page_size: 30 },
              },
            }),
          },
          configRouteApi: {},
        },
        "@/utils/chatConfigBinding": {},
      },
      { localStorage: storage },
    ).useSessions();
    const permissionMode = ref("full");
    sessions.currSessionId.value = "old";
    const scope = effectScope();
    scope.run(() =>
      runChatStatement(
        (node, text) =>
          ts.isExpressionStatement(node) &&
          text.startsWith("watch(currSessionId,") &&
          text.includes("permissionMode"),
        { watch, currSessionId: sessions.currSessionId, permissionMode },
      ),
    );
    try {
      await sessions[action](action === "deleteSession" ? "old" : undefined);
      await nextTick();
      assert.equal(permissionMode.value, "ask");
    } finally {
      scope.stop();
    }
  });
}

test("opening a conversation restores its permission mode", async () => {
  const storage = memoryStorage();
  prefs.writeChatSessionPref("stored", "permission_mode", "workspace", storage);
  prefs.writeChatSessionPref("odd", "permission_mode", "root", storage);
  prefs.writeChatSessionPref("noask", "permission_mode", "workspace_no_ask", storage);
  const context = {
    showChatWorkspace() {},
    selectedProjectId: ref(null),
    currSessionId: ref(""),
    replyTarget: ref(null),
    route: { path: "" },
    basePath: () => "/chat",
    router: { push: async () => {} },
    loadedSessions: { stored: true, fresh: true, odd: true, noask: true },
    loadSessionMessages: async () => {},
    permissionMode: ref("full"),
    readChatSessionPrefs: (id) => prefs.readChatSessionPrefs(id, storage),
    readSessionProviderSelection: () => null,
    setProviderSelection() {},
    scrollToBottom() {},
    focusChatInput: async () => {},
  };
  runChatStatement(
    (node) =>
      ts.isFunctionDeclaration(node) && node.name?.text === "selectSession",
    context,
  );
  await context.selectSession("stored", false);
  assert.equal(context.permissionMode.value, "workspace");
  await context.selectSession("fresh", false);
  assert.equal(context.permissionMode.value, "ask");
  context.permissionMode.value = "full";
  // An unknown stored mode falls back to asking.
  await context.selectSession("odd", false);
  assert.equal(context.permissionMode.value, "ask");
  // "Don't ask again" from workspace is kept per conversation too.
  await context.selectSession("noask", false);
  assert.equal(context.permissionMode.value, "workspace_no_ask");
});
