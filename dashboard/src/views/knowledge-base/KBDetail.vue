<template>
  <div class="kb-detail-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <v-btn
        icon="mdi-arrow-left"
        variant="text"
        @click="$router.push({ name: 'NativeKBList' })"
      />
      <div class="header-content">
        <div class="kb-title">
          <span class="kb-emoji">{{ kb.emoji || '📚' }}</span>
          <h1 class="text-h4">{{ kb.kb_name }}</h1>
        </div>
        <p v-if="kb.description" class="text-subtitle-1 text-medium-emphasis mt-2">
          {{ kb.description }}
        </p>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <v-progress-circular indeterminate color="primary" size="64" />
    </div>

    <!-- 主内容 -->
    <div v-else class="kb-content">
      <!-- 标签页 -->
      <v-tabs v-model="activeTab" class="mb-6" color="primary">
        <v-tab value="overview">
          <v-icon start>mdi-information-outline</v-icon>
          {{ t('tabs.overview') }}
        </v-tab>
        <v-tab value="documents">
          <v-icon start>mdi-file-document-multiple</v-icon>
          {{ t('tabs.documents') }}
          <v-chip class="ml-2" size="small" variant="tonal">{{ kb.doc_count || 0 }}</v-chip>
        </v-tab>
        <v-tab value="sessions">
          <v-icon start>mdi-account-multiple</v-icon>
          {{ t('tabs.sessions') }}
        </v-tab>
        <v-tab value="settings">
          <v-icon start>mdi-cog</v-icon>
          {{ t('tabs.settings') }}
        </v-tab>
      </v-tabs>

      <!-- 标签页内容 -->
      <v-window v-model="activeTab">
        <!-- 概览 -->
        <v-window-item value="overview">
          <v-row>
            <v-col cols="12" md="6">
              <v-card elevation="2">
                <v-card-title>{{ t('overview.title') }}</v-card-title>
                <v-divider />
                <v-card-text>
                  <v-list density="comfortable">
                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-label</v-icon>
                      </template>
                      <v-list-item-title>{{ t('overview.name') }}</v-list-item-title>
                      <v-list-item-subtitle>{{ kb.kb_name }}</v-list-item-subtitle>
                    </v-list-item>

                    <v-list-item v-if="kb.description">
                      <template #prepend>
                        <v-icon>mdi-text</v-icon>
                      </template>
                      <v-list-item-title>{{ t('overview.description') }}</v-list-item-title>
                      <v-list-item-subtitle>{{ kb.description }}</v-list-item-subtitle>
                    </v-list-item>

                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-emoticon</v-icon>
                      </template>
                      <v-list-item-title>{{ t('overview.emoji') }}</v-list-item-title>
                      <v-list-item-subtitle>{{ kb.emoji || '📚' }}</v-list-item-subtitle>
                    </v-list-item>

                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-calendar-plus</v-icon>
                      </template>
                      <v-list-item-title>{{ t('overview.createdAt') }}</v-list-item-title>
                      <v-list-item-subtitle>{{ formatDate(kb.created_at) }}</v-list-item-subtitle>
                    </v-list-item>

                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-calendar-edit</v-icon>
                      </template>
                      <v-list-item-title>{{ t('overview.updatedAt') }}</v-list-item-title>
                      <v-list-item-subtitle>{{ formatDate(kb.updated_at) }}</v-list-item-subtitle>
                    </v-list-item>
                  </v-list>
                </v-card-text>
              </v-card>
            </v-col>

            <v-col cols="12" md="6">
              <v-card elevation="2" class="mb-4">
                <v-card-title>{{ t('overview.stats') }}</v-card-title>
                <v-divider />
                <v-card-text>
                  <v-row>
                    <v-col cols="6">
                      <div class="stat-box">
                        <v-icon size="48" color="primary">mdi-file-document</v-icon>
                        <div class="stat-value">{{ kb.doc_count || 0 }}</div>
                        <div class="stat-label">{{ t('overview.docCount') }}</div>
                      </div>
                    </v-col>
                    <v-col cols="6">
                      <div class="stat-box">
                        <v-icon size="48" color="secondary">mdi-text-box</v-icon>
                        <div class="stat-value">{{ kb.chunk_count || 0 }}</div>
                        <div class="stat-label">{{ t('overview.chunkCount') }}</div>
                      </div>
                    </v-col>
                  </v-row>
                </v-card-text>
              </v-card>

              <v-card elevation="2">
                <v-card-title>{{ t('overview.embeddingModel') }}</v-card-title>
                <v-divider />
                <v-card-text>
                  <v-list density="comfortable">
                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-vector-point</v-icon>
                      </template>
                      <v-list-item-title>{{ t('overview.embeddingModel') }}</v-list-item-title>
                      <v-list-item-subtitle>{{ kb.embedding_provider_id || t('overview.notSet') }}</v-list-item-subtitle>
                    </v-list-item>

                    <v-list-item>
                      <template #prepend>
                        <v-icon>mdi-sort-ascending</v-icon>
                      </template>
                      <v-list-item-title>{{ t('overview.rerankModel') }}</v-list-item-title>
                      <v-list-item-subtitle>{{ kb.rerank_provider_id || t('overview.notSet') }}</v-list-item-subtitle>
                    </v-list-item>
                  </v-list>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </v-window-item>

        <!-- 文档管理 -->
        <v-window-item value="documents">
          <DocumentsTab :kb-id="kbId" :kb="kb" @refresh="loadKB" />
        </v-window-item>

        <!-- 会话配置 -->
        <v-window-item value="sessions">
          <SessionsTab :kb-id="kbId" />
        </v-window-item>

        <!-- 设置 -->
        <v-window-item value="settings">
          <SettingsTab :kb="kb" @updated="loadKB" />
        </v-window-item>
      </v-window>
    </div>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'
