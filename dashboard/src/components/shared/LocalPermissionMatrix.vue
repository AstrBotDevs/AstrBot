<template>
  <div class="local-permission-matrix" :class="{ 'local-permission-matrix--simple': unsupported }">
    <v-progress-linear v-if="runtimeLoading && !runtime" indeterminate color="primary" />
    <v-alert v-else-if="!runtime" type="warning" variant="tonal" density="compact">
      {{ tm('runtimeUnknown') }}
    </v-alert>
    <dl v-else class="runtime-info">
      <div>
        <dt><Monitor :size="14" aria-hidden="true" />{{ tm('runtime.os') }}</dt>
        <dd>{{ { linux: 'Linux', darwin: 'macOS', windows: 'Windows' }[runtime.os] || runtime.os }}</dd>
      </div>
      <div>
        <dt><Cpu :size="14" aria-hidden="true" />{{ tm('runtime.arch') }}</dt>
        <dd>{{ runtime.arch || '—' }}</dd>
      </div>
      <div :class="{ 'runtime-info--warning': sandboxMissing }">
        <dt>
          <component
            :is="sandboxMissing ? ShieldAlert : unsupported ? ShieldOff : Shield"
            :size="14"
            :class="sandboxMissing ? 'text-warning' : unsupported ? '' : 'text-primary'"
            aria-hidden="true"
          />
          {{ tm('runtime.sandbox') }}
        </dt>
        <dd>
          {{ tm(`runtime.status.${runtime.sandbox.status}`, {
            backend: runtime.sandbox.backend === 'seatbelt' ? 'Seatbelt' : 'bubblewrap',
            dependency: runtime.sandbox.backend === 'seatbelt' ? 'sandbox-exec' : 'bwrap'
          }) }}
        </dd>
      </div>
    </dl>

    <v-table class="permission-table">
      <thead>
        <tr>
          <th scope="col">{{ tm('role') }}</th>
          <th v-if="unsupported" scope="col">{{ tm('accessMode') }}</th>
          <template v-else>
            <th scope="col" class="text-center">{{ tm('execution') }}</th>
            <th scope="col" class="text-center">{{ tm('network') }}</th>
            <th scope="col" class="text-center">{{ tm('filesystem') }}</th>
          </template>
        </tr>
      </thead>
      <tbody>
        <tr v-for="role in roles" :key="role" :aria-label="tm(`roles.${role}`)">
          <th scope="row">{{ tm(`roles.${role}`) }}</th>
          <td v-if="unsupported">
            <v-select
              :model-value="accessModes[role]"
              :items="[
                { title: tm('modes.none'), value: 'none' },
                { title: tm('modes.files'), value: 'files' },
                { title: tm('modes.full'), value: 'full' }
              ]"
              :placeholder="tm('unsupportedSelection')"
              :aria-label="`${tm(`roles.${role}`)} · ${tm('accessMode')}`"
              persistent-placeholder
              hide-details
              variant="outlined"
              density="compact"
              :color="accessModes[role] === 'full' ? 'warning' : 'primary'"
              :menu-props="{ rounded: 'lg' }"
              @update:model-value="updatePermission(role, accessPolicies[$event])"
            >
              <template #prepend-inner>
                <component
                  :is="accessIcons[accessModes[role]]"
                  v-if="accessModes[role]"
                  :size="18"
                  :class="accessModes[role] === 'full' ? 'text-warning' : 'text-medium-emphasis'"
                  aria-hidden="true"
                />
              </template>
              <template #item="{ props: itemProps, item }">
                <v-list-item v-bind="itemProps" role="option" :aria-selected="accessModes[role] === item.value">
                  <template #prepend>
                    <component :is="accessIcons[item.value]" :size="18" class="mr-3" aria-hidden="true" />
                  </template>
                </v-list-item>
              </template>
            </v-select>
          </td>
          <template v-else>
            <td class="permission-toggle">
              <v-checkbox-btn
                :model-value="policy(role).allow_execution"
                :disabled="permissionLocks[role].execution"
                :aria-label="`${tm(`roles.${role}`)} · ${tm('execution')}`"
                color="primary"
                density="compact"
                @update:model-value="updatePermission(role, { allow_execution: Boolean($event) })"
              />
              <LockKeyhole v-if="permissionLocks[role].execution" class="permission-lock" :size="12" aria-hidden="true" />
            </td>
            <td class="permission-toggle">
              <v-checkbox-btn
                :model-value="policy(role).allow_network"
                :disabled="permissionLocks[role].network"
                :aria-label="`${tm(`roles.${role}`)} · ${tm('network')}`"
                color="primary"
                density="compact"
                @update:model-value="updatePermission(role, { allow_network: Boolean($event) })"
              />
              <LockKeyhole v-if="permissionLocks[role].network" class="permission-lock" :size="12" aria-hidden="true" />
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
                @update:model-value="updatePermission(role, { filesystem_scope: $event })"
              />
            </td>
          </template>
        </tr>
      </tbody>
    </v-table>

    <v-alert v-if="memberHasElevatedAccess" type="warning" variant="tonal" density="compact">
      {{ tm('memberWarning') }}
    </v-alert>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Cpu, FolderOpen, LockKeyhole, Monitor, Shield, ShieldAlert, ShieldOff } from '@lucide/vue'
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
const sandboxMissing = computed(() => runtime.value?.sandbox?.status === 'missing')
const roles = ['member', 'admin']
const defaults = {
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
}

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
    ...defaults[role],
    ...(props.modelValue?.[role] || {})
  }
  if (!['none', 'workspace', 'host'].includes(resolved.filesystem_scope)) {
    resolved.filesystem_scope = defaults[role].filesystem_scope
  }
  resolved.allow_execution = resolved.filesystem_scope !== 'none' && resolved.allow_execution === true
  resolved.allow_network = resolved.allow_execution && resolved.allow_network === true
  return resolved
}

