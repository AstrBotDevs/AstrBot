import {
  EXTENSION_DETAILS_ROUTE_NAME,
  EXTENSION_ROUTE_NAME
} from './routeConstants.mjs';
import type { RouteLocationNormalized } from 'vue-router';

const redirectToDataTab = (name: string) => (to: RouteLocationNormalized) => ({
  name,
  query: to.query,
  hash: to.hash
});

const MainRoutes = {
  path: '/main',
  meta: {
    requiresAuth: true
  },
  redirect: '/welcome',
  component: () => import('@/layouts/full/FullLayout.vue'),
  children: [
    {
      name: 'MainPage',
      path: '/',
      component: () => import('@/views/WelcomePage.vue')
    },
    {
      name: 'Welcome',
      path: '/welcome',
      component: () => import('@/views/WelcomePage.vue')
    },
    {
      path: '/extension',
      component: () => import('@/views/extension/PluginWorkspacePage.vue'),
      children: [
        {
          path: '',
          redirect: (to: RouteLocationNormalized) => {
            const legacyTab = String(to.hash || '').replace(/^#/, '');
            const routeNames: Record<string, string> = {
              market: 'ExtensionMarketplace',
              mcp: 'ExtensionMcp',
              skills: 'ExtensionSkills',
              components: 'ExtensionComponents'
            };
            return {
              name: routeNames[legacyTab] || EXTENSION_ROUTE_NAME,
              query: to.query
            };
          }
        },
        {
          name: EXTENSION_ROUTE_NAME,
          path: 'plugins',
          component: () => import('@/views/ExtensionPage.vue'),
          props: { initialTab: 'installed' },
          meta: { extensionTab: 'installed', pluginView: 'installed' }
        },
        {
          name: 'ExtensionMarketplace',
          path: 'plugins/market',
          component: () => import('@/views/ExtensionPage.vue'),
          props: { initialTab: 'market' },
          meta: { extensionTab: 'installed', pluginView: 'market' }
        },
        {
          name: 'ExtensionMcp',
          path: 'mcp',
          component: () => import('@/views/extension/McpServersPage.vue'),
          meta: { extensionTab: 'mcp' }
        },
        {
          name: 'ExtensionSkills',
          path: 'skills',
          component: () => import('@/views/extension/SkillsPage.vue'),
          meta: { extensionTab: 'skills' }
        },
        {
          name: 'ExtensionComponents',
          path: 'components',
          component: () => import('@/views/extension/ComponentsPage.vue'),
          meta: { extensionTab: 'components' }
        },
        {
          name: EXTENSION_DETAILS_ROUTE_NAME,
          path: 'plugins/:pluginId',
          component: () => import('@/views/ExtensionPage.vue'),
          props: { initialTab: 'installed' },
          meta: { extensionTab: 'installed', pluginView: 'installed' }
        },
        {
          name: 'ExtensionMarketDetails',
          path: 'plugins/market/:pluginId',
          component: () => import('@/views/ExtensionPage.vue'),
          props: { initialTab: 'market' },
          meta: { extensionTab: 'installed', pluginView: 'market' }
        }
      ]
    },
    {
      name: 'PluginPage',
      path: '/plugin-page/:pluginName/:pageName',
      component: () => import('@/views/PluginPagePage.vue')
    },
    {
      path: '/extension/:pluginId',
      redirect: (to: RouteLocationNormalized) => ({
        name:
          String(to.hash || '').replace(/^#/, '') === 'market'
            ? 'ExtensionMarketDetails'
            : EXTENSION_DETAILS_ROUTE_NAME,
        params: { pluginId: to.params.pluginId },
        query: to.query,
        hash: to.hash === '#plugin-components' ? to.hash : ''
      })
    },
    {
      path: '/extension/market',
      redirect: { name: 'ExtensionMarketplace' }
    },
    {
      path: '/extension/market/:pluginId',
      redirect: (to: RouteLocationNormalized) => ({
        name: 'ExtensionMarketDetails',
        params: { pluginId: to.params.pluginId },
        query: to.query
      })
    },
    {
      path: '/extension-marketplace',
      redirect: { name: 'ExtensionMarketplace' }
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
      path: '/normal',
      redirect: '/config'
    },
    {
      path: '/system',
      redirect: '/settings#system-config'
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
      name: 'Data',
      path: '/data',
      component: () => import('@/views/DataPage.vue'),
      redirect: redirectToDataTab('Stats'),
      children: [
        {
          name: 'Stats',
          path: 'statistics',
          component: () => import('@/views/stats/StatsPage.vue'),
          meta: { dataTab: 'statistics' }
        },
        {
          name: 'Conversation',
          path: 'conversations',
          component: () => import('@/views/conversation/ConversationWorkspacePage.vue'),
          meta: { dataTab: 'conversations' }
        },
        {
          name: 'ConversationLegacy',
          path: 'conversations/legacy',
          component: () => import('@/views/conversation/LegacyConversationPage.vue'),
          meta: { dataTab: 'conversations' }
        },
        {
          name: 'Console',
          path: 'logs',
          component: () => import('@/views/ConsolePage.vue'),
          meta: { dataTab: 'logs' }
        },
        {
          name: 'Trace',
          path: 'trace',
          component: () => import('@/views/TracePage.vue'),
          meta: { dataTab: 'trace' }
        }
      ]
    },
    {
      path: '/dashboard/default',
      redirect: redirectToDataTab('Stats')
    },
    {
      path: '/conversation',
      redirect: redirectToDataTab('Conversation')
    },
    {
      path: '/console',
      redirect: redirectToDataTab('Console')
    },
    {
      path: '/trace',
      redirect: redirectToDataTab('Trace')
    },
    {
      path: '/observability',
      redirect: redirectToDataTab('Stats')
    },
    {
      name: 'SubAgent',
      path: '/subagent',
      component: () => import('@/views/SubAgentPage.vue')
    },
    {
      name: 'CronJobs',
      path: '/cron',
      component: () => import('@/views/CronJobPage.vue')
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
