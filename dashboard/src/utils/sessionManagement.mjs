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
