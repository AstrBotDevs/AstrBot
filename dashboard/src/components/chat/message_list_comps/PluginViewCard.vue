<template>
  <div class="plugin-view-card" :class="{ 'workbench-view': workbench }">
    <iframe
      v-if="srcdoc"
      ref="frame"
      :srcdoc="srcdoc"
      :style="{ height: workbench ? '100%' : `${height}px` }"
      sandbox="allow-scripts"
      :title="String(part.title || part.name || 'Plugin view')"
    />
    <div v-else class="plugin-view-fallback">
      <p>{{ part.text }}</p>
      <span v-if="error" role="status">{{ tm("pluginView.unavailable") }}</span>
      <span v-else>{{ tm("pluginView.loading") }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { inject, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useTheme } from "vuetify";
import { fetchWithAuth } from "@/api/http";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { viewActionKey, type ViewActionHandler } from "@/utils/chatViews";
import type { MessagePart } from "@/composables/useMessages";

const props = defineProps<{
  part: MessagePart;
  isDark?: boolean;
  workbench?: boolean;
  actionHandler?: ViewActionHandler;
}>();
const frame = ref<HTMLIFrameElement>();
const srcdoc = ref("");
const error = ref(false);
const height = ref(240);
const { locale } = useI18n();
const theme = useTheme();
const { tm } = useModuleI18n("features/chat");
const runAction = inject(viewActionKey, undefined);
const session =
  crypto.randomUUID?.() ||
  Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
let snapshot: { data: Record<string, unknown>; revision: number };
let viewContext: Record<string, unknown> = {};
let disposed = false;

function send(message: Record<string, unknown>) {
  frame.value?.contentWindow?.postMessage(
    { channel: "astrbot-plugin-page", session, ...message },
    "*",
  );
}

async function receive(event: MessageEvent) {
  if (
    event.source !== frame.value?.contentWindow ||
    event.data?.channel !== "astrbot-plugin-page" ||
    (event.origin !== "null" && event.origin !== window.location.origin)
  )
    return;
  const message = event.data;
  if (message.kind === "ready" && snapshot) {
    send({
      kind: "context",
      context: {
        ...viewContext,
        target: viewContext.target || props.part.target || "chat_message",
        view: { id: String(props.part.id), ...snapshot },
        isDark: props.isDark ?? theme.global.current.value.dark,
        themeColors: { ...theme.global.current.value.colors },
        locale: locale.value,
      },
    });
  } else if (message.kind === "resize" && message.session === session) {
    if (typeof message.height === "number" && Number.isFinite(message.height))
      height.value = Math.max(80, Math.min(1000, message.height));
  } else if (message.kind === "request" && message.session === session) {
    try {
      if (message.action !== "view:action")
        throw Object.assign(
          new Error("This capability is unavailable in chat views."),
          { code: "UNSUPPORTED_CAPABILITY" },
        );
      const action = props.actionHandler || runAction;
      if (!action) throw new Error("This chat cannot handle view actions.");
      const receipt = await action(String(props.part.id), message.input);
      if (receipt.snapshot) snapshot = receipt.snapshot;
      send({
        kind: "response",
        requestId: message.requestId,
        ok: !receipt.error,
        error: receipt.error,
        snapshot: receipt.snapshot
          ? { id: String(props.part.id), ...receipt.snapshot }
          : undefined,
      });
    } catch (failure: any) {
      if (failure.snapshot) snapshot = failure.snapshot;
      send({
        kind: "response",
        requestId: message.requestId,
        ok: false,
        snapshot: failure.snapshot
          ? { id: String(props.part.id), ...failure.snapshot }
          : undefined,
        error: {
          code: failure.code || "ACTION_OUTCOME_UNKNOWN",
          message: failure.message || "The action outcome is unknown.",
        },
      });
    }
  }
}

watch(
  () => [props.isDark, locale.value, theme.global.current.value],
  () => {
    if (snapshot)
      send({
        kind: "context",
        context: {
          isDark: props.isDark ?? theme.global.current.value.dark,
          themeColors: { ...theme.global.current.value.colors },
          locale: locale.value,
        },
      });
  },
  { deep: true },
);

onMounted(async () => {
  window.addEventListener("message", receive);
  try {
    const [response, bridgeResponse] = await Promise.all([
      fetchWithAuth(
        `/api/v1/chat/views/${encodeURIComponent(String(props.part.id))}`,
      ),
      fetchWithAuth("/api/plugin/page/bridge-sdk.js"),
    ]);
    if (!response.ok) throw new Error("View unavailable.");
    if (!bridgeResponse.ok) throw new Error("View bridge unavailable.");
    const { data } = await response.json();
    const bridgeSource = await bridgeResponse.text();
    if (disposed) return;
    snapshot = { data: data.data, revision: data.revision };
    viewContext = {
      ...data.context,
      pageName: props.part.name,
      pageTitle: props.part.title || data.context?.pageTitle || props.part.name,
      target: data.target || props.part.target || "chat_message",
    };
    const document = new DOMParser().parseFromString(data.html, "text/html");
    document.querySelectorAll("base").forEach((element) => element.remove());
    const base = document.createElement("base");
    base.href = new URL(data.base_url, window.location.origin).href;
    const script = document.createElement("script");
    script.textContent = bridgeSource;
    document.head.prepend(base, script);
    srcdoc.value = "<!doctype html>" + document.documentElement.outerHTML;
  } catch {
    error.value = true;
  }
});

onBeforeUnmount(() => {
  disposed = true;
  window.removeEventListener("message", receive);
});
</script>

<style scoped>
.plugin-view-card {
  margin: 12px 0;
  overflow: hidden;
  background: transparent;
}
iframe {
  display: block;
  width: 100%;
  background: transparent;
  border: 0;
}
.plugin-view-card.workbench-view {
  margin: 0;
  height: 100%;
  min-height: 0;
}
.plugin-view-fallback {
  padding: 12px;
}
.plugin-view-fallback span {
  opacity: 0.65;
  font-size: 12px;
}
</style>
