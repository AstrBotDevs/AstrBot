const MainRoutes = {
  path: '/main',
  meta: {
    requiresAuth: true
  },
  redirect: '/main/dashboard/default',
  component: () => import('@/layouts/full/FullLayout.vue'),
  children: [
    {
      name: 'Dashboard',
      path: '/',
      component: () => import('@/views/dashboards/default/DefaultDashboard.vue')
    },
    {
      name: 'Extensions',
      path: '/extension',
      component: () => import('@/views/ExtensionPage.vue')
    },
    {
      name: 'ExtensionMarketplace',
      path: '/extension-marketplace',
      component: () => import('@/views/ExtensionPage.vue')
    },
    {
      name: 'Platforms',
      path: '/platforms',
      component: () => import('@/views/PlatformPage.vue')
    },
    {
      name: 'Providers',
      path: '/providers',
      component: () => import('@/views/ProviderPage.vue')
    },
    {
      name: 'ToolUsePage',
      path: '/tool-use',
      component: () => import('@/views/ToolUsePage.vue')
    },
    {
      name: 'Configs',
      path: '/config',
      component: () => import('@/views/ConfigPage.vue')
    },
    {
      name: 'Default',
      path: '/dashboard/default',
      component: () => import('@/views/dashboards/default/DefaultDashboard.vue')
    },    {
      name: 'Conversation',
      path: '/conversation',
      component: () => import('@/views/ConversationPage.vue')
    },
    {
      name: 'SessionManagement',
      path: '/session-management',
      component: () => import('@/views/SessionManagementPage.vue')
    },
    {
      name: 'Console',
      path: '/console',
      component: () => import('@/views/ConsolePage.vue')
    },
    {
      name: 'Alkaid',
      path: '/alkaid',
      component: () => import('@/views/AlkaidPage.vue'),
      children: [
        {
          path: 'knowledge-base',
          name: 'KnowledgeBase',
          component: () => import('@/views/alkaid/KnowledgeBase.vue')
        },
        {
          path: 'long-term-memory',
          name: 'LongTermMemory',
          component: () => import('@/views/alkaid/LongTermMemory.vue')
        },
        {
          path: 'other',
          name: 'OtherFeatures',
          component: () => import('@/views/alkaid/Other.vue')
        }
      ]
    },
    {
      name: 'Chat',
      path: '/chat',
      component: () => import('@/views/ChatPage.vue')
    },
    {
      name: 'Settings',
      path: '/settings',
      component: () => import('@/views/Settings.vue')
    },
    {
      name: 'About',
      path: '/about',
      component: () => import('@/views/AboutPage.vue')
    }
  ]
};

export default MainRoutes;
