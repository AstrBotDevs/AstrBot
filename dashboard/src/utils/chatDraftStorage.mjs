export const CHAT_DRAFT_STORAGE_PREFIX = "astrbot.chat.draft.";

/**
 * Read the text draft for a session or the new-conversation composer.
 *
 * @param {string} sessionId The active session ID, or an empty string for a new conversation.
 * @param {Storage} [storage] An optional storage implementation.
 * @returns {string} The stored draft, or an empty string when unavailable.
 */
export function readChatDraft(sessionId, storage) {
  try {
    const target = storage ?? globalThis.localStorage;
    return (
      target?.getItem(`${CHAT_DRAFT_STORAGE_PREFIX}${sessionId || "new"}`) || ""
    );
  } catch {
    return "";
  }
}

/**
 * Persist or remove the text draft for a session or new conversation.
 *
 * @param {string} sessionId The active session ID, or an empty string for a new conversation.
 * @param {string} draft The draft text to persist.
 * @param {Storage} [storage] An optional storage implementation.
 * @returns {void}
 */
export function writeChatDraft(sessionId, draft, storage) {
  try {
    const target = storage ?? globalThis.localStorage;
    const key = `${CHAT_DRAFT_STORAGE_PREFIX}${sessionId || "new"}`;
    if (draft) {
      target?.setItem(key, draft);
    } else {
      target?.removeItem(key);
    }
  } catch {
    // Draft persistence must not block composing or sending a message.
  }
}
