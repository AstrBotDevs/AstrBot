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
      component: () => import('@/views/ExtensionMarketplace.vue')
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
    },
    {
      name: 'Conversation',
      path: '/conversation',
      component: () => import('@/views/ConversationPage.vue')
    },
    {
      name: 'Console',
      path: '/console',
      component: () => import('@/views/ConsolePage.vue')
    },
    {
      name: 'Project ATRI',
      path: '/project-atri',
      component: () => import('@/views/ATRIProject.vue')
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
