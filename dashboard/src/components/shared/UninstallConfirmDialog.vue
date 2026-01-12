<template>
  <v-dialog 
    v-model="show" 
    max-width="500" 
    @click:outside="handleCancel"
    @keydown.esc="handleCancel"
  >
    <v-card>
      <v-card-title class="text-h5">
        {{ tm('dialogs.uninstall.title') }}
      </v-card-title>
      
      <v-card-text>
        <div class="mb-4">
          {{ tm('dialogs.uninstall.message') }}
        </div>
        
        <v-divider class="my-4"></v-divider>
        
        <div class="text-subtitle-2 mb-3">{{ t('core.common.actions') }}:</div>
        
        <v-checkbox
          v-model="deleteConfig"
          :label="tm('dialogs.uninstall.deleteConfig')"
          color="warning"
          hide-details
          class="mb-2"
        >
          <template v-slot:append>
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-icon v-bind="props" size="small" color="grey">mdi-information-outline</v-icon>
              </template>
              <span>{{ tm('dialogs.uninstall.configHint') }}</span>
            </v-tooltip>
          </template>
        </v-checkbox>
        
        <v-checkbox
          v-model="deleteData"
          :label="tm('dialogs.uninstall.deleteData')"
          color="error"
          hide-details
        >
          <template v-slot:append>
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-icon v-bind="props" size="small" color="grey">mdi-information-outline</v-icon>
              </template>
              <span>{{ tm('dialogs.uninstall.dataHint') }}</span>
            </v-tooltip>
          </template>
        </v-checkbox>
        
        <v-alert
          v-if="deleteConfig || deleteData"
          type="warning"
          variant="tonal"
          density="compact"
          class="mt-4"
        >
          <template v-slot:prepend>
            <v-icon>mdi-alert</v-icon>
          </template>
          {{ t('messages.validation.operation_cannot_be_undone') }}
        </v-alert>
      </v-card-text>
      
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn
          color="grey"
          variant="text"
          @click="handleCancel"
        >
          {{ t('core.common.cancel') }}
        </v-btn>
        <v-btn
          color="error"
          variant="elevated"
          @click="handleConfirm"
        >
          {{ t('core.common.confirm') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['update:modelValue', 'confirm', 'cancel']);

const { t } = useI18n();
const { tm } = useModuleI18n('features/extension');

const show = ref(props.modelValue);
const deleteConfig = ref(false);
const deleteData = ref(false);

watch(() => props.modelValue, (val) => {
  show.value = val;
  if (val) {
    // 重置选项
    deleteConfig.value = false;
    deleteData.value = false;
  }
});

watch(show, (val) => {
  emit('update:modelValue', val);
});

const handleConfirm = () => {
  emit('confirm', {
    deleteConfig: deleteConfig.value,
    deleteData: deleteData.value,
  });
  show.value = false;
};

const handleCancel = () => {
  emit('cancel');
  show.value = false;
};
</script>
