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
              </div>
            </template>

            <template #item.capabilities="{ item }">
              <div class="capability-tags py-2">
                <v-chip
                  v-for="capability in item.capabilities || []"
                  :key="`${item.sandbox_id}-${capability}`"
                  size="x-small"
                  color="secondary"
                  variant="tonal"
                >
                  {{ capability }}
                </v-chip>
                <span v-if="!item.capabilities?.length" class="text-caption text-medium-emphasis">-</span>
              </div>
            </template>

            <template #item.status="{ item }">
              <div class="py-2">
                <v-chip size="small" :color="statusColor(item)" variant="tonal">
                  {{ statusLabel(item) }}
                  <v-tooltip v-if="item.controller_session_id" activator="parent" location="top">
                    {{ item.controller_session_id }}
                  </v-tooltip>
                </v-chip>
              </div>
            </template>

            <template #item.last_used="{ item }">
              <span class="text-body-2">{{ formatTime(item.last_used_at) }}</span>
            </template>

            <template #item.actions="{ item }">
              <div class="sandbox-actions-cell">
                <v-btn size="small" variant="tonal" @click="openDetails(item)">{{ tm('actions.inspect') }}</v-btn>
                <v-btn size="small" color="amber" variant="tonal" :disabled="!canUseAction(item, 'setDefault')" @click="setDefaultSandbox(item)">{{ tm('actions.setDefault') }}</v-btn>
                <v-btn size="small" variant="tonal" :disabled="!canUseAction(item, 'configure')" @click="openConfig(item)">{{ tm('actions.configure') }}</v-btn>
                <v-btn size="small" color="primary" variant="tonal" :disabled="!canUseAction(item, 'console')" @click="openConsole(item)">
                  {{ tm('actions.console') }}
                  <v-tooltip activator="parent" location="top">{{ tm('tooltips.console') }}</v-tooltip>
                </v-btn>
                <v-btn size="small" variant="tonal" :disabled="!canUseAction(item, 'release')" @click="releaseSandbox(item)">{{ tm('actions.release') }}</v-btn>
                <v-btn size="small" variant="tonal" :disabled="!canUseAction(item, 'screenshot')" @click="screenshotSandbox(item)">{{ tm('actions.screenshot') }}</v-btn>
                <v-btn size="small" color="error" variant="tonal" :disabled="!canUseAction(item, 'destroy')" @click="openDestroyConfirm(item)">{{ tm('actions.destroy') }}</v-btn>
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
      <div class="pa-4" v-if="selectedSandboxRecord">
        <div class="text-h6">{{ selectedSandboxRecord.sandbox_name || selectedSandboxRecord.sandbox_id }}</div>
        <div class="text-caption text-medium-emphasis mb-4">{{ selectedSandboxRecord.sandbox_id }}</div>
        <v-divider class="mb-4" />
        <v-list density="compact">
          <v-list-item :title="tm('fields.provider')" :subtitle="selectedSandboxRecord.provider" />
          <v-list-item
            v-if="selectedSandboxRecord.capabilities?.length"
            :title="tm('fields.capabilities')"
            :subtitle="selectedSandboxRecord.capabilities.join(', ')"
          />
          <v-list-item
            v-if="selectedSandboxRecord.tool_names?.length"
            :title="tm('fields.toolNames')"
            :subtitle="selectedSandboxRecord.tool_names.join(', ')"
          />
          <v-list-item :title="tm('fields.status')" :subtitle="statusLabel(selectedSandboxRecord)" />
          <v-list-item :title="tm('fields.owner')" :subtitle="selectedSandboxRecord.owner_session_id || '-'" />
          <v-list-item :title="tm('fields.controller')" :subtitle="selectedSandboxRecord.controller_session_id || '-'" />
          <v-list-item :title="tm('fields.retentionPolicy')" :subtitle="retentionLabel(selectedSandboxRecord.retention_policy)" />
          <v-list-item :title="tm('fields.occupiedUntil')" :subtitle="formatTime(selectedSandboxRecord.lease_expires_at)" />
          <v-list-item :title="tm('fields.idleCleanupAt')" :subtitle="formatTime(selectedSandboxRecord.idle_cleanup_at)" />
          <v-list-item :title="tm('fields.expiresAt')" :subtitle="formatTime(selectedSandboxRecord.expires_at)" />
        </v-list>
        <v-divider class="my-4" />
        <div class="text-subtitle-2 mb-2">{{ tm('fields.connectInfo') }}</div>
        <pre class="connect-info">{{ JSON.stringify(selectedSandboxRecord.connect_info || {}, null, 2) }}</pre>
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
          <v-select v-model="createProvider" :items="providerOptions" :label="tm('fields.provider')" variant="outlined" :disabled="!hasProviderOptions" />
          <v-text-field v-model="createName" :label="tm('create.name')" variant="outlined" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="createDialog = false">{{ tm('actions.cancel') }}</v-btn>
          <v-btn color="primary" :loading="creatingRequestPending" :disabled="!hasProviderOptions || creatingRequestPending" @click="createSandbox">
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
          <v-btn color="error" @click="confirmDestroySandbox">{{ tm('actions.destroy') }}</v-btn>
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
import { isDangerousConsoleCommand } from './sandbox/consoleUtils'
import type {
  ConsoleHistoryEntry,
  LoadSandboxesResult,
  ProviderOption,
  SandboxAction,
  SandboxProviderInfo,
  SandboxRecord,
} from './sandbox/types'

