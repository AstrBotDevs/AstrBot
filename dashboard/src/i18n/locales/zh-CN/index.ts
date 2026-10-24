// Assembled translations for zh-CN (lazy-loaded per locale)
import zhCNCommon from './core/common.json';
import zhCNActions from './core/actions.json';
import zhCNStatus from './core/status.json';
import zhCNNavigation from './core/navigation.json';
import zhCNHeader from './core/header.json';
import zhCNShared from './core/shared.json';
import zhCNChat from './features/chat.json';
import zhCNExtension from './features/extension.json';
import zhCNConversation from './features/conversation.json';
import zhCNSessionManagement from './features/session-management.json';
import zhCNToolUse from './features/tool-use.json';
import zhCNProvider from './features/provider.json';
import zhCNPlatform from './features/platform.json';
import zhCNConfig from './features/config.json';
import zhCNConfigMetadata from './features/config-metadata.json';
import zhCNConsole from './features/console.json';
import zhCNTrace from './features/trace.json';
import zhCNAbout from './features/about.json';
import zhCNSettings from './features/settings.json';
import zhCNAuth from './features/auth.json';
import zhCNChart from './features/chart.json';
import zhCNDashboard from './features/dashboard.json';
import zhCNCron from './features/cron.json';
import zhCNStats from './features/stats.json';
import zhCNAlkaidIndex from './features/alkaid/index.json';
import zhCNAlkaidKnowledgeBase from './features/alkaid/knowledge-base.json';
import zhCNAlkaidMemory from './features/alkaid/memory.json';
import zhCNKnowledgeBaseIndex from './features/knowledge-base/index.json';
import zhCNKnowledgeBaseDetail from './features/knowledge-base/detail.json';
import zhCNKnowledgeBaseDocument from './features/knowledge-base/document.json';
import zhCNPersona from './features/persona.json';
import zhCNCommand from './features/command.json';
import zhCNWelcome from './features/welcome.json';
import zhCNErrors from './messages/errors.json';
import zhCNSuccess from './messages/success.json';
import zhCNValidation from './messages/validation.json';

export default {
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
      welcome: zhCNWelcome
    },
    messages: {
      errors: zhCNErrors,
      success: zhCNSuccess,
      validation: zhCNValidation
    }
  };
