export const CHAT_SELECTED_CONFIG_STORAGE_KEY = 'chat.selectedConfigId';

export type ChatMessageType = 'FriendMessage' | 'GroupMessage';

export interface WebchatUmoDetails {
  platformId: string;
  messageType: ChatMessageType;
  username: string;
  sessionKey: string;
  umo: string;
}

export function getStoredDashboardUsername(): string {
  return (localStorage.getItem('user') || '').trim() || 'guest';
}

export function getStoredSelectedChatConfigId(): string {
  return (localStorage.getItem(CHAT_SELECTED_CONFIG_STORAGE_KEY) || '').trim() || 'default';
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

