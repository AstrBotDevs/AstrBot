<script setup>
import { ref, watch, computed, onUnmounted } from "vue";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js";
import axios from "axios";
import DOMPurify from "dompurify";
import "highlight.js/styles/github-dark.css";
import { useI18n } from "@/i18n/composables";

// 1. 在 setup 作用域创建 MarkdownIt 实例
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: false,
});

md.enable(["table", "strikethrough"]);
md.renderer.rules.table_open = () => '<div class="table-container"><table>';
md.renderer.rules.table_close = () => "</table></div>";

// 2. 复制按钮的 SVG 图标常量
const ICONS = {
  SUCCESS:
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"></polyline></svg>',
  ERROR:
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>',
  COPY: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>',
};

const props = defineProps({
  show: { type: Boolean, default: false },
  pluginName: { type: String, default: "" },
  repoUrl: { type: String, default: null },
  mode: {
    type: String,
    default: "readme",
    validator: (value) => ["readme", "changelog"].includes(value),
  },
});

const emit = defineEmits(["update:show"]);
const { t, locale } = useI18n();

const content = ref(null);
const error = ref(null);
const loading = ref(false);
const isEmpty = ref(false);
const copyFeedbackTimer = ref(null);
const lastRequestId = ref(0);

onUnmounted(() => {
  if (copyFeedbackTimer.value) clearTimeout(copyFeedbackTimer.value);
});

// 渲染后的 HTML
const renderedHtml = computed(() => {
  // 强制依赖 locale，确保语言切换时重新渲染
  const _ = locale?.value;
  if (!content.value) return "";

  // 设置 fence 规则，直接使用当前作用域的 t 函数
  md.renderer.rules.fence = (tokens, idx) => {
    const token = tokens[idx];
    const lang = token.info.trim() || "";
    const code = token.content;

    const highlighted =
      lang && hljs.getLanguage(lang)
        ? hljs.highlight(code, { language: lang }).value
        : md.utils.escapeHtml(code);

    return `<div class="code-block-wrapper">
      ${lang ? `<span class="code-lang-label">${lang}</span>` : ""}
      <button class="copy-code-btn" title="${t("core.common.copy")}">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
      </button>
      <pre class="hljs"><code class="language-${lang}">${highlighted}</code></pre>
    </div>`;
  };

  const rawHtml = md.render(content.value);

  const cleanHtml = DOMPurify.sanitize(rawHtml, {
    ALLOWED_TAGS: [
      "h1",
      "h2",
      "h3",
      "h4",
      "h5",
      "h6",
      "p",
      "br",
      "hr",
      "ul",
      "ol",
      "li",
      "blockquote",
      "pre",
      "code",
      "a",
      "img",
      "table",
      "thead",
      "tbody",
      "tr",
      "th",
      "td",
      "strong",
      "em",
      "del",
      "s",
      "details",
      "summary",
      "div",
      "span",
      "input",
      "button",
      "svg",
      "rect",
      "path",
      "polyline",
    ],
    ALLOWED_ATTR: [
      "href",
      "src",
      "alt",
      "title",
      "class",
      "id",
      "target",
      "rel",
      "type",
      "checked",
      "disabled",
      "open",
      "align",
      "width",
      "height",
      "viewBox",
      "fill",
      "stroke",
      "stroke-width",
      "points",
      "d",
      "x",
      "y",
      "rx",
      "ry",
    ],
  });

  // 3. 后处理方案：完全隔离，安全性最高
  const tempDiv = document.createElement("div");
  tempDiv.innerHTML = cleanHtml;
  tempDiv.querySelectorAll("a").forEach((link) => {
    const href = link.getAttribute("href");
    // 强制所有外部链接使用安全的 _blank 策略
    if (href && (href.startsWith("http") || href.startsWith("//"))) {
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    }
  });

  return tempDiv.innerHTML;
});

const modeConfig = computed(() => {
  const isChangelog = props.mode === "changelog";
  const keyBase = `core.common.${isChangelog ? "changelog" : "readme"}`;
  return {
    title: t(`${keyBase}.title`),
    loading: t(`${keyBase}.loading`),
    emptyTitle: t(`${keyBase}.empty.title`),
    emptySubtitle: t(`${keyBase}.empty.subtitle`),
    apiPath: `/api/plugin/${isChangelog ? "changelog" : "readme"}`,
  };
});

async function fetchContent() {
  if (!props.pluginName) return;
  const requestId = ++lastRequestId.value;
  loading.value = true;
  content.value = null;
  error.value = null;
  isEmpty.value = false;

  try {
    const res = await axios.get(
      `${modeConfig.value.apiPath}?name=${props.pluginName}`,
    );
    if (requestId !== lastRequestId.value) return;

    if (res.data.status === "ok") {
      if (res.data.data.content) content.value = res.data.data.content;
      else isEmpty.value = true;
    } else {
      error.value = res.data.message;
    }
  } catch (err) {
    if (requestId === lastRequestId.value) error.value = err.message;
  } finally {
    if (requestId === lastRequestId.value) loading.value = false;
  }
}

