<template>
  <v-dialog
    :model-value="modelValue"
    max-width="520"
    @update:model-value="onVisibilityChange"
  >
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        {{ tm('system_group.system.dashboard.totp.disableTitle') }}
        <v-spacer></v-spacer>
        <v-btn icon variant="text" size="small" @click="onCancel">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text class="pa-4">
        <template v-if="showRecovery">
          <div class="totp-dialog-subtitle mb-3">
            {{ tm('system_group.system.dashboard.totp.disableRecoverySubtitle') }}
          </div>
          <v-text-field
            v-model="recoveryCode"
            :label="tm('system_group.system.dashboard.totp.disableRecoveryCode')"
            variant="outlined"
            density="compact"
            class="totp-code-input"
            :error-messages="errorMsg"
            :loading="verifying"
            hide-details="auto"
            prepend-inner-icon="mdi-key-variant"
            @keyup.enter="confirmDisable"
          ></v-text-field>
          <div class="d-flex justify-end ga-2 mt-4">
            <v-btn
              variant="text"
              :disabled="verifying"
              @click="showRecovery = false"
            >
              {{ tm('system_group.system.dashboard.totp.disableUseCode') }}
            </v-btn>
            <v-btn
              color="error"
              variant="tonal"
              :loading="verifying"
              :disabled="!isValidRecoveryCode"
              @click="confirmDisable"
            >
              {{ tm('system_group.system.dashboard.totp.disableConfirm') }}
            </v-btn>
          </div>
        </template>
        <template v-else>
          <div class="totp-dialog-subtitle mb-3">
            {{ tm('system_group.system.dashboard.totp.disableSubtitle') }}
          </div>
          <v-text-field
            v-model="code"
            :label="tm('system_group.system.dashboard.totp.disableCode')"
            variant="outlined"
            density="compact"
            class="totp-code-input"
            maxlength="6"
            :error-messages="errorMsg"
            :loading="verifying"
            hide-details="auto"
            prepend-inner-icon="mdi-shield-key"
            @keyup.enter="confirmDisable"
          ></v-text-field>
          <div class="d-flex justify-end ga-2 mt-4">
            <v-btn
              variant="text"
              :disabled="verifying"
              @click="showRecovery = true"
            >
              {{ tm('system_group.system.dashboard.totp.disableUseRecovery') }}
            </v-btn>
            <v-btn
              color="error"
              variant="tonal"
              :loading="verifying"
              :disabled="!code || code.length < 6"
              @click="confirmDisable"
            >
              {{ tm('system_group.system.dashboard.totp.disableConfirm') }}
            </v-btn>
          </div>
        </template>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import axios from "@/utils/request";

const emit = defineEmits(["update:modelValue", "disableCompleted"]);
const { tm } = useModuleI18n("features/config-metadata");

const code = ref("");
const recoveryCode = ref("");
const showRecovery = ref(false);
const verifying = ref(false);
const errorMsg = ref("");

const isValidRecoveryCode = computed(() => {
  if (!recoveryCode.value) return false;
  const normalized = recoveryCode.value.replace(/[^A-Za-z0-9]/g, "");
  return normalized.length === 32;
});

function resetState() {
  code.value = "";
  recoveryCode.value = "";
  showRecovery.value = false;
  verifying.value = false;
  errorMsg.value = "";
}

function onVisibilityChange(val) {
  if (!val) {
    resetState();
  }
  emit("update:modelValue", val);
}

function onCancel() {
  resetState();
  emit("update:modelValue", false);
}

async function confirmDisable() {
  const inputCode = showRecovery.value ? recoveryCode.value : code.value;
  if (!inputCode) return;
  verifying.value = true;
  errorMsg.value = "";
  try {
    const res = await axios.post("/api/auth/totp/disable", { code: inputCode });
    if (res.data.status !== "ok") {
      errorMsg.value = res.data.message || tm("system_group.system.dashboard.totp.disableError");
      return;
    }
    resetState();
    emit("disableCompleted");
    emit("update:modelValue", false);
  } catch (error) {
    errorMsg.value = String(error || "") || tm("system_group.system.dashboard.totp.disableError");
  } finally {
    verifying.value = false;
  }
}
</script>

<style scoped>
.totp-dialog-subtitle {
  font-size: 0.9rem;
  color: rgba(var(--v-theme-on-surface), 0.68);
}

.totp-code-input {
  max-width: 240px;
  margin: 0 auto;
}
</style>
