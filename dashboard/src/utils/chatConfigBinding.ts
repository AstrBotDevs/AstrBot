export const CHAT_SELECTED_CONFIG_STORAGE_KEY = 'chat.selectedConfigId';

export type ChatMessageType = 'FriendMessage' | 'GroupMessage';

export interface WebchatUmoDetails {
  platformId: string;
  messageType: ChatMessageType;
  username: string;
  sessionKey: string;
  umo: string;
}

function getFromLocalStorage(key: string, fallback: string): string {
  try {
    if (typeof localStorage === 'undefined') {
      return fallback;
    }
    const value = localStorage.getItem(key);
    return value == null ? fallback : value;
  } catch {
    return fallback;
  }
}

function setToLocalStorage(key: string, value: string): void {
  try {
    if (typeof localStorage === 'undefined') {
      return;
    }
    localStorage.setItem(key, value);
  } catch {
    // Ignore storage errors (e.g. private mode / restricted storage).
  }
}

export function getStoredDashboardUsername(): string {
  return getFromLocalStorage('user', '').trim() || 'guest';
}

export function getStoredSelectedChatConfigId(): string {
  const username = getStoredDashboardUsername();
  const userScopedKey = `${CHAT_SELECTED_CONFIG_STORAGE_KEY}:${username}`;
  return getFromLocalStorage(userScopedKey, '').trim()
    || getFromLocalStorage(CHAT_SELECTED_CONFIG_STORAGE_KEY, '').trim()
    || 'default';
}

export function setStoredSelectedChatConfigId(configId: string): void {
  const username = getStoredDashboardUsername();
  setToLocalStorage(`${CHAT_SELECTED_CONFIG_STORAGE_KEY}:${username}`, configId);
}

export function buildWebchatUmoDetails(sessionId: string, isGroup = false): WebchatUmoDetails {
  const platformId = 'webchat';
  const username = getStoredDashboardUsername();
  const messageType: ChatMessageType = isGroup ? 'GroupMessage' : 'FriendMessage';
  const sessionKey = `${platformId}!${username}!${sessionId}`;
  return {
    platformId,
    messageType,
    username,
    sessionKey,
    umo: `${platformId}:${messageType}:${sessionKey}`
  };
}
