<script setup>
import { ref, watch, onMounted, computed } from 'vue';
import axios from 'axios';
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import 'highlight.js/styles/github.css';
import { useI18n } from '@/i18n/composables';

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  pluginName: {
    type: String,
    default: ''
  },
  repoUrl: {
    type: String,
    default: null
  }
});

const emit = defineEmits(['update:show']);

// 国际化
const { t } = useI18n();

const content = ref(null);
const error = ref(null);
const loading = ref(false);

// 监听show的变化，当显示对话框时加载内容
watch(() => props.show, (newVal) => {
  if (newVal && props.pluginName) {
    fetchReadme();
  }
});

// 监听pluginName的变化
watch(() => props.pluginName, (newVal) => {
  if (props.show && newVal) {
    fetchReadme();
  }
});

// 获取README内容
async function fetchReadme() {
  if (!props.pluginName) return;
  
  loading.value = true;
  content.value = null;
  error.value = null;
  
  try {
    // 从本地文件获取README
    const res = await axios.get(`/api/plugin/readme?name=${props.pluginName}`);
    if (res.data.status === 'ok') {
      content.value = res.data.data.content;
    } else {
      error.value = res.data.message || t('core.common.readme.errors.fetchFailed');
    }
  } catch (err) {
    error.value = err.message || t('core.common.readme.errors.fetchError');
  } finally {
    loading.value = false;
  }
}

// 打开GitHub中的仓库
function openRepoInNewTab() {
  if (props.repoUrl) {
    window.open(props.repoUrl, '_blank');
  }
}

// 配置markdown-it，启用代码高亮
const md = new MarkdownIt({
  html: true,        // 启用HTML标签
  breaks: true,       // 换行转<br>
  linkify: true,      // 自动转链接
  typographer: false, // 禁用智能引号
  highlight: function(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value;
      } catch (e) {
        console.error(e);
      }
    }
    return hljs.highlightAuto(code).value;
  }
});

// 渲染Markdown内容
function renderMarkdown(content) {
  if (!content) return '';
  return md.render(content);
}

// 刷新README内容
function refreshReadme() {
  fetchReadme();
}

// 计算属性处理双向绑定
const _show = computed({
  get() {
    return props.show;
  },
  set(value) {
    emit('update:show', value);
  }
});
</script>

<template>
  <v-dialog v-model="_show" width="800" persistent>
    <v-card>
      <v-card-title class="d-flex justify-space-between align-center">
        <span class="text-h5">{{ t('core.common.readme.title') }}</span>
        <v-btn icon @click="$emit('update:show', false)" variant="text">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text style="height: 70vh; overflow-y: auto;">
        <div class="d-flex justify-space-between mb-4">
          <v-btn 
            v-if="repoUrl"
            color="primary" 
            prepend-icon="mdi-github"
            @click="openRepoInNewTab()" 
          >
            {{ t('core.common.readme.buttons.viewOnGithub') }}
          </v-btn>
          <v-btn
            color="secondary"
            prepend-icon="mdi-refresh"
            @click="refreshReadme()"
          >
            {{ t('core.common.readme.buttons.refresh') }}
          </v-btn>
        </div>
        
        <!-- 加载中 -->
        <div v-if="loading" class="d-flex flex-column align-center justify-center" style="height: 100%;">
          <v-progress-circular indeterminate color="primary" size="64" class="mb-4"></v-progress-circular>
          <p class="text-body-1 text-center">{{ t('core.common.readme.loading') }}</p>
        </div>
        
        <!-- 内容显示 -->
        <div v-else-if="content" class="markdown-body" v-html="renderMarkdown(content)"></div>
        
        <!-- 错误提示 -->
        <div v-else-if="error" class="d-flex flex-column align-center justify-center" style="height: 100%;">
          <v-icon size="64" color="error" class="mb-4">mdi-alert-circle-outline</v-icon>
          <p class="text-body-1 text-center mb-4">{{ error }}</p>
        </div>
        
        <!-- 无内容提示 -->
        <div v-else class="d-flex flex-column align-center justify-center" style="height: 100%;">
          <v-icon size="64" color="warning" class="mb-4">mdi-file-question-outline</v-icon>
          <p class="text-body-1 text-center mb-4">{{ t('core.common.readme.empty.title') }}<br>{{ t('core.common.readme.empty.subtitle') }}</p>
        </div>
      </v-card-text>
      <v-divider></v-divider>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="primary" variant="tonal" @click="$emit('update:show', false)">
          {{ t('core.common.close') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style>
.markdown-body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    line-height: 1.6;
    padding: 8px 0;
    color: var(--v-theme-secondaryText);
}

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

.markdown-body code {
    padding: 0.2em 0.4em;
    margin: 0;
    background-color: var(--v-theme-codeBg);
    border-radius: 3px;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 85%;
}

.markdown-body pre {
    padding: 16px;
    overflow: auto;
    font-size: 85%;
    line-height: 1.45;
    background-color: var(--v-theme-containerBg);
    border-radius: 3px;
    margin-bottom: 16px;
}

.markdown-body pre code {
    background-color: transparent;
    padding: 0;
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
    overflow: auto;
    margin-bottom: 16px;
}

.markdown-body table th,
.markdown-body table td {
    padding: 6px 13px;
    border: 1px solid var(--v-theme-background);
}

.markdown-body table tr {
    background-color: var(--v-theme-surface);
    border-top: 1px solid var(--v-theme-border);
}

.markdown-body table tr:nth-child(2n) {
    background-color: var(--v-theme-background);
}

.markdown-body hr {
    height: 0.25em;
    padding: 0;
    margin: 24px 0;
    background-color: var(--v-theme-containerBg);
    border: 0;
}
</style>

<script>
export default {
  name: 'ReadmeDialog',
  computed: {
    _show: {
      get() {
        return this.show;
      },
      set(value) {
        this.$emit('update:show', value);
      }
    }
  }
}
</script> 
