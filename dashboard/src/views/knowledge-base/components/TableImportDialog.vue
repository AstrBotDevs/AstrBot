<template>
  <v-dialog :model-value="modelValue" max-width="820px" persistent @update:model-value="onDialogToggle">
    <v-card>
      <v-card-title class="pa-4 d-flex align-center">
        <span class="text-h5">{{ t('table.title') }}</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" @click="close" />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-6">
        <!-- 阶段一：选择文件 -->
        <div v-if="phase === 'select'">
          <div class="upload-dropzone" :class="{ dragover: isDragging }" @drop.prevent="handleDrop"
            @dragover.prevent="isDragging = true" @dragleave="isDragging = false" @click="fileInput?.click()">
            <v-icon size="64" color="primary">mdi-table-large-plus</v-icon>
            <p class="mt-4 text-h6">{{ t('table.dropzone') }}</p>
            <p class="text-caption text-medium-emphasis mt-2">{{ t('table.supportedFormats') }}</p>
            <input ref="fileInput" type="file" hidden accept=".csv,.xls,.xlsx" @change="handleFileSelect" />
          </div>

          <div v-if="selectedFile" class="file-item pa-3 mt-4 rounded bg-surface-variant">
            <div class="d-flex align-center justify-space-between">
              <div class="d-flex align-center gap-2">
                <v-icon color="success">mdi-file-table-outline</v-icon>
                <div>
                  <div class="font-weight-medium">{{ selectedFile.name }}</div>
                  <div class="text-caption">{{ formatFileSize(selectedFile.size) }}</div>
                </div>
              </div>
              <v-btn icon="mdi-close" variant="text" size="small" @click="clearFile" />
            </div>
          </div>

          <v-text-field v-model.number="headerRow" :label="t('table.headerRow')" :hint="t('table.headerRowHint')"
            persistent-hint type="number" variant="outlined" density="compact" class="mt-4" style="max-width: 240px" />
        </div>

        <!-- 阶段二：列配置 + 数据预览 -->
        <div v-else>
          <div class="d-flex align-center mb-2">
            <v-icon color="success" class="mr-2">mdi-file-table-outline</v-icon>
            <span class="font-weight-medium">{{ selectedFile?.name }}</span>
            <v-chip size="x-small" variant="tonal" class="ml-3">{{ t('table.totalRows', { count: totalRows }) }}</v-chip>
            <v-spacer />
            <v-btn variant="text" size="small" prepend-icon="mdi-restore" @click="resetToSelect">
              {{ t('table.reselect') }}
            </v-btn>
          </div>

          <h3 class="text-subtitle-1 font-weight-bold mt-4">{{ t('table.columnConfig') }}</h3>
          <p class="text-caption text-medium-emphasis mb-2">{{ t('table.columnConfigHint') }}</p>

          <v-table density="compact" class="config-table">
            <thead>
              <tr>
                <th>{{ t('table.columnName') }}</th>
                <th class="text-center" style="width: 120px">{{ t('table.indexColumn') }}</th>
                <th class="text-center" style="width: 120px">{{ t('table.returnColumn') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(col, idx) in columns" :key="idx">
                <td class="font-weight-medium">{{ col.name }}</td>
                <td class="text-center">
                  <v-checkbox v-model="col.is_index" color="primary" hide-details density="compact"
                    class="d-inline-flex" />
                </td>
                <td class="text-center">
                  <v-checkbox v-model="col.is_returned" color="primary" hide-details density="compact"
                    class="d-inline-flex" />
                </td>
              </tr>
            </tbody>
          </v-table>

          <h3 class="text-subtitle-1 font-weight-bold mt-6 mb-2">{{ t('table.dataPreview') }}</h3>
          <div class="preview-scroll">
            <v-table density="compact" class="preview-table">
              <thead>
                <tr>
                  <th v-for="(h, i) in headers" :key="i" :class="{ 'index-col': columns[i]?.is_index }">{{ h }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in sampleRows" :key="ri">
                  <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </div>
      </v-card-text>

      <v-divider />

      <v-card-actions class="pa-4">
        <v-btn v-if="phase === 'configure'" variant="text" prepend-icon="mdi-arrow-left" @click="resetToSelect">
          {{ t('table.back') }}
        </v-btn>
        <v-spacer />
        <v-btn variant="text" :disabled="previewing || importing" @click="close">
          {{ t('table.cancel') }}
        </v-btn>
        <v-btn v-if="phase === 'select'" color="primary" variant="elevated" :loading="previewing"
          :disabled="!selectedFile" @click="doPreview">
          {{ t('table.preview') }}
        </v-btn>
        <v-btn v-else color="primary" variant="elevated" :loading="importing" :disabled="!hasIndexColumn"
          @click="doImport">
          {{ t('table.import') }}
        </v-btn>
      </v-card-actions>
    </v-card>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { knowledgeApi } from '@/api/v1'
import { useModuleI18n } from '@/i18n/composables'

const { tm: t } = useModuleI18n('features/knowledge-base/detail')

const props = defineProps<{
  modelValue: boolean
  kbId: string
}>()

const emit = defineEmits(['update:modelValue', 'started'])

interface ColumnConfig {
  name: string
  is_index: boolean
  is_returned: boolean
}

const phase = ref<'select' | 'configure'>('select')
const selectedFile = ref<File | null>(null)
const headerRow = ref(0)
const isDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const previewing = ref(false)
const importing = ref(false)

const headers = ref<string[]>([])
const sampleRows = ref<string[][]>([])
const totalRows = ref(0)
const columns = ref<ColumnConfig[]>([])

const snackbar = ref({ show: false, text: '', color: 'success' })

const showSnackbar = (text: string, color = 'success') => {
  snackbar.value.text = text
  snackbar.value.color = color
  snackbar.value.show = true
}

const hasIndexColumn = computed(() => columns.value.some((c) => c.is_index))

const onDialogToggle = (value: boolean) => {
  if (!value) {
    close()
  }
}

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    selectedFile.value = target.files[0]
  }
  target.value = ''
}

const handleDrop = (event: DragEvent) => {
  isDragging.value = false
  if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
    selectedFile.value = event.dataTransfer.files[0]
  }
}

