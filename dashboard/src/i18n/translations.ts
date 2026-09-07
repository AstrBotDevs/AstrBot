// 静态导入所有翻译文件
// 这种方式确保构建时所有翻译都会被正确打包

// 中文翻译
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
import zhCNStats from './locales/zh-CN/features/stats.json';
import zhCNAlkaidIndex from './locales/zh-CN/features/alkaid/index.json';
import zhCNAlkaidKnowledgeBase from './locales/zh-CN/features/alkaid/knowledge-base.json';
import zhCNAlkaidMemory from './locales/zh-CN/features/alkaid/memory.json';
import zhCNKnowledgeBaseIndex from './locales/zh-CN/features/knowledge-base/index.json';
import zhCNKnowledgeBaseDetail from './locales/zh-CN/features/knowledge-base/detail.json';
import zhCNKnowledgeBaseDocument from './locales/zh-CN/features/knowledge-base/document.json';
import zhCNPersona from './locales/zh-CN/features/persona.json';
import zhCNCommand from './locales/zh-CN/features/command.json';
import zhCNSubagent from './locales/zh-CN/features/subagent.json';
import zhCNWelcome from './locales/zh-CN/features/welcome.json';

import zhCNErrors from './locales/zh-CN/messages/errors.json';
import zhCNSuccess from './locales/zh-CN/messages/success.json';
import zhCNValidation from './locales/zh-CN/messages/validation.json';

// English translation
import enUSCommon from './locales/en-US/core/common.json';
import enUSActions from './locales/en-US/core/actions.json';
import enUSStatus from './locales/en-US/core/status.json';
import enUSNavigation from './locales/en-US/core/navigation.json';
import enUSHeader from './locales/en-US/core/header.json';
import enUSShared from './locales/en-US/core/shared.json';

import enUSChat from './locales/en-US/features/chat.json';
import enUSExtension from './locales/en-US/features/extension.json';
import enUSConversation from './locales/en-US/features/conversation.json';
import enUSSessionManagement from './locales/en-US/features/session-management.json';
import enUSToolUse from './locales/en-US/features/tool-use.json';
import enUSProvider from './locales/en-US/features/provider.json';
import enUSPlatform from './locales/en-US/features/platform.json';
import enUSConfig from './locales/en-US/features/config.json';
import enUSConfigMetadata from './locales/en-US/features/config-metadata.json';
import enUSConsole from './locales/en-US/features/console.json';
import enUSTrace from './locales/en-US/features/trace.json';
import enUSAbout from './locales/en-US/features/about.json';
import enUSSettings from './locales/en-US/features/settings.json';
import enUSAuth from './locales/en-US/features/auth.json';
import enUSChart from './locales/en-US/features/chart.json';
import enUSDashboard from './locales/en-US/features/dashboard.json';
import enUSCron from './locales/en-US/features/cron.json';
import enUSStats from './locales/en-US/features/stats.json';
import enUSAlkaidIndex from './locales/en-US/features/alkaid/index.json';
import enUSAlkaidKnowledgeBase from './locales/en-US/features/alkaid/knowledge-base.json';
import enUSAlkaidMemory from './locales/en-US/features/alkaid/memory.json';
import enUSKnowledgeBaseIndex from './locales/en-US/features/knowledge-base/index.json';
import enUSKnowledgeBaseDetail from './locales/en-US/features/knowledge-base/detail.json';
import enUSKnowledgeBaseDocument from './locales/en-US/features/knowledge-base/document.json';
import enUSPersona from './locales/en-US/features/persona.json';
import enUSCommand from './locales/en-US/features/command.json';
import enUSSubagent from './locales/en-US/features/subagent.json';
import enUSWelcome from './locales/en-US/features/welcome.json';

import enUSErrors from './locales/en-US/messages/errors.json';
import enUSSuccess from './locales/en-US/messages/success.json';
import enUSValidation from './locales/en-US/messages/validation.json';

// Russian translation
import ruRUCommon from './locales/ru-RU/core/common.json';
import ruRUActions from './locales/ru-RU/core/actions.json';
import ruRUStatus from './locales/ru-RU/core/status.json';
import ruRUNavigation from './locales/ru-RU/core/navigation.json';
import ruRUHeader from './locales/ru-RU/core/header.json';
import ruRUShared from './locales/ru-RU/core/shared.json';

