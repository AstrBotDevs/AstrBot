<template>
  <v-dialog v-model="isOpen" max-width="480" persistent>
    <v-card>
      <v-card-title class="dialog-title d-flex align-center justify-space-between">
        <span>{{ title }}</span>
        <v-btn icon="mdi-close" variant="text" @click="handleClose"></v-btn>
      </v-card-title>
      <v-card-text>
        <div class="message-text">{{ message }}</div>
        <div class="action-hints">
          <span class="hint-item">{{ confirmHint }}</span>
          <span class="hint-item">{{ cancelHint }}</span>
          <span class="hint-item">{{ closeHint }}</span>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="gray" @click="handleCancel">{{ t('core.common.dialog.cancelButton') }}</v-btn>
        <v-btn color="red" @click="handleConfirm" class="confirm-button">{{ t('core.common.dialog.confirmButton') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref } from "vue";
import { useI18n } from '@/i18n/composables';

const { t } = useI18n();

const isOpen = ref(false);
const title = ref("");
const message = ref("");
const confirmHint = ref("");
const cancelHint = ref("");
const closeHint = ref("");
let resolvePromise = null;

const open = (options) => {
  title.value = options.title || t('core.common.dialog.confirmTitle');
  message.value = options.message || t('core.common.dialog.confirmMessage');
  confirmHint.value = options.confirmHint || "";
  cancelHint.value = options.cancelHint || "";
  closeHint.value = options.closeHint || "";
  isOpen.value = true;

  return new Promise((resolve) => {
    resolvePromise = resolve;
  });
};

const handleConfirm = () => {
  isOpen.value = false;
  if (resolvePromise) resolvePromise(true);
};

const handleCancel = () => {
  isOpen.value = false;
  if (resolvePromise) resolvePromise(false);
};

const handleClose = () => {
  isOpen.value = false;
  if (resolvePromise) resolvePromise('close');
};

defineExpose({ open });
</script>


<style scoped>
.message-text {
  margin-bottom: 8px;
  line-height: 1.5;
  font-size: 16px;
  font-weight: 600;
}

.action-hints {
  display: flex;
  gap: 15px;
}

.hint-item {
  color: var(--v-theme-secondaryText, #666);
  font-size: 12px;
  opacity: 0.7;
}

.dialog-title {
  font-size: 20px;
  font-weight: 500;
}

.confirm-button {
  color: rgb(239, 68, 68);
}
</style>
