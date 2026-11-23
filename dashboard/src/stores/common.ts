import { defineStore } from "pinia";
import { ref } from "vue";
import { pluginApi, statsApi } from "@/api/v1";
import { resolveApiUrl } from "@/utils/request";
import { isRecord } from "@/utils/typeGuards";

interface LogObject {
  uuid?: string;
  type: string;
  level: string;
  time: number;
  data: string;
  [key: string]: unknown;
}

interface PluginItem extends Record<string, unknown> {
  name: string;
  market_plugin_id: string;
  short_desc: string;
  download_count?: number;
  download_url: string;
  i18n: Record<string, unknown>;
  desc: string;
  author: string;
  repo: string;
  installed: boolean;
  version: string;
  social_link: string;
  tags: string[];
  logo: string;
  pinned: boolean;
  stars: number;
  updated_at: string;
  display_name: string;
  astrbot_version: string;
  category: string;
  support_platforms: string[];
}

export const useCommonStore = defineStore("common", () => {
  const eventSource = ref<AbortController | null>(null);
  const log_cache = ref<LogObject[]>([]);
  const sse_connected = ref(false);
  const log_cache_max_len = ref(1000);
  const startTime = ref(-1);
  const astrbotVersion = ref("");
  const dashboardVersion = ref("");
  const pluginMarketDataBySource = ref<Record<string, PluginItem[]>>(Object.create(null));
  const pluginMarketData = ref<PluginItem[]>([]);
  const isUnmounted = ref(false);

  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function appendLog(log: LogObject) {
    log_cache.value.push(log);
    if (log_cache.value.length > log_cache_max_len.value) {
      log_cache.value.splice(0, log_cache.value.length - log_cache_max_len.value);
    }
  }

  function consumeLogSegment(segment: string) {
    const line = segment.trim();
    if (!line.startsWith("data: ")) return;
    const logLine = line.slice(6).trim();
    if (!logLine) return;
    try {
      const logObject = JSON.parse(logLine) as LogObject;
      if (!logObject.uuid) {
        logObject.uuid =
          typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
            ? crypto.randomUUID()
            : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
                const random = (Math.random() * 16) | 0;
                return (character === "x" ? random : (random & 0x3) | 0x8).toString(16);
              });
      }
      appendLog(logObject);
    } catch (error) {
      console.warn("Failed to parse SSE log line, skipping:", error, logLine);
    }
  }

  async function createEventSource() {
    if (eventSource.value || isUnmounted.value) return;
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    const controller = new AbortController();
    const { signal } = controller;
    eventSource.value = controller;
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
    let retryDelay = 2000;
    const cancelReader = () => {
      void reader?.cancel().catch(() => undefined);
    };
    signal.addEventListener("abort", cancelReader, { once: true });

    try {
      const response = await fetch(resolveApiUrl("/api/live-log"), {
        method: "GET",
        headers: {
          "Content-Type": "multipart/form-data",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        signal,
        cache: "no-cache",
      });
      reader = response.body?.getReader() ?? null;
      if (signal.aborted) return;
      if (!response.ok) throw new Error(`SSE connection failed: ${response.status}`);
      if (!reader) throw new Error("Response body is null");
      console.info("SSE stream opened");
      sse_connected.value = true;
      const decoder = new TextDecoder();
      let bufferedText = "";
      while (!signal.aborted) {
        const { done, value } = await reader.read();
        if (signal.aborted) break;
        if (done) {
          console.info("SSE stream closed");
          break;
        }
        bufferedText += decoder.decode(value, { stream: true });
        const segments = bufferedText.split("\n\n");
        bufferedText = segments.pop() || "";
        segments.forEach(consumeLogSegment);
      }
    } catch (error) {
      if (!signal.aborted && !isUnmounted.value) {
        retryDelay = 1000;
        console.error("SSE error:", error);
        appendLog({
          type: "log",
          level: "ERROR",
          time: Date.now() / 1000,
          data: "SSE Connection failed, retrying in 1 second...",
          uuid: `error-${Date.now()}`,
        });
      }
    } finally {
      signal.removeEventListener("abort", cancelReader);
      if (reader) {
        try {
          await reader.cancel();
        } catch {
          // An errored or aborted stream can reject cancellation after read() settles.
        } finally {
          reader.releaseLock();
        }
      }
      if (eventSource.value === controller) {
        eventSource.value = null;
        sse_connected.value = false;
        if (!signal.aborted && !isUnmounted.value) {
          reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            void createEventSource();
          }, retryDelay);
        }
      }
    }
  }

  function closeEventSourcet() {
    isUnmounted.value = true;
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    eventSource.value?.abort();
    eventSource.value = null;
    sse_connected.value = false;
  }

  function getLogCache() {
    return log_cache.value;
  }

  async function fetchStartTime() {
    const response = await statsApi.startTime();
    const value = Number(response.data.data.start_time ?? -1);
    startTime.value = Number.isFinite(value) ? value : -1;
    return startTime.value;
  }

  function setAstrBotVersion(version: unknown, dashboard: unknown = "") {
    astrbotVersion.value = String(version || "").replace(/^v/i, "");
    dashboardVersion.value = String(dashboard || "");
  }

  async function fetchAstrBotVersion(force = false) {
    if (!force && astrbotVersion.value) return astrbotVersion.value;
    const response = await statsApi.version();
    const data = response.data?.data;
    setAstrBotVersion(data?.version, data?.dashboard_version);
    return astrbotVersion.value;
  }

  function getStartTime() {
    if (startTime.value === -1) void fetchStartTime().catch(() => undefined);
    return startTime.value;
  }

  async function getPluginCollections(force = false, customSource: string | null = null) {
    const sourceKey = String(customSource || "")
      .trim()
      .replace(/\/+$/, "");
    if (!force) {
      if (!sourceKey && pluginMarketData.value.length) return pluginMarketData.value;
      if (sourceKey && Array.isArray(pluginMarketDataBySource.value[sourceKey]))
        return pluginMarketDataBySource.value[sourceKey];
    }
    const response = await pluginApi.market({
      force_refresh: force || undefined,
      custom_registry: sourceKey || undefined,
    });
    const entries: unknown = response.data.data;
    const data: PluginItem[] = [];
    if (entries && typeof entries === "object") {
      for (const [key, value] of Object.entries(entries)) {
        if (key === "$meta" || !isRecord(value)) continue;
        const plugin: Record<string, unknown> = value;
        const fallbackName = key.includes("/") ? "" : key.trim();
        const author = String(plugin.author || "").trim();
        const name = String(plugin.name || "").trim() || fallbackName;
        const parsedDownloadCount = Number(plugin.download_count);
        const downloadCount =
          plugin.download_count === undefined ||
          plugin.download_count === null ||
          plugin.download_count === "" ||
          !Number.isFinite(parsedDownloadCount)
            ? undefined
            : Math.max(0, Math.trunc(parsedDownloadCount));
        const platforms = Array.isArray(plugin.support_platforms)
          ? plugin.support_platforms
          : Array.isArray(plugin.support_platform)
            ? plugin.support_platform
            : plugin.platform;
        data.push({
          ...plugin,
          name: name || key,
          market_plugin_id: String(plugin.market_plugin_id || "").trim() || (author && name ? `${author}/${name}` : ""),
          desc: String(plugin.desc || ""),
          short_desc: String(plugin.short_desc || ""),
          author: String(plugin.author || ""),
          repo: String(plugin.repo || ""),
          installed: false,
          version: String(plugin.version || "未知"),
          social_link: String(plugin.social_link || ""),
          tags: Array.isArray(plugin.tags) ? plugin.tags.filter((tag): tag is string => typeof tag === "string") : [],
          logo: String(plugin.logo || ""),
          pinned: Boolean(plugin.pinned),
          stars: Number(plugin.stars) || 0,
          download_count: downloadCount,
          updated_at: String(plugin.updated_at || ""),
          download_url: String(plugin.download_url || ""),
          display_name: String(plugin.display_name || ""),
          i18n: isRecord(plugin.i18n) ? plugin.i18n : {},
          astrbot_version: String(plugin.astrbot_version || ""),
          category: String(plugin.category || ""),
          support_platforms: Array.isArray(platforms)
            ? platforms.filter((platform): platform is string => typeof platform === "string")
            : [],
        });
      }
    }
    if (sourceKey) pluginMarketDataBySource.value[sourceKey] = data;
    else pluginMarketData.value = data;
    return data;
  }

  return {
    eventSource,
    log_cache,
    sse_connected,
    log_cache_max_len,
    startTime,
    astrbotVersion,
    dashboardVersion,
    pluginMarketDataBySource,
    setAstrBotVersion,
    fetchAstrBotVersion,
    pluginMarketData,
    createEventSource,
    closeEventSourcet,
    getLogCache,
    fetchStartTime,
    getStartTime,
    getPluginCollections,
  };
});
