import {
  createCssVariablesTheme,
  createHighlighterCore,
  getTokenStyleObject,
  stringifyTokenStyle,
} from 'shiki/core';
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript';
import { createOnigurumaEngine } from 'shiki/engine/oniguruma';

export {
  createCssVariablesTheme,
  createJavaScriptRegexEngine,
  createOnigurumaEngine,
  getTokenStyleObject,
  stringifyTokenStyle,
};

type LanguageModule = { default: unknown };
type BundledLanguageLoader = () => Promise<LanguageModule>;
type ThemeModule = { default: { name?: string } };
type ThemeLoader = () => Promise<ThemeModule>;

const LIMITED_SHIKI_LANGUAGE_LOADERS = {
  abap: () => import('shiki/langs/abap.mjs'),
  ada: () => import('shiki/langs/ada.mjs'),
  asm: () => import('shiki/langs/asm.mjs'),
  bash: () => import('shiki/langs/bash.mjs'),
  c: () => import('shiki/langs/c.mjs'),
  cmake: () => import('shiki/langs/cmake.mjs'),
  cobol: () => import('shiki/langs/cobol.mjs'),
  'common-lisp': () => import('shiki/langs/common-lisp.mjs'),
  cpp: () => import('shiki/langs/cpp.mjs'),
  csharp: () => import('shiki/langs/csharp.mjs'),
  css: () => import('shiki/langs/css.mjs'),
  d: () => import('shiki/langs/d.mjs'),
  dart: () => import('shiki/langs/dart.mjs'),
  diff: () => import('shiki/langs/diff.mjs'),
  dockerfile: () => import('shiki/langs/dockerfile.mjs'),
  dotenv: () => import('shiki/langs/dotenv.mjs'),
  'fortran-fixed-form': () => import('shiki/langs/fortran-fixed-form.mjs'),
  'fortran-free-form': () => import('shiki/langs/fortran-free-form.mjs'),
  go: () => import('shiki/langs/go.mjs'),
  graphql: () => import('shiki/langs/graphql.mjs'),
  haskell: () => import('shiki/langs/haskell.mjs'),
  hcl: () => import('shiki/langs/hcl.mjs'),
  html: () => import('shiki/langs/html.mjs'),
  http: () => import('shiki/langs/http.mjs'),
  ini: () => import('shiki/langs/ini.mjs'),
  java: () => import('shiki/langs/java.mjs'),
  javascript: () => import('shiki/langs/javascript.mjs'),
  json: () => import('shiki/langs/json.mjs'),
  json5: () => import('shiki/langs/json5.mjs'),
  jsonc: () => import('shiki/langs/jsonc.mjs'),
  jsx: () => import('shiki/langs/jsx.mjs'),
  julia: () => import('shiki/langs/julia.mjs'),
  kotlin: () => import('shiki/langs/kotlin.mjs'),
  lisp: () => import('shiki/langs/lisp.mjs'),
  lua: () => import('shiki/langs/lua.mjs'),
  makefile: () => import('shiki/langs/makefile.mjs'),
  markdown: () => import('shiki/langs/markdown.mjs'),
  matlab: () => import('shiki/langs/matlab.mjs'),
  nginx: () => import('shiki/langs/nginx.mjs'),
  'objective-c': () => import('shiki/langs/objective-c.mjs'),
  ocaml: () => import('shiki/langs/ocaml.mjs'),
  pascal: () => import('shiki/langs/pascal.mjs'),
  perl: () => import('shiki/langs/perl.mjs'),
  php: () => import('shiki/langs/php.mjs'),
  plsql: () => import('shiki/langs/plsql.mjs'),
  powershell: () => import('shiki/langs/powershell.mjs'),
  prisma: () => import('shiki/langs/prisma.mjs'),
  prolog: () => import('shiki/langs/prolog.mjs'),
  properties: () => import('shiki/langs/properties.mjs'),
  proto: () => import('shiki/langs/proto.mjs'),
  python: () => import('shiki/langs/python.mjs'),
  r: () => import('shiki/langs/r.mjs'),
  ruby: () => import('shiki/langs/ruby.mjs'),
  rust: () => import('shiki/langs/rust.mjs'),
  sas: () => import('shiki/langs/sas.mjs'),
  scala: () => import('shiki/langs/scala.mjs'),
  scss: () => import('shiki/langs/scss.mjs'),
  sql: () => import('shiki/langs/sql.mjs'),
  'ssh-config': () => import('shiki/langs/ssh-config.mjs'),
  swift: () => import('shiki/langs/swift.mjs'),
  terraform: () => import('shiki/langs/terraform.mjs'),
  toml: () => import('shiki/langs/toml.mjs'),
  tsx: () => import('shiki/langs/tsx.mjs'),
  typescript: () => import('shiki/langs/typescript.mjs'),
  vb: () => import('shiki/langs/vb.mjs'),
  vhdl: () => import('shiki/langs/vhdl.mjs'),
  vue: () => import('shiki/langs/vue.mjs'),
  xml: () => import('shiki/langs/xml.mjs'),
  yaml: () => import('shiki/langs/yaml.mjs'),
  zig: () => import('shiki/langs/zig.mjs'),
} as const satisfies Record<string, BundledLanguageLoader>;

