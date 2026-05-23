<template>
  <v-dialog :model-value="modelValue" max-width="760" persistent @update:model-value="emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2">mdi-folder-import</v-icon>
        {{ t('packageImport.title') }}
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-6">
        <div v-if="status === 'idle'">
          <v-alert type="info" variant="tonal" class="mb-4">
            {{ t('packageImport.description') }}
          </v-alert>

          <v-file-input
            v-model="packageFile"
            :label="t('packageImport.fileLabel')"
            accept=".zip"
            prepend-icon="mdi-file-zip-box"
            show-size
          />
        </div>

        <div v-else-if="status === 'checking'" class="text-center py-8">
          <v-progress-circular indeterminate color="primary" size="64" class="mb-4" />
          <div class="text-subtitle-1">{{ t('packageImport.checking') }}</div>
        </div>

        <div v-else-if="status === 'confirm'">
          <v-alert :type="versionAlertType" variant="tonal" class="mb-4">
            {{ versionAlertMessage }}
          </v-alert>

          <v-alert
            v-if="importBlockingMessage"
            type="error"
            variant="tonal"
            class="mb-4"
          >
            {{ importBlockingMessage }}
          </v-alert>

          <v-card variant="outlined" class="mb-4">
            <v-card-title class="text-subtitle-1">
              <v-icon class="mr-2">mdi-package-variant-closed</v-icon>
              {{ t('packageImport.packageSummary') }}
            </v-card-title>
            <v-card-text>
              <div class="d-flex flex-wrap ga-2 mb-3">
                <v-chip size="small" color="primary" variant="tonal">
                  {{ checkResult?.knowledge_base?.kb_name || '-' }}
                </v-chip>
                <v-chip size="small" color="success" variant="tonal">
                  {{ t('packageImport.documents', { count: checkResult?.statistics?.documents ?? 0 }) }}
                </v-chip>
                <v-chip size="small" color="secondary" variant="tonal">
                  {{ t('packageImport.chunks', { count: checkResult?.statistics?.chunks ?? 0 }) }}
                </v-chip>
              </div>
              <div class="text-body-2">
                <div>{{ t('packageImport.exportedAt') }}: {{ formatDate(checkResult?.exported_at) }}</div>
                <div>{{ t('packageImport.version') }}: {{ checkResult?.backup_version || '-' }}</div>
                <div>
                  {{ t('packageImport.embeddingSource') }}:
                  {{ checkResult?.provider_summary?.embedding?.provider_id || '-' }}
                  <span v-if="checkResult?.provider_summary?.embedding?.dimensions">
                    ({{ t('packageImport.dimension', { count: checkResult?.provider_summary?.embedding?.dimensions }) }})
                  </span>
                </div>
                <div>
                  {{ t('packageImport.rerankSource') }}:
                  {{ checkResult?.provider_summary?.rerank?.provider_id || t('packageImport.notSet') }}
                </div>
              </div>
            </v-card-text>
          </v-card>

          <v-text-field
            v-model="kbName"
            :label="t('packageImport.nameLabel')"
            class="mb-4"
            variant="outlined"
          />

          <v-select
            v-model="embeddingProviderId"
            :items="embeddingProviders"
            :item-title="item => item.embedding_model || item.id"
            item-value="id"
            :label="t('packageImport.embeddingProvider')"
            variant="outlined"
            class="mb-4"
            :hint="embeddingHint"
            persistent-hint
          />

          <v-select
            v-model="rerankProviderId"
            :items="rerankProviders"
            :item-title="item => item.rerank_model || item.id"
            item-value="id"
            :label="t('packageImport.rerankProvider')"
            variant="outlined"
            clearable
          />

          <v-alert v-if="checkResult?.warnings?.length" type="warning" variant="tonal" class="mt-4">
            <div v-for="warning in checkResult.warnings" :key="warning">{{ warning }}</div>
          </v-alert>
        </div>

        <div v-else-if="status === 'processing'" class="text-center py-8">
          <v-progress-circular indeterminate color="primary" size="64" class="mb-4" />
          <div class="text-subtitle-1 mb-3">{{ t('packageImport.processing') }}</div>
          <div class="text-body-2 text-medium-emphasis">{{ progress.message }}</div>
          <v-progress-linear
            class="mt-4"
            :model-value="progress.current"
            :max="progress.total"
            color="primary"
          />
        </div>

        <div v-else-if="status === 'completed'" class="text-center py-8">
          <v-icon size="64" color="success" class="mb-4">mdi-check-circle</v-icon>
          <div class="text-h6 mb-2">{{ t('packageImport.completed') }}</div>
          <div class="text-body-2 text-medium-emphasis">
            {{ importResult?.knowledge_base?.kb_name }}
          </div>
        </div>

        <div v-else-if="status === 'failed'" class="py-4">
          <v-alert type="error" variant="tonal">
            {{ errorMessage }}
          </v-alert>
        </div>
      </v-card-text>

      <v-divider />

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" @click="handleClose">
          {{ status === 'completed' ? t('packageImport.close') : t('packageImport.cancel') }}
        </v-btn>
        <v-btn
          v-if="status === 'idle'"
          color="primary"
          variant="elevated"
          :disabled="!packageFile"
          :loading="uploading"
          @click="uploadAndCheck"
        >
          {{ t('packageImport.uploadAndCheck') }}
        </v-btn>
        <v-btn
          v-else-if="status === 'confirm'"
          color="primary"
          variant="elevated"
          :disabled="!canImport"
          @click="confirmImport"
        >
          {{ t('packageImport.confirmImport') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

const { tm: t } = useModuleI18n('features/knowledge-base/index')

const props = defineProps<{
  modelValue: boolean
  embeddingProviders: any[]
  rerankProviders: any[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'imported'): void
}>()

const status = ref<'idle' | 'checking' | 'confirm' | 'processing' | 'completed' | 'failed'>('idle')
const packageFile = ref<File | null>(null)
const uploadedFilename = ref('')
const uploading = ref(false)
const checkResult = ref<any>(null)
const kbName = ref('')
const embeddingProviderId = ref('')
const rerankProviderId = ref<string | null>(null)
const taskId = ref('')
const progress = ref({ current: 0, total: 100, message: '' })
const errorMessage = ref('')
const importResult = ref<any>(null)

const versionAlertType = computed(() => {
  if (checkResult.value?.version_status === 'major_diff') return 'error'
  if (checkResult.value?.version_status === 'minor_diff') return 'warning'
  return 'info'
})

const versionAlertMessage = computed(() => {
  if (checkResult.value?.version_status === 'major_diff') {
    return t('packageImport.versionMajorDiff', {
      backup: checkResult.value?.backup_version || '-',
      current: checkResult.value?.current_version || '-'
    })
  }
  if (checkResult.value?.version_status === 'minor_diff') {
    return t('packageImport.versionMinorDiff', {
      backup: checkResult.value?.backup_version || '-',
      current: checkResult.value?.current_version || '-'
    })
  }
  return t('packageImport.versionMatch', {
    backup: checkResult.value?.backup_version || '-'
  })
})

const importBlockingMessage = computed(() => {
  if (checkResult.value?.can_import) return ''
  if (checkResult.value?.version_status === 'major_diff') return ''
  return checkResult.value?.error || t('packageImport.importBlocked')
})

const embeddingHint = computed(() => {
  const required = checkResult.value?.local_provider_matches?.embedding?.required_dimensions
  if (!required) return ''
  return t('packageImport.embeddingHint', { count: required })
})

const canImport = computed(() => {
  return Boolean(
    kbName.value.trim() &&
    embeddingProviderId.value &&
    checkResult.value?.can_import
  )
})

watch(
  () => props.modelValue,
  (open) => {
    if (!open) {
      resetState()
    }
  }
)

const resetState = () => {
  status.value = 'idle'
  packageFile.value = null
  uploadedFilename.value = ''
  uploading.value = false
  checkResult.value = null
  kbName.value = ''
  embeddingProviderId.value = ''
  rerankProviderId.value = null
  taskId.value = ''
  progress.value = { current: 0, total: 100, message: '' }
  errorMessage.value = ''
  importResult.value = null
}

const handleClose = () => {
  emit('update:modelValue', false)
  resetState()
}

const uploadAndCheck = async () => {
  if (!packageFile.value) return

  uploading.value = true
  status.value = 'checking'
  errorMessage.value = ''

  try {
    const formData = new FormData()
    formData.append('file', packageFile.value)
    const uploadResponse = await axios.post('/api/kb/package/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (uploadResponse.data.status !== 'ok') {
      throw new Error(uploadResponse.data.message)
    }

    uploadedFilename.value = uploadResponse.data.data.filename
    const checkResponse = await axios.post('/api/kb/package/check', {
      filename: uploadedFilename.value
    })

    if (checkResponse.data.status !== 'ok') {
      throw new Error(checkResponse.data.message)
    }

    checkResult.value = checkResponse.data.data
    if (!checkResult.value.valid) {
      throw new Error(checkResult.value.error || t('packageImport.invalidPackage'))
    }

    kbName.value = checkResult.value.suggested_kb_name || ''
    embeddingProviderId.value = checkResult.value.local_provider_matches?.embedding?.preselected_provider_id || ''
    rerankProviderId.value = checkResult.value.local_provider_matches?.rerank?.preselected_provider_id || null
    status.value = 'confirm'
  } catch (error: any) {
    status.value = 'failed'
    errorMessage.value = error.response?.data?.message || error.message || t('packageImport.invalidPackage')
  } finally {
    uploading.value = false
  }
}

const confirmImport = async () => {
  status.value = 'processing'
  progress.value = { current: 0, total: 100, message: '' }
  errorMessage.value = ''

  try {
    const response = await axios.post('/api/kb/package/import', {
      filename: uploadedFilename.value,
      confirmed: true,
      kb_name: kbName.value.trim(),
      embedding_provider_id: embeddingProviderId.value,
      rerank_provider_id: rerankProviderId.value
    })

    if (response.data.status !== 'ok') {
      throw new Error(response.data.message)
    }

    taskId.value = response.data.data.task_id
    pollProgress()
  } catch (error: any) {
    status.value = 'failed'
    errorMessage.value = error.response?.data?.message || error.message || t('packageImport.importFailed')
  }
}

const pollProgress = async () => {
  if (!taskId.value) return

  try {
    const response = await axios.get('/api/kb/package/progress', {
      params: { task_id: taskId.value }
    })
    if (response.data.status !== 'ok') {
      throw new Error(response.data.message)
    }

    const data = response.data.data
    if (data.status === 'processing' && data.progress) {
      progress.value = {
        current: data.progress.current || 0,
        total: data.progress.total || 100,
        message: data.progress.message || ''
      }
      setTimeout(pollProgress, 1000)
      return
    }

    if (data.status === 'completed') {
      importResult.value = data.result
      status.value = 'completed'
      emit('imported')
      return
    }

    if (data.status === 'failed') {
      throw new Error(data.error || t('packageImport.importFailed'))
    }

    setTimeout(pollProgress, 1000)
  } catch (error: any) {
    status.value = 'failed'
    errorMessage.value = error.response?.data?.message || error.message || t('packageImport.importFailed')
  }
}

const formatDate = (value?: string) => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}
</script>
