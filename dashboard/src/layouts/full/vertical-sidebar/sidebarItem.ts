import { markRaw, type Component } from 'vue';
import {
  BookSearch,
  Bot,
  Box,
  Clock3,
  Database,
  Heart,
  PencilRuler,
  Puzzle,
  SlidersHorizontal,
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
  collapsible?: boolean;
  pluginInfo?: {
    id: string;
    displayName?: string;
    author?: string | null;
    version?: string;
  };
  groupToggle?: boolean;
}

export const SYSTEM_GROUP_KEY = 'core.navigation.groups.system';
export const EXTENSION_GROUP_KEY = 'core.navigation.groups.extension';

// Kept for the legacy sidebar customization storage; the default layout no
// longer uses a collapsible "more" group.
export const MORE_GROUP_KEY = 'core.navigation.groups.more';

// 注意：这个文件现在包含i18n键值而不是直接的文本
// 在组件中使用时需要通过t()函数进行翻译
// 所有键名都使用 core.navigation.* 格式
const sidebarItem: menu[] = [
  {
    header: SYSTEM_GROUP_KEY,
  },
  {
    title: 'core.navigation.platforms',
    icon: markRaw(Bot),
    to: '/platforms',
  },
  {
    title: 'core.navigation.providers',
    icon: markRaw(Box),
    to: '/providers',
  },
  {
    title: 'core.navigation.extension',
    icon: markRaw(Puzzle),
    to: '/extension',
  },
  {
    title: 'core.navigation.config',
    icon: markRaw(SlidersHorizontal),
    to: '/config',
  },
  {
    title: 'core.navigation.data',
    icon: markRaw(Database),
    to: '/data'
  },
  {
    title: 'core.navigation.sessionManagement',
    icon: markRaw(PencilRuler),
    to: '/session-management'
  },
  {
    header: EXTENSION_GROUP_KEY,
    collapsible: true,
    groupToggle: true,
  },
  {
    title: 'core.navigation.persona',
    icon: markRaw(Heart),
    to: '/persona'
  },
  {
    title: 'core.navigation.knowledgeBase',
    icon: markRaw(BookSearch),
    to: '/knowledge-base',
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
];

export default sidebarItem;
