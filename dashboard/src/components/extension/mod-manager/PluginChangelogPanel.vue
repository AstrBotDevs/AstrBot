<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import { enableKatex, enableMermaid } from 'markstream-vue'
import 'markstream-vue/index.css'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/github.css'
import { useModuleI18n } from '@/i18n/composables'
import GitHubMarkdownViewer from '@/components/shared/GitHubMarkdownViewer.vue'
import { preprocessPluginMarkdown } from '@/utils/preprocessPluginMarkdown'

enableKatex()
enableMermaid()

const props = defineProps<{
  pluginName: string
  active?: boolean
}>()

const { tm } = useModuleI18n('features/extension')

const loading = ref(false)
const error = ref<string | null>(null)
const content = ref('')

const canFetch = computed(() => Boolean(props.active) && Boolean(props.pluginName))

function resetState() {
  loading.value = false
  error.value = null
  content.value = ''
}

async function fetchChangelog() {
  if (!props.pluginName) return

  loading.value = true
  error.value = null
  content.value = ''

  try {
    const res = await axios.get(`/api/plugin/changelog?name=${encodeURIComponent(props.pluginName)}`)
    if (res.data?.status === 'ok') {
      content.value = preprocessPluginMarkdown(res.data.data?.content || '')
    } else {
      error.value = res.data?.message || tm('modManager.changelogPanel.errors.fetchFailed')
    }
  } catch (err: any) {
    error.value = err?.message || tm('modManager.changelogPanel.errors.fetchError')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.active,
  (isActive) => {
    if (isActive && props.pluginName) {
      fetchChangelog()
    }
  },
  { immediate: true }
)

watch(
  () => props.pluginName,
  (name) => {
    if (props.active && name) {
      fetchChangelog()
    } else {
      resetState()
    }
  }
)
</script>

<template>
  <v-card class="h-100 d-flex flex-column" rounded="lg" variant="flat">
    <v-card-title class="d-flex align-center ga-2">
      <div class="text-subtitle-1 font-weight-medium">{{ tm('modManager.panelTabs.changelog') }}</div>
    </v-card-title>

    <v-divider />

    <v-card-text class="pa-0 flex-grow-1">
      <div class="changelog-scroll">
        <div v-if="loading" class="d-flex flex-column align-center justify-center" style="height: 100%">
          <v-progress-circular indeterminate color="primary" size="56" class="mb-3" />
          <div class="text-body-2 text-medium-emphasis">{{ tm('modManager.changelogPanel.loading') }}</div>
        </div>

        <div v-else-if="error" class="d-flex flex-column align-center justify-center pa-6" style="height: 100%">
          <v-icon size="64" color="error" class="mb-4">mdi-alert-circle-outline</v-icon>
          <div class="text-body-1 text-center mb-4">{{ error }}</div>
          <v-btn color="primary" variant="tonal" @click="fetchChangelog">
            {{ tm('modManager.changelogPanel.actions.retry') }}
          </v-btn>
        </div>

        <div v-else-if="content" class="changelog-scroll__content">
          <div class="changelog-scroll__container">
            <GitHubMarkdownViewer :content="content" header-icon="mdi-history" header-label="CHANGELOG.md" />
          </div>
        </div>

        <div v-else class="d-flex flex-column align-center justify-center pa-6" style="height: 100%">
          <v-icon size="64" color="warning" class="mb-4">mdi-file-question-outline</v-icon>
          <p class="text-body-1 text-center mb-0">
            {{ tm('modManager.changelogPanel.empty.title') }}<br />
            {{ tm('modManager.changelogPanel.empty.subtitle') }}
          </p>
        </div>

        <div v-if="!canFetch" class="d-none" />
      </div>
    </v-card-text>
  </v-card>
</template>

<style scoped>
.changelog-scroll {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
}

.changelog-scroll__container {
  max-width: 1012px;
  margin: 0 auto;
  padding: 32px;
}

.changelog-scroll__content {
  min-height: 100%;
}


@media (max-width: 767px) {
  .changelog-scroll__container {
    padding: 16px;
  }
  .github-style-content {
    padding: 24px;
  }
}
</style>