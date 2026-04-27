export const DRAG_MIME_SESSION_IDS = "application/x-astrbot-session-ids";
export const DRAG_MIME_SOURCE_PROJECT_ID =
  "application/x-astrbot-source-project-id";

export function toggleSessionSelection(selectedSessionIds, sessionId) {
  return selectedSessionIds.includes(sessionId)
    ? selectedSessionIds.filter((id) => id !== sessionId)
    : [...selectedSessionIds, sessionId];
}

export function getDragSessionIds(sourceSessionId, selectedSessionIds) {
  return selectedSessionIds.includes(sourceSessionId)
    ? [...selectedSessionIds]
    : [sourceSessionId];
}

export function shouldSuppressClickAfterLongPress(suppressNextClick) {
  return {
    suppress: suppressNextClick,
    nextSuppressState: false,
  };
}

export function toggleExpandedProject(currentProjectId, projectId) {
  return currentProjectId === projectId ? null : projectId;
}

export function getProjectDragPayload(
  sessionId,
  sourceProjectId,
  selectedSessionIds = [],
) {
  return {
    sessionIds: getDragSessionIds(sessionId, selectedSessionIds),
    sourceProjectId,
  };
}
