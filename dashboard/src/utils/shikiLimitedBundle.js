import { createHighlighterCore } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";
import { bundledLanguages, bundledLanguagesInfo } from "shiki/langs";
import githubDark from "shiki/themes/github-dark.mjs";
import githubLight from "shiki/themes/github-light.mjs";

const supportedLanguages = new Set([
  "c", "cpp", "csharp", "css", "dart", "diff", "docker", "glsl", "go",
  "graphql", "haml", "html", "html-derivative", "ini", "java", "javascript",
  "json", "jsx", "kotlin", "lua", "markdown", "php", "powershell", "python",
  "r", "regexp", "ruby", "rust", "scala", "shellscript", "sql", "swift",
  "tsx", "typescript", "vue", "xml", "yaml",
]);

// These grammars are bundled with their parent language.
const embeddedLanguages = {
  "cpp-macro": "cpp",
  "markdown-vue": "vue",
  "vue-directives": "vue",
  "vue-interpolations": "vue",
  "vue-sfc-style-variable-injection": "vue",
};

const BUILT_IN_LANGUAGES = ["text", "plaintext", "plain"];

export const LIMITED_SHIKI_LANGUAGE_ALIASES = {
  bat: "powershell",
  "c++": "cpp",
  cc: "cpp",
  cjs: "javascript",
  cxx: "cpp",
  console: "bash",
  cts: "typescript",
  cs: "csharp",
  docker: "dockerfile",
  golang: "go",
  h: "c",
  "h++": "cpp",
  hh: "cpp",
  hpp: "cpp",
  htm: "html",
  js: "javascript",
  kt: "kotlin",
  kts: "kotlin",
  md: "markdown",
  mjs: "javascript",
  mts: "typescript",
  plain: "text",
  plaintext: "text",
  ps1: "powershell",
  pwsh: "powershell",
  py: "python",
  rs: "rust",
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
  ...Object.keys(embeddedLanguages),
  ...bundledLanguagesInfo
    .filter(({ id }) => supportedLanguages.has(id))
    .flatMap(({ id, aliases = [] }) => [id, ...aliases]),
]);

export function normalizeLimitedShikiLanguage(language) {
  const normalized = String(language || "text")
    .trim()
    .split(/\s+/, 1)[0]
    .split(":", 1)[0]
    .toLowerCase();

  if (!normalized) return "text";
  if (normalized in LIMITED_SHIKI_LANGUAGE_ALIASES) {
    return LIMITED_SHIKI_LANGUAGE_ALIASES[normalized];
  }

  return LIMITED_SHIKI_SUPPORTED_LANGUAGES.has(normalized) ? normalized : "text";
}

export function createHighlighter() {
  return createHighlighterCore({
    engine: createJavaScriptRegexEngine(),
    themes: [githubLight, githubDark],
    langs: [],
  });
}

export async function loadShikiLanguages(highlighter, languages) {
  const loaded = new Set(highlighter.getLoadedLanguages());
  const grammars = [];
  let pending = new Set(languages.map(normalizeLimitedShikiLanguage));
  while (pending.size) {
    const loaders = new Set(
      [...pending]
        .filter((language) => language !== "text" && !loaded.has(language))
        .map((language) => bundledLanguages[embeddedLanguages[language] ?? language]),
    );
    pending = new Set();
    const modules = await Promise.all([...loaders].map((load) => load()));
    for (const { default: registrations } of modules) {
      for (const grammar of registrations) {
        loaded.add(grammar.name);
        for (const alias of grammar.aliases ?? []) loaded.add(alias);
        // Keep the embedded highlighting that the preloaded bundle provided.
        for (const embedded of grammar.embeddedLangsLazy ?? []) {
          if (supportedLanguages.has(embedded)) pending.add(embedded);
        }
      }
      grammars.push(...registrations);
    }
  }
  if (grammars.length) highlighter.loadLanguageSync(grammars);
}
