<script setup>
import { ref, watch, computed, nextTick } from "vue";
import axios from "axios";
import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";
import hljs from "highlight.js";
import "highlight.js/styles/github-dark.css";
import { useI18n } from "@/i18n/composables";

// 定义在 setup 中以便访问 i18n
let md = null;

// 初始化 renderer 的函数（将在 setup 中调用）
const initMarkdownIt = (t) => {
  md = new MarkdownIt({
    html: true,
    linkify: true,
    typographer: true,
    breaks: false,
    highlight: function (str, lang) {
      if (lang && hljs.getLanguage(lang)) {
        try {
          return `<pre class="hljs"><code class="language-${lang}">${
            hljs.highlight(str, { language: lang }).value
          }</code></pre>`;
        } catch (__) {}
      }
      return `<pre class="hljs"><code>${md.utils.escapeHtml(str)}</code></pre>`;
    },
  });

  md.enable(["table", "strikethrough"]);

  // 自定义表格渲染规则：添加滚动容器
  md.renderer.rules.table_open = () => '<div class="table-container"><table>';
  md.renderer.rules.table_close = () => "</table></div>";

  // 自定义渲染规则
  md.renderer.rules.fence = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const lang = token.info.trim() || "";
    const code = token.content;

    let highlighted;
    if (lang && hljs.getLanguage(lang)) {
      try {
        highlighted = hljs.highlight(code, { language: lang }).value;
      } catch (__) {
        highlighted = md.utils.escapeHtml(code);
      }
    } else {
      highlighted = md.utils.escapeHtml(code);
    }

    const langLabel = lang
      ? `<span class="code-lang-label">${lang}</span>`
      : "";

    return `<div class="code-block-wrapper">
    ${langLabel}
    <button class="copy-code-btn" title="${t("core.common.copy")}">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
      </svg>
    </button>
    <pre class="hljs"><code class="language-${lang}">${highlighted}</code></pre>
  </div>`;
  };
};

// 配置 DOMPurify 允许的标签和属性
const purifyConfig = {
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
    "input", // 用于复选框
    "button",
    "svg",
    "rect",
    "path",
    "polyline", // 用于复制成功的图标
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
    "disabled", // 用于复选框
    "open", // 用于 details
    "align", // 用于居中（尊重原始 Markdown 意图）
    "width",
    "height",
    "viewBox",
    "fill",
    "stroke",
    "stroke-width",
    "points", // 用于 polyline
    "d",
    "x",
    "y",
    "rx",
    "ry", // SVG 属性
  ],
  ADD_ATTR: ["target"], // 允许添加 target 属性
};

const props = defineProps({
  show: {
    type: Boolean,
    default: false,
  },
  pluginName: {
    type: String,
    default: "",
  },
  repoUrl: {
    type: String,
    default: null,
  },
  // 模式: 'readme' 或 'changelog'
  mode: {
    type: String,
    default: "readme",
    validator: (value) => ["readme", "changelog"].includes(value),
  },
});

const emit = defineEmits(["update:show"]);

// 国际化
const { t } = useI18n();

// 初始化 markdown-it
initMarkdownIt(t);

const content = ref(null);
const error = ref(null);
const loading = ref(false);
const isEmpty = ref(false); // 请求成功但无内容
const markdownContainer = ref(null);

// 渲染后的 HTML
const renderedHtml = computed(() => {
  if (!content.value || !md) return "";
  const rawHtml = md.render(content.value);
  const cleanHtml = DOMPurify.sanitize(rawHtml, purifyConfig);

  // 手动处理链接，避免全局 hook 污染
  // 创建一个临时容器来解析 HTML
  const tempDiv = document.createElement("div");
  tempDiv.innerHTML = cleanHtml;

  // 查找所有链接并添加 target="_blank"
  const links = tempDiv.querySelectorAll("a");
  links.forEach((link) => {
    const href = link.getAttribute("href");
    if (href && (href.startsWith("http://") || href.startsWith("https://"))) {
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    }
  });

  return tempDiv.innerHTML;
});

// 根据模式返回不同的配置
const modeConfig = computed(() => {
  if (props.mode === "changelog") {
    return {
      title: t("core.common.changelog.title"),
      loading: t("core.common.changelog.loading"),
      emptyTitle: t("core.common.changelog.empty.title"),
      emptySubtitle: t("core.common.changelog.empty.subtitle"),
      apiPath: "/api/plugin/changelog",
    };
  }
  return {
    title: t("core.common.readme.title"),
    loading: t("core.common.readme.loading"),
    emptyTitle: t("core.common.readme.empty.title"),
    emptySubtitle: t("core.common.readme.empty.subtitle"),
    apiPath: "/api/plugin/readme",
  };
});

