<template>
  <div class="totp-manager">
    <v-switch
      :model-value="modelValue"
      @update:model-value="onTotpToggle"
      color="primary"
      inset
      density="compact"
      hide-details
    ></v-switch>
    <div v-if="modelValue" class="totp-manager-actions">
      <v-chip
        size="small"
        :color="isTotpInitialSetup ? 'warning' : 'success'"
        variant="tonal"
      >
        <v-icon start size="14">
          {{ isTotpInitialSetup ? 'mdi-alert-circle-outline' : 'mdi-check-circle-outline' }}
        </v-icon>
        {{ isTotpInitialSetup
          ? tm('system_group.system.dashboard.totp.statusPending')
          : tm('system_group.system.dashboard.totp.statusEnabled') }}
      </v-chip>
      <v-btn
        color="primary"
        variant="tonal"
        size="small"
        @click="openTotpDialog"
      >
        {{ tm('system_group.system.dashboard.totp.manage') }}
      </v-btn>
    </div>
  </div>
  <div v-if="modelValue && isTotpInitialSetup" class="totp-setup-hint">
    {{ tm('system_group.system.dashboard.totp.setupRequiredHint') }}
  </div>

  <DashboardTotpSetupDialog
    v-model="setupDialogVisible"
    :config-root="configRoot"
    :mode="setupDialogMode"
    @setup-complete="onSetupComplete"
  />
  <DashboardTotpRecoveryDialog
    v-model="recoveryDialogVisible"
    :recovery-code="pendingRecoveryCode"
    @close="recoveryDialogVisible = false"
  />
  <DashboardTotpManageDialog
    v-model="manageDialogVisible"
    :config-root="configRoot"
    @rotate="onStartRotate"
    @rotate-recovery="onStartRotateRecovery"
  />
</template>

<script setup>
import { computed, ref } from 'vue'
import DashboardTotpSetupDialog from './DashboardTotpSetupDialog.vue'
import DashboardTotpRecoveryDialog from './DashboardTotpRecoveryDialog.vue'
import DashboardTotpManageDialog from './DashboardTotpManageDialog.vue'
import { authApi } from '@/api/v1'
import { useModuleI18n } from '@/i18n/composables'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  configRoot: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:modelValue'])
const { tm } = useModuleI18n('features/config-metadata')

const setupDialogVisible = ref(false)
const recoveryDialogVisible = ref(false)
const manageDialogVisible = ref(false)
const setupDialogMode = ref('setup')
const pendingRecoveryCode = ref('')

const totpSecret = computed(() => props.configRoot?.dashboard?.totp?.secret || '')
const totpRecoveryCodeHash = computed(
  () => props.configRoot?.dashboard?.totp?.recovery_code_hash || ''
)
const isTotpInitialSetup = computed(
  () =>
    props.modelValue === true
    && (!totpSecret.value || !totpRecoveryCodeHash.value)
)

function emitUpdate(val) {
  emit('update:modelValue', val)
}

function clearTotpConfig() {
  if (props.configRoot?.dashboard?.totp) {
    props.configRoot.dashboard.totp.enable = false
  }
}

function writeTotpSecretToConfig(secret, recoveryCodeHash = '') {
  if (!props.configRoot?.dashboard) return
  if (!props.configRoot.dashboard.totp) {
    props.configRoot.dashboard.totp = {}
  }
  props.configRoot.dashboard.totp.enable = true
  props.configRoot.dashboard.totp.secret = secret
  props.configRoot.dashboard.totp.recovery_code_hash = recoveryCodeHash
}

function onTotpToggle(val) {
  if (!val) {
    clearTotpConfig()
    emitUpdate(val)
    return
  }
  if (!totpSecret.value || !totpRecoveryCodeHash.value) {
    setupDialogMode.value = 'setup'
    setupDialogVisible.value = true
  }
  emitUpdate(true)
}

function openTotpDialog() {
  if (isTotpInitialSetup.value) {
    setupDialogMode.value = 'setup'
    setupDialogVisible.value = true
    return
  }
  manageDialogVisible.value = true
}

function onSetupComplete({ secret, recoveryCode, recoveryCodeHash }) {
  writeTotpSecretToConfig(secret, recoveryCodeHash)
  pendingRecoveryCode.value = recoveryCode
  recoveryDialogVisible.value = true
}

function onStartRotate() {
  manageDialogVisible.value = false
  setupDialogMode.value = 'rotate'
  setupDialogVisible.value = true
}

async function onStartRotateRecovery() {
  manageDialogVisible.value = false
  if (!totpSecret.value) return
  try {
    const res = await authApi.recoverTotp()
    if (res.data.status !== 'ok') return
    const { recovery_code: recoveryCode, recovery_code_hash: recoveryCodeHash } = res.data.data || {}
    if (!recoveryCode || !recoveryCodeHash) return
    if (!props.configRoot?.dashboard?.totp) return
    props.configRoot.dashboard.totp.recovery_code_hash = recoveryCodeHash
    pendingRecoveryCode.value = recoveryCode
    recoveryDialogVisible.value = true
  } catch {
    // silently fail
  }
}
</script>

<style scoped>
.totp-manager {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.totp-manager-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.totp-setup-hint {
  margin-top: 6px;
  font-size: 0.8rem;
  color: rgba(var(--v-theme-warning), 0.95);
}
</style>
