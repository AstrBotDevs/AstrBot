<template>
  <v-dialog
    :model-value="modelValue"
    max-width="520"
    @update:model-value="val => emit('update:modelValue', val)"
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
        {{ tm('system_group.system.dashboard.totp.configuration') }}
        <v-spacer></v-spacer>
        <v-btn icon variant="text" size="small" @click="emit('update:modelValue', false)">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text class="pa-4">
        <div class="totp-dialog-subtitle mb-3">
          {{ tm('system_group.system.dashboard.totp.activeSubtitle') }}
        </div>
        <div class="text-center">
          <QrCodeViewer
            v-if="totpProvisioningUri"
            :value="totpProvisioningUri"
            alt="TOTP QR Code"
            :size="220"
          />
          <div class="totp-current-secret-wrap mt-3">
            <code class="totp-secret">{{ totpSecret }}</code>
          </div>
        </div>
        <div class="d-flex justify-center ga-3 mt-4">
          <v-btn
            color="primary"
            variant="tonal"
            @click="emit('rotate')"
          >
            <v-icon class="mr-1" size="16">mdi-shield-key</v-icon>
            {{ tm('system_group.system.dashboard.totp.rotate') }}
          </v-btn>
          <v-btn
            color="secondary"
            variant="tonal"
            @click="emit('rotate-recovery')"
          >
            <v-icon class="mr-1" size="16">mdi-key-variant</v-icon>
            {{ tm('system_group.system.dashboard.totp.rotateRecovery') }}
          </v-btn>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed } from 'vue'
import QrCodeViewer from './QrCodeViewer.vue'
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

const emit = defineEmits(['update:modelValue', 'rotate', 'rotate-recovery'])
const { tm } = useModuleI18n('features/config-metadata')

const totpSecret = computed(() => props.configRoot?.dashboard?.totp?.secret || '')

const totpProvisioningUri = computed(() => {
  if (!totpSecret.value) return ''
  const label = encodeURIComponent(props.configRoot?.dashboard?.username || 'AstrBot')
  const issuer = encodeURIComponent('AstrBot')
  return `otpauth://totp/${label}?secret=${encodeURIComponent(totpSecret.value)}&issuer=${issuer}`
})
</script>

<style scoped>
.totp-dialog-subtitle {
  font-size: 0.9rem;
  color: rgba(var(--v-theme-on-surface), 0.68);
}

.totp-current-secret-wrap {
  background: rgba(var(--v-theme-on-surface), 0.04);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  padding: 10px;
}

.totp-secret {
  word-break: break-all;
  font-size: 0.8rem;
  font-weight: 500;
}
</style>
