import { defineStore } from "pinia";
import { ref } from "vue";
import axios, { resolveApiUrl } from "@/utils/request";

interface LogObject {
  uuid?: string;
  type: string;
  level: string;
  time: number;
  data: string;
  [key: string]: unknown;
}

interface PluginItem {
  name: string;
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
  const pluginMarketData = ref<PluginItem[]>([]);
  const isUnmounted = ref(false);

  async function createEventSource() {
    if (eventSource.value || isUnmounted.value) {
      return;
    }
    const controller = new AbortController();
    const { signal } = controller;

    const headers = {
      "Content-Type": "multipart/form-data",
      Authorization: "Bearer " + localStorage.getItem("token"),
    };

    fetch(resolveApiUrl("/api/live-log"), {
      method: "GET",
      headers,
      signal,
      cache: "no-cache",
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`SSE connection failed: ${response.status}`);
        }
        console.info("SSE stream opened");
        sse_connected.value = true;

        if (!response.body) {
          throw new Error("Response body is null");
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let bufferedText = "";

        const processStream = ({
          done,
          value,
        }: {
          done: boolean;
          value?: Uint8Array;
        }): Promise<void> => {
          if (done) {
            console.info("SSE stream closed");
            setTimeout(() => {
              if (isUnmounted.value) return;
              eventSource.value = null;
              createEventSource();
            }, 2000);
            return Promise.resolve();
          }

          const text = decoder.decode(value, { stream: true });
          bufferedText += text;

          const segments = bufferedText.split("\n\n");
          bufferedText = segments.pop() || "";

          segments.forEach((segment) => {
            const line = segment.trim();
            if (!line.startsWith("data: ")) {
              return;
            }

            const logLine = line.replace("data: ", "").trim();
            if (!logLine) {
              return;
            }

            try {
              const logObject = JSON.parse(logLine) as LogObject;

              if (!logObject.uuid) {
                if (
                  typeof crypto !== "undefined" &&
                  typeof crypto.randomUUID === "function"
                ) {
                  logObject.uuid = crypto.randomUUID();
                } else {
                  logObject.uuid =
                    "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(
                      /[xy]/g,
                      function (c) {
                        const r = (Math.random() * 16) | 0,
                          v = c == "x" ? r : (r & 0x3) | 0x8;
                        return v.toString(16);
                      },
                    );
                }
              }

              log_cache.value.push(logObject);
              if (log_cache.value.length > log_cache_max_len.value) {
                log_cache.value.splice(
                  0,
                  log_cache.value.length - log_cache_max_len.value,
                );
              }
            } catch (err) {
              console.warn(
                "Failed to parse SSE log line, skipping:",
                err,
                logLine,
              );
            }
          });

          return reader.read().then(processStream);
        };

        reader.read().then(processStream);
      })
      .catch((error) => {
        console.error("SSE error:", error);
        log_cache.value.push({
          type: "log",
          level: "ERROR",
          time: Date.now() / 1000,
          data: "SSE Connection failed, retrying in 5 seconds...",
          uuid: "error-" + Date.now(),
        } as LogObject);
        setTimeout(() => {
          if (isUnmounted.value) return;
          eventSource.value = null;
          createEventSource();
        }, 1000);
      });

    eventSource.value = controller;
  }

  function closeEventSourcet() {
    isUnmounted.value = true;
    if (eventSource.value) {
      eventSource.value.abort();
      eventSource.value = null;
    }
  }

  function getLogCache() {
    return log_cache.value;
  }

  async function fetchStartTime() {
    const res = await axios.get("/api/stat/start-time");
    startTime.value = res.data.data.start_time;
    return startTime.value;
  }

  function getStartTime() {
    if (startTime.value !== -1) {
      return startTime.value;
    }
    fetchStartTime().catch(() => undefined);
    return startTime.value;
  }

  async function getPluginCollections(
    force = false,
    customSource: string | null = null,
  ) {
    if (!force && pluginMarketData.value.length > 0 && !customSource) {
      return Promise.resolve(pluginMarketData.value);
    }

    let url = force
      ? "/api/plugin/market_list?force_refresh=true"
      : "/api/plugin/market_list";
    if (customSource) {
      url +=
        (url.includes("?") ? "&" : "?") +
        `custom_registry=${encodeURIComponent(customSource)}`;
    }

    return axios
      .get(url)
      .then((res) => {
        const data: PluginItem[] = [];
        if (res.data.data && typeof res.data.data === "object") {
          for (const key in res.data.data) {
            const pluginData = res.data.data[key];

            data.push({
              name: pluginData.name || key,
              desc: pluginData.desc,
              author: pluginData.author,
              repo: pluginData.repo,
              installed: false,
              version: pluginData?.version ? pluginData.version : "未知",
              social_link: pluginData?.social_link,
              tags: pluginData?.tags ? pluginData.tags : [],
              logo: pluginData?.logo ? pluginData.logo : "",
              pinned: pluginData?.pinned ? pluginData.pinned : false,
              stars: pluginData?.stars ? pluginData.stars : 0,
              updated_at: pluginData?.updated_at ? pluginData.updated_at : "",
              display_name: pluginData?.display_name
                ? pluginData.display_name
                : "",
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

        pluginMarketData.value = data;
        return data;
      })
      .catch((err) => {
        return Promise.reject(err);
      });
  }

  return {
    eventSource,
    log_cache,
    sse_connected,
    log_cache_max_len,
    startTime,
    pluginMarketData,
    createEventSource,
    closeEventSourcet,
    getLogCache,
    fetchStartTime,
    getStartTime,
    getPluginCollections,
  };
});
