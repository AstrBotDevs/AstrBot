/**
 * I18n TypeScript Type Definitions
 * 国际化类型定义，确保类型安全
 */

// 核心模块类型定义
export interface CoreTranslations {
  common: {
    save: string;
    cancel: string;
    close: string;
    delete: string;
    edit: string;
    add: string;
    confirm: string;
    loading: string;
    success: string;
    error: string;
    warning: string;
    info: string;
    name: string;
    description: string;
    author: string;
    status: string;
    actions: string;
    enable: string;
    disable: string;
    enabled: string;
    disabled: string;
    reload: string;
    configure: string;
    install: string;
    uninstall: string;
    update: string;
    language: string;
  };
  actions: {
    create: string;
    read: string;
    update: string;
    delete: string;
    search: string;
    filter: string;
    sort: string;
    export: string;
    import: string;
    backup: string;
    restore: string;
  };
  status: {
    loading: string;
    success: string;
    error: string;
    warning: string;
    info: string;
    pending: string;
    processing: string;
    completed: string;
    failed: string;
    cancelled: string;
  };
  navigation: {
    dashboard: string;
    platforms: string;
    providers: string;
    toolUse: string;
    config: string;
    extension: string;
    chat: string;
    conversation: string;
    console: string;
    alkaid: string;
    about: string;
    settings: string;
    documentation: string;
    github: string;
    drag: string;
  };
}

// 功能模块类型定义
export interface FeatureTranslations {
  chat: {
    title: string;
    subtitle: string;
    input: {
      placeholder: string;
      send: string;
      clear: string;
    };
    message: {
      user: string;
      assistant: string;
      system: string;
    };
    voice: {
      start: string;
      stop: string;
      recording: string;
    };
  };
  extension: {
    title: string;
    subtitle: string;
    showSystemPlugins: string;
    hideSystemPlugins: string;
    platformCommandConfig: string;
    noPlugins: string;
    tryInstallOrShowSystem: string;
    configDialog: {
      title: string;
      noConfig: string;
    };
    platformConfig: {
      title: string;
      description: string;
      noPlatforms: string;
      addPlatformFirst: string;
      goToPlatformManagement: string;
    };
    marketplace: {
      title: string;
      installPlugin: string;
      fromGitHub: string;
      fromLocal: string;
      repoUrl: string;
      selectFile: string;
      pluginDevelopmentDoc: string;
      submitPluginRepo: string;
    };
  };
  conversation: {
    title: string;
    subtitle: string;
    table: {
      id: string;
      platform: string;
      user: string;
      message: string;
      time: string;
      actions: string;
    };
    filter: {
      platform: string;
      user: string;
      dateRange: string;
    };
    export: {
      title: string;
      format: string;
      range: string;
    };
  };
  provider: {
    title: string;
    tabTypes: {
      chat_completion: string;
      speech_to_text: string;
      text_to_speech: string;
      embedding: string;
    };
    openaiDescription: string;
    defaultDescription: string;
  };
  platform: {
    title: string;
    subtitle: string;
    adapters: string;
    addAdapter: string;
  };
  config: {
    title: string;
    subtitle: string;
    sections: {
      general: string;
      advanced: string;
      security: string;
    };
  };
  console: {
    title: string;
    subtitle: string;
    clear: string;
    download: string;
  };
  about: {
    title: string;
    version: string;
    author: string;
    license: string;
    repository: string;
  };
  alkaid: {
    comingSoon: string;
    knowledgeBase: {
      title: string;
      subtitle: string;
    };
    memory: {
      title: string;
      subtitle: string;
    };
  };
}

// 消息模块类型定义
export interface MessageTranslations {
  errors: {
    network: {
      timeout: string;
      connection: string;
      server: string;
    };
    validation: {
      required: string;
      invalid: string;
      tooLong: string;
      tooShort: string;
    };
    auth: {
      unauthorized: string;
      forbidden: string;
      tokenExpired: string;
    };
  };
  success: {
    save: {
      completed: string;
      config: string;
      settings: string;
    };
    action: {
      created: string;
      updated: string;
      deleted: string;
    };
  };
  validation: {
    required: string;
    email: string;
    url: string;
    number: string;
    min: string;
    max: string;
  };
}

// 完整的翻译类型
export interface TranslationSchema extends CoreTranslations, FeatureTranslations, MessageTranslations {}

