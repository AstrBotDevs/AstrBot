<script setup>
import axios from "axios";
import { computed, onBeforeUnmount, onMounted, ref, toRaw, watch } from "vue";
import { useRoute } from "vue-router";
import { useModuleI18n } from "@/i18n/composables";
import { useCustomizerStore } from "@/stores/customizer";
import { usePluginI18n } from "@/utils/pluginI18n";

const BRIDGE_CHANNEL = "astrbot-plugin-page";

const route = useRoute();
const { tm } = useModuleI18n("features/extension");
const { locale, pluginName: pluginDisplayName, pluginPageTitle } = usePluginI18n();
const customizer = useCustomizerStore();

const loading = ref(true);
const errorMessage = ref("");
const plugin = ref(null);
const page = ref(null);
const iframeSrc = ref("");
const iframeRef = ref(null);
const sseConnections = new Map();
const BRIDGE_TARGET_ORIGIN = window.location.origin;
let iframeMessageOrigin = null;

const pluginName = computed(() => String(route.params.pluginName || ""));
const pageName = computed(() => String(route.params.pageName || ""));
const localizedPageTitle = computed(() =>
  pluginPageTitle(
    plugin.value,
    page.value || pageName.value,
    page.value?.title || pageName.value || tm("buttons.openPages"),
  ),
);
const getIframeWindow = () => iframeRef.value?.contentWindow || null;
const themeParam = computed(() => (customizer.isDark ? "dark" : "light"));

const toPostMessageData = (value, fallback = null) => {
  try {
    return JSON.parse(JSON.stringify(toRaw(value)));
  } catch {
    return fallback;
  }
};

const cleanupSSEConnections = () => {
  for (const eventSource of sseConnections.values()) {
    eventSource.close();
  }
  sseConnections.clear();
};

const postToIframe = (payload) => {
  const iframeWindow = getIframeWindow();
  if (!iframeWindow) {
    return;
  }
  const targetOrigin =
    typeof iframeMessageOrigin === "string" && iframeMessageOrigin !== "null" ? iframeMessageOrigin : "*";
  iframeWindow.postMessage({ channel: BRIDGE_CHANNEL, ...payload }, targetOrigin);
};

const parseContentDispositionFilename = (headerValue) => {
  if (typeof headerValue !== "string") {
    return "download.bin";
  }

  const utf8Match = headerValue.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }

  const plainMatch = headerValue.match(/filename="?([^";]+)"?/i);
  if (plainMatch?.[1]) {
    return plainMatch[1];
  }
  return "download.bin";
};

const normalizePluginEndpoint = (endpoint) => {
  if (typeof endpoint !== "string") {
    throw new Error("Plugin bridge endpoint must be a string.");
  }

  const trimmed = endpoint.trim().replace(/^\/+/, "");
  if (!trimmed) {
    throw new Error("Plugin bridge endpoint cannot be empty.");
  }
  if (trimmed.includes("\\") || trimmed.includes("://") || trimmed.includes("?") || trimmed.includes("#")) {
    throw new Error("Plugin bridge endpoint is invalid.");
  }

  const segments = trimmed.split("/");
  if (segments.some((segment) => !segment || segment === "." || segment === "..")) {
    throw new Error("Plugin bridge endpoint is invalid.");
  }
  return segments.map((segment) => encodeURIComponent(segment)).join("/");
};

const buildPluginApiPath = (endpoint) => {
  const normalized = normalizePluginEndpoint(endpoint);
  return `/api/plug/${encodeURIComponent(pluginName.value)}/${normalized}`;
};

const isBridgeUploadFile = (value) => {
  if (!value || typeof value !== "object") {
    return false;
  }
  if (typeof File !== "undefined" && value instanceof File) {
    return true;
  }
  if (typeof Blob !== "undefined" && value instanceof Blob) {
    return true;
  }
  const tag = Object.prototype.toString.call(value);
  if (tag === "[object File]" || tag === "[object Blob]") {
    return true;
  }
  return typeof value.arrayBuffer === "function" && typeof value.size === "number";
};

const coerceBridgeUploadFile = async (value, fileName) => {
  if (!isBridgeUploadFile(value)) {
    throw new Error("Missing uploaded file payload.");
  }
  if (typeof Blob !== "undefined" && value instanceof Blob) {
    return value;
  }

  const buffer = await value.arrayBuffer();
  const fileType = typeof value.type === "string" && value.type ? value.type : "application/octet-stream";
  if (typeof File !== "undefined") {
    return new File([buffer], fileName, {
      type: fileType,
      lastModified: typeof value.lastModified === "number" ? value.lastModified : Date.now(),
    });
  }
  return new Blob([buffer], { type: fileType });
};