const clearFile = () => {
  selectedFile.value = null
}

const resetToSelect = () => {
  phase.value = 'select'
}

const doPreview = async () => {
  if (!selectedFile.value) {
    showSnackbar(t('table.fileRequired'), 'warning')
    return
  }
  previewing.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('header_row', String(headerRow.value || 0))
    formData.append('preview_rows', '20')

    const response = await knowledgeApi.previewTable(props.kbId, formData)
    if (response.data.status === 'ok') {
      const data = response.data.data
      headers.value = data.headers || []
      sampleRows.value = data.rows || []
      totalRows.value = data.total_rows || 0
      columns.value = headers.value.map((name: string, idx: number) => ({
        name,
        is_index: idx === 0,
        is_returned: true
      }))
      phase.value = 'configure'
    } else {
      showSnackbar(response.data.message || t('table.previewFailed'), 'error')
    }
  } catch (error: any) {
    console.error('Failed to preview table:', error)
    showSnackbar(error.response?.data?.message || t('table.previewFailed'), 'error')
  } finally {
    previewing.value = false
  }
}

const doImport = async () => {
  if (!selectedFile.value) {
    showSnackbar(t('table.fileRequired'), 'warning')
    return
  }
  if (!hasIndexColumn.value) {
    showSnackbar(t('table.indexRequired'), 'warning')
    return
  }
  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('header_row', String(headerRow.value || 0))
    formData.append('columns_config', JSON.stringify(columns.value))

    const response = await knowledgeApi.importTable(props.kbId, formData)
    if (response.data.status === 'ok') {
      const result = response.data.data
      emit('started', { taskId: result.task_id, fileName: selectedFile.value.name })
      close()
    } else {
      showSnackbar(response.data.message || t('table.importFailed'), 'error')
    }
  } catch (error: any) {
    console.error('Failed to import table:', error)
    showSnackbar(error.response?.data?.message || t('table.importFailed'), 'error')
  } finally {
    importing.value = false
  }
}

const close = () => {
  if (previewing.value || importing.value) {
    return
  }
  phase.value = 'select'
  selectedFile.value = null
  headerRow.value = 0
  headers.value = []
  sampleRows.value = []
  totalRows.value = 0
  columns.value = []
  emit('update:modelValue', false)
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
</script>

<style scoped>
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
}

.config-table {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}

.preview-scroll {
  max-height: 280px;
  overflow: auto;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}

.preview-table th {
  white-space: nowrap;
  font-weight: 600;
}

.preview-table th.index-col {
  color: rgb(var(--v-theme-primary));
}

.preview-table td {
  white-space: nowrap;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
