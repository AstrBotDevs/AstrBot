<template>
  <div class="document-detail-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <v-btn
        icon="mdi-arrow-left"
        variant="text"
        @click="$router.push({ name: 'NativeKBDetail', params: { kbId } })"
      />
      <div class="header-content">
        <h1 class="text-h4">{{ document.doc_name }}</h1>
        <p class="text-subtitle-1 text-medium-emphasis mt-2">{{ t('title') }}</p>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <v-progress-circular indeterminate color="primary" size="64" />
    </div>

    <!-- 主内容 -->
    <div v-else class="document-content">
      <!-- 文档信息卡片 -->
      <v-card elevation="2" class="mb-6">
        <v-card-title>{{ t('info.title') }}</v-card-title>
        <v-divider />
        <v-card-text>
          <v-row>
            <v-col cols="12" md="3">
              <div class="info-item">
                <v-icon start>mdi-label</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">{{ t('info.name') }}</div>
                  <div class="text-body-1">{{ document.doc_name }}</div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="2">
              <div class="info-item">
                <v-icon start :color="getFileColor(document.file_type)">
                  {{ getFileIcon(document.file_type) }}
                </v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">{{ t('info.type') }}</div>
                  <div class="text-body-1">{{ document.file_type || '-' }}</div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="2">
              <div class="info-item">
                <v-icon start>mdi-file-chart</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">{{ t('info.size') }}</div>
                  <div class="text-body-1">{{ formatFileSize(document.file_size) }}</div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="2">
              <div class="info-item">
                <v-icon start>mdi-text-box</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">{{ t('info.chunkCount') }}</div>
                  <div class="text-body-1">{{ document.chunk_count || 0 }}</div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="3">
              <div class="info-item">
                <v-icon start>mdi-calendar</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">{{ t('info.createdAt') }}</div>
                  <div class="text-body-1">{{ formatDate(document.created_at) }}</div>
                </div>
              </div>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 分块列表 -->
      <v-card elevation="2">
        <v-card-title class="d-flex align-center pa-4">
          <span>{{ t('chunks.title') }}</span>
          <v-chip class="ml-2" size="small" variant="tonal">
            {{ totalChunks }} {{ t('chunks.title') }}
          </v-chip>
          <v-spacer />
          <v-text-field
            v-model="searchQuery"
            prepend-inner-icon="mdi-magnify"
            :placeholder="t('chunks.searchPlaceholder')"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            style="max-width: 300px"
          />
        </v-card-title>

        <v-divider />

        <v-card-text class="pa-0">
          <v-data-table
            :headers="headers"
            :items="filteredChunks"
            :loading="loadingChunks"
            :items-per-page="pageSize"
            hide-default-footer
          >
            <template #item.chunk_index="{ item }">
              <v-chip size="small" variant="tonal" color="primary">
                #{{ item.chunk_index + 1 }}
              </v-chip>
            </template>

            <template #item.content="{ item }">
              <div class="chunk-content-preview">
                {{ item.content }}
              </div>
            </template>

            <template #item.char_count="{ item }">
              <v-chip size="small" variant="outlined">
                {{ item.char_count }} 字符
              </v-chip>
            </template>

            <template #item.actions="{ item }">
              <v-btn
                icon="mdi-eye"
                variant="text"
                size="small"
                color="info"
                @click="viewChunk(item)"
              />
            </template>

            <template #no-data>
              <div class="text-center py-8">
                <v-icon size="64" color="grey-lighten-2">mdi-text-box-outline</v-icon>
                <p class="mt-4 text-medium-emphasis">{{ t('chunks.empty') }}</p>
              </div>
            </template>
          </v-data-table>
          

          <!-- 自定义分页器 -->
          <div v-if="!searchQuery && totalChunks > 0" class="pa-4 d-flex align-center justify-space-between">
            <div class="text-caption text-medium-emphasis">
              {{ t('chunks.showing') }} {{ (page - 1) * pageSize + 1 }} - {{ Math.min(page * pageSize, totalChunks) }} / {{ totalChunks }}
            </div>
            <div class="d-flex align-center gap-2">
              <v-select
                v-model="pageSize"
                :items="[10, 25, 50, 100]"
                density="compact"
                variant="outlined"
                hide-details
                style="width: 100px"
                @update:model-value="handlePageSizeChange"
              />
              <v-pagination
                v-model="page"
                :length="Math.ceil(totalChunks / pageSize)"
                :total-visible="5"
                @update:model-value="handlePageChange"
              />
            </div>
          </div>
        </v-card-text>
      </v-card>
    </div>

    <!-- 查看分块对话框 -->
    <v-dialog v-model="showViewDialog" max-width="800px" scrollable>
      <v-card>
        <v-card-title class="pa-4">
          <span>{{ t('view.title') }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="showViewDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pa-6">
          <v-list density="comfortable">
            <v-list-item>
              <template #prepend>
                <v-icon>mdi-pound</v-icon>
              </template>
              <v-list-item-title>{{ t('view.index') }}</v-list-item-title>
              <v-list-item-subtitle>#{{ (selectedChunk?.chunk_index || 0) + 1 }}</v-list-item-subtitle>
            </v-list-item>

            <v-list-item>
              <template #prepend>
                <v-icon>mdi-text</v-icon>
              </template>
              <v-list-item-title>{{ t('view.charCount') }}</v-list-item-title>
              <v-list-item-subtitle>{{ selectedChunk?.char_count || 0 }} 字符</v-list-item-subtitle>
            </v-list-item>

            <v-list-item>
              <template #prepend>
                <v-icon>mdi-key</v-icon>
              </template>
              <v-list-item-title>{{ t('view.vecDocId') }}</v-list-item-title>
              <v-list-item-subtitle>{{ selectedChunk?.chunk_id || '-' }}</v-list-item-subtitle>
            </v-list-item>
          </v-list>

          <v-divider class="my-4" />

          <div class="text-caption text-medium-emphasis mb-2">{{ t('view.content') }}</div>
          <div class="chunk-content-view">
            {{ selectedChunk?.content }}
          </div>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="showViewDialog = false">
            {{ t('view.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

const { tm: t } = useModuleI18n('features/knowledge-base/document')
const route = useRoute()

const kbId = ref(route.params.kbId as string)
const docId = ref(route.params.docId as string)

// 状态
const loading = ref(true)
const loadingChunks = ref(false)
const document = ref<any>({})
const chunks = ref<any[]>([])
const searchQuery = ref('')
const showViewDialog = ref(false)
const selectedChunk = ref<any>(null)

// 分页状态
const page = ref(1)
const pageSize = ref(10)
const totalChunks = ref(0)

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

// 表格列
const headers = [
  { title: t('chunks.index'), key: 'chunk_index', width: 100 },
  { title: t('chunks.content'), key: 'content', sortable: false },
  { title: t('chunks.charCount'), key: 'char_count', width: 150 },
  { title: t('chunks.actions'), key: 'actions', sortable: false, width: 150 }
]

// 过滤分块
const filteredChunks = computed(() => {
  if (!searchQuery.value) return chunks.value
  const query = searchQuery.value.toLowerCase()
  return chunks.value.filter(chunk =>
    chunk.content.toLowerCase().includes(query)
  )
})

// 加载文档详情
const loadDocument = async () => {
  loading.value = true
  try {
    const response = await axios.get('/api/kb/document/get', {
      params: { doc_id: docId.value, kb_id: kbId.value }
    })
    if (response.data.status === 'ok') {
      document.value = response.data.data
    }
  } catch (error) {
    console.error('Failed to load document:', error)
    showSnackbar('加载文档详情失败', 'error')
  } finally {
    loading.value = false
  }
}

// 加载分块列表
const loadChunks = async () => {
  loadingChunks.value = true
  try {
    const response = await axios.get('/api/kb/chunk/list', {
      params: { 
        doc_id: docId.value, 
        kb_id: kbId.value,
        page: page.value,
        page_size: pageSize.value
      }
    })
    if (response.data.status === 'ok') {
      chunks.value = response.data.data.items || []
      totalChunks.value = response.data.data.items.length
    }
  } catch (error) {
    console.error('Failed to load chunks:', error)
    showSnackbar('加载分块列表失败', 'error')
  } finally {
    loadingChunks.value = false
  }
}

// 处理分页变化
const handlePageChange = (newPage: number) => {
  page.value = newPage
  loadChunks()
}

const handlePageSizeChange = (newPageSize: number) => {
  pageSize.value = newPageSize
  page.value = 1
  loadChunks()
}

// 查看分块
const viewChunk = (chunk: any) => {
  selectedChunk.value = chunk
  showViewDialog.value = true
}

// 工具函数
const getFileIcon = (fileType: string) => {
  const type = fileType?.toLowerCase() || ''
  if (type.includes('pdf')) return 'mdi-file-pdf-box'
  if (type.includes('md')) return 'mdi-language-markdown'
  if (type.includes('txt')) return 'mdi-file-document-outline'
  return 'mdi-file'
}

const getFileColor = (fileType: string) => {
  const type = fileType?.toLowerCase() || ''
  if (type.includes('pdf')) return 'error'
  if (type.includes('md')) return 'info'
  if (type.includes('txt')) return 'success'
  return 'grey'
}

const formatFileSize = (bytes: number) => {
  if (!bytes) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex++
  }
  return `${size.toFixed(2)} ${units[unitIndex]}`
}

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  loadDocument()
  loadChunks()
})
</script>

<style scoped>
.document-detail-page {
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

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.document-content {
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

.info-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.chunk-content-preview {
  max-width: 400px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.875rem;
  line-height: 1.5;
}

.chunk-content-view {
  padding: 16px;
  background: rgba(var(--v-theme-surface-variant), 0.3);
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  font-family: 'Consolas', 'Monaco', monospace;
}

.gap-2 {
  gap: 8px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .document-detail-page {
    padding: 16px;
  }
}
</style>
