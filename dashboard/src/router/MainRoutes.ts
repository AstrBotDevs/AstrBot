const MainRoutes = {
  path: '/main',
  meta: {
    requiresAuth: true
  },
  redirect: '/main/platforms',
  component: () => import('@/layouts/full/FullLayout.vue'),
  children: [
    {
      name: 'MainPage',
      path: '/',
      component: () => import('@/views/PlatformPage.vue')
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
      name: 'Configs',
      path: '/config',
      component: () => import('@/views/ConfigPage.vue')
    },
    {
      name: 'Default',
      path: '/dashboard/default',
      component: () => import('@/views/dashboards/default/DefaultDashboard.vue')
    },
    {
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
      name: 'Persona',
      path: '/persona',
      component: () => import('@/views/PersonaPage.vue')
    },
    {
      name: 'Console',
      path: '/console',
      component: () => import('@/views/ConsolePage.vue')
    },
    {
      name: 'NativeKnowledgeBase',
      path: '/knowledge-base',
      component: () => import('@/views/knowledge-base/index.vue'),
      children: [
        {
          path: '',
          name: 'NativeKBList',
          component: () => import('@/views/knowledge-base/KBList.vue')
        },
        {
          path: ':kbId',
          name: 'NativeKBDetail',
          component: () => import('@/views/knowledge-base/KBDetail.vue'),
          props: true
        },
        {
          path: ':kbId/document/:docId',
          name: 'NativeDocumentDetail',
          component: () => import('@/views/knowledge-base/DocumentDetail.vue'),
          props: true
        }
      ]
    },

    // 旧版本的知识库路由
    {
      name: 'KnowledgeBase',
      path: '/alkaid/knowledge-base',
      component: () => import('@/views/alkaid/KnowledgeBase.vue'),
    },
    // {
    //   name: 'Alkaid',
    //   path: '/alkaid',
    //   component: () => import('@/views/AlkaidPage.vue'),
    //   children: [
    //     {
    //       path: 'knowledge-base',
    //       name: 'KnowledgeBase',
    //       component: () => import('@/views/alkaid/KnowledgeBase.vue')
    //     },
    //     {
    //       path: 'long-term-memory',
    //       name: 'LongTermMemory',
    //       component: () => import('@/views/alkaid/LongTermMemory.vue')
    //     },
    //     {
    //       path: 'other',
    //       name: 'OtherFeatures',
    //       component: () => import('@/views/alkaid/Other.vue')
    //     }
    //   ]
    // },
    {
      name: 'Chat',
      path: '/chat',
      component: () => import('@/views/ChatPage.vue'),
      children: [
        {
          path: ':conversationId',
          name: 'ChatDetail',
          component: () => import('@/views/ChatPage.vue'),
          props: true
        }
      ]
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
