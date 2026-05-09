<template>
  <div class="sandbox-page">
    <v-container fluid class="pa-0">
      <section class="sandbox-toolbar px-4 py-4">
        <div>
          <div class="text-h4 font-weight-bold">{{ tm('title') }}</div>
          <div class="text-body-2 text-medium-emphasis mt-1">{{ tm('subtitle') }}</div>
        </div>
        <div class="toolbar-actions">
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="createDialog = true">
            {{ tm('actions.create') }}
          </v-btn>
          <v-btn variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="loadSandboxes">
            {{ tm('actions.refresh') }}
          </v-btn>
        </div>
      </section>

      <section class="sandbox-metrics px-4 pb-4">
        <div class="metric-block">
          <span>{{ tm('metrics.total') }}</span>
          <strong>{{ sandboxes.length }}</strong>
        </div>
        <div class="metric-block">
          <span>{{ tm('metrics.providers') }}</span>
          <strong>{{ providerCount }}</strong>
        </div>
        <div class="metric-block">
          <span>{{ tm('metrics.busy') }}</span>
          <strong>{{ busyCount }}</strong>
        </div>
        <div class="metric-block">
          <span>{{ tm('metrics.default') }}</span>
          <strong>{{ defaultCount }}</strong>
        </div>
      </section>

      <v-card flat class="mx-4 sandbox-table-shell">
        <v-card-text class="pa-0">
          <v-data-table
            :headers="headers"
            :items="sandboxes"
            :loading="loading"
            item-value="sandbox_id"
            class="elevation-0"
          >
            <template #item.identity="{ item }">
              <div class="py-2">
                <div class="d-flex align-center ga-2">
                  <span class="font-weight-medium">{{ item.sandbox_name || item.sandbox_id }}</span>
                  <v-chip v-if="item.is_default" size="x-small" color="amber" variant="tonal">{{ tm('labels.default') }}</v-chip>
                </div>
                <div class="text-caption text-medium-emphasis">{{ item.sandbox_id }}</div>
              </div>
            </template>

            <template #item.provider="{ item }">
              <div class="d-flex flex-column ga-1 py-2">
                <v-chip size="small" color="primary" variant="tonal" class="provider-chip">{{ item.provider || tm('labels.unknown') }}</v-chip>
                <span class="text-caption text-medium-emphasis">{{ item.booter_type || tm('labels.unknown') }}</span>
              </div>
            </template>

            <template #item.status="{ item }">
              <div class="py-2">
                <v-chip size="small" :color="statusColor(item.status)" variant="tonal">
                  {{ statusLabel(item.status) }}
                </v-chip>
                <div v-if="item.controller_session_id" class="text-caption text-medium-emphasis mt-1">
                  {{ item.controller_session_id }}
                </div>
              </div>
            </template>

            <template #item.last_used="{ item }">
              <span class="text-body-2">{{ formatTime(item.last_used_at) }}</span>
            </template>

            <template #item.actions="{ item }">
              <div class="sandbox-actions-cell">
                <v-btn size="small" variant="tonal" @click="openDetails(item)">{{ tm('actions.inspect') }}</v-btn>
                <v-btn size="small" color="amber" variant="tonal" :disabled="item.is_default || !isOperational(item)" @click="setDefaultSandbox(item)">{{ tm('actions.setDefault') }}</v-btn>
                <v-btn size="small" variant="tonal" :disabled="!isOperational(item)" @click="openConfig(item)">{{ tm('actions.configure') }}</v-btn>
                <v-btn size="small" color="primary" variant="tonal" :disabled="!isOperational(item) || !hasCapability(item, 'shell')" @click="openConsole(item)">
                  {{ tm('actions.console') }}
                  <v-tooltip activator="parent" location="top">{{ tm('tooltips.console') }}</v-tooltip>
                </v-btn>
                <v-btn size="small" variant="tonal" :disabled="!canReleaseFromDashboard(item)" @click="releaseSandbox(item)">{{ tm('actions.release') }}</v-btn>
                <v-btn size="small" variant="tonal" :disabled="!isOperational(item) || !hasCapability(item, 'screenshot')" @click="screenshotSandbox(item)">{{ tm('actions.screenshot') }}</v-btn>
                <v-btn size="small" color="error" variant="tonal" @click="openDestroyConfirm(item)">{{ tm('actions.destroy') }}</v-btn>
              </div>
            </template>

            <template #no-data>
              <div class="text-center py-10">
                <v-icon size="56" color="grey">mdi-cube-outline</v-icon>
                <div class="text-h6 mt-3">{{ tm('empty.title') }}</div>
                <div class="text-body-2 text-medium-emphasis">{{ tm('empty.subtitle') }}</div>
              </div>
            </template>
          </v-data-table>
        </v-card-text>
      </v-card>
    </v-container>

    <v-navigation-drawer v-model="detailsOpen" location="right" temporary width="420">
      <div class="pa-4" v-if="selectedSandbox">
        <div class="text-h6">{{ selectedSandbox.sandbox_name || selectedSandbox.sandbox_id }}</div>
        <div class="text-caption text-medium-emphasis mb-4">{{ selectedSandbox.sandbox_id }}</div>
        <v-divider class="mb-4" />
        <v-list density="compact">
          <v-list-item :title="tm('fields.provider')" :subtitle="selectedSandbox.provider" />
          <v-list-item :title="tm('fields.booterType')" :subtitle="selectedSandbox.booter_type" />
          <v-list-item :title="tm('fields.status')" :subtitle="selectedSandbox.status || '-'" />
          <v-list-item :title="tm('fields.owner')" :subtitle="selectedSandbox.owner_session_id || '-'" />
          <v-list-item :title="tm('fields.controller')" :subtitle="selectedSandbox.controller_session_id || '-'" />
          <v-list-item :title="tm('fields.retentionPolicy')" :subtitle="retentionLabel(selectedSandbox.retention_policy)" />
          <v-list-item :title="tm('fields.leaseExpires')" :subtitle="formatTime(selectedSandbox.lease_expires_at)" />
          <v-list-item :title="tm('fields.idleTimeout')" :subtitle="String(selectedSandbox.idle_timeout ?? '-')" />
          <v-list-item :title="tm('fields.expiresAt')" :subtitle="formatTime(selectedSandbox.expires_at)" />
        </v-list>
        <v-divider class="my-4" />
        <div class="text-subtitle-2 mb-2">{{ tm('fields.connectInfo') }}</div>
        <pre class="connect-info">{{ JSON.stringify(selectedSandbox.connect_info || {}, null, 2) }}</pre>
      </div>
    </v-navigation-drawer>

    <v-dialog v-model="consoleOpen" max-width="1040">
      <v-card v-if="consoleSandbox" class="console-dialog-card">
        <v-card-text class="pa-4">
        <div class="d-flex align-center justify-space-between mb-2">
          <div>
            <div class="text-h6">{{ tm('console.title') }}</div>
            <div class="text-caption text-medium-emphasis">{{ consoleSandbox.sandbox_name || consoleSandbox.sandbox_id }}</div>
          </div>
          <div class="d-flex align-center ga-2">
            <v-chip size="small" :color="hasController(consoleSandbox) ? 'warning' : 'success'" variant="tonal">
              {{ hasController(consoleSandbox) ? tm('labels.busy') : tm('labels.available') }}
            </v-chip>
            <v-btn icon="mdi-close" variant="text" size="small" @click="consoleOpen = false" />
          </div>
        </div>

        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          {{ tm('console.notice') }}
        </v-alert>

        <div class="terminal-shell">
          <div class="terminal-header">
            <span>{{ consoleSandbox.provider || 'sandbox' }}</span>
            <span>{{ consoleSandbox.controller_session_id || tm('labels.noController') }}</span>
          </div>
          <div ref="consoleBodyRef" class="terminal-body">
            <div v-if="!consoleHistory.length" class="terminal-muted">{{ tm('console.empty') }}</div>
            <div v-for="entry in consoleHistory" :key="entry.id" class="terminal-entry">
              <div class="terminal-command"><span class="terminal-prompt">{{ displayConsoleCwd(entry.cwd) }} $</span> {{ entry.command }}</div>
              <pre v-if="entry.stdout" class="terminal-stdout">{{ entry.stdout }}</pre>
              <pre v-if="entry.stderr" class="terminal-stderr">{{ entry.stderr }}</pre>
              <div class="terminal-running" v-if="entry.running">{{ tm('console.running') }}</div>
              <div v-else class="terminal-exit">exit_code: {{ entry.exitCode }}</div>
            </div>
          </div>
          <div class="terminal-input-row" @click="focusConsoleInput">
            <span class="terminal-prompt">{{ displayConsoleCwd(consoleCwd) }} $</span>
            <textarea
              ref="consoleInputRef"
              v-model="consoleCommand"
              :placeholder="tm('console.command')"
              rows="1"
              class="terminal-input"
              @keydown.enter="handleConsoleEnter"
            />
          </div>
        </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <v-dialog v-model="createDialog" max-width="520">
      <v-card>
        <v-card-title>{{ tm('create.title') }}</v-card-title>
        <v-card-text>
          <v-select v-model="createProvider" :items="providerOptions" :label="tm('fields.provider')" variant="outlined" />
          <v-text-field v-model="createName" :label="tm('create.name')" variant="outlined" />
          <v-alert v-if="createProvider !== 'cua'" type="info" variant="tonal" density="compact">
            {{ tm('create.providerHint') }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="createDialog = false">{{ tm('actions.cancel') }}</v-btn>
          <v-btn color="primary" :loading="creating" :disabled="createProvider !== 'cua'" @click="createSandbox">
            {{ tm('actions.create') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="configDialog" max-width="560">
      <v-card>
        <v-card-title>{{ tm('config.title') }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="configSandboxName"
            :label="tm('config.name')"
            variant="outlined"
            :rules="[requiredSandboxNameRule]"
            class="mb-2"
          />
          <v-radio-group v-model="configRetentionPolicy" :label="tm('fields.retentionPolicy')" inline>
            <v-radio :label="tm('labels.temporary')" value="temporary" />
            <v-radio :label="tm('labels.persistent')" value="persistent" />
          </v-radio-group>
          <v-text-field
            v-model.number="configIdleTimeout"
            :label="tm('config.idleTimeout')"
            :disabled="configRetentionPolicy === 'persistent'"
            type="number"
            min="0"
            variant="outlined"
            :hint="tm('config.idleTimeoutHint')"
            persistent-hint
          />
          <v-text-field
            v-model="configExpiresAt"
            :label="tm('config.expiresAt')"
            :disabled="configRetentionPolicy === 'persistent'"
            type="datetime-local"
            variant="outlined"
            class="mt-4"
            :hint="tm('config.expiresAtHint')"
            persistent-hint
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="configDialog = false">{{ tm('actions.cancel') }}</v-btn>
          <v-btn color="primary" :loading="savingConfig" :disabled="!canSaveConfig" @click="saveConfig">{{ tm('actions.save') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="screenshotDialog" max-width="900">
      <v-card>
        <v-card-title>{{ tm('screenshot.title') }}</v-card-title>
        <v-card-text>
          <div v-if="screenshotDataUrl" class="screenshot-preview-wrap">
            <v-img :src="screenshotDataUrl" :alt="tm('screenshot.title')" class="screenshot-preview" />
          </div>
          <v-alert v-else type="info" variant="tonal" density="compact">
            {{ tm('screenshot.noPreview') }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="screenshotDialog = false">{{ tm('actions.close') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="destroyDialog" max-width="520">
      <v-card>
        <v-card-title>{{ tm('destroyConfirm.title') }}</v-card-title>
        <v-card-text>
          <v-alert type="warning" variant="tonal">
            {{ tm('destroyConfirm.message', { name: destroySandboxTarget?.sandbox_name || destroySandboxTarget?.sandbox_id || '-' }) }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="destroyDialog = false">{{ tm('actions.cancel') }}</v-btn>
          <v-btn color="error" :loading="destroying" @click="confirmDestroySandbox">{{ tm('actions.destroy') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="3000" location="top">
      {{ snackbar.message }}
      <template #actions>
        <v-btn variant="text" @click="snackbar.show = false">{{ tm('actions.close') }}</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import axios, { type AxiosRequestConfig } from 'axios'
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useModuleI18n } from '@/i18n/composables'

type SandboxRecord = {
  sandbox_id: string
  sandbox_name?: string
  booter_type?: string
  provider?: string
  managed?: boolean
  created_by_astrbot?: boolean
  is_default?: boolean
  owner_session_id?: string | null
  controller_session_id?: string | null
  lease_expires_at?: number | null
  last_used_at?: number | null
  idle_timeout?: number | null
  expires_at?: number | null
  retention_policy?: string | null
  status?: string
  connect_info?: Record<string, unknown>
  capabilities?: string[]
}

type ConsoleHistoryEntry = {
  id: number
  cwd: string
  command: string
  stdout: string
  stderr: string
  exitCode: unknown
  running?: boolean
}

const { tm } = useModuleI18n('features/sandbox')

const loading = ref(false)
const creating = ref(false)
const savingConfig = ref(false)
const sandboxes = ref<SandboxRecord[]>([])
const detailsOpen = ref(false)
const selectedSandbox = ref<SandboxRecord | null>(null)
const createDialog = ref(false)
const configDialog = ref(false)
const configSandbox = ref<SandboxRecord | null>(null)
const configRetentionPolicy = ref('temporary')
const configIdleTimeout = ref<number | null>(null)
const configExpiresAt = ref('')
const configSandboxName = ref('')
const createName = ref('')
const createProvider = ref('cua')
const createPollingTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const createGeneration = ref(0)
const screenshotDialog = ref(false)
const screenshotDataUrl = ref('')
const destroyDialog = ref(false)
const destroying = ref(false)
const destroySandboxTarget = ref<SandboxRecord | null>(null)
const consoleOpen = ref(false)
const consoleSandbox = ref<SandboxRecord | null>(null)
const consoleCommand = ref('')
const consoleRunning = ref(false)
const consoleHistory = ref<ConsoleHistoryEntry[]>([])
const consoleHistoryBySandbox = ref<Record<string, ConsoleHistoryEntry[]>>({})
const consoleCwdBySandbox = ref<Record<string, string>>({})
const consoleCwd = ref('~')
const consoleInputRef = ref<HTMLTextAreaElement | null>(null)
const consoleBodyRef = ref<HTMLElement | null>(null)
let consoleEntryId = 0
const snackbar = ref({ show: false, message: '', color: 'success' })

const providerOptions = [
  { title: 'CUA', value: 'cua' },
  { title: 'Shipyard Neo', value: 'shipyard_neo' },
  { title: 'Shipyard', value: 'shipyard' }
]

const headers = computed(() => [
  { title: tm('headers.sandbox'), key: 'identity', sortable: false, width: '22%' },
  { title: tm('headers.provider'), key: 'provider', sortable: false, width: '14%' },
  { title: tm('headers.status'), key: 'status', sortable: false, width: '12%' },
  { title: tm('headers.lastUsed'), key: 'last_used', sortable: false, width: '18%' },
  { title: tm('headers.actions'), key: 'actions', sortable: false, align: 'end' as const, width: 520 }
])

const providerCount = computed(() => new Set(sandboxes.value.map((item) => item.provider || item.booter_type || 'unknown')).size)
const busyCount = computed(() => sandboxes.value.filter((item) => !!item.controller_session_id).length)
const defaultCount = computed(() => sandboxes.value.filter((item) => item.is_default).length)
const canSaveConfig = computed(() => configSandboxName.value.trim().length > 0)

function toast(message: string, color: 'success' | 'error' | 'warning' = 'success') {
  snackbar.value = { show: true, message, color }
}

function requiredSandboxNameRule(value: string) {
  return !!value?.trim() || tm('config.nameRequired')
}

function hasCapability(item: SandboxRecord, capability: string) {
  return item.capabilities?.includes(capability) ?? false
}

function hasController(item: SandboxRecord) {
  return !!item.controller_session_id
}

function canReleaseFromDashboard(item: SandboxRecord) {
  return !!item.controller_session_id
}

function statusLabel(status?: string | null) {
  const key = status || 'unknown'
  const labels: Record<string, string> = {
    creating: tm('labels.creating'),
    running: tm('labels.running'),
    error: tm('labels.error'),
    stopping: tm('labels.stopping'),
    stopped: tm('labels.stopped'),
    unknown: tm('labels.unknown'),
  }
  return labels[key] || key
}

function statusColor(status?: string | null) {
  const colors: Record<string, string> = {
    creating: 'amber',
    running: 'success',
    error: 'error',
    stopping: 'warning',
    stopped: 'grey',
    unknown: 'grey',
  }
  return colors[status || 'unknown'] || 'grey'
}

function isOperational(item: SandboxRecord) {
  return item.status === 'running'
}

function formatTime(value?: number | null) {
  if (!value) return '-'
  return new Date(value * 1000).toLocaleString()
}

function retentionLabel(value?: string | null) {
  return value === 'persistent' ? tm('labels.persistent') : tm('labels.temporary')
}

function toDateTimeLocal(value?: number | null) {
  if (!value) return ''
  const date = new Date(value * 1000)
  const offsetMs = date.getTimezoneOffset() * 60 * 1000
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16)
}

function fromDateTimeLocal(value: string) {
  if (!value) return null
  return Math.floor(new Date(value).getTime() / 1000)
}

function openDetails(item: SandboxRecord) {
  selectedSandbox.value = item
  detailsOpen.value = true
}

function openConfig(item: SandboxRecord) {
  configSandbox.value = item
  configSandboxName.value = item.sandbox_name || item.sandbox_id
  configRetentionPolicy.value = item.retention_policy === 'persistent' ? 'persistent' : 'temporary'
  configIdleTimeout.value = item.idle_timeout ?? null
  configExpiresAt.value = toDateTimeLocal(item.expires_at)
  configDialog.value = true
}

async function loadSandboxes() {
  loading.value = true
  try {
    // Add cache-bust parameter to prevent the browser from serving a stale list.
    const res = await axios.get('/api/sandbox', { params: { _t: Date.now() } })
    if (res.data.status === 'ok') {
      sandboxes.value = res.data.data?.sandboxes || []
    } else {
      toast(res.data.message || tm('messages.loadFailed'), 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm('messages.loadFailed'), 'error')
  } finally {
    loading.value = false
  }
}

function sandboxApiPath(item: SandboxRecord | string, suffix = '') {
  const sandboxId = typeof item === 'string' ? item : item.sandbox_id
  return `/api/sandbox/${encodeURIComponent(sandboxId)}${suffix}`
}

async function sandboxAction(
  method: 'post' | 'patch' | 'delete',
  path: string,
  payload?: Record<string, unknown>,
  successMessage?: string,
  config: AxiosRequestConfig = {}
) {
  try {
    let res
    if (method === 'post') {
      res = await axios.post(path, payload, config)
    } else if (method === 'patch') {
      res = await axios.patch(path, payload, config)
    } else {
      res = await axios.delete(path, { ...config, data: payload })
    }
    if (res.data.status === 'ok') {
      if (successMessage) toast(successMessage)
      await loadSandboxes()
      return res.data.data
    }
    toast(res.data.message || tm('messages.operationFailed'), 'error')
  } catch (e: any) {
    toast(e?.response?.data?.message || tm('messages.operationFailed'), 'error')
  }
  return null
}

async function createSandbox() {
  const providerId = createProvider.value
  const sandboxName = createName.value || undefined

  creating.value = true
  const currentGen = ++createGeneration.value

  try {
    const res = await axios.post('/api/sandbox', {
      provider_id: providerId,
      sandbox_name: sandboxName
    }, { params: { session_id: 'dashboard' } })

    if (res.data.status !== 'ok') {
      toast(res.data.message || tm('messages.operationFailed'), 'error')
      creating.value = false
      return
    }

    const created = res.data.data?.sandbox as SandboxRecord | undefined
    if (!created?.sandbox_id) {
      toast(tm('messages.operationFailed'), 'error')
      creating.value = false
      return
    }

    // Only close dialog and clear input after the server has accepted the request.
    createDialog.value = false
    createName.value = ''
    toast(tm('messages.created'))

    // Poll until the sandbox leaves the "creating" state.
    const sandboxId = created.sandbox_id
    let attempts = 0
    const maxAttempts = 60 // 2 minutes total for heavy providers

    const poll = async () => {
      // Drop stale polls from a previous create invocation.
      if (currentGen !== createGeneration.value) return

      attempts++
      await loadSandboxes()

      // Guard again after the await in case a newer create bumped the generation.
      if (currentGen !== createGeneration.value) return

      const record = sandboxes.value.find((s) => s.sandbox_id === sandboxId)

      // If the record is not yet visible, keep polling (list may lag).
      if (!record) {
        if (attempts >= maxAttempts) {
          creating.value = false
          toast(
            `Sandbox ${sandboxId} not yet visible. Refresh to check status.`,
            'warning'
          )
          return
        }
        createPollingTimer.value = setTimeout(poll, 2000)
        return
      }

      if (record.status !== 'creating') {
        creating.value = false
        return
      }

      if (attempts >= maxAttempts) {
        creating.value = false
        toast(
          `Sandbox ${sandboxId} is still being created. Refresh to check status.`,
          'warning'
        )
        return
      }

      createPollingTimer.value = setTimeout(poll, 2000)
    }

    await poll()
  } catch (e: any) {
    toast(e?.response?.data?.message || tm('messages.operationFailed'), 'error')
    creating.value = false
  }
}

function setDefaultSandbox(item: SandboxRecord) {
  return sandboxAction(
    'post',
    sandboxApiPath(item, '/default'),
    undefined,
    tm('messages.defaultSet')
  )
}

async function saveConfig() {
  if (!configSandbox.value || !canSaveConfig.value) return
  savingConfig.value = true
  try {
    const persistent = configRetentionPolicy.value === 'persistent'
    const data = await sandboxAction(
      'patch',
      sandboxApiPath(configSandbox.value),
      {
        sandbox_name: configSandboxName.value.trim(),
        retention_policy: configRetentionPolicy.value,
        idle_timeout: persistent ? null : configIdleTimeout.value,
        expires_at: persistent ? null : fromDateTimeLocal(configExpiresAt.value)
      },
      tm('messages.configSaved')
    )
    if (data) configDialog.value = false
  } finally {
    savingConfig.value = false
  }
}

function releaseSandbox(item: SandboxRecord) {
  return sandboxAction(
    'delete',
    '/api/sandbox/current',
    undefined,
    tm('messages.released'),
    {
      params: { session_id: 'dashboard', sandbox_id: item.sandbox_id }
    }
  )
}

function openConsole(item: SandboxRecord) {
  consoleSandbox.value = item
  consoleHistory.value = [...(consoleHistoryBySandbox.value[item.sandbox_id] || [])]
  consoleCwd.value = consoleCwdBySandbox.value[item.sandbox_id] || '~'
  consoleOpen.value = true
  requestAnimationFrame(() => {
    focusConsoleInput()
    scrollConsoleToBottom()
  })
}

function openDestroyConfirm(item: SandboxRecord) {
  destroySandboxTarget.value = item
  destroyDialog.value = true
}

async function confirmDestroySandbox() {
  if (!destroySandboxTarget.value) return
  destroying.value = true
  try {
    const data = await sandboxAction(
      'delete',
      sandboxApiPath(destroySandboxTarget.value),
      undefined,
      tm('messages.destroyed'),
      { params: { session_id: 'dashboard' } }
    )
    if (data) {
      destroyDialog.value = false
      destroySandboxTarget.value = null
    }
  } finally {
    destroying.value = false
  }
}

async function screenshotSandbox(item: SandboxRecord) {
  const data = await sandboxAction('post', sandboxApiPath(item, '/screenshot'))
  if (!data) return
  const screenshot = data?.screenshot
  const legacyResult = data?.result
  const mimeType = screenshot?.mime_type || legacyResult?.mime_type || 'image/png'
  const base64 = screenshot?.base64 || legacyResult?.base64 || ''
  screenshotDataUrl.value = screenshot?.data_url || (base64 ? `data:${mimeType};base64,${base64}` : '')
  screenshotDialog.value = true
}

async function runConsoleCommand() {
  if (consoleRunning.value || !consoleSandbox.value || !consoleCommand.value.trim()) return
  const command = consoleCommand.value.trim()
  const cwd = consoleCwd.value
  const sandboxId = consoleSandbox.value.sandbox_id
  const entry: ConsoleHistoryEntry = {
    id: ++consoleEntryId,
    cwd,
    command,
    stdout: '',
    stderr: '',
    exitCode: '-',
    running: true
  }
  consoleHistory.value.push(entry)
  consoleHistory.value = [...consoleHistory.value]
  consoleHistoryBySandbox.value[sandboxId] = consoleHistory.value
  consoleCommand.value = ''
  await scrollConsoleToBottom()
  consoleRunning.value = true
  try {
    const shellCommand = buildConsoleShellCommand(command, cwd)
    const data = await sandboxAction('post', sandboxApiPath(sandboxId, '/shell'), {
      command: shellCommand,
      timeout: 300
    })
    if (data?.result) {
      const { stdout, nextCwd } = parseConsoleShellResult(String(data.result.stdout ?? ''), cwd)
      entry.stdout = normalizeTerminalOutput(stdout)
      entry.stderr = normalizeTerminalOutput(String(data.result.stderr ?? ''))
      entry.exitCode = data.result.exit_code ?? data.result.returncode ?? '-'
      entry.running = false
      consoleHistory.value = [...consoleHistory.value]
      consoleHistoryBySandbox.value[sandboxId] = consoleHistory.value
      consoleCwd.value = nextCwd
      consoleCwdBySandbox.value[sandboxId] = nextCwd
      await nextTick()
      await scrollConsoleToBottom()
      focusConsoleInput()
    } else {
      entry.running = false
      consoleHistory.value = [...consoleHistory.value]
    }
  } catch (e: any) {
    entry.stderr = e?.message || String(e)
    entry.running = false
    consoleHistory.value = [...consoleHistory.value]
  } finally {
    entry.running = false
    consoleHistory.value = [...consoleHistory.value]
    consoleRunning.value = false
    await nextTick()
    focusConsoleInput()
  }
}

function quoteForShell(value: string) {
  return `'${value.replace(/'/g, `'"'"'`)}'`
}

function buildConsoleShellCommand(command: string, cwd: string) {
  const prefix = cwd && cwd !== '~' ? `cd ${quoteForShell(cwd)} && ` : ''
  return `${prefix}{ ${command}; __astrbot_status=$?; }; printf '\n__ASTRBOT_CWD__%s\n' "$PWD"; exit $__astrbot_status`
}

function parseConsoleShellResult(stdout: string, fallbackCwd: string) {
  const marker = '\n__ASTRBOT_CWD__'
  const markerIndex = stdout.lastIndexOf(marker)
  if (markerIndex === -1) return { stdout, nextCwd: fallbackCwd }
  const visibleStdout = stdout.slice(0, markerIndex).replace(/\n$/, '')
  const nextCwd = stdout.slice(markerIndex + marker.length).trim() || fallbackCwd
  return { stdout: visibleStdout, nextCwd }
}

function normalizeTerminalOutput(value: string) {
  const withoutAnsi = value
    .replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1B\\))/g, '')
    .replace(/\r(?!\n)/g, '\n')
  const lines = withoutAnsi.split('\n')
  const normalized: string[] = []
  for (const rawLine of lines) {
    const line = rawLine.trimEnd()
    const previous = normalized[normalized.length - 1] || ''
    if (!line && isTransientProgressLine(previous)) continue
    if (!line && !previous) continue
    if (shouldReplaceProgressLine(previous, line)) {
      normalized[normalized.length - 1] = line
      continue
    }
    normalized.push(line)
  }
  return normalized.join('\n').replace(/\n{3,}/g, '\n\n').trimEnd()
}

function progressLineKey(value: string) {
  return value
    .replace(/\b\d+%\b/g, '%')
    .replace(/\b\d+(?:\.\d+)?\s*(?:B|kB|MB|GB)\b/gi, '#')
    .replace(/\s+/g, ' ')
    .trim()
}

function shouldReplaceProgressLine(previous: string, current: string) {
  if (!previous || !current) return false
  if (isTransientProgressLine(previous) && isTransientProgressLine(current)) return true
  if (!/[%.]/.test(previous) || !/[%.]/.test(current)) return false
  return progressLineKey(previous) === progressLineKey(current)
}

function isTransientProgressLine(value: string) {
  const line = value.trim()
  return /^\d+%\s+\[/.test(line) || /^\S.+\.\.\.\s+\d+%$/.test(line)
}

function displayConsoleCwd(cwd: string) {
  if (cwd === '/home/cua') return '~'
  if (cwd.startsWith('/home/cua/')) return `~${cwd.slice('/home/cua'.length)}`
  return cwd
}

function handleConsoleEnter(event: KeyboardEvent) {
  if (event.shiftKey) return
  event.preventDefault()
  runConsoleCommand()
}

function focusConsoleInput() {
  consoleInputRef.value?.focus()
}

async function scrollConsoleToBottom() {
  await nextTick()
  const body = consoleBodyRef.value
  if (body) body.scrollTop = body.scrollHeight
}

onMounted(loadSandboxes)

onUnmounted(() => {
  if (createPollingTimer.value) {
    clearTimeout(createPollingTimer.value)
  }
  // Bump generation so any in-flight polls stop immediately.
  createGeneration.value++
})
</script>

<style scoped>
.sandbox-page {
  min-height: 100%;
}

.sandbox-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.sandbox-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  background: rgba(var(--v-theme-outline), 0.2);
}

.metric-block {
  min-height: 86px;
  padding: 18px;
  background: rgb(var(--v-theme-surface));
}

.metric-block span {
  display: block;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.78rem;
}

.metric-block strong {
  display: block;
  margin-top: 8px;
  font-size: 1.35rem;
  line-height: 1.2;
}

.sandbox-table-shell {
  border: 1px solid rgba(var(--v-theme-outline), 0.16);
  overflow-x: auto;
  max-width: calc(100% - 32px);
}

.sandbox-actions-cell {
  display: flex;
  flex-wrap: nowrap;
  justify-content: flex-end;
  gap: 4px;
  min-width: 500px;
  padding-block: 8px;
}

.provider-chip {
  align-self: flex-start;
  width: fit-content;
  min-width: 0;
}

.connect-info {
  overflow: auto;
  border-radius: 8px;
  padding: 12px;
  background: rgba(var(--v-theme-on-surface), 0.05);
  font-size: 12px;
}

.screenshot-preview-wrap {
  overflow: hidden;
  border: 1px solid rgba(var(--v-theme-outline), 0.18);
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.screenshot-preview {
  max-height: 70vh;
}

.console-dialog-card {
  overflow: hidden;
}

.terminal-shell {
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 12px;
  background: #0b1020;
  color: #e5e7eb;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
  background: #111827;
  color: #9ca3af;
  font-size: 12px;
}

.terminal-body {
  height: 56vh;
  overflow: auto;
  padding: 14px;
}

.terminal-muted {
  color: #64748b;
}

.terminal-entry + .terminal-entry {
  margin-top: 16px;
}

.terminal-command {
  color: #93c5fd;
}

.terminal-exit {
  color: #bfdbfe;
}

.terminal-prompt {
  color: #22c55e;
}

.terminal-stdout,
.terminal-stderr {
  margin: 8px 0 0;
  overflow-x: auto;
  white-space: pre-wrap;
  overflow-wrap: normal;
}

.terminal-stdout {
  color: #e5e7eb;
}

.terminal-stderr {
  color: #fca5a5;
}

.terminal-exit {
  margin-top: 8px;
  font-size: 12px;
}

.terminal-input-row {
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: center;
  gap: 10px;
  min-height: 56px;
  padding: 12px 14px;
  border-top: 1px solid rgba(148, 163, 184, 0.22);
  background: #111827;
  cursor: text;
}

.terminal-input {
  width: 100%;
  height: 24px;
  min-height: 24px;
  max-height: 24px;
  resize: none;
  border: 0;
  outline: none;
  overflow: hidden;
  background: transparent;
  color: #e5e7eb;
  font: inherit;
}

.terminal-input::placeholder {
  color: #64748b;
}

@media (max-width: 960px) {
  .sandbox-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .toolbar-actions {
    justify-content: flex-start;
  }

  .sandbox-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 600px) {
  .sandbox-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
