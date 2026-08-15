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
      path: '/normal',
      redirect: '/config',
    },
    {
      path: '/system',
      redirect: '/settings#system-config',
    },
    {
      name: 'Stats',
      path: '/dashboard/default',
      component: () => import('@/views/stats/StatsPage.vue'),
    },
    {
      name: 'Conversation',
      path: '/conversation',
      component: () => import('@/views/ConversationPage.vue'),
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
      name: 'Console',
      path: '/console',
      component: () => import('@/views/ConsolePage.vue'),
    },
    {
      name: 'Trace',
      path: '/trace',
      component: () => import('@/views/TracePage.vue'),
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