const sendBridgeResponse = (requestId, ok, payload) => {
  postToIframe({
    kind: "response",
    requestId,
    ok,
    ...(ok ? { data: payload } : { error: payload }),
  });
};

const closeSSEConnection = (subscriptionId) => {
  const eventSource = sseConnections.get(subscriptionId);
  if (eventSource) {
    eventSource.close();
    sseConnections.delete(subscriptionId);
  }
};

const sendIframeContext = () => {
  if (!plugin.value || !page.value) {
    return;
  }
  postToIframe({
    kind: "context",
    context: {
      pluginName: plugin.value.name,
      displayName: pluginDisplayName(plugin.value),
      pageName: page.value.name,
      pageTitle: localizedPageTitle.value,
      locale: locale.value,
      i18n: toPostMessageData(plugin.value.i18n, {}),
      isDark: customizer.isDark,
    },
  });
};

const handleBridgeRequest = async (message) => {
  const { requestId, action } = message;
  try {
    if (!requestId) {
      throw new Error("Missing plugin bridge request id.");
    }

    if (action === "api:get") {
      const response = await axios.get(buildPluginApiPath(message.endpoint), {
        params: message.params || {},
      });
      if (response.data?.status === "error") {
        throw new Error(response.data.message || "Plugin GET request failed.");
      }
      sendBridgeResponse(requestId, true, response.data?.data ?? response.data);
      return;
    }

    if (action === "api:post") {
      const response = await axios.post(buildPluginApiPath(message.endpoint), message.body || {});
      if (response.data?.status === "error") {
        throw new Error(response.data.message || "Plugin POST request failed.");
      }
      sendBridgeResponse(requestId, true, response.data?.data ?? response.data);
      return;
    }

    if (action === "files:upload") {
      const formData = new FormData();
      const uploadFile = await coerceBridgeUploadFile(
        message.file,
        typeof message.fileName === "string" && message.fileName ? message.fileName : "upload.bin",
      );
      formData.append("file", uploadFile);
      const response = await axios.post(buildPluginApiPath(message.endpoint), formData, {
        timeout: 60000,
        maxContentLength: Infinity,
        maxBodyLength: Infinity,
      });
      if (response.data?.status === "error") {
        throw new Error(response.data.message || "Plugin upload request failed.");
      }
      sendBridgeResponse(requestId, true, response.data?.data ?? response.data);
      return;
    }

    if (action === "files:download") {
      const response = await axios.get(buildPluginApiPath(message.endpoint), {
        params: message.params || {},
        responseType: "blob",
      });
      const blobUrl = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = blobUrl;
      anchor.download =
        (typeof message.filename === "string" && message.filename) ||
        parseContentDispositionFilename(response.headers["content-disposition"]);
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => {
        URL.revokeObjectURL(blobUrl);
      }, 0);
      sendBridgeResponse(requestId, true, { filename: anchor.download });
      return;
    }

    if (action === "sse:subscribe") {
      const subscriptionId = String(message.subscriptionId || "");
      if (!subscriptionId) {
        throw new Error("Missing SSE subscription id.");
      }
      closeSSEConnection(subscriptionId);
      const url = new URL(buildPluginApiPath(message.endpoint), window.location.origin);
      Object.entries(message.params || {}).forEach(([key, value]) => {
        url.searchParams.set(key, String(value));
      });
      const eventSource = new EventSource(url.toString(), {
        withCredentials: true,
      });
      sseConnections.set(subscriptionId, eventSource);
      eventSource.onopen = () => {
        postToIframe({ kind: "sse_state", subscriptionId, state: "open" });
      };
      eventSource.onmessage = (event) => {
        postToIframe({
          kind: "sse_message",
          subscriptionId,
          data: event.data,
          lastEventId: event.lastEventId,
        });
      };
      eventSource.onerror = () => {
        if (eventSource.readyState === EventSource.CLOSED) {
          closeSSEConnection(subscriptionId);
          postToIframe({ kind: "sse_state", subscriptionId, state: "closed" });
          return;
        }
        postToIframe({ kind: "sse_state", subscriptionId, state: "error" });
      };
      sendBridgeResponse(requestId, true, { subscriptionId });
      return;
    }

    if (action === "sse:unsubscribe") {
      closeSSEConnection(String(message.subscriptionId || ""));
      sendBridgeResponse(requestId, true, {
        subscriptionId: message.subscriptionId,
      });
      return;
    }

    throw new Error(`Unsupported plugin bridge action: ${action}`);
  } catch (error) {
    sendBridgeResponse(requestId, false, error?.message || "Plugin bridge request failed.");
  }
};

