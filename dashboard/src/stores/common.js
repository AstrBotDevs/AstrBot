import { defineStore } from "pinia";
import { statsApi } from "@/api/v1";

export const normalizeMarketPluginEntry = (pluginData, fallbackName = "") => {
  const data = pluginData && typeof pluginData === "object" ? pluginData : {};
  const pluginAuthor = String(data.author || "").trim();
  const pluginName = String(data.name || "").trim() || String(fallbackName || "").trim();
  const displayPluginName = pluginName || fallbackName || "";
  const marketPluginId =
    String(data.market_plugin_id || "").trim() ||
    (pluginAuthor && pluginName ? `${pluginAuthor}/${pluginName}` : "");
  const parsedDownloadCount = Number(data.download_count);
  const downloadCount =
    data.download_count === undefined ||
    data.download_count === null ||
    data.download_count === "" ||
    !Number.isFinite(parsedDownloadCount)
      ? undefined
      : Math.max(0, Math.trunc(parsedDownloadCount));

  return {
    ...data,
    name: displayPluginName,
    market_plugin_id: marketPluginId,
    short_desc: data.short_desc ? data.short_desc : "",
    installed: false,
    version: data.version ? data.version : "未知",
    tags: data.tags ? data.tags : [],
    logo: data.logo ? data.logo : "",
    pinned: data.pinned ? data.pinned : false,
    stars: data.stars ? data.stars : 0,
    download_count: downloadCount,
    updated_at: data.updated_at ? data.updated_at : "",
    download_url: data.download_url ? data.download_url : "",
    display_name: data.display_name ? data.display_name : "",
    i18n: data.i18n && typeof data.i18n === "object" ? data.i18n : {},
    astrbot_version: data.astrbot_version ? data.astrbot_version : "",
    category: data.category ? data.category : "",
    support_platforms: Array.isArray(data.support_platforms)
      ? data.support_platforms
      : Array.isArray(data.support_platform)
        ? data.support_platform
        : Array.isArray(data.platform)
          ? data.platform
          : [],
  };
};

export const useCommonStore = defineStore("common", {
  state: () => ({
    startTime: -1,
    astrbotVersion: "",
    dashboardVersion: "",

    pluginMarketData: [],
    pluginMarketDataBySource: {},
  }),
  actions: {
    async fetchStartTime() {
      const res = await statsApi.startTime();
      this.startTime = res.data.data.start_time;
      return this.startTime;
    },
    setAstrBotVersion(version, dashboardVersion = "") {
      this.astrbotVersion = String(version || "").replace(/^v/i, "");
      this.dashboardVersion = String(dashboardVersion || "");
    },
    async fetchAstrBotVersion(force = false) {
      if (!force && this.astrbotVersion) {
        return this.astrbotVersion;
      }
      const res = await statsApi.version();
      const data = res.data?.data || {};
      this.setAstrBotVersion(data.version, data.dashboard_version);
      return this.astrbotVersion;
    },
    getStartTime() {
      if (this.startTime !== -1) {
        return this.startTime;
      }
      this.fetchStartTime().catch(() => {});
      return this.startTime;
    },
  },
});
