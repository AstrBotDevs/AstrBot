<template>
  <v-dialog
    :model-value="modelValue"
    max-width="460"
    persistent
    @update:model-value="onVisibilityChange"
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
        {{ t('features.authorization.stepUpTitle') }}
        <v-spacer></v-spacer>
        <v-btn
          icon
          variant="text"
          size="small"
          :disabled="loading"
          @click="cancel"
        >
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text class="pa-4">
        <div class="step-up-dialog-subtitle mb-3">
          {{ t('features.authorization.stepUpText') }}
        </div>
        <v-text-field
          v-model="password"
          class="mt-4"
          type="password"
          autocomplete="current-password"
          :label="t('features.authorization.password')"
          :disabled="loading"
          :error-messages="errorMessage"
          autofocus
          @keyup.enter="confirm"
        />
        <v-text-field
          v-model="code"
          :label="t('features.authorization.totpCode')"
          autocomplete="one-time-code"
          inputmode="numeric"
          :disabled="loading"
          :error-messages="errorMessage ? [] : undefined"
          @keyup.enter="confirm"
        />
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer></v-spacer>
        <v-btn variant="text" :disabled="loading" @click="cancel">
          {{ t('features.authorization.cancel') }}
        </v-btn>
        <v-btn
          color="primary"
          :loading="loading"
          :disabled="!password && !code"
          @click="confirm"
        >
          {{ t('features.authorization.verify') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n } from '@/i18n/composables';

const props = defineProps<{
  modelValue: boolean;
  loading?: boolean;
  errorMessage?: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  confirm: [credentials: { password?: string; code?: string }];
  cancel: [];
}>();

const { t } = useI18n();
const password = ref('');
const code = ref('');

function clearCredentials() {
  password.value = '';
  code.value = '';
}

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) clearCredentials();
  },
);

function onVisibilityChange(value: boolean) {
  if (!value) {
    cancel();
  }
}

function cancel() {
  clearCredentials();
  emit('cancel');
  emit('update:modelValue', false);
}

function confirm() {
  if (!password.value && !code.value) return;
  emit('confirm', {
    password: password.value || undefined,
    code: code.value || undefined,
  });
  clearCredentials();
}
</script>

<style scoped>
.step-up-dialog-subtitle {
  font-size: 0.9rem;
  color: rgba(var(--v-theme-on-surface), 0.68);
}
</style>
