<template>
  <div class="local-permission-matrix">
    <v-table density="compact" class="permission-table">
      <thead>
        <tr>
          <th>{{ tm('ai_group.agent_computer_use.local_permissions.role') }}</th>
          <th class="text-center">{{ tm('ai_group.agent_computer_use.local_permissions.execution') }}</th>
          <th class="text-center">{{ tm('ai_group.agent_computer_use.local_permissions.network') }}</th>
          <th class="text-center">{{ tm('ai_group.agent_computer_use.local_permissions.hostFilesystem') }}</th>
          <th>{{ tm('ai_group.agent_computer_use.local_permissions.result') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="role in roles" :key="role">
          <td class="role-cell">
            {{ tm(`ai_group.agent_computer_use.local_permissions.roles.${role}`) }}
          </td>
          <td class="permission-cell">
            <v-checkbox-btn
              :model-value="policy(role).allow_execution"
              color="primary"
              density="compact"
              :aria-label="tm('ai_group.agent_computer_use.local_permissions.execution')"
              @update:model-value="updatePermission(role, 'allow_execution', Boolean($event))"
            />
          </td>
          <td class="permission-cell">
            <v-checkbox-btn
              :model-value="policy(role).allow_network"
              :disabled="!policy(role).allow_execution"
              color="primary"
              density="compact"
              :aria-label="tm('ai_group.agent_computer_use.local_permissions.network')"
              @update:model-value="updatePermission(role, 'allow_network', Boolean($event))"
            />
          </td>
          <td class="permission-cell">
            <v-checkbox-btn
              :model-value="policy(role).filesystem_scope === 'host'"
              color="primary"
              density="compact"
              :aria-label="tm('ai_group.agent_computer_use.local_permissions.hostFilesystem')"
              @update:model-value="updatePermission(role, 'filesystem_scope', $event ? 'host' : 'workspace')"
            />
          </td>
          <td>
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
      class="mt-3"
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
    filesystem_scope: 'host'
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
  width: 100%;
}

.permission-table {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}

.permission-table th {
  white-space: nowrap;
  font-size: 0.8rem;
}

.role-cell {
  min-width: 92px;
  font-weight: 500;
}

.permission-cell {
  text-align: center;
}

.permission-cell :deep(.v-selection-control) {
  justify-content: center;
}

.permission-help {
  margin-top: 10px;
  font-size: 0.8rem;
  line-height: 1.45;
}

@media (max-width: 720px) {
  .local-permission-matrix {
    overflow-x: auto;
  }

  .permission-table {
    min-width: 620px;
  }
}
</style>
