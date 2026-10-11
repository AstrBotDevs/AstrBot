import { reactive, shallowRef, onMounted, watch } from "vue";
import { pluginApi } from "@/api/v1";
import { usePluginI18n } from "@/utils/pluginI18n";
import type { menu } from "@/layouts/full/vertical-sidebar/sidebarItem";

const DEFAULT_ICON = "mdi-puzzle";
const GROUP_I18N_KEY = "core.navigation.pluginView";
const GROUP_ICON = "mdi-puzzle-outline";

interface PluginEntry {
  name: string;
  display_name?: string | null;
  author?: string | null;
  version?: string;
  activated: boolean;
  pages: string[];
  i18n?: Record<string, Record<string, unknown>>;
}

type ViewTitleResolver = ReturnType<typeof usePluginI18n>["pluginViewTitle"];

/** 模块级共享状态，由 useExtensionPage.getExtensions() 更新 */
export const pluginSidebarState = reactive<{
  plugins: PluginEntry[];
}>({
  plugins: [],
});

function buildPluginItems(
  plugins: PluginEntry[],
  viewTitle: ViewTitleResolver,
): menu | null {
  const activeWithPages = plugins.filter(
    (p) => p.activated && Array.isArray(p.pages) && p.pages.length > 0,
  );

  if (activeWithPages.length === 0) return null;

  const children: menu[] = activeWithPages.map((p) => {
    return buildPageItem(p, p.pages[0], viewTitle);
  });

  return {
    title: GROUP_I18N_KEY,
    icon: GROUP_ICON,
    children,
  };
}

function buildPageItem(
  p: PluginEntry,
  page: string,
  viewTitle: ViewTitleResolver,
): menu {
  const displayName = p.display_name || p.name || "Unknown Plugin";
  return {
    title: viewTitle(p, page),
    icon: DEFAULT_ICON,
    to: `/plugin-view/${encodeURIComponent(p.name)}/${encodeURIComponent(page)}`,
    isRawTitle: true,
    pluginInfo: {
      id: p.name,
      displayName,
      author: p.author,
      version: p.version,
    },
  };
}

function buildPluginGroups(
  plugins: PluginEntry[],
  viewTitle: ViewTitleResolver,
): menu[] {
  return plugins
    .filter((p) => p.activated && Array.isArray(p.pages) && p.pages.length > 0)
    .map((p) => {
      const displayName = p.display_name || p.name || "Unknown Plugin";
      return {
        title: displayName,
        icon: GROUP_ICON,
        isRawTitle: true,
        children: p.pages.map((page) => buildPageItem(p, page, viewTitle)),
      };
    });
}

let initialFetched = false;

async function initPluginState() {
  if (initialFetched) return;
  initialFetched = true;
  try {
    const res = await pluginApi.list();
    if (res.data?.status === "ok") {
      pluginSidebarState.plugins = res.data.data ?? [];
    }
  } catch {
    // 静默失败，后续 getExtensions() 会补充
  }
}

export function usePluginSidebarItems() {
  const { locale, pluginViewTitle } = usePluginI18n();
  const pluginItems = shallowRef<menu | null>(null);
  const pluginGroups = shallowRef<menu[]>([]);

  function refreshItems() {
    pluginItems.value = buildPluginItems(pluginSidebarState.plugins, pluginViewTitle);
    pluginGroups.value = buildPluginGroups(pluginSidebarState.plugins, pluginViewTitle);
  }

  onMounted(async () => {
    await initPluginState();
    refreshItems();
  });

  watch(
    [() => pluginSidebarState.plugins, locale],
    () => {
      refreshItems();
    },
  );

  return { pluginItems, pluginGroups };
}
