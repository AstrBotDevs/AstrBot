import { reactive, shallowRef, onMounted, watch } from "vue";
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

/** MDI SVG 缓存，iconName → sanitized SVG string */
const svgCache = new Map<string, string | null>();

function sanitizeSvg(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed.startsWith("<svg")) return null;
  const lower = trimmed.toLowerCase();
  if (lower.includes("<script")) return null;
  if (/\bon\w+\s*=/.test(lower)) return null;
  return trimmed;
}

async function loadSvgIcon(iconName: string): Promise<string | null> {
  if (svgCache.has(iconName)) return svgCache.get(iconName)!;

  const name = iconName.startsWith("mdi-") ? iconName.slice(4) : iconName;
  try {
    const res = await fetch(`${MDI_SVG_BASE}/${name}.svg`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = await res.text();
    const sanitized = sanitizeSvg(raw);
    svgCache.set(iconName, sanitized);
    return sanitized;
  } catch {
    svgCache.set(iconName, null);
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
    const items = buildPluginItems(pluginSidebarState.plugins);
    pluginItems.value = items;
    if (!items?.children) return;

    // 并行加载 SVG，失败时降级到默认图标
    await Promise.all(
      items.children.map(async (child) => {
        if (!child.icon) return;
        let svg = await loadSvgIcon(child.icon);
        if (!svg && child.icon !== DEFAULT_ICON) {
          svg = await loadSvgIcon(DEFAULT_ICON);
        }
        (child as any).iconSvg = svg ?? undefined;
      }),
    );
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
