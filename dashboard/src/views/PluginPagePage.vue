<script setup>
import axios from "axios";
import { computed, onBeforeUnmount, onMounted, ref, toRaw, watch } from "vue";
import { useRoute } from "vue-router";
import { pluginApi } from "@/api/v1";
import { fetchWithAuth } from "@/api/http";
import { useModuleI18n } from "@/i18n/composables";
import { usePluginI18n } from "@/utils/pluginI18n";
import { useCustomizerStore } from "@/stores/customizer";

const BRIDGE_CHANNEL = "astrbot-plugin-page";

const route = useRoute();
const { tm } = useModuleI18n("features/extension");
const {
  locale,
  pluginName: pluginDisplayName,
  pluginPageTitle,
} = usePluginI18n();
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
const themeParam = computed(() => customizer.isDark ? "dark" : "light");

const toPostMessageData = (value, fallback = null) => {
  try {
    return JSON.parse(JSON.stringify(toRaw(value)));
  } catch {
    return fallback;
  }
};

const cleanupSSEConnections = () => {
  for (const connection of sseConnections.values()) {
    connection.close();
  }
  sseConnections.clear();
};

const postToIframe = (payload) => {
  const iframeWindow = getIframeWindow();
  if (!iframeWindow) {
    return;
  }
  const targetOrigin =
    typeof iframeMessageOrigin === "string" && iframeMessageOrigin !== "null"
      ? iframeMessageOrigin
      : "*";
  iframeWindow.postMessage(
    { channel: BRIDGE_CHANNEL, ...payload },
    targetOrigin,
  );
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
  if (
    trimmed.includes("\\") ||
    trimmed.includes("://") ||
    trimmed.includes("?") ||
    trimmed.includes("#")
  ) {
    throw new Error("Plugin bridge endpoint is invalid.");
  }

  const segments = trimmed.split("/");
  if (
    segments.some((segment) => !segment || segment === "." || segment === "..")
  ) {
    throw new Error("Plugin bridge endpoint is invalid.");
  }
  return segments.map((segment) => encodeURIComponent(segment)).join("/");
};

const buildPluginApiPath = (endpoint) => {
  const normalized = normalizePluginEndpoint(endpoint);
  return `/api/v1/plugins/extensions/${encodeURIComponent(pluginName.value)}/${normalized}`;
};

const isBridgeUploadFile = (value) => {
  if (!value || typeof value !== "object") {
    return false;
  }
  if (value instanceof ArrayBuffer || ArrayBuffer.isView(value)) {
    return true;
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
  return (
    typeof value.arrayBuffer === "function" && typeof value.size === "number"
  );
};

const createBridgeUploadBlob = (parts, fileName, fileType, lastModified) => {
  const normalizedType =
    typeof fileType === "string" && fileType
      ? fileType
      : "application/octet-stream";
  if (typeof File !== "undefined") {
    return new File(parts, fileName, {
      type: normalizedType,
      lastModified:
        typeof lastModified === "number" ? lastModified : Date.now(),
    });
  }
  return new Blob(parts, { type: normalizedType });
};

const coerceBridgeUploadFile = async (
  value,
  fileName,
  fileType,
  lastModified,
) => {
  if (!isBridgeUploadFile(value)) {
    throw new Error("Missing uploaded file payload.");
  }
  if (value instanceof ArrayBuffer) {
    return createBridgeUploadBlob([value], fileName, fileType, lastModified);
  }
  if (ArrayBuffer.isView(value)) {
    const viewBuffer = value.buffer.slice(
      value.byteOffset,
      value.byteOffset + value.byteLength,
    );
    return createBridgeUploadBlob(
      [viewBuffer],
      fileName,
      fileType,
      lastModified,
    );
  }
  if (typeof Blob !== "undefined" && value instanceof Blob) {
    return value;
  }

  const buffer = await value.arrayBuffer();
  const fallbackType =
    typeof value.type === "string" && value.type
      ? value.type
      : "application/octet-stream";
  const normalizedType =
    typeof fileType === "string" && fileType
      ? fileType
      : fallbackType;
  return createBridgeUploadBlob(
    [buffer],
    fileName,
    normalizedType,
    typeof lastModified === "number" ? lastModified : value.lastModified,
  );
};

const sendBridgeResponse = (requestId, ok, payload) => {
  postToIframe({
    kind: "response",
    requestId,
    ok,
    ...(ok ? { data: payload } : { error: payload }),
  });
};

const getBridgeErrorMessage = (error, fallback) => {
  const responseData = error?.response?.data;
  if (responseData && typeof responseData === "object") {
    if (typeof responseData.message === "string" && responseData.message) {
      return responseData.message;
    }
    if (typeof responseData.error === "string" && responseData.error) {
      return responseData.error;
    }
  }
  return error?.message || fallback;
};

const closeSSEConnection = (subscriptionId) => {
  const connection = sseConnections.get(subscriptionId);
  if (connection) {
    connection.close();
    sseConnections.delete(subscriptionId);
  }
};

const getFetchErrorMessage = async (response, fallback) => {
  let text = "";
  try {
    text = await response.text();
  } catch {
    return fallback;
  }
  if (!text) {
    return fallback;
  }
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed?.message === "string" && parsed.message) {
      return parsed.message;
    }
    if (typeof parsed?.error === "string" && parsed.error) {
      return parsed.error;
    }
  } catch {
    return text;
  }
  return text;
};

