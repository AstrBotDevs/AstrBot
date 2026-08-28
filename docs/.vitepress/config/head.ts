import type { HeadConfig } from 'vitepress';

export function head(base = '/'): HeadConfig[] {
  const prefix = base.endsWith('/') ? base.slice(0, -1) : base;
  return [
    [
      'link',
      {
        rel: 'preconnect',
        href: 'https://fonts.googleapis.cn',
        crossorigin: '',
      },
    ],
    ['link', { rel: 'dns-prefetch', href: 'https://fonts.googleapis.cn' }],
    [
      'link',
      { rel: 'preconnect', href: 'https://fonts.gstatic.cn', crossorigin: '' },
    ],
    ['link', { rel: 'dns-prefetch', href: 'https://fonts.gstatic.cn' }],
    [
      'link',
      {
        rel: 'stylesheet',
        href: 'https://fonts.googleapis.com/css2?family=Outfit:wght@100..900&display=swap',
      },
    ],
    ['link', { rel: 'icon', href: `${prefix}/logo.png` }],
    ['meta', { name: 'description', content: 'AstrBot' }],
    [
      'meta',
      { name: 'viewport', content: 'width=device-width, initial-scale=1.0' },
    ],
  ];
}
