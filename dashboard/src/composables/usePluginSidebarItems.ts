import { onMounted, reactive, shallowRef, watch } from "vue";
import { pluginApi } from "@/api/v1";
import { useI18n } from "@/i18n/composables";
import type { menu } from "@/layouts/full/vertical-sidebar/sidebarItem";
import { resolvePluginI18n, resolvePluginViewText } from "@/utils/pluginI18n";

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
  views?: { name: string; title?: string; description?: string }[];
  i18n?: Record<
    string,
    {
      metadata?: { display_name?: unknown };
      views?: Record<string, { title?: unknown }>;
      pages?: Record<string, { title?: unknown }>;
    }
  > | null;
}

/** Shared state refreshed by useExtensionPage.getExtensions(). */
export const pluginSidebarState = reactive<{
  plugins: PluginEntry[];
}>({
  plugins: [],
});

function buildPluginItems(plugins: PluginEntry[], locale: string): menu | null {
  const activeWithPages = plugins.filter((p) => p.activated && Array.isArray(p.pages) && p.pages.length > 0);

  if (activeWithPages.length === 0) return null;

  const children: menu[] = activeWithPages.map((p) => {
    return buildPageItem(p, p.pages[0], locale);
  });

  return {
    title: GROUP_I18N_KEY,
    icon: GROUP_ICON,
    children,
  };
}

function buildPageItem(p: PluginEntry, page: string, locale: string): menu {
  const displayName =
    [resolvePluginI18n(p.i18n, locale, "metadata.display_name"), p.display_name, p.name]
      .find((value) => typeof value === "string" && value.trim())
      ?.trim() || "Unknown Plugin";
  return {
    title: resolvePluginViewText(
      p.i18n,
      locale,
      p.views?.find((view) => view.name === page) || { name: page },
      "title",
    ),
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

function buildPluginGroups(plugins: PluginEntry[], locale: string): menu[] {
  return plugins
    .filter((p) => p.activated && Array.isArray(p.pages) && p.pages.length > 0)
    .map((p) => {
      const displayName =
        [resolvePluginI18n(p.i18n, locale, "metadata.display_name"), p.display_name, p.name]
          .find((value) => typeof value === "string" && value.trim())
          ?.trim() || "Unknown Plugin";
      return {
        value: `plugin:${p.name}`,
        title: displayName,
        icon: GROUP_ICON,
        isRawTitle: true,
        children: p.pages.map((page) => buildPageItem(p, page, locale)),
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
    // getExtensions() will refresh the shared state after an initial failure.
  }
}

export function usePluginSidebarItems() {
  const { locale } = useI18n();
  const pluginItems = shallowRef<menu | null>(null);
  const pluginGroups = shallowRef<menu[]>([]);

  function refreshItems() {
    pluginItems.value = buildPluginItems(pluginSidebarState.plugins, locale.value);
    pluginGroups.value = buildPluginGroups(pluginSidebarState.plugins, locale.value);
  }

  onMounted(async () => {
    await initPluginState();
    refreshItems();
  });

  watch([() => pluginSidebarState.plugins, locale], () => {
    refreshItems();
  });

  return { pluginItems, pluginGroups };
}