const parseSSEBlock = (block, previousLastEventId) => {
  let eventType = "message";
  let lastEventId = previousLastEventId;
  const dataLines = [];

  for (const rawLine of block.split("\n")) {
    if (!rawLine || rawLine.startsWith(":")) {
      continue;
    }

    const colonIndex = rawLine.indexOf(":");
    const field = colonIndex === -1 ? rawLine : rawLine.slice(0, colonIndex);
    let value = colonIndex === -1 ? "" : rawLine.slice(colonIndex + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }

    if (field === "event") {
      eventType = value || "message";
    } else if (field === "data") {
      dataLines.push(value);
    } else if (field === "id" && !value.includes("\0")) {
      lastEventId = value;
    }
  }

  return {
    eventType,
    lastEventId,
    data: dataLines.join("\n"),
    hasData: dataLines.length > 0,
  };
};

const readSSEStream = async (subscriptionId, response, abortController) => {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lastEventId = "";

  const dispatchBufferedEvents = (flush = false) => {
    const normalized = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const blocks = normalized.split("\n\n");
    const completeBlocks = flush ? blocks : blocks.slice(0, -1);
    buffer = flush ? "" : blocks[blocks.length - 1] || "";

    for (const block of completeBlocks) {
      if (!sseConnections.has(subscriptionId)) {
        return;
      }
      const event = parseSSEBlock(block, lastEventId);
      lastEventId = event.lastEventId;
      if (!event.hasData) {
        continue;
      }
      postToIframe({
        kind: "sse_message",
        subscriptionId,
        data: event.data,
        eventType: event.eventType,
        lastEventId,
      });
    }
  };

  try {
    while (!abortController.signal.aborted) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      dispatchBufferedEvents();
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      dispatchBufferedEvents(true);
    }

    if (!abortController.signal.aborted) {
      postToIframe({ kind: "sse_state", subscriptionId, state: "closed" });
    }
  } catch {
    if (!abortController.signal.aborted) {
      postToIframe({ kind: "sse_state", subscriptionId, state: "error" });
    }
  } finally {
    if (sseConnections.get(subscriptionId)?.abortController === abortController) {
      sseConnections.delete(subscriptionId);
    }
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
      const response = await axios.post(
        buildPluginApiPath(message.endpoint),
        message.body || {},
      );
      if (response.data?.status === "error") {
        throw new Error(response.data.message || "Plugin POST request failed.");
      }
      sendBridgeResponse(requestId, true, response.data?.data ?? response.data);
      return;
    }

    if (action === "files:upload") {
      const formData = new FormData();
      const fileName =
        typeof message.fileName === "string" && message.fileName
          ? message.fileName
          : "upload.bin";
      const uploadFile = await coerceBridgeUploadFile(
        message.fileBuffer || message.file,
        fileName,
        message.fileType,
        message.fileLastModified,
      );
      formData.append("file", uploadFile, fileName);
      const response = await axios.post(
        buildPluginApiPath(message.endpoint),
        formData,
        {
          timeout: 60000,
          maxContentLength: Infinity,
          maxBodyLength: Infinity,
        },
      );
      if (response.data?.status === "error") {
        throw new Error(
          response.data.message || "Plugin upload request failed.",
        );
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
        parseContentDispositionFilename(
          response.headers["content-disposition"],
        );
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
      const url = new URL(
        buildPluginApiPath(message.endpoint),
        window.location.origin,
      );
      Object.entries(message.params || {}).forEach(([key, value]) => {
        url.searchParams.set(key, String(value));
      });
      const abortController = new AbortController();
      const connection = {
        abortController,
        close() {
          abortController.abort();
        },
      };
      sseConnections.set(subscriptionId, connection);

      const response = await fetchWithAuth(url.toString(), {
        headers: { Accept: "text/event-stream" },
        signal: abortController.signal,
      });
      if (!response.ok) {
        const errorMessage = await getFetchErrorMessage(
          response,
          `Plugin SSE request failed with status ${response.status}.`,
        );
        closeSSEConnection(subscriptionId);
        throw new Error(errorMessage);
      }
      if (!response.body) {
        closeSSEConnection(subscriptionId);
        throw new Error("Plugin SSE response body is not readable.");
      }

      sendBridgeResponse(requestId, true, { subscriptionId });
      postToIframe({ kind: "sse_state", subscriptionId, state: "open" });
      void readSSEStream(subscriptionId, response, abortController);
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
    sendBridgeResponse(
      requestId,
      false,
      getBridgeErrorMessage(error, "Plugin bridge request failed."),
    );
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
    const detailResponse = await pluginApi.get(pluginName.value);
    if (detailResponse.data?.status === "error") {
      throw new Error(
        detailResponse.data.message || tm("messages.pluginPageLoadFailed"),
      );
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

    const entryResponse = await pluginApi.page(pluginName.value, pageName.value);
    if (entryResponse.data?.status === "error") {
      throw new Error(
        entryResponse.data.message || tm("messages.pluginPageLoadFailed"),
      );
    }

    const pageEntry = entryResponse.data?.data || null;
    if (
      !pageEntry ||
      typeof pageEntry.content_path !== "string" ||
      !pageEntry.content_path.length
    ) {
      errorMessage.value = tm("messages.pluginPageNotFound");
      return;
    }

    plugin.value = pluginData;
    page.value = pageEntry;
    const contentUrl = new URL(pageEntry.content_path, window.location.origin);
    contentUrl.searchParams.set('theme', themeParam.value);
    iframeSrc.value = contentUrl.pathname + contentUrl.search + contentUrl.hash;
  } catch (error) {
    errorMessage.value =
      error?.response?.data?.message ||
      error?.message ||
      tm("messages.pluginPageLoadFailed");
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
watch(() => customizer.uiTheme, () => {
  sendIframeContext();
});
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