const { tm } = useModuleI18n('features/sandbox')

const loading = ref(false)
const creatingRequestPending = ref(false)
const savingConfig = ref(false)
const sandboxes = ref<SandboxRecord[]>([])
const detailsOpen = ref(false)
const selectedSandboxId = ref<string | null>(null)
const createDialog = ref(false)
const configDialog = ref(false)
const configSandbox = ref<SandboxRecord | null>(null)
const configRetentionPolicy = ref('temporary')
const configIdleTimeout = ref<number | null>(null)
const configExpiresAt = ref('')
const configSandboxName = ref('')
const createName = ref('')
const createProvider = ref('')
const createPollingTimers = ref<Record<string, ReturnType<typeof setTimeout>>>({})
const createGeneration = ref(0)
const pendingCreateSandboxes = ref<Record<string, { placeholder: SandboxRecord; attempts: number; refreshFailures: number }>>({})
const destroyPollingTimers = ref<Record<string, ReturnType<typeof setTimeout>>>({})
const destroyGeneration = ref(0)
const pendingDestroySandboxes = ref<Record<string, { attempts: number; refreshFailures: number }>>({})
const screenshotDialog = ref(false)
const screenshotDataUrl = ref('')
const destroyDialog = ref(false)
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

const providerOptions = ref<ProviderOption[]>([])
const hasProviderOptions = computed(() => providerOptions.value.length > 0)
let sandboxesRefreshTimer: ReturnType<typeof window.setInterval> | null = null

const headers = computed(() => [
  { title: tm('headers.sandbox'), key: 'identity', sortable: false, width: '22%' },
  { title: tm('headers.provider'), key: 'provider', sortable: false, width: '12%' },
  { title: tm('headers.capabilities'), key: 'capabilities', sortable: false, width: '18%' },
  { title: tm('headers.status'), key: 'status', sortable: false, width: '12%' },
  { title: tm('headers.lastUsed'), key: 'last_used', sortable: false, width: '14%' },
  { title: tm('headers.actions'), key: 'actions', sortable: false, align: 'end' as const, width: 520 }
])

const providerCount = computed(() => new Set(sandboxes.value.map((item) => item.provider || 'unknown')).size)
const busyCount = computed(() => sandboxes.value.filter((item) => !!item.controller_session_id).length)
const defaultCount = computed(() => sandboxes.value.filter((item) => item.is_default).length)
const canSaveConfig = computed(() => configSandboxName.value.trim().length > 0)
const selectedSandboxRecord = computed(() => {
  if (!selectedSandboxId.value) return null
  return sandboxes.value.find((item) => item.sandbox_id === selectedSandboxId.value) || null
})

