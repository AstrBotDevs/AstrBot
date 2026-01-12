<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import GitHubMarkdownViewer from '@/components/shared/GitHubMarkdownViewer.vue'
import { preprocessPluginMarkdown } from '@/utils/preprocessPluginMarkdown'
import { enableKatex, enableMermaid } from 'markstream-vue'
import 'markstream-vue/index.css'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github.css'

enableKatex()
enableMermaid()

const UPSTREAM_REPO_URL = 'https://github.com/AstrBotDevs/AstrBot'
const UPSTREAM_README_API_URL = 'https://api.github.com/repos/AstrBotDevs/AstrBot/readme'
const UPSTREAM_RAW_BASE_URL = 'https://raw.githubusercontent.com/AstrBotDevs/AstrBot/master/'

const { tm } = useModuleI18n('features/extension')

const loading = ref(false)
const error = ref<string | null>(null)
const content = ref('')

const docsLink = computed(() => ({
  key: 'docs',
  label: String(tm('modManager.welcome.links.docs')),
  icon: 'mdi-book-open-page-variant',
  url: 'https://astrbot.app/'
}))

function openInNewTab(url: string) {
  if (!url) return
  window.open(url, '_blank')
}

function openUpstreamRepo() {
  openInNewTab(UPSTREAM_REPO_URL)
}

async function fetchUpstreamReadme() {
  loading.value = true
  error.value = null
  content.value = ''

  try {
    const res = await fetch(UPSTREAM_README_API_URL, {
      method: 'GET',
      headers: {
        Accept: 'application/vnd.github.raw+json'
      }
    })

    if (!res.ok) {
      if (res.status === 403) {
        error.value = String(tm('modManager.welcome.readme.errors.rateLimited'))
      } else {
        error.value = String(tm('modManager.welcome.readme.errors.fetchFailed'))
      }
      return
    }

    const rawText = await res.text()
    content.value = preprocessPluginMarkdown(rawText || '', { baseUrl: UPSTREAM_RAW_BASE_URL })
  } catch {
    error.value = String(tm('modManager.welcome.readme.errors.fetchFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchUpstreamReadme()
})
</script>

<template>
  <div class="h-100 d-flex flex-column">
    <div class="d-flex align-center ga-3 pa-6">
      <v-icon size="40" color="info">mdi-puzzle-outline</v-icon>
      <div style="min-width: 0">
        <div class="text-h6">{{ tm('modManager.welcome.title') }}</div>
        <div class="text-body-2 text-medium-emphasis">{{ tm('modManager.welcome.subtitle') }}</div>
      </div>

      <v-spacer />

      <v-btn
        color="primary"
        variant="tonal"
        prepend-icon="mdi-github"
        class="ml-2"
        @click="openUpstreamRepo"
      >
        {{ tm('modManager.welcome.actions.viewOnGithub') }}
      </v-btn>

      <v-btn
        variant="tonal"
        color="secondary"
        :prepend-icon="docsLink.icon"
        class="ml-2"
        @click="openInNewTab(docsLink.url)"
      >
        {{ docsLink.label }}
      </v-btn>
    </div>

    <v-divider />

    <div class="pa-0 flex-grow-1 welcome-scroll">
      <div v-if="loading" class="d-flex flex-column align-center justify-center pa-6 welcome-state">
        <v-progress-circular indeterminate color="primary" size="56" class="mb-3" />
        <div class="text-body-2 text-medium-emphasis">{{ tm('modManager.welcome.readme.loading') }}</div>
      </div>

      <div v-else-if="error" class="d-flex flex-column align-center justify-center pa-6 welcome-state">
        <v-icon size="64" color="error" class="mb-4">mdi-alert-circle-outline</v-icon>
        <div class="text-body-1 text-center mb-4">{{ error }}</div>
        <v-btn color="primary" variant="tonal" @click="fetchUpstreamReadme">
          {{ tm('modManager.welcome.actions.retry') }}
        </v-btn>
      </div>

      <div v-else-if="content" class="welcome-readme">
        <div class="welcome-readme__container">
          <GitHubMarkdownViewer :content="content" header-icon="mdi-book-open-outline" header-label="README.md" :show-header="false" />

          <v-alert type="info" variant="tonal" density="comfortable" class="mt-8">
            <div class="text-body-2">
              {{ tm('modManager.welcome.tip.market') }}
            </div>
          </v-alert>
        </div>
      </div>

      <div v-else class="d-flex flex-column align-center justify-center pa-6 welcome-state">
        <v-icon size="64" color="warning" class="mb-4">mdi-file-question-outline</v-icon>
        <p class="text-body-1 text-center mb-0">
          {{ tm('modManager.welcome.readme.empty.title') }}<br />
          {{ tm('modManager.welcome.readme.empty.subtitle') }}
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.welcome-scroll {
  min-height: 0;
  overflow-y: auto;
}

.welcome-state {
  height: 100%;
}

.welcome-readme__container {
  max-width: 1012px;
  margin: 0 auto;
  padding: 32px;
}


@media (max-width: 767px) {
  .welcome-readme__container {
    padding: 16px;
  }
  .github-style-content {
    padding: 16px;
  }
}
</style>