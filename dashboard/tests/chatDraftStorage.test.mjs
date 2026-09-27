import assert from "node:assert/strict";
import test from "node:test";

import {
  CHAT_DRAFT_STORAGE_PREFIX,
  readChatDraft,
  writeChatDraft,
} from "../src/utils/chatDraftStorage.mjs";

/**
 * Create an in-memory Storage subset for draft tests.
 *
 * @returns {{getItem: Function, setItem: Function, removeItem: Function}} The storage stub.
 */
function createStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

test("stores session and new-conversation drafts independently", () => {
  const storage = createStorage();

  writeChatDraft("", "new conversation", storage);
  writeChatDraft("session-1", "existing session", storage);

  assert.equal(readChatDraft("", storage), "new conversation");
  assert.equal(readChatDraft("session-1", storage), "existing session");
  assert.equal(readChatDraft("session-2", storage), "");
});

test("removes an empty draft instead of retaining stale text", () => {
  const storage = createStorage();
  writeChatDraft("session-1", "draft", storage);

  writeChatDraft("session-1", "", storage);

  assert.equal(readChatDraft("session-1", storage), "");
});

test("uses the stable AstrBot draft namespace", () => {
  assert.equal(CHAT_DRAFT_STORAGE_PREFIX, "astrbot.chat.draft.");
});

test("ignores unavailable storage", () => {
  const storage = {
    getItem() {
      throw new Error("SecurityError");
    },
    setItem() {
      throw new Error("QuotaExceededError");
    },
    removeItem() {
      throw new Error("SecurityError");
    },
  };

  assert.equal(readChatDraft("session-1", storage), "");
  assert.doesNotThrow(() => writeChatDraft("session-1", "draft", storage));
  assert.doesNotThrow(() => writeChatDraft("session-1", "", storage));
});
