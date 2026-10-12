<template>
  <div class="local-permission-matrix" :class="{ 'local-permission-matrix--without-network': isolationUnavailable }">
    <v-progress-linear v-if="runtimeLoading && !runtime" indeterminate color="primary" />
    <v-alert v-else-if="!runtime" type="warning" variant="tonal" density="compact">
      {{ tm('runtimeUnknown') }}
    </v-alert>

    <v-table class="permission-table">
      <thead>
        <tr>
          <th scope="col">{{ tm('role') }}</th>
          <th scope="col" class="text-center">{{ tm('execution') }}</th>
          <th v-if="!isolationUnavailable" scope="col" class="text-center">{{ tm('network') }}</th>
          <th scope="col" class="text-center">{{ tm('filesystem') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="role in roles" :key="role" :aria-label="tm(`roles.${role}`)">
          <th scope="row">{{ tm(`roles.${role}`) }}</th>
          <td>
            <v-tooltip
              location="top"
              :disabled="!isolationUnavailable || policy(role).filesystem_scope !== 'workspace'"
              :text="executionUnavailableHint"
            >
              <template #activator="{ props: tooltipProps }">
                <span
                  v-bind="tooltipProps"
                  class="execution-control"
                  :tabindex="isolationUnavailable && policy(role).filesystem_scope === 'workspace' ? 0 : undefined"
                >
                  <v-checkbox-btn
                    :model-value="policy(role).allow_execution && !permissionLocks[role].execution"
                    :disabled="permissionLocks[role].execution"
                    :aria-label="`${tm(`roles.${role}`)} · ${tm('execution')}`"
                    color="primary"
                    density="compact"
                    @update:model-value="updatePermission(role, { allow_execution: Boolean($event) })"
                  />
                </span>
              </template>
            </v-tooltip>
          </td>
          <td v-if="!isolationUnavailable">
            <v-checkbox-btn
              :model-value="policy(role).allow_network"
              :disabled="permissionLocks[role].network"
              :aria-label="`${tm(`roles.${role}`)} · ${tm('network')}`"
              color="primary"
              density="compact"
              @update:model-value="updatePermission(role, { allow_network: Boolean($event) })"
            />
          </td>
          <td>
            <v-select
              :model-value="policy(role).filesystem_scope"
              :items="[
                { title: tm('modes.none'), value: 'none' },
                { title: tm('scopes.workspace'), value: 'workspace', props: { disabled: unsupported } },
                { title: tm('scopes.host'), value: 'host' }
              ]"
              :disabled="!runtime"
              :aria-label="`${tm(`roles.${role}`)} · ${tm('filesystem')}`"
              variant="outlined"
              density="compact"
              hide-details
              :menu-props="{ rounded: 'lg', maxWidth: 420 }"
              @update:model-value="updatePermission(role, { filesystem_scope: $event })"
            >
              <template #item="{ props: itemProps, item }">
                <v-list-item v-bind="itemProps" :lines="false" role="option" :aria-selected="policy(role).filesystem_scope === item.value">
                  <template #subtitle>
                    <div class="scope-hint">
                      {{ tm(unsupported && item.value === 'workspace' ? 'scopeHints.workspaceUnsupported' : `scopeHints.${item.value}`) }}
                      <v-menu
                        v-if="item.value === 'host'"
                        open-on-hover
                        open-on-click
                        open-on-focus
                        :close-on-content-click="false"
                        location="top"
                        :max-width="360"
                      >
                        <template #activator="{ props: helpProps }">
                          <button v-bind="helpProps" type="button" class="scope-help" :aria-label="tm('filesystem')" @click.stop>
                            <CircleHelp :size="14" aria-hidden="true" />
                          </button>
                        </template>
                        <v-card class="pa-3 text-body-2">
                          <div>{{ tm('scopeDetails.account') }}</div>
                          <div class="mt-2">{{ tm('scopeDetails.docker') }}</div>
                        </v-card>
                      </v-menu>
                    </div>
                  </template>
                </v-list-item>
              </template>
            </v-select>
          </td>
        </tr>
      </tbody>
    </v-table>

    <button
      v-if="isolationUnavailable"
      type="button"
      class="isolation-hint"
      aria-haspopup="dialog"
      @click="isolationDialogOpen = true"
    >
      <ShieldAlert :size="16" aria-hidden="true" />
      <span>{{ tm(`runtime.setupHint.${runtime.sandbox.status}`, {
        backend: runtime.sandbox.backend === 'seatbelt' ? 'Seatbelt' : 'bubblewrap',
        dependency: runtime.sandbox.backend === 'seatbelt' ? 'sandbox-exec' : 'bwrap'
      }) }}</span>
    </button>

    <v-dialog v-model="isolationDialogOpen" max-width="640">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm('runtime.sandbox') }}</v-card-title>
        <v-card-text class="pa-6 pb-2">
          <p class="text-body-1">{{ tm('runtime.dialog.intro') }}</p>
          <details v-if="runtime?.sandbox?.status === 'unavailable' && runtime.sandbox.error" class="sandbox-diagnostics mt-4">
            <summary>{{ tm('runtime.dialog.startupError') }}</summary>
            <pre class="mt-2">{{ runtime.sandbox.error }}</pre>
          </details>
          <a
            :href="isolationDocumentationUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="d-inline-block text-primary text-decoration-underline text-body-2 mt-5"
          >{{ tm('runtime.dialog.documentation') }}</a>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="isolationDialogOpen = false">{{ tm('runtime.close') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-alert v-if="memberHasElevatedAccess" type="warning" variant="tonal" density="compact">
      {{ tm('memberWarning') }}
    </v-alert>
  </div>
</template>

<script>
export const windowsPermissionDefaults = {
  member: { filesystem_scope: 'none', allow_execution: false, allow_network: false },
  admin: { filesystem_scope: 'host', allow_execution: true, allow_network: true }
}
</script>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { CircleHelp, ShieldAlert } from '@lucide/vue'
import { useI18n, useModuleI18n } from '@/i18n/composables'
import { statsApi } from '@/api/v1'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue'])
const { locale } = useI18n()
const { tm } = useModuleI18n('features/config-metadata.ai_group.agent_computer_use.local_permissions')
const runtime = ref(null)
const runtimeLoading = ref(true)
const isolationDialogOpen = ref(false)
const isolationDocumentationUrl = computed(() =>
  `https://docs.astrbot.app/${locale.value === 'zh-CN' ? '' : 'en/'}use/astrbot-agent-sandbox.html#local-environment`
)
const unsupported = computed(() => runtime.value?.sandbox?.status === 'unsupported')
const sandboxUnavailable = computed(() => ['missing', 'unavailable'].includes(runtime.value?.sandbox?.status))
const isolationUnavailable = computed(() => unsupported.value || sandboxUnavailable.value)
const executionUnavailableHint = computed(() => isolationUnavailable.value ? tm(
  `runtime.executionUnavailable.${runtime.value.sandbox.status}`,
  {
    backend: runtime.value.sandbox.backend === 'seatbelt' ? 'Seatbelt' : 'bubblewrap',
    dependency: runtime.value.sandbox.backend === 'seatbelt' ? 'sandbox-exec' : 'bwrap'
  }
) : '')
const roles = ['member', 'admin']
const defaults = computed(() => runtime.value?.os === 'windows' ? windowsPermissionDefaults : {
  member: {
    allow_execution: false,
    allow_network: false,
    filesystem_scope: 'workspace'
  },
  admin: {
    allow_execution: true,
    allow_network: true,
    filesystem_scope: 'workspace'
  }
})

onMounted(async () => {
  try {
    const response = await statsApi.version()
    runtime.value = response.data?.data?.runtime ?? null
  } catch (error) {
    console.warn('Failed to load runtime information:', error)
  } finally {
    runtimeLoading.value = false
  }
})

function policy(role) {
  const resolved = {
    ...defaults.value[role],
    ...(props.modelValue?.[role] || {})
  }
  if (!['none', 'workspace', 'host'].includes(resolved.filesystem_scope)) {
    resolved.filesystem_scope = defaults.value[role].filesystem_scope
  }
  resolved.allow_execution = resolved.filesystem_scope !== 'none' && resolved.allow_execution === true &&
    !(isolationUnavailable.value && resolved.filesystem_scope === 'workspace')
  resolved.allow_network = resolved.allow_execution && resolved.allow_network === true
  return resolved
}

function updatePermission(role, changes) {
  const updatedRole = {
    ...policy(role),
    ...changes
  }
  if (updatedRole.filesystem_scope === 'none') {
    updatedRole.allow_execution = false
  }
  if (isolationUnavailable.value && updatedRole.allow_execution) {
    // Without isolation, execution requires host access and cannot block networking.
    updatedRole.allow_execution = updatedRole.filesystem_scope === 'host'
    updatedRole.allow_network = updatedRole.allow_execution
  }
  if (!updatedRole.allow_execution) {
    updatedRole.allow_network = false
  }
  emit('update:modelValue', {
    ...(props.modelValue || {}),
    [role]: updatedRole
  })
}

const permissionLocks = computed(() => Object.fromEntries(roles.map(role => {
  const current = policy(role)
  return [role, {
    execution: !runtime.value || current.filesystem_scope === 'none' ||
      (isolationUnavailable.value && current.filesystem_scope === 'workspace'),
    network: !runtime.value || !current.allow_execution
  }]
})))
const memberHasElevatedAccess = computed(() => {
  const member = policy('member')
  return member.allow_network || member.filesystem_scope === 'host'
})
</script>

<style scoped>
.scope-hint {
  padding-top: 4px;
  white-space: normal;
  overflow-wrap: anywhere;
  font-size: 0.75rem;
  line-height: 1.5;
}

.scope-help {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: inherit;
  vertical-align: middle;
  cursor: help;
}

.local-permission-matrix {
  display: grid;
  gap: 12px;
  width: 100%;
  min-width: 0;
  padding-top: 12px;
}

.isolation-hint {
  display: inline-flex;
  align-items: center;
  justify-self: start;
  gap: 6px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 0.75rem;
  line-height: 1.5;
  text-align: left;
}

.isolation-hint svg {
  flex-shrink: 0;
}

.isolation-hint span {
  text-decoration: underline;
  text-underline-offset: 2px;
}

.sandbox-diagnostics {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 0.75rem;
}

.sandbox-diagnostics summary {
  cursor: pointer;
}

.sandbox-diagnostics pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.permission-table {
  min-width: 0;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.16);
  border-radius: 8px;
}

.permission-table :deep(table) {
  table-layout: fixed;
}

.permission-table :deep(th),
.permission-table :deep(td) {
  padding: 12px;
  text-align: center;
}

.permission-table :deep(thead th) {
  background: rgba(var(--v-theme-on-surface), 0.035);
}

.permission-table :deep(th:first-child) {
  width: 100px;
  text-align: left;
}

.permission-table :deep(.v-selection-control) {
  justify-content: center;
}

.execution-control {
  display: inline-flex;
}

@media (max-width: 600px) {
  .permission-table :deep(table) {
    min-width: 580px;
  }

  .permission-table :deep(th),
  .permission-table :deep(td) {
    padding: 8px 4px;
  }

  .permission-table :deep(th:first-child) {
    width: 60px;
  }

  .local-permission-matrix--without-network .permission-table :deep(table) {
    min-width: 420px;
  }
}
</style>
