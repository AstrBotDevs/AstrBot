<script setup lang="ts">
import { ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { Form } from "vee-validate";
import { useModuleI18n } from "@/i18n/composables";

const { tm: t } = useModuleI18n("features/auth");

const show1 = ref(false);
const password = ref("");
const username = ref("");
const loading = ref(false);

/* eslint-disable @typescript-eslint/no-explicit-any */
async function validate(_values: any, { setErrors }: any) {
  loading.value = true;

  const authStore = useAuthStore();
  const redirectParam = new URLSearchParams(window.location.search).get(
    "redirect",
  );
  // 将 string | null 显式断言为与 store 兼容的类型，避免因 store 初始状态推断不完整而导致的编译错误
  authStore.returnUrl = redirectParam as unknown as string | null;
  return authStore
    .login(username.value, password.value)
    .then(() => {
      loading.value = false;
    })
    .catch((err) => {
      setErrors({ apiError: err });
      loading.value = false;
    });
}
</script>

<template>
  <Form
    v-slot="{ errors, isSubmitting }"
    class="mt-4 login-form"
    @submit="validate"
  >
    <v-text-field
      v-model="username"
      :label="t('username')"
      class="mb-6 input-field"
      required
      hide-details="auto"
      variant="outlined"
      prepend-inner-icon="mdi-account"
      :disabled="loading"
    />

    <v-text-field
      v-model="password"
      :label="t('password')"
      required
      variant="outlined"
      hide-details="auto"
      :append-icon="show1 ? 'mdi-eye' : 'mdi-eye-off'"
      :type="show1 ? 'text' : 'password'"
      class="pwd-input"
      prepend-inner-icon="mdi-lock"
      :disabled="loading"
      @click:append="show1 = !show1"
    />

    <div class="mt-2">
      <small style="color: grey">{{ t("defaultHint") }}</small>
    </div>

    <v-btn
      color="secondary"
      :loading="isSubmitting || loading"
      block
      class="login-btn mt-8"
      variant="flat"
      size="large"
      type="submit"
    >
      <span class="login-btn-text">{{ t("login") }}</span>
    </v-btn>

    <div
      v-if="errors.apiError"
      class="mt-4 error-container"
    >
      <v-alert
        color="error"
        variant="tonal"
        icon="mdi-alert-circle"
        border="start"
      >
        {{ errors.apiError }}
      </v-alert>
    </div>
  </Form>
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
