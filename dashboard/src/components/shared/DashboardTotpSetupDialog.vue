<template>
  <v-dialog
    :model-value="modelValue"
    max-width="520"
    @update:model-value="onVisibilityChange"
    @click:outside="onCancel"
  >
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        {{ cardTitle }}
        <v-spacer></v-spacer>
        <v-btn icon variant="text" size="small" @click="onCancel">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text class="pa-4">
        <template v-if="step === 'verify'">
          <div class="totp-dialog-subtitle mb-3">
            输入当前认证器应用中的验证码以验证身份。
          </div>
          <div class="text-center">
            <v-text-field
              v-model="verifyCode"
              label="当前验证码"
              variant="outlined"
              density="compact"
              class="totp-code-input"
              maxlength="6"
              :error-messages="verifyError"
              :loading="verifyingIdentity"
              hide-details="auto"
              prepend-inner-icon="mdi-shield-key"
              @keyup.enter="verifyIdentity"
            ></v-text-field>
          </div>
          <div class="d-flex justify-end ga-2 mt-4">
            <v-btn
              variant="text"
              :disabled="verifyingIdentity"
              @click="onCancel"
            >
              取消
            </v-btn>
            <v-btn
              color="primary"
              variant="tonal"
              :loading="verifyingIdentity"
              :disabled="!verifyCode || verifyCode.length < 6"
              @click="verifyIdentity"
            >
              验证
            </v-btn>
          </div>
        </template>
        <template v-else>
          <div class="totp-dialog-subtitle mb-3">
            {{ dialogSubtitle }}
          </div>
          <div class="text-center">
            <v-alert
                type="info"
                variant="tonal"
                density="compact"
                class="mb-3 text-start"
                :text="tm('system_group.system.dashboard.totp.rotateCodeHint')"
                hide-details
              ></v-alert>
              <QrCodeViewer
                v-if="totpProvisioningUri"
                :value="totpProvisioningUri"
                alt="TOTP QR Code"
                :size="220"
              />
              <div class="totp-new-secret-wrap mt-3">
                <code class="totp-secret">{{ newSecret }}</code>
              </div>
              <v-text-field
                v-model="code"
                :label="tm('system_group.system.dashboard.totp.rotateCode')"
                variant="outlined"
                density="compact"
                class="totp-code-input mt-3"
                maxlength="6"
                :error-messages="codeError"
                :loading="verifying"
                hide-details="auto"
                prepend-inner-icon="mdi-shield-key"
                @keyup.enter="confirmSetup"
              ></v-text-field>
            </div>
            <div class="d-flex justify-end ga-2 mt-4">
              <v-btn
                variant="text"
                :disabled="verifying"
                @click="onCancel"
              >
                {{ tm('system_group.system.dashboard.totp.rotateCancel') }}
              </v-btn>
              <v-btn
                color="primary"
                variant="tonal"
                :loading="verifying"
                :disabled="!code || code.length < 6"
                @click="confirmSetup"
              >
                {{ confirmLabel }}
              </v-btn>
            </div>
        </template>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { authApi } from '@/api/v1'
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
  },
  mode: {
    type: String,
    default: 'setup',
    validator: (v) => ['setup', 'rotate'].includes(v)
  }
})

const emit = defineEmits(['update:modelValue', 'setupComplete'])
const { tm } = useModuleI18n('features/config-metadata')

const step = ref('verify')
const loading = ref(false)
const newSecret = ref('')
const code = ref('')
const codeError = ref('')
const verifying = ref(false)

const verifyCode = ref('')
const verifyError = ref('')
const verifyingIdentity = ref(false)

const cardTitle = computed(() => {
  if (step.value === 'verify') {
    return '验证当前 TOTP'
  }
  return props.mode === 'rotate'
    ? tm('system_group.system.dashboard.totp.rotateTitle')
    : tm('system_group.system.dashboard.totp.setupTitle')
})

const dialogSubtitle = computed(() => {
  return props.mode === 'rotate'
    ? tm('system_group.system.dashboard.totp.rotateSubtitle')
    : tm('system_group.system.dashboard.totp.setupSubtitle')
})

const confirmLabel = computed(() => {
  return props.mode === 'rotate'
    ? tm('system_group.system.dashboard.totp.rotateConfirm')
    : tm('system_group.system.dashboard.totp.setupConfirm')
})

const totpProvisioningUri = computed(() => {
  if (!newSecret.value) return ''
  const label = encodeURIComponent(props.configRoot?.dashboard?.username || 'AstrBot')
  const issuer = encodeURIComponent('AstrBot')
  return `otpauth://totp/${label}?secret=${encodeURIComponent(newSecret.value)}&issuer=${issuer}`
})

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      if (props.mode === 'rotate') {
        step.value = 'verify'
        return
      }
      step.value = 'setup'
      void fetchNewSecret()
      return
    }
    resetState()
  }
)

function resetState() {
  step.value = 'verify'
  newSecret.value = ''
  code.value = ''
  codeError.value = ''
  verifyCode.value = ''
  verifyError.value = ''
  verifyingIdentity.value = false
}

function onVisibilityChange(val) {
  if (!val) {
    resetState()
  }
  emit('update:modelValue', val)
}

function onCancel() {
  resetState()
  emit('update:modelValue', false)
}

async function fetchNewSecret() {
  if (loading.value || newSecret.value) {
    return
  }
  loading.value = true
  try {
    const res = await authApi.setupTotp()
    if (res.data.status !== 'ok') {
      return
    }
    newSecret.value = res.data.data?.secret || ''
    code.value = ''
    codeError.value = ''
  } finally {
    loading.value = false
  }
}

async function verifyIdentity() {
  if (!verifyCode.value) return
  verifyingIdentity.value = true
  verifyError.value = ''
  try {
    const res = await authApi.setupTotp({ code: verifyCode.value })
    if (res.data.status !== 'ok') {
      verifyError.value = res.data.message || '验证失败'
      return
    }
    newSecret.value = res.data.data?.secret || ''
    step.value = 'setup'
  } catch {
    verifyError.value = '验证失败'
  } finally {
    verifyingIdentity.value = false
  }
}

async function confirmSetup() {
  if (!code.value || code.value.length < 6) return
  verifying.value = true
  codeError.value = ''
  try {
    const res = await authApi.setupTotp({
      secret: newSecret.value,
      code: code.value,
    })
    if (res.data.status !== 'ok') {
      codeError.value = res.data.message || tm('system_group.system.dashboard.totp.rotateError')
      return
    }
    const recoveryCode = String(res.data.data?.recovery_code || '')
    const recoveryCodeHash = String(res.data.data?.recovery_code_hash || '')
    const secret = newSecret.value
    resetState()
    emit('setupComplete', {
      secret,
      recoveryCode,
      recoveryCodeHash,
    })
    emit('update:modelValue', false)
  } catch {
    codeError.value = tm('system_group.system.dashboard.totp.rotateError')
  } finally {
    verifying.value = false
  }
}
</script>

<style scoped>
.totp-dialog-subtitle {
  font-size: 0.9rem;
  color: rgba(var(--v-theme-on-surface), 0.68);
}

.totp-new-secret-wrap {
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

.totp-code-input {
  max-width: 240px;
  margin: 0 auto;
}
</style>
