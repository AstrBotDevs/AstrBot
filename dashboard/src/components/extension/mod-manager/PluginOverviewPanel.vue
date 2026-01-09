<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import { MarkdownRender, enableKatex, enableMermaid } from 'markstream-vue'
import 'markstream-vue/index.css'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github.css'
import { useI18n } from '@/i18n/composables'

enableKatex()
enableMermaid()

const props = defineProps<{
  pluginName: string
  repoUrl?: string | null
  active?: boolean
}>()

const { t } = useI18n()

const loading = ref(false)
const error = ref<string | null>(null)
const content = ref('')

const canFetch = computed(() => Boolean(props.active) && Boolean(props.pluginName))
const hasRepo = computed(() => Boolean(props.repoUrl))

async function fetchReadme() {
  if (!props.pluginName) return

  loading.value = true
  content.value = ''
  error.value = null

  try {
    const res = await axios.get(`/api/plugin/readme?name=${props.pluginName}`)
    if (res.data?.status === 'ok') {
      content.value = res.data.data?.content || ''
    } else {
      error.value = res.data?.message || t('core.common.readme.errors.fetchFailed')
    }
  } catch (err: any) {
    error.value = err?.message || t('core.common.readme.errors.fetchError')
  } finally {
    loading.value = false
  }
}

function openRepoInNewTab() {
  if (props.repoUrl) {
    window.open(props.repoUrl, '_blank')
  }
}

function refreshReadme() {
  fetchReadme()
}

watch(
  () => props.active,
  (isActive) => {
    if (isActive && props.pluginName) {
      fetchReadme()
    }
  },
  { immediate: true }
)

watch(
  () => props.pluginName,
  (name) => {
    if (props.active && name) {
      fetchReadme()
    } else {
      loading.value = false
      error.value = null
      content.value = ''
    }
  }
)
</script>

<template>
  <v-card class="h-100 d-flex flex-column" rounded="lg" variant="flat">
    <v-card-title class="d-flex align-center ga-2">
      <div class="text-subtitle-1 font-weight-medium">文档</div>
      <v-spacer />

      <v-btn
        v-if="hasRepo"
        color="primary"
        prepend-icon="mdi-github"
        variant="tonal"
        @click="openRepoInNewTab"
      >
        {{ t('core.common.readme.buttons.viewOnGithub') }}
      </v-btn>

      <v-btn
        color="secondary"
        prepend-icon="mdi-refresh"
        variant="tonal"
        :disabled="!pluginName"
        @click="refreshReadme"
      >
        {{ t('core.common.readme.buttons.refresh') }}
      </v-btn>
    </v-card-title>

    <v-divider />

    <v-card-text class="pa-0 flex-grow-1">
      <div class="readme-scroll">
        <div v-if="loading" class="d-flex flex-column align-center justify-center" style="height: 100%">
          <v-progress-circular indeterminate color="primary" size="56" class="mb-3" />
          <div class="text-body-2 text-medium-emphasis">{{ t('core.common.readme.loading') }}</div>
        </div>

        <div v-else-if="error" class="d-flex flex-column align-center justify-center pa-6" style="height: 100%">
          <v-icon size="64" color="error" class="mb-4">mdi-alert-circle-outline</v-icon>
          <div class="text-body-1 text-center mb-4">{{ error }}</div>
          <v-btn color="primary" variant="tonal" @click="fetchReadme">重试</v-btn>
        </div>

        <div v-else-if="content" class="markdown-body pa-4">
          <MarkdownRender :content="content" :typewriter="false" class="markdown-content" />
        </div>

        <div v-else class="d-flex flex-column align-center justify-center pa-6" style="height: 100%">
          <v-icon size="64" color="warning" class="mb-4">mdi-file-question-outline</v-icon>
          <p class="text-body-1 text-center mb-0">
            {{ t('core.common.readme.empty.title') }}<br />
            {{ t('core.common.readme.empty.subtitle') }}
          </p>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<style scoped>
.readme-scroll {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
}
</style>

<style>
/* 更贴近 GitHub 的 markdown 展示样式（不引入新依赖，仅调整样式） */
.markdown-body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  word-wrap: break-word;
  padding: 8px 0;
  color: rgba(var(--v-theme-on-surface), 0.87);
}

.markdown-body > :first-child {
  margin-top: 0;
}

.markdown-body > :last-child {
  margin-bottom: 0;
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
  padding-bottom: 0.3em;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.35);
}

.markdown-body h2 {
  font-size: 1.5em;
  padding-bottom: 0.3em;
  border-bottom: 1px solid rgba(var(--v-border-color), 0.35);
}

.markdown-body h3 {
  font-size: 1.25em;
}

.markdown-body p {
  margin-top: 0;
  margin-bottom: 16px;
}

.markdown-body hr {
  height: 0.25em;
  padding: 0;
  margin: 24px 0;
  background-color: rgba(var(--v-theme-on-surface), 0.08);
  border: 0;
}

.markdown-body a {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}

.markdown-body a:hover {
  text-decoration: underline;
}

/* Lists */
.markdown-body ul,
.markdown-body ol {
  padding-left: 2em;
  margin-top: 0;
  margin-bottom: 16px;
}

.markdown-body li + li {
  margin-top: 0.25em;
}

.markdown-body li > p {
  margin-top: 0;
}

/* Task list */
.markdown-body .task-list-item {
  list-style-type: none;
}

.markdown-body .task-list-item input[type='checkbox'] {
  margin: 0 0.35em 0 0;
  vertical-align: middle;
}

/* Code */
.markdown-body code {
  padding: 0.2em 0.4em;
  margin: 0;
  background-color: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 85%;
}

.markdown-body pre {
  padding: 16px;
  overflow: auto;
  font-size: 85%;
  line-height: 1.45;
  background-color: rgba(var(--v-theme-on-surface), 0.04);
  border: 1px solid rgba(var(--v-border-color), 0.35);
  border-radius: 6px;
  margin: 0 0 16px;
}

.markdown-body pre code {
  background-color: transparent;
  padding: 0;
}

/* Blockquote */
.markdown-body blockquote {
  padding: 0 1em;
  color: rgba(var(--v-theme-on-surface), 0.72);
  border-left: 0.25em solid rgba(var(--v-border-color), 0.45);
  margin: 0 0 16px;
}

/* Images */
.markdown-body img {
  max-width: 100%;
  height: auto;
  margin: 0.5em 0;
  box-sizing: border-box;
  border-radius: 6px;
}


/* Tables (GitHub-like) */
.markdown-body table {
  border-spacing: 0;
  border-collapse: collapse;
  width: max-content;
  min-width: 100%;
  display: block;
  overflow: auto;
  margin: 0 0 16px;
}

.markdown-body table th,
.markdown-body table td {
  padding: 6px 13px;
  border: 1px solid rgba(var(--v-border-color), 0.35);
}

.markdown-body table th {
  font-weight: 600;
}

.markdown-body table tr {
  background-color: transparent;
}

.markdown-body table tr:nth-child(2n) {
  background-color: rgba(var(--v-theme-on-surface), 0.02);
}
</style>