const THEME_LOADERS = {
  'github-dark': () => import('shiki/themes/github-dark.mjs'),
  'github-light': () => import('shiki/themes/github-light.mjs'),
  'vitesse-dark': () => import('shiki/themes/vitesse-dark.mjs'),
  'vitesse-light': () => import('shiki/themes/vitesse-light.mjs'),
} as const satisfies Record<string, ThemeLoader>;

const BUILT_IN_LANGUAGES = ['text', 'plaintext', 'plain', 'ansi'] as const;

export const LIMITED_SHIKI_LANGUAGE_ALIASES: Record<string, string> = {
  assembly: 'asm',
  bat: 'powershell',
  'c#': 'csharp',
  'c++': 'cpp',
  caml: 'ocaml',
  cc: 'cpp',
  cjs: 'javascript',
  cmd: 'powershell',
  console: 'bash',
  cs: 'csharp',
  cts: 'typescript',
  cxx: 'cpp',
  delphi: 'pascal',
  docker: 'dockerfile',
  env: 'dotenv',
  f: 'fortran-free-form',
  f77: 'fortran-fixed-form',
  f90: 'fortran-free-form',
  f95: 'fortran-free-form',
  for: 'fortran-free-form',
  fortran: 'fortran-free-form',
  golang: 'go',
  gql: 'graphql',
  h: 'c',
  'h++': 'cpp',
  hh: 'cpp',
  hpp: 'cpp',
  hs: 'haskell',
  htm: 'html',
  hxx: 'cpp',
  js: 'javascript',
  jsonl: 'json',
  kt: 'kotlin',
  kts: 'kotlin',
  make: 'makefile',
  md: 'markdown',
  mjs: 'javascript',
  mts: 'typescript',
  nasm: 'asm',
  objc: 'objective-c',
  objectivec: 'objective-c',
  pas: 'pascal',
  plain: 'text',
  plaintext: 'text',
  'pl/sql': 'plsql',
  proto3: 'proto',
  protobuf: 'proto',
  ps: 'powershell',
  ps1: 'powershell',
  pwsh: 'powershell',
  py: 'python',
  rb: 'ruby',
  rs: 'rust',
  sh: 'bash',
  shell: 'bash',
  shellscript: 'bash',
  svg: 'xml',
  't-sql': 'sql',
  text: 'text',
  tf: 'terraform',
  tfvars: 'terraform',
  'transact-sql': 'sql',
  ts: 'typescript',
  tsql: 'sql',
  txt: 'text',
  vbnet: 'vb',
  vbs: 'vb',
  vbscript: 'vb',
  'visual-basic': 'vb',
  visualbasic: 'vb',
  xhtml: 'html',
  yml: 'yaml',
  zsh: 'bash',
};

