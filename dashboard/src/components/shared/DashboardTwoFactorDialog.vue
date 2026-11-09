<template>
  <v-dialog
    :model-value="modelValue"
    max-width="520"
    @update:model-value="onVisibilityChange"
    @click:outside="onCancel"
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
        {{ tm('system_group.system.dashboard.totp.configSaveTitle') }}
        <v-spacer></v-spacer>
        <v-btn icon variant="text" size="small" @click="onCancel">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text class="pa-4">
        <div class="totp-dialog-subtitle mb-3">
          {{ tm('system_group.system.dashboard.totp.configSaveSubtitle') }}
        </div>
        <div v-if="rotationHint" class="totp-dialog-rotation-hint mb-3">
          {{ rotationHint }}
        </div>
        <v-text-field
          v-model="code"
          :label="tm('system_group.system.dashboard.totp.configSaveCode')"
          variant="outlined"
          density="compact"
          class="totp-code-input"
          maxlength="6"
          :error-messages="errorMessage"
          :loading="saving"
          hide-details="auto"
          prepend-inner-icon="mdi-shield-key"
          @keyup.enter="confirm"
        ></v-text-field>
        <div class="d-flex justify-end ga-2 mt-4">
          <v-btn
            variant="text"
            :disabled="saving"
            @click="onCancel"
          >
            {{ tm('system_group.system.dashboard.totp.configSaveCancel') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="saving"
            :disabled="!code || code.length < 6"
            @click="confirm"
          >
            {{ tm('system_group.system.dashboard.totp.configSaveConfirm') }}
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
  errorMessage: {
    type: String,
    default: ''
  },
  saving: {
    type: Boolean,
    default: false
  },
  rotationHint: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'confirm', 'cancel'])
const { tm } = useModuleI18n('features/config-metadata')

const code = ref('')

function resetState() {
  code.value = ''
}

function onVisibilityChange(val) {
  if (!val) {
    resetState()
  }
  emit('update:modelValue', val)
}

function onCancel() {
  resetState()
  emit('cancel')
  emit('update:modelValue', false)
}

function confirm() {
  if (!code.value) return
  emit('confirm', code.value)
}
</script>

<style scoped>
.totp-dialog-subtitle {
  font-size: 0.9rem;
  color: rgba(var(--v-theme-on-surface), 0.68);
}

.totp-dialog-rotation-hint {
  font-size: 0.82rem;
  color: rgba(var(--v-theme-info, 33, 150, 243), 0.78);
  background: rgba(var(--v-theme-info, 33, 150, 243), 0.08);
  padding: 8px 12px;
  border-radius: 6px;
  line-height: 1.4;
}

.totp-code-input {
  max-width: 240px;
  margin: 0 auto;
}
</style>
