<template>
  <v-dialog
    :model-value="modelValue"
    max-width="520"
    persistent
    @update:model-value="val => emit('update:modelValue', val)"
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
        {{ tm('system_group.system.dashboard.totp.recoveryTitle') }}
        <v-spacer></v-spacer>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text class="pa-4">
        <div class="totp-dialog-subtitle mb-3">
          {{ tm('system_group.system.dashboard.totp.recoverySubtitle') }}
        </div>
        <v-alert
          type="warning"
          variant="tonal"
          density="compact"
          class="mb-3"
          :text="tm('system_group.system.dashboard.totp.recoveryWarning')"
          hide-details
        ></v-alert>
        <div class="totp-recovery-card">
          <code class="totp-recovery-text">{{ recoveryCode }}</code>
        </div>
        <v-checkbox
          v-model="acknowledged"
          :label="tm('system_group.system.dashboard.totp.recoveryAcknowledge')"
          color="primary"
          density="comfortable"
          hide-details
          class="mt-2"
        ></v-checkbox>
        <div class="d-flex justify-end mt-4">
          <v-btn
            color="primary"
            variant="tonal"
            :disabled="!acknowledged"
            @click="onClose"
          >
            {{ tm('system_group.system.dashboard.totp.recoveryClose') }}
          </v-btn>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { useModuleI18n } from '@/i18n/composables'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  recoveryCode: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'close'])
const { tm } = useModuleI18n('features/config-metadata')

const acknowledged = ref(false)

function onClose() {
  acknowledged.value = false
  emit('close')
  emit('update:modelValue', false)
}
</script>

<style scoped>
.totp-dialog-subtitle {
  font-size: 0.9rem;
  color: rgba(var(--v-theme-on-surface), 0.68);
}

.totp-recovery-card {
  background: rgba(var(--v-theme-on-surface), 0.04);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  padding: 12px;
  text-align: center;
  margin: 8px 0;
}

.totp-recovery-text {
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: 1.3px;
  word-break: keep-all;
  user-select: all;
}
</style>
