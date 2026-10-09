// Sub-route (tab) metadata for sidebar entries that host multiple routes, e.g.
// /data (statistics/conversations/logs/trace). Keyed by the parent sidebar
// item's title (an i18n key from sidebarItem.ts). Pages use
// resolveSubItemOrder() from sidebarCustomization.js to honor user-defined
// ordering, and labelKey is always an absolute i18n key resolved with t().
import {
  ChartNoAxesColumnIncreasing,
  Logs,
  MessageSquareText,
  Waypoints,
} from '@lucide/vue';

export const SIDEBAR_SUB_ITEMS = {
  'core.navigation.data': [
    {
      value: 'statistics',
      labelKey: 'core.navigation.dataTabs.statistics',
      icon: ChartNoAxesColumnIncreasing,
      routeName: 'Stats',
    },
    {
      value: 'conversations',
      labelKey: 'core.navigation.dataTabs.conversations',
      icon: MessageSquareText,
      routeName: 'Conversation',
    },
    {
      value: 'logs',
      labelKey: 'core.navigation.dataTabs.logs',
      icon: Logs,
      routeName: 'Console',
    },
    {
      value: 'trace',
      labelKey: 'core.navigation.dataTabs.trace',
      icon: Waypoints,
      routeName: 'Trace',
    },
  ],
  'core.navigation.extension': [
    {
      value: 'installed',
      labelKey: 'core.navigation.extensionTabs.installed',
      icon: 'mdi-puzzle-outline',
      routeName: 'Extensions',
    },
    {
      value: 'skills',
      labelKey: 'core.navigation.extensionTabs.skills',
      icon: 'mdi-lightning-bolt-outline',
      routeName: 'ExtensionSkills',
    },
    {
      value: 'mcp',
      labelKey: 'core.navigation.extensionTabs.mcp',
      icon: 'mdi-server-network',
      routeName: 'ExtensionMcp',
    },
    {
      value: 'components',
      labelKey: 'core.navigation.extensionTabs.components',
      icon: 'mdi-wrench-outline',
      routeName: 'ExtensionComponents',
    },
  ],
  'core.navigation.providers': [
    {
      value: 'chat_completion',
      labelKey: 'features.provider.providers.tabs.chatCompletion',
      icon: 'mdi-message-text',
    },
    {
      value: 'speech_to_text',
      labelKey: 'features.provider.providers.tabs.speechToText',
      icon: 'mdi-microphone-message',
    },
    {
      value: 'text_to_speech',
      labelKey: 'features.provider.providers.tabs.textToSpeech',
      icon: 'mdi-volume-high',
    },
    {
      value: 'embedding',
      labelKey: 'features.provider.providers.tabs.embedding',
      icon: 'mdi-code-json',
    },
    {
      value: 'rerank',
      labelKey: 'features.provider.providers.tabs.rerank',
      icon: 'mdi-compare-vertical',
    },
  ],
};
