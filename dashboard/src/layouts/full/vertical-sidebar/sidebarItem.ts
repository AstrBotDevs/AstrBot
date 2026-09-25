import { markRaw, type Component } from 'vue';
import {
  BookOpen,
  Bot,
  Clock3,
  Database,
  Ellipsis,
  Hand,
  Heart,
  PencilRuler,
  Puzzle,
  Settings,
  Sparkles,
  Workflow,
} from '@lucide/vue';

export interface menu {
  header?: string;
  title?: string;
  icon?: string | Component;
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
  isRawTitle?: boolean;
}

export const MORE_GROUP_KEY = 'core.navigation.groups.more';

// 注意：这个文件现在包含i18n键值而不是直接的文本
// 在组件中使用时需要通过t()函数进行翻译
// 所有键名都使用 core.navigation.* 格式
const sidebarItem: menu[] = [
  {
    title: 'core.navigation.welcome',
    icon: markRaw(Hand),
    to: '/welcome',
  },
  {
    title: 'core.navigation.platforms',
    icon: markRaw(Bot),
    to: '/platforms',
  },
  {
    title: 'core.navigation.providers',
    icon: markRaw(Sparkles),
    to: '/providers',
  },
  {
    title: 'core.navigation.extension',
    icon: markRaw(Puzzle),
    to: '/extension',
  },
  {
    title: 'core.navigation.config',
    icon: markRaw(Settings),
    to: '/config',
  },
  {
    title: 'core.navigation.knowledgeBase',
    icon: markRaw(BookOpen),
    to: '/knowledge-base',
  },
  {
    title: 'core.navigation.persona',
    icon: markRaw(Heart),
    to: '/persona'
  },
  {
    title: 'core.navigation.data',
    icon: markRaw(Database),
    to: '/data'
  },
  {
    title: 'core.navigation.groups.more',
    icon: markRaw(Ellipsis),
    children: [
      {
        title: 'core.navigation.sessionManagement',
        icon: markRaw(PencilRuler),
        to: '/session-management'
      },
      {
        title: 'core.navigation.cron',
        icon: markRaw(Clock3),
        to: '/cron'
      },
      {
        title: 'core.navigation.subagent',
        icon: markRaw(Workflow),
        to: '/subagent'
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
