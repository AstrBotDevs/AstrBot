// Author: elecvoid243, 2026-07-18
// Spec: docs/superpowers/specs/2026-07-18-codemirror-file-editor-design.md §4
// Extension -> CodeMirror language key map + lazy language-pack loaders.
// Every loader is a dynamic import so no language pack enters the initial
// bundle; resolved LanguageSupport instances are cached per key. Unmapped
// extensions return null -> the editor mounts as plain text (e.g. .gitignore).

import {
  LanguageSupport,
  StreamLanguage,
} from "@codemirror/language";

export type CmLanguageKey =
  | "python"
  | "javascript"
  | "jsx"
  | "typescript"
  | "tsx"
  | "json"
  | "yaml"
  | "shell"
  | "css"
  | "html"
  | "xml"
  | "markdown"
  | "sql"
  | "rust"
  | "go"
  | "cpp"
  | "diff";

const EXT_TO_KEY: Record<string, CmLanguageKey> = {
  ".py": "python",
  ".js": "javascript",
  ".mjs": "javascript",
  ".cjs": "javascript",
  ".jsx": "jsx",
  ".ts": "typescript",
  ".tsx": "tsx",
  ".json": "json",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".sh": "shell",
  ".bash": "shell",
  ".zsh": "shell",
  ".css": "css",
  ".html": "html",
  ".htm": "html",
  // Approximation: template highlights well; <script> coloring is coarse.
  ".vue": "html",
  ".xml": "xml",
  ".svg": "xml",
  ".md": "markdown",
  ".sql": "sql",
  ".rs": "rust",
  ".go": "go",
  // lang-cpp also covers plain C.
  ".c": "cpp",
  ".h": "cpp",
  ".cpp": "cpp",
  ".cc": "cpp",
  ".cxx": "cpp",
  ".hpp": "cpp",
  ".c++": "cpp",
  ".diff": "diff",
  ".patch": "diff",
};

/**
 * Resolve a file path to a CM language key (extension-only, case-insensitive).
 * Returns null for unmapped extensions -> caller edits as plain text.
 */
export function languageKeyForPath(filePath: string): CmLanguageKey | null {
  const m = String(filePath || "").match(/\.([\w+]+)$/i);
  if (!m) return null;
  return EXT_TO_KEY["." + m[1].toLowerCase()] ?? null;
}

const loaders: Record<CmLanguageKey, () => Promise<LanguageSupport>> = {
  python: async () => (await import("@codemirror/lang-python")).python(),
  javascript: async () =>
    (await import("@codemirror/lang-javascript")).javascript(),
  jsx: async () =>
    (await import("@codemirror/lang-javascript")).javascript({ jsx: true }),
  typescript: async () =>
    (await import("@codemirror/lang-javascript")).javascript({
      typescript: true,
    }),
  tsx: async () =>
    (await import("@codemirror/lang-javascript")).javascript({
      jsx: true,
      typescript: true,
    }),
  json: async () => (await import("@codemirror/lang-json")).json(),
  yaml: async () => (await import("@codemirror/lang-yaml")).yaml(),
  shell: async () =>
    new LanguageSupport(
      StreamLanguage.define(
        (await import("@codemirror/legacy-modes/mode/shell")).shell,
      ),
    ),
  css: async () => (await import("@codemirror/lang-css")).css(),
  html: async () => (await import("@codemirror/lang-html")).html(),
  xml: async () => (await import("@codemirror/lang-xml")).xml(),
  markdown: async () => (await import("@codemirror/lang-markdown")).markdown(),
  sql: async () => (await import("@codemirror/lang-sql")).sql(),
  rust: async () => (await import("@codemirror/lang-rust")).rust(),
  go: async () => (await import("@codemirror/lang-go")).go(),
  cpp: async () => (await import("@codemirror/lang-cpp")).cpp(),
  diff: async () =>
    new LanguageSupport(
      StreamLanguage.define(
        (await import("@codemirror/legacy-modes/mode/diff")).diff,
      ),
    ),
};

const cache = new Map<CmLanguageKey, Promise<LanguageSupport>>();

/**
 * Lazily import + instantiate the language pack for a key. The promise is
 * cached per key; a rejected load is evicted so a later attempt can retry
 * (the caller falls back to plain text for the current session on failure).
 */
export function loadLanguage(key: CmLanguageKey): Promise<LanguageSupport> {
  const hit = cache.get(key);
  if (hit) return hit;
  const p = loaders[key]();
  cache.set(key, p);
  p.catch(() => cache.delete(key));
  return p;
}