const CREATE_POLL_INTERVAL_MS = 2000
const CREATE_POLL_MAX_ATTEMPTS = 60
const CREATE_POLL_MAX_REFRESH_FAILURES = 3
const DESTROY_POLL_INTERVAL_MS = 2000
const DESTROY_POLL_MAX_ATTEMPTS = 60
const DESTROY_POLL_MAX_REFRESH_FAILURES = 3
function toast(message: string, color: 'success' | 'error' | 'warning' = 'success') {
  snackbar.value = { show: true, message, color }
}

function localizedSandboxError(message?: string) {
  const text = String(message || '').trim()
  const limitMatch = text.match(/Sandbox limit reached\. Maximum managed sandboxes: (\d+)\./)
  if (limitMatch) {
    return tm('messages.maxSandboxesReached', { max: limitMatch[1] })
  }
  return text || tm('messages.operationFailed')
}

function requiredSandboxNameRule(value: string) {
  return !!value?.trim() || tm('config.nameRequired')
}

function hasCapability(item: SandboxRecord, capability: string) {
  return item.capabilities?.includes(capability) ?? false
}

function hasController(item?: { controller_session_id?: string | null } | null) {
  return !!item?.controller_session_id
}

function displayStatusKey(item?: SandboxRecord | string | null) {
  if (typeof item === 'string') return item
  const status = item?.status || 'unknown'
  if (status === 'running') {
    return hasController(item) ? 'busy' : 'available'
  }
  return status
}

function statusLabel(item?: SandboxRecord | string | null) {
  const key = displayStatusKey(item)
  const labels: Record<string, string> = {
    creating: tm('labels.creating'),
    restoring: tm('labels.restoring'),
    running: tm('labels.running'),
    busy: tm('labels.busy'),
    available: tm('labels.available'),
    error: tm('labels.error'),
    stopping: tm('labels.stopping'),
    stopped: tm('labels.stopped'),
    unknown: tm('labels.unknown'),
  }
  return labels[key] || tm('labels.unknownStatus', { status: key })
}

function statusColor(item?: SandboxRecord | string | null) {
  const key = displayStatusKey(item)
  const colors: Record<string, string> = {
    creating: 'amber',
    restoring: 'info',
    running: 'success',
    busy: 'warning',
    available: 'success',
    error: 'error',
    stopping: 'warning',
    stopped: 'grey',
    unknown: 'grey',
  }
  return colors[key] || 'grey'
}

function isCreatePendingStatus(status?: string | null) {
  return status === 'creating' || status === 'restoring'
}

function canUseAction(item: SandboxRecord, action: SandboxAction) {
  const status = item.status || 'unknown'

  switch (action) {
    case 'setDefault':
      return !item.is_default && status !== 'stopping'
    case 'configure':
      return status !== 'creating' && status !== 'restoring' && status !== 'stopping'
    case 'console':
      return status === 'running' && hasCapability(item, 'shell')
    case 'release':
      return status !== 'stopping' && !!item.controller_session_id
    case 'screenshot':
      return status === 'running' && hasCapability(item, 'screenshot')
    case 'destroy':
      return status !== 'stopping'
  }
}

function upsertSandboxRecord(record: SandboxRecord) {
  const index = sandboxes.value.findIndex((item) => item.sandbox_id === record.sandbox_id)
  if (index === -1) {
    sandboxes.value = [...sandboxes.value, record]
    return
  }

  const next = [...sandboxes.value]
  next[index] = record
  sandboxes.value = next
}

function removeSandboxRecord(sandboxId: string) {
  sandboxes.value = sandboxes.value.filter((item) => item.sandbox_id !== sandboxId)
}

