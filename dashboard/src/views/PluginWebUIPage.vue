<script setup>
import axios from "axios";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useModuleI18n } from "@/i18n/composables";

const BRIDGE_CHANNEL = "astrbot-plugin-webui";

const route = useRoute();
const router = useRouter();
const { tm } = useModuleI18n("features/extension");

const loading = ref(true);
const errorMessage = ref("");
const plugin = ref(null);
const webui = ref(null);
const iframeSrc = ref("");
const iframeRef = ref(null);
const sseConnections = new Map();
const BRIDGE_TARGET_ORIGIN = window.location.origin;
let iframeMessageOrigin = null;

const pluginName = computed(() => String(route.params.pluginName || ""));
const getIframeWindow = () => iframeRef.value?.contentWindow || null;

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
  if (!plugin.value || !webui.value) {
    return;
  }
  postToIframe({
    kind: "context",
    context: {
      pluginName: plugin.value.name,
      displayName: plugin.value.display_name || plugin.value.name,
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
      if (!(message.file instanceof Blob)) {
        throw new Error("Missing uploaded file payload.");
      }
      formData.append(
        "file",
        message.file,
        typeof message.fileName === "string" && message.fileName
          ? message.fileName
          : "upload.bin",
      );
      const response = await fetch(buildPluginApiPath(message.endpoint), {
        method: "POST",
        body: formData,
        credentials: "same-origin",
      });
      const payload = await response.json();
      if (!response.ok || payload.status !== "ok") {
        throw new Error(payload.message || "Plugin upload request failed.");
      }
      sendBridgeResponse(requestId, true, payload.data);
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
      URL.revokeObjectURL(blobUrl);
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
      const eventSource = new EventSource(url.toString(), { withCredentials: true });
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
        postToIframe({ kind: "sse_state", subscriptionId, state: "error" });
      };
      sendBridgeResponse(requestId, true, { subscriptionId });
      return;
    }

    if (action === "sse:unsubscribe") {
      closeSSEConnection(String(message.subscriptionId || ""));
      sendBridgeResponse(requestId, true, { subscriptionId: message.subscriptionId });
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

const loadPluginWebUI = async () => {
  loading.value = true;
  errorMessage.value = "";
  plugin.value = null;
  webui.value = null;
  iframeSrc.value = "";
  iframeMessageOrigin = null;
  cleanupSSEConnections();

  try {
    const response = await axios.get("/api/plugin/get", {
      params: {
        name: pluginName.value,
      },
    });
    if (response.data?.status === "error") {
      throw new Error(response.data.message || tm("messages.pluginWebUILoadFailed"));
    }

    const pluginData = Array.isArray(response.data?.data)
      ? response.data.data[0]
      : null;
    if (!pluginData) {
      errorMessage.value = tm("messages.pluginNotFound");
      return;
    }

    if (!pluginData.activated) {
      errorMessage.value = tm("messages.pluginDisabled");
      return;
    }

    const webuiEntry =
      pluginData.webui && typeof pluginData.webui === "object"
        ? pluginData.webui
        : null;
    if (!webuiEntry || typeof webuiEntry.content_path !== "string" || !webuiEntry.content_path.length) {
      errorMessage.value = tm("messages.pluginWebUIPageNotFound");
      return;
    }

    plugin.value = pluginData;
    webui.value = webuiEntry;
    iframeSrc.value = webuiEntry.content_path;
  } catch (error) {
    errorMessage.value =
      error?.response?.data?.message || error?.message || tm("messages.pluginWebUILoadFailed");
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

watch([pluginName], loadPluginWebUI, { immediate: true });
</script>

<template>
  <div class="plugin-webui-page">
    <div class="d-flex align-center flex-wrap mb-4" style="gap: 12px">
      <v-btn
        variant="tonal"
        color="primary"
        prepend-icon="mdi-arrow-left"
        @click="router.push('/extension#installed')"
      >
        {{ tm("buttons.back") }}
      </v-btn>

      <div>
        <div class="text-h2 mb-1">
          {{ webui?.display_name || tm("buttons.openWebUI") }}
        </div>
        <div class="text-body-2 text-medium-emphasis">
          {{ plugin?.display_name || plugin?.name || pluginName }}
        </div>
      </div>
    </div>

    <v-card class="plugin-webui-card" elevation="0">
      <v-card-text class="pa-0">
        <div v-if="loading" class="plugin-webui-state">
          <v-progress-circular indeterminate color="primary" />
          <span>{{ tm("status.loading") }}</span>
        </div>

        <div v-else-if="errorMessage" class="pa-6">
          <v-alert type="error" variant="tonal">
            {{ errorMessage }}
          </v-alert>
        </div>

        <iframe
          v-else
          ref="iframeRef"
          :src="iframeSrc"
          class="plugin-webui-frame"
          referrerpolicy="no-referrer"
          sandbox="allow-scripts allow-forms allow-downloads"
          @load="handleIframeLoad"
        ></iframe>
      </v-card-text>
    </v-card>
  </div>
</template>

<style scoped>
.plugin-webui-card {
  background-color: rgb(var(--v-theme-surface));
  border-radius: 16px;
  overflow: hidden;
}

.plugin-webui-frame {
  width: 100%;
  min-height: calc(100vh - 220px);
  border: 0;
  background: transparent;
}

.plugin-webui-state {
  min-height: calc(100vh - 220px);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
</style>
