<script setup lang="ts">
import { ref } from 'vue';
import { Form } from 'vee-validate';
import { useModuleI18n } from '@/i18n/composables';
import { useAuthStore } from '@/stores/auth';

const { tm: t } = useModuleI18n('features/auth');

const username = ref('astrbot');
const password = ref('');
const confirmPassword = ref('');
const showPassword = ref(false);
const showConfirmPassword = ref(false);
const loading = ref(false);

const usernameRules = [
  (value: string) => !!value || t('setup.validation.usernameRequired'),
  (value: string) => (value && value.length >= 3) || t('setup.validation.usernameMinLength'),
];
const passwordRules = [
  (value: string) => !!value || t('setup.validation.passwordRequired'),
  (value: string) => (value && value.length >= 8) || t('setup.validation.passwordMinLength'),
  (value: string) => /[A-Z]/.test(value) || t('setup.validation.passwordUppercase'),
  (value: string) => /[a-z]/.test(value) || t('setup.validation.passwordLowercase'),
  (value: string) => /\d/.test(value) || t('setup.validation.passwordDigit'),
];
const confirmPasswordRules = [
  (value: string) => !!value || t('setup.validation.confirmPasswordRequired'),
  (value: string) => value === password.value || t('setup.validation.passwordMatch'),
];

/* eslint-disable @typescript-eslint/no-explicit-any */
async function validate(values: any, { setErrors }: any) {
  loading.value = true;
  const authStore = useAuthStore();
  return authStore.setup(username.value, password.value, confirmPassword.value).catch((err) => {
    setErrors({ apiError: err });
  }).finally(() => {
    loading.value = false;
  });
}
</script>

<template>
  <Form @submit="validate" class="mt-4 setup-form" v-slot="{ errors, isSubmitting }">
    <v-text-field v-model="username" :label="t('setup.username')" class="mb-5 input-field" required hide-details="auto"
      variant="outlined" prepend-inner-icon="mdi-account-edit" :disabled="loading" :rules="usernameRules"></v-text-field>

    <v-text-field v-model="password" :label="t('setup.password')" required variant="outlined" hide-details="auto"
      :append-inner-icon="showPassword ? 'mdi-eye' : 'mdi-eye-off'" :type="showPassword ? 'text' : 'password'"
      @click:append-inner="showPassword = !showPassword" class="pwd-input mb-5" prepend-inner-icon="mdi-lock-plus"
      :disabled="loading" :rules="passwordRules"></v-text-field>

    <v-text-field v-model="confirmPassword" :label="t('setup.confirmPassword')" required variant="outlined"
      hide-details="auto" :append-inner-icon="showConfirmPassword ? 'mdi-eye' : 'mdi-eye-off'"
      :type="showConfirmPassword ? 'text' : 'password'" @click:append-inner="showConfirmPassword = !showConfirmPassword"
      class="pwd-input" prepend-inner-icon="mdi-lock-check" :disabled="loading" :rules="confirmPasswordRules"></v-text-field>

    <small class="setup-hint">{{ t('setup.passwordHint') }}</small>

    <v-btn color="secondary" :loading="isSubmitting || loading" block class="setup-btn mt-8" variant="flat" size="large"
      type="submit">
      <span class="setup-btn-text">{{ t('setup.submit') }}</span>
    </v-btn>

    <div v-if="errors.apiError" class="mt-4 error-container">
      <v-alert color="error" variant="tonal" icon="mdi-alert-circle" border="start">
        {{ errors.apiError }}
      </v-alert>
    </div>
  </Form>
</template>

<style lang="scss">
.setup-form {
  .input-field,
  .pwd-input {
    .v-field__field {
      padding-top: 5px;
      padding-bottom: 5px;
    }

    .v-field__outline {
      opacity: 0.7;
    }

    &:hover .v-field__outline {
      opacity: 0.9;
    }

    .v-field--focused .v-field__outline {
      opacity: 1;
    }

    .v-field__prepend-inner {
      padding-right: 8px;
      opacity: 0.7;
    }
  }

  .setup-hint {
    display: block;
    margin-top: 8px;
    color: grey;
  }

  .setup-btn {
    height: 48px;
    transition: all 0.3s ease;
    letter-spacing: 0.5px;
    border-radius: 8px !important;

    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 5px 15px rgba(94, 53, 177, 0.2) !important;
    }

    .setup-btn-text {
      font-size: 1.05rem;
      font-weight: 500;
    }
  }

  .error-container {
    .v-alert {
      border-left-width: 4px !important;
    }
  }
}
</style>
