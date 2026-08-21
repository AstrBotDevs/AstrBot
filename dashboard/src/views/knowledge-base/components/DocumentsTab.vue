<template>
  <div class="documents-tab">
    <!-- 操作栏 -->
    <div class="action-bar mb-4">
      <v-btn
        prepend-icon="mdi-upload"
        color="primary"
        variant="outlined"
        @click="showUploadDialog = true"
      >
        {{ t('documents.upload') }}
      </v-btn>
      <v-text-field
        v-model="searchQuery"
        prepend-inner-icon="mdi-magnify"
        :placeholder="'搜索文档...'"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        class="documents-search"
      />
    </div>

    <!-- 文档列表 -->
    <v-card variant="outlined">
      <v-data-table-server
        :headers="headers"
        :items="documents"
        :loading="loading"
        :items-per-page="pageSize"
        :page="page"
        :items-length="total"
        @update:page="handlePageChange"
        @update:items-per-page="handlePageSizeChange"
      >
        <template #item.doc_name="{ item }">
          <div class="d-flex align-center gap-2">
            <v-icon :color="getFileColor(item.file_type)" class="mr-2">
              {{ getFileIcon(item.file_type) }}
            </v-icon>
            <div class="documents-tab__name flex-grow-1">
              <span class="font-weight-medium">{{ item.doc_name }}</span>
              <!-- 上传进度 -->
              <div v-if="item.uploading" class="mt-1">
                <div class="text-caption text-medium-emphasis mb-1">
                  {{ getStageText(item.uploadProgress?.stage || 'waiting') }}
                  <span v-if="item.uploadProgress?.current">
                    ({{ item.uploadProgress.current }} /
                    {{ item.uploadProgress.total }})
                  </span>
                </div>
                <v-progress-linear
                  :model-value="getUploadPercentage(item)"
                  color="primary"
                  height="4"
                  rounded
                  striped
                />
              </div>
            </div>
          </div>
        </template>

        <template #item.file_size="{ item }">
          {{ formatFileSize(item.file_size) }}
        </template>

        <template #item.created_at="{ item }">
          {{ formatDate(item.created_at) }}
        </template>

        <template #item.actions="{ item }">
          <v-btn
            icon="mdi-eye"
            variant="text"
            size="small"
            color="info"
            :aria-label="t('documents.view')"
            @click="viewDocument(item)"
          />
          <v-btn
            icon="mdi-delete"
            variant="text"
            size="small"
            color="error"
            :aria-label="t('documents.delete')"
            @click="confirmDelete(item)"
          />
        </template>

        <template #no-data>
          <div class="text-center py-8">
            <v-icon size="64" color="on-surface-variant"
              >mdi-file-document-outline</v-icon
            >
            <p class="mt-4 text-medium-emphasis">{{ t('documents.empty') }}</p>
          </div>
        </template>
      </v-data-table-server>
    </v-card>

    <!-- 上传对话框 -->
    <v-dialog
      v-model="showUploadDialog"
      max-width="650px"
      persistent
      @after-enter="initUploadSettings"
    >
      <v-card>
        <v-card-title class="pa-4 d-flex align-center">
          <span class="text-h5">{{ t('upload.title') }}</span>
          <v-spacer />
          <v-btn
            icon="mdi-close"
            variant="text"
            :aria-label="t('upload.cancel')"
            @click="closeUploadDialog"
          />
        </v-card-title>

        <v-tabs v-model="uploadMode" grow class="mb-4">
          <v-tab value="file">{{ t('upload.fileUpload') }}</v-tab>
          <v-tab value="url">
            {{ t('upload.fromUrl') }}
            <v-badge
              color="warning"
              :content="t('upload.beta')"
              inline
              class="ml-2"
            />
          </v-tab>
        </v-tabs>

        <v-card-text class="pa-6 pt-2">
          <v-window v-model="uploadMode">
            <!-- 文件上传 -->
            <v-window-item value="file">
              <!-- 文件选择 -->
              <div
                class="upload-dropzone"
                :class="{ dragover: isDragging }"
                @drop.prevent="handleDrop"
                @dragover.prevent="isDragging = true"
                @dragleave="isDragging = false"
                @click="fileInput?.click()"
              >
                <v-icon size="64" color="primary">mdi-cloud-upload</v-icon>
                <p class="mt-4 text-h6">{{ t('upload.dropzone') }}</p>
                <p class="text-caption text-medium-emphasis mt-2">
                  {{ t('upload.supportedFormats') }}
                </p>
                <p class="text-caption text-medium-emphasis">
                  {{ t('upload.maxSize') }}
                </p>
                <p class="text-caption text-medium-emphasis">
                  {{ t('upload.folderHint') }}
                </p>
                <div class="mt-4 d-flex justify-center ga-2" @click.stop>
                  <v-btn
                    size="small"
                    variant="tonal"
                    @click="fileInput?.click()"
                  >
                    {{ t('upload.selectFile') }}
                  </v-btn>
                  <v-btn
                    size="small"
                    variant="tonal"
                    @click="folderInput?.click()"
                  >
                    {{ t('upload.selectFolder') }}
                  </v-btn>
                </div>
                <input
                  ref="fileInput"
                  type="file"
                  multiple
                  hidden
                  accept=".txt,.md,.markdown,.rst,.adoc,.pdf,.docx,.epub,.xls,.xlsx,text/markdown,text/plain,text/x-markdown"
                  @change="handleFileSelect"
                />
                <input
                  ref="folderInput"
                  type="file"
                  multiple
                  hidden
                  webkitdirectory
                  @change="handleFileSelect"
                />
              </div>

              <div v-if="selectedFiles.length > 0" class="mt-4">
                <div class="d-flex align-center justify-space-between mb-2">
                  <span class="text-subtitle-2"
                    >已选择 {{ selectedFiles.length }} 个文件</span
                  >
                  <v-btn variant="text" size="small" @click="selectedFiles = []"
                    >清空</v-btn
                  >
                </div>
                <div class="files-list">
                  <div
                    v-for="(file, index) in selectedFiles"
                    :key="index"
                    class="file-item pa-3 mb-2 rounded bg-surface-variant"
                  >
                    <div class="d-flex align-center justify-space-between">
                      <div class="d-flex align-center gap-2">
                        <v-icon>{{ getFileIcon(file.name) }}</v-icon>
                        <div>
                          <div class="font-weight-medium">{{ file.name }}</div>
                          <div class="text-caption">
                            {{ formatFileSize(file.size) }}
                          </div>
                        </div>
                      </div>
                      <v-btn
                        icon="mdi-close"
                        variant="text"
                        size="small"
                        :aria-label="t('documents.delete')"
                        @click="removeFile(index)"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </v-window-item>

            <!-- URL上传 -->
            <v-window-item value="url" class="pt-2">
              <!-- Tavily Key 快速配置 -->
              <div
                v-if="
                  tavilyConfigStatus === 'not_configured' ||
                  tavilyConfigStatus === 'error'
                "
                class="mb-4"
              >
                <v-alert
                  :type="tavilyConfigStatus === 'error' ? 'error' : 'info'"
                  variant="tonal"
                  density="compact"
                >
                  <div class="d-flex align-center justify-space-between">
                    <span>
                      {{
                        tavilyConfigStatus === 'error'
                          ? '检查网页搜索配置失败'
                          : '使用此功能需要配置 Tavily Key'
                      }}
                    </span>
                    <v-btn
                      size="small"
                      variant="flat"
                      @click="showTavilyDialog = true"
                    >
                      配置
                    </v-btn>
                  </div>
                </v-alert>
              </div>

              <v-text-field
                v-model="uploadUrl"
                :label="t('upload.urlPlaceholder')"
                variant="outlined"
                clearable
                :disabled="tavilyConfigStatus === 'not_configured'"
                autofocus
                :hint="t('upload.urlHint', { supported: 'HTML' })"
                persistent-hint
              />
            </v-window-item>
          </v-window>

          <!-- 清洗设置 (仅在URL模式下显示) -->
          <div v-if="uploadMode === 'url'" class="mt-6">
            <div class="d-flex align-center mb-4">
              <h3 class="text-h6">{{ t('upload.cleaningSettings') }}</h3>
            </div>
            <v-row>
              <v-col cols="12" sm="4">
                <v-switch
                  v-model="uploadSettings.enable_cleaning"
                  :label="t('upload.enableCleaning')"
                  color="primary"
                />
              </v-col>
              <v-col cols="12" sm="8">
                <v-select
                  v-model="uploadSettings.cleaning_provider_id"
                  :items="llmProviders"
                  item-title="id"
                  item-value="id"
                  :label="t('upload.cleaningProvider')"
                  :hint="t('upload.cleaningProviderHint')"
                  persistent-hint
                  variant="outlined"
                  density="compact"
                  :disabled="!uploadSettings.enable_cleaning"
                />
              </v-col>
            </v-row>
          </div>

          <!-- 分块设置 -->
          <div class="mt-6">
            <div class="d-flex align-center mb-4">
              <h3 class="text-h6">{{ t('upload.chunkSettings') }}</h3>
            </div>
            <v-row>
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model.number="uploadSettings.chunk_size"
                  :label="t('upload.chunkSize')"
                  :hint="t('upload.chunkSizeHint')"
                  persistent-hint
                  type="number"
                  variant="outlined"
                  density="compact"
                  :placeholder="props.kb?.chunk_size?.toString() || '512'"
                />
              </v-col>
              <v-col cols="12" sm="6">
                <v-text-field
                  v-model.number="uploadSettings.chunk_overlap"
                  :label="t('upload.chunkOverlap')"
                  :hint="t('upload.chunkOverlapHint')"
                  persistent-hint
                  type="number"
                  variant="outlined"
                  density="compact"
                  :placeholder="props.kb?.chunk_overlap?.toString() || '50'"
                />
              </v-col>
            </v-row>
          </div>

          <div class="mt-2">
            <h3 class="text-h6 mb-4">{{ t('upload.batchSettings') }}</h3>
            <v-row>
              <v-col cols="12" sm="4">
                <v-text-field
                  v-model.number="uploadSettings.batch_size"
                  :label="t('upload.batchSize')"
                  hint="每批处理的文本数量"
                  persistent-hint
                  type="number"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="12" sm="4">
                <v-text-field
                  v-model.number="uploadSettings.tasks_limit"
                  :label="t('upload.tasksLimit')"
                  hint="并发任务数量限制"
                  persistent-hint
                  type="number"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
              <v-col cols="12" sm="4">
                <v-text-field
                  v-model.number="uploadSettings.max_retries"
                  :label="t('upload.maxRetries')"
                  hint="失败时的最大重试次数"
                  persistent-hint
                  type="number"
                  variant="outlined"
                  density="compact"
                />
              </v-col>
            </v-row>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn
            variant="text"
            :disabled="uploading"
            @click="closeUploadDialog"
          >
            {{ t('upload.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="elevated"
            :loading="uploading"
            :disabled="isUploadDisabled"
            @click="startUpload"
          >
            {{ t('upload.submit') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="showDeleteDialog" max-width="450px">
      <v-card>
        <v-card-title class="pa-4 text-h6">{{
          t('documents.delete')
        }}</v-card-title>
        <v-card-text class="pa-6">
          <p>
            {{
              t('documents.deleteConfirm', {
                name: deleteTarget?.doc_name || '',
              })
            }}
          </p>
          <v-alert type="error" variant="tonal" density="compact" class="mt-4">
            {{ t('documents.deleteWarning') }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="showDeleteDialog = false">取消</v-btn>
          <v-btn
            color="error"
            variant="elevated"
            :loading="deleting"
            @click="deleteDocument"
          >
            删除
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>

    <!-- Tavily Key 配置对话框 -->
    <TavilyKeyDialog v-model="showTavilyDialog" @success="onTavilyKeySet" />
  </div>
</template>

<script setup lang="ts">
import TavilyKeyDialog from './TavilyKeyDialog.vue';
import { ref, watch, onMounted, onUnmounted, computed } from 'vue';
import { useRouter } from 'vue-router';
import { configProfileApi, knowledgeApi, providerApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { resolveErrorMessage } from '@/utils/errorUtils';
import {
  collectDroppedKnowledgeBaseFiles,
  collectFilesFromFileList,
} from '@/utils/knowledgeBaseUploadFiles';

const { tm: t } = useModuleI18n('features/knowledge-base/detail');
const router = useRouter();

interface KnowledgeBaseConfig {
  chunk_size?: number | null;
  chunk_overlap?: number | null;
  [key: string]: unknown;
}

interface UploadProgressState {
  stage: string;
  current: number;
  total: number;
}

interface DocumentItem {
  doc_id: string;
  doc_name: string;
  file_type: string;
  file_size: number;
  chunk_count: number;
  created_at: string;
  uploading?: boolean;
  taskId?: string;
  uploadProgress?: UploadProgressState;
}

interface LlmProviderItem {
  id: string;
  [key: string]: unknown;
}

interface UploadSettingsState {
  chunk_size: number | null;
  chunk_overlap: number | null;
  batch_size: number;
  tasks_limit: number;
  max_retries: number;
  enable_cleaning: boolean;
  cleaning_provider_id: string | null;
}

interface UrlUploadPayload {
  kb_id: string;
  url: string;
  batch_size: number;
  tasks_limit: number;
  max_retries: number;
  chunk_size?: number;
  chunk_overlap?: number;
  enable_cleaning?: true;
  cleaning_provider_id?: string;
  [key: string]: unknown;
}

interface DocumentsPayload {
  items?: DocumentItem[];
  total?: number;
}

interface UploadTaskPayload {
  task_id?: string;
  file_count?: number;
  url?: string;
}

interface KnowledgeTaskProgressPayload {
  file_index?: number;
  stage?: string;
  current?: number;
  total?: number;
}

interface KnowledgeTaskResultPayload {
  success_count?: number;
  failed_count?: number;
}

interface KnowledgeTaskPayload {
  status?: string;
  progress?: KnowledgeTaskProgressPayload;
  result?: KnowledgeTaskResultPayload;
  error?: string;
}

interface ProviderSettings {
  websearch_tavily_key?: string[];
  [key: string]: unknown;
}

interface DashboardConfig {
  provider_settings?: ProviderSettings;
  [key: string]: unknown;
}

const props = defineProps<{
  kbId: string;
  kb: KnowledgeBaseConfig;
}>();

const emit = defineEmits(['refresh']);

// 状态
const loading = ref(false);
const uploading = ref(false);
const deleting = ref(false);
const documents = ref<DocumentItem[]>([]);
const page = ref(1);
const pageSize = ref(10);
const total = ref(0);
const searchQuery = ref('');
const showUploadDialog = ref(false);
const showDeleteDialog = ref(false);
const selectedFiles = ref<File[]>([]);
const deleteTarget = ref<DocumentItem | null>(null);
const isDragging = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const folderInput = ref<HTMLInputElement | null>(null);
const uploadMode = ref('file'); // 'file' or 'url'
const uploadUrl = ref('');
const llmProviders = ref<LlmProviderItem[]>([]);
const progressPollingInterval = ref<number | null>(null);
const tavilyConfigStatus = ref('loading'); // 'loading', 'configured', 'not_configured', 'error'
const showTavilyDialog = ref(false);
let documentsRequestId = 0;

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

// 上传设置
const uploadSettings = ref<UploadSettingsState>({
  chunk_size: null as number | null,
  chunk_overlap: null as number | null,
  batch_size: 32,
  tasks_limit: 3,
  max_retries: 3,
  enable_cleaning: false,
  cleaning_provider_id: null as string | null,
});

// 初始化上传设置
const initUploadSettings = () => {
  uploadSettings.value = {
    chunk_size: props.kb?.chunk_size || null,
    chunk_overlap: props.kb?.chunk_overlap || null,
    batch_size: 32,
    tasks_limit: 3,
    max_retries: 3,
    enable_cleaning: false,
    cleaning_provider_id: null,
  };
};

const isUploadDisabled = computed(() => {
  if (uploading.value) {
    return true;
  }
  if (uploadMode.value === 'file') {
    return selectedFiles.value.length === 0;
  }
  if (uploadMode.value === 'url') {
    if (!uploadUrl.value) {
      return true;
    }
    if (
      uploadSettings.value.enable_cleaning &&
      !uploadSettings.value.cleaning_provider_id
    ) {
      return true;
    }
    return false;
  }
  return true;
});

// 表格列
const headers = [
  { title: t('documents.name'), key: 'doc_name', sortable: false },
  { title: t('documents.type'), key: 'file_type', sortable: false },
  { title: t('documents.size'), key: 'file_size', sortable: false },
  { title: t('documents.chunks'), key: 'chunk_count', sortable: false },
  { title: t('documents.createdAt'), key: 'created_at', sortable: false },
  {
    title: t('documents.actions'),
    key: 'actions',
    sortable: false,
    align: 'end' as const,
  },
];

// 加载文档列表
const loadDocuments = async () => {
  const requestId = ++documentsRequestId;
  loading.value = true;
  try {
    const response = await knowledgeApi.documents(props.kbId, {
      page: page.value,
      page_size: pageSize.value,
      search: searchQuery.value.trim() || undefined,
    });
    if (requestId !== documentsRequestId) return;
    if (response.data.status === 'ok') {
      const payload = response.data.data as DocumentsPayload | undefined;
      documents.value = payload?.items || [];
      total.value = payload?.total || 0;
    }
  } catch (error) {
    if (requestId !== documentsRequestId) return;
    console.error('Failed to load documents:', error);
    showSnackbar(t('documents.loadFailed'), 'error');
  } finally {
    if (requestId === documentsRequestId) loading.value = false;
  }
};

const handlePageChange = (newPage: number) => {
  page.value = newPage;
  void loadDocuments();
};

const handlePageSizeChange = (newPageSize: number) => {
  pageSize.value = newPageSize;
  page.value = 1;
  void loadDocuments();
};

// 文件选择
const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement;
  if (target.files && target.files.length > 0) {
    const newFiles = collectFilesFromFileList(target.files);
    if (newFiles.length === 0) {
      showSnackbar(t('upload.noSupportedFiles'), 'warning');
    } else {
      addFiles(newFiles);
    }
  }
  target.value = '';
};

const addFiles = (files: File[]) => {
  selectedFiles.value.push(...files);
};

const removeFile = (index: number) => {
  selectedFiles.value.splice(index, 1);
};

const handleDrop = async (event: DragEvent) => {
  isDragging.value = false;
  if (!event.dataTransfer) {
    return;
  }
  const newFiles = await collectDroppedKnowledgeBaseFiles(event.dataTransfer);
  if (newFiles.length === 0) {
    showSnackbar(t('upload.noSupportedFiles'), 'warning');
    return;
  }
  addFiles(newFiles);
};

// 上传调度器
const startUpload = async () => {
  if (uploadMode.value === 'file') {
    await uploadFiles();
  } else if (uploadMode.value === 'url') {
    await uploadFromUrl();
  }
};

// 上传文件
const uploadFiles = async () => {
  if (selectedFiles.value.length === 0) {
    showSnackbar(t('upload.fileRequired'), 'warning');
    return;
  }

  uploading.value = true;

  try {
    const formData = new FormData();

    // 添加所有文件
    selectedFiles.value.forEach((file, index) => {
      formData.append(`file${index}`, file, file.name);
    });

    formData.append('kb_id', props.kbId);
    if (uploadSettings.value.chunk_size) {
      formData.append('chunk_size', uploadSettings.value.chunk_size.toString());
    }
    if (uploadSettings.value.chunk_overlap) {
      formData.append(
        'chunk_overlap',
        uploadSettings.value.chunk_overlap.toString(),
      );
    }
    formData.append('batch_size', uploadSettings.value.batch_size.toString());
    formData.append('tasks_limit', uploadSettings.value.tasks_limit.toString());
    formData.append('max_retries', uploadSettings.value.max_retries.toString());

    const response = await knowledgeApi.uploadDocument(props.kbId, formData);

    if (response.data.status === 'ok') {
      const result = response.data.data as UploadTaskPayload | undefined;
      const taskId = result?.task_id || '';

      showSnackbar(`正在后台上传 ${result?.file_count || 0} 个文件...`, 'info');

      // 为每个文件添加占位条目到文档列表
      const uploadingDocs: DocumentItem[] = selectedFiles.value.map(
        (file, index) => ({
          doc_id: `uploading_${taskId}_${index}`,
          doc_name: file.name,
          file_type: file.name.split('.').pop() || '',
          file_size: file.size,
          chunk_count: 0,
          created_at: new Date().toISOString(),
          uploading: true,
          taskId,
          uploadProgress: {
            stage: 'waiting',
            current: 0,
            total: 100,
          },
        }),
      );

      // 添加到文档列表顶部
      documents.value = [...uploadingDocs, ...documents.value];

      // 关闭对话框
      closeUploadDialog();

      // 开始轮询进度
      if (taskId) {
        startProgressPolling(taskId);
      }
    } else {
      showSnackbar(
        response.data.message || t('documents.uploadFailed'),
        'error',
      );
    }
  } catch (error) {
    console.error('Failed to upload document:', error);
    showSnackbar(
      resolveErrorMessage(error, t('documents.uploadFailed')),
      'error',
    );
  } finally {
    uploading.value = false;
  }
};

// 从 URL 上传
const uploadFromUrl = async () => {
  if (!uploadUrl.value) {
    showSnackbar(t('upload.urlRequired'), 'warning');
    return;
  }

  uploading.value = true;

  try {
    const payload: UrlUploadPayload = {
      kb_id: props.kbId,
      url: uploadUrl.value,
      batch_size: uploadSettings.value.batch_size,
      tasks_limit: uploadSettings.value.tasks_limit,
      max_retries: uploadSettings.value.max_retries,
    };
    if (uploadSettings.value.chunk_size) {
      payload.chunk_size = uploadSettings.value.chunk_size;
    }
    if (uploadSettings.value.chunk_overlap) {
      payload.chunk_overlap = uploadSettings.value.chunk_overlap;
    }
    if (uploadSettings.value.enable_cleaning) {
      payload.enable_cleaning = true;
      if (uploadSettings.value.cleaning_provider_id) {
        payload.cleaning_provider_id =
          uploadSettings.value.cleaning_provider_id;
      }
    }

    const response = await knowledgeApi.importDocumentFromUrl(
      props.kbId,
      payload,
    );

    if (response.data.status === 'ok') {
      const result = response.data.data as UploadTaskPayload | undefined;
      const taskId = result?.task_id || '';

      showSnackbar(`正在从 URL 后台提取内容...`, 'info');

      // 添加占位条目
      const uploadingDoc: DocumentItem = {
        doc_id: `uploading_${taskId}_0`,
        doc_name: result?.url || uploadUrl.value,
        file_type: 'url',
        file_size: 0, // URL has no size
        chunk_count: 0,
        created_at: new Date().toISOString(),
        uploading: true,
        taskId,
        uploadProgress: {
          stage: 'waiting',
          current: 0,
          total: 100,
        },
      };

      documents.value = [uploadingDoc, ...documents.value];
      closeUploadDialog();

      if (taskId) {
        startProgressPolling(taskId);
      }
    } else {
      showSnackbar(
        response.data.message || t('documents.uploadFailed'),
        'error',
      );
    }
  } catch (error: unknown) {
    console.error('Failed to upload from URL:', error);
    const message = resolveErrorMessage(error, t('documents.uploadFailed'));
    showSnackbar(message, 'error');
  } finally {
    uploading.value = false;
  }
};

// 开始轮询进度
const startProgressPolling = (taskId: string) => {
  // 如果已经在轮询，先停止
  if (progressPollingInterval.value) {
    stopProgressPolling();
  }

  progressPollingInterval.value = window.setInterval(async () => {
    try {
      const response = await knowledgeApi.task(taskId);

      if (response.data.status === 'ok') {
        const data = response.data.data as KnowledgeTaskPayload | undefined;
        const status = data?.status;

        if (status === 'processing' && data?.progress) {
          // 更新进度
          const progress = data.progress;
          const fileIndex = progress.file_index || 0;

          // 更新对应文件的进度
          documents.value = documents.value.map((doc) => {
            if (doc.taskId === taskId) {
              const docIndex = parseInt(doc.doc_id.split('_').pop() || '0', 10);
              if (docIndex === fileIndex) {
                return {
                  ...doc,
                  uploadProgress: {
                    stage: progress.stage || 'waiting',
                    current: progress.current || 0,
                    total: progress.total || 100,
                  },
                };
              }
            }
            return doc;
          });
        } else if (status === 'completed') {
          // 任务完成
          stopProgressPolling();

          const result = data?.result;
          const successCount = result?.success_count || 0;
          const failedCount = result?.failed_count || 0;

          // 移除上传中的占位文档
          documents.value = documents.value.filter(
            (doc) => doc.taskId !== taskId,
          );

          // 重新加载文档列表
          await loadDocuments();
          emit('refresh');

          if (failedCount === 0) {
            showSnackbar(`成功上传 ${successCount} 个文档`);
          } else {
            showSnackbar(
              `上传完成: ${successCount} 个成功, ${failedCount} 个失败`,
              'warning',
            );
          }
        } else if (status === 'failed') {
          // 任务失败
          stopProgressPolling();

          // 移除上传中的占位文档
          documents.value = documents.value.filter(
            (doc) => doc.taskId !== taskId,
          );

          showSnackbar(`上传失败: ${data?.error || '未知错误'}`, 'error');
        }
      } else {
        // 任务不存在，停止轮询
        stopProgressPolling();
        documents.value = documents.value.filter(
          (doc) => doc.taskId !== taskId,
        );
      }
    } catch (error) {
      console.error('Failed to fetch progress:', error);
      // 不立即停止，允许重试
    }
  }, 500); // 每500ms轮询一次
};

// 停止轮询进度
const stopProgressPolling = () => {
  if (progressPollingInterval.value) {
    clearInterval(progressPollingInterval.value);
    progressPollingInterval.value = null;
  }
};

// 获取上传百分比
const getUploadPercentage = (item: DocumentItem) => {
  if (!item.uploadProgress) return 0;
  const { current, total } = item.uploadProgress;
  if (!total || total === 0) return 0;
  return (current / total) * 100;
};

// 获取阶段文本
const getStageText = (stage: string) => {
  const stageMap: Record<string, string> = {
    waiting: '等待中...',
    extracting: '提取内容...',
    cleaning: '清洗内容...',
    parsing: '解析文档...',
    chunking: '文本分块...',
    embedding: '生成向量...',
  };
  return stageMap[stage] || stage;
};

// 关闭上传对话框
const closeUploadDialog = () => {
  showUploadDialog.value = false;
  selectedFiles.value = [];
  uploadUrl.value = '';
  uploadMode.value = 'file';
  initUploadSettings();
};

// 查看文档
const viewDocument = (doc: DocumentItem) => {
  void router.push({
    name: 'NativeDocumentDetail',
    params: { kbId: props.kbId, docId: doc.doc_id },
  });
};

// 确认删除
const confirmDelete = (doc: DocumentItem) => {
  deleteTarget.value = doc;
  showDeleteDialog.value = true;
};

// 删除文档
const deleteDocument = async () => {
  if (!deleteTarget.value) return;

  deleting.value = true;
  try {
    const response = await knowledgeApi.deleteDocument(
      props.kbId,
      deleteTarget.value.doc_id,
    );

    if (response.data.status === 'ok') {
      showSnackbar(t('documents.deleteSuccess'));
      showDeleteDialog.value = false;
      await loadDocuments();
      emit('refresh');
    } else {
      showSnackbar(
        response.data.message || t('documents.deleteFailed'),
        'error',
      );
    }
  } catch (error) {
    console.error('Failed to delete document:', error);
    showSnackbar(t('documents.deleteFailed'), 'error');
  } finally {
    deleting.value = false;
  }
};

// 工具函数
const getFileIcon = (fileType: string) => {
  const type = fileType?.toLowerCase() || '';
  if (type.includes('pdf')) return 'mdi-file-pdf-box';
  if (type.includes('epub')) return 'mdi-book-open-page-variant';
  if (type.includes('rst') || type.includes('adoc'))
    return 'mdi-file-document-outline';
  if (type.includes('md') || type.includes('markdown'))
    return 'mdi-language-markdown';
  if (type.includes('txt')) return 'mdi-file-document-outline';
  if (type.includes('url')) return 'mdi-link-variant';
  return 'mdi-file';
};

const getFileColor = (fileType: string) => {
  const type = fileType?.toLowerCase() || '';
  if (type.includes('pdf')) return 'error';
  if (type.includes('epub')) return 'warning';
  if (type.includes('rst') || type.includes('adoc')) return 'success';
  if (type.includes('md')) return 'info';
  if (type.includes('txt')) return 'success';
  if (type.includes('url')) return 'primary';
  return 'grey';
};

const formatFileSize = (bytes: number) => {
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

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

// 加载LLM providers
const loadLlmProviders = async () => {
  try {
    const response = await providerApi.listByProviderType('chat_completion');
    if (response.data.status === 'ok') {
      llmProviders.value = Array.isArray(response.data.data)
        ? (response.data.data as LlmProviderItem[])
        : [];
    }
  } catch (error) {
    console.error('Failed to load LLM providers:', error);
  }
};

// 检查Tavily Key配置
const checkTavilyConfig = async () => {
  tavilyConfigStatus.value = 'loading';
  try {
    const response = await configProfileApi.get('default');
    if (response.data.status === 'ok') {
      const payload = response.data.data as
        { config?: DashboardConfig } | undefined;
      const config = payload?.config || {};
      const tavilyKeys = config.provider_settings?.websearch_tavily_key;
      if (
        Array.isArray(tavilyKeys) &&
        tavilyKeys.length > 0 &&
        tavilyKeys.some((key) => key.trim() !== '')
      ) {
        tavilyConfigStatus.value = 'configured';
      } else {
        tavilyConfigStatus.value = 'not_configured';
      }
    } else {
      tavilyConfigStatus.value = 'error';
    }
  } catch (error) {
    console.warn('Failed to check Tavily key config:', error);
    tavilyConfigStatus.value = 'error';
  }
};

const onTavilyKeySet = () => {
  showSnackbar('Tavily API Key 配置成功', 'success');
  void checkTavilyConfig();
};

watch(searchQuery, (_value, _oldValue, onCleanup) => {
  page.value = 1;
  documentsRequestId += 1;
  const timeoutId = window.setTimeout(() => void loadDocuments(), 300);
  onCleanup(() => void window.clearTimeout(timeoutId));
});

onMounted(() => {
  void loadDocuments();
  void loadLlmProviders();
  void checkTavilyConfig();
});

onUnmounted(() => {
  documentsRequestId += 1;
  stopProgressPolling();
});
</script>

<style scoped>
.documents-search {
  max-width: 300px;
}

.documents-tab__name {
  padding: var(--astrbot-space-1) 0;
}

.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--astrbot-space-4);
  flex-wrap: wrap;
}

.upload-dropzone {
  border: 2px dashed rgb(var(--v-theme-outline));
  border-radius: 8px;
  padding: var(--astrbot-space-8) var(--astrbot-space-6);
  text-align: center;
  cursor: pointer;
  background: rgb(var(--v-theme-surface-variant));
}

.upload-dropzone:hover,
.upload-dropzone.dragover {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-surface-variant));
}

.files-list {
  max-height: 300px;
  overflow-y: auto;
}

.file-item:hover {
  background: rgb(var(--v-theme-surface-variant));
}

@media (max-width: 768px) {
  .action-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .action-bar > * {
    width: 100%;
  }
}
</style>
