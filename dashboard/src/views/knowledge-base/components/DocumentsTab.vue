<template>
  <div class="documents-tab">
    <!-- 操作栏 -->
    <div class="action-bar mb-4">
      <v-btn
        prepend-icon="mdi-upload"
        color="primary"
        variant="elevated"
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
        style="max-width: 300px"
      />
    </div>

    <!-- 文档列表 -->
    <v-card elevation="2">
      <v-data-table
        :headers="headers"
        :items="documents"
        :loading="loading"
        :search="searchQuery"
        :items-per-page="10"
      >
        <template #item.doc_name="{ item }">
          <div class="d-flex align-center gap-2">
            <v-icon :color="getFileColor(item.file_type)">
              {{ getFileIcon(item.file_type) }}
            </v-icon>
            <span class="font-weight-medium">{{ item.doc_name }}</span>
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
            @click="viewDocument(item)"
          />
          <v-btn
            icon="mdi-delete"
            variant="text"
            size="small"
            color="error"
            @click="confirmDelete(item)"
          />
        </template>

        <template #no-data>
          <div class="text-center py-8">
            <v-icon size="64" color="grey-lighten-2">mdi-file-document-outline</v-icon>
            <p class="mt-4 text-medium-emphasis">{{ t('documents.empty') }}</p>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <!-- 上传对话框 -->
    <v-dialog v-model="showUploadDialog" max-width="600px" persistent>
      <v-card>
        <v-card-title class="pa-4">
          <span class="text-h5">{{ t('upload.title') }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="closeUploadDialog" />
        </v-card-title>

        <v-divider />

        <v-card-text class="pa-6">
          <!-- 文件选择 -->
          <div
            class="upload-dropzone"
            :class="{ 'dragover': isDragging }"
            @drop.prevent="handleDrop"
            @dragover.prevent="isDragging = true"
            @dragleave="isDragging = false"
            @click="$refs.fileInput.click()"
          >
            <v-icon size="64" color="primary">mdi-cloud-upload</v-icon>
            <p class="mt-4 text-h6">{{ t('upload.dropzone') }}</p>
            <p class="text-caption text-medium-emphasis mt-2">{{ t('upload.supportedFormats') }}</p>
            <p class="text-caption text-medium-emphasis">{{ t('upload.maxSize') }}</p>
            <input
              ref="fileInput"
              type="file"
              hidden
              accept=".txt,.md,.pdf"
              @change="handleFileSelect"
            />
          </div>

          <div v-if="selectedFile" class="mt-4 pa-4 rounded bg-surface-variant">
            <div class="d-flex align-center justify-space-between">
              <div class="d-flex align-center gap-2">
                <v-icon>{{ getFileIcon(selectedFile.name) }}</v-icon>
                <div>
                  <div class="font-weight-medium">{{ selectedFile.name }}</div>
                  <div class="text-caption">{{ formatFileSize(selectedFile.size) }}</div>
                </div>
              </div>
              <v-btn icon="mdi-close" variant="text" size="small" @click="selectedFile = null" />
            </div>
          </div>

          <!-- 分块设置 -->
          <v-expansion-panels class="mt-4">
            <v-expansion-panel>
              <v-expansion-panel-title>
                <v-icon start>mdi-cog</v-icon>
                {{ t('upload.chunkSettings') }}
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-text-field
                  v-model.number="uploadSettings.chunk_size"
                  :label="t('upload.chunkSize')"
                  :hint="t('upload.chunkSizeHint')"
                  type="number"
                  variant="outlined"
                  density="compact"
                  class="mb-2"
                />
                <v-text-field
                  v-model.number="uploadSettings.chunk_overlap"
                  :label="t('upload.chunkOverlap')"
                  :hint="t('upload.chunkOverlapHint')"
                  type="number"
                  variant="outlined"
                  density="compact"
                />
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
        </v-card-text>

        <v-divider />

        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="closeUploadDialog">
            {{ t('upload.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="elevated"
            @click="uploadDocument"
            :loading="uploading"
            :disabled="!selectedFile"
          >
            {{ t('upload.submit') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="showDeleteDialog" max-width="450px">
      <v-card>
        <v-card-title class="pa-4 text-h6">{{ t('documents.delete') }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-6">
          <p>{{ t('documents.deleteConfirm', { name: deleteTarget?.doc_name || '' }) }}</p>
          <v-alert type="error" variant="tonal" density="compact" class="mt-4">
            {{ t('documents.deleteWarning') }}
          </v-alert>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="showDeleteDialog = false">取消</v-btn>
          <v-btn color="error" variant="elevated" @click="deleteDocument" :loading="deleting">
            删除
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
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

const { tm: t } = useModuleI18n('features/knowledge-base/detail')
const router = useRouter()

const props = defineProps<{
  kbId: string
  kb: any
}>()

const emit = defineEmits(['refresh'])

// 状态
const loading = ref(false)
const uploading = ref(false)
const deleting = ref(false)
const documents = ref<any[]>([])
const searchQuery = ref('')
const showUploadDialog = ref(false)
const showDeleteDialog = ref(false)
const selectedFile = ref<File | null>(null)
const deleteTarget = ref<any>(null)
const isDragging = ref(false)

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

// 上传设置
const uploadSettings = ref({
  chunk_size: null,
  chunk_overlap: null
})

// 表格列
const headers = [
  { title: t('documents.name'), key: 'doc_name', sortable: true },
  { title: t('documents.type'), key: 'file_type', sortable: true },
  { title: t('documents.size'), key: 'file_size', sortable: true },
  { title: t('documents.chunks'), key: 'chunk_count', sortable: true },
  { title: t('documents.createdAt'), key: 'created_at', sortable: true },
  { title: t('documents.actions'), key: 'actions', sortable: false, align: 'end' }
]

// 加载文档列表
const loadDocuments = async () => {
  loading.value = true
  try {
    const response = await axios.get('/api/kb/document/list', {
      params: { kb_id: props.kbId }
    })
    if (response.data.status === 'ok') {
      documents.value = response.data.data.items || []
    }
  } catch (error) {
    console.error('Failed to load documents:', error)
    showSnackbar('加载文档列表失败', 'error')
  } finally {
    loading.value = false
  }
}

// 文件选择
const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files[0]) {
    selectedFile.value = target.files[0]
  }
}

// 拖放上传
const handleDrop = (event: DragEvent) => {
  isDragging.value = false
  if (event.dataTransfer?.files && event.dataTransfer.files[0]) {
    selectedFile.value = event.dataTransfer.files[0]
  }
}

// 上传文档
const uploadDocument = async () => {
  if (!selectedFile.value) {
    showSnackbar(t('upload.fileRequired'), 'warning')
    return
  }

  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('kb_id', props.kbId)
    if (uploadSettings.value.chunk_size) {
      formData.append('chunk_size', uploadSettings.value.chunk_size.toString())
    }
    if (uploadSettings.value.chunk_overlap) {
      formData.append('chunk_overlap', uploadSettings.value.chunk_overlap.toString())
    }

    const response = await axios.post('/api/kb/document/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (response.data.status === 'ok') {
      showSnackbar(t('documents.uploadSuccess'))
      closeUploadDialog()
      await loadDocuments()
      emit('refresh')
    } else {
      showSnackbar(response.data.message || t('documents.uploadFailed'), 'error')
    }
  } catch (error) {
    console.error('Failed to upload document:', error)
    showSnackbar(t('documents.uploadFailed'), 'error')
  } finally {
    uploading.value = false
  }
}

// 关闭上传对话框
const closeUploadDialog = () => {
  showUploadDialog.value = false
  selectedFile.value = null
  uploadSettings.value = { chunk_size: null, chunk_overlap: null }
}

// 查看文档
const viewDocument = (doc: any) => {
  router.push({
    name: 'NativeDocumentDetail',
    params: { kbId: props.kbId, docId: doc.doc_id }
  })
}

// 确认删除
const confirmDelete = (doc: any) => {
  deleteTarget.value = doc
  showDeleteDialog.value = true
}

// 删除文档
const deleteDocument = async () => {
  if (!deleteTarget.value) return

  deleting.value = true
  try {
    const response = await axios.post('/api/kb/document/delete', {
      doc_id: deleteTarget.value.doc_id
    })

    if (response.data.status === 'ok') {
      showSnackbar(t('documents.deleteSuccess'))
      showDeleteDialog.value = false
      await loadDocuments()
      emit('refresh')
    } else {
      showSnackbar(response.data.message || t('documents.deleteFailed'), 'error')
    }
  } catch (error) {
    console.error('Failed to delete document:', error)
    showSnackbar(t('documents.deleteFailed'), 'error')
  } finally {
    deleting.value = false
  }
}

// 工具函数
const getFileIcon = (fileType: string) => {
  const type = fileType?.toLowerCase() || ''
  if (type.includes('pdf')) return 'mdi-file-pdf-box'
  if (type.includes('md') || type.includes('markdown')) return 'mdi-language-markdown'
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
  loadDocuments()
})
</script>

<style scoped>
.documents-tab {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.upload-dropzone {
  border: 2px dashed rgba(var(--v-theme-primary), 0.3);
  border-radius: 12px;
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s ease;
  background: rgba(var(--v-theme-surface-variant), 0.3);
}

.upload-dropzone:hover,
.upload-dropzone.dragover {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.05);
  transform: scale(1.02);
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
