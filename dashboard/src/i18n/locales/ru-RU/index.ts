// Assembled translations for ru-RU (lazy-loaded per locale)
import ruRUCommon from './core/common.json';
import ruRUActions from './core/actions.json';
import ruRUStatus from './core/status.json';
import ruRUNavigation from './core/navigation.json';
import ruRUHeader from './core/header.json';
import ruRUShared from './core/shared.json';
import ruRUChat from './features/chat.json';
import ruRUExtension from './features/extension.json';
import ruRUConversation from './features/conversation.json';
import ruRUSessionManagement from './features/session-management.json';
import ruRUToolUse from './features/tool-use.json';
import ruRUProvider from './features/provider.json';
import ruRUPlatform from './features/platform.json';
import ruRUConfig from './features/config.json';
import ruRUConfigMetadata from './features/config-metadata.json';
import ruRUConsole from './features/console.json';
import ruRUTrace from './features/trace.json';
import ruRUAbout from './features/about.json';
import ruRUSettings from './features/settings.json';
import ruRUAuth from './features/auth.json';
import ruRUChart from './features/chart.json';
import ruRUDashboard from './features/dashboard.json';
import ruRUCron from './features/cron.json';
import ruRUStats from './features/stats.json';
import ruRUAlkaidIndex from './features/alkaid/index.json';
import ruRUAlkaidKnowledgeBase from './features/alkaid/knowledge-base.json';
import ruRUAlkaidMemory from './features/alkaid/memory.json';
import ruRUKnowledgeBaseIndex from './features/knowledge-base/index.json';
import ruRUKnowledgeBaseDetail from './features/knowledge-base/detail.json';
import ruRUKnowledgeBaseDocument from './features/knowledge-base/document.json';
import ruRUPersona from './features/persona.json';
import ruRUCommand from './features/command.json';
import ruRUSubagent from './features/subagent.json';
import ruRUWelcome from './features/welcome.json';
import ruRUErrors from './messages/errors.json';
import ruRUSuccess from './messages/success.json';
import ruRUValidation from './messages/validation.json';

export default {
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
  };
