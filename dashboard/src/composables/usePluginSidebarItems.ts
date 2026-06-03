import { ref, shallowRef, onMounted, onUnmounted } from "vue";
import axios from "axios";
import type { menu } from "@/layouts/full/vertical-sidebar/sidebarItem";

const DEFAULT_ICON = "mdi-puzzle";

interface PluginEntry {
  name: string;
  display_name?: string | null;
  activated: boolean;
  pages: string[];
  icon?: string | null;
}

const pluginItems = shallowRef<menu[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

let refreshTimer: ReturnType<typeof setInterval> | null = null;

async function fetchPluginSidebarItems() {
  loading.value = true;
  error.value = null;

  try {
    const response = await axios.get("/api/plugin/get");
    if (response.data?.status === "error") {
      error.value = response.data.message || "Failed to load plugins";
      return;
    }

    const plugins: PluginEntry[] = response.data?.data ?? [];

    const activeWithPages = plugins.filter(
      (p) => p.activated && Array.isArray(p.pages) && p.pages.length > 0,
    );

    pluginItems.value = activeWithPages.map((p) => {
      const displayName =
        p.display_name || p.name || "Unknown Plugin";
      const firstPage = p.pages[0];
      const icon = p.icon || DEFAULT_ICON;

      return {
        title: displayName,
        icon,
        to: `/plugin-page/${encodeURIComponent(p.name)}/${encodeURIComponent(firstPage)}`,
        isRawTitle: true,
      };
    });
  } catch (e: any) {
    error.value = e?.message || "Failed to load plugins";
    pluginItems.value = [];
  } finally {
    loading.value = false;
  }
}

export function usePluginSidebarItems() {
  onMounted(() => {
    fetchPluginSidebarItems();

    // 每隔 60 秒刷新一次以响应插件激活/停用
    refreshTimer = setInterval(fetchPluginSidebarItems, 60_000);
  });

  onUnmounted(() => {
    if (refreshTimer !== null) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  });

  return {
    pluginItems,
    loading,
    error,
    refresh: fetchPluginSidebarItems,
  };
}
