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
// 在组件中使用时需要通过$t()函数进行翻译
const sidebarItem: menu[] = [
  {
    title: 'sidebar.dashboard',
    icon: 'mdi-view-dashboard',
    to: '/dashboard/default'
  },
  {
    title: 'sidebar.platforms',
    icon: 'mdi-message-processing',
    to: '/platforms',
  },
  {
    title: 'sidebar.providers',
    icon: 'mdi-creation',
    to: '/providers',
  },
  {
    title: 'sidebar.toolUse',
    icon: 'mdi-function-variant',
    to: '/tool-use'
  },
  {
    title: 'sidebar.config',
    icon: 'mdi-cog',
    to: '/config',
  },
  {
    title: 'sidebar.extension',
    icon: 'mdi-puzzle',
    to: '/extension'
  },
  {
    title: 'sidebar.chat',
    icon: 'mdi-chat',
    to: '/chat'
  },
  {
    title: 'sidebar.conversation',
    icon: 'mdi-database',
    to: '/conversation'
  },
  {
    title: 'sidebar.console',
    icon: 'mdi-console',
    to: '/console'
  },
  {
    title: 'sidebar.alkaid',
    icon: 'mdi-test-tube',
    to: '/alkaid'
  },
  {
    title: 'sidebar.about',
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
