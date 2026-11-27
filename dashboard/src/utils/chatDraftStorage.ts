import { chatPreferences } from "./chatPreferences";

/** Read the current user's draft for a session or the new-conversation composer. */
export function readChatDraft(sessionId: string, storage?: Storage): string {
  const preferences = chatPreferences(undefined, storage);
  const draft = sessionId
    ? preferences.sessions[sessionId]?.draft
    : preferences.global.draft;
  return typeof draft === "string" ? draft : "";
}

/** Persist or remove a draft without changing other session preferences. */
export function writeChatDraft(
  sessionId: string,
  draft: string,
  storage?: Storage,
): void {
  chatPreferences((preferences) => {
    const scope = sessionId
      ? (preferences.sessions[sessionId] ||= {})
      : preferences.global;
    if (draft) scope.draft = draft;
    else delete scope.draft;
  }, storage);
}
