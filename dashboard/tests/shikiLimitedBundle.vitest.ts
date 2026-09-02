import { describe, expect, it } from 'vitest';
import {
  bundledLanguages,
  codeToHtml,
  createCssVariablesTheme,
  createHighlighter,
  createJavaScriptRegexEngine,
  createOnigurumaEngine,
  getTokenStyleObject,
  isFenceLanguageSettled,
  normalizeLimitedShikiLanguage,
  stringifyTokenStyle,
} from 'shiki';

describe('limited shiki bundle', () => {
  it('exports the stream-diffs shiki surface', () => {
    expect(codeToHtml).toEqual(expect.any(Function));
    expect(createCssVariablesTheme).toEqual(expect.any(Function));
    expect(createHighlighter).toEqual(expect.any(Function));
    expect(createJavaScriptRegexEngine).toEqual(expect.any(Function));
    expect(createOnigurumaEngine).toEqual(expect.any(Function));
    expect(getTokenStyleObject).toEqual(expect.any(Function));
    expect(stringifyTokenStyle).toEqual(expect.any(Function));
    expect(bundledLanguages.javascript).toEqual(expect.any(Function));
    expect(bundledLanguages.js).toEqual(expect.any(Function));
  });

  it('highlights C++ fences instead of falling back to plaintext', async () => {
    expect(normalizeLimitedShikiLanguage('C++')).toBe('cpp');
    expect(normalizeLimitedShikiLanguage('hpp')).toBe('cpp');
    expect(bundledLanguages.cpp).toEqual(expect.any(Function));
    expect(bundledLanguages['c++']).toEqual(expect.any(Function));

    const html = await codeToHtml(
      '#include <iostream>\nint main() { return 0; }\n',
      { lang: 'c++', theme: 'github-light' },
    );
    expect(html).toContain('class="shiki github-light"');
    expect(html).toMatch(/<span style="color:#[0-9A-Fa-f]+">#include<\/span>/);
    expect(html).toContain('iostream');
  });

  it('covers TIOBE and config languages without preloading them', async () => {
    expect(normalizeLimitedShikiLanguage('golang')).toBe('go');
    expect(normalizeLimitedShikiLanguage('C#')).toBe('csharp');
    expect(normalizeLimitedShikiLanguage('toml')).toBe('toml');
    expect(normalizeLimitedShikiLanguage('scratch')).toBe('text');
    expect(normalizeLimitedShikiLanguage('python:line-numbers')).toBe('python');
    expect(normalizeLimitedShikiLanguage('c++:linenos')).toBe('cpp');
    expect(normalizeLimitedShikiLanguage('h++')).toBe('cpp');
    expect(bundledLanguages.rust).toEqual(expect.any(Function));
    expect(bundledLanguages.shellscript).toEqual(expect.any(Function));
    expect(bundledLanguages.terraform).toEqual(expect.any(Function));

    const highlighter = await createHighlighter({
      langs: ['text'],
      themes: ['github-light'],
    });
    expect(highlighter.getLoadedLanguages()).not.toContain('python');
    expect(highlighter.getLoadedLanguages()).not.toContain('rust');

    await highlighter.ensureLanguage('python');
    const html = highlighter.codeToHtml('print(1)\n', {
      lang: 'python',
      theme: 'github-light',
    });
    expect(html).toMatch(/style="color:#[0-9A-Fa-f]+"/);
  });

  it('does not treat a streaming prefix as a settled fence language', () => {
    expect(
      isFenceLanguageSettled({ language: 'c', code: '', loading: true }),
    ).toBe(false);
    expect(
      isFenceLanguageSettled({ language: 'cp', code: '', loading: true }),
    ).toBe(false);
    expect(
      isFenceLanguageSettled({ language: 'java', code: '', loading: true }),
    ).toBe(false);
    expect(
      isFenceLanguageSettled({ language: 'cpp', code: '', loading: true }),
    ).toBe(true);
    expect(
      isFenceLanguageSettled({
        language: 'c',
        code: 'int main() {}\n',
        loading: true,
      }),
    ).toBe(true);
    expect(
      isFenceLanguageSettled({ language: 'c', code: '', loading: false }),
    ).toBe(true);
    expect(
      isFenceLanguageSettled({ language: 'python', code: '', loading: true }),
    ).toBe(true);
    expect(
      isFenceLanguageSettled({
        language: 'python:line-numbers',
        code: '',
        loading: true,
      }),
    ).toBe(true);
  });
});
