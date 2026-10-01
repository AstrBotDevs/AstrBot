<script setup>
import { computed, ref, watch } from 'vue';
import { useI18n } from '@/i18n/composables';
import { useModuleI18n } from '@/i18n/composables';
import AstrBotCoreConfigWrapper from '@/components/config/AstrBotCoreConfigWrapper.vue';
import { configProfileApi } from '@/api/v1';

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  configId: {
    type: String,
    default: '',
  },
  configName: {
    type: String,
    default: '',
  },
});
const emit = defineEmits(['update:modelValue']);

const { t } = useI18n();
const { tm } = useModuleI18n('features/config');

const open = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

const loading = ref(false);
const saving = ref(false);
const loadFailed = ref(false);
const configData = ref(null);
const configMetadata = ref(null);
const snackbar = ref(false);
const snackbarText = ref('');
const snackbarColor = ref('success');

watch(
  [open, () => props.configId],
  async ([isOpen, id]) => {
    if (!isOpen || !id) return;
    loading.value = true;
    loadFailed.value = false;
    configData.value = null;
    configMetadata.value = null;
    try {
      const res = await configProfileApi.get(id);
      configData.value = res.data.data.config;
      configMetadata.value = res.data.data.metadata;
    } catch {
      loadFailed.value = true;
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

async function save() {
  if (!configData.value || saving.value) return;
  saving.value = true;
  try {
    const res = await configProfileApi.update(
      props.configId,
      JSON.parse(JSON.stringify(configData.value)),
    );
    const ok = res.data?.status === 'ok';
    snackbarText.value = res.data?.message || tm(ok ? 'messages.saveSuccess' : 'messages.saveError');
    snackbarColor.value = ok ? 'success' : 'error';
  } catch {
    snackbarText.value = tm('messages.saveError');
    snackbarColor.value = 'error';
  } finally {
    saving.value = false;
    snackbar.value = true;
  }
}
</script>

<template>
  <v-navigation-drawer
    v-model="open"
    location="right"
    temporary
    :width="760"
    class="config-profile-drawer"
  >
    <div class="config-profile-drawer__layout">
      <div class="config-profile-drawer__header">
        <div class="config-profile-drawer__title text-h3">
          {{ t('core.shared.configProfileDrawer.title') }}
          <span v-if="configName" class="config-profile-drawer__name">{{ configName }}</span>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" @click="open = false" />
      </div>

      <div class="config-profile-drawer__content">
        <div v-if="loading" class="d-flex justify-center py-8">
          <v-progress-circular indeterminate color="primary" />
        </div>
        <div v-else-if="loadFailed" class="text-center py-8 text-grey">
          <v-icon>mdi-information-outline</v-icon>
          <p class="mt-2">{{ t('core.shared.configProfileDrawer.loadFailed') }}</p>
        </div>
        <AstrBotCoreConfigWrapper
          v-else-if="configData && configMetadata"
          :metadata="configMetadata"
          :config_data="configData"
        />
      </div>

      <div class="config-profile-drawer__footer">
        <v-btn variant="text" @click="open = false">
          {{ t('core.shared.configProfileDrawer.close') }}
        </v-btn>
        <v-btn
          color="primary"
          variant="tonal"
          :loading="saving"
          :disabled="!configData || loading || loadFailed"
          @click="save"
        >
          {{ tm('actions.save') }}
        </v-btn>
      </div>
    </div>

    <v-snackbar v-model="snackbar" :color="snackbarColor" :timeout="2500" location="bottom right">
      {{ snackbarText }}
    </v-snackbar>
  </v-navigation-drawer>
</template>

<style scoped>
.config-profile-drawer {
  max-width: 92vw;
}

.config-profile-drawer__layout {
  display: flex;
  height: 100%;
  flex-direction: column;
}

.config-profile-drawer__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px 12px 0 24px;
}

.config-profile-drawer__title {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.config-profile-drawer__name {
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 14px;
  font-weight: 500;
}

.config-profile-drawer__content {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 8px 16px 16px;
}

.config-profile-drawer__footer {
  display: flex;
  flex: 0 0 auto;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 16px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
</style>
