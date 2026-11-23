import assert from "node:assert/strict";
import { test } from "vitest";
import { CHAT_PREFERENCES_KEY, chatPreferences } from "../src/utils/chatPreferences.ts";

function storage(initial = {}) {
  const values = new Map(Object.entries({ user: "alice", ...initial }));
  return {
    values,
    get length() {
      return values.size;
    },
    key: (index) => [...values.keys()][index],
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

test("legacy chat settings migrate to one user-scoped record without losing session choices", () => {
  const target = storage({
    chatNavigationInSidebar: "true",
    selectedProvider: "global",
    selectedProviderModel: "default-model",
    "chat.selectedConfigId": "config",
    "chat.transportMode": "websocket",
    "chat.sttProvider": "speech",
    "chat.projectExpandedIds": '["project"]',
    "chat.sessionProvider.one": '{"providerId":"one-provider","modelName":"one-model"}',
    "astrbot.chat.draft.one": "draft",
    "astrbot.chat.draft.new": "new draft",
    "chat.sessionProvider.broken": "bad json",
  });
  const prefs = chatPreferences(undefined, target);
  assert.equal(prefs.global.provider.providerId, "global");
  assert.equal(prefs.global.navigationInSidebar, true);
  assert.equal(prefs.global.configId, "config");
  assert.equal(prefs.global.transportMode, "websocket");
  assert.equal(prefs.global.sttProvider, "speech");
  assert.equal(prefs.global.expandedProjectIds[0], "project");
  assert.equal(prefs.sessions.one.provider.modelName, "one-model");
  assert.equal(prefs.sessions.one.draft, "draft");
  assert.equal(prefs.global.draft, "new draft");
  assert.deepEqual([...target.values.keys()].sort(), [CHAT_PREFERENCES_KEY, "user"].sort());
  assert.equal(chatPreferences(undefined, target).sessions.one.draft, "draft");
});

test("workbench updates preserve models and drafts and isolate users", () => {
  const target = storage();
  chatPreferences((prefs) => {
    prefs.sessions.one = {
      provider: { providerId: "p", modelName: "m" },
      draft: "keep",
    };
  }, target);
  chatPreferences((prefs) => {
    prefs.sessions.one.workbench = {
      tabs: [],
      activeId: "",
      open: false,
      seen: ["closed"],
    };
  }, target);
  target.setItem("user", "bob");
  assert.equal(chatPreferences(undefined, target).sessions.one, undefined);
  chatPreferences((prefs) => {
    prefs.global.transportMode = "sse";
  }, target);
  target.setItem("user", "alice");
  const prefs = chatPreferences(undefined, target);
  assert.equal(prefs.sessions.one.provider.modelName, "m");
  assert.equal(prefs.sessions.one.draft, "keep");
  assert.equal(prefs.sessions.one.workbench.seen[0], "closed");
  assert.equal(prefs.global.transportMode, undefined);
});

test("failed consolidated writes retain old entries for a later migration", () => {
  const target = storage({ "astrbot.chat.draft.one": "keep" });
  target.setItem = () => {
    throw new Error("Quota exceeded");
  };
  assert.equal(chatPreferences(undefined, target).sessions.one.draft, "keep");
  assert.equal(target.getItem("astrbot.chat.draft.one"), "keep");
});

test("malformed or inaccessible storage does not break ChatUI", () => {
  const target = storage({ [CHAT_PREFERENCES_KEY]: "bad json" });
  chatPreferences((prefs) => {
    prefs.global.configId = "new";
  }, target);
  assert.equal(chatPreferences(undefined, target).global.configId, "new");
  assert.doesNotThrow(() =>
    chatPreferences(undefined, {
      getItem() {
        throw new Error("Blocked");
      },
    }),
  );
});

test("migration preserves newer consolidated values and waits for a logged-in user", () => {
  const target = storage({ user: "", "astrbot.chat.draft.one": "old" });
  chatPreferences(undefined, target);
  assert.equal(target.getItem("astrbot.chat.draft.one"), "old");
  target.setItem("user", "alice");
  target.setItem(
    CHAT_PREFERENCES_KEY,
    JSON.stringify({
      version: 1,
      users: { alice: { global: {}, sessions: { one: { draft: "new" } } } },
    }),
  );
  assert.equal(chatPreferences(undefined, target).sessions.one.draft, "new");
  assert.equal(target.getItem("astrbot.chat.draft.one"), null);
});
