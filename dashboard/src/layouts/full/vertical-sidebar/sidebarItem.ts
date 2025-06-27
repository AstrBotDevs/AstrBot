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
    title: 'core.navigation.dashboard',
    icon: 'mdi-view-dashboard',
    to: '/dashboard/default'
  },
  {
    title: 'core.navigation.platforms',
    icon: 'mdi-message-processing',
    to: '/platforms',
  },
  {
    title: 'core.navigation.providers',
    icon: 'mdi-creation',
    to: '/providers',
  },
  {
    title: 'core.navigation.toolUse',
    icon: 'mdi-function-variant',
    to: '/tool-use'
  },
  {
    title: 'core.navigation.config',
    icon: 'mdi-cog',
    to: '/config',
  },
  {
    title: 'core.navigation.extension',
    icon: 'mdi-puzzle',
    to: '/extension'
  },
  {
    title: 'core.navigation.chat',
    icon: 'mdi-chat',
    to: '/chat'
  },
  {
    title: 'core.navigation.conversation',
    icon: 'mdi-database',
    to: '/conversation'
  },
  {
    title: 'core.navigation.sessionManagement',
    icon: 'mdi-account-group',
    to: '/session-management'
  },
  {
    title: 'core.navigation.console',

    icon: 'mdi-console',
    to: '/console'
  },
  {
    title: 'core.navigation.alkaid',
    icon: 'mdi-test-tube',
    to: '/alkaid'
  },
  {
    title: 'core.navigation.about',
    icon: 'mdi-information',
    to: '/about'
  },
  // {
  //   title: 'Project ATRI',
  //   icon: 'mdi-grain',
  //   to: '/project-atri'
  // },
];

export default sidebarItem;
