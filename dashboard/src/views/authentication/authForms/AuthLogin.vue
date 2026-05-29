<script setup lang="ts">
import { ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { Form } from 'vee-validate';
import { useModuleI18n } from '@/i18n/composables';

const { tm: t } = useModuleI18n('features/auth');

const valid = ref(false);
const show1 = ref(false);
const password = ref('');
const username = ref('');
const loading = ref(false);

/* eslint-disable @typescript-eslint/no-explicit-any */
async function validate(values: any, { setErrors }: any) {
  loading.value = true;

  const authStore = useAuthStore();
  // @ts-ignore
  authStore.returnUrl = new URLSearchParams(window.location.search).get('redirect');
  return authStore.login(username.value, password.value).then((res) => {
    console.log(res);
    loading.value = false;
  }).catch((err) => {
    setErrors({ apiError: err });
    loading.value = false;
  });
}

// Forgot password flow
const showForgotDialog = ref(false);
const showConfirmDialog = ref(false);
const forgotCode = ref('');
const forgotError = ref('');
const forgotLoading = ref(false);
const restartPending = ref(false);
const codeRequested = ref(false);

async function openForgotDialog() {
  forgotCode.value = '';
  forgotError.value = '';
  codeRequested.value = false;
  showForgotDialog.value = true;

  // Request a confirmation code from the backend
  const authStore = useAuthStore();
  try {
    await authStore.forgotPasswordInit();
    codeRequested.value = true;
  } catch (err: any) {
    forgotError.value = err?.response?.data?.message || err?.message || String(err);
  }
}

function closeForgotDialog() {
  showForgotDialog.value = false;
  forgotError.value = '';
  codeRequested.value = false;
}

function submitForgotStep1() {
  forgotError.value = '';
  const trimmedCode = forgotCode.value.trim();
  if (!trimmedCode || trimmedCode.length !== 6) {
    forgotError.value = t('forgotPassword.codeInvalid');
    return;
  }
  forgotCode.value = trimmedCode;
  showForgotDialog.value = false;
  showConfirmDialog.value = true;
}

function closeConfirmDialog() {
  showConfirmDialog.value = false;
  showForgotDialog.value = true;
}

async function confirmReset() {
  forgotLoading.value = true;
  forgotError.value = '';
  const authStore = useAuthStore();
  try {
    await authStore.forgotPassword(forgotCode.value);
    showConfirmDialog.value = false;
    restartPending.value = true;
    pollForRestart();
  } catch (err: any) {
    forgotError.value = err?.response?.data?.message || err?.message || String(err);
  } finally {
    forgotLoading.value = false;
  }
}

async function pollForRestart() {
  let attempts = 0;
  const maxAttempts = 60;
  const interval = 2000;

  while (attempts < maxAttempts) {
    await new Promise((resolve) => setTimeout(resolve, interval));
    attempts++;
    try {
      const res = await fetch('/api/auth/setup-status', { method: 'GET', signal: AbortSignal.timeout(3000) });
      if (!res.ok) throw new Error('Server not ready');
      restartPending.value = false;
      window.location.reload();
      return;
    } catch {
      // Server is still restarting, keep polling
    }
  }
  // Fallback after timeout
  restartPending.value = false;
  window.location.reload();
}

</script>

<template>
  <Form @submit="validate" class="mt-4 login-form" v-slot="{ errors, isSubmitting }">
    <v-text-field v-model="username" :label="t('username')" class="mb-6 input-field" required hide-details="auto"
      variant="outlined" prepend-inner-icon="mdi-account" :disabled="loading || restartPending"></v-text-field>

    <v-text-field v-model="password" :label="t('password')" required variant="outlined" hide-details="auto"
      :append-inner-icon="show1 ? 'mdi-eye' : 'mdi-eye-off'" :type="show1 ? 'text' : 'password'"
      @click:append-inner="show1 = !show1" class="pwd-input" prepend-inner-icon="mdi-lock" :disabled="loading || restartPending"></v-text-field>

    <div class="mt-2 d-flex justify-space-between align-center">
      <small style="color: grey;">{{ t('defaultHint') }}</small>
      <v-btn variant="text" size="small" color="primary" @click="openForgotDialog" :disabled="restartPending">
        {{ t('forgotPassword.label') }}
      </v-btn>
    </div>

    <v-btn color="secondary" :loading="isSubmitting || loading || restartPending" block class="login-btn mt-8" variant="flat" size="large"
      :disabled="valid" type="submit">
      <span class="login-btn-text">{{ restartPending ? t('restarting') : t('login') }}</span>
    </v-btn>

    <div v-if="errors.apiError" class="mt-4 error-container">
      <v-alert color="error" variant="tonal" icon="mdi-alert-circle" border="start">
        {{ errors.apiError }}
      </v-alert>
    </div>
  </Form>

  <!-- Step 1: Confirmation code input -->
  <v-dialog v-model="showForgotDialog" max-width="480" persistent>
    <v-card>
      <v-card-title class="text-h6">{{ t('forgotPassword.title') }}</v-card-title>
      <v-card-text>
        <p class="mb-4">{{ t('forgotPassword.codeHint') }}</p>
        <v-text-field
          v-model="forgotCode"
          :label="t('forgotPassword.codeLabel')"
          variant="outlined"
          hide-details="auto"
          maxlength="6"
          :disabled="!codeRequested"
          @keyup.enter="submitForgotStep1"
        ></v-text-field>
        <div v-if="forgotError" class="mt-2">
          <v-alert color="error" variant="tonal" density="compact" icon="mdi-alert-circle">
            {{ forgotError }}
          </v-alert>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="closeForgotDialog">{{ t('cancel') }}</v-btn>
        <v-btn color="primary" variant="flat" @click="submitForgotStep1" :disabled="!codeRequested">{{ t('next') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Step 2: Final confirmation + warning -->
  <v-dialog v-model="showConfirmDialog" max-width="480" persistent>
    <v-card>
      <v-card-title class="text-h6 text-warning">{{ t('forgotPassword.confirmTitle') }}</v-card-title>
      <v-card-text>
        <v-alert color="warning" variant="tonal" icon="mdi-alert" class="mb-4">
          <div class="font-weight-bold mb-1">{{ t('forgotPassword.warningTitle') }}</div>
          <div>{{ t('forgotPassword.warningText') }}</div>
        </v-alert>
        <p>{{ t('forgotPassword.restartHint') }}</p>
        <div v-if="forgotError" class="mt-2">
          <v-alert color="error" variant="tonal" density="compact" icon="mdi-alert-circle">
            {{ forgotError }}
          </v-alert>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="closeConfirmDialog">{{ t('cancel') }}</v-btn>
        <v-btn color="error" variant="flat" :loading="forgotLoading" @click="confirmReset">
          {{ t('forgotPassword.confirmReset') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Restart pending overlay -->
  <v-overlay v-model="restartPending" class="align-center justify-center" persistent>
    <v-card color="surface" class="pa-6 text-center" max-width="400">
      <v-progress-circular indeterminate color="primary" size="64" class="mb-4"></v-progress-circular>
      <div class="text-h6 mb-2">{{ t('restartingTitle') }}</div>
      <div class="text-body-2 text-medium-emphasis">{{ t('restartingHint') }}</div>
    </v-card>
  </v-overlay>
</template>

<style lang="scss">
.login-form {
  .v-text-field .v-field--active input {
    font-weight: 500;
  }

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

  .pwd-input {
    position: relative;

    .v-input__append {
      position: absolute;
      right: 10px;
      top: 50%;
      transform: translateY(-50%);
      opacity: 0.7;

      &:hover {
        opacity: 1;
      }
    }
  }

  .login-btn {
    margin-top: 12px;
    height: 48px;
    transition: all 0.3s ease;
    letter-spacing: 0.5px;
    border-radius: 8px !important;

    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 5px 15px rgba(94, 53, 177, 0.2) !important;
    }

    .login-btn-text {
      font-size: 1.05rem;
      font-weight: 500;
    }
  }

  .hint-text {
    color: var(--v-theme-secondaryText);
    padding-left: 5px;
  }

  .error-container {
    .v-alert {
      border-left-width: 4px !important;
    }
  }
}

.custom-divider {
  border-color: rgba(0, 0, 0, 0.08) !important;
}
</style>
