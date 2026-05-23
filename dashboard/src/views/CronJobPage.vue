<template>
  <div class="dashboard-page cron-page" :class="{ 'is-dark': isDark }">
    <v-container fluid class="dashboard-shell pa-4 pa-md-6">
      <div class="dashboard-header">
        <div class="dashboard-header-main">
          <div class="d-flex align-center flex-wrap" style="gap: 8px;">
            <h1 class="dashboard-title">{{ tm('page.title') }}</h1>
            <v-chip size="x-small" color="orange-darken-2" variant="tonal" label>
              {{ tm('page.beta') }}
            </v-chip>
          </template>
          <template #item.cron_expression="{ item }">
            <div v-if="item.run_once">{{ formatTime(item.run_at) }}</div>
            <div v-else>
              <div>{{ item.cron_expression || tm('table.notAvailable') }}</div>
              <div class="text-caption text-medium-emphasis">{{ item.timezone || tm('table.timezoneLocal') }}</div>
            </div>
          </template>
          <template #item.target_sessions="{ item }">
            <div v-if="item.target_sessions?.length">
              <div v-for="session in item.target_sessions" :key="session">{{ session }}</div>
            </div>
            <div v-else>{{ tm('table.notAvailable') }}</div>
          </template>
          <template #item.next_run_time="{ item }">{{ formatTime(item.next_run_time) }}</template>
          <template #item.last_run_at="{ item }">{{ formatTime(item.last_run_at) }}</template>
          <template #item.note="{ item }">{{ item.note || tm('table.notAvailable') }}</template>
          <template #item.actions="{ item }">
            <div class="d-flex align-center flex-nowrap" style="gap: 12px; min-width: 140px;">
              <v-switch v-model="item.enabled" inset density="compact" hide-details color="primary"
                class="mt-0" @change="toggleJob(item)" />
              <v-btn size="small" variant="text" color="primary" @click="openEdit(item)">
                {{ tm('actions.edit') }}
              </v-btn>
              <v-btn size="small" variant="text" color="error" @click="deleteJob(item)">
                {{ tm('actions.delete') }}
              </v-btn>
            </div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

        <div class="dashboard-header-actions">
          <v-btn variant="text" color="primary" :loading="loading" prepend-icon="mdi-refresh" @click="loadJobs">
            {{ tm('actions.refresh') }}
          </v-btn>
          <v-btn variant="tonal" color="primary" prepend-icon="mdi-plus" @click="openCreate">
            {{ tm('actions.create') }}
          </v-btn>
        </div>
      </div>

    <v-dialog v-model="createDialog" max-width="560">
      <v-card>
        <v-card-title class="text-h6">
          {{ editingJobId ? tm('form.editTitle') : tm('form.title') }}
        </v-card-title>
        <v-card-subtitle class="text-body-2 text-medium-emphasis">
          {{ tm('form.chatHint') }}
        </v-card-subtitle>
        <v-card-text>
          <v-switch v-model="newJob.run_once" :label="tm('form.runOnce')" inset color="primary" hide-details />
          <v-text-field v-model="newJob.name" :label="tm('form.name')" variant="outlined" density="comfortable" />
          <v-text-field v-model="newJob.note" :label="tm('form.note')" variant="outlined" density="comfortable" />
          <v-text-field v-if="!newJob.run_once" v-model="newJob.cron_expression" :label="tm('form.cron')"
            :placeholder="tm('form.cronPlaceholder')" variant="outlined" density="comfortable" />
          <v-text-field v-else v-model="newJob.run_at" :label="tm('form.runAt')" type="datetime-local"
            variant="outlined" density="comfortable" />
          <v-textarea v-model="newJob.target_sessions_text" :label="tm('form.targetSessions')"
            :placeholder="tm('form.targetSessionsPlaceholder')" variant="outlined" density="comfortable"
            rows="3" auto-grow />
          <v-text-field v-model="newJob.timezone" :label="tm('form.timezone')" variant="outlined"
            density="comfortable" />
          <v-switch v-model="newJob.enabled" :label="tm('form.enabled')" inset color="primary" hide-details />
        </v-card-text>
        <v-card-actions class="justify-end">
          <v-btn variant="text" @click="createDialog = false">{{ tm('actions.cancel') }}</v-btn>
          <v-btn variant="tonal" color="primary" :loading="creating" @click="submitJob">
            {{ editingJobId ? tm('actions.save') : tm('actions.submit') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref } from 'vue'
import { useTheme } from 'vuetify'
import { useModuleI18n } from '@/i18n/composables'

const { tm } = useModuleI18n('features/cron')
const theme = useTheme()

const isDark = computed(() => theme.global.current.value.dark)
const loading = ref(false)
const jobs = ref<any[]>([])
const proactivePlatforms = ref<{ id: string; name: string; display_name?: string }[]>([])
const createDialog = ref(false)
const creating = ref(false)
const editingJobId = ref<string | null>(null)
const newJob = ref({
  run_once: false,
  name: '',
  note: '',
  cron_expression: '',
  run_at: '',
  target_sessions_text: '',
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
  { title: tm('table.headers.targetSessions'), key: 'target_sessions', minWidth: '220px' },
  { title: tm('table.headers.nextRun'), key: 'next_run_time', minWidth: '160px' },
  { title: tm('table.headers.lastRun'), key: 'last_run_at', minWidth: '160px' },
  { title: tm('table.headers.note'), key: 'note', minWidth: '220px' },
  { title: tm('table.headers.actions'), key: 'actions', width: 160, sortable: false }
])

function toast(message: string, color: 'success' | 'error' | 'warning' = 'success') {
  snackbar.value = { show: true, message, color }
}

function parseTimeValue(value: any): number {
  if (!value) return 0
  const ts = new Date(value).getTime()
  return Number.isNaN(ts) ? 0 : ts
}

function formatTime(val: any): string {
  if (!val) return tm('table.notAvailable')
  try {
    // If the datetime string doesn't have timezone info, assume it's UTC
    // This handles cases where the backend returns naive datetime strings
    let dateStr = val
    if (typeof val === 'string' && val.includes('T')) {
      // Check for timezone suffix: Z, +HH:MM, -HH:MM, +HHMM, -HHMM
      const hasTimezone = /[Zz]$|[+-]\d{2}:?\d{2}$/.test(val)
      if (!hasTimezone) {
        // ISO datetime without timezone suffix - treat as UTC
        dateStr = val + 'Z'
      }
    }
    return new Date(dateStr).toLocaleString()
  } catch (e) {
    return String(val)
  }
}

function parseTargetSessions(text: string): string[] {
  return Array.from(
    new Set(
      String(text || '')
        .split(/\r?\n|,/)
        .map((item) => item.trim())
        .filter(Boolean)
    )
  )
}

function buildJobPayload() {
  const target_sessions = parseTargetSessions(newJob.value.target_sessions_text)
  return {
    run_once: newJob.value.run_once,
    name: newJob.value.name,
    note: newJob.value.note,
    cron_expression: newJob.value.cron_expression,
    run_at: newJob.value.run_at,
    target_sessions,
    timezone: newJob.value.timezone,
    enabled: newJob.value.enabled
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

function scheduleLabel(item: any): string {
  if (item.run_once) {
    return formatTime(item.run_at)
  }
  return item.cron_expression || tm('table.notAvailable')
}

function scheduleMeta(item: any): string {
  if (item.run_once) {
    return tm('table.type.once')
  }
  return item.timezone || tm('table.timezoneLocal')
}

async function loadJobs() {
  loading.value = true
  try {
    const res = await axios.get('/api/cron/jobs')
    if (res.data.status === 'ok') {
      const data = Array.isArray(res.data.data) ? res.data.data : []
      jobs.value = data.map((job: any) => ({
        ...job,
        target_sessions: job?.target_sessions || job?.payload?.target_sessions || (job?.payload?.session ? [job.payload.session] : [])
      }))
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
  } catch {
    // Ignore platform fetch failures and keep the fallback state.
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
      jobs.value = jobs.value.filter((item) => item.job_id !== job.job_id)
    } else {
      toast(res.data.message || tm('messages.deleteFailed'), 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm('messages.deleteFailed'), 'error')
  }
}

function openCreate() {
  editingJobId.value = null
  resetNewJob()
  createDialog.value = true
}

function openEdit(job: any) {
  editingJobId.value = job.job_id
  newJob.value = {
    run_once: !!job.run_once,
    name: job.name || '',
    note: job.note || job.description || '',
    cron_expression: job.cron_expression || '',
    run_at: job.run_at ? String(job.run_at).slice(0, 16) : '',
    target_sessions_text: (job.target_sessions || []).join('\n'),
    timezone: job.timezone || '',
    enabled: Boolean(job.enabled)
  }
  createDialog.value = true
}

function resetNewJob() {
  newJob.value = {
    run_once: false,
    name: '',
    note: '',
    cron_expression: '',
    run_at: '',
    target_sessions_text: '',
    timezone: '',
    enabled: true
  }
}

async function submitJob() {
  const payload = buildJobPayload()
  if (!payload.target_sessions.length) {
    toast(tm('messages.targetSessionsRequired'), 'warning')
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
    const url = editingJobId.value
      ? `/api/cron/jobs/${editingJobId.value}`
      : '/api/cron/jobs'
    const method = editingJobId.value ? 'patch' : 'post'
    const res = await axios({
      url,
      method,
      data: payload
    })
    if (res.data.status === 'ok') {
      toast(editingJobId.value ? tm('messages.updateSuccess') : tm('messages.createSuccess'))
      createDialog.value = false
      editingJobId.value = null
      resetNewJob()
      await loadJobs()
    } else {
      toast(
        res.data.message || (editingJobId.value ? tm('messages.updateFailed') : tm('messages.createFailed')),
        'error'
      )
    }
  } catch (e: any) {
    toast(
      e?.response?.data?.message || (editingJobId.value ? tm('messages.updateFailed') : tm('messages.createFailed')),
      'error'
    )
  } finally {
    creating.value = false
  }
}

async function updateJob() {
  if (!editingJobId.value) {
    return
  }
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
    const payload = {
      ...newJob.value,
      run_at: newJob.value.run_once ? toIsoDatetime(newJob.value.run_at) : '',
      description: newJob.value.note
    }
    const res = await axios.patch(`/api/cron/jobs/${editingJobId.value}`, payload)
    if (res.data.status === 'ok') {
      toast(tm('messages.updateSuccess'))
      createDialog.value = false
      editingJobId.value = ''
      resetNewJob()
      await loadJobs()
    } else {
      toast(res.data.message || tm('messages.updateFailed'), 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm('messages.updateFailed'), 'error')
  } finally {
    creating.value = false
  }
}

async function submitJob() {
  if (isEditing.value) {
    await updateJob()
    return
  }
  await createJob()
}

onMounted(() => {
  loadJobs()
  loadPlatforms()
})
</script>

<style scoped>
@import '@/styles/dashboard-shell.css';

.cron-page {
  padding-bottom: 40px;
}

.task-surface {
  min-width: 0;
}

.platform-section {
  margin-bottom: 24px;
}

.platform-chip-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.platform-empty {
  margin-bottom: 24px;
}

.task-table-wrap {
  border: 1px solid var(--dashboard-border);
  border-radius: 14px;
  overflow: auto;
  background: var(--dashboard-surface);
}

.task-table {
  width: 100%;
  min-width: 1120px;
  border-collapse: collapse;
}

.task-table .col-name {
  width: 220px;
}

.task-table .col-type {
  width: 120px;
}

.task-table .col-cron {
  width: 260px;
}

.task-table .col-session {
  width: 340px;
}

.task-table .col-next-run,
.task-table .col-last-run {
  width: 180px;
}

.task-table .col-actions {
  width: 220px;
}

.task-table th {
  padding: 14px 16px;
  text-align: left;
  background: rgba(var(--v-theme-primary), 0.04);
  color: var(--dashboard-muted);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--dashboard-border);
  white-space: nowrap;
}

.task-table td {
  padding: 16px;
  vertical-align: top;
  border-bottom: 1px solid var(--dashboard-border);
}

.task-table tbody tr:last-child td {
  border-bottom: 0;
}

.name-col {
  min-width: 220px;
}

.task-name,
.task-text {
  color: var(--dashboard-text);
  font-size: 14px;
  line-height: 1.5;
}

.task-name {
  font-weight: 600;
}

.task-subline {
  margin-top: 6px;
  color: var(--dashboard-muted);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.task-session {
  max-width: 340px;
  color: var(--dashboard-text);
  font-size: 14px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.actions-col {
  width: 220px;
}

.table-actions {
  display: grid;
  gap: 10px;
  justify-items: start;
  min-width: 190px;
}

.table-actions-toggle {
  display: flex;
  align-items: center;
}

.table-actions-switch {
  flex: 0 0 auto;
}

.cron-page :deep(.table-actions-switch .v-selection-control) {
  min-width: auto;
}

.table-actions-buttons {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
}

.state-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 220px;
  border: 1px dashed var(--dashboard-border-strong);
  border-radius: 14px;
  color: var(--dashboard-muted);
  font-size: 14px;
}

@media (max-width: 900px) {
  .table-actions {
    justify-items: start;
  }

  .table-actions-buttons,
  .table-actions-toggle {
    justify-content: flex-start;
  }
}
</style>
