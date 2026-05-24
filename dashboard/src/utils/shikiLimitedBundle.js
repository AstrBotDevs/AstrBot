import { createHighlighterCore } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";
import bash from "shiki/langs/bash.mjs";
import css from "shiki/langs/css.mjs";
import diff from "shiki/langs/diff.mjs";
import dockerfile from "shiki/langs/dockerfile.mjs";
import html from "shiki/langs/html.mjs";
import ini from "shiki/langs/ini.mjs";
import java from "shiki/langs/java.mjs";
import javascript from "shiki/langs/javascript.mjs";
import json from "shiki/langs/json.mjs";
import jsx from "shiki/langs/jsx.mjs";
import markdown from "shiki/langs/markdown.mjs";
import powershell from "shiki/langs/powershell.mjs";
import python from "shiki/langs/python.mjs";
import sql from "shiki/langs/sql.mjs";
import tsx from "shiki/langs/tsx.mjs";
import typescript from "shiki/langs/typescript.mjs";
import vue from "shiki/langs/vue.mjs";
import xml from "shiki/langs/xml.mjs";
import yaml from "shiki/langs/yaml.mjs";
import githubDark from "shiki/themes/github-dark.mjs";
import githubLight from "shiki/themes/github-light.mjs";
import vitesseDark from "shiki/themes/vitesse-dark.mjs";
import vitesseLight from "shiki/themes/vitesse-light.mjs";

export const LIMITED_SHIKI_LANGUAGES = [
  ...bash,
  ...css,
  ...diff,
  ...dockerfile,
  ...html,
  ...ini,
  ...java,
  ...javascript,
  ...json,
  ...jsx,
  ...markdown,
  ...powershell,
  ...python,
  ...sql,
  ...tsx,
  ...typescript,
  ...vue,
  ...xml,
  ...yaml,
];

const THEME_BY_NAME = {
  "github-dark": githubDark,
  "github-light": githubLight,
  "vitesse-dark": vitesseDark,
  "vitesse-light": vitesseLight,
};

const BUILT_IN_LANGUAGES = ["text", "plaintext", "plain"];

export const LIMITED_SHIKI_LANGUAGE_ALIASES = {
  bat: "powershell",
  cjs: "javascript",
  console: "bash",
  cts: "typescript",
  docker: "dockerfile",
  htm: "html",
  js: "javascript",
  md: "markdown",
  mjs: "javascript",
  mts: "typescript",
  plain: "text",
  plaintext: "text",
  ps1: "powershell",
  pwsh: "powershell",
  py: "python",
  shell: "bash",
  shellscript: "bash",
  sh: "bash",
  svg: "xml",
  text: "text",
  ts: "typescript",
  txt: "text",
  xhtml: "html",
  yml: "yaml",
  zsh: "bash",
};

export const LIMITED_SHIKI_SUPPORTED_LANGUAGES = new Set([
  ...BUILT_IN_LANGUAGES,
  ...LIMITED_SHIKI_LANGUAGES.flatMap((language) => [
    language.name,
    ...(language.aliases || []),
  ]),
]);

function getThemeName(theme) {
  return typeof theme === "string" ? theme : theme?.name;
}

function resolveTheme(theme) {
  if (!theme) return null;
  if (typeof theme !== "string") return theme;
  return THEME_BY_NAME[theme] || null;
}

function uniqueThemes(themes) {
  const seen = new Set();
  const result = [];

  for (const theme of themes) {
    const resolved = resolveTheme(theme);
    const name = getThemeName(resolved);
    if (!resolved || !name || seen.has(name)) continue;
    seen.add(name);
    result.push(resolved);
  }

  return result;
}

export function normalizeLimitedShikiLanguage(language) {
  const normalized = String(language || "text")
    .trim()
    .split(/\s+/, 1)[0]
    .toLowerCase();

  if (!normalized) return "text";
  if (normalized in LIMITED_SHIKI_LANGUAGE_ALIASES) {
    return LIMITED_SHIKI_LANGUAGE_ALIASES[normalized];
  }

  return LIMITED_SHIKI_SUPPORTED_LANGUAGES.has(normalized) ? normalized : "text";
}

function normalizeCodeOptions(options) {
  if (!options || typeof options !== "object") return options;
  return {
    ...options,
    lang: normalizeLimitedShikiLanguage(options.lang),
  };
}

function wrapLimitedHighlighter(highlighter) {
  const codeToHtml = highlighter.codeToHtml.bind(highlighter);
  const codeToTokens = highlighter.codeToTokens.bind(highlighter);
  const codeToHast = highlighter.codeToHast.bind(highlighter);
  const getLanguage = highlighter.getLanguage.bind(highlighter);
  const getLoadedLanguages = highlighter.getLoadedLanguages.bind(highlighter);
  const loadThemeSync = highlighter.loadThemeSync?.bind(highlighter);
  const loadTheme = highlighter.loadTheme?.bind(highlighter);

  return {
    ...highlighter,
    codeToHast(code, options) {
      return codeToHast(code, normalizeCodeOptions(options));
    },
    codeToHtml(code, options) {
      return codeToHtml(code, normalizeCodeOptions(options));
    },
    codeToTokens(code, options) {
      return codeToTokens(code, normalizeCodeOptions(options));
    },
    getLanguage(language) {
      return getLanguage(normalizeLimitedShikiLanguage(language));
    },
    getLoadedLanguages() {
      return [...new Set([...getLoadedLanguages(), ...BUILT_IN_LANGUAGES])];
    },
    loadLanguage() {
      return Promise.resolve();
    },
    loadLanguageSync() {},
    async loadTheme(...themes) {
      const resolved = uniqueThemes(themes.flat());
      if (resolved.length && loadTheme) await loadTheme(...resolved);
    },
    loadThemeSync(...themes) {
      const resolved = uniqueThemes(themes.flat());
      if (resolved.length && loadThemeSync) loadThemeSync(...resolved);
    },
  };
}

export async function createHighlighter(options = {}) {
  const themes = uniqueThemes([
    ...(Array.isArray(options.themes) ? options.themes : []),
    ...Object.values(THEME_BY_NAME),
  ]);

  const highlighter = await createHighlighterCore({
    ...options,
    engine: options.engine || createJavaScriptRegexEngine(),
    langs: LIMITED_SHIKI_LANGUAGES,
    themes,
  });

  return wrapLimitedHighlighter(highlighter);
}
