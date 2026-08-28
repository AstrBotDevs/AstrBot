import { describe, expect, it } from 'vitest';
import { docsHref } from '@/utils/docsHref';

describe('docsHref', () => {
  it('builds same-origin help paths for each locale', () => {
    expect(docsHref('', 'zh-CN')).toBe('/help/');
    expect(docsHref('index.html', 'zh-CN')).toBe('/help/');
    expect(docsHref('/faq.html', 'zh-CN')).toBe('/help/faq.html');
    expect(docsHref('faq.html', 'zh-CN')).toBe('/help/faq.html');
    expect(docsHref('faq.html', 'en-US')).toBe('/help/en/faq.html');
  });
});
