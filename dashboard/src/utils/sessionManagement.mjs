export const DRAG_MIME_SESSION_IDS = "application/x-astrbot-session-ids";

export function configureSessionDrag(event, sessionIds) {
  event.dataTransfer?.setData(
    DRAG_MIME_SESSION_IDS,
    JSON.stringify(sessionIds),
  );
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    if (
      typeof document !== "undefined" &&
      typeof event.dataTransfer.setDragImage === "function"
    ) {
      const dragImage = document.createElement("canvas");
      dragImage.width = 1;
      dragImage.height = 1;
      event.dataTransfer.setDragImage(dragImage, 0, 0);
    }
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

export function moveSessionIdsBefore(
  currentSessionIds,
  movingSessionIds,
  targetSessionId,
) {
  const movingSet = new Set(movingSessionIds);
  const remainingSessionIds = currentSessionIds.filter(
    (id) => !movingSet.has(id),
  );
  const targetIndex = remainingSessionIds.indexOf(targetSessionId);
  if (targetIndex === -1) return currentSessionIds;
  return [
    ...remainingSessionIds.slice(0, targetIndex),
    ...movingSessionIds,
    ...remainingSessionIds.slice(targetIndex),
  ];
}

export function moveSessionIdsAfter(
  currentSessionIds,
  movingSessionIds,
  targetSessionId,
) {
  const movingSet = new Set(movingSessionIds);
  const remainingSessionIds = currentSessionIds.filter(
    (id) => !movingSet.has(id),
  );
  const targetIndex = remainingSessionIds.indexOf(targetSessionId);
  if (targetIndex === -1) return currentSessionIds;
  return [
    ...remainingSessionIds.slice(0, targetIndex + 1),
    ...movingSessionIds,
    ...remainingSessionIds.slice(targetIndex + 1),
  ];
}

export function moveSessionIdsToEnd(currentSessionIds, movingSessionIds) {
  const movingSet = new Set(movingSessionIds);
  return [
    ...currentSessionIds.filter((id) => !movingSet.has(id)),
    ...movingSessionIds,
  ];
}