// 监听show的变化，当显示对话框时加载内容
watch(
  () => props.show,
  (newVal) => {
    if (newVal && props.pluginName) {
      fetchContent();
    }
  },
);

// 监听pluginName的变化
watch(
  () => props.pluginName,
  (newVal) => {
    if (props.show && newVal) {
      fetchContent();
    }
  },
);

// 监听mode的变化
watch(
  () => props.mode,
  () => {
    if (props.show && props.pluginName) {
      fetchContent();
    }
  },
);

// 监听 renderedHtml 变化，初始化复制按钮
watch(renderedHtml, () => {
  nextTick(() => {
    initCopyButtons();
  });
});

// 初始化复制按钮
function initCopyButtons() {
  if (!markdownContainer.value) return;

  const copyButtons =
    markdownContainer.value.querySelectorAll(".copy-code-btn");

  copyButtons.forEach((btn) => {
    btn.addEventListener("click", handleCopyCode);
  });
}

// 处理复制代码
function handleCopyCode(event) {
  const btn = event.currentTarget;
  const wrapper = btn.closest(".code-block-wrapper");
  const code = wrapper.querySelector("code");

  if (code) {
    navigator.clipboard
      .writeText(code.textContent)
      .then(() => {
        // 显示成功状态
        btn.setAttribute("title", t("core.common.copied")); // 使用 i18n
        btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="20,6 9,17 4,12"></polyline>
      </svg>`;
        btn.style.color = "#4caf50";

        setTimeout(() => {
          btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>`;
          btn.style.color = "";
        }, 2000);
        setTimeout(() => {
          btn.setAttribute("title", t("core.common.copy")); // 还原 title
        }, 2000);
      })
      .catch((err) => {
        console.error("复制失败:", err);
      });
  }
}

