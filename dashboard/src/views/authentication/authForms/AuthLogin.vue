<script setup lang="ts">
import axios from "axios";
import { onMounted, ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useModuleI18n } from "@/i18n/composables";
import AuthStageAccount from "./stages/AuthStageAccount.vue";
import AuthStageTotp from "./stages/AuthStageTotp.vue";
import AuthStageRecovery from "./stages/AuthStageRecovery.vue";
import AuthStageTemporaryToken from "./stages/AuthStageTemporaryToken.vue";

const { tm: t } = useModuleI18n("features/auth");
const authStore = useAuthStore();

const username = ref("");
const password = ref("");
const totpCode = ref("");
const trustTotpDevice = ref(false);
const recoveryCode = ref("");
const temporaryToken = ref("");
const temporaryTokenLoginEnabled = ref(false);
const loading = ref(false);
const apiError = ref("");
const stage = ref<"account" | "totp" | "recovery" | "temporary-token">(
  "account",
);

function syncReturnUrl() {
  // @ts-ignore
  authStore.returnUrl = new URLSearchParams(window.location.search).get(
    "redirect",
  );
}

function resetTotpStage() {
  totpCode.value = "";
  trustTotpDevice.value = false;
}

function goToAccountStage() {
  stage.value = "account";
  apiError.value = "";
  resetTotpStage();
  temporaryToken.value = "";
}

function goToTotpStage() {
  stage.value = "totp";
  apiError.value = "";
}

function goToRecoveryStage() {
  stage.value = "recovery";
  apiError.value = "";
  recoveryCode.value = "";
}

function goToTemporaryTokenStage() {
  stage.value = "temporary-token";
  apiError.value = "";
  temporaryToken.value = "";
}

async function submitAccountStage() {
  if (!username.value || !password.value) {
    return;
  }
  loading.value = true;
  apiError.value = "";
  try {
    syncReturnUrl();
    const res = await authStore.login(username.value, password.value);
    if (res === "totp_required") {
      goToTotpStage();
    }
  } catch (err) {
    apiError.value = String(err || "") || "Login failed";
  } finally {
    loading.value = false;
  }
}

async function submitTotpStage() {
  if (!totpCode.value) {
    return;
  }
  loading.value = true;
  apiError.value = "";
  try {
    await authStore.login(
      username.value,
      password.value,
      totpCode.value,
      trustTotpDevice.value,
    );
  } catch (err) {
    apiError.value = String(err || "") || "Verification failed";
  } finally {
    loading.value = false;
  }
}

async function submitTemporaryTokenStage() {
  const token = temporaryToken.value.trim();
  if (!token) {
    return;
  }
  loading.value = true;
  apiError.value = "";
  try {
    syncReturnUrl();
    await authStore.loginWithTemporaryToken(token);
  } catch (err) {
    apiError.value = String(err || "") || "Temporary token login failed";
  } finally {
    loading.value = false;
  }
}

async function loadTemporaryTokenLoginStatus() {
  try {
    const res = await axios.get("/api/auth/setup-status");
    temporaryTokenLoginEnabled.value =
      !!res.data?.data?.temporary_login_token_enabled;
  } catch {
    temporaryTokenLoginEnabled.value = false;
  }
}

onMounted(() => {
  void loadTemporaryTokenLoginStatus();
});

defineExpose({ stage });

async function submitRecoveryStage() {
  if (!recoveryCode.value) {
    return;
  }
  loading.value = true;
  apiError.value = "";
  try {
    await authStore.login(username.value, password.value, recoveryCode.value);
  } catch (err) {
    apiError.value = String(err || "") || "Recovery login failed";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="mt-4 login-form">
    <template v-if="stage === 'account'">
      <AuthStageAccount
        :username="username"
        :password="password"
        :loading="loading"
        @update:username="(value) => (username = value)"
        @update:password="(value) => (password = value)"
        @submit="submitAccountStage"
      />

      <div v-if="temporaryTokenLoginEnabled" class="temporary-token-link-row">
        <span
          class="temporary-token-login-link"
          role="button"
          tabindex="0"
          @click="goToTemporaryTokenStage"
          @keyup.enter="goToTemporaryTokenStage"
          @keyup.space.prevent="goToTemporaryTokenStage"
        >
          {{ t("temporaryToken.link") }}
        </span>
      </div>
    </template>

    <AuthStageTotp
      v-else-if="stage === 'totp'"
      :username="username"
      :code="totpCode"
      :trust-device="trustTotpDevice"
      :loading="loading"
      @update:code="(value) => (totpCode = value)"
      @update:trust-device="(value) => (trustTotpDevice = value)"
      @submit="submitTotpStage"
      @back="goToAccountStage"
      @use-recovery="goToRecoveryStage"
    />

    <AuthStageTemporaryToken
      v-else-if="stage === 'temporary-token'"
      :token="temporaryToken"
      :loading="loading"
      @update:token="(value) => (temporaryToken = value)"
      @submit="submitTemporaryTokenStage"
      @back="goToAccountStage"
    />

    <AuthStageRecovery
      v-else
      :code="recoveryCode"
      :loading="loading"
      @update:code="(value) => (recoveryCode = value)"
      @submit="submitRecoveryStage"
      @back="goToTotpStage"
    />

    <div v-if="apiError" class="mt-4 error-container">
      <v-alert
        color="error"
        variant="tonal"
        icon="mdi-alert-circle"
        border="start"
      >
        {{ apiError }}
      </v-alert>
    </div>
  </div>
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

  .error-container {
    .v-alert {
      border-left-width: 4px !important;
    }
  }

  .account-stage-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 0 4px;
  }

  .account-stage-user {
    font-size: 0.95rem;
    font-weight: 600;
    color: rgba(var(--v-theme-on-surface), 0.85);
  }

  .temporary-token-subtitle {
    margin-top: 4px;
    font-size: 0.82rem;
    color: rgba(var(--v-theme-on-surface), 0.62);
    line-height: 1.4;
  }

  .temporary-token-link-row {
    margin-top: 14px;
    text-align: center;
  }

  .temporary-token-login-link {
    color: rgb(var(--v-theme-primary));
    cursor: pointer;
    font-size: 0.9rem;
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .temporary-token-login-link:focus-visible {
    border-radius: 4px;
    outline: 2px solid rgba(var(--v-theme-primary), 0.35);
    outline-offset: 3px;
  }
}
</style>
