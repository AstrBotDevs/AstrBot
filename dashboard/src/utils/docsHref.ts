export const DOCS_MOUNT = '/help';

function resolveDocsLocale(locale?: string): string {
  if (locale) {
    return locale;
  }
  if (typeof localStorage !== 'undefined') {
    return localStorage.getItem('astrbot-locale') || 'zh-CN';
  }
  return 'zh-CN';
}

export function docsHref(path = '', locale?: string): string {
  const isEn = resolveDocsLocale(locale).toLowerCase().startsWith('en');
  const prefix = isEn ? `${DOCS_MOUNT}/en` : DOCS_MOUNT;
  const clean = path.replace(/^\/+/, '');
  if (!clean || clean === 'index.html') {
    return `${prefix}/`;
  }
  return `${prefix}/${clean}`;
}
