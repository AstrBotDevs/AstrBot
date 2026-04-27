export const DRAG_MIME_SESSION_IDS = "application/x-astrbot-session-ids";

export function configureSessionDrag(event, sessionIds) {
  event.dataTransfer?.setData(
    DRAG_MIME_SESSION_IDS,
    JSON.stringify(sessionIds),
  );
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
  }
}

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

export function toggleExpandedProjectIds(currentProjectIds, projectId) {
  return currentProjectIds.includes(projectId)
    ? currentProjectIds.filter((id) => id !== projectId)
    : [...currentProjectIds, projectId];
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
