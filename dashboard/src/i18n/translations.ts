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
import zhCNLogs from './locales/zh-CN/features/logs.json';
import zhCNTrace from './locales/zh-CN/features/trace.json';
import zhCNAbout from './locales/zh-CN/features/about.json';
import zhCNSettings from './locales/zh-CN/features/settings.json';
import zhCNAuth from './locales/zh-CN/features/auth.json';
import zhCNChart from './locales/zh-CN/features/chart.json';
import zhCNDashboard from './locales/zh-CN/features/dashboard.json';
import zhCNCron from './locales/zh-CN/features/cron.json';
import zhCNStats from './locales/zh-CN/features/stats.json';
import zhCNAlkaidMemory from './locales/zh-CN/features/alkaid/memory.json';
import zhCNKnowledgeBaseIndex from './locales/zh-CN/features/knowledge-base/index.json';
import zhCNKnowledgeBaseDetail from './locales/zh-CN/features/knowledge-base/detail.json';
import zhCNKnowledgeBaseDocument from './locales/zh-CN/features/knowledge-base/document.json';
import zhCNPersona from './locales/zh-CN/features/persona.json';
import zhCNCommand from './locales/zh-CN/features/command.json';
import zhCNSubagent from './locales/zh-CN/features/subagent.json';
import zhCNWelcome from './locales/zh-CN/features/welcome.json';
import zhCNAuthorization from './locales/zh-CN/features/authorization.json';
import zhCNDataFiles from './locales/zh-CN/features/data-files.json';

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
import enUSLogs from './locales/en-US/features/logs.json';
import enUSTrace from './locales/en-US/features/trace.json';
import enUSAbout from './locales/en-US/features/about.json';
import enUSSettings from './locales/en-US/features/settings.json';
import enUSAuth from './locales/en-US/features/auth.json';
import enUSChart from './locales/en-US/features/chart.json';
import enUSDashboard from './locales/en-US/features/dashboard.json';
import enUSCron from './locales/en-US/features/cron.json';
import enUSStats from './locales/en-US/features/stats.json';
import enUSAlkaidMemory from './locales/en-US/features/alkaid/memory.json';
import enUSKnowledgeBaseIndex from './locales/en-US/features/knowledge-base/index.json';
import enUSKnowledgeBaseDetail from './locales/en-US/features/knowledge-base/detail.json';
import enUSKnowledgeBaseDocument from './locales/en-US/features/knowledge-base/document.json';
import enUSPersona from './locales/en-US/features/persona.json';
import enUSCommand from './locales/en-US/features/command.json';
import enUSSubagent from './locales/en-US/features/subagent.json';
import enUSWelcome from './locales/en-US/features/welcome.json';
import enUSAuthorization from './locales/en-US/features/authorization.json';
import enUSDataFiles from './locales/en-US/features/data-files.json';

import enUSErrors from './locales/en-US/messages/errors.json';
import enUSSuccess from './locales/en-US/messages/success.json';
import enUSValidation from './locales/en-US/messages/validation.json';

// 组装翻译对象
export const translations = {
  'zh-CN': {
    core: {
      common: zhCNCommon,
      actions: zhCNActions,
      status: zhCNStatus,
      navigation: zhCNNavigation,
      header: zhCNHeader,
      shared: zhCNShared,
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
      logs: zhCNLogs,
      trace: zhCNTrace,
      about: zhCNAbout,
      settings: zhCNSettings,
      auth: zhCNAuth,
      chart: zhCNChart,
      dashboard: zhCNDashboard,
      cron: zhCNCron,
      stats: zhCNStats,
      alkaid: {
        memory: zhCNAlkaidMemory,
      },
      'knowledge-base': {
        index: zhCNKnowledgeBaseIndex,
        detail: zhCNKnowledgeBaseDetail,
        document: zhCNKnowledgeBaseDocument,
      },
      persona: zhCNPersona,
      command: zhCNCommand,
      subagent: zhCNSubagent,
      welcome: zhCNWelcome,
      authorization: zhCNAuthorization,
      'data-files': zhCNDataFiles,
    },
    messages: {
      errors: zhCNErrors,
      success: zhCNSuccess,
      validation: zhCNValidation,
    },
  },
  'en-US': {
    core: {
      common: enUSCommon,
      actions: enUSActions,
      status: enUSStatus,
      navigation: enUSNavigation,
      header: enUSHeader,
      shared: enUSShared,
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
      logs: enUSLogs,
      trace: enUSTrace,
      about: enUSAbout,
      settings: enUSSettings,
      auth: enUSAuth,
      chart: enUSChart,
      dashboard: enUSDashboard,
      cron: enUSCron,
      stats: enUSStats,
      alkaid: {
        memory: enUSAlkaidMemory,
      },
      'knowledge-base': {
        index: enUSKnowledgeBaseIndex,
        detail: enUSKnowledgeBaseDetail,
        document: enUSKnowledgeBaseDocument,
      },
      persona: enUSPersona,
      command: enUSCommand,
      subagent: enUSSubagent,
      welcome: enUSWelcome,
      authorization: enUSAuthorization,
      'data-files': enUSDataFiles,
    },
    messages: {
      errors: enUSErrors,
      success: enUSSuccess,
      validation: enUSValidation,
    },
  },
};

export type TranslationData = typeof translations;
