<template>
  <div class="onboarding-model">
    <div
      v-if="error"
      class="model-status-banner model-status-banner--error mb-4"
      role="alert"
    >
      <v-icon icon="mdi-alert-circle-outline" size="18" class="model-status-banner__icon" />
      <span class="model-status-banner__text">{{ error }}</span>
    </div>

    <div
      v-if="testStatus !== 'idle' && testMessage"
      class="model-status-banner mb-4"
      :class="`model-status-banner--${testStatus}`"
      role="status"
    >
      <v-icon
        :icon="testStatus === 'success' ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'"
        size="18"
        class="model-status-banner__icon"
      />
      <span class="model-status-banner__text">{{ testMessage }}</span>
    </div>

    <v-progress-linear v-if="loadingSources || loadingDefault" indeterminate color="primary" class="mb-3" rounded />

    <v-autocomplete
      v-model="choice"
      :items="choices"
      :label="t('guide.provider')"
      variant="outlined"
      density="compact"
      :disabled="disabled || loadingModels || testing"
      hide-details
      auto-select-first
      class="model-field"
      @update:model-value="choose"
    >
      <template #prepend-inner>
        <img
          v-if="selectedProviderSource"
          :src="resolveSourceIcon(selectedProviderSource)"
          width="20"
          height="20"
          alt=""
          class="model-select-icon"
          :class="{ 'provider-icon--monochrome': isMonochromeSourceIcon(selectedProviderSource) }"
        />
      </template>
      <template #item="{ props: itemProps, item }">
        <v-list-item v-bind="itemProps">
          <template #prepend>
            <div class="model-option-avatar">
              <img
                v-if="item.raw.icon"
                :src="item.raw.icon"
                width="20"
                height="20"
                alt=""
                :class="{ 'provider-icon--monochrome': item.raw.isMonochrome }"
              />
              <v-icon v-else icon="mdi-creation-outline" size="16" />
            </div>
          </template>
        </v-list-item>
      </template>
    </v-autocomplete>

    <div v-if="!selectedProviderSource" class="model-choices">
      <button
        v-for="source in availableSourceTypes.filter(s => !s.isSponsor).slice(0, 6)"
        :key="source.value"
        type="button"
        :disabled="disabled"
        @click="choice = `template:${source.value}`; choose(choice)"
      >
        <span class="model-choice-avatar">
          <img
            v-if="source.icon"
            :src="source.icon"
            width="22"
            height="22"
            alt=""
            :class="{ 'provider-icon--monochrome': source.isMonochrome }"
          />
          <v-icon v-else icon="mdi-creation-outline" size="18" />
        </span>
        <span class="model-choice-label">{{ source.label }}</span>
        <v-icon icon="mdi-chevron-right" size="18" class="model-choice-chevron" />
      </button>
    </div>

    <v-btn v-if="!loadingSources && !choices.length" variant="text" class="mt-2" @click="loadConfig">
      {{ t('guide.retry') }}
    </v-btn>

    <fieldset v-if="editableProviderSource" :disabled="disabled || loadingModels || testing" class="model-fields">
      <v-text-field
        v-if="'key' in editableProviderSource"
        :model-value="Array.isArray(editableProviderSource.key) ? editableProviderSource.key[0] : editableProviderSource.key"
        @update:model-value="editableProviderSource.key = Array.isArray(editableProviderSource.key) ? [$event, ...editableProviderSource.key.slice(1)] : $event; clearTestFeedback()"
        label="API Key"
        :type="showKey ? 'text' : 'password'"
        autocomplete="off"
        variant="outlined"
        density="compact"
        hide-details
        class="model-field"
      >
        <template #append-inner>
          <v-btn
            :icon="showKey ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
            size="x-small"
            variant="text"
            :aria-label="t('guide.toggleKey')"
            :title="t('guide.toggleKey')"
            @click="showKey = !showKey"
          />
        </template>
      </v-text-field>

      <v-text-field
        v-if="'api_base' in editableProviderSource"
        v-model="editableProviderSource.api_base"
        label="API Base URL"
        variant="outlined"
        density="compact"
        hide-details
        class="model-field"
        @update:model-value="clearTestFeedback"
      />

      <div class="model-picker">
        <v-combobox
          v-model="model"
          :items="modelOptions"
          :label="t('guide.model')"
          variant="outlined"
          density="compact"
          :return-object="false"
          hide-details
          class="model-field"
          @update:model-value="clearTestFeedback"
        />
        <v-btn
          variant="tonal"
          color="primary"
          size="default"
          class="model-fetch-btn"
          :loading="loadingModels"
          :disabled="disabled || testing"
          prepend-icon="mdi-refresh"
          @click="fetchAvailableModels"
        >
          {{ t('guide.fetchModels') }}
        </v-btn>
      </div>

      <details
        v-if="advancedSourceConfig && Object.keys(advancedSourceConfig).length"
        class="model-advanced config-form"
      >
        <summary class="model-advanced__summary">
          <span>{{ tm('providerSources.advancedConfig') }}</span>
          <v-icon class="model-advanced__chevron" size="20">mdi-chevron-right</v-icon>
        </summary>
        <div class="model-advanced__content">
          <AstrBotConfig
            :iterable="advancedSourceConfig"
            :metadata="providerSourceSchema"
            metadata-key="provider"
            :is-editing="true"
          />
        </div>
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
const testing = ref(false);
const testStatus = ref<'idle' | 'success' | 'error'>('idle');
const testMessage = ref('');
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
    .map(s => ({
      title: getSourceDisplayName(s),
      value: `source:${s.id}`,
      icon: resolveSourceIcon?.(s),
      isMonochrome: isMonochromeSourceIcon?.(s),
    })),
  ...availableSourceTypes.value.map(s => ({
    title: s.label,
    value: `template:${s.value}`,
    icon: s.icon,
    isMonochrome: s.isMonochrome,
  })),
]);
const modelOptions = computed(() => [...new Set([
  ...sourceProviders.value.map(p => p.model), ...availableModels.value.map(m => m.name),
])]);
const ready = computed(() => !!selectedProviderSource.value && !!String(model.value || '').trim() && !loadingSources.value && !loadingDefault.value && !loadingModels.value && !testing.value);
watch([loadingModels, testing], ([modelsLoading, isTesting]) => emit('update:busy', modelsLoading || isTesting));
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

