// Some IMEs emit Enter right after compositionend; treat that same-keystroke
// window as composition so selecting a candidate does not send the message.
const RECENT_COMPOSITION_END_THRESHOLD_MS = 100;

/**
 * @param {KeyboardEvent} event
 * @param {boolean} compositionActive
 * @param {number | null} lastCompositionEndAt
 */
export function isComposingEnter(
  event,
  compositionActive,
  lastCompositionEndAt = null,
) {
  const hasLegacyCompositionKeyCode =
    typeof event.keyCode === "number" && event.keyCode === 229;
  const isAfterRecentCompositionEnd =
    typeof event.timeStamp === "number" &&
    typeof lastCompositionEndAt === "number" &&
    event.timeStamp >= lastCompositionEndAt &&
    event.timeStamp - lastCompositionEndAt <
      RECENT_COMPOSITION_END_THRESHOLD_MS;

  return (
    event.key === "Enter" &&
    (compositionActive ||
      event.isComposing ||
      hasLegacyCompositionKeyCode ||
      isAfterRecentCompositionEnd)
  );
}
