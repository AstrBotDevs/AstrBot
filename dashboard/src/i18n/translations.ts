import zhCNCommon from './locales/zh-CN/core/common.json';
import zhCNActions from './locales/zh-CN/core/actions.json';
import zhCNStatus from './locales/zh-CN/core/status.json';
import zhCNNavigation from './locales/zh-CN/core/navigation.json';
import zhCNHeader from './locales/zh-CN/core/header.json';
import zhCNShared from './locales/zh-CN/core/shared.json';

import zhCNChat from './locales/zh-CN/features/chat.json';
import zhCNExtension from './locales/zh-CN/features/extension.json';
import zhCNConversation from './locales/zh-CN/features/conversation.json';
import zhCNSessionManagement from './locales/zh-CN/features/session-management.json';
import zhCNToolUse from './locales/zh-CN/features/tool-use.json';
import zhCNProvider from './locales/zh-CN/features/provider.json';
import zhCNPlatform from './locales/zh-CN/features/platform.json';
import zhCNConfig from './locales/zh-CN/features/config.json';
import zhCNConfigMetadata from './locales/zh-CN/features/config-metadata.json';
import zhCNConsole from './locales/zh-CN/features/console.json';
import zhCNTrace from './locales/zh-CN/features/trace.json';
import zhCNAbout from './locales/zh-CN/features/about.json';
import zhCNSettings from './locales/zh-CN/features/settings.json';
import zhCNAuth from './locales/zh-CN/features/auth.json';
import zhCNChart from './locales/zh-CN/features/chart.json';
import zhCNDashboard from './locales/zh-CN/features/dashboard.json';
import zhCNCron from './locales/zh-CN/features/cron.json';
import zhCNAlkaidIndex from './locales/zh-CN/features/alkaid/index.json';
import zhCNAlkaidKnowledgeBase from './locales/zh-CN/features/alkaid/knowledge-base.json';
import zhCNAlkaidMemory from './locales/zh-CN/features/alkaid/memory.json';
import zhCNKnowledgeBaseIndex from './locales/zh-CN/features/knowledge-base/index.json';
import zhCNKnowledgeBaseDetail from './locales/zh-CN/features/knowledge-base/detail.json';
import zhCNKnowledgeBaseDocument from './locales/zh-CN/features/knowledge-base/document.json';
import zhCNPersona from './locales/zh-CN/features/persona.json';
import zhCNMigration from './locales/zh-CN/features/migration.json';
import zhCNCommand from './locales/zh-CN/features/command.json';
import zhCNSubagent from './locales/zh-CN/features/subagent.json';
import zhCNWelcome from './locales/zh-CN/features/welcome.json';

import zhCNErrors from './locales/zh-CN/messages/errors.json';
import zhCNSuccess from './locales/zh-CN/messages/success.json';
import zhCNValidation from './locales/zh-CN/messages/validation.json';

export const SUPPORTED_LOCALES = ['zh-CN', 'en-US', 'ru-RU'] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

// 保留一份静态 schema 作为类型来源
export const translationSchema = {
  core: {
    common: zhCNCommon,
    actions: zhCNActions,
    status: zhCNStatus,
    navigation: zhCNNavigation,
    header: zhCNHeader,
    shared: zhCNShared
  },
  features: {
    chat: zhCNChat,
    extension: zhCNExtension,
    conversation: zhCNConversation,
    'session-management': zhCNSessionManagement,
    tooluse: zhCNToolUse,
    provider: zhCNProvider,
    platform: zhCNPlatform,
    config: zhCNConfig,
    'config-metadata': zhCNConfigMetadata,
    console: zhCNConsole,
    trace: zhCNTrace,
    about: zhCNAbout,
    settings: zhCNSettings,
    auth: zhCNAuth,
    chart: zhCNChart,
    dashboard: zhCNDashboard,
    cron: zhCNCron,
    alkaid: {
      index: zhCNAlkaidIndex,
      'knowledge-base': zhCNAlkaidKnowledgeBase,
      memory: zhCNAlkaidMemory
    },
    'knowledge-base': {
      index: zhCNKnowledgeBaseIndex,
      detail: zhCNKnowledgeBaseDetail,
      document: zhCNKnowledgeBaseDocument
    },
    persona: zhCNPersona,
    migration: zhCNMigration,
    command: zhCNCommand,
    subagent: zhCNSubagent,
    welcome: zhCNWelcome
  },
  messages: {
    errors: zhCNErrors,
    success: zhCNSuccess,
    validation: zhCNValidation
  }
} as const;

export type TranslationData = typeof translationSchema;

type TranslationModule = {
  default: Record<string, any>;
};