function clearTestFeedback() {
  testStatus.value = 'idle';
  testMessage.value = '';
}

function choose(value: string | null) {
  if (!value) return;
  error.value = '';
  clearTestFeedback();
  if (value.startsWith('source:')) {
    selectProviderSource(displayedProviderSources.value.find(s => s.id === value.slice(7)));
  } else {
    addProviderSource(value.slice(9));
  }
  model.value = sourceProviders.value.find(p => p.enable !== false)?.model || '';
}

async function save(): Promise<string | undefined> {
  if (!selectedProviderSource.value || !String(model.value || '').trim() || loadingSources.value || loadingDefault.value || loadingModels.value) return;
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

async function test(): Promise<boolean> {
  if (!ready.value || testing.value) return false;
  testing.value = true;
  error.value = '';
  clearTestFeedback();
  try {
    const providerId = await save();
    if (!providerId) return false;
    const response = await providerApi.test(providerId);
    if (response.data.status === 'ok' && response.data.data?.status === 'available') {
      testStatus.value = 'success';
      testMessage.value = t('guide.testSuccess');
      return true;
    }
    testStatus.value = 'error';
    testMessage.value = response.data.data?.error || response.data.message || t('guide.testFailed');
    return false;
  } catch (cause: any) {
    testStatus.value = 'error';
    testMessage.value = cause?.response?.data?.message || cause?.message || t('guide.testFailed');
    return false;
  } finally {
    testing.value = false;
  }
}

defineExpose({ save, test, ready, model, testing, testStatus, testMessage });
</script>

<style scoped>
.onboarding-model :deep(.v-field) {
  border-radius: var(--astrbot-radius-control);
  background: rgba(var(--v-theme-on-surface), 0.025);
  --v-field-border-opacity: 0.2;
}

.model-status-banner {
  --banner-accent: var(--v-theme-error);
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(var(--banner-accent), 0.2);
  border-radius: var(--astrbot-radius-control);
  background: rgba(var(--banner-accent), 0.06);
  color: rgb(var(--v-theme-on-surface));
  font-size: 13px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.model-status-banner--success {
  --banner-accent: var(--v-theme-success);
}

.model-status-banner__icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: rgb(var(--banner-accent));
}

.model-status-banner__text {
  min-width: 0;
  flex: 1;
}

.model-select-icon {
  object-fit: contain;
  margin-right: 4px;
}

.model-option-avatar {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  margin-right: 10px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.model-choices {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.model-choices button {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  min-height: 54px;
  padding: 10px 14px;
  text-align: left;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.09);
  border-radius: var(--astrbot-radius-control);
  background: rgba(var(--v-theme-on-surface), 0.02);
  transition: background-color 0.16s ease, border-color 0.16s ease;
}

.model-choices button:hover,
.model-choices button:focus-visible {
  border-color: rgba(var(--v-theme-primary), 0.4);
  background: rgba(var(--v-theme-primary), 0.06);
}

.model-choice-avatar {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.model-choice-avatar img {
  object-fit: contain;
}

.model-choice-label {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 14px;
  font-weight: 500;
}

.model-choice-chevron {
  color: rgba(var(--v-theme-on-surface), 0.42);
}

.model-fields {
  border: 0;
  padding: 16px 0 0;
  margin: 0;
  min-width: 0;
  display: grid;
  gap: 14px;
}

.model-picker {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.model-picker > :first-child {
  min-width: 0;
}

.model-fetch-btn {
  flex-shrink: 0;
  height: 40px;
  text-transform: none;
  border-radius: var(--astrbot-radius-control);
}

.model-advanced {
  border-top: 1px solid rgba(var(--v-theme-borderLight), 0.36);
  padding-top: 12px;
}

.model-advanced__summary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 2px;
  cursor: pointer;
  list-style: none;
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.72);
  user-select: none;
}

.model-advanced__summary::-webkit-details-marker {
  display: none;
}

.model-advanced__summary:hover {
  color: rgb(var(--v-theme-on-surface));
}

.model-advanced__chevron {
  margin-left: auto;
  color: rgba(var(--v-theme-on-surface), 0.45);
  transition: transform 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}

.model-advanced[open] .model-advanced__chevron {
  transform: rotate(90deg);
}

.model-advanced__content {
  box-sizing: border-box;
  margin-top: 6px;
}

.model-advanced :deep(.config-row) {
  padding: 10px 0;
  row-gap: 8px;
}

.model-advanced :deep(.property-info),
.model-advanced :deep(.config-input) {
  flex: 0 0 100%;
  max-width: 100%;
  padding: 0;
}

.model-advanced :deep(.property-info .v-list-item) {
  padding-inline: 0;
}

.model-advanced :deep(.config-input > :not(.config-field--full-width)) {
  max-width: none;
}

.model-advanced :deep(.config-divider) {
  margin-inline: 0;
}

@media (max-width: 600px) {
  .model-choices {
    grid-template-columns: 1fr;
  }

  .model-picker {
    flex-wrap: wrap;
  }

  .model-picker > :first-child {
    flex-basis: 100%;
  }
}
</style>

<style scoped src="@/styles/config-form.css"></style>