watch(
  [() => props.show, () => props.pluginName, () => props.mode],
  ([show, name]) => {
    if (show && name) fetchContent();
  },
  { immediate: true },
);

function handleContainerClick(event) {
  const btn = event.target.closest(".copy-code-btn");
  if (!btn) return;
  const code = btn.closest(".code-block-wrapper")?.querySelector("code");
  if (code) {
    if (navigator.clipboard?.writeText) {
      navigator.clipboard
        .writeText(code.textContent)
        .then(() => showCopyFeedback(btn, true))
        .catch(() => tryFallbackCopy(code.textContent, btn));
    } else {
      tryFallbackCopy(code.textContent, btn);
    }
  }
}

function tryFallbackCopy(text, btn) {
  try {
    const textArea = document.createElement("textarea");
    textArea.value = text;
    Object.assign(textArea.style, {
      position: "absolute",
      opacity: "0",
      zIndex: "-1",
    });
    btn.parentNode.appendChild(textArea);
    textArea.select();
    const success = document.execCommand("copy");
    btn.parentNode.removeChild(textArea);
    showCopyFeedback(btn, success);
  } catch (err) {
    showCopyFeedback(btn, false);
  }
}

function showCopyFeedback(btn, success) {
  if (copyFeedbackTimer.value) clearTimeout(copyFeedbackTimer.value);
  btn.setAttribute("title", t(`core.common.${success ? "copied" : "error"}`));
  btn.innerHTML = success ? ICONS.SUCCESS : ICONS.ERROR;
  btn.style.color = success ? "var(--v-theme-success)" : "var(--v-theme-error)";

  copyFeedbackTimer.value = setTimeout(() => {
    if (document.body.contains(btn)) {
      btn.innerHTML = ICONS.COPY;
      btn.style.color = "";
      btn.setAttribute("title", t("core.common.copy"));
    }
    copyFeedbackTimer.value = null;
  }, 2000);
}

const _show = computed({
  get: () => props.show,
  set: (val) => emit("update:show", val),
});

// 安全打开外部链接
function openExternalLink(url) {
  if (!url) return;
  window.open(url, "_blank", "noopener,noreferrer");
}
</script>

