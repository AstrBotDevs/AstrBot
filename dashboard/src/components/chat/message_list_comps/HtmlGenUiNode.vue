<template>
  <div class="html-genui-node" :class="{ 'is-dark': isDark, 'is-loading': isLoading }">
    <div class="html-genui-header">
      <div class="html-genui-title">{{ panelTitle }}</div>
      <div class="html-genui-toggle" role="tablist" aria-label="HTML GenUI view">
        <button
          class="html-genui-toggle-button"
          :class="{ active: viewMode === 'preview' }"
          type="button"
          role="tab"
          :aria-selected="viewMode === 'preview'"
          @click="viewMode = 'preview'"
        >
          Preview
        </button>
        <button
          class="html-genui-toggle-button"
          :class="{ active: viewMode === 'source' }"
          type="button"
          role="tab"
          :aria-selected="viewMode === 'source'"
          @click="viewMode = 'source'"
        >
          Source
        </button>
      </div>
    </div>

    <iframe
      v-if="viewMode === 'preview'"
      class="html-genui-frame"
      :srcdoc="renderedSrcdoc"
      :sandbox="sandboxPolicy"
      title="Generated HTML UI preview"
      loading="lazy"
    ></iframe>
    <pre v-else class="html-genui-source"><code>{{ htmlContent }}</code></pre>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";

const RENDER_THROTTLE_MS = 500;
const sandboxPolicy =
  "allow-forms allow-modals allow-pointer-lock allow-popups allow-scripts";

const props = defineProps<{
  node?: {
    attrs?: Array<[string, string]>;
    content?: string;
    raw?: string;
    loading?: boolean;
  } | null;
  loading?: boolean;
  isDark?: boolean;
  title?: string;
}>();

const renderedSrcdoc = ref("");
const viewMode = ref<"preview" | "source">("preview");
let pendingTimer: ReturnType<typeof setTimeout> | null = null;
let lastRenderAt = 0;

const htmlContent = computed(() =>
  stripHtmlGenUiWrapper(String(props.node?.content || props.node?.raw || "")),
);
const isLoading = computed(() => Boolean(props.loading || props.node?.loading));
const isDark = computed(() => Boolean(props.isDark));
const panelTitle = computed(
  () => props.title?.trim() || attrValue("title") || "HTML UI",
);

watch(
  [htmlContent, isLoading, isDark],
  () => {
    scheduleRender(!isLoading.value);
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  if (pendingTimer) {
    clearTimeout(pendingTimer);
    pendingTimer = null;
  }
});

function scheduleRender(force = false) {
  if (force) {
    renderNow();
    return;
  }

  const elapsed = Date.now() - lastRenderAt;
  if (elapsed >= RENDER_THROTTLE_MS) {
    renderNow();
    return;
  }

  if (!pendingTimer) {
    pendingTimer = setTimeout(renderNow, RENDER_THROTTLE_MS - elapsed);
  }
}

function renderNow() {
  if (pendingTimer) {
    clearTimeout(pendingTimer);
    pendingTimer = null;
  }
  lastRenderAt = Date.now();
  renderedSrcdoc.value = buildSrcdoc(htmlContent.value, isDark.value);
}

function stripHtmlGenUiWrapper(value: string) {
  return value
    .replace(/^\s*<html-genui\b[^>]*>/i, "")
    .replace(/<\/html-genui>\s*$/i, "")
    .trim();
}

function attrValue(name: string) {
  const attr = props.node?.attrs?.find(
    ([key]) => key.toLowerCase() === name.toLowerCase(),
  );
  return attr?.[1]?.trim() || "";
}

function buildSrcdoc(content: string, dark: boolean) {
  const headExtras = buildHeadExtras(dark);
  if (/<html[\s>]/i.test(content)) {
    return injectHeadExtras(content, headExtras);
  }

  return `<!doctype html>
<html>
<head>${headExtras}</head>
<body>${content}</body>
</html>`;
}

function injectHeadExtras(html: string, headExtras: string) {
  if (/<head[\s>]/i.test(html)) {
    return html.replace(/<head([^>]*)>/i, `<head$1>${headExtras}`);
  }
  if (/<html[\s>]/i.test(html)) {
    return html.replace(/<html([^>]*)>/i, `<html$1><head>${headExtras}</head>`);
  }
  return `<!doctype html><html><head>${headExtras}</head><body>${html}</body></html>`;
}

function buildHeadExtras(dark: boolean) {
  const bg = dark ? "#111827" : "#ffffff";
  const fg = dark ? "#f9fafb" : "#111827";
  return `<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<base target="_blank">
<style>
  :root { color-scheme: ${dark ? "dark" : "light"}; }
  * { box-sizing: border-box; }
  html, body { min-height: 100%; margin: 0; }
  body {
    background: ${bg};
    color: ${fg};
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  img, video, canvas, svg { max-width: 100%; }
</style>`;
}
</script>

<style scoped>
.html-genui-node {
  width: 100%;
  margin: 12px 0;
  overflow: hidden;
  border: 1px solid rgba(128, 128, 128, 0.24);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
}

.html-genui-node.is-dark {
  border-color: rgba(160, 160, 160, 0.28);
}

.html-genui-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 42px;
  padding: 8px 10px 8px 12px;
  border-bottom: 1px solid rgba(128, 128, 128, 0.2);
  background: rgba(128, 128, 128, 0.04);
}

.html-genui-title {
  min-width: 0;
  overflow: hidden;
  color: rgba(var(--v-theme-on-surface), 0.84);
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.html-genui-toggle {
  display: inline-flex;
  flex: 0 0 auto;
  overflow: hidden;
  border: 1px solid rgba(128, 128, 128, 0.22);
  border-radius: 6px;
  background: rgba(128, 128, 128, 0.06);
}

.html-genui-toggle-button {
  min-width: 64px;
  border: 0;
  border-right: 1px solid rgba(128, 128, 128, 0.2);
  padding: 4px 10px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.68);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
}

.html-genui-toggle-button:focus {
  outline: none;
}

.html-genui-toggle-button:focus-visible {
  outline: 2px solid rgba(128, 128, 128, 0.36);
  outline-offset: -2px;
}

.html-genui-toggle-button:last-child {
  border-right: 0;
}

.html-genui-toggle-button.active {
  background: rgba(128, 128, 128, 0.16);
  color: rgba(var(--v-theme-on-surface), 0.92);
}

.html-genui-frame {
  display: block;
  width: 100%;
  height: clamp(280px, 52vh, 620px);
  border: 0;
  background: #fff;
}

.html-genui-node.is-loading .html-genui-frame {
  opacity: 0.96;
}

.html-genui-source {
  height: clamp(280px, 52vh, 620px);
  margin: 0;
  overflow: auto;
  padding: 14px;
  background: rgba(var(--v-theme-on-surface), 0.035);
  color: rgba(var(--v-theme-on-surface), 0.86);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
    "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.55;
  tab-size: 2;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
