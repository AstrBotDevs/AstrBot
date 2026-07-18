import {
  createHighlighter,
  normalizeLimitedShikiLanguage,
} from "./shikiLimitedBundle";

export const SHIKI_THEMES = {
  light: "github-light",
  dark: "github-dark",
};

let highlighterPromise;

function normalizeLanguage(language) {
  return normalizeLimitedShikiLanguage(language);
}

export function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export async function getShikiHighlighter() {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: Object.values(SHIKI_THEMES),
    });
  }

  return highlighterPromise;
}

export async function ensureShikiLanguages() {
  const highlighter = await getShikiHighlighter();

  return highlighter;
}

export function renderShikiCode(highlighter, code, language, colorMode = "auto") {
  const normalizedLanguage = normalizeLanguage(language);
  const options =
    colorMode === "dark"
      ? { lang: normalizedLanguage, theme: SHIKI_THEMES.dark }
      : colorMode === "light"
        ? { lang: normalizedLanguage, theme: SHIKI_THEMES.light }
        : { lang: normalizedLanguage, themes: SHIKI_THEMES };

  try {
    return highlighter.codeToHtml(code, options);
  } catch (err) {
    console.warn(
      `Failed to render code with Shiki language "${normalizedLanguage}". Falling back to plain text.`,
      err,
    );

    const fallbackOptions =
      colorMode === "dark"
        ? { lang: "text", theme: SHIKI_THEMES.dark }
        : colorMode === "light"
          ? { lang: "text", theme: SHIKI_THEMES.light }
          : { lang: "text", themes: SHIKI_THEMES };

    return highlighter.codeToHtml(code, fallbackOptions);
  }
}

export function collectMarkdownFenceLanguages(markdownIt, markdown) {
  if (!markdown) return [];

  return markdownIt
    .parse(markdown, {})
    .filter((token) => token.type === "fence")
    .map((token) => normalizeLanguage(token.info));
}

export function normalizeShikiLanguage(language) {
  return normalizeLanguage(language);
}

// 2026-07-17 workspace file editor: centralized extension→language map.
// Extracted from FileBrowserFilePreview.vue (which mirrored
// ToolResultView.vue) so the read-only preview and the tool-result
// view share one source of truth. (The edit-mode editor moved to
// CodeMirror 6 on 2026-07-18 and maps extensions separately in
// @/utils/codemirrorLanguages.)
const EXT_TO_LANG = {
  ".py": "python",
  ".js": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".ts": "typescript",
  ".tsx": "tsx",
  ".jsx": "jsx",
  ".vue": "vue",
  ".json": "json",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".sh": "bash",
  ".bash": "bash",
  ".zsh": "bash",
  ".css": "css",
  ".html": "html",
  ".htm": "html",
  ".xml": "xml",
  ".svg": "xml",
  ".md": "markdown",
  ".sql": "sql",
  ".java": "java",
  ".ini": "ini",
  ".diff": "diff",
  ".patch": "diff",
  ".ps1": "powershell",
  ".dockerfile": "dockerfile",
  ".txt": "text",
  ".c": "c",
  ".h": "c",
  ".cpp": "cpp",
  ".cc": "cpp",
  ".cxx": "cpp",
  ".hpp": "cpp",
  ".c++": "cpp",
  ".go": "go",
  ".rs": "rust",
  // Verilog / SystemVerilog
  ".v": "verilog",
  ".vh": "verilog",
  ".sv": "system-verilog",
  ".svh": "system-verilog",
  // MATLAB. `.m` is also the Objective-C extension, but
  // objective-c is not in the shiki whitelist, so claiming it
  // here does not collide with anything currently supported.
  ".m": "matlab",
  ".matlab": "matlab",
};

export function detectLanguage(filePath) {
  const m = String(filePath || "").match(/\.([\w]+)$/i);
  if (!m) return "text";
  const key = "." + m[1].toLowerCase();
  return EXT_TO_LANG[key] || "text";
}