import ruRUChat from './locales/ru-RU/features/chat.json';
import ruRUExtension from './locales/ru-RU/features/extension.json';
import ruRUConversation from './locales/ru-RU/features/conversation.json';
import ruRUSessionManagement from './locales/ru-RU/features/session-management.json';
import ruRUToolUse from './locales/ru-RU/features/tool-use.json';
import ruRUProvider from './locales/ru-RU/features/provider.json';
import ruRUPlatform from './locales/ru-RU/features/platform.json';
import ruRUConfig from './locales/ru-RU/features/config.json';
import ruRUConfigMetadata from './locales/ru-RU/features/config-metadata.json';
import ruRUConsole from './locales/ru-RU/features/console.json';
import ruRUTrace from './locales/ru-RU/features/trace.json';
import ruRUAbout from './locales/ru-RU/features/about.json';
import ruRUSettings from './locales/ru-RU/features/settings.json';
import ruRUAuth from './locales/ru-RU/features/auth.json';
import ruRUChart from './locales/ru-RU/features/chart.json';
import ruRUDashboard from './locales/ru-RU/features/dashboard.json';
import ruRUCron from './locales/ru-RU/features/cron.json';
import ruRUStats from './locales/ru-RU/features/stats.json';
import ruRUAlkaidIndex from './locales/ru-RU/features/alkaid/index.json';
import ruRUAlkaidKnowledgeBase from './locales/ru-RU/features/alkaid/knowledge-base.json';
import ruRUAlkaidMemory from './locales/ru-RU/features/alkaid/memory.json';
import ruRUKnowledgeBaseIndex from './locales/ru-RU/features/knowledge-base/index.json';
import ruRUKnowledgeBaseDetail from './locales/ru-RU/features/knowledge-base/detail.json';
import ruRUKnowledgeBaseDocument from './locales/ru-RU/features/knowledge-base/document.json';
import ruRUPersona from './locales/ru-RU/features/persona.json';
import ruRUCommand from './locales/ru-RU/features/command.json';
import ruRUSubagent from './locales/ru-RU/features/subagent.json';
import ruRUWelcome from './locales/ru-RU/features/welcome.json';

import ruRUErrors from './locales/ru-RU/messages/errors.json';
import ruRUSuccess from './locales/ru-RU/messages/success.json';
import ruRUValidation from './locales/ru-RU/messages/validation.json';

// Japanese translation
import jaJPCommon from './locales/ja-JP/core/common.json';
import jaJPActions from './locales/ja-JP/core/actions.json';
import jaJPStatus from './locales/ja-JP/core/status.json';
import jaJPNavigation from './locales/ja-JP/core/navigation.json';
import jaJPHeader from './locales/ja-JP/core/header.json';
import jaJPShared from './locales/ja-JP/core/shared.json';

import jaJPChat from './locales/ja-JP/features/chat.json';
import jaJPExtension from './locales/ja-JP/features/extension.json';
import jaJPConversation from './locales/ja-JP/features/conversation.json';
import jaJPSessionManagement from './locales/ja-JP/features/session-management.json';
import jaJPToolUse from './locales/ja-JP/features/tool-use.json';
import jaJPProvider from './locales/ja-JP/features/provider.json';
import jaJPPlatform from './locales/ja-JP/features/platform.json';
import jaJPConfig from './locales/ja-JP/features/config.json';
import jaJPConfigMetadata from './locales/ja-JP/features/config-metadata.json';
import jaJPConsole from './locales/ja-JP/features/console.json';
import jaJPTrace from './locales/ja-JP/features/trace.json';
import jaJPAbout from './locales/ja-JP/features/about.json';
import jaJPSettings from './locales/ja-JP/features/settings.json';
import jaJPAuth from './locales/ja-JP/features/auth.json';
import jaJPChart from './locales/ja-JP/features/chart.json';
import jaJPDashboard from './locales/ja-JP/features/dashboard.json';
import jaJPCron from './locales/ja-JP/features/cron.json';
import jaJPStats from './locales/ja-JP/features/stats.json';
import jaJPAlkaidIndex from './locales/ja-JP/features/alkaid/index.json';
import jaJPAlkaidKnowledgeBase from './locales/ja-JP/features/alkaid/knowledge-base.json';
import jaJPAlkaidMemory from './locales/ja-JP/features/alkaid/memory.json';
import jaJPKnowledgeBaseIndex from './locales/ja-JP/features/knowledge-base/index.json';
import jaJPKnowledgeBaseDetail from './locales/ja-JP/features/knowledge-base/detail.json';
import jaJPKnowledgeBaseDocument from './locales/ja-JP/features/knowledge-base/document.json';
import jaJPPersona from './locales/ja-JP/features/persona.json';
import jaJPCommand from './locales/ja-JP/features/command.json';
import jaJPSubagent from './locales/ja-JP/features/subagent.json';
import jaJPWelcome from './locales/ja-JP/features/welcome.json';

import jaJPErrors from './locales/ja-JP/messages/errors.json';
import jaJPSuccess from './locales/ja-JP/messages/success.json';
import jaJPValidation from './locales/ja-JP/messages/validation.json';

