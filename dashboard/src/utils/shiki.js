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
