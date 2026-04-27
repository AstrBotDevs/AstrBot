export function isComposingEnter(event, compositionActive) {
  return (
    event.key === "Enter" &&
    (compositionActive || event.isComposing || event.keyCode === 229)
  );
}
