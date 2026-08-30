import type MarkdownIt from 'markdown-it';

import {
  createHighlighter,
  normalizeLimitedShikiLanguage,
} from './shikiLimitedBundle';

export const SHIKI_THEMES = {
  light: 'github-light',
  dark: 'github-dark',
} as const;

type ShikiHighlighter = Awaited<ReturnType<typeof createHighlighter>>;
type ColorMode = 'auto' | 'dark' | 'light';
type MarkdownItInstance = ReturnType<typeof MarkdownIt>;

let highlighterPromise: Promise<ShikiHighlighter> | undefined;

function normalizeLanguage(language: unknown): string {
  return normalizeLimitedShikiLanguage(language);
}

export function escapeHtml(value = ''): string {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

export async function getShikiHighlighter(): Promise<ShikiHighlighter> {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighter({
      themes: [SHIKI_THEMES.light, SHIKI_THEMES.dark],
    });
  }

  return highlighterPromise;
}

export async function ensureShikiLanguages(
  langs: string[] = [],
): Promise<ShikiHighlighter> {
  const highlighter = await getShikiHighlighter();
  await Promise.all(
    langs.map((language) => highlighter.ensureLanguage(language)),
  );
  return highlighter;
}

export function renderShikiCode(
  highlighter: ShikiHighlighter,
  code: string,
  language: unknown,
  colorMode: ColorMode = 'auto',
): string {
  const normalizedLanguage = normalizeLanguage(language);
  let options:
    | { lang: string; themes: typeof SHIKI_THEMES }
    | { lang: string; theme: string } = {
    lang: normalizedLanguage,
    themes: SHIKI_THEMES,
  };
  if (colorMode === 'dark') {
    options = { lang: normalizedLanguage, theme: SHIKI_THEMES.dark };
  } else if (colorMode === 'light') {
    options = { lang: normalizedLanguage, theme: SHIKI_THEMES.light };
  }

  try {
    return highlighter.codeToHtml(code, options);
  } catch (error: unknown) {
    console.warn(
      `Failed to render code with Shiki language "${normalizedLanguage}". Falling back to plain text.`,
      error,
    );

    let fallbackOptions:
      | { lang: string; themes: typeof SHIKI_THEMES }
      | { lang: string; theme: string } = {
      lang: 'text',
      themes: SHIKI_THEMES,
    };
    if (colorMode === 'dark') {
      fallbackOptions = { lang: 'text', theme: SHIKI_THEMES.dark };
    } else if (colorMode === 'light') {
      fallbackOptions = { lang: 'text', theme: SHIKI_THEMES.light };
    }

    return highlighter.codeToHtml(code, fallbackOptions);
  }
}

export function collectMarkdownFenceLanguages(
  markdownIt: MarkdownItInstance,
  markdown: string,
): string[] {
  if (!markdown) return [];

  return markdownIt
    .parse(markdown, {})
    .filter((token) => token.type === 'fence')
    .map((token) => normalizeLanguage(token.info));
}

export function normalizeShikiLanguage(language: unknown): string {
  return normalizeLanguage(language);
}
