import type { RouteLocationGeneric } from 'vue-router';
import {
  EXTENSION_DETAILS_ROUTE_NAME,
  EXTENSION_ROUTE_NAME,
} from './routeConstants';

const MainRoutes = {
  path: '/main',
  meta: {
    requiresAuth: true,
  },
  redirect: '/welcome',
  component: () => import('@/layouts/full/FullLayout.vue'),
  children: [
    {
      name: 'MainPage',
      path: '/',
      component: () => import('@/views/WelcomePage.vue'),
    },
    {
      name: 'Welcome',
      path: '/welcome',
      component: () => import('@/views/WelcomePage.vue'),
    },
    {
      name: EXTENSION_ROUTE_NAME,
      path: '/extension',
      component: () => import('@/views/ExtensionPage.vue'),
    },
    {
      name: 'PluginPageHost',
      path: '/extension/:extensionId/pages/:pageId',
      component: () => import('@/views/extension/PluginPageHost.vue'),
    },
    {
      name: EXTENSION_DETAILS_ROUTE_NAME,
      path: '/extension/:pluginId',
      component: () => import('@/views/ExtensionPage.vue'),
    },
    {
      name: 'ExtensionMarketplace',
      path: '/extension-marketplace',
      component: () => import('@/views/ExtensionPage.vue'),
    },
    {
      name: 'Platforms',
      path: '/platforms',
      component: () => import('@/views/PlatformPage.vue'),
    },
    {
      name: 'Providers',
      path: '/providers',
      component: () => import('@/views/ProviderPage.vue'),
    },
    {
      name: 'Configs',
      path: '/config',
      component: () => import('@/views/ConfigPage.vue'),
    },
    {
      name: 'DashboardWorkspace',
      path: '/dashboard',
      component: () => import('@/views/DashboardWorkspacePage.vue'),
      redirect: (to: RouteLocationGeneric) => ({
        name: 'Stats',
        query: to.query,
        hash: to.hash,
      }),
      children: [
        {
          name: 'Stats',
          path: 'statistics',
          component: () => import('@/views/stats/StatsPage.vue'),
          meta: { dataTab: 'statistics' },
        },
        {
          name: 'Conversation',
          path: 'conversations',
          component: () =>
            import('@/views/conversation/ConversationWorkspacePage.vue'),
          meta: { dataTab: 'conversations' },
        },
        {
          name: 'Logs',
          path: 'logs',
          component: () => import('@/views/LogsPage.vue'),
          meta: { dataTab: 'logs' },
        },
        {
          name: 'Trace',
          path: 'trace',
          component: () => import('@/views/TracePage.vue'),
          meta: { dataTab: 'trace' },
        },
      ],
    },
    {
      name: 'SessionManagement',
      path: '/session-management',
      component: () => import('@/views/SessionManagementPage.vue'),
    },
    {
      name: 'Authorization',
      path: '/authorization',
      component: () => import('@/views/AuthorizationPage.vue'),
    },
    {
      name: 'Persona',
      path: '/persona',
      component: () => import('@/views/PersonaPage.vue'),
    },
    {
      name: 'SubAgent',
      path: '/subagent',
      component: () => import('@/views/SubAgentPage.vue'),
    },
    {
      name: 'CronJobs',
      path: '/cron',
      component: () => import('@/views/CronJobPage.vue'),
    },
    {
      name: 'DataFiles',
      path: '/data',
      component: () => import('@/views/DataFilesPage.vue'),
    },
    {
      name: 'NativeKnowledgeBase',
      path: '/knowledge-base',
      component: () => import('@/views/knowledge-base/index.vue'),
      children: [
        {
          path: '',
          name: 'NativeKBList',
          component: () => import('@/views/knowledge-base/KBList.vue'),
        },
        {
          path: ':kbId',
          name: 'NativeKBDetail',
          component: () => import('@/views/knowledge-base/KBDetail.vue'),
          props: true,
        },
        {
          path: ':kbId/document/:docId',
          name: 'NativeDocumentDetail',
          component: () => import('@/views/knowledge-base/DocumentDetail.vue'),
          props: true,
        },
      ],
    },
    {
      name: 'Alkaid',
      path: '/alkaid',
      component: () => import('@/views/AlkaidPage.vue'),
      children: [
        {
          path: '',
          redirect: '/alkaid/long-term-memory',
        },
        {
          name: 'AlkaidLongTermMemory',
          path: 'long-term-memory',
          component: () => import('@/views/alkaid/LongTermMemoryPage.vue'),
        },
      ],
    },

    {
      name: 'Chat',
      path: '/chat',
      component: () => import('@/views/ChatPage.vue'),
      children: [
        {
          path: ':conversationId',
          name: 'ChatDetail',
          component: () => import('@/views/ChatPage.vue'),
          props: true,
        },
      ],
    },
    {
      name: 'Settings',
      path: '/settings',
      component: () => import('@/views/Settings.vue'),
    },
    {
      name: 'About',
      path: '/about',
      component: () => import('@/views/AboutPage.vue'),
    },
  ],
};

export default MainRoutes;
