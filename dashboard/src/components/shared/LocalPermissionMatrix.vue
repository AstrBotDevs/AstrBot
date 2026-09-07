<template>
  <div class="local-permission-matrix">
    <v-table class="permission-table">
      <thead>
        <tr>
          <th scope="col">{{ tm('ai_group.agent_computer_use.local_permissions.role') }}</th>
          <th scope="col" class="text-center">{{ tm('ai_group.agent_computer_use.local_permissions.execution') }}</th>
          <th scope="col" class="text-center">{{ tm('ai_group.agent_computer_use.local_permissions.network') }}</th>
          <th scope="col" class="text-center">{{ tm('ai_group.agent_computer_use.local_permissions.hostFilesystem') }}</th>
          <th scope="col" class="text-center">{{ tm('ai_group.agent_computer_use.local_permissions.result') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="role in roles" :key="role" class="permission-row">
          <td class="role-cell">
            {{ tm(`ai_group.agent_computer_use.local_permissions.roles.${role}`) }}
          </td>
          <td class="permission-cell" :data-label="tm('ai_group.agent_computer_use.local_permissions.execution')">
            <v-checkbox-btn
              :model-value="policy(role).allow_execution"
              color="primary"
              density="compact"
              :aria-label="`${tm(`ai_group.agent_computer_use.local_permissions.roles.${role}`)} · ${tm('ai_group.agent_computer_use.local_permissions.execution')}`"
              @update:model-value="updatePermission(role, 'allow_execution', Boolean($event))"
            />
          </td>
          <td class="permission-cell" :data-label="tm('ai_group.agent_computer_use.local_permissions.network')">
            <v-checkbox-btn
              :model-value="policy(role).allow_network"
              :disabled="!policy(role).allow_execution"
              color="primary"
              density="compact"
              :aria-label="`${tm(`ai_group.agent_computer_use.local_permissions.roles.${role}`)} · ${tm('ai_group.agent_computer_use.local_permissions.network')}`"
              @update:model-value="updatePermission(role, 'allow_network', Boolean($event))"
            />
          </td>
          <td class="permission-cell" :data-label="tm('ai_group.agent_computer_use.local_permissions.hostFilesystem')">
            <v-checkbox-btn
              :model-value="policy(role).filesystem_scope === 'host'"
              color="primary"
              density="compact"
              :aria-label="`${tm(`ai_group.agent_computer_use.local_permissions.roles.${role}`)} · ${tm('ai_group.agent_computer_use.local_permissions.hostFilesystem')}`"
              @update:model-value="updatePermission(role, 'filesystem_scope', $event ? 'host' : 'workspace')"
            />
          </td>
          <td class="permission-status">
            <v-chip size="small" :color="policyResult(role).color" variant="tonal">
              {{ policyResult(role).label }}
            </v-chip>
          </td>
        </tr>
      </tbody>
    </v-table>

    <div class="permission-help text-medium-emphasis">
      {{ tm('ai_group.agent_computer_use.local_permissions.help') }}
    </div>

    <v-alert
      v-if="memberHasElevatedAccess"
      type="warning"
      variant="tonal"
      density="compact"
      class="permission-warning"
    >
      {{ tm('ai_group.agent_computer_use.local_permissions.memberWarning') }}
    </v-alert>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useModuleI18n } from '@/i18n/composables'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue'])
const { tm } = useModuleI18n('features/config-metadata')
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

function policy(role) {
  const resolved = {
    ...defaults[role],
    ...(props.modelValue?.[role] || {})
  }
  if (!resolved.allow_execution) {
    resolved.allow_network = false
  }
  if (!['workspace', 'host'].includes(resolved.filesystem_scope)) {
    resolved.filesystem_scope = defaults[role].filesystem_scope
  }
  return resolved
}

function updatePermission(role, key, value) {
  const updatedRole = {
    ...policy(role),
    [key]: value
  }
  if (key === 'allow_execution' && !value) {
    updatedRole.allow_network = false
  }
  emit('update:modelValue', {
    ...(props.modelValue || {}),
    [role]: updatedRole
  })
}

function policyResult(role) {
  const current = policy(role)
  if (!current.allow_execution) {
    return {
      label: tm('ai_group.agent_computer_use.local_permissions.states.filesOnly'),
      color: 'default'
    }
  }
  if (current.allow_network && current.filesystem_scope === 'host') {
    return {
      label: tm('ai_group.agent_computer_use.local_permissions.states.full'),
      color: 'warning'
    }
  }
  return {
    label: tm('ai_group.agent_computer_use.local_permissions.states.isolated'),
    color: 'primary'
  }
}

const memberHasElevatedAccess = computed(() => {
  const member = policy('member')
  return member.allow_network || member.filesystem_scope === 'host'
})
</script>

<style scoped>
.local-permission-matrix {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
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

.permission-table th {
  white-space: normal;
  line-height: 1.4;
  font-size: 0.8rem;
  background: rgba(var(--v-theme-on-surface), 0.035);
}

.permission-table :deep(th),
.permission-table :deep(td) {
  border-bottom-color: rgba(var(--v-theme-on-surface), 0.12) !important;
}

.role-cell {
  min-width: 80px;
  font-weight: 500;
}

.permission-cell {
  text-align: center;
}

.permission-cell :deep(.v-selection-control) {
  justify-content: center;
}

.permission-status {
  text-align: center;
}

.permission-status :deep(.v-chip) {
  height: auto;
  min-height: 24px;
  padding-block: 4px;
}

.permission-status :deep(.v-chip__content) {
  white-space: normal;
}

.permission-help {
  font-size: 0.8rem;
  line-height: 1.65;
}

.permission-warning {
  font-size: 0.8rem;
  line-height: 1.6;
}

@media (max-width: 600px) {
  .permission-table {
    border: 0;
    background: transparent;
  }

  .permission-table :deep(table) {
    display: block;
  }

  .permission-table thead {
    display: none;
  }

  .permission-table tbody {
    display: grid;
    gap: 12px;
  }

  .permission-table .permission-row {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    padding: 12px;
    border: 1px solid rgba(var(--v-theme-on-surface), 0.16);
    border-radius: 8px;
  }

  .permission-table .permission-row > td {
    height: auto;
    min-width: 0;
    padding: 0;
    border-bottom: 0 !important;
  }

  .permission-table .permission-row > .permission-cell {
    display: flex;
    grid-column: 1 / -1;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    min-height: 44px;
  }

  .permission-cell :deep(.v-selection-control) {
    flex: 0 0 auto;
  }

  .permission-cell::before {
    content: attr(data-label);
    font-size: 0.8rem;
    text-align: left;
  }

  .permission-status {
    grid-column: 2;
    grid-row: 1;
  }
}
</style>
