// Per-locale translation loaders.
// Each locale is bundled into its own async chunk so only the active
// language is downloaded instead of all of them upfront.

import type zhCN from './locales/zh-CN';

export type Translations = typeof zhCN;

export const localeLoaders = {
  'zh-CN': () => import('./locales/zh-CN').then((m) => m.default),
  'en-US': () => import('./locales/en-US').then((m) => m.default),
  'ru-RU': () => import('./locales/ru-RU').then((m) => m.default),
  'ja-JP': () => import('./locales/ja-JP').then((m) => m.default)
} as const;

export type Locale = keyof typeof localeLoaders;