<template>
  <v-dialog v-model="_show" width="800">
    <v-card>
      <v-card-title class="d-flex justify-space-between align-center">
        <span class="text-h5">{{ modeConfig.title }}</span>
        <v-btn icon @click="_show = false" variant="text">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text style="height: 70vh; overflow-y: auto">
        <div class="d-flex justify-space-between mb-4">
          <v-btn
            v-if="repoUrl"
            color="primary"
            prepend-icon="mdi-github"
            @click="openExternalLink(repoUrl)"
          >
            {{ t("core.common.readme.buttons.viewOnGithub") }}
          </v-btn>
          <v-btn
            color="secondary"
            prepend-icon="mdi-refresh"
            @click="fetchContent"
          >
            {{ t("core.common.readme.buttons.refresh") }}
          </v-btn>
        </div>

        <div
          v-if="loading"
          class="d-flex flex-column align-center justify-center"
          style="height: 100%"
        >
          <v-progress-circular
            indeterminate
            color="primary"
            size="64"
            class="mb-4"
          ></v-progress-circular>
          <p class="text-body-1 text-center">{{ modeConfig.loading }}</p>
        </div>

        <div
          v-else-if="renderedHtml"
          class="markdown-body"
          v-html="renderedHtml"
          @click="handleContainerClick"
        ></div>

        <div
          v-else-if="error"
          class="d-flex flex-column align-center justify-center"
          style="height: 100%"
        >
          <v-icon size="64" color="error" class="mb-4"
            >mdi-alert-circle-outline</v-icon
          >
          <p class="text-body-1 text-center mb-2">
            {{ t("core.common.error") }}
          </p>
          <p class="text-body-2 text-center text-medium-emphasis">
            {{ error }}
          </p>
        </div>

        <div
          v-else-if="isEmpty"
          class="d-flex flex-column align-center justify-center"
          style="height: 100%"
        >
          <v-icon size="64" color="warning" class="mb-4"
            >mdi-file-question-outline</v-icon
          >
          <p class="text-body-1 text-center mb-2">
            {{ modeConfig.emptyTitle }}
          </p>
          <p class="text-body-2 text-center text-medium-emphasis">
            {{ modeConfig.emptySubtitle }}
          </p>
        </div>
      </v-card-text>
      <v-divider></v-divider>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="primary" variant="tonal" @click="_show = false">
          {{ t("core.common.close") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
:deep(.markdown-body) {
  --markdown-border: rgba(128, 128, 128, 0.3);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial,
    sans-serif;
  line-height: 1.6;
  padding: 8px 0;
  color: var(--v-theme-secondaryText);
}

:deep(.markdown-body [align="center"]) {
  text-align: center;
}
:deep(.markdown-body [align="right"]) {
  text-align: right;
}

:deep(.markdown-body h1),
:deep(.markdown-body h2),
:deep(.markdown-body h3),
:deep(.markdown-body h4),
:deep(.markdown-body h5),
:deep(.markdown-body h6) {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.25;
}

:deep(.markdown-body h1) {
  font-size: 2em;
  border-bottom: 1px solid var(--v-theme-border);
  padding-bottom: 0.3em;
}
:deep(.markdown-body h2) {
  font-size: 1.5em;
  border-bottom: 1px solid var(--v-theme-border);
  padding-bottom: 0.3em;
}
:deep(.markdown-body p) {
  margin-top: 0;
  margin-bottom: 16px;
}

:deep(.markdown-body .code-block-wrapper) {
  position: relative;
  margin-bottom: 16px;
}
:deep(.markdown-body .code-lang-label) {
  position: absolute;
  top: 8px;
  left: 12px;
  font-size: 12px;
  color: #8b949e;
  text-transform: uppercase;
  font-weight: 500;
  z-index: 1;
}

:deep(.markdown-body .copy-code-btn) {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(110, 118, 129, 0.4);
  border: none;
  border-radius: 6px;
  padding: 6px;
  cursor: pointer;
  color: #c9d1d9;
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    background-color 0.2s,
    color 0.2s;
  z-index: 1;
}

:deep(.markdown-body .copy-code-btn:hover) {
  background: rgba(110, 118, 129, 0.6);
  color: #fff;
}

:deep(.markdown-body code) {
  padding: 0.2em 0.4em;
  margin: 0;
  background-color: rgba(110, 118, 129, 0.2);
  border-radius: 6px;
  font-size: 85%;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

:deep(.markdown-body pre.hljs) {
  padding: 16px;
  padding-top: 32px;
  overflow: auto;
  font-size: 85%;
  line-height: 1.45;
  background-color: #0d1117;
  border-radius: 6px;
  margin: 0;
}

:deep(.markdown-body pre.hljs code) {
  background-color: transparent;
  padding: 0;
  border-radius: 0;
  color: #c9d1d9;
}
:deep(.markdown-body ul),
:deep(.markdown-body ol) {
  padding-left: 2em;
  margin-bottom: 16px;
}

:deep(.markdown-body img) {
  max-width: 100%;
  margin: 8px 0;
  box-sizing: border-box;
  background-color: var(--v-theme-background);
  border-radius: 3px;
}

:deep(.markdown-body img[src*="shields.io"]),
:deep(.markdown-body img[src*="badge"]) {
  display: inline-block;
  vertical-align: middle;
  height: auto;
  margin: 2px 4px;
  background-color: transparent;
}

:deep(.markdown-body blockquote) {
  padding: 0 1em;
  color: var(--v-theme-secondaryText);
  border-left: 0.25em solid var(--v-theme-border);
  margin-bottom: 16px;
}

:deep(.markdown-body a) {
  color: var(--v-theme-primary);
  text-decoration: none;
}
:deep(.markdown-body a:hover) {
  text-decoration: underline;
}

:deep(.markdown-body table) {
  border-spacing: 0;
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 0;
  border: 1px solid var(--markdown-border);
}
:deep(.markdown-body .table-container) {
  width: 100%;
  overflow-x: auto;
  margin-bottom: 16px;
  border: 1px solid var(--markdown-border);
  border-radius: 6px;
}

:deep(.markdown-body table th),
:deep(.markdown-body table td) {
  padding: 6px 13px;
  border: 1px solid var(--markdown-border);
}
:deep(.markdown-body table th) {
  font-weight: 600;
  background-color: rgba(128, 128, 128, 0.1);
}
:deep(.markdown-body table tr) {
  background-color: transparent;
}
:deep(.markdown-body table tr:nth-child(2n)) {
  background-color: rgba(128, 128, 128, 0.05);
}

:deep(.markdown-body hr) {
  height: 0.25em;
  padding: 0;
  margin: 24px 0;
  background-color: var(--v-theme-containerBg);
  border: 0;
}

:deep(.markdown-body details) {
  margin-bottom: 16px;
  border: 1px solid var(--v-theme-border);
  border-radius: 6px;
  padding: 8px 12px;
  background-color: var(--v-theme-surface);
}

:deep(.markdown-body details[open]) {
  padding-bottom: 12px;
}
:deep(.markdown-body summary) {
  cursor: pointer;
  font-weight: 600;
  padding: 4px 0;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

:deep(.markdown-body summary::before) {
  content: "▶";
  font-size: 0.75em;
  transition: transform 0.2s ease;
}
:deep(.markdown-body details[open] summary::before) {
  transform: rotate(90deg);
}
:deep(.markdown-body summary::-webkit-details-marker) {
  display: none;
}
:deep(.markdown-body details > *:not(summary)) {
  margin-top: 12px;
}

:deep(.markdown-body .hljs-keyword),
:deep(.markdown-body .hljs-selector-tag),
:deep(.markdown-body .hljs-title),
:deep(.markdown-body .hljs-section),
:deep(.markdown-body .hljs-doctag),
:deep(.markdown-body .hljs-name),
:deep(.markdown-body .hljs-strong) {
  font-weight: bold;
}
</style>