// 翻译键类型
export type TranslationKey = 
  // Core keys
  | `core.common.${keyof CoreTranslations['common']}`
  | `core.actions.${keyof CoreTranslations['actions']}`
  | `core.status.${keyof CoreTranslations['status']}`
  | `core.navigation.${keyof CoreTranslations['navigation']}`
  
  // Feature keys
  | `features.chat.${keyof FeatureTranslations['chat'] | `input.${keyof FeatureTranslations['chat']['input']}` | `message.${keyof FeatureTranslations['chat']['message']}` | `voice.${keyof FeatureTranslations['chat']['voice']}`}`
  | `features.extension.${keyof FeatureTranslations['extension'] | `configDialog.${keyof FeatureTranslations['extension']['configDialog']}` | `platformConfig.${keyof FeatureTranslations['extension']['platformConfig']}` | `marketplace.${keyof FeatureTranslations['extension']['marketplace']}`}`
  | `features.conversation.${keyof FeatureTranslations['conversation'] | `table.${keyof FeatureTranslations['conversation']['table']}` | `filter.${keyof FeatureTranslations['conversation']['filter']}` | `export.${keyof FeatureTranslations['conversation']['export']}`}`
  | `features.provider.${keyof FeatureTranslations['provider'] | `tabTypes.${keyof FeatureTranslations['provider']['tabTypes']}`}`
  | `features.platform.${keyof FeatureTranslations['platform']}`
  | `features.config.${keyof FeatureTranslations['config'] | `sections.${keyof FeatureTranslations['config']['sections']}`}`
  | `features.console.${keyof FeatureTranslations['console']}`
  | `features.about.${keyof FeatureTranslations['about']}`
  | `features.alkaid.${keyof FeatureTranslations['alkaid'] | `knowledgeBase.${keyof FeatureTranslations['alkaid']['knowledgeBase']}` | `memory.${keyof FeatureTranslations['alkaid']['memory']}`}`
  
  // Message keys
  | `messages.errors.${keyof MessageTranslations['errors'] | `network.${keyof MessageTranslations['errors']['network']}` | `validation.${keyof MessageTranslations['errors']['validation']}` | `auth.${keyof MessageTranslations['errors']['auth']}`}`
  | `messages.success.${keyof MessageTranslations['success'] | `save.${keyof MessageTranslations['success']['save']}` | `action.${keyof MessageTranslations['success']['action']}`}`
  | `messages.validation.${keyof MessageTranslations['validation']}`;

// 语言环境类型
export type Locale = 'zh-CN' | 'en-US';

// 翻译函数类型
export type TranslationFunction = {
  (key: TranslationKey): string;
  (key: TranslationKey, params: Record<string, string | number>): string;
};

// 模块加载状态
export interface ModuleLoadingState {
  core: boolean;
  features: boolean;
  messages: boolean;
}

// 翻译配置
export interface I18nConfig {
  locale: Locale;
  fallbackLocale: Locale;
  lazy: boolean;
  preload: string[];
  caching: boolean;
  devMode: boolean;
}

// 验证结果
export interface ValidationResult {
  isValid: boolean;
  missingKeys: string[];
  extraKeys: string[];
  errors: ValidationError[];
}

export interface ValidationError {
  type: 'missing' | 'extra' | 'type_mismatch' | 'empty_value';
  key: string;
  message: string;
  severity: 'error' | 'warning';
}

// 使用情况报告
export interface UsageReport {
  unusedKeys: string[];
  undefinedKeys: string[];
  coverage: number;
  totalKeys: number;
  usedKeys: number;
}

// 翻译统计信息
export interface TranslationStats {
  modules: {
    [moduleName: string]: {
      keys: number;
      coverage: number;
      lastUpdated: string;
    };
  };
  locales: {
    [locale: string]: {
      totalKeys: number;
      translatedKeys: number;
      coverage: number;
    };
  };
  overall: {
    totalKeys: number;
    averageCoverage: number;
    lastSync: string;
  };
}

// 开发工具类型
export interface DevToolsData {
  currentLocale: Locale;
  loadedModules: string[];
  cacheStats: {
    size: number;
    hits: number;
    misses: number;
  };
  performance: {
    loadTime: number;
    renderTime: number;
  };
}

// 导出类型声明模块
declare module 'vue-i18n' {
  export interface DefineLocaleMessage extends TranslationSchema {}
} 