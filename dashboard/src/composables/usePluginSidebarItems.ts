import { reactive, shallowRef, onMounted, watch } from "vue";
import { pluginApi } from "@/api/v1";
import type { menu } from "@/layouts/full/vertical-sidebar/sidebarItem";

const DEFAULT_ICON = "mdi-puzzle";
const GROUP_I18N_KEY = "core.navigation.pluginWebui";
const GROUP_ICON = "mdi-puzzle-outline";

interface PluginEntry {
  name: string;
  display_name?: string | null;
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
  const activeWithPages = plugins.filter(
    (p) => p.activated && Array.isArray(p.pages) && p.pages.length > 0,
  );

  if (activeWithPages.length === 0) return null;

  const children: menu[] = activeWithPages.map((p) => {
    const displayName = p.display_name || p.name || "Unknown Plugin";
    const firstPage = p.pages[0];

    return {
      title: displayName,
      icon: DEFAULT_ICON,
      to: `/plugin-page/${encodeURIComponent(p.name)}/${encodeURIComponent(firstPage)}`,
      isRawTitle: true,
    };
  });

  return {
    title: GROUP_I18N_KEY,
    icon: GROUP_ICON,
    children,
  };
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
  const pluginItems = shallowRef<menu | null>(null);

  function refreshItems() {
    pluginItems.value = buildPluginItems(pluginSidebarState.plugins);
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

  return { pluginItems };
}
