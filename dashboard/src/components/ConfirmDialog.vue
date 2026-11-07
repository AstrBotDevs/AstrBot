<template>
  <v-dialog v-model="isOpen" max-width="400">
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ title }}</v-card-title>
      <v-card-text>
      {{ message }}
      <v-checkbox
        v-if="checkboxOptions"
        v-model="checkboxChecked"
        :label="checkboxOptions.label"
        :hint="checkboxOptions.hint"
        persistent-hint
        density="compact"
        class="mt-2"
      ></v-checkbox>
    </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="gray" variant="text" @click="handleCancel">{{ t('core.common.dialog.cancelButton') }}</v-btn>
        <v-btn color="red" variant="tonal" @click="handleConfirm">{{ t('core.common.dialog.confirmButton') }}</v-btn>
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
const checkboxOptions = ref(null);
const checkboxChecked = ref(false);
let resolvePromise = null; // ✅ 确保 Promise 句柄可用

const open = (options) => {
  title.value = options.title || t('core.common.dialog.confirmTitle');
  message.value = options.message || t('core.common.dialog.confirmMessage');
  checkboxOptions.value = options.checkbox || null;
  checkboxChecked.value = false;
  isOpen.value = true;

  return new Promise((resolve) => {
    resolvePromise = resolve; // ✅ 赋值 Promise 解析方法
  });
};

const handleConfirm = () => {
  isOpen.value = false;
  if (resolvePromise) {
    // With a checkbox the caller needs the checked state back as well.
    resolvePromise(
      checkboxOptions.value
        ? { confirmed: true, checked: checkboxChecked.value }
        : true
    );
    resolvePromise = null;
  }
};

const handleCancel = () => {
  isOpen.value = false;
  if (resolvePromise) {
    resolvePromise(
      checkboxOptions.value
        ? { confirmed: false, checked: false }
        : false
    );
    resolvePromise = null;
  }
};

defineExpose({ open }); // ✅ 确保 `confirmPlugin.ts` 可以访问 `open`
</script>
