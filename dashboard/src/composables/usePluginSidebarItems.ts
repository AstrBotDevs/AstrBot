import { onMounted, reactive, shallowRef, watch } from "vue";
import type { menu } from "@/layouts/full/vertical-sidebar/sidebarItem";
import axios from "@/utils/request";

const DEFAULT_ICON = "mdi-puzzle";
const GROUP_I18N_KEY = "core.navigation.pluginWebui";
const GROUP_ICON = "mdi-puzzle-outline";

interface PluginEntry {
  name: string;
  display_name?: string | null;
  author?: string | null;
  version?: string;
  activated: boolean;
  pages: string[];
}

/** 模块级共享状态，由 useExtensionPage.getExtensions() 更新 */
export const pluginSidebarState = reactive<{
  plugins: PluginEntry[];
}>({
  plugins: [],
});

function buildPluginItems(plugins: PluginEntry[]): menu | null {
  const activeWithPages = plugins.filter((p) => p.activated && Array.isArray(p.pages) && p.pages.length > 0);

  if (activeWithPages.length === 0) return null;

  const children: menu[] = activeWithPages.map((p) => {
    return buildPageItem(p, p.pages[0]);
  });

  return {
    title: GROUP_I18N_KEY,
    icon: GROUP_ICON,
    children,
  };
}

function buildPageItem(p: PluginEntry, page: string): menu {
  const displayName = p.display_name || p.name || "Unknown Plugin";
  return {
    title: page,
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

function buildPluginGroups(plugins: PluginEntry[]): menu[] {
  return plugins
    .filter((p) => p.activated && Array.isArray(p.pages) && p.pages.length > 0)
    .map((p) => {
      const displayName = p.display_name || p.name || "Unknown Plugin";
      return {
        title: displayName,
        icon: GROUP_ICON,
        isRawTitle: true,
        children: p.pages.map((page) => buildPageItem(p, page)),
      };
    });
}

let initialFetched = false;

async function initPluginState() {
  if (initialFetched) return;
  initialFetched = true;
  try {
    const res = await axios.get("/api/plugin/get");
    if (res.data?.status === "ok") {
      pluginSidebarState.plugins = res.data.data ?? [];
    }
  } catch {
    // 静默失败，后续 getExtensions() 会补充
  }
}

export function usePluginSidebarItems() {
  const pluginItems = shallowRef<menu | null>(null);
  const pluginGroups = shallowRef<menu[]>([]);

  function refreshItems() {
    pluginItems.value = buildPluginItems(pluginSidebarState.plugins);
    pluginGroups.value = buildPluginGroups(pluginSidebarState.plugins);
  }

  onMounted(async () => {
    await initPluginState();
    refreshItems();
  });

  watch(
    () => pluginSidebarState.plugins,
    () => {
      refreshItems();
    },
  );

  return { pluginItems, pluginGroups };
}