// 获取内容
async function fetchContent() {
  if (!props.pluginName) return;

  loading.value = true;
  content.value = null;
  error.value = null;
  isEmpty.value = false;

  try {
    const res = await axios.get(
      `${modeConfig.value.apiPath}?name=${props.pluginName}`,
    );
    if (res.data.status === "ok") {
      if (res.data.data.content) {
        content.value = res.data.data.content;
      } else {
        // 请求成功但无内容
        isEmpty.value = true;
      }
    } else {
      error.value = res.data.message;
    }
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
}

// 打开GitHub中的仓库
function openRepoInNewTab() {
  if (props.repoUrl) {
    window.open(props.repoUrl, "_blank");
  }
}

// 刷新内容
function refreshContent() {
  fetchContent();
}

// 计算属性处理双向绑定
const _show = computed({
  get() {
    return props.show;
  },
  set(value) {
    emit("update:show", value);
  },
});
</script>

<template>
  <v-dialog v-model="_show" width="800">
    <v-card>
      <v-card-title class="d-flex justify-space-between align-center">
        <span class="text-h5">{{ modeConfig.title }}</span>
        <v-btn icon @click="$emit('update:show', false)" variant="text">
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
            @click="openRepoInNewTab()"
          >
            {{ t("core.common.readme.buttons.viewOnGithub") }}
          </v-btn>
          <v-btn
            color="secondary"
            prepend-icon="mdi-refresh"
            @click="refreshContent()"
          >
            {{ t("core.common.readme.buttons.refresh") }}
          </v-btn>
        </div>

        <!-- 加载中 -->
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

        <!-- 内容显示 -->
        <div
          v-else-if="renderedHtml"
          ref="markdownContainer"
          class="markdown-body"
          v-html="renderedHtml"
        ></div>

        <!-- 错误提示 -->
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

        <!-- 无内容提示 -->
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
        <v-btn
          color="primary"
          variant="tonal"
          @click="$emit('update:show', false)"
        >
          {{ t("core.common.close") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style>
.markdown-body {
  font-family:
    -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  line-height: 1.6;
  padding: 8px 0;
  color: var(--v-theme-secondaryText);
}

/* 支持 align 属性居中 */
.markdown-body [align="center"] {
  text-align: center;
}

.markdown-body [align="right"] {
  text-align: right;
}

/* 标题样式 */
.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4,
.markdown-body h5,
.markdown-body h6 {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.25;
}

.markdown-body h1 {
  font-size: 2em;
  border-bottom: 1px solid var(--v-theme-border);
  padding-bottom: 0.3em;
}

.markdown-body h2 {
  font-size: 1.5em;
  border-bottom: 1px solid var(--v-theme-border);
  padding-bottom: 0.3em;
}

.markdown-body p {
  margin-top: 0;
  margin-bottom: 16px;
}

/* 代码块容器 */
.markdown-body .code-block-wrapper {
  position: relative;
  margin-bottom: 16px;
}

.markdown-body .code-lang-label {
  position: absolute;
  top: 8px;
  left: 12px;
  font-size: 12px;
  color: #8b949e;
  text-transform: uppercase;
  font-weight: 500;
  z-index: 1;
}

.markdown-body .copy-code-btn {
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

.markdown-body .copy-code-btn:hover {
  background: rgba(110, 118, 129, 0.6);
  color: #fff;
}

.markdown-body code {
  padding: 0.2em 0.4em;
  margin: 0;
  background-color: rgba(110, 118, 129, 0.4);
  border-radius: 6px;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 85%;
}

.markdown-body pre.hljs {
  padding: 16px;
  padding-top: 32px;
  overflow: auto;
  font-size: 85%;
  line-height: 1.45;
  background-color: #0d1117;
  border-radius: 6px;
  margin: 0;
}

.markdown-body pre.hljs code {
  background-color: transparent;
  padding: 0;
  border-radius: 0;
  color: #c9d1d9;
}

.markdown-body ul,
.markdown-body ol {
  padding-left: 2em;
  margin-bottom: 16px;
}

.markdown-body img {
  max-width: 100%;
  margin: 8px 0;
  box-sizing: border-box;
  background-color: var(--v-theme-background);
  border-radius: 3px;
}

/* Shields.io 徽章样式 */
.markdown-body img[src*="shields.io"],
.markdown-body img[src*="badge"] {
  display: inline-block;
  vertical-align: middle;
  height: auto;
  margin: 2px 4px;
  background-color: transparent;
}

.markdown-body blockquote {
  padding: 0 1em;
  color: var(--v-theme-secondaryText);
  border-left: 0.25em solid var(--v-theme-border);
  margin-bottom: 16px;
}

.markdown-body a {
  color: var(--v-theme-primary);
  text-decoration: none;
}

.markdown-body a:hover {
  text-decoration: underline;
}

.markdown-body table {
  border-spacing: 0;
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 0; /* margin 交给 container */
  border: none; /* border 交给 container */
}

.markdown-body .table-container {
  width: 100%;
  overflow-x: auto;
  margin-bottom: 16px;
  border: 1px solid #30363d;
  border-radius: 6px;
}

.markdown-body table th,
.markdown-body table td {
  padding: 6px 13px;
  border: 1px solid #30363d;
}

.markdown-body table th {
  font-weight: 600;
  background-color: rgba(110, 118, 129, 0.1);
}

.markdown-body table tr {
  background-color: transparent;
  border-top: 1px solid #30363d;
}

.markdown-body table tr:nth-child(2n) {
  background-color: rgba(110, 118, 129, 0.05);
}

.markdown-body hr {
  height: 0.25em;
  padding: 0;
  margin: 24px 0;
  background-color: var(--v-theme-containerBg);
  border: 0;
}

/* 折叠内容样式 */
.markdown-body details {
  margin-bottom: 16px;
  border: 1px solid var(--v-theme-border);
  border-radius: 6px;
  padding: 8px 12px;
  background-color: var(--v-theme-surface);
}

.markdown-body details[open] {
  padding-bottom: 12px;
}

.markdown-body summary {
  cursor: pointer;
  font-weight: 600;
  padding: 4px 0;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.markdown-body summary::before {
  content: "▶";
  font-size: 0.75em;
  transition: transform 0.2s ease;
}

.markdown-body details[open] summary::before {
  transform: rotate(90deg);
}

.markdown-body summary::-webkit-details-marker {
  display: none;
}

.markdown-body details > *:not(summary) {
  margin-top: 12px;
}

/* 高亮样式覆盖 - 确保正确显示 */
.markdown-body .hljs-keyword,
.markdown-body .hljs-selector-tag,
.markdown-body .hljs-title,
.markdown-body .hljs-section,
.markdown-body .hljs-doctag,
.markdown-body .hljs-name,
.markdown-body .hljs-strong {
  font-weight: bold;
}
</style>

<script>
export default {
  name: "ReadmeDialog",
};
</script>