// NOTE:
// `zh-CN` is statically imported above to build `translationSchema` (used at runtime and for type inference).
// If the same JSON files are also included in the lazy-loading glob, Vite will warn that those modules cannot
// be moved into a separate chunk. Excluding `zh-CN` here keeps the default locale bundled while allowing
// other locales to be truly lazy-loaded.
const localeModuleLoaders = import.meta.glob<TranslationModule>([
  './locales/*/**/*.json',
  '!./locales/zh-CN/**/*.json'
]);
const localeCache = new Map<SupportedLocale, TranslationData>();
const loadingPromises = new Map<SupportedLocale, Promise<TranslationData>>();

export function isLocaleSupported(locale: string): locale is SupportedLocale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(locale);
}

const PATH_SEGMENT_ALIASES: Record<string, string> = {
  'tool-use': 'tooluse'
};

function getSchemaNode(pathSegments: string[]): any {
  let node: any = translationSchema;
  for (const segment of pathSegments) {
    if (!node || typeof node !== 'object') {
      return null;
    }
    node = node[segment];
  }
  return node;
}

function normalizePathSegment(segment: string, normalizedParentPath: string[]): string {
  // Prefer schema-driven normalization: only map when the target key exists under the same parent.
  const parentNode = getSchemaNode(normalizedParentPath);
  if (parentNode && typeof parentNode === 'object') {
    if (segment in parentNode) {
      return segment;
    }

    const alias = PATH_SEGMENT_ALIASES[segment];
    if (alias && alias in parentNode) {
      return alias;
    }

    // Heuristic: if file uses kebab-case but schema key is collapsed (e.g. tool-use -> tooluse)
    const collapsed = segment.replace(/-/g, '');
    if (collapsed !== segment && collapsed in parentNode) {
      return collapsed;
    }
  }

  // Fallback to explicit aliases to keep backward compatibility.
  return PATH_SEGMENT_ALIASES[segment] ?? segment;
}

function normalizePathSegments(segments: string[]): string[] {
  const normalized: string[] = [];
  for (const segment of segments) {
    normalized.push(normalizePathSegment(segment, normalized));
  }
  return normalized;
}

function setNestedValue(target: Record<string, any>, pathSegments: string[], value: Record<string, any>): void {
  let current = target;

  for (let index = 0; index < pathSegments.length - 1; index++) {
    const segment = pathSegments[index];
    if (!(segment in current) || typeof current[segment] !== 'object') {
      current[segment] = {};
    }
    current = current[segment];
  }

  const finalSegment = pathSegments[pathSegments.length - 1];
  if (!(finalSegment in current) || typeof current[finalSegment] !== 'object') {
    current[finalSegment] = {};
  }

  current[finalSegment] = {
    ...current[finalSegment],
    ...value
  };
}

function extractLocaleAndPath(modulePath: string): { locale: string; pathSegments: string[] } | null {
  const match = modulePath.match(/^\.\/locales\/([^/]+)\/(.+)\.json$/);
  if (!match) {
    return null;
  }

  const [, locale, relativePath] = match;
  const pathSegments = normalizePathSegments(relativePath.split('/'));

  return {
    locale,
    pathSegments
  };
}

export async function loadLocaleTranslations(locale: SupportedLocale): Promise<TranslationData> {
  if (locale === 'zh-CN') {
    localeCache.set(locale, translationSchema);
    return translationSchema;
  }

  const cached = localeCache.get(locale);
  if (cached) {
    return cached;
  }

  const inFlight = loadingPromises.get(locale);
  if (inFlight) {
    return inFlight;
  }

  const loadingPromise = (async () => {
    const localeData: Record<string, any> = {};

    const entries = Object.entries(localeModuleLoaders).filter(([modulePath]) =>
      modulePath.startsWith(`./locales/${locale}/`)
    );

    if (entries.length === 0) {
      throw new Error(`No translation modules found for locale: ${locale}`);
    }

    let loadedModuleCount = 0;

    await Promise.all(
      entries.map(async ([modulePath, loadModule]) => {
        const parsed = extractLocaleAndPath(modulePath);
        if (!parsed || !isLocaleSupported(parsed.locale)) {
          return;
        }

        const loadedModule = await loadModule();
        const moduleData = loadedModule.default || loadedModule;
        setNestedValue(localeData, parsed.pathSegments, moduleData);
        loadedModuleCount += 1;
      })
    );

    if (loadedModuleCount === 0 || Object.keys(localeData).length === 0) {
      throw new Error(`Loaded empty translations for locale: ${locale}`);
    }

    const typedLocaleData = localeData as TranslationData;
    localeCache.set(locale, typedLocaleData);

    return typedLocaleData;
  })();

  loadingPromises.set(locale, loadingPromise);

  try {
    return await loadingPromise;
  } finally {
    loadingPromises.delete(locale);
  }
}

export function clearLocaleTranslationsCache(locale?: SupportedLocale): void {
  if (locale) {
    localeCache.delete(locale);
    loadingPromises.delete(locale);
    return;
  }

  localeCache.clear();
  loadingPromises.clear();
}