function setPendingCreateSandbox(
  sandboxId: string,
  pending: { placeholder: SandboxRecord; attempts: number; refreshFailures: number }
) {
  pendingCreateSandboxes.value = {
    ...pendingCreateSandboxes.value,
    [sandboxId]: pending
  }
}

function removePendingCreateSandbox(sandboxId: string) {
  const next = { ...pendingCreateSandboxes.value }
  delete next[sandboxId]
  pendingCreateSandboxes.value = next
}

function setPendingDestroySandbox(
  sandboxId: string,
  pending: { attempts: number; refreshFailures: number }
) {
  pendingDestroySandboxes.value = {
    ...pendingDestroySandboxes.value,
    [sandboxId]: pending
  }
}

function removePendingDestroySandbox(sandboxId: string) {
  const next = { ...pendingDestroySandboxes.value }
  delete next[sandboxId]
  pendingDestroySandboxes.value = next
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
  selectedSandboxId.value = item.sandbox_id
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

async function loadSandboxes(options: { silent?: boolean } = {}): Promise<LoadSandboxesResult> {
  const { silent = false } = options
  if (!silent) loading.value = true
  try {
    // Add cache-bust parameter to prevent the browser from serving a stale list.
    const res = await axios.get('/api/sandbox', { params: { _t: Date.now() } })
    if (res.data.status === 'ok') {
      const records = res.data.data?.sandboxes || []
      sandboxes.value = records
      return { ok: true, records }
    } else {
      const error = res.data.message || tm('messages.loadFailed')
      if (!silent) toast(error, 'error')
      return { ok: false, records: sandboxes.value, error }
    }
  } catch (e: any) {
    const error = e?.response?.data?.message || tm('messages.loadFailed')
    if (!silent) toast(error, 'error')
    return { ok: false, records: sandboxes.value, error }
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadProviders() {
  try {
    const res = await axios.get('/api/sandbox/providers', { params: { _t: Date.now() } })
    if (res.data.status !== 'ok') {
      providerOptions.value = []
      createProvider.value = ''
      return
    }

    const providers = (res.data.data?.providers || []) as SandboxProviderInfo[]
    const defaultProviderId = String(res.data.data?.default_provider_id || '').trim()
    providerOptions.value = providers.map((provider) => ({
      title: provider.provider_id,
      value: provider.provider_id,
    }))

    if (!providerOptions.value.some((option) => option.value === createProvider.value)) {
      const defaultOption = providerOptions.value.find((option) => option.value === defaultProviderId)
      createProvider.value = defaultOption?.value || providerOptions.value[0]?.value || ''
    }
  } catch {
    providerOptions.value = []
    createProvider.value = ''
  }
}

function startSandboxesAutoRefresh() {
  if (sandboxesRefreshTimer !== null) return
  sandboxesRefreshTimer = window.setInterval(() => {
    void loadSandboxes({ silent: true })
  }, 5000)
}

function stopSandboxesAutoRefresh() {
  if (sandboxesRefreshTimer !== null) {
    window.clearInterval(sandboxesRefreshTimer)
    sandboxesRefreshTimer = null
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
  config: AxiosRequestConfig = {},
  throwOnError = false
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
    if (throwOnError) throw new Error(res.data.message || tm('messages.operationFailed'))
    toast(res.data.message || tm('messages.operationFailed'), 'error')
  } catch (e: any) {
    if (throwOnError) throw e
    toast(e?.response?.data?.message || tm('messages.operationFailed'), 'error')
  }
  return null
}

function clearCreatePollingTimer(sandboxId: string) {
  const timer = createPollingTimers.value[sandboxId]
  if (timer) {
    clearTimeout(timer)
    const next = { ...createPollingTimers.value }
    delete next[sandboxId]
    createPollingTimers.value = next
  }
}

function stopCreatePolling() {
  for (const timer of Object.values(createPollingTimers.value)) {
    clearTimeout(timer)
  }
  createPollingTimers.value = {}
  createGeneration.value++
  pendingCreateSandboxes.value = {}
}

function clearDestroyPollingTimer(sandboxId: string) {
  const timer = destroyPollingTimers.value[sandboxId]
  if (timer) {
    clearTimeout(timer)
    const next = { ...destroyPollingTimers.value }
    delete next[sandboxId]
    destroyPollingTimers.value = next
  }
}

function stopDestroyPollingForSandbox(sandboxId: string) {
  clearDestroyPollingTimer(sandboxId)
  removePendingDestroySandbox(sandboxId)
}

function stopDestroyPolling() {
  for (const timer of Object.values(destroyPollingTimers.value)) {
    clearTimeout(timer)
  }
  destroyPollingTimers.value = {}
  destroyGeneration.value++
  pendingDestroySandboxes.value = {}
}

function finishDestroyPolling(sandboxId: string) {
  clearDestroyPollingTimer(sandboxId)
  removePendingDestroySandbox(sandboxId)
  removeSandboxRecord(sandboxId)
}

function finishCreatePolling(sandboxId: string, record?: SandboxRecord) {
  clearCreatePollingTimer(sandboxId)
  removePendingCreateSandbox(sandboxId)
  if (!record) return

  if (record.status === 'running') {
    return
  }

  if (record.status === 'error') {
    toast(tm('messages.createFailed'), 'error')
    return
  }

  if (record.status === 'unknown') {
    toast(tm('messages.createUnknown'), 'warning')
    return
  }

  toast(tm('messages.createUnexpectedStatus', { status: statusLabel(record.status) }), 'warning')
}

function startCreatePolling(sandboxId: string, placeholder: SandboxRecord) {
  setPendingCreateSandbox(sandboxId, {
    placeholder,
    attempts: 0,
    refreshFailures: 0
  })
  upsertSandboxRecord(placeholder)
  const currentGen = createGeneration.value

  const poll = async (trackedSandboxId: string) => {
    if (currentGen !== createGeneration.value) return

    const pending = pendingCreateSandboxes.value[trackedSandboxId]
    if (!pending) return

    setPendingCreateSandbox(trackedSandboxId, {
      ...pending,
      attempts: pending.attempts + 1
    })
    const result = await loadSandboxes({ silent: true })

    if (currentGen !== createGeneration.value) return

    const latestPending = pendingCreateSandboxes.value[trackedSandboxId]
    if (!latestPending) return

    if (!result.ok) {
      const refreshFailures = latestPending.refreshFailures + 1
      setPendingCreateSandbox(trackedSandboxId, {
        ...latestPending,
        refreshFailures
      })
      if (refreshFailures >= CREATE_POLL_MAX_REFRESH_FAILURES || latestPending.attempts >= CREATE_POLL_MAX_ATTEMPTS) {
        finishCreatePolling(trackedSandboxId)
        toast(tm('messages.createRefreshUnstable'), 'warning')
        return
      }
      createPollingTimers.value = {
        ...createPollingTimers.value,
        [trackedSandboxId]: setTimeout(() => void poll(trackedSandboxId), CREATE_POLL_INTERVAL_MS)
      }
      return
    }

    setPendingCreateSandbox(trackedSandboxId, {
      ...latestPending,
      refreshFailures: 0
    })
    const record = result.records.find((item) => item.sandbox_id === trackedSandboxId)

    if (!record) {
      upsertSandboxRecord(latestPending.placeholder)
      if (latestPending.attempts >= CREATE_POLL_MAX_ATTEMPTS) {
        finishCreatePolling(trackedSandboxId)
        toast(tm('messages.createNotVisible', { sandboxId: trackedSandboxId }), 'warning')
        return
      }
      createPollingTimers.value = {
        ...createPollingTimers.value,
        [trackedSandboxId]: setTimeout(() => void poll(trackedSandboxId), CREATE_POLL_INTERVAL_MS)
      }
      return
    }

    if (isCreatePendingStatus(record.status)) {
      upsertSandboxRecord(record)
      if (latestPending.attempts >= CREATE_POLL_MAX_ATTEMPTS) {
        finishCreatePolling(trackedSandboxId)
        toast(tm('messages.createTimedOut', { sandboxId: trackedSandboxId }), 'warning')
        return
      }
      createPollingTimers.value = {
        ...createPollingTimers.value,
        [trackedSandboxId]: setTimeout(() => void poll(trackedSandboxId), CREATE_POLL_INTERVAL_MS)
      }
      return
    }

    finishCreatePolling(trackedSandboxId, record)
  }

  createPollingTimers.value = {
    ...createPollingTimers.value,
    [sandboxId]: setTimeout(() => void poll(sandboxId), CREATE_POLL_INTERVAL_MS)
  }
}

function startDestroyPolling(sandboxId: string) {
  setPendingDestroySandbox(sandboxId, {
    attempts: 0,
    refreshFailures: 0
  })
  const currentGen = destroyGeneration.value

  const poll = async (trackedSandboxId: string) => {
    if (currentGen !== destroyGeneration.value) return

    const pending = pendingDestroySandboxes.value[trackedSandboxId]
    if (!pending) return

    setPendingDestroySandbox(trackedSandboxId, {
      ...pending,
      attempts: pending.attempts + 1
    })
    const result = await loadSandboxes({ silent: true })

    if (currentGen !== destroyGeneration.value) return

    const latestPending = pendingDestroySandboxes.value[trackedSandboxId]
    if (!latestPending) return

    if (!result.ok) {
      const refreshFailures = latestPending.refreshFailures + 1
      setPendingDestroySandbox(trackedSandboxId, {
        ...latestPending,
        refreshFailures
      })
      if (refreshFailures >= DESTROY_POLL_MAX_REFRESH_FAILURES || latestPending.attempts >= DESTROY_POLL_MAX_ATTEMPTS) {
        clearDestroyPollingTimer(trackedSandboxId)
        removePendingDestroySandbox(trackedSandboxId)
        toast(tm('messages.destroyRefreshUnstable'), 'warning')
        return
      }
      destroyPollingTimers.value = {
        ...destroyPollingTimers.value,
        [trackedSandboxId]: setTimeout(() => void poll(trackedSandboxId), DESTROY_POLL_INTERVAL_MS)
      }
      return
    }

    const record = result.records.find((item) => item.sandbox_id === trackedSandboxId)
    if (!record) {
      finishDestroyPolling(trackedSandboxId)
      return
    }

    upsertSandboxRecord(record)
    if (latestPending.attempts >= DESTROY_POLL_MAX_ATTEMPTS) {
      clearDestroyPollingTimer(trackedSandboxId)
      removePendingDestroySandbox(trackedSandboxId)
      toast(tm('messages.destroyTimedOut', { sandboxId: trackedSandboxId }), 'warning')
      return
    }

    destroyPollingTimers.value = {
      ...destroyPollingTimers.value,
      [trackedSandboxId]: setTimeout(() => void poll(trackedSandboxId), DESTROY_POLL_INTERVAL_MS)
    }
  }

  destroyPollingTimers.value = {
    ...destroyPollingTimers.value,
    [sandboxId]: setTimeout(() => void poll(sandboxId), DESTROY_POLL_INTERVAL_MS)
  }
}

async function createSandbox() {
  const providerId = createProvider.value
  if (!providerId) {
    toast(tm('messages.operationFailed'), 'error')
    return
  }
  const sandboxName = createName.value || undefined

  creatingRequestPending.value = true

  try {
    const res = await axios.post('/api/sandbox', {
      provider_id: providerId,
      sandbox_name: sandboxName
    }, { params: { session_id: 'dashboard' } })

    if (res.data.status !== 'ok') {
      toast(localizedSandboxError(res.data.message), 'error')
      return
    }

    const created = res.data.data?.sandbox as SandboxRecord | undefined
    if (!created?.sandbox_id) {
      toast(tm('messages.operationFailed'), 'error')
      return
    }

    createDialog.value = false
    createName.value = ''
    startCreatePolling(created.sandbox_id, created)
  } catch (e: any) {
    toast(localizedSandboxError(e?.response?.data?.message), 'error')
  } finally {
    creatingRequestPending.value = false
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
    'post',
    sandboxApiPath(item, '/force-release'),
    undefined,
    tm('messages.released')
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
  const target = destroySandboxTarget.value
  if (!target) return
  const targetId = target.sandbox_id
  destroyDialog.value = false
  destroySandboxTarget.value = null
  try {
    const res = await axios.delete(sandboxApiPath(targetId, '/force'), {
      params: { _t: Date.now() }
    })
    if (res.data.status === 'ok') {
      startDestroyPolling(targetId)
      const sandbox = res.data.data?.sandbox as SandboxRecord | undefined
      if (sandbox?.sandbox_id) {
        upsertSandboxRecord(sandbox)
      }
      void loadSandboxes({ silent: true })
    } else {
      stopDestroyPollingForSandbox(targetId)
      toast(res.data.message || tm('messages.operationFailed'), 'error')
      await loadSandboxes({ silent: true })
    }
  } catch (e: any) {
    stopDestroyPollingForSandbox(targetId)
    toast(e?.response?.data?.message || tm('messages.operationFailed'), 'error')
    await loadSandboxes({ silent: true })
  }
}

async function screenshotSandbox(item: SandboxRecord) {
  const data = await sandboxAction('post', sandboxApiPath(item, '/admin-screenshot'))
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
  if (isDangerousConsoleCommand(command) && !window.confirm(tm('console.dangerConfirm', { command }))) return
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
    const data = await sandboxAction('post', sandboxApiPath(sandboxId, '/admin-shell'), {
      command: shellCommand,
      timeout: 300
    }, undefined, {}, true)
    if (!data?.result) {
      throw new Error(tm('messages.operationFailed'))
    }
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
    entry.stderr = normalizeTerminalOutput(e?.message || String(e))
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
  const prefix = cwd && cwd !== '~' ? `cd ${quoteForShell(cwd)}; ` : ''
  return `${prefix}{ ${command}; __astrbot_status=$?; }; printf '\n__ASTRBOT_CWD__%s\n' "$PWD"; exit $__astrbot_status`
}

function parseConsoleShellResult(stdout: string, fallbackCwd: string) {
  const marker = '\n__ASTRBOT_CWD__'
  const markerIndex = stdout.lastIndexOf(marker)
  if (markerIndex === -1) return { stdout: stripConsoleCwdMarkers(stdout), nextCwd: fallbackCwd }
  const visibleStdout = stdout.slice(0, markerIndex).replace(/\n$/, '')
  const nextCwd = stdout.slice(markerIndex + marker.length).trim() || fallbackCwd
  return { stdout: stripConsoleCwdMarkers(visibleStdout), nextCwd }
}

function stripConsoleCwdMarkers(stdout: string) {
  return stdout
    .split('\n')
    .filter((line) => !line.includes('__ASTRBOT_CWD__'))
    .join('\n')
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
  if (cwd === '/workspace') return '~'
  if (cwd.startsWith('/workspace/')) return `~${cwd.slice('/workspace'.length)}`
  const homeMatch = cwd.match(/^\/home\/[^/]+(.*)$/)
  if (homeMatch) {
    const suffix = homeMatch[1] || ''
    return suffix ? `~${suffix}` : '~'
  }
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

onMounted(async () => {
  await loadProviders()
  await loadSandboxes()
  startSandboxesAutoRefresh()
})

onUnmounted(() => {
  stopSandboxesAutoRefresh()
  stopCreatePolling()
  stopDestroyPolling()
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

.capability-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-width: 280px;
  min-width: 180px;
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
