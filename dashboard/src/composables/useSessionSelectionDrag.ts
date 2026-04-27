import { onBeforeUnmount, ref, type Ref } from "vue";
import {
  getDragSessionIds,
  getProjectDragPayload,
  shouldSuppressClickAfterLongPress,
  toggleSessionSelection,
} from "@/utils/sessionManagement.mjs";

export function useSessionSelectionDrag(selectedSessions: Ref<string[]>) {
  const draggingSessionIds = ref<string[]>([]);
  const draggingSourceProjectId = ref<string | null>(null);
  const sessionListDropReady = ref(false);
  const isSessionSelectionMode = ref(false);
  const suppressNextSessionClick = ref(false);
  const sessionLongPressMs = 450;
  let sessionLongPressTimer: number | null = null;

  function isSessionSelected(sessionId: string) {
    return selectedSessions.value.includes(sessionId);
  }

  function clearSessionSelection() {
    selectedSessions.value = [];
    isSessionSelectionMode.value = false;
  }

  function toggleSidebarSessionSelection(sessionId: string) {
    selectedSessions.value = toggleSessionSelection(
      selectedSessions.value,
      sessionId,
    );
    isSessionSelectionMode.value = selectedSessions.value.length > 0;
  }

  function startSessionLongPress(sessionId: string) {
    cancelSessionLongPress();
    sessionLongPressTimer = window.setTimeout(() => {
      isSessionSelectionMode.value = true;
      suppressNextSessionClick.value = true;
      if (!isSessionSelected(sessionId)) {
        selectedSessions.value = [...selectedSessions.value, sessionId];
      }
    }, sessionLongPressMs);
  }

  function cancelSessionLongPress() {
    if (sessionLongPressTimer !== null) {
      window.clearTimeout(sessionLongPressTimer);
      sessionLongPressTimer = null;
    }
  }

  function consumeSuppressedSessionClick() {
    const clickSuppression = shouldSuppressClickAfterLongPress(
      suppressNextSessionClick.value,
    );
    suppressNextSessionClick.value = clickSuppression.nextSuppressState;
    return clickSuppression.suppress;
  }

  function startSessionDragState(sessionId: string) {
    cancelSessionLongPress();
    draggingSessionIds.value = getDragSessionIds(
      sessionId,
      selectedSessions.value,
    );
    draggingSourceProjectId.value = null;
    return draggingSessionIds.value;
  }

  function startProjectSessionDragState(
    sessionId: string,
    sourceProjectId: string,
  ) {
    cancelSessionLongPress();
    const payload = getProjectDragPayload(
      sessionId,
      sourceProjectId,
      selectedSessions.value,
    );
    draggingSessionIds.value = payload.sessionIds;
    draggingSourceProjectId.value = payload.sourceProjectId;
    return payload;
  }

  function finishSessionDrag() {
    draggingSessionIds.value = [];
    draggingSourceProjectId.value = null;
    sessionListDropReady.value = false;
  }

  onBeforeUnmount(cancelSessionLongPress);

  return {
    draggingSessionIds,
    draggingSourceProjectId,
    sessionListDropReady,
    isSessionSelectionMode,
    isSessionSelected,
    clearSessionSelection,
    toggleSidebarSessionSelection,
    startSessionLongPress,
    cancelSessionLongPress,
    consumeSuppressedSessionClick,
    startSessionDragState,
    startProjectSessionDragState,
    finishSessionDrag,
  };
}
