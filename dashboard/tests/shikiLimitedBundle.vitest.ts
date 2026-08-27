import { describe, expect, it } from 'vitest';
import {
  bundledLanguages,
  codeToHtml,
  createCssVariablesTheme,
  createHighlighter,
  createJavaScriptRegexEngine,
  createOnigurumaEngine,
  getTokenStyleObject,
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
});