// 组装翻译对象
export const translations = {
  'zh-CN': {
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
      stats: zhCNStats,
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
      command: zhCNCommand,
      subagent: zhCNSubagent,
      welcome: zhCNWelcome
    },
    messages: {
      errors: zhCNErrors,
      success: zhCNSuccess,
      validation: zhCNValidation
    }
  },
  'en-US': {
    core: {
      common: enUSCommon,
      actions: enUSActions,
      status: enUSStatus,
      navigation: enUSNavigation,
      header: enUSHeader,
      shared: enUSShared
    },
    features: {
      chat: enUSChat,
      extension: enUSExtension,
      conversation: enUSConversation,
      'session-management': enUSSessionManagement,
      tooluse: enUSToolUse,
      provider: enUSProvider,
      platform: enUSPlatform,
      config: enUSConfig,
      'config-metadata': enUSConfigMetadata,
      console: enUSConsole,
      trace: enUSTrace,
      about: enUSAbout,
      settings: enUSSettings,
      auth: enUSAuth,
      chart: enUSChart,
      dashboard: enUSDashboard,
      cron: enUSCron,
      stats: enUSStats,
      alkaid: {
        index: enUSAlkaidIndex,
        'knowledge-base': enUSAlkaidKnowledgeBase,
        memory: enUSAlkaidMemory
      },
      'knowledge-base': {
        index: enUSKnowledgeBaseIndex,
        detail: enUSKnowledgeBaseDetail,
        document: enUSKnowledgeBaseDocument
      },
      persona: enUSPersona,
      command: enUSCommand,
      subagent: enUSSubagent,
      welcome: enUSWelcome
    },
    messages: {
      errors: enUSErrors,
      success: enUSSuccess,
      validation: enUSValidation
    }
  },
  'ru-RU': {
    core: {
      common: ruRUCommon,
      actions: ruRUActions,
      status: ruRUStatus,
      navigation: ruRUNavigation,
      header: ruRUHeader,
      shared: ruRUShared
    },
    features: {
      chat: ruRUChat,
      extension: ruRUExtension,
      conversation: ruRUConversation,
      'session-management': ruRUSessionManagement,
      tooluse: ruRUToolUse,
      provider: ruRUProvider,
      platform: ruRUPlatform,
      config: ruRUConfig,
      'config-metadata': ruRUConfigMetadata,
      console: ruRUConsole,
      trace: ruRUTrace,
      about: ruRUAbout,
      settings: ruRUSettings,
      auth: ruRUAuth,
      chart: ruRUChart,
      dashboard: ruRUDashboard,
      cron: ruRUCron,
      stats: ruRUStats,
      alkaid: {
        index: ruRUAlkaidIndex,
        'knowledge-base': ruRUAlkaidKnowledgeBase,
        memory: ruRUAlkaidMemory
      },
      'knowledge-base': {
        index: ruRUKnowledgeBaseIndex,
        detail: ruRUKnowledgeBaseDetail,
        document: ruRUKnowledgeBaseDocument
      },
      persona: ruRUPersona,
      command: ruRUCommand,
      subagent: ruRUSubagent,
      welcome: ruRUWelcome
    },
    messages: {
      errors: ruRUErrors,
      success: ruRUSuccess,
      validation: ruRUValidation
    }
  },
  'ja-JP': {
    core: {
      common: jaJPCommon,
      actions: jaJPActions,
      status: jaJPStatus,
      navigation: jaJPNavigation,
      header: jaJPHeader,
      shared: jaJPShared
    },
    features: {
      chat: jaJPChat,
      extension: jaJPExtension,
      conversation: jaJPConversation,
      'session-management': jaJPSessionManagement,
      tooluse: jaJPToolUse,
      provider: jaJPProvider,
      platform: jaJPPlatform,
      config: jaJPConfig,
      'config-metadata': jaJPConfigMetadata,
      console: jaJPConsole,
      trace: jaJPTrace,
      about: jaJPAbout,
      settings: jaJPSettings,
      auth: jaJPAuth,
      chart: jaJPChart,
      dashboard: jaJPDashboard,
      cron: jaJPCron,
      stats: jaJPStats,
      alkaid: {
        index: jaJPAlkaidIndex,
        'knowledge-base': jaJPAlkaidKnowledgeBase,
        memory: jaJPAlkaidMemory
      },
      'knowledge-base': {
        index: jaJPKnowledgeBaseIndex,
        detail: jaJPKnowledgeBaseDetail,
        document: jaJPKnowledgeBaseDocument
      },
      persona: jaJPPersona,
      command: jaJPCommand,
      subagent: jaJPSubagent,
      welcome: jaJPWelcome
    },
    messages: {
      errors: jaJPErrors,
      success: jaJPSuccess,
      validation: jaJPValidation
    }
  }
};

export type TranslationData = typeof translations; 
