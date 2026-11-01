import { defineStore } from "pinia";
import { pluginApi, statsApi } from "@/api/v1";

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
    async getPluginCollections(force = false, customSource = null) {
      // 获取插件市场数据
      const sourceKey = String(customSource || "")
        .trim()
        .replace(/\/+$/, "");
      if (!force) {
        if (!sourceKey && this.pluginMarketData.length > 0) {
          return Promise.resolve(this.pluginMarketData);
        }
        if (
          sourceKey &&
          Array.isArray(this.pluginMarketDataBySource[sourceKey])
        ) {
          return Promise.resolve(this.pluginMarketDataBySource[sourceKey]);
        }
      }

      return pluginApi
        .market({
          force_refresh: force || undefined,
          custom_registry: sourceKey || undefined,
        })
        .then((res) => {
          let data = [];
          if (res.data.data && typeof res.data.data === "object") {
            for (let key in res.data.data) {
              if (key === "$meta") {
                continue;
              }

              const pluginData = res.data.data[key];
              const fallbackPluginName = String(key || "").includes("/")
                ? ""
                : String(key || "").trim();
              const pluginAuthor = String(pluginData?.author || "").trim();
              const pluginName =
                String(pluginData?.name || "").trim() || fallbackPluginName;
              const displayPluginName = pluginName || key;
              const marketPluginId =
                String(pluginData?.market_plugin_id || "").trim() ||
                (pluginAuthor && pluginName
                  ? `${pluginAuthor}/${pluginName}`
                  : "");
              const parsedDownloadCount = Number(pluginData?.download_count);
              const downloadCount =
                pluginData?.download_count === undefined ||
                pluginData?.download_count === null ||
                pluginData?.download_count === "" ||
                !Number.isFinite(parsedDownloadCount)
                  ? undefined
                  : Math.max(0, Math.trunc(parsedDownloadCount));

              data.push({
                ...pluginData,
                name: displayPluginName, // 优先使用插件数据中的name字段，否则使用键名
                market_plugin_id: marketPluginId,
                desc: pluginData.desc,
                short_desc: pluginData?.short_desc ? pluginData.short_desc : "",
                author: pluginData.author,
                repo: pluginData.repo,
                installed: false,
                version: pluginData?.version ? pluginData.version : "未知",
                social_link: pluginData?.social_link,
                tags: pluginData?.tags ? pluginData.tags : [],
                logo: pluginData?.logo ? pluginData.logo : "",
                pinned: pluginData?.pinned ? pluginData.pinned : false,
                stars: pluginData?.stars ? pluginData.stars : 0,
                download_count: downloadCount,
                updated_at: pluginData?.updated_at ? pluginData.updated_at : "",
                download_url: pluginData?.download_url
                  ? pluginData.download_url
                  : "",
                display_name: pluginData?.display_name
                  ? pluginData.display_name
                  : "",
                i18n:
                  pluginData?.i18n && typeof pluginData.i18n === "object"
                    ? pluginData.i18n
                    : {},
                astrbot_version: pluginData?.astrbot_version
                  ? pluginData.astrbot_version
                  : "",
                category: pluginData?.category ? pluginData.category : "",
                support_platforms: Array.isArray(pluginData?.support_platforms)
                  ? pluginData.support_platforms
                  : Array.isArray(pluginData?.support_platform)
                  ? pluginData.support_platform
                  : Array.isArray(pluginData?.platform)
                  ? pluginData.platform
                  : [],
              });
            }
          }

          if (sourceKey) {
            this.pluginMarketDataBySource[sourceKey] = data;
          } else {
            this.pluginMarketData = data;
          }
          return data;
        })
        .catch((err) => {
          return Promise.reject(err);
        });
    },
  },
});
