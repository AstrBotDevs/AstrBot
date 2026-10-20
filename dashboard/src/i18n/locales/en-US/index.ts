// Assembled translations for en-US (lazy-loaded per locale)
import enUSCommon from './core/common.json';
import enUSActions from './core/actions.json';
import enUSStatus from './core/status.json';
import enUSNavigation from './core/navigation.json';
import enUSHeader from './core/header.json';
import enUSShared from './core/shared.json';
import enUSChat from './features/chat.json';
import enUSExtension from './features/extension.json';
import enUSConversation from './features/conversation.json';
import enUSSessionManagement from './features/session-management.json';
import enUSToolUse from './features/tool-use.json';
import enUSProvider from './features/provider.json';
import enUSPlatform from './features/platform.json';
import enUSConfig from './features/config.json';
import enUSConfigMetadata from './features/config-metadata.json';
import enUSConsole from './features/console.json';
import enUSTrace from './features/trace.json';
import enUSAbout from './features/about.json';
import enUSSettings from './features/settings.json';
import enUSAuth from './features/auth.json';
import enUSChart from './features/chart.json';
import enUSDashboard from './features/dashboard.json';
import enUSCron from './features/cron.json';
import enUSStats from './features/stats.json';
import enUSAlkaidIndex from './features/alkaid/index.json';
import enUSAlkaidKnowledgeBase from './features/alkaid/knowledge-base.json';
import enUSAlkaidMemory from './features/alkaid/memory.json';
import enUSKnowledgeBaseIndex from './features/knowledge-base/index.json';
import enUSKnowledgeBaseDetail from './features/knowledge-base/detail.json';
import enUSKnowledgeBaseDocument from './features/knowledge-base/document.json';
import enUSPersona from './features/persona.json';
import enUSCommand from './features/command.json';
import enUSSubagent from './features/subagent.json';
import enUSWelcome from './features/welcome.json';
import enUSErrors from './messages/errors.json';
import enUSSuccess from './messages/success.json';
import enUSValidation from './messages/validation.json';

export default {
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
  };
