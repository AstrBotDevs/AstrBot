export interface menu {
  header?: string;
  title?: string;
  icon?: string;
  to?: string;
  divider?: boolean;
  chip?: string;
  chipColor?: string;
  chipVariant?: string;
  chipIcon?: string;
  children?: menu[];
  disabled?: boolean;
  type?: string;
  subCaption?: string;
}

// 注意：这个文件现在包含i18n键值而不是直接的文本
// 在组件中使用时需要通过t()函数进行翻译
// 所有键名都使用 core.navigation.* 格式
const sidebarItem: menu[] = [
  {
    title: 'core.navigation.welcome',
    icon: 'mdi-hand-wave-outline',
    to: '/welcome',
  },
  {
    title: 'core.navigation.platforms',
    icon: 'mdi-robot',
    to: '/platforms',
  },
  {
    title: 'core.navigation.providers',
    icon: 'mdi-creation',
    to: '/providers',
  },
  {
    title: 'core.navigation.config',
    icon: 'mdi-cog',
    to: '/config',
  },
  {
    title: 'core.navigation.extension',
    icon: 'mdi-puzzle',
    to: '/extension#installed',
    children: [
      {
        title: 'core.navigation.extensionTabs.installed',
        icon: 'mdi-puzzle',
        to: '/extension#installed'
      },
      {
        title: 'core.navigation.extensionTabs.market',
        icon: 'mdi-store',
        to: '/extension#market'
      },
      {
        title: 'core.navigation.extensionTabs.mcp',
        icon: 'mdi-server-network',
        to: '/extension#mcp'
      },
      {
        title: 'core.navigation.extensionTabs.skills',
        icon: 'mdi-lightning-bolt',
        to: '/extension#skills'
      },
      {
        title: 'core.navigation.extensionTabs.components',
        icon: 'mdi-wrench',
        to: '/extension#components'
      }
    ]
  },
  {
    title: 'core.navigation.knowledgeBase',
    icon: 'mdi-book-open-variant',
    to: '/knowledge-base',
  },
  {
    title: 'core.navigation.persona',
    icon: 'mdi-heart',
    to: '/persona'
  },
  {
    title: 'core.navigation.groups.more',
    icon: 'mdi-dots-horizontal',
    children: [
      {
        title: 'core.navigation.conversation',
        icon: 'mdi-database',
        to: '/conversation'
      },
      {
        title: 'core.navigation.sessionManagement',
        icon: 'mdi-pencil-ruler',
        to: '/session-management'
      },
      {
        title: 'core.navigation.cron',
        icon: 'mdi-clock-outline',
        to: '/cron'
      },
      {
        title: 'core.navigation.subagent',
        icon: 'mdi-vector-link',
        to: '/subagent'
      },
      {
        title: 'core.navigation.dashboard',
        icon: 'mdi-view-dashboard',
        to: '/dashboard/default'
      },
      {
        title: 'core.navigation.console',
        icon: 'mdi-console',
        to: '/console'
      },
      {
        title: 'core.navigation.trace',
        icon: 'mdi-timeline-text-outline',
        to: '/trace'
      },
    ]
  }
  // {
  //   title: 'Project ATRI',
  //   icon: 'mdi-grain',
  //   to: '/project-atri'
  // },
];

export default sidebarItem;