export const bundledLanguages: Record<string, BundledLanguageLoader> = {
  ...LIMITED_SHIKI_LANGUAGE_LOADERS,
};

for (const [alias, canonical] of Object.entries(
  LIMITED_SHIKI_LANGUAGE_ALIASES,
)) {
  const loader = bundledLanguages[canonical];
  if (loader) {
    bundledLanguages[alias] ??= loader;
  }
}

export const LIMITED_SHIKI_SUPPORTED_LANGUAGES = new Set<string>([
  ...BUILT_IN_LANGUAGES,
  ...Object.keys(bundledLanguages),
]);

const CANONICAL_LANGUAGE_IDS = Object.keys(LIMITED_SHIKI_LANGUAGE_LOADERS);

export function isFenceLanguageSettled(
  node:
    | {
        language?: string;
        code?: string;
        loading?: boolean;
      }
    | null
    | undefined,
): boolean {
  if (!node?.loading) return true;
  const language = String(node.language || '')
    .trim()
    .split(/\s+/, 1)[0]
    .split(':', 1)[0]
    .toLowerCase();
  if (!language) return true;
  if (String(node.code || '').length > 0) return true;
  const canonical = normalizeLimitedShikiLanguage(language);
  return !CANONICAL_LANGUAGE_IDS.some(
    (id) =>
      id !== language &&
      id !== canonical &&
      (id.startsWith(language) || id.startsWith(canonical)),
  );
}

type ResolvedTheme = Awaited<ReturnType<ThemeLoader>>['default'];
type ThemeReference =
  keyof typeof THEME_LOADERS | ResolvedTheme | string | null | undefined;

type Highlighter = Awaited<ReturnType<typeof createHighlighterCore>>;
type NormalizableCodeOptions = { lang?: unknown; [key: string]: unknown };
type CreateHighlighterOptions = Omit<
  Parameters<typeof createHighlighterCore>[0],
  'themes' | 'langs'
> & {
  themes?: ThemeReference[];
  langs?: unknown[];
};

function getThemeName(theme: ResolvedTheme | null) {
  return theme?.name;
}

async function resolveTheme(
  theme: ThemeReference,
): Promise<ResolvedTheme | null> {
  if (!theme) return null;
  if (typeof theme !== 'string') return theme;
  const loader = THEME_LOADERS[theme as keyof typeof THEME_LOADERS];
  if (!loader) return null;
  return (await loader()).default;
}

async function uniqueThemes(
  themes: ThemeReference[],
): Promise<ResolvedTheme[]> {
  const seen = new Set<string>();
  const result: ResolvedTheme[] = [];

  for (const theme of themes) {
    const resolved = await resolveTheme(theme);
    const name = getThemeName(resolved);
    if (!resolved || !name || seen.has(name)) continue;
    seen.add(name);
    result.push(resolved);
  }

  return result;
}

export function normalizeLimitedShikiLanguage(language: unknown): string {
  const normalized = String(language || 'text')
    .trim()
    .split(/\s+/, 1)[0]
    .split(':', 1)[0]
    .toLowerCase();

  if (!normalized) return 'text';
  if (normalized in LIMITED_SHIKI_LANGUAGE_ALIASES) {
    return LIMITED_SHIKI_LANGUAGE_ALIASES[normalized];
  }

  return LIMITED_SHIKI_SUPPORTED_LANGUAGES.has(normalized)
    ? normalized
    : 'text';
}

function normalizeCodeOptions<T extends NormalizableCodeOptions>(
  options: T,
): T {
  return {
    ...options,
    lang: normalizeLimitedShikiLanguage(options.lang),
  };
}

function isBuiltInLanguage(language: string) {
  return (BUILT_IN_LANGUAGES as readonly string[]).includes(language);
}

