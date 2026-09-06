import type { editor } from "monaco-editor";

/**
 * Defines the custom "reactor" Monaco theme:
 * - Transparent background so the reactor canvas shows through
 * - Cherenkov blue accents for UI elements
 * - Industrial precision aesthetic
 */
export function defineReactorMonacoTheme() {
  // Access monaco via the global
  const monaco = (window as any).monaco;
  if (!monaco) return;

  monaco.editor.defineTheme("reactor-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "", foreground: "E4E1E6", background: "00000000" },
      { token: "comment", foreground: "5C6370", fontStyle: "italic" },
      { token: "keyword", foreground: "7DD9CC" },
      { token: "string", foreground: "69F0AE" },
      { token: "number", foreground: "FFD54F" },
      { token: "type", foreground: "A1C9FF" },
      { token: "delimiter", foreground: "8E9099" },
      { token: "variable", foreground: "E4E1E6" },
    ],
    colors: {
      "editor.background": "#00000000",
      "editor.foreground": "#E4E1E6",
      "editor.lineHighlightBackground": "#1A3A5C22",
      "editor.lineHighlightBorder": "#00F2FF18",
      "editor.selectionBackground": "#005FB044",
      "editor.inactiveSelectionBackground": "#005FB022",
      "editorLineNumber.foreground": "#44474F",
      "editorLineNumber.activeForeground": "#00F2FF",
      "editorCursor.foreground": "#00F2FF",
      "editorWhitespace.foreground": "#1A1A22",
      "editorIndentGuide.background": "#1A1A22",
      "editorIndentGuide.activeBackground": "#00F2FF22",
      "editor.wordHighlightBackground": "#005FB018",
      "editorGutter.background": "#00000000",
      "scrollbar.shadow": "#00000000",
      "scrollbarSlider.background": "#1A3A5C44",
      "scrollbarSlider.hoverBackground": "#1A3A5C88",
      "scrollbarSlider.activeBackground": "#00F2FF44",
    },
  } satisfies editor.IStandaloneThemeData);
}

/**
 * Highlight error lines in Monaco editor with Cherenkov red glow
 */
export function setMonacoEditorErrors(
  monaco: any,
  editorInstance: editor.IStandaloneCodeEditor | null,
  errors: Array<{ line: number; message: string }>,
) {
  if (!editorInstance || !monaco) return;

  const model = editorInstance.getModel();
  if (!model) return;

  const markers: editor.IMarkerData[] = errors.map((err) => ({
    severity: monaco.MarkerSeverity.Error,
    message: err.message,
    startLineNumber: err.line,
    startColumn: 1,
    endLineNumber: err.line,
    endColumn: model.getLineMaxColumn(err.line),
  }));

  monaco.editor.setModelMarkers(model, "reactor-errors", markers);
}
