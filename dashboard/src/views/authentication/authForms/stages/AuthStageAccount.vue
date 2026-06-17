<script setup lang="ts">
import { ref } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

const { tm: t } = useModuleI18n('features/auth');

const props = defineProps<{
  username: string;
  password: string;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:username', value: string): void;
  (e: 'update:password', value: string): void;
  (e: 'submit'): void;
}>();

const showPassword = ref(false);

function onSubmit() {
  emit('submit');
}
</script>

<template>
  <v-text-field
    :model-value="props.username"
    :label="t('username')"
    autocomplete="username"
    class="mb-6 input-field"
    required
    hide-details="auto"
    variant="outlined"
    prepend-inner-icon="mdi-account"
    :disabled="props.loading"
    @update:model-value="(value: string) => emit('update:username', value)"
    @keyup.enter="onSubmit"
  ></v-text-field>

  <v-text-field
    :model-value="props.password"
    :label="t('password')"
    autocomplete="current-password"
    required
    variant="outlined"
    hide-details="auto"
    :append-inner-icon="showPassword ? 'mdi-eye' : 'mdi-eye-off'"
    :type="showPassword ? 'text' : 'password'"
    @click:append-inner="showPassword = !showPassword"
    class="pwd-input"
    prepend-inner-icon="mdi-lock"
    :disabled="props.loading"
    @update:model-value="(value: string) => emit('update:password', value)"
    @keyup.enter="onSubmit"
  ></v-text-field>

  <div class="mt-2">
    <small style="color: grey;">{{ t('defaultHint') }}</small>
  </div>

  <v-btn
    color="secondary"
    block
    class="login-btn mt-8"
    variant="flat"
    size="large"
    :loading="props.loading"
    :disabled="props.loading || !props.username || !props.password"
    @click="onSubmit"
  >
    <span class="login-btn-text">{{ t('login') }}</span>
  </v-btn>
</template>