const handleWindowMessage = (event) => {
  const iframeWindow = getIframeWindow();
  if (!iframeWindow || event.source !== iframeWindow) {
    return;
  }
  if (event.origin !== BRIDGE_TARGET_ORIGIN && event.origin !== "null") {
    return;
  }
  if (iframeMessageOrigin && event.origin !== iframeMessageOrigin) {
    return;
  }
  iframeMessageOrigin = event.origin;

  const message = event.data;
  if (!message || message.channel !== BRIDGE_CHANNEL) {
    return;
  }

  if (message.kind === "ready") {
    sendIframeContext();
    return;
  }

  if (message.kind === "request") {
    void handleBridgeRequest(message);
  }
};

const handleIframeLoad = () => {
  sendIframeContext();
};

const loadPluginPage = async () => {
  loading.value = true;
  errorMessage.value = "";
  plugin.value = null;
  page.value = null;
  iframeSrc.value = "";
  iframeMessageOrigin = null;
  cleanupSSEConnections();

  try {
    const detailResponse = await axios.get("/api/plugin/detail", {
      params: {
        name: pluginName.value,
      },
    });
    if (detailResponse.data?.status === "error") {
      throw new Error(detailResponse.data.message || tm("messages.pluginPageLoadFailed"));
    }

    const pluginData = detailResponse.data?.data || null;
    if (!pluginData) {
      errorMessage.value = tm("messages.pluginNotFound");
      return;
    }

    if (!pluginData.activated) {
      errorMessage.value = tm("messages.pluginDisabled");
      return;
    }

    const entryResponse = await axios.get("/api/plugin/page/entry", {
      params: {
        name: pluginName.value,
        page: pageName.value,
      },
    });
    if (entryResponse.data?.status === "error") {
      throw new Error(entryResponse.data.message || tm("messages.pluginPageLoadFailed"));
    }

    const pageEntry = entryResponse.data?.data || null;
    if (!pageEntry || typeof pageEntry.content_path !== "string" || !pageEntry.content_path.length) {
      errorMessage.value = tm("messages.pluginPageNotFound");
      return;
    }

    plugin.value = pluginData;
    page.value = pageEntry;
    const contentUrl = new URL(pageEntry.content_path, window.location.origin);
    contentUrl.searchParams.set("theme", themeParam.value);
    iframeSrc.value = contentUrl.pathname + contentUrl.search + contentUrl.hash;
  } catch (error) {
    errorMessage.value = error?.response?.data?.message || error?.message || tm("messages.pluginPageLoadFailed");
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  window.addEventListener("message", handleWindowMessage);
});

onBeforeUnmount(() => {
  window.removeEventListener("message", handleWindowMessage);
  cleanupSSEConnections();
});

watch([pluginName, pageName], loadPluginPage, { immediate: true });
watch(locale, () => {
  sendIframeContext();
});
watch(
  () => customizer.uiTheme,
  () => {
    sendIframeContext();
  },
);
</script>

<template>
  <div class="plugin-page-page">
    <div v-if="loading" class="plugin-page-state">
      <v-progress-circular indeterminate color="primary" />
      <span>{{ tm("status.loading") }}</span>
    </div>

    <div v-else-if="errorMessage" class="plugin-page-state">
      <v-alert type="error" variant="tonal" class="ma-6">
        {{ errorMessage }}
      </v-alert>
    </div>

    <iframe
      v-else
      ref="iframeRef"
      :src="iframeSrc"
      class="plugin-page-frame"
      referrerpolicy="no-referrer"
      sandbox="allow-scripts allow-forms allow-downloads"
      @load="handleIframeLoad"
    ></iframe>
  </div>
</template>

<style scoped>
.plugin-page-page {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
}

.plugin-page-frame {
  width: 100%;
  flex: 1;
  border: 0;
  background: transparent;
}

.plugin-page-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
</style>
