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
  isRawTitle?: boolean;
}

export const MORE_GROUP_KEY = "core.navigation.groups.more";

// Navigation labels are translated by the sidebar using these i18n keys.
const sidebarItem: menu[] = [
  {
    title: "core.navigation.welcome",
    icon: "mdi-hand-wave-outline",
    to: "/welcome",
  },
  {
    title: "core.navigation.platforms",
    icon: "mdi-robot",
    to: "/platforms",
  },
  {
    title: "core.navigation.providers",
    icon: "mdi-creation",
    to: "/providers",
  },
  {
    title: "core.navigation.config",
    icon: "mdi-cog",
    to: "/config#normal",
    children: [
      {
        title: "core.navigation.configTabs.normal",
        icon: "mdi-cog",
        to: "/config#normal",
      },
      {
        title: "core.navigation.configTabs.system",
        icon: "mdi-cog-outline",
        to: "/config#system",
      },
    ],
  },
  {
    title: "core.navigation.extension",
    icon: "mdi-puzzle",
    to: "/extension",
  },
  {
    title: "core.navigation.knowledgeBase",
    icon: "mdi-book-open-variant",
    to: "/knowledge-base",
  },
  {
    title: "core.navigation.persona",
    icon: "mdi-heart",
    to: "/persona",
  },
  {
    title: "core.navigation.data",
    icon: "mdi-database",
    to: "/data",
  },
  {
    title: MORE_GROUP_KEY,
    icon: "mdi-dots-horizontal",
    children: [
      {
        title: "core.navigation.sessionManagement",
        icon: "mdi-pencil-ruler",
        to: "/session-management",
      },
      {
        title: "core.navigation.cron",
        icon: "mdi-clock-outline",
        to: "/cron",
      },
      {
        title: "core.navigation.subagent",
        icon: "mdi-vector-link",
        to: "/subagent",
      },
    ],
  },
];

export default sidebarItem;
