import { chatPreferences } from "./chatPreferences";

export type ChatMessageType = "FriendMessage" | "GroupMessage";

export interface WebchatUmoDetails {
  platformId: string;
  messageType: ChatMessageType;
  username: string;
  sessionKey: string;
  umo: string;
}

function getFromLocalStorage(key: string, fallback: string): string {
  try {
    if (typeof localStorage === "undefined") {
      return fallback;
    }
    const value = localStorage.getItem(key);
    return value == null ? fallback : value;
  } catch {
    return fallback;
  }
}

export function getStoredDashboardUsername(): string {
  return getFromLocalStorage("user", "").trim() || "guest";
}

export function getStoredSelectedChatConfigId(): string {
  return chatPreferences().global.configId?.trim() || "default";
}

export function setStoredSelectedChatConfigId(configId: string): void {
  chatPreferences((preferences) => {
    preferences.global.configId = configId;
  });
}

export function buildWebchatUmoDetails(sessionId: string, isGroup = false): WebchatUmoDetails {
  const platformId = "webchat";
  const username = getStoredDashboardUsername();
  const messageType: ChatMessageType = isGroup ? "GroupMessage" : "FriendMessage";
  const sessionKey = `${platformId}!${username}!${sessionId}`;
  return {
    platformId,
    messageType,
    username,
    sessionKey,
    umo: `${platformId}:${messageType}:${sessionKey}`,
  };
}
