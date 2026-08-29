import { describe, expect, it } from 'vitest';
import { configDocsHref, docsHref } from '@/utils/docsHref';

describe('docsHref', () => {
  it('builds same-origin help paths for each locale', () => {
    expect(docsHref('', 'zh-CN')).toBe('/help/');
    expect(docsHref('index.html', 'zh-CN')).toBe('/help/');
    expect(docsHref('/faq.html', 'zh-CN')).toBe('/help/faq.html');
    expect(docsHref('faq.html', 'zh-CN')).toBe('/help/faq.html');
    expect(docsHref('faq.html', 'en-US')).toBe('/help/en/faq.html');
  });
});

describe('configDocsHref', () => {
  it('builds locale-prefixed paths from relative metadata docs', () => {
    expect(configDocsHref('use/computer.html', 'zh-CN')).toBe(
      '/help/use/computer.html',
    );
    expect(configDocsHref('use/computer.html', 'en-US')).toBe(
      '/help/en/use/computer.html',
    );
    expect(configDocsHref('/use/proactive-agent.html', 'zh-CN')).toBe(
      '/help/use/proactive-agent.html',
    );
  });

  it('does not fall back to the docs index', () => {
    expect(configDocsHref(undefined, 'zh-CN')).toBe('');
    expect(configDocsHref('', 'zh-CN')).toBe('');
    expect(configDocsHref('   ', 'en-US')).toBe('');
    expect(configDocsHref('index.html', 'zh-CN')).toBe('');
    expect(configDocsHref(12, 'zh-CN')).toBe('');
  });
});
