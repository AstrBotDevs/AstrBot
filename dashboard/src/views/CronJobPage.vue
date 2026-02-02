<template>
  <div class="cron-page">
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <div class="d-flex align-center" style="gap: 8px;">
          <h2 class="text-h5 font-weight-bold">{{ tm('page.title') }}</h2>
          <v-chip size="x-small" color="orange-darken-2" variant="tonal" label>{{ tm('page.beta') }}</v-chip>
        </div>
        <div class="text-body-2 text-medium-emphasis">
          {{ tm('page.subtitle') }}
          <span v-if="proactivePlatforms.length">
            {{ tm('page.proactive.supported', { platforms: proactivePlatformText }) }}
          </span>
          <span v-else>{{ tm('page.proactive.unsupported') }}</span>
        </div>
      </div>
      <div class="d-flex align-center" style="gap: 8px;">
        <v-btn variant="tonal" color="primary" @click="openCreate">{{ tm('actions.create') }}</v-btn>
        <v-btn variant="tonal" color="primary" :loading="loading" @click="loadJobs">{{ tm('actions.refresh') }}</v-btn>
      </div>
    </div>

    <v-card class="rounded-lg" variant="flat">
      <v-card-text>
        <div class="d-flex align-center justify-space-between mb-3">
          <div class="text-subtitle-1 font-weight-bold">{{ tm('table.title') }}</div>
        </div>

        <v-alert v-if="!jobs.length && !loading" type="info" variant="tonal">{{ tm('table.empty') }}</v-alert>

        <v-data-table :items="jobs" :headers="headers" :loading="loading" item-key="job_id" density="comfortable"
          class="elevation-0">
          <template #item.name="{ item }">
            <div class="py-4">
              <div class="font-weight-medium">{{ item.name }}</div>
              <div class="text-caption text-medium-emphasis">{{ item.description }}</div>
            </div>
          </template>
          <template #item.type="{ item }">
            <v-chip size="small" :color="item.run_once ? 'orange' : 'primary'" variant="tonal">
              {{ jobTypeLabel(item) }}
            </v-chip>
          </template>
          <template #item.cron_expression="{ item }">
            <div v-if="item.run_once">{{ formatTime(item.run_at) }}</div>
            <div v-else>
              <div>{{ item.cron_expression || tm('table.notAvailable') }}</div>
              <div class="text-caption text-medium-emphasis">{{ item.timezone || tm('table.timezoneLocal') }}</div>
            </div>
          </template>
          <template #item.next_run_time="{ item }">{{ formatTime(item.next_run_time) }}</template>
          <template #item.last_run_at="{ item }">{{ formatTime(item.last_run_at) }}</template>
          <template #item.note="{ item }">{{ item.note || tm('table.notAvailable') }}</template>
          <template #item.actions="{ item }">
            <div class="d-flex" style="gap: 8px;">
              <v-switch v-model="item.enabled" inset density="compact" hide-details color="primary"
                @change="toggleJob(item)" />
              <v-btn size="small" variant="text" color="primary" @click="deleteJob(item)">{{ tm('actions.delete')
                }}</v-btn>
            </div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="2600">
      {{ snackbar.message }}
    </v-snackbar>

    <v-dialog v-model="createDialog" max-width="560">
      <v-card>
        <v-card-title class="text-h6">{{ tm('form.title') }}</v-card-title>
        <v-card-text>
          <v-switch v-model="newJob.run_once" :label="tm('form.runOnce')" inset color="primary" hide-details />
          <v-text-field v-model="newJob.name" :label="tm('form.name')" variant="outlined" density="comfortable" />
          <v-text-field v-model="newJob.note" :label="tm('form.note')" variant="outlined" density="comfortable" />
          <v-text-field v-if="!newJob.run_once" v-model="newJob.cron_expression" :label="tm('form.cron')"
            :placeholder="tm('form.cronPlaceholder')" variant="outlined" density="comfortable" />
          <v-text-field v-else v-model="newJob.run_at" :label="tm('form.runAt')" type="datetime-local"
            variant="outlined" density="comfortable" />
          <v-text-field v-model="newJob.session" :label="tm('form.session')" variant="outlined" density="comfortable" />
          <v-text-field v-model="newJob.timezone" :label="tm('form.timezone')" variant="outlined"
            density="comfortable" />
          <v-switch v-model="newJob.enabled" :label="tm('form.enabled')" inset color="primary" hide-details />
        </v-card-text>
        <v-card-actions class="justify-end">
          <v-btn variant="text" @click="createDialog = false">{{ tm('actions.cancel') }}</v-btn>
          <v-btn variant="tonal" color="primary" :loading="creating" @click="createJob">{{ tm('actions.submit')
            }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

const { tm } = useModuleI18n('features/cron')

const loading = ref(false)
const jobs = ref<any[]>([])
const proactivePlatforms = ref<{ id: string; name: string; display_name?: string }[]>([])
const createDialog = ref(false)
const creating = ref(false)
const newJob = ref({
  run_once: false,
  name: '',
  note: '',
  cron_expression: '',
  run_at: '',
  session: '',
  timezone: '',
  enabled: true
})

const snackbar = ref({ show: false, message: '', color: 'success' })

const proactivePlatformText = computed(() =>
  proactivePlatforms.value.map((p) => `${p.display_name || p.name}(${p.id})`).join(' / ')
)

const headers = computed(() => [
  { title: tm('table.headers.name'), key: 'name', minWidth: '200px' },
  { title: tm('table.headers.type'), key: 'type', width: 110 },
  { title: tm('table.headers.cron'), key: 'cron_expression', minWidth: '160px' },
  { title: tm('table.headers.nextRun'), key: 'next_run_time', minWidth: '160px' },
  { title: tm('table.headers.lastRun'), key: 'last_run_at', minWidth: '160px' },
  { title: tm('table.headers.note'), key: 'note', minWidth: '220px' },
  { title: tm('table.headers.actions'), key: 'actions', width: 160, sortable: false }
])

function toast(message: string, color: 'success' | 'error' | 'warning' = 'success') {
  snackbar.value = { show: true, message, color }
}

function formatTime(val: any): string {
  if (!val) return tm('table.notAvailable')
  try {
    return new Date(val).toLocaleString()
  } catch (e) {
    return String(val)
  }
}

function jobTypeLabel(item: any): string {
  if (item.run_once) return tm('table.type.once')
  const type = item.job_type || 'active_agent'
  const map: Record<string, string> = {
    active_agent: tm('table.type.activeAgent'),
    workflow: tm('table.type.workflow')
  }
  return map[type] || tm('table.type.unknown', { type })
}

async function loadJobs() {
  loading.value = true
  try {
    const res = await axios.get('/api/cron/jobs')
    if (res.data.status === 'ok') {
      jobs.value = Array.isArray(res.data.data) ? res.data.data : []
    } else {
      toast(res.data.message || tm('messages.loadFailed'), 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm('messages.loadFailed'), 'error')
  } finally {
    loading.value = false
  }
}

async function loadPlatforms() {
  try {
    const res = await axios.get('/api/platform/stats')
    if (res.data.status === 'ok' && Array.isArray(res.data.data?.platforms)) {
      proactivePlatforms.value = res.data.data.platforms
        .filter((p: any) => p?.meta?.support_proactive_message)
        .map((p: any) => ({
          id: p?.id || p?.meta?.id || 'unknown',
          name: p?.meta?.name || p?.type || '',
          display_name: p?.meta?.display_name || p?.display_name
        }))
    }
  } catch (e) {
    // ignore platform fetch errors in UI; subtitle will show fallback
  }
}

async function toggleJob(job: any) {
  try {
    const res = await axios.patch(`/api/cron/jobs/${job.job_id}`, { enabled: job.enabled })
    if (res.data.status !== 'ok') {
      toast(res.data.message || tm('messages.updateFailed'), 'error')
      await loadJobs()
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm('messages.updateFailed'), 'error')
    await loadJobs()
  }
}

async function deleteJob(job: any) {
  try {
    const res = await axios.delete(`/api/cron/jobs/${job.job_id}`)
    if (res.data.status === 'ok') {
      toast(tm('messages.deleteSuccess'))
      jobs.value = jobs.value.filter((j) => j.job_id !== job.job_id)
    } else {
      toast(res.data.message || tm('messages.deleteFailed'), 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm('messages.deleteFailed'), 'error')
  }
}

function openCreate() {
  resetNewJob()
  createDialog.value = true
}

function resetNewJob() {
  newJob.value = {
    run_once: false,
    name: '',
    note: '',
    cron_expression: '',
    run_at: '',
    session: '',
    timezone: '',
    enabled: true
  }
}

async function createJob() {
  if (!newJob.value.session) {
    toast(tm('messages.sessionRequired'), 'warning')
    return
  }
  if (!newJob.value.note) {
    toast(tm('messages.noteRequired'), 'warning')
    return
  }
  if (!newJob.value.run_once && !newJob.value.cron_expression) {
    toast(tm('messages.cronRequired'), 'warning')
    return
  }
  if (newJob.value.run_once && !newJob.value.run_at) {
    toast(tm('messages.runAtRequired'), 'warning')
    return
  }
  creating.value = true
  try {
    const payload: any = { ...newJob.value }
    const res = await axios.post('/api/cron/jobs', payload)
    if (res.data.status === 'ok') {
      toast(tm('messages.createSuccess'))
      createDialog.value = false
      resetNewJob()
      await loadJobs()
    } else {
      toast(res.data.message || tm('messages.createFailed'), 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm('messages.createFailed'), 'error')
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  loadJobs()
  loadPlatforms()
})
</script>

<style scoped>
.cron-page {
  padding: 20px;
  padding-top: 8px;
  padding-bottom: 40px;
}
</style>
