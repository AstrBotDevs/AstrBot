<template>
  <v-dialog
    :model-value="modelValue"
    max-width="520"
    @update:model-value="onVisibilityChange"
    @click:outside="onCancel"
  >
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        {{ tm('system_group.system.dashboard.totp.rotateRecoveryTitle') }}
        <v-spacer></v-spacer>
        <v-btn icon variant="text" size="small" @click="onCancel">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-divider></v-divider>
      <v-card-text class="pa-4">
        <div class="totp-dialog-subtitle mb-3">
          {{ tm('system_group.system.dashboard.totp.rotateRecoverySubtitle') }}
        </div>
        <v-text-field
          v-model="code"
          :label="tm('system_group.system.dashboard.totp.rotateRecoveryCode')"
          variant="outlined"
          density="compact"
          class="totp-code-input"
          maxlength="6"
          :error-messages="codeError"
          :loading="verifying"
          hide-details="auto"
          prepend-inner-icon="mdi-shield-key"
          @keyup.enter="confirmRotate"
        ></v-text-field>
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
            @click="confirmRotate"
          >
            {{ tm('system_group.system.dashboard.totp.rotateRecoveryConfirm') }}
          </v-btn>
        </div>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import axios from "@/utils/request";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  configRoot: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(["update:modelValue", "rotated"]);
const { tm } = useModuleI18n("features/config-metadata");

const code = ref("");
const codeError = ref("");
const verifying = ref(false);

const totpSecret = computed(() => props.configRoot?.dashboard?.totp?.secret || "");

function resetState() {
  code.value = "";
  codeError.value = "";
  verifying.value = false;
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

async function confirmRotate() {
  if (!totpSecret.value) {
    codeError.value = tm("system_group.system.dashboard.totp.rotateRecoveryMissingSecret");
    return;
  }
  if (!code.value || code.value.length < 6) {
    return;
  }
  verifying.value = true;
  codeError.value = "";
  try {
    const res = await axios.post("/api/auth/totp/verify-setup", {
      secret: totpSecret.value,
      code: code.value,
    });
    if (res.data.status !== "ok") {
      codeError.value = res.data.message || tm("system_group.system.dashboard.totp.rotateError");
      return;
    }
    emit("rotated", {
      recoveryCode: String(res.data.data?.recovery_code || ""),
      recoveryCodeHash: String(res.data.data?.recovery_code_hash || ""),
    });
    resetState();
    emit("update:modelValue", false);
  } catch {
    codeError.value = tm("system_group.system.dashboard.totp.rotateError");
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
