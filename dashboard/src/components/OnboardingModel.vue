<template>
  <div class="onboarding-model">
    <v-alert v-if="error" type="error" variant="tonal" class="mb-4" role="alert">{{ error }}</v-alert>
    <v-progress-linear v-if="loadingSources || loadingDefault" indeterminate color="primary" />
    <v-autocomplete v-model="choice" :items="choices" :label="t('guide.provider')" variant="outlined"
      :disabled="disabled || loadingModels" hide-details auto-select-first @update:model-value="choose">
      <template #prepend-inner>
        <img v-if="selectedProviderSource" :src="resolveSourceIcon(selectedProviderSource)" width="24" height="24" alt=""
          :class="{ 'provider-icon--monochrome': isMonochromeSourceIcon(selectedProviderSource) }" />
      </template>
    </v-autocomplete>
    <div v-if="!selectedProviderSource" class="model-choices">
      <button v-for="source in availableSourceTypes.filter(s => !s.isSponsor).slice(0, 6)" :key="source.value"
        type="button" :disabled="disabled" @click="choice = `template:${source.value}`; choose(choice)">
        <img v-if="source.icon" :src="source.icon" width="28" height="28" alt=""
          :class="{ 'provider-icon--monochrome': source.isMonochrome }" />
        <span>{{ source.label }}</span>
        <v-icon icon="mdi-chevron-right" size="18" />
      </button>
    </div>
    <v-btn v-if="!loadingSources && !choices.length" variant="text" @click="loadConfig">{{ t('guide.retry') }}</v-btn>
    <fieldset v-if="editableProviderSource" :disabled="disabled || loadingModels" class="model-fields">
      <v-text-field v-if="'key' in editableProviderSource"
        :model-value="Array.isArray(editableProviderSource.key) ? editableProviderSource.key[0] : editableProviderSource.key"
        @update:model-value="editableProviderSource.key = Array.isArray(editableProviderSource.key) ? [$event, ...editableProviderSource.key.slice(1)] : $event"
        label="API Key" :type="showKey ? 'text' : 'password'" autocomplete="off" variant="outlined" hide-details>
        <template #append-inner>
          <v-btn :icon="showKey ? 'mdi-eye-off-outline' : 'mdi-eye-outline'" size="small" variant="text"
            :aria-label="t('guide.toggleKey')" :title="t('guide.toggleKey')" @click="showKey = !showKey" />
        </template>
      </v-text-field>
      <v-text-field v-if="'api_base' in editableProviderSource" v-model="editableProviderSource.api_base"
        label="API Base URL" variant="outlined" hide-details />
      <div class="model-picker">
        <v-combobox v-model="model" :items="modelOptions" :label="t('guide.model')" variant="outlined"
          :return-object="false" hide-details />
        <v-btn variant="tonal" color="primary" :loading="loadingModels" :disabled="disabled"
          prepend-icon="mdi-refresh" @click="fetchAvailableModels">{{ t('guide.fetchModels') }}</v-btn>
      </div>
      <details v-if="advancedSourceConfig && Object.keys(advancedSourceConfig).length" class="model-advanced">
        <summary>{{ tm('providerSources.advancedConfig') }}</summary>
        <AstrBotConfig :iterable="advancedSourceConfig" :metadata="providerSourceSchema" metadata-key="provider" :is-editing="true" />
      </details>
    </fieldset>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { configProfileApi, providerApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { useProviderSources } from '@/composables/useProviderSources';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';

defineProps<{ disabled?: boolean }>();
const emit = defineEmits<{ 'update:busy': [value: boolean] }>();
const { tm } = useModuleI18n('features/provider');
const { tm: t } = useModuleI18n('features/welcome');
const error = ref('');
const choice = ref('');
const model = ref('');
const showKey = ref(false);
const loadingDefault = ref(false);
const {
  availableSourceTypes, displayedProviderSources, selectedProviderSource, editableProviderSource,
  availableModels, loadingSources, loadingModels, isSourceModified, sourceProviders, providers,
  advancedSourceConfig, providerSourceSchema, resolveSourceIcon, isMonochromeSourceIcon, getSourceDisplayName,
  addProviderSource, selectProviderSource, saveProviderSource, fetchAvailableModels,
  buildModelProviderConfig, loadConfig,
} = useProviderSources({ defaultTab: 'chat_completion', tm: (key, params) => tm(key, params as Record<string, string | number>),
  showMessage: (message, color) => { error.value = color === 'error' ? message : ''; } });

const choices = computed(() => [
  ...displayedProviderSources.value.filter(s => !s.isPlaceholder && s.enable !== false)
    .map(s => ({ title: getSourceDisplayName(s), value: `source:${s.id}` })),
  ...availableSourceTypes.value.map(s => ({ title: s.label, value: `template:${s.value}` })),
]);
const modelOptions = computed(() => [...new Set([
  ...sourceProviders.value.map(p => p.model), ...availableModels.value.map(m => m.name),
])]);
const ready = computed(() => !!selectedProviderSource.value && !!String(model.value || '').trim() && !loadingSources.value && !loadingDefault.value && !loadingModels.value);
watch(loadingModels, value => emit('update:busy', value));
watch(loadingSources, async (loading, _, onCleanup) => {
  if (loading || choice.value) return;
  let active = true;
  onCleanup(() => { active = false; loadingDefault.value = false; });
  const existing = providers.value.filter(provider => provider.enable !== false && provider.id && provider.model &&
    displayedProviderSources.value.some(source => !source.isPlaceholder && source.enable !== false && source.id === provider.provider_source_id));
  if (!existing.length) return;
  loadingDefault.value = true;
  try {
    const response = await configProfileApi.get('default');
    if (response.data.status !== 'ok') throw new Error(response.data.message || t('onboard.providerLoadFailed'));
    if (!active || choice.value) return;
    const config = response.data.data?.config as Record<string, any> | undefined;
    const defaultId = config?.agent_runner?.config?.model?.provider_id;
    const provider = defaultId ? existing.find(item => item.id === defaultId) : existing[0];
    if (!provider) return;
    choice.value = `source:${provider.provider_source_id}`;
    choose(choice.value);
    model.value = provider.model;
  } catch (cause: any) {
    if (active && !choice.value) error.value = cause?.response?.data?.message || cause?.message || t('onboard.providerLoadFailed');
  } finally {
    if (active) loadingDefault.value = false;
  }
}, { immediate: true });

function choose(value: string | null) {
  if (!value) return;
  error.value = '';
  if (value.startsWith('source:')) {
    selectProviderSource(displayedProviderSources.value.find(s => s.id === value.slice(7)));
  } else {
    addProviderSource(value.slice(9));
  }
  model.value = sourceProviders.value.find(p => p.enable !== false)?.model || '';
}

async function save(): Promise<string | undefined> {
  if (!ready.value) return;
  error.value = '';
  try {
    if (isSourceModified.value && !await saveProviderSource()) return;
    const name = String(model.value).trim();
    const existing = sourceProviders.value.find(p => p.model === name);
    if (existing?.enable !== false && existing?.id) return existing.id;
    const config = buildModelProviderConfig(name);
    if (!config) return;
    const result = existing
      ? await providerApi.update(existing.id, { ...existing, enable: true })
      : await providerApi.createInSource(String(config.provider_source_id), config);
    if (result.data.status !== 'ok') throw new Error(result.data.message || tm('providerSources.saveError'));
    await loadConfig();
    return existing?.id || config.id;
  } catch (cause: any) {
    error.value = cause?.response?.data?.message || cause?.message || tm('providerSources.saveError');
  }
}

defineExpose({ save, ready });
</script>

<style scoped>
.model-choices { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 20px; }
.model-choices button { display: flex; align-items: center; gap: 12px; min-width: 0; min-height: 68px; padding: 16px; text-align: left; border: 1px solid rgba(var(--v-theme-on-surface), .14); border-radius: 8px; }
.model-choices button:hover, .model-choices button:focus-visible { border-color: rgb(var(--v-theme-primary)); background: rgba(var(--v-theme-primary), .04); }
.model-choices span { flex: 1; overflow-wrap: anywhere; font-weight: 500; }
.model-choices img { flex-shrink: 0; object-fit: contain; }
.model-fields { border: 0; padding: 24px 0 0; margin: 0; min-width: 0; display: grid; gap: 24px; }
.model-picker { display: flex; gap: 12px; align-items: center; min-width: 0; }
.model-picker > :first-child { min-width: 0; }
.model-advanced { border-top: 1px solid rgba(var(--v-theme-on-surface), .1); padding-top: 16px; }
.model-advanced summary { cursor: pointer; color: rgba(var(--v-theme-on-surface), .65); }
.model-advanced :deep(.config-row) { padding: 12px 0; row-gap: 8px; }
.model-advanced :deep(.property-info), .model-advanced :deep(.config-input) { flex: 0 0 100%; max-width: 100%; padding: 0; }
.model-advanced :deep(.property-info .v-list-item) { padding-inline: 0; }
.model-advanced :deep(.config-divider) { margin-inline: 0; }
@media (max-width: 600px) {
  .model-choices { grid-template-columns: 1fr; }
  .model-picker { flex-wrap: wrap; }
  .model-picker > :first-child { flex-basis: 100%; }
}
</style>