import DocumentsTab from './components/DocumentsTab.vue'
import SessionsTab from './components/SessionsTab.vue'
import SettingsTab from './components/SettingsTab.vue'

const { tm: t } = useModuleI18n('features/knowledge-base/detail')
const route = useRoute()

const kbId = ref(route.params.kbId as string)
const loading = ref(true)
const activeTab = ref('overview')
const kb = ref<any>({})

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

// 加载知识库详情
const loadKB = async () => {
  loading.value = true
  try {
    const response = await axios.get('/api/kb/get', {
      params: { kb_id: kbId.value }
    })
    if (response.data.status === 'ok') {
      kb.value = response.data.data
    } else {
      showSnackbar(response.data.message || '加载失败', 'error')
    }
  } catch (error) {
    console.error('Failed to load knowledge base:', error)
    showSnackbar('加载知识库详情失败', 'error')
  } finally {
    loading.value = false
  }
}

// 格式化日期
const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  loadKB()
})
</script>

<style scoped>
.kb-detail-page {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.page-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 32px;
}

.header-content {
  flex: 1;
}

.kb-title {
  display: flex;
  align-items: center;
  gap: 16px;
}

.kb-emoji {
  font-size: 48px;
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.kb-content {
  animation: slideUp 0.4s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.stat-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px;
  text-align: center;
  border-radius: 12px;
  background: rgba(var(--v-theme-surface-variant), 0.3);
  transition: all 0.3s ease;
}

.stat-box:hover {
  transform: translateY(-4px);
  background: rgba(var(--v-theme-surface-variant), 0.5);
}

.stat-value {
  font-size: 2rem;
  font-weight: 600;
  margin-top: 8px;
  color: rgb(var(--v-theme-on-surface));
}

.stat-label {
  font-size: 0.875rem;
  color: rgb(var(--v-theme-on-surface-variant));
  margin-top: 4px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .kb-detail-page {
    padding: 16px;
  }

  .kb-title {
    flex-direction: column;
    align-items: flex-start;
  }

  .kb-emoji {
    font-size: 36px;
  }
}
</style>
