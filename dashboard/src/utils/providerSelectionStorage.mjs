export const SELECTED_PROVIDER_KEY = "selectedProvider";
export const SELECTED_PROVIDER_MODEL_KEY = "selectedProviderModel";
export const SESSION_PROVIDER_STORAGE_PREFIX = "chat.sessionProvider.";

/**
 * Remove the persisted chat provider/model selection (global and per-session).
 *
 * @param {Storage} [storage] An optional storage implementation.
 * @param {string} [sessionId] Limit the per-session cleanup to one session.
 * @returns {void}
 */
export function clearProviderSelectionStorage(
  storage = globalThis.localStorage,
  sessionId,
) {
  if (!storage) return;
  try {
    storage.removeItem(SELECTED_PROVIDER_KEY);
    storage.removeItem(SELECTED_PROVIDER_MODEL_KEY);
    if (sessionId) {
      storage.removeItem(SESSION_PROVIDER_STORAGE_PREFIX + sessionId);
      return;
    }
    const sessionKeys = [];
    for (let i = 0; i < storage.length; i += 1) {
      const key = storage.key(i);
      if (key && key.startsWith(SESSION_PROVIDER_STORAGE_PREFIX)) {
        sessionKeys.push(key);
      }
    }
    sessionKeys.forEach((key) => storage.removeItem(key));
  } catch {
    // Selection persistence must not block the UI.
  }
}