function updatePermission(role, changes) {
  const updatedRole = {
    ...policy(role),
    ...changes
  }
  if (updatedRole.filesystem_scope === 'none' || (sandboxMissing.value && changes.filesystem_scope === 'workspace')) {
    updatedRole.allow_execution = false
  }
  if (sandboxMissing.value && changes.allow_execution === true) {
    if (updatedRole.filesystem_scope === 'workspace') {
      updatedRole.allow_execution = false
    } else {
      updatedRole.allow_network = true
    }
  }
  if (!updatedRole.allow_execution) {
    updatedRole.allow_network = false
  }
  emit('update:modelValue', {
    ...(props.modelValue || {}),
    [role]: updatedRole
  })
}

const accessPolicies = {
  none: { filesystem_scope: 'none', allow_execution: false, allow_network: false },
  files: { filesystem_scope: 'host', allow_execution: false, allow_network: false },
  full: { filesystem_scope: 'host', allow_execution: true, allow_network: true }
}
const accessIcons = { none: LockKeyhole, files: FolderOpen, full: ShieldAlert }
const permissionLocks = computed(() => Object.fromEntries(roles.map(role => {
  const current = policy(role)
  return [role, {
    execution: !runtime.value || current.filesystem_scope === 'none' ||
      (sandboxMissing.value && current.filesystem_scope === 'workspace' && !current.allow_execution),
    network: !runtime.value || !current.allow_execution ||
      (sandboxMissing.value && current.allow_network)
  }]
})))
const accessModes = computed(() => Object.fromEntries(roles.map(role => {
  const current = policy(role)
  let mode = null
  if (current.filesystem_scope === 'none') {
    mode = 'none'
  } else if (current.filesystem_scope === 'host') {
    if (!current.allow_execution) mode = 'files'
    else if (current.allow_network) mode = 'full'
  }
  return [role, mode]
})))

const memberHasElevatedAccess = computed(() => {
  const member = policy('member')
  return member.allow_network || member.filesystem_scope === 'host'
})
</script>

<style scoped>
.local-permission-matrix {
  display: grid;
  gap: 12px;
  width: 100%;
  min-width: 0;
  padding-top: 12px;
}

.runtime-info,
.runtime-info > div,
.runtime-info dt {
  display: flex;
  align-items: center;
  gap: 8px;
}

.runtime-info {
  flex-wrap: wrap;
  margin: 0;
  font-size: 0.8125rem;
  line-height: 20px;
}

.runtime-info > div {
  flex-wrap: wrap;
  padding: 6px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.runtime-info dt {
  gap: 6px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 0.75rem;
}

.runtime-info dd {
  margin: 0;
  font-weight: 500;
}

.runtime-info > .runtime-info--warning {
  border-color: rgba(var(--v-theme-warning), 0.3);
  background: rgba(var(--v-theme-warning), 0.08);
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

.permission-toggle {
  position: relative;
}

.permission-lock {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: rgba(var(--v-theme-on-surface), 0.4);
  pointer-events: none;
}

.local-permission-matrix--simple {
  max-width: 640px;
  gap: 8px;
}

.local-permission-matrix--simple .permission-table :deep(table) {
  min-width: 0;
}

.local-permission-matrix--simple .permission-table :deep(th:first-child) {
  width: 140px;
}

.local-permission-matrix--simple .permission-table :deep(thead th) {
  height: 40px;
  font-size: 0.75rem;
  color: rgba(var(--v-theme-on-surface), 0.65);
}

.local-permission-matrix--simple .permission-table :deep(td) {
  height: 68px;
  padding: 12px 16px;
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

  .local-permission-matrix--simple .permission-table :deep(th:first-child) {
    width: 88px;
  }
}
</style>
