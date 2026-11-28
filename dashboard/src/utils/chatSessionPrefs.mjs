import { chatPreferences } from "@/utils/chatPreferences";

/**
 * Read the per-conversation ChatUI options of a session.
 *
 * They live in the session's record of the user's ChatUI preferences
 * (`chatPreferences().sessions[id].options`). Keys are the request field
 * names (for example `permission_mode`), so the result can be spread into
 * any chat request (send, regenerate, thread, WebSocket). To add an option,
 * store it with `writeChatSessionPref` and accept the same field on the
 * backend (`resolve_webchat_chat_options`).
 *
 * @param {string} sessionId The session ID; a new conversation has none yet.
 * @param {Storage} [storage] An optional storage implementation.
 * @returns {Record<string, unknown>} The stored options, or an empty object.
 */
export function readChatSessionPrefs(sessionId, storage) {
  if (!sessionId) return {};
  const options = chatPreferences(undefined, storage).sessions[sessionId]
    ?.options;
  return options && typeof options === "object" && !Array.isArray(options)
    ? { ...options }
    : {};
}

/**
 * Store one option for a session; an empty value removes it.
 *
 * @param {string} sessionId The session ID; ignored for a new conversation.
 * @param {string} key The request field name.
 * @param {unknown} value The value, or an empty value to fall back to the default.
 * @param {Storage} [storage] An optional storage implementation.
 * @returns {void}
 */
export function writeChatSessionPref(sessionId, key, value, storage) {
  if (!sessionId) return;
  chatPreferences((preferences) => {
    const session = (preferences.sessions[sessionId] ||= {});
    const options = { ...(session.options || {}) };
    if (
      value === "" ||
      value === null ||
      value === undefined ||
      value === false
    ) {
      delete options[key];
    } else {
      options[key] = value;
    }
    if (Object.keys(options).length) session.options = options;
    else delete session.options;
  }, storage);
}

/**
 * Forget the stored options of a deleted session.
 *
 * @param {string} sessionId The deleted session ID.
 * @param {Storage} [storage] An optional storage implementation.
 * @returns {void}
 */
export function clearChatSessionPrefs(sessionId, storage) {
  if (!sessionId) return;
  chatPreferences((preferences) => {
    delete preferences.sessions[sessionId]?.options;
  }, storage);
}
