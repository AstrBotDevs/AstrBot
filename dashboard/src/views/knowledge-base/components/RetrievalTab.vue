<template>
  <div class="retrieval-tab">
    <v-card elevation="2">
      <v-card-title class="pa-4 pb-0">{{ t('retrieval.title') }}</v-card-title>
      <v-card-subtitle class="pb-4 pt-2">
        {{ t('retrieval.subtitle') }}
      </v-card-subtitle>

      <v-divider />
      <v-progress-linear v-if="loading" indeterminate color="primary" height="2" />

      <v-card-text class="pa-6">
        <!-- 查询输入区域 -->
        <v-row class="mb-4">
          <v-col cols="12" md="8">
            <v-textarea v-model="query" :label="t('retrieval.query')" :placeholder="t('retrieval.queryPlaceholder')"
              variant="outlined" rows="3" auto-grow clearable />

            <!-- debug -->
            <div v-if="debugVisualize" class="mt-2">
              <v-card variant="outlined">
                <v-img :src="`data:image/png;base64,${debugVisualize}`" :alt="t('retrieval.tsneVisualization')" cover>
                  <template v-slot:placeholder>
                    <div class="d-flex align-center justify-center fill-height">
                      <v-progress-circular indeterminate color="primary" />
                    </div>
                  </template>
                </v-img>
              </v-card>
            </div>
          </v-col>
          <v-col cols="12" md="4">
            <v-card variant="outlined" class="pa-4">
              <h4 class="text-subtitle-2 mb-3">{{ t('retrieval.settings') }}</h4>

              <v-text-field v-model.number="topK" :label="t('retrieval.topK')" :hint="t('retrieval.topKHint')"
                type="number" variant="outlined" density="compact" persistent-hint class="mb-3" />

              <v-switch v-model="debugMode" :label="t('retrieval.debugMode')" color="primary" density="compact"
                hide-details>
                <template v-slot:label>
                  <span class="text-caption">
                    <v-icon size="small" class="mr-1">mdi-bug</v-icon>
                    Debug (t-SNE)
                  </span>
                </template>
              </v-switch>
            </v-card>
          </v-col>
        </v-row>

        <div class="d-flex justify-end mb-4">
          <v-btn prepend-icon="mdi-magnify" color="primary" variant="elevated" @click="performRetrieval"
            :loading="loading" :disabled="!query || query.trim() === ''">
            {{ loading ? t('retrieval.searching') : t('retrieval.search') }}
          </v-btn>
        </div>

        <!-- 检索结果 -->
        <div v-if="hasSearched" class="results-section">
          <v-divider class="mb-4" />

          <div class="d-flex align-center mb-4">
            <h3 class="text-h6">{{ t('retrieval.results') }}</h3>
            <v-chip class="ml-3" color="primary" variant="tonal" size="small">
              {{ results.length }} {{ t('retrieval.results') }}
            </v-chip>
          </div>

          <!-- 结果列表 -->
          <div v-if="results.length > 0" class="results-list">
            <v-card v-for="(result, index) in results" :key="result.chunk_id" variant="outlined" class="mb-4">
              <v-card-title class="d-flex align-center pa-2">
                <v-chip size="x-small" color="primary" class="mr-2">
                  #{{ index + 1 }}
                </v-chip>
                <span class="text-subtitle-1">
                  {{ t('retrieval.chunk', { index: result.chunk_index }) }}
                </span>
                <div class="ml-4">
                  <v-chip size="x-small" variant="tonal" class="mr-2">
                    <v-icon start size="small">mdi-file-document</v-icon>
                    {{ result.doc_name }}
                  </v-chip>
                  <v-chip size="x-small" variant="tonal">
                    <v-icon start size="small">mdi-text</v-icon>
                    {{ t('retrieval.charCount', { count: result.char_count }) }}
                  </v-chip>
                </div>
                <v-spacer />
                <v-chip size="x-small" :color="getScoreColor(result.score)">
                  {{ t('retrieval.score') }}: {{ result.score.toFixed(4) }}
                </v-chip>
              </v-card-title>

              <v-divider />

              <v-card-text class="pa-4">
                <div class="content-box">
                  {{ result.content }}
                </div>
              </v-card-text>
            </v-card>
          </div>

          <!-- 空结果 -->
          <div v-else class="text-center py-12">
            <v-icon size="80" color="grey-lighten-2">mdi-text-box-search-outline</v-icon>
            <p class="text-h6 mt-4 text-medium-emphasis">{{ t('retrieval.noResults') }}</p>
            <p class="text-body-2 text-medium-emphasis">{{ t('retrieval.tryDifferentQuery') }}</p>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

const { tm: t } = useModuleI18n('features/knowledge-base/detail')

const props = defineProps<{
  kbId: string,
  kbName: string,
}>()

// 状态
const loading = ref(false)
const query = ref('')
const topK = ref(5)
const debugMode = ref(false)
const results = ref<any[]>([])
const hasSearched = ref(false)
const debugVisualize = ref<string | null>(null)

const snackbar = ref({
  show: false,
  text: '',
  color: 'success'
})

const showSnackbar = (text: string, color: string = 'success') => {
  snackbar.value.text = text
  snackbar.value.color = color
  snackbar.value.show = true
}

// 执行检索
const performRetrieval = async () => {
  if (!query.value || query.value.trim() === '') {
    showSnackbar(t('retrieval.queryRequired'), 'warning')
    return
  }

  loading.value = true
  hasSearched.value = false
  debugVisualize.value = null

  try {
    const response = await axios.post('/api/kb/retrieve', {
      query: query.value,
      kb_names: [props.kbName],
      top_k: topK.value,
      debug: debugMode.value
    })

    if (response.data.status === 'ok') {
      results.value = response.data.data.results || []
      hasSearched.value = true

      if (debugMode.value && response.data.data.visualization) {
        debugVisualize.value = response.data.data.visualization
      }

      showSnackbar(t('retrieval.searchSuccess', { count: results.value.length }))
    } else {
      showSnackbar(response.data.message || t('retrieval.searchFailed'), 'error')
    }
  } catch (error) {
    console.error('Retrieval failed:', error)
    showSnackbar(t('retrieval.searchFailed'), 'error')
  } finally {
    loading.value = false
  }
}

// 根据分数获取颜色
const getScoreColor = (score: number) => {
  if (score >= 0.8) return 'success'
  if (score >= 0.6) return 'info'
  if (score >= 0.4) return 'warning'
  return 'error'
}
</script>

<style scoped>
.retrieval-tab {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

.results-section {
  animation: slideUp 0.4s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.content-box {
  background: rgba(var(--v-theme-surface-variant), 0.1);
  border-radius: 8px;
  padding: 16px;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 0.9rem;
  line-height: 1.6;
  height: 120px;
  overflow-y: auto;
  font-size: 13px;
}
</style>
