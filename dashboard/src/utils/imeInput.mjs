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
    event.timeStamp - lastCompositionEndAt < 100;

  return (
    event.key === "Enter" &&
    (compositionActive ||
      event.isComposing ||
      hasLegacyCompositionKeyCode ||
      isAfterRecentCompositionEnd)
  );
}
