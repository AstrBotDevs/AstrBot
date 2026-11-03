// Assembled translations for ja-JP (lazy-loaded per locale)
import jaJPCommon from './core/common.json';
import jaJPActions from './core/actions.json';
import jaJPStatus from './core/status.json';
import jaJPNavigation from './core/navigation.json';
import jaJPHeader from './core/header.json';
import jaJPShared from './core/shared.json';
import jaJPChat from './features/chat.json';
import jaJPExtension from './features/extension.json';
import jaJPConversation from './features/conversation.json';
import jaJPSessionManagement from './features/session-management.json';
import jaJPToolUse from './features/tool-use.json';
import jaJPProvider from './features/provider.json';
import jaJPPlatform from './features/platform.json';
import jaJPConfig from './features/config.json';
import jaJPConfigMetadata from './features/config-metadata.json';
import jaJPConsole from './features/console.json';
import jaJPTrace from './features/trace.json';
import jaJPAbout from './features/about.json';
import jaJPSettings from './features/settings.json';
import jaJPAuth from './features/auth.json';
import jaJPChart from './features/chart.json';
import jaJPDashboard from './features/dashboard.json';
import jaJPCron from './features/cron.json';
import jaJPStats from './features/stats.json';
import jaJPAlkaidIndex from './features/alkaid/index.json';
import jaJPAlkaidKnowledgeBase from './features/alkaid/knowledge-base.json';
import jaJPAlkaidMemory from './features/alkaid/memory.json';
import jaJPKnowledgeBaseIndex from './features/knowledge-base/index.json';
import jaJPKnowledgeBaseDetail from './features/knowledge-base/detail.json';
import jaJPKnowledgeBaseDocument from './features/knowledge-base/document.json';
import jaJPPersona from './features/persona.json';
import jaJPCommand from './features/command.json';
import jaJPWelcome from './features/welcome.json';
import jaJPErrors from './messages/errors.json';
import jaJPSuccess from './messages/success.json';
import jaJPValidation from './messages/validation.json';

export default {
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
      welcome: jaJPWelcome
    },
    messages: {
      errors: jaJPErrors,
      success: jaJPSuccess,
      validation: jaJPValidation
    }
  };
