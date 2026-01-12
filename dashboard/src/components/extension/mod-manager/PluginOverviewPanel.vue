<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import { enableKatex, enableMermaid } from 'markstream-vue'
import 'markstream-vue/index.css'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github.css'
import { useI18n } from '@/i18n/composables'
import GitHubMarkdownViewer from '@/components/shared/GitHubMarkdownViewer.vue'
import { preprocessPluginMarkdown } from '@/utils/preprocessPluginMarkdown'

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
      content.value = preprocessPluginMarkdown(res.data.data?.content || '')
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

        <div v-else-if="content" class="readme-scroll__content">
          <div class="readme-scroll__container">
            <GitHubMarkdownViewer
              :content="content"
              header-icon="mdi-book-open-outline"
              header-label="README.md"
              :show-header="false"
            />
          </div>
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

.readme-scroll__container {
  max-width: 1012px;
  margin: 0 auto;
  padding: 32px;
}

.readme-scroll__content {
  min-height: 100%;
}


@media (max-width: 767px) {
  .readme-scroll__container {
    padding: 16px;
  }
  .github-style-content {
    padding: 24px;
  }
}
</style>
