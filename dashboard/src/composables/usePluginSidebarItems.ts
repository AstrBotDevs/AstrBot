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
  i18n?: Record<string, Record<string, unknown>> | null;
}

/** Localized labels resolved from the plugin i18n payload. */
interface PluginLabels {
  plugin: (plugin: PluginEntry) => string;
  view: (plugin: PluginEntry, viewName: string) => string;
}

/** 模块级共享状态，由 useExtensionPage.getExtensions() 更新 */
export const pluginSidebarState = reactive<{
  plugins: PluginEntry[];
}>({
  plugins: [],
});

function buildPluginItems(
  plugins: PluginEntry[],
  labels: PluginLabels,
): menu | null {
  const activeWithPages = plugins.filter(
    (p) => p.activated && Array.isArray(p.pages) && p.pages.length > 0,
  );

  if (activeWithPages.length === 0) return null;

  const children: menu[] = activeWithPages.map((p) => {
    return buildPageItem(p, p.pages[0], labels);
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
  labels: PluginLabels,
): menu {
  const viewLabel = labels.view(p, page);
  return {
    title: viewLabel,
    icon: DEFAULT_ICON,
    to: `/plugin-view/${encodeURIComponent(p.name)}/${encodeURIComponent(page)}`,
    isRawTitle: true,
    pluginInfo: {
      id: p.name,
      displayName: labels.plugin(p),
      viewTitle: viewLabel,
      author: p.author,
      version: p.version,
    },
  };
}

function buildPluginGroups(
  plugins: PluginEntry[],
  labels: PluginLabels,
): menu[] {
  return plugins
    .filter((p) => p.activated && Array.isArray(p.pages) && p.pages.length > 0)
    .map((p) => {
      return {
        title: labels.plugin(p),
        icon: GROUP_ICON,
        isRawTitle: true,
        children: p.pages.map((page) => buildPageItem(p, page, labels)),
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
  const { locale, pluginName, pluginViewTitle } = usePluginI18n();

  const pluginItems = shallowRef<menu | null>(null);
  const pluginGroups = shallowRef<menu[]>([]);

  // Plugin i18n ships with the plugin list payload, so labels are resolved on
  // the client: the view title first, then the plugin display name, then the
  // raw view directory name.
  const labels: PluginLabels = {
    plugin: (plugin) => pluginName(plugin) || plugin.name || "",
    view: (plugin, viewName) =>
      pluginViewTitle(
        plugin,
        viewName,
        pluginName(plugin) || plugin.name || viewName,
      ),
  };

  function refreshItems() {
    pluginItems.value = buildPluginItems(pluginSidebarState.plugins, labels);
    pluginGroups.value = buildPluginGroups(pluginSidebarState.plugins, labels);
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

  // The list payload is locale independent, so switching the WebUI language
  // only needs the labels rebuilt.
  watch(locale, () => {
    refreshItems();
  });

  return { pluginItems, pluginGroups };
}
