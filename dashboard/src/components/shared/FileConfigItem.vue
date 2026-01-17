<template>
  <div class="file-config-item">
    <div class="d-flex align-center gap-2">
      <v-btn size="small" color="primary" variant="tonal" @click="dialog = true">
        {{ tm('fileUpload.button') }}
      </v-btn>
      <span class="text-caption text-medium-emphasis">
        {{ fileCountText }}
      </span>
    </div>

    <v-dialog v-model="dialog" max-width="1200" width="1200">
      <v-card class="file-dialog-card">
        <v-card-title class="d-flex align-center">
          <span class="text-h6">{{ tm('fileUpload.dialogTitle') }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
        </v-card-title>

        <v-card-text class="file-dialog-body">
          <div class="file-dialog">
            <div v-if="fileList.length === 0" class="empty-text">
              {{ tm('fileUpload.empty') }}
            </div>

            <div class="file-grid">
              <div v-for="filePath in fileList" :key="filePath" class="file-pill">
                <span class="file-pill-name">{{ getDisplayName(filePath) }}</span>
                <v-btn
                  icon="mdi-close"
                  size="x-small"
                  variant="text"
                  class="file-pill-delete"
                  @click="deleteFile(filePath)"
                />
              </div>

              <div
                class="upload-tile"
                :class="{ dragover: isDragging }"
                @drop.prevent="handleDrop"
                @dragover.prevent="isDragging = true"
                @dragleave="isDragging = false"
                @click="openFilePicker"
              >
                <div class="upload-icon">
                  <v-icon size="28" color="primary">mdi-plus</v-icon>
                </div>
                <div class="upload-text">{{ tm('fileUpload.dropzone') }}</div>
                <div v-if="allowedTypesText" class="upload-hint">
                  {{ tm('fileUpload.allowedTypes', { types: allowedTypesText }) }}
                </div>
                <input
                  ref="fileInput"
                  type="file"
                  multiple
                  hidden
                  :accept="acceptAttr"
                  @change="handleFileSelect"
                />
              </div>
            </div>
          </div>
        </v-card-text>

        <v-card-actions class="file-dialog-actions">
          <v-spacer />
          <v-btn color="primary" variant="elevated" @click="dialog = false">
            {{ tm('fileUpload.done') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import axios from 'axios'
import { useToast } from '@/utils/toast'
import { useModuleI18n } from '@/i18n/composables'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  itemMeta: {
    type: Object,
    default: null
  },
  pluginName: {
    type: String,
    default: ''
  },
  configKey: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue'])
const { tm } = useModuleI18n('features/config')
const toast = useToast()

const dialog = ref(false)
const isDragging = ref(false)
const fileInput = ref(null)
const uploading = ref(false)
const MAX_FILE_BYTES = 500 * 1024 * 1024
const MAX_FILE_MB = 500

const fileList = computed({
  get: () => (Array.isArray(props.modelValue) ? props.modelValue : []),
  set: (val) => emit('update:modelValue', val)
})

const acceptAttr = computed(() => {
  const types = props.itemMeta?.file_types
  if (!Array.isArray(types) || types.length === 0) {
    return undefined
  }
  return types
    .map((ext) => `.${String(ext).replace(/^\\./, '')}`)
    .join(',')
})

const allowedTypesText = computed(() => {
  const types = props.itemMeta?.file_types
  if (!Array.isArray(types) || types.length === 0) {
    return ''
  }
  return types.map((ext) => String(ext).replace(/^\\./, '')).join(', ')
})

const fileCountText = computed(() => {
  return tm('fileUpload.fileCount', { count: fileList.value.length })
})

const openFilePicker = () => {
  fileInput.value?.click()
}

const handleFileSelect = (event) => {
  const target = event.target
  if (target?.files && target.files.length > 0) {
    uploadFiles(Array.from(target.files))
  }
  if (target) {
    target.value = ''
  }
}

const handleDrop = (event) => {
  isDragging.value = false
  if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
    uploadFiles(Array.from(event.dataTransfer.files))
  }
}

const uploadFiles = async (files) => {
  if (!props.pluginName || !props.configKey) {
    toast.warning('Missing plugin config info')
    return
  }
  if (uploading.value) {
    return
  }

  const oversized = files.filter((file) => file.size > MAX_FILE_BYTES)
  if (oversized.length > 0) {
    oversized.forEach((file) => {
      toast.warning(
        tm('fileUpload.fileTooLarge', { name: file.name, max: MAX_FILE_MB })
      )
    })
  }
  const validFiles = files.filter((file) => file.size <= MAX_FILE_BYTES)
  if (validFiles.length === 0) {
    return
  }

  uploading.value = true
  try {
    const formData = new FormData()
    validFiles.forEach((file, index) => {
      formData.append(`file${index}`, file)
    })

    const response = await axios.post(
      `/api/config/plugin/file/upload?plugin_name=${encodeURIComponent(
        props.pluginName
      )}&key=${encodeURIComponent(props.configKey)}`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )

    if (response.data.status === 'ok') {
      const uploaded = response.data.data?.uploaded || []
      const errors = response.data.data?.errors || []

      if (uploaded.length > 0) {
        const merged = [...fileList.value]
        for (const path of uploaded) {
          if (!merged.includes(path)) {
            merged.push(path)
          }
        }
        fileList.value = merged
        toast.success(tm('fileUpload.uploadSuccess', { count: uploaded.length }))
      }

      if (errors.length > 0) {
        toast.warning(errors.join('\\n'))
      }
    } else {
      toast.error(response.data.message || tm('fileUpload.uploadFailed'))
    }
  } catch (error) {
    console.error('File upload failed:', error)
    toast.error(tm('fileUpload.uploadFailed'))
  } finally {
    uploading.value = false
  }
}

const deleteFile = (filePath) => {
  fileList.value = fileList.value.filter((item) => item !== filePath)
  toast.success(tm('fileUpload.deleteSuccess'))
}

const getDisplayName = (path) => {
  if (!path) return ''
  const parts = String(path).split('/')
  return parts[parts.length - 1] || path
}
</script>

<style scoped>
.file-config-item {
  width: 100%;
}

.file-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.file-dialog-card {
  height: 70vh;
}

.file-dialog-body {
  overflow-y: auto;
  max-height: calc(70vh - 120px);
}

.file-dialog-actions {
  padding: 16px 24px 20px;
}

.upload-tile {
  border: 2px dashed rgba(var(--v-theme-on-surface), 0.2);
  border-radius: 18px;
  width: 240px;
  height: 200px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  cursor: pointer;
  background: rgba(var(--v-theme-surface-variant), 0.35);
  transition: border-color 0.2s ease, background 0.2s ease;
}

.upload-tile:hover,
.upload-tile.dragover {
  border-color: rgba(var(--v-theme-primary), 0.6);
  background: rgba(var(--v-theme-primary), 0.06);
}

.upload-icon {
  width: 48px;
  height: 48px;
  border-radius: 16px;
  background: rgba(var(--v-theme-primary), 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
}

.upload-text {
  font-size: 14px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.upload-hint {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.empty-text {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.file-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.file-pill {
  position: relative;
  min-height: 84px;
  padding: 12px 32px 12px 12px;
  border-radius: 16px;
  background: rgba(var(--v-theme-surface), 0.95);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
}

.file-pill-name {
  font-weight: 600;
  text-align: center;
  word-break: break-word;
}

.file-pill-delete {
  position: absolute;
  top: 6px;
  right: 6px;
}

@media (max-width: 1400px) {
  .file-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .file-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