async function loadLangIntoHighlighter(
  highlighter: Highlighter,
  language: unknown,
) {
  const normalized = normalizeLimitedShikiLanguage(language);
  if (isBuiltInLanguage(normalized)) return;
  if (highlighter.getLoadedLanguages().includes(normalized)) return;
  const loader = bundledLanguages[normalized];
  if (!loader) return;
  const loaded = await loader();
  highlighter.loadLanguageSync(loaded.default as never);
}

function wrapLimitedHighlighter(highlighter: Highlighter) {
  const codeToHtml = highlighter.codeToHtml.bind(highlighter);
  const codeToTokens = highlighter.codeToTokens.bind(highlighter);
  const codeToHast = highlighter.codeToHast.bind(highlighter);
  const getLanguage = highlighter.getLanguage.bind(highlighter);
  const getLoadedLanguages = highlighter.getLoadedLanguages.bind(highlighter);
  const loadThemeSync = highlighter.loadThemeSync?.bind(highlighter);
  const loadTheme = highlighter.loadTheme?.bind(highlighter);

  return {
    ...highlighter,
    codeToHast(code: string, options: NormalizableCodeOptions) {
      return codeToHast(
        code,
        normalizeCodeOptions(options) as unknown as Parameters<
          typeof codeToHast
        >[1],
      );
    },
    codeToHtml(code: string, options: NormalizableCodeOptions) {
      return codeToHtml(
        code,
        normalizeCodeOptions(options) as unknown as Parameters<
          typeof codeToHtml
        >[1],
      );
    },
    codeToTokens(code: string, options: NormalizableCodeOptions) {
      return codeToTokens(
        code,
        normalizeCodeOptions(options) as unknown as Parameters<
          typeof codeToTokens
        >[1],
      );
    },
    ensureLanguage(language: unknown) {
      return loadLangIntoHighlighter(highlighter, language);
    },
    getLanguage(language: unknown) {
      return getLanguage(normalizeLimitedShikiLanguage(language));
    },
    getLoadedLanguages() {
      return [...new Set([...getLoadedLanguages(), ...BUILT_IN_LANGUAGES])];
    },
    async loadTheme(...themes: ThemeReference[][]) {
      const resolved = await uniqueThemes(themes.flat());
      if (resolved.length && loadTheme) {
        await loadTheme(...resolved);
      }
    },
    loadThemeSync(...themes: ThemeReference[][]) {
      const resolved = themes
        .flat()
        .filter((theme) => theme && typeof theme !== 'string');
      if (resolved.length && loadThemeSync) {
        loadThemeSync(...(resolved as ResolvedTheme[]));
      }
    },
  };
}

export async function createHighlighter(
  options: Partial<CreateHighlighterOptions> = {},
) {
  const themes = await uniqueThemes(
    Array.isArray(options.themes) ? options.themes : [],
  );

  const highlighter = await createHighlighterCore({
    ...options,
    engine: options.engine || createJavaScriptRegexEngine(),
    langs: [],
    themes,
  });

  const wrapped = wrapLimitedHighlighter(highlighter);
  const requestedLangs = Array.isArray(options.langs) ? options.langs : [];
  for (const language of requestedLangs) {
    if (typeof language === 'string') {
      await loadLangIntoHighlighter(highlighter, language);
      continue;
    }
    if (language) {
      highlighter.loadLanguageSync(language as never);
    }
  }

  return wrapped;
}

let limitedCodeToHtmlHighlighter:
  ReturnType<typeof createHighlighter> | undefined;

export async function codeToHtml(
  code: string,
  options: NormalizableCodeOptions = {},
) {
  limitedCodeToHtmlHighlighter ??= createHighlighter({
    themes: ['github-light', 'github-dark'],
  });
  const highlighter = await limitedCodeToHtmlHighlighter;
  await highlighter.ensureLanguage(options.lang);
  return highlighter.codeToHtml(code, options);
}
