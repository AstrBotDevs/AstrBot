<script setup lang="ts">
import { useModuleI18n } from "@/i18n/composables";

const { tm: t } = useModuleI18n("features/auth");

const props = defineProps<{
  token: string;
  loading: boolean;
}>();

const emit = defineEmits<{
  (e: "update:token", value: string): void;
  (e: "submit"): void;
  (e: "back"): void;
}>();

function onSubmit() {
  emit("submit");
}
</script>

<template>
  <div class="account-stage-header">
    <div>
      <div class="account-stage-user">{{ t("temporaryToken.title") }}</div>
      <div class="temporary-token-subtitle">
        {{ t("temporaryToken.subtitle") }}
      </div>
    </div>
    <v-btn
      variant="text"
      size="small"
      icon="mdi-arrow-left"
      :disabled="props.loading"
      @click="emit('back')"
    >
      <v-tooltip activator="parent" location="top">
        {{ t("temporaryToken.backToLogin") }}
      </v-tooltip>
    </v-btn>
  </div>

  <v-text-field
    :model-value="props.token"
    :label="t('temporaryToken.token')"
    class="mt-4 pwd-input"
    required
    variant="outlined"
    hide-details="auto"
    type="password"
    prepend-inner-icon="mdi-key-variant"
    :disabled="props.loading"
    @update:model-value="(value: string) => emit('update:token', value)"
    @keyup.enter="onSubmit"
  ></v-text-field>

  <v-btn
    color="secondary"
    block
    class="login-btn mt-8"
    variant="flat"
    size="large"
    :loading="props.loading"
    :disabled="props.loading || !props.token"
    @click="onSubmit"
  >
    <span class="login-btn-text">{{ t("temporaryToken.submit") }}</span>
  </v-btn>
</template>
