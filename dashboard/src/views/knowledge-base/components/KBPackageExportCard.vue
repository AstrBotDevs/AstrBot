<template>
  <v-card elevation="2" class="mt-6">
    <v-card-title>{{ t('packageExport.title') }}</v-card-title>
    <v-divider />

    <v-card-text class="pa-6">
      <div v-if="status === 'idle'">
        <p class="text-body-1 mb-4">{{ t('packageExport.description') }}</p>
        <v-alert type="info" variant="tonal" class="mb-4">
          {{ t('packageExport.includes') }}
        </v-alert>
        <v-btn color="primary" variant="elevated" @click="startExport">
          <v-icon start>mdi-export</v-icon>
          {{ t('packageExport.button') }}
        </v-btn>
      </div>

      <div v-else-if="status === 'processing'" class="text-center py-8">
        <v-progress-circular indeterminate color="primary" size="64" class="mb-4" />
        <div class="text-subtitle-1">{{ t('packageExport.processing') }}</div>
        <div class="text-body-2 text-medium-emphasis mt-2">{{ progress.message }}</div>
        <v-progress-linear
          class="mt-4"
          :model-value="progress.current"
          :max="progress.total"
          color="primary"
        />
      </div>

      <div v-else-if="status === 'completed'" class="text-center py-8">
        <v-icon size="64" color="success" class="mb-4">mdi-check-circle</v-icon>
        <div class="text-h6 mb-2">{{ t('packageExport.completed') }}</div>
        <div class="text-body-2 text-medium-emphasis mb-4">{{ result?.filename }}</div>
        <v-btn color="primary" variant="elevated" class="mr-2" @click="downloadPackage">
          <v-icon start>mdi-download</v-icon>
          {{ t('packageExport.download') }}
        </v-btn>
        <v-btn variant="text" @click="resetExport">
          {{ t('packageExport.reset') }}
        </v-btn>
      </div>

      <div v-else-if="status === 'failed'">
        <v-alert type="error" variant="tonal" class="mb-4">
          {{ errorMessage }}
        </v-alert>
        <v-btn color="primary" variant="elevated" @click="resetExport">
          {{ t('packageExport.retry') }}
        </v-btn>
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

const { tm: t } = useModuleI18n('features/knowledge-base/detail')

const props = defineProps<{
  kb: any
}>()

const status = ref<'idle' | 'processing' | 'completed' | 'failed'>('idle')
const taskId = ref('')
const progress = ref({ current: 0, total: 100, message: '' })
const result = ref<any>(null)
const errorMessage = ref('')

const startExport = async () => {
  status.value = 'processing'
  progress.value = { current: 0, total: 100, message: '' }
  errorMessage.value = ''

  try {
    const response = await axios.post('/api/kb/package/export', {
      kb_id: props.kb.kb_id
    })
    if (response.data.status !== 'ok') {
      throw new Error(response.data.message)
    }

    taskId.value = response.data.data.task_id
    pollProgress()
  } catch (error: any) {
    status.value = 'failed'
    errorMessage.value = error.response?.data?.message || error.message || t('packageExport.failed')
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
      result.value = data.result
      status.value = 'completed'
      return
    }

    if (data.status === 'failed') {
      throw new Error(data.error || t('packageExport.failed'))
    }

    setTimeout(pollProgress, 1000)
  } catch (error: any) {
    status.value = 'failed'
    errorMessage.value = error.response?.data?.message || error.message || t('packageExport.failed')
  }
}

const downloadPackage = () => {
  if (!result.value?.filename) return
  const token = localStorage.getItem('token')
  if (!token) return

  const link = document.createElement('a')
  link.href = `/api/kb/package/download?filename=${encodeURIComponent(result.value.filename)}&token=${encodeURIComponent(token)}`
  link.download = result.value.filename
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

const resetExport = () => {
  status.value = 'idle'
  taskId.value = ''
  progress.value = { current: 0, total: 100, message: '' }
  result.value = null
  errorMessage.value = ''
}
</script>
