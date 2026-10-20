<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables';

const { tm: t } = useModuleI18n('features/auth');

const props = defineProps<{
  code: string;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:code', value: string): void;
  (e: 'submit'): void;
  (e: 'back'): void;
}>();

function normalizeRecoveryCode(code: string): string {
  return code.toUpperCase().replace(/[^A-Z2-7]/g, '').slice(0, 32);
}

function formatRecoveryCode(code: string): string {
  const normalized = normalizeRecoveryCode(code);
  const groups = normalized.match(/.{1,8}/g);
  return groups ? groups.join('-') : '';
}

function onCodeInput(raw: string) {
  emit('update:code', formatRecoveryCode(raw));
}

function isRecoveryCodeComplete(code: string): boolean {
  return normalizeRecoveryCode(code).length === 32;
}

function onSubmit() {
  emit('submit');
}
</script>

<template>
  <div class="account-stage-header">
    <div class="account-stage-user">{{ t('recovery.title') }}</div>
    <v-btn variant="text" size="small" color="primary" :disabled="props.loading" @click="emit('back')">
      {{ t('setup.totp.back') }}
    </v-btn>
  </div>

  <div class="recovery-code-section mt-2">
    <v-alert color="warning" variant="tonal" icon="mdi-alert" class="mb-4" density="compact">
      {{ t('recovery.totpDisableWarning') }}
    </v-alert>

    <v-text-field
      :model-value="props.code"
      :label="t('recovery.code')"
      class="mt-6 mb-2 input-field"
      required
      hide-details="auto"
      variant="outlined"
      :disabled="props.loading"
      maxlength="35"
      prepend-inner-icon="mdi-key-variant"
      @update:model-value="(value: string) => onCodeInput(value)"
      @keyup.enter="onSubmit"
    ></v-text-field>
  </div>

  <v-btn
    color="secondary"
    block
    class="login-btn mt-4"
    variant="flat"
    size="large"
    :loading="props.loading"
    :disabled="props.loading || !isRecoveryCodeComplete(props.code)"
    @click="onSubmit"
  >
    <span class="login-btn-text">{{ t('recovery.submit') }}</span>
  </v-btn>
</template>
