<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables';

const { tm: t } = useModuleI18n('features/auth');

const props = defineProps<{
  username: string;
  code: string;
  trustDevice: boolean;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:code', value: string): void;
  (e: 'update:trustDevice', value: boolean): void;
  (e: 'submit'): void;
  (e: 'back'): void;
  (e: 'useRecovery'): void;
}>();

function onSubmit() {
  emit('submit');
}
</script>

<template>
  <div class="account-stage-header">
    <div class="account-stage-user">{{ props.username }}</div>
    <v-btn variant="text" size="small" color="primary" :disabled="props.loading" @click="emit('back')">
      {{ t('setup.totp.back') }}
    </v-btn>
  </div>

  <div class="mt-2">
    <small style="color: grey;">{{ t('totp.verify') }}</small>
  </div>

  <v-text-field
    :model-value="props.code"
    :label="t('totp.code')"
    class="mt-6 mb-2 input-field"
    required
    hide-details="auto"
    variant="outlined"
    prepend-inner-icon="mdi-shield-key"
    :disabled="props.loading"
    inputmode="numeric"
    @update:model-value="(value: string) => emit('update:code', value)"
    @keyup.enter="onSubmit"
  ></v-text-field>

  <v-checkbox
    :model-value="props.trustDevice"
    :label="t('totp.trustDevice')"
    color="secondary"
    density="comfortable"
    hide-details
    class="mt-1"
    @update:model-value="(value: boolean | null) => emit('update:trustDevice', !!value)"
  ></v-checkbox>

  <div class="text-center mt-2">
    <v-btn variant="text" size="small" color="primary" :disabled="props.loading" @click="emit('useRecovery')">
      {{ t('recovery.useRecoveryCode') }}
    </v-btn>
  </div>

  <v-btn
    color="secondary"
    block
    class="login-btn mt-8"
    variant="flat"
    size="large"
    :loading="props.loading"
    :disabled="props.loading || !props.code"
    @click="onSubmit"
  >
    <span class="login-btn-text">{{ t('totp.verify') }}</span>
  </v-btn>
</template>
