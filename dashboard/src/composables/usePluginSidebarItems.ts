import { reactive, shallowRef, computed, onMounted, watch } from "vue";
import axios from "axios";
import type { menu } from "@/layouts/full/vertical-sidebar/sidebarItem";

const DEFAULT_ICON = "mdi-puzzle";
const GROUP_I18N_KEY = "core.navigation.pluginWebui";
const GROUP_ICON = "mdi-puzzle-outline";
const MDI_SVG_BASE = "https://cdn.jsdelivr.net/npm/@mdi/svg@7/svg";

interface PluginEntry {
  name: string;
  display_name?: string | null;
  activated: boolean;
  pages: string[];
  icon?: string | null;
}

/** 模块级共享状态，由 useExtensionPage.getExtensions() 更新 */
export const pluginSidebarState = reactive<{
  plugins: PluginEntry[];
}>({
  plugins: [],
});

/** MDI SVG 缓存，iconName → raw SVG string */
const svgCache = reactive<Record<string, string | null>>({});

async function loadSvgIcon(iconName: string): Promise<string | null> {
  if (iconName in svgCache) return svgCache[iconName];

  const name = iconName.startsWith("mdi-") ? iconName.slice(4) : iconName;
  try {
    const res = await fetch(`${MDI_SVG_BASE}/${name}.svg`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const svgText = await res.text();
    svgCache[iconName] = svgText;
    return svgText;
  } catch {
    svgCache[iconName] = null;
    return null;
  }
}

function buildPluginItems(plugins: PluginEntry[]): (menu & { iconSvg?: string }) | null {
  const activeWithPages = plugins.filter(
    (p) => p.activated && Array.isArray(p.pages) && p.pages.length > 0,
  );

  if (activeWithPages.length === 0) return null;

  const children: menu[] = activeWithPages.map((p) => {
    const displayName = p.display_name || p.name || "Unknown Plugin";
    const firstPage = p.pages[0];
    const icon = p.icon || DEFAULT_ICON;

    return {
      title: displayName,
      icon,
      iconSvg: svgCache[icon] ?? undefined,
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
    const res = await axios.get("/api/plugin/get");
    if (res.data?.status === "ok") {
      pluginSidebarState.plugins = res.data.data ?? [];
    }
  } catch {
    // 静默失败，后续 getExtensions() 会补充
  }
}

export function usePluginSidebarItems() {
  const pluginItems = shallowRef<(menu & { iconSvg?: string }) | null>(null);

  async function refreshItems() {
    const plugins = pluginSidebarState.plugins;
    const items = buildPluginItems(plugins);
    pluginItems.value = items;
    if (!items?.children) return;

    // 后台加载 SVG，加载完成后逐个更新
    for (const child of items.children) {
      const iconName = child.icon;
      if (!iconName || svgCache[iconName] !== undefined) continue;

      const svg = await loadSvgIcon(iconName);
      // 触发响应式更新
      pluginItems.value = buildPluginItems(pluginSidebarState.plugins);
    }
  }

  onMounted(async () => {
    await initPluginState();
    refreshItems();
  });

  watch(() => pluginSidebarState.plugins, () => {
    refreshItems();
  });

  return { pluginItems };
}
