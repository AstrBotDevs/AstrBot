<template>
  <div class="dashboard-page cron-page" :class="{ 'is-dark': isDark }">
    <v-container fluid class="dashboard-shell pa-4 pa-md-6">
      <div class="dashboard-header">
        <div class="dashboard-header-main">
          <div class="dashboard-eyebrow">{{ tm('header.eyebrow') }}</div>
          <div class="d-flex align-center flex-wrap" style="gap: 8px;">
            <h1 class="dashboard-title">{{ tm('page.title') }}</h1>
            <v-chip size="x-small" color="orange-darken-2" variant="tonal" label>
              {{ tm('page.beta') }}
            </v-chip>
          </div>
          <p class="dashboard-subtitle">
            {{ tm('page.subtitle') }}
          </p>
        </div>

        <div class="dashboard-header-actions">
          <v-btn variant="text" color="primary" :loading="loading" prepend-icon="mdi-refresh" @click="loadJobs">
            {{ tm('actions.refresh') }}
          </v-btn>
          <v-btn variant="tonal" color="primary" prepend-icon="mdi-plus" @click="openCreate">
            {{ tm('actions.create') }}
          </v-btn>
        </div>
      </div>

      <div class="dashboard-overview-grid">
        <section
          v-for="card in overviewCards"
          :key="card.label"
          class="dashboard-card dashboard-overview-card"
        >
          <div class="dashboard-card-icon">
            <v-icon size="18">{{ card.icon }}</v-icon>
          </div>
          <div class="dashboard-card-label">{{ card.label }}</div>
          <div class="dashboard-card-value">{{ card.value }}</div>
          <div class="dashboard-card-note">{{ card.note }}</div>
        </section>
      </div>

      <div class="dashboard-section-head">
        <div>
          <div class="dashboard-section-title">{{ tm('section.platforms.title') }}</div>
          <div class="dashboard-section-subtitle">
            {{
              proactivePlatforms.length
                ? tm('page.proactive.supported', { platforms: proactivePlatformText })
                : tm('page.proactive.unsupported')
            }}
          </div>
        </div>
      </div>

      <section v-if="proactivePlatforms.length" class="platform-section">
        <div class="platform-chip-wrap">
          <v-chip
            v-for="platform in proactivePlatforms"
            :key="platform.id"
            size="small"
            variant="tonal"
            color="primary"
          >
            {{ platform.display_name || platform.name }} · {{ platform.id }}
          </v-chip>
        </div>
      </section>
      <div v-else class="dashboard-empty platform-empty">
        {{ tm('page.proactive.unsupported') }}
      </div>

      <div class="dashboard-section-head">
        <div>
          <div class="dashboard-section-title">{{ tm('table.title') }}</div>
          <div class="dashboard-section-subtitle">{{ tm('table.subtitle') }}</div>
        </div>
      </div>

      <section class="task-surface">
        <div v-if="loading && !jobs.length" class="state-panel">
          <v-progress-circular indeterminate size="22" width="2" color="primary" />
          <span>{{ tm('actions.refresh') }}...</span>
        </div>

        <div v-else-if="!jobs.length" class="state-panel">
          <v-icon size="20" color="primary">mdi-calendar-blank-outline</v-icon>
          <span>{{ tm('table.empty') }}</span>
        </div>

        <div v-else class="task-table-wrap">
          <table class="task-table">
            <colgroup>
              <col class="col-name" />
              <col class="col-type" />
              <col class="col-cron" />
              <col class="col-session" />
              <col class="col-next-run" />
              <col class="col-last-run" />
              <col class="col-actions" />
            </colgroup>
            <thead>
              <tr>
                <th>{{ tm('table.headers.name') }}</th>
                <th>{{ tm('table.headers.type') }}</th>
                <th>{{ tm('table.headers.cron') }}</th>
                <th>{{ tm('table.headers.session') }}</th>
                <th>{{ tm('table.headers.nextRun') }}</th>
                <th>{{ tm('table.headers.lastRun') }}</th>
                <th class="actions-col">{{ tm('table.headers.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in sortedJobs" :key="item.job_id">
                <td class="name-col">
                  <div class="task-name">{{ item.name || tm('table.notAvailable') }}</div>
                  <div class="task-subline">{{ item.description || item.job_id }}</div>
                </td>
                <td>
                  <v-chip size="small" :color="item.run_once ? 'orange' : 'primary'" variant="tonal">
                    {{ jobTypeLabel(item) }}
                  </v-chip>
                </td>
                <td>
                  <div class="task-text">{{ scheduleLabel(item) }}</div>
                  <div class="task-subline">{{ scheduleMeta(item) }}</div>
                </td>
                <td>
                  <div class="task-session">{{ item.session || tm('table.notAvailable') }}</div>
                </td>
                <td>
                  <div class="task-text">{{ formatTime(item.next_run_time) }}</div>
                </td>
                <td>
                  <div class="task-text">{{ formatTime(item.last_run_at) }}</div>
                </td>
                <td class="actions-col">
                  <div class="table-actions">
                    <div class="table-actions-toggle">
                      <v-switch
                        v-model="item.enabled"
                        inset
                        density="compact"
                        hide-details
                        color="primary"
                        class="table-actions-switch mt-0"
                        @change="toggleJob(item)"
                      />
                    </div>
                    <div class="table-actions-buttons">
                      <v-btn
                        v-if="item.job_type === 'active_agent'"
                        size="small"
                        variant="text"
                        color="primary"
                        @click="openEdit(item)"
                      >
                        {{ tm('actions.edit') }}
                      </v-btn>
                      <v-btn size="small" variant="text" color="error" @click="deleteJob(item)">
                        {{ tm('actions.delete') }}
                      </v-btn>
                    </div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="2600">
        {{ snackbar.message }}
      </v-snackbar>

      <v-dialog v-model="createDialog" max-width="640">
        <v-card class="dashboard-dialog-card">
          <v-card-title class="text-h6 pt-5 px-5">{{ dialogTitle }}</v-card-title>
          <v-card-subtitle class="px-5 text-body-2 text-medium-emphasis">
            {{ tm('form.chatHint') }}
          </v-card-subtitle>
          <v-card-text class="px-5 pb-2">
            <div class="dashboard-form-grid dashboard-form-grid--single">
              <v-switch
                v-model="newJob.run_once"
                :label="tm('form.runOnce')"
                inset
                color="primary"
                hide-details
              />
              <v-text-field v-model="newJob.name" :label="tm('form.name')" variant="outlined" density="comfortable" />
              <v-text-field v-model="newJob.note" :label="tm('form.note')" variant="outlined" density="comfortable" />
              <v-text-field
                v-if="!newJob.run_once"
                v-model="newJob.cron_expression"
                :label="tm('form.cron')"
                :placeholder="tm('form.cronPlaceholder')"
                variant="outlined"
                density="comfortable"
              />
              <v-text-field
                v-else
                v-model="newJob.run_at"
                :label="tm('form.runAt')"
                type="datetime-local"
                variant="outlined"
                density="comfortable"
              />
              <v-text-field v-model="newJob.session" :label="tm('form.session')" variant="outlined" density="comfortable" />
              <v-text-field v-model="newJob.timezone" :label="tm('form.timezone')" variant="outlined" density="comfortable" />
              <v-switch
                v-model="newJob.enabled"
                :label="tm('form.enabled')"
                inset
                color="primary"
                hide-details
              />
            </div>
          </v-card-text>
          <v-card-actions class="justify-end px-5 pb-5">
            <v-btn variant="text" @click="createDialog = false">{{ tm('actions.cancel') }}</v-btn>
            <v-btn variant="tonal" color="primary" :loading="creating" @click="submitJob">
              {{ dialogSubmitText }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </v-container>
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
const editingJobId = ref('')
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

const enabledJobsCount = computed(() => jobs.value.filter((job) => job.enabled).length)
const runOnceCount = computed(() => jobs.value.filter((job) => job.run_once).length)
const recurringCount = computed(() => jobs.value.filter((job) => !job.run_once).length)

const sortedJobs = computed(() =>
  [...jobs.value].sort((a, b) => {
    if (a.enabled !== b.enabled) {
      return a.enabled ? -1 : 1
    }

    const nextA = parseTimeValue(a.next_run_time ?? a.run_at)
    const nextB = parseTimeValue(b.next_run_time ?? b.run_at)

    if (nextA !== nextB) {
      if (!nextA) return 1
      if (!nextB) return -1
      return nextA - nextB
    }

    return String(a.name || '').localeCompare(String(b.name || ''))
  })
)

const overviewCards = computed(() => [
  {
    label: tm('overview.totalTasks'),
    value: String(jobs.value.length),
    note: tm('overview.totalTasksNote'),
    icon: 'mdi-calendar-multiple'
  },
  {
    label: tm('overview.enabledTasks'),
    value: String(enabledJobsCount.value),
    note: tm('overview.enabledTasksNote'),
    icon: 'mdi-check-circle-outline'
  }
])

const isEditing = computed(() => !!editingJobId.value)
const dialogTitle = computed(() => tm(isEditing.value ? 'form.editTitle' : 'form.title'))
const dialogSubmitText = computed(() => tm(isEditing.value ? 'actions.save' : 'actions.submit'))

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
    return new Date(val).toLocaleString()
  } catch {
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
        session: job?.payload?.session || job?.session || ''
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
  editingJobId.value = ''
  resetNewJob()
  createDialog.value = true
}

function toDatetimeLocalValue(value: any): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const offset = date.getTimezoneOffset()
  const local = new Date(date.getTime() - offset * 60_000)
  return local.toISOString().slice(0, 16)
}

function toIsoDatetime(value: string): string {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toISOString()
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

function openEdit(job: any) {
  editingJobId.value = job.job_id
  newJob.value = {
    run_once: !!job.run_once,
    name: job.name || '',
    note: job.note || job.description || '',
    cron_expression: job.cron_expression || '',
    run_at: toDatetimeLocalValue(job.run_at),
    session: job.session || job?.payload?.session || '',
    timezone: job.timezone || '',
    enabled: job.enabled !== false
  }
  createDialog.value = true
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
    const payload = {
      ...newJob.value,
      run_at: newJob.value.run_once ? toIsoDatetime(newJob.value.run_at) : ''
    }
    const res = await axios.post('/api/cron/jobs', payload)
    if (res.data.status === 'ok') {
      toast(tm('messages.createSuccess'))
      createDialog.value = false
      editingJobId.value = ''
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

.cron-page :deep(.dashboard-overview-grid) {
  grid-template-columns: repeat(2, minmax(0, 1fr));
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
