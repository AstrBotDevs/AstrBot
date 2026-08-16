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
        <p class="text-subtitle-1 text-medium-emphasis mt-2">
          {{ t('title') }}
        </p>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <v-progress-circular indeterminate color="primary" size="64" />
    </div>

    <div v-else-if="loadError" class="loading-container">
      <v-icon size="72" color="error">mdi-alert-circle-outline</v-icon>
      <p class="mt-4 text-medium-emphasis">{{ t('states.loadError') }}</p>
      <v-btn
        class="mt-4"
        prepend-icon="mdi-refresh"
        color="primary"
        variant="tonal"
        @click="loadDocument"
      >
        {{ t('states.retry') }}
      </v-btn>
    </div>

    <!-- 主内容 -->
    <div v-else class="document-content">
      <!-- 文档信息卡片 -->
      <v-card variant="outlined" class="mb-6">
        <v-card-title>{{ t('info.title') }}</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="3">
              <div class="info-item">
                <v-icon start>mdi-label</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t('info.name') }}
                  </div>
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
                  <div class="text-caption text-medium-emphasis">
                    {{ t('info.type') }}
                  </div>
                  <div class="text-body-1">{{ document.file_type || '-' }}</div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="2">
              <div class="info-item">
                <v-icon start>mdi-file-chart</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t('info.size') }}
                  </div>
                  <div class="text-body-1">
                    {{ formatFileSize(document.file_size) }}
                  </div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="2">
              <div class="info-item">
                <v-icon start>mdi-text-box</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t('info.chunkCount') }}
                  </div>
                  <div class="text-body-1">{{ document.chunk_count || 0 }}</div>
                </div>
              </div>
            </v-col>
            <v-col cols="12" md="3">
              <div class="info-item">
                <v-icon start>mdi-calendar</v-icon>
                <div>
                  <div class="text-caption text-medium-emphasis">
                    {{ t('info.createdAt') }}
                  </div>
                  <div class="text-body-1">
                    {{ formatDate(document.created_at) }}
                  </div>
                </div>
              </div>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 分块列表 -->
      <v-card variant="outlined">
        <v-card-title class="d-flex align-center pa-4">
          <span>{{ t('chunks.title') }}</span>
          <v-chip class="ml-2" size="small" variant="tonal">
            {{ totalChunks }} {{ t('chunks.title') }}
          </v-chip>
          <v-spacer />
        </v-card-title>

        <v-card-text class="pa-0">
          <v-alert
            v-if="chunksLoadError"
            type="error"
            variant="tonal"
            class="ma-4"
          >
            <div class="d-flex align-center justify-space-between ga-4">
              <span>{{ t('states.chunksLoadError') }}</span>
              <v-btn
                prepend-icon="mdi-refresh"
                variant="tonal"
                size="small"
                @click="loadChunks"
              >
                {{ t('states.retry') }}
              </v-btn>
            </div>
          </v-alert>
          <v-data-table
            v-else
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
              <!-- 删除 -->
              <v-btn
                icon="mdi-delete"
                variant="text"
                size="small"
                color="error"
                @click="deleteChunk(item)"
              />
            </template>

            <template #no-data>
              <div class="text-center py-8">
                <v-icon size="64" color="on-surface-variant"
                  >mdi-text-box-outline</v-icon
                >
                <p class="mt-4 text-medium-emphasis">{{ t('chunks.empty') }}</p>
              </div>
            </template>
          </v-data-table>

          <!-- 自定义分页器 -->
          <div
            v-if="!chunksLoadError && !searchQuery && totalChunks > 0"
            class="pa-4 d-flex align-center justify-space-between"
          >
            <div class="text-caption text-medium-emphasis">
              {{ t('chunks.showing') }} {{ (page - 1) * pageSize + 1 }} -
              {{ Math.min(page * pageSize, totalChunks) }} / {{ totalChunks }}
            </div>
            <div class="d-flex align-center gap-2">
              <v-select
                v-model="pageSize"
                :items="[10, 25, 50, 100]"
                density="compact"
                variant="outlined"
                hide-details
                class="chunk-page-size"
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
      <v-card class="app-dialog">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
          <span>{{ t('view.title') }}</span>
          <v-spacer />
          <v-btn
            icon="mdi-close"
            variant="text"
            @click="showViewDialog = false"
          />
        </v-card-title>
        <v-card-text class="pa-6">
          <v-list density="comfortable">
            <v-list-item>
              <template #prepend>
                <v-icon>mdi-pound</v-icon>
              </template>
              <v-list-item-title>{{ t('view.index') }}</v-list-item-title>
              <v-list-item-subtitle
                >#{{
                  (selectedChunk?.chunk_index || 0) + 1
                }}</v-list-item-subtitle
              >
            </v-list-item>

            <v-list-item>
              <template #prepend>
                <v-icon>mdi-text</v-icon>
              </template>
              <v-list-item-title>{{ t('view.charCount') }}</v-list-item-title>
              <v-list-item-subtitle
                >{{ selectedChunk?.char_count || 0 }} 字符</v-list-item-subtitle
              >
            </v-list-item>

            <v-list-item>
              <template #prepend>
                <v-icon>mdi-key</v-icon>
              </template>
              <v-list-item-title>{{ t('view.vecDocId') }}</v-list-item-title>
              <v-list-item-subtitle>{{
                selectedChunk?.chunk_id || '-'
              }}</v-list-item-subtitle>
            </v-list-item>
          </v-list>

          <div class="text-caption text-medium-emphasis mb-2">
            {{ t('view.content') }}
          </div>
          <div class="chunk-content-view">
            {{ selectedChunk?.content }}
          </div>
        </v-card-text>
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
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { knowledgeApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog';

interface KnowledgeDocument {
  doc_name?: string;
  file_type?: string;
  file_size?: number;
  chunk_count?: number;
  created_at?: string;
}

interface KnowledgeChunk {
  chunk_id: string;
  chunk_index: number;
  content: string;
  char_count: number;
}

const { tm: t } = useModuleI18n('features/knowledge-base/document');
const route = useRoute();

const confirmDialog = useConfirmDialog();

const kbId = ref(route.params.kbId as string);
const docId = ref(route.params.docId as string);

// 状态
const loading = ref(true);
const loadingChunks = ref(false);
const loadError = ref(false);
const chunksLoadError = ref(false);
const document = ref<KnowledgeDocument>({});
const chunks = ref<KnowledgeChunk[]>([]);
const searchQuery = ref('');
const showViewDialog = ref(false);
const selectedChunk = ref<KnowledgeChunk | null>(null);

// 分页状态
const page = ref(1);
const pageSize = ref(10);
const totalChunks = ref(0);

const snackbar = ref({
  show: false,
  text: '',
  color: 'success',
});

const showSnackbar = (text: string, color: string = 'success') => {
  snackbar.value.text = text;
  snackbar.value.color = color;
  snackbar.value.show = true;
};

// 表格列
const headers = [
  { title: t('chunks.index'), key: 'chunk_index', width: 100 },
  { title: t('chunks.content'), key: 'content', sortable: false },
  { title: t('chunks.charCount'), key: 'char_count', width: 150 },
  { title: t('chunks.actions'), key: 'actions', sortable: false, width: 150 },
];

// 过滤分块
const filteredChunks = computed(() => {
  if (!searchQuery.value) return chunks.value;
  const query = searchQuery.value.toLowerCase();
  return chunks.value.filter((chunk) =>
    chunk.content.toLowerCase().includes(query),
  );
});

// 加载文档详情
const loadDocument = async () => {
  loading.value = true;
  loadError.value = false;
  try {
    const response = await knowledgeApi.document(kbId.value, docId.value);
    if (response.data.status === 'ok') {
      document.value = response.data.data;
    } else {
      loadError.value = true;
      showSnackbar(response.data.message || t('states.loadError'), 'error');
    }
  } catch (error) {
    console.error('Failed to load document:', error);
    loadError.value = true;
    showSnackbar(t('states.loadError'), 'error');
  } finally {
    loading.value = false;
  }
};

// 加载分块列表
const loadChunks = async () => {
  loadingChunks.value = true;
  chunksLoadError.value = false;
  try {
    const response = await knowledgeApi.chunks(kbId.value, {
      document_id: docId.value,
      page: page.value,
      page_size: pageSize.value,
    });
    if (response.data.status === 'ok') {
      chunks.value = response.data.data.items || [];
      totalChunks.value = response.data.data.total || 0;
    } else {
      chunksLoadError.value = true;
      showSnackbar(
        response.data.message || t('states.chunksLoadError'),
        'error',
      );
    }
  } catch (error) {
    console.error('Failed to load chunks:', error);
    chunksLoadError.value = true;
    showSnackbar(t('states.chunksLoadError'), 'error');
  } finally {
    loadingChunks.value = false;
  }
};

// 处理分页变化
const handlePageChange = (newPage: number) => {
  page.value = newPage;
  void loadChunks();
};

const handlePageSizeChange = (newPageSize: number) => {
  pageSize.value = newPageSize;
  page.value = 1;
  void loadChunks();
};

// 查看分块
const viewChunk = (chunk: KnowledgeChunk) => {
  selectedChunk.value = chunk;
  showViewDialog.value = true;
};

// 删除分块
const deleteChunk = async (chunk: KnowledgeChunk) => {
  if (!(await askForConfirmation(t('chunks.deleteConfirm'), confirmDialog)))
    return;
  try {
    const response = await knowledgeApi.deleteChunk(
      kbId.value,
      chunk.chunk_id,
      docId.value,
    );
    if (response.data.status === 'ok') {
      showSnackbar(t('chunks.deleteSuccess'));
      void loadChunks();
    } else {
      showSnackbar(t('chunks.deleteFailed'), 'error');
    }
  } catch (error) {
    console.error('Failed to delete chunk:', error);
    showSnackbar(t('chunks.deleteFailed'), 'error');
  }
};

// 工具函数
const getFileIcon = (fileType?: string) => {
  const type = fileType?.toLowerCase() || '';
  if (type.includes('pdf')) return 'mdi-file-pdf-box';
  if (type.includes('epub')) return 'mdi-book-open-page-variant';
  if (type.includes('md')) return 'mdi-language-markdown';
  if (type.includes('txt')) return 'mdi-file-document-outline';
  return 'mdi-file';
};

const getFileColor = (fileType?: string) => {
  const type = fileType?.toLowerCase() || '';
  if (type.includes('pdf')) return 'error';
  if (type.includes('epub')) return 'warning';
  if (type.includes('md')) return 'info';
  if (type.includes('txt')) return 'success';
  return 'on-surface-variant';
};

const formatFileSize = (bytes?: number) => {
  if (!bytes) return '-';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(2)} ${units[unitIndex]}`;
};

const formatDate = (dateStr?: string) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

onMounted(() => {
  void loadDocument();
  void loadChunks();
});
</script>

<style scoped>
.document-detail-page {
  padding: 24px;
  max-width: 1040px;
  margin: 0 auto;
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
  font-size: 14px;
  line-height: 20px;
}

.chunk-page-size {
  width: 100px;
}

.chunk-content-view {
  padding: 16px;
  background: rgb(var(--v-theme-surface-variant));
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 20px;
  font-family: var(--astrbot-font-mono);
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
