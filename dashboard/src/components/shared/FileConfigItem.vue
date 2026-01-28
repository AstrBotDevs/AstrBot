<template>
  <div class="file-config-item">
    <div class="d-flex align-center gap-2">
      <v-btn size="small" color="primary" variant="tonal" @click="dialog = true">
        {{ tm('fileUpload.button') }}
      </v-btn>
      <span class="text-caption text-medium-emphasis ml-2">
        {{ fileCountText }}
      </span>
    </div>

    <v-dialog v-model="dialog" max-width="700">
      <v-card class="file-dialog-card" variant="flat">
        <v-card-title class="d-flex align-center">
          <span class="text-h3">{{ tm('fileUpload.dialogTitle') }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
        </v-card-title>

        <v-card-text class="file-dialog-body">
          <div v-if="mergedFileItems.length === 0" class="empty-text">
            {{ tm('fileUpload.empty') }}
          </div>

          <v-list density="compact" lines="one">
            <v-list-item v-for="item in mergedFileItems" :key="item.path">
              <template #prepend>
                <v-icon size="18">mdi-file</v-icon>
              </template>
              <v-list-item-title class="file-name">
                {{ getDisplayName(item.path) }}
              </v-list-item-title>
              <template #append>
                <div class="d-flex align-center gap-1">
                  <v-chip v-if="item.status !== 'ok'" size="x-small" :color="getStatusColor(item.status)"
                    variant="tonal">
                    {{ getStatusText(item.status) }}
                  </v-chip>
                  <v-btn v-if="item.status === 'unconfigured'" icon="mdi-plus" size="x-small" variant="text"
                    @click="addToConfig(item.path)" />
                  <v-btn icon="mdi-delete" size="x-small" variant="text"
                    @click="item.status === 'unconfigured' ? deletePhysicalFile(item.path) : deleteFile(item.path)" />
                </div>
              </template>
            </v-list-item>

            <v-divider v-if="mergedFileItems.length > 0" class="my-2" />

            <v-list-item class="upload-item" :class="{ dragover: isDragging }" @drop.prevent="handleDrop"
              @dragover.prevent="isDragging = true" @dragleave="isDragging = false" @click="openFilePicker">
              <template #prepend>
                <v-icon size="18" color="primary">mdi-plus</v-icon>
              </template>
              <v-list-item-title>{{ tm('fileUpload.dropzone') }}</v-list-item-title>
              <v-list-item-subtitle v-if="allowedTypesText" class="upload-hint">
                {{ tm('fileUpload.allowedTypes', { types: allowedTypesText }) }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>

          <input ref="fileInput" type="file" multiple hidden :accept="acceptAttr" @change="handleFileSelect" />
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
import { computed, ref, watch } from 'vue'
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
const loadingFiles = ref(false)
const MAX_FILE_BYTES = 500 * 1024 * 1024
const MAX_FILE_MB = 500
const directoryFiles = ref([])

const fileList = computed({
  get: () => (Array.isArray(props.modelValue) ? props.modelValue : []),
  set: (val) => emit('update:modelValue', val)
})

const mergedFileItems = computed(() => {
  const configured = new Set(fileList.value)
  const existing = new Set(directoryFiles.value)
  const items = []

  for (const path of fileList.value) {
    items.push({
      path,
      status: existing.has(path) ? 'ok' : 'missing'
    })
  }

  for (const path of directoryFiles.value) {
    if (!configured.has(path)) {
      items.push({
        path,
        status: 'unconfigured'
      })
    }
  }

  return items
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

const getStatusText = (status) => {
  if (status === 'missing') {
    return tm('fileUpload.statusMissing')
  }
  if (status === 'unconfigured') {
    return tm('fileUpload.statusUnconfigured')
  }
  return ''
}

const getStatusColor = (status) => {
  if (status === 'missing') {
    return 'error'
  }
  if (status === 'unconfigured') {
    return 'warning'
  }
  return 'primary'
}

const openFilePicker = () => {
  fileInput.value?.click()
}

const loadDirectoryFiles = async () => {
  if (!props.pluginName || !props.configKey || loadingFiles.value) {
    return
  }

  loadingFiles.value = true
  try {
    const response = await axios.get(
      `/api/config/file/get?scope=plugin&name=${encodeURIComponent(
        props.pluginName
      )}&key=${encodeURIComponent(props.configKey)}`
    )
    if (response.data.status === 'ok') {
      const files = response.data.data?.files || []
      directoryFiles.value = Array.from(new Set(files))
    } else {
      toast.warning(response.data.message || tm('fileUpload.loadFailed'))
    }
  } catch (error) {
    console.error('Load file list failed:', error)
    toast.warning(tm('fileUpload.loadFailed'))
  } finally {
    loadingFiles.value = false
  }
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
      `/api/config/file/upload?scope=plugin&name=${encodeURIComponent(
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
        const updatedDirectory = new Set(directoryFiles.value)
        uploaded.forEach((path) => updatedDirectory.add(path))
        directoryFiles.value = Array.from(updatedDirectory)
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

const addToConfig = (filePath) => {
  if (!fileList.value.includes(filePath)) {
    fileList.value = [...fileList.value, filePath]
    toast.success(tm('fileUpload.addToConfig'))
  }
}

const deleteFile = (filePath) => {
  fileList.value = fileList.value.filter((item) => item !== filePath)
  directoryFiles.value = directoryFiles.value.filter((item) => item !== filePath)

  if (props.pluginName) {
    axios
      .post(
        `/api/config/file/delete?scope=plugin&name=${encodeURIComponent(
          props.pluginName
        )}`,
        { path: filePath }
      )
      .catch((error) => {
        console.warn('Staged file delete failed:', error)
        toast.warning(tm('fileUpload.deleteFailed'))
      })
  }

  toast.success(tm('fileUpload.deleteSuccess'))
}

const deletePhysicalFile = (filePath) => {
  directoryFiles.value = directoryFiles.value.filter((item) => item !== filePath)

  if (props.pluginName) {
    axios
      .post(
        `/api/config/file/delete?scope=plugin&name=${encodeURIComponent(
          props.pluginName
        )}`,
        { path: filePath }
      )
      .catch((error) => {
        console.warn('File delete failed:', error)
        toast.warning(tm('fileUpload.deleteFailed'))
      })
  }

  toast.success(tm('fileUpload.deleteSuccess'))
}

const getDisplayName = (path) => {
  if (!path) return ''
  const parts = String(path).split('/')
  return parts[parts.length - 1] || path
}

watch(
  () => dialog.value,
  (value) => {
    if (value) {
      loadDirectoryFiles()
    }
  }
)
</script>

<style scoped>
.file-config-item {
  width: 100%;
}

.file-dialog-card {
  height: 70vh;
  box-shadow: none;
}

.file-dialog-body {
  overflow-y: auto;
  max-height: calc(70vh - 120px);
}

.file-dialog-actions {
  padding: 16px 24px 20px;
}

.upload-hint {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.empty-text {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.file-name {
  font-weight: 600;
  word-break: break-word;
}

.upload-item {
  cursor: pointer;
  transition: background 0.2s ease;
}

.upload-item:hover,
.upload-item.dragover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
</style>
