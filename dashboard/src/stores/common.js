import { defineStore } from "pinia";
import axios, { resolveApiUrl } from "@/utils/request";

/**
 * Common store used across the dashboard.
 * Uses the project's custom axios instance (`@/utils/request`) and resolveApiUrl
 * to ensure all requests honor the configured API base URL and dev proxy.
 */
export const useCommonStore = defineStore("common", {
  state: () => ({
    // AbortController for SSE connection (or null)
    eventSource: null,
    // Cached logs from SSE
    log_cache: [],
    // Whether SSE is connected
    sse_connected: false,
    // Max length for log cache
    log_cache_max_len: 1000,
    // Backend start time
    startTime: -1,
    astrbotVersion: "",
    dashboardVersion: "",

    // Plugin market data cache
    pluginMarketData: [],
    pluginMarketDataBySource: {},
  }),
  actions: {
    async createEventSource() {
      if (this.eventSource) {
        return;
      }

      const controller = new AbortController();
      const { signal } = controller;

      // Headers for SSE request - include token if available
      const headers = {
        "Content-Type": "multipart/form-data",
      };
      const token = localStorage.getItem("token");
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      // Resolve the URL using resolveApiUrl so base URL / proxy rules are applied
      const url = resolveApiUrl("/api/live-log");

      try {
        const response = await fetch(url, {
          method: "GET",
          headers,
          signal,
          cache: "no-cache",
        });

        if (!response.ok) {
          throw new Error(`SSE connection failed: ${response.status}`);
        }

        console.info("SSE stream opened");
        this.sse_connected = true;

        if (!response.body) {
          throw new Error("Response body is null");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let bufferedText = "";

        const processStream = ({ done, value }) => {
          if (done) {
            console.info("SSE stream closed");
            // reconnect after short delay unless store was intentionally closed
            setTimeout(() => {
              if (this.eventSource === null) return;
              this.eventSource = null;
              this.createEventSource();
            }, 2000);
            return Promise.resolve();
          }

          const text = decoder.decode(value, { stream: true });
          bufferedText += text;

          // SSE events are separated by double-newline
          const segments = bufferedText.split("\n\n");
          bufferedText = segments.pop() || "";

          segments.forEach((segment) => {
            const line = segment.trim();
            if (!line.startsWith("data: ")) {
              return;
            }

            const logLine = line.replace("data: ", "").trim();
            if (!logLine) return;

            try {
              const logObject = JSON.parse(logLine);

              if (!logObject.uuid) {
                if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
                  logObject.uuid = crypto.randomUUID();
                } else {
                  // Fallback UUID v4 generator
                  logObject.uuid = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
                    const r = (Math.random() * 16) | 0,
                      v = c === "x" ? r : (r & 0x3) | 0x8;
                    return v.toString(16);
                  });
                }
              }

              this.log_cache.push(logObject);
              if (this.log_cache.length > this.log_cache_max_len) {
                this.log_cache.splice(0, this.log_cache.length - this.log_cache_max_len);
              }
            } catch (err) {
              console.warn("Failed to parse SSE log line, skipping:", err, logLine);
            }
          });

          return reader.read().then(processStream);
        };

        reader.read().then(processStream);
      } catch (error) {
        console.error("SSE error:", error);
        // Push an error log and attempt reconnect
        this.log_cache.push({
          type: "log",
          level: "ERROR",
          time: Date.now() / 1000,
          data: "SSE Connection failed, retrying...",
          uuid: `error-${Date.now()}`,
        });
        setTimeout(() => {
          this.eventSource = null;
          this.createEventSource();
        }, 1000);
      }

      // store controller so it can be aborted later
      this.eventSource = controller;
    },

    closeEventSourcet() {
      if (this.eventSource) {
        try {
          this.eventSource.abort();
        } catch (e) {
          // ignore abort errors
        }
        this.eventSource = null;
        this.sse_connected = false;
      }
    },

    getLogCache() {
      return this.log_cache;
    },

    async fetchStartTime() {
      // Use custom axios instance so baseURL / interceptors are applied
      const res = await axios.get("/api/stat/start-time");
      this.startTime = res.data?.data?.start_time ?? this.startTime;
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
      const res = await axios.get("/api/stat/version");
      const data = res.data?.data || {};
      this.setAstrBotVersion(data.version, data.dashboard_version);
      return this.astrbotVersion;
    },

    getStartTime() {
      if (this.startTime !== -1) {
        return this.startTime;
      }
      // Fire-and-forget fetch to populate startTime
      this.fetchStartTime().catch(() => undefined);
      return this.startTime;
    },

    async getPluginCollections(force = false, customSource = null) {
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

      let url = force
        ? "/api/plugin/market_list?force_refresh=true"
        : "/api/plugin/market_list";
      if (sourceKey) {
        url += `${url.includes("?") ? "&" : "?"}custom_registry=${encodeURIComponent(sourceKey)}`;
      }

      try {
        const res = await axios.get(url);
        const data = [];
        if (res.data?.data && typeof res.data.data === "object") {
          for (const key in res.data.data) {
            if (key === "$meta") continue;

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
              (pluginAuthor && pluginName ? `${pluginAuthor}/${pluginName}` : "");
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
              name: displayPluginName,
              market_plugin_id: marketPluginId,
              desc: pluginData.desc,
              short_desc: pluginData?.short_desc || "",
              author: pluginData.author,
              repo: pluginData.repo,
              installed: false,
              version: pluginData?.version || "未知",
              social_link: pluginData?.social_link,
              tags: pluginData?.tags || [],
              logo: pluginData?.logo || "",
              pinned: Boolean(pluginData?.pinned),
              stars: pluginData?.stars || 0,
              download_count: downloadCount,
              updated_at: pluginData?.updated_at || "",
              download_url: pluginData?.download_url || "",
              display_name: pluginData?.display_name || "",
              i18n:
                pluginData?.i18n && typeof pluginData.i18n === "object"
                  ? pluginData.i18n
                  : {},
              astrbot_version: pluginData?.astrbot_version || "",
              category: pluginData?.category || "",
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
      } catch (err) {
        return Promise.reject(err);
      }
    },
  },
});
