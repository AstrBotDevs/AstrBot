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
            <div class="execution-cell">
              <v-tooltip
                location="top"
                :disabled="!permissionLocks[role].execution || !isolationUnavailable || policy(role, false).filesystem_scope !== 'workspace'"
                :text="executionUnavailableHint"
              >
                <template #activator="{ props: tooltipProps }">
                  <span
                    v-bind="tooltipProps"
                    class="execution-control"
                    :tabindex="permissionLocks[role].execution && isolationUnavailable && policy(role, false).filesystem_scope === 'workspace' ? 0 : undefined"
                  >
                    <v-checkbox-btn
                      :model-value="policy(role, false).allow_execution"
                      :disabled="permissionLocks[role].execution"
                      :aria-label="`${tm(`roles.${role}`)} · ${tm('execution')}`"
                      :aria-describedby="executionBlockedRoles.includes(role) ? `local-execution-${role}-inactive` : undefined"
                      color="primary"
                      density="compact"
                      @update:model-value="updatePermission(role, { allow_execution: Boolean($event) })"
                    />
                  </span>
                </template>
              </v-tooltip>
              <span
                v-if="executionBlockedRoles.includes(role)"
                :id="`local-execution-${role}-inactive`"
                class="execution-status text-warning text-caption"
              >
                {{ tm('executionInactive') }}
                <v-tooltip
                  location="top"
                  open-on-click
                  :max-width="480"
                  :text="tm('executionBlocked', {
                    role: tm(`roles.${role}`),
                    reason: isolationFailureReason
                  })"
                >
                  <template #activator="{ props: helpProps }">
                    <button v-bind="helpProps" type="button" class="scope-help" :aria-label="`${tm(`roles.${role}`)} · ${tm('executionInactiveHelp')}`">
                      <CircleHelp :size="14" aria-hidden="true" />
                    </button>
                  </template>
                </v-tooltip>
              </span>
            </div>
          </td>
          <td v-if="!isolationUnavailable">
            <v-checkbox-btn
              :model-value="policy(role, false).allow_network"
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
                { title: tm('scopes.workspace'), value: 'workspace' },
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
                      {{ tm(`scopeHints.${item.value}`) }}
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

    <v-alert v-if="memberHasElevatedAccess" type="warning" variant="tonal" density="compact">
      {{ tm('memberWarning') }}
    </v-alert>
  </div>
</template>

<script>
export const localPermissionDefaults = {
  member: { filesystem_scope: 'workspace', allow_execution: false, allow_network: false },
  admin: { filesystem_scope: 'host', allow_execution: true, allow_network: true }
}
</script>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { CircleHelp } from '@lucide/vue'
import { useModuleI18n } from '@/i18n/composables'
import { statsApi } from '@/api/v1'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue'])
const { tm } = useModuleI18n('features/config-metadata.ai_group.agent_computer_use.local_permissions')
const runtime = ref(null)
const runtimeLoading = ref(true)
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
const isolationFailureReason = computed(() => {
  if (!isolationUnavailable.value) return ''
  const reason = tm(`runtime.isolationFailure.${runtime.value.sandbox.status}`, {
    backend: runtime.value.sandbox.backend === 'seatbelt' ? 'Seatbelt' : 'bubblewrap',
    dependency: runtime.value.sandbox.backend === 'seatbelt' ? 'sandbox-exec' : 'bwrap'
  })
  return runtime.value.sandbox.error ? `${reason} ${runtime.value.sandbox.error}` : reason
})
const roles = ['member', 'admin']
const defaults = computed(() => localPermissionDefaults)
const executionBlockedRoles = computed(() => roles.filter(role =>
  isolationUnavailable.value && policy(role, false).allow_execution && !policy(role).allow_execution
))

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

function policy(role, applyRuntime = true) {
  const resolved = {
    ...defaults.value[role],
    ...(props.modelValue?.[role] || {})
  }
  if (!['none', 'workspace', 'host'].includes(resolved.filesystem_scope)) {
    resolved.filesystem_scope = defaults.value[role].filesystem_scope
  }
  resolved.allow_execution = resolved.filesystem_scope !== 'none' && resolved.allow_execution === true
  resolved.allow_network = resolved.allow_execution && resolved.allow_network === true
  if (applyRuntime && isolationUnavailable.value && resolved.allow_execution &&
      (resolved.filesystem_scope !== 'host' || !resolved.allow_network)) {
    return { ...resolved, allow_execution: false, allow_network: false }
  }
  return resolved
}

function updatePermission(role, changes) {
  const updatedRole = {
    ...policy(role, false),
    ...changes
  }
  if (updatedRole.filesystem_scope === 'none') {
    updatedRole.allow_execution = false
  }
  if (isolationUnavailable.value && changes.allow_execution === true) {
    // Explicitly enabling direct execution also grants its required network access.
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
  const current = policy(role, false)
  return [role, {
    execution: !runtime.value || current.filesystem_scope === 'none' ||
      (isolationUnavailable.value && current.filesystem_scope === 'workspace' && !current.allow_execution),
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

.execution-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 4px;
}

.execution-status {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
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
