<template>
  <div class="provider-page">
    <v-container fluid class="pa-0">
      <div class="provider-tabs-scroll">
        <div
          class="provider-tabs"
          role="tablist"
          :aria-label="tm('providerTypes.title')"
        >
          <button
            v-for="type in providerTypes"
            :key="type.value"
            type="button"
            class="provider-tab"
            :class="{ 'provider-tab--active': selectedProviderType === type.value }"
            role="tab"
            :aria-selected="selectedProviderType === type.value"
            @click="selectedProviderType = type.value"
          >
            <v-icon :icon="type.icon" size="16" />
            <span>{{ type.label }}</span>
          </button>
        </div>
      </div>

      <div class="provider-content">
        <div class="provider-workbench">
          <div class="provider-workbench__sidebar">
            <ProviderSourcesPanel
              :displayed-provider-sources="selectedProviderType === 'chat_completion'
                ? displayedProviderSources
                : displayedLegacyProviders"
              :selected-provider-source="selectedProviderType === 'chat_completion'
                ? selectedProviderSource
                : selectedLegacyProvider"
              :available-source-types="availableSourceTypes"
              :title="selectedProviderType === 'chat_completion' ? '' : tm('providers.title')"
              :empty-text="selectedProviderType === 'chat_completion' ? '' : getEmptyText()"
              :select-hint="selectedProviderType === 'chat_completion'
                ? ''
                : tm('providers.selectHint')"
              :delete-label="selectedProviderType === 'chat_completion'
                ? ''
                : tm('providers.deleteProvider')"
              :loading="loadingSources"
              :tm="tm"
              :resolve-source-icon="resolveSourceIcon"
              :is-monochrome-source-icon="isMonochromeSourceIcon"
              :get-source-display-name="getSourceDisplayName"
              @add-provider-source="selectedProviderType === 'chat_completion'
                ? addProviderSource($event)
                : addLegacyProvider($event)"
              @select-provider-source="selectedProviderType === 'chat_completion'
                ? selectProviderSource($event)
                : selectLegacyProvider($event)"
              @delete-provider-source="selectedProviderType === 'chat_completion'
                ? deleteProviderSource($event)
                : deleteLegacyProvider($event)"
            />
          </div>

          <div class="provider-workbench__divider"></div>

          <div class="provider-workbench__main">
            <template v-if="selectedProviderType === 'chat_completion'">
            <div v-if="selectedProviderSource" class="provider-config-shell">
              <div class="provider-config-header">
                <div class="provider-config-headline">
                  <div class="provider-config-title">{{ selectedProviderSource.id }}</div>
                  <div class="provider-config-subtitle">
                    {{ selectedProviderSource.api_base || 'N/A' }}
                  </div>
                </div>

                <div class="provider-config-actions">
                  <v-btn
                    color="primary"
                    prepend-icon="mdi-content-save-outline"
                    :loading="savingSource"
                    :disabled="!isSourceModified"
                    variant="tonal"
                    rounded="xl"
                    @click="saveProviderSource"
                  >
                    {{ tm('providerSources.save') }}
                  </v-btn>
                </div>
              </div>

              <v-divider></v-divider>

              <div class="provider-config-body">
                <section class="provider-section">
                  <div class="provider-section-head">
                    <div class="provider-section-title">{{ tm('providers.settings') }}</div>
                  </div>
                  <AstrBotConfig
                    v-if="basicSourceConfig"
                    :iterable="basicSourceConfig"
                    :metadata="providerSourceSchema"
                    metadataKey="provider"
                    :is-editing="true"
                  />
                </section>

                <v-divider v-if="advancedSourceConfig"></v-divider>

                <section v-if="advancedSourceConfig" class="provider-section">
                  <div class="provider-section-head">
                    <div class="provider-section-title">{{ tm('providerSources.advancedConfig') }}</div>
                  </div>
                  <AstrBotConfig
                    :iterable="advancedSourceConfig"
                    :metadata="providerSourceSchema"
                    metadataKey="provider"
                    :is-editing="true"
                  />
                </section>

                <v-divider></v-divider>

                <section class="provider-section provider-section--models">
                  <ProviderModelsPanel
                    :entries="filteredMergedModelEntries"
                    :available-count="availableModels.length"
                    v-model:model-search="modelSearch"
                    :loading-models="loadingModels"
                    :is-source-modified="isSourceModified"
                    :supports-image-input="supportsImageInput"
                    :supports-audio-input="supportsAudioInput"
                    :supports-tool-call="supportsToolCall"
                    :supports-reasoning="supportsReasoning"
                    :format-context-limit="formatContextLimit"
                    :testing-providers="testingProviders"
                    :tm="tm"
                    @fetch-models="fetchAvailableModels"
                    @open-manual-model="openManualModelDialog"
                    @open-provider-edit="openProviderEdit"
                    @toggle-provider-enable="toggleProviderEnable"
                    @test-provider="testProvider"
                    @delete-provider="deleteProvider"
                    @add-model-provider="openModelAddDialog"
                  />
                </section>
              </div>
            </div>

            <div v-else class="provider-empty-state">
              <v-icon size="48" color="grey-lighten-1">mdi-cursor-default-click</v-icon>
              <p class="mt-2">{{ tm('providerSources.selectHint') }}</p>
            </div>
            </template>

            <template v-else>
            <div v-if="selectedLegacyProvider" class="provider-config-shell">
              <div class="provider-config-header">
                <div class="provider-config-headline">
                  <div class="provider-config-title">
                    {{ newSelectedProviderConfig.id || selectedLegacyProvider.id }}
                  </div>
                  <div class="provider-config-subtitle">
                    {{
                      newSelectedProviderConfig.api_base ||
                      newSelectedProviderConfig.embedding_api_base ||
                      newSelectedProviderConfig.rerank_api_base ||
                      newSelectedProviderConfig.type ||
                      'N/A'
                    }}
                  </div>
                </div>

                <div class="provider-config-actions d-flex align-center ga-2">
                  <v-btn
                    v-if="updatingMode"
                    color="primary"
                    prepend-icon="mdi-connection"
                    :loading="isProviderTesting(selectedLegacyProvider.id)"
                    :disabled="selectedLegacyProvider.enable === false"
                    variant="text"
                    rounded="xl"
                    @click="testSingleProvider(selectedLegacyProvider)"
                  >
                    {{ tm('availability.test') }}
                  </v-btn>
                  <v-btn
                    color="primary"
                    prepend-icon="mdi-content-save-outline"
                    :loading="loading"
                    :disabled="!isLegacyProviderModified"
                    variant="tonal"
                    rounded="xl"
                    @click="saveLegacyProvider"
                  >
                    {{ tm('dialogs.config.save') }}
                  </v-btn>
                </div>
              </div>

              <v-divider></v-divider>

              <div class="provider-config-body">
                <section class="provider-section">
                  <div class="provider-section-head">
                    <div class="provider-section-title">{{ tm('providers.settings') }}</div>
                  </div>
                  <AstrBotConfig
                    :iterable="newSelectedProviderConfig"
                    :metadata="configSchema"
                    metadataKey="provider"
                    :is-editing="updatingMode"
                  />
                </section>
              </div>
            </div>

            <div v-else class="provider-empty-state">
              <v-icon size="48" color="grey-lighten-1">mdi-cursor-default-click</v-icon>
              <p class="mt-2">{{ tm('providers.selectHint') }}</p>
            </div>
            </template>
          </div>
        </div>
      </div>
    </v-container>

    <v-dialog v-model="showManualModelDialog" max-width="400">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">
          {{ tm('models.manualDialogTitle') }}
        </v-card-title>
        <v-card-text class="py-4">
          <v-text-field
            v-model="manualModelId"
            :label="tm('models.manualDialogModelLabel')"
            flat
            variant="solo-filled"
            autofocus
            clearable
          ></v-text-field>
          <v-text-field
            :model-value="manualProviderId"
            flat
            variant="solo-filled"
            :label="tm('models.manualDialogPreviewLabel')"
            persistent-hint
            :hint="tm('models.manualDialogPreviewHint')"
          ></v-text-field>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showManualModelDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" @click="confirmManualModel">添加</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="showProviderEditDialog" width="800">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">
          {{ providerEditDialogTitle }}
        </v-card-title>
        <v-card-text class="py-4">
          <AstrBotConfig
            v-if="providerEditData"
            :iterable="providerEditData"
            :metadata="providerModelConfigSchema"
            metadataKey="provider"
            :is-editing="true"
          />
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn
            variant="text"
            :disabled="savingProviders.includes(providerEditData?.id)"
            @click="showProviderEditDialog = false"
          >
            {{ tm('dialogs.config.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="savingProviders.includes(providerEditData?.id)"
            @click="saveEditedProvider"
          >
            {{ tm('dialogs.config.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="top">
      {{ snackbar.message }}
    </v-snackbar>

  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { providerApi } from '@/api/v1'
import { useModuleI18n } from '@/i18n/composables'
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue'
import ProviderModelsPanel from '@/components/provider/ProviderModelsPanel.vue'
import ProviderSourcesPanel from '@/components/provider/ProviderSourcesPanel.vue'
import { useProviderModelConfigDialog } from '@/composables/useProviderModelConfigDialog'
import { useProviderSources } from '@/composables/useProviderSources'

const props = defineProps({
  defaultTab: {
    type: String,
    default: 'chat_completion'
  }
})

const { tm } = useModuleI18n('features/provider')

const snackbar = ref({
  show: false,
  message: '',
  color: 'success'
})

function showMessage(message, color = 'success') {
  snackbar.value = { show: true, message, color }
}

const {
  providers,
  selectedProviderType,
  selectedProviderSource,
  availableModels,
  loadingSources,
  loadingModels,
  savingSource,
  testingProviders,
  isSourceModified,
  configSchema,
  providerSourceSchema,
  manualModelId,
  modelSearch,
  providerTypes,
  availableSourceTypes,
  displayedProviderSources,
  filteredMergedModelEntries,
  filteredProviders,
  basicSourceConfig,
  advancedSourceConfig,
  manualProviderId,
  resolveSourceIcon,
  isMonochromeSourceIcon,
  getSourceDisplayName,
  supportsImageInput,
  supportsAudioInput,
  supportsToolCall,
  supportsReasoning,
  formatContextLimit,
  updateDefaultTab,
  selectProviderSource,
  addProviderSource,
  deleteProviderSource,
  saveProviderSource,
  fetchAvailableModels,
  buildModelProviderConfig,
  deleteProvider,
  modelAlreadyConfigured,
  toggleProviderEnable,
  testProvider,
  loadConfig
} = useProviderSources({
  defaultTab: props.defaultTab,
  tm,
  showMessage
})

const unsavedLegacyProviderMarker = Symbol('unsavedLegacyProvider')
const legacyProviderDrafts = ref([])
const selectedLegacyProvider = ref(null)
const newSelectedProviderConfig = ref({})
const newProviderOriginalId = ref('')
const updatingMode = ref(false)
const loading = ref(false)
const isLegacyProviderModified = ref(false)
const showManualModelDialog = ref(false)
let suppressLegacyProviderWatch = false

const displayedLegacyProviders = computed(() => [
  ...filteredProviders.value,
  ...legacyProviderDrafts.value.filter(
    (provider) => provider.provider_type === selectedProviderType.value
  )
])

const {
  showProviderEditDialog,
  providerEditData,
  savingProviders,
  providerModelConfigSchema,
  providerEditDialogTitle,
  openProviderEdit,
  openModelAddDialog,
  saveEditedProvider
} = useProviderModelConfigDialog({
  selectedProviderSource,
  configSchema,
  buildModelProviderConfig,
  modelAlreadyConfigured,
  loadConfig,
  tm,
  showMessage
})

function openManualModelDialog() {
  if (!selectedProviderSource.value) {
    showMessage(tm('providerSources.selectHint'), 'error')
    return
  }
  manualModelId.value = ''
  showManualModelDialog.value = true
}

async function confirmManualModel() {
  const modelId = manualModelId.value.trim()
  if (!selectedProviderSource.value) {
    showMessage(tm('providerSources.selectHint'), 'error')
    return
  }
  if (!modelId) {
    showMessage(tm('models.manualModelRequired'), 'error')
    return
  }
  if (modelAlreadyConfigured(modelId)) {
    showMessage(tm('models.manualModelExists'), 'error')
    return
  }
  showManualModelDialog.value = false
  openModelAddDialog(modelId)
}

watch(() => props.defaultTab, (val) => {
  updateDefaultTab(val)
})

watch(selectedProviderType, () => {
  selectedLegacyProvider.value = null
  newProviderOriginalId.value = ''
  updatingMode.value = false
  isLegacyProviderModified.value = false
  suppressLegacyProviderWatch = true
  newSelectedProviderConfig.value = {}
  nextTick(() => {
    suppressLegacyProviderWatch = false
  })
})

watch(newSelectedProviderConfig, (config) => {
  if (suppressLegacyProviderWatch || !selectedLegacyProvider.value) return

  isLegacyProviderModified.value = true
  if (selectedLegacyProvider.value[unsavedLegacyProviderMarker]) {
    Object.assign(
      selectedLegacyProvider.value,
      JSON.parse(JSON.stringify(config))
    )
  }
}, { deep: true })

function getEmptyText() {
  const selectedType = providerTypes.value.find(
    (type) => type.value === selectedProviderType.value
  )
  return tm('providers.empty.typed', {
    type: selectedType?.label || selectedProviderType.value
  })
}

function addLegacyProvider(name) {
  const template = configSchema.value.provider?.config_template?.[name]
  if (!template) {
    showMessage(tm('dialogs.addProvider.noTemplates'), 'error')
    return
  }

  const draft = JSON.parse(JSON.stringify(template))
  const existingIds = new Set([
    ...providers.value.map((provider) => provider.id),
    ...legacyProviderDrafts.value.map((provider) => provider.id)
  ])
  const baseId = String(draft.id || name)
  let nextId = baseId
  let counter = 1
  while (existingIds.has(nextId)) {
    nextId = `${baseId}_${counter}`
    counter += 1
  }
  draft.id = nextId
  draft[unsavedLegacyProviderMarker] = true
  legacyProviderDrafts.value.push(draft)
  selectLegacyProvider(draft)
}

function selectLegacyProvider(provider) {
  selectedLegacyProvider.value = provider
  newProviderOriginalId.value = provider[unsavedLegacyProviderMarker]
    ? ''
    : provider.id
  suppressLegacyProviderWatch = true
  newSelectedProviderConfig.value = {}

  const templates = configSchema.value.provider?.config_template || {}
  let defaultConfig = {}
  for (const key in templates) {
    if (templates[key]?.type === provider.type) {
      defaultConfig = templates[key]
      break
    }
  }

  const mergeConfigWithOrder = (target, source, reference) => {
    if (source && typeof source === 'object' && !Array.isArray(source)) {
      for (const key in source) {
        if (Object.prototype.hasOwnProperty.call(source, key)) {
          if (typeof source[key] === 'object' && source[key] !== null) {
            target[key] = Array.isArray(source[key]) ? [...source[key]] : { ...source[key] }
          } else {
            target[key] = source[key]
          }
        }
      }
    }

    for (const key in reference) {
      if (typeof reference[key] === 'object' && reference[key] !== null) {
        if (!(key in target)) {
          if (Array.isArray(reference[key])) {
            target[key] = [...reference[key]]
          } else {
            target[key] = {}
          }
        }
        if (!Array.isArray(reference[key])) {
          mergeConfigWithOrder(
            target[key],
            source && source[key] ? source[key] : {},
            reference[key]
          )
        }
      } else if (!(key in target)) {
        target[key] = reference[key]
      }
    }
  }

  if (defaultConfig) {
    mergeConfigWithOrder(newSelectedProviderConfig.value, provider, defaultConfig)
  }

  updatingMode.value = !provider[unsavedLegacyProviderMarker]
  isLegacyProviderModified.value = Boolean(provider[unsavedLegacyProviderMarker])
  nextTick(() => {
    suppressLegacyProviderWatch = false
  })
}

async function saveLegacyProvider() {
  if (!selectedLegacyProvider.value) return

  loading.value = true
  const wasUpdating = updatingMode.value
  const selectedDraft = selectedLegacyProvider.value
  const savedId = newSelectedProviderConfig.value.id
  try {
    if (wasUpdating) {
      const res = await providerApi.update(
        newProviderOriginalId.value,
        newSelectedProviderConfig.value
      )
      if (res.data.status === 'error') {
        throw new Error(res.data.message || '更新失败!')
      }
      showMessage(res.data.message || '更新成功!')
    } else {
      const res = await providerApi.create(newSelectedProviderConfig.value)
      if (res.data.status === 'error') {
        throw new Error(res.data.message || '添加失败!')
      }
      showMessage(res.data.message || '添加成功!')
      legacyProviderDrafts.value = legacyProviderDrafts.value.filter(
        (provider) => provider !== selectedDraft
      )
    }

    await loadConfig()
    const savedProvider = providers.value.find((provider) => provider.id === savedId)
    if (savedProvider) {
      selectLegacyProvider(savedProvider)
      isLegacyProviderModified.value = false
    }
  } catch (err) {
    showMessage(err.response?.data?.message || err.message, 'error')
  } finally {
    loading.value = false
  }
}

async function deleteLegacyProvider(provider) {
  if (provider[unsavedLegacyProviderMarker]) {
    legacyProviderDrafts.value = legacyProviderDrafts.value.filter(
      (draft) => draft !== provider
    )
    if (selectedLegacyProvider.value === provider) {
      selectedLegacyProvider.value = null
      newSelectedProviderConfig.value = {}
      newProviderOriginalId.value = ''
      updatingMode.value = false
      isLegacyProviderModified.value = false
    }
    return
  }

  const deleted = await deleteProvider(provider)
  if (deleted && selectedLegacyProvider.value?.id === provider.id) {
    selectedLegacyProvider.value = null
    newSelectedProviderConfig.value = {}
    newProviderOriginalId.value = ''
    updatingMode.value = false
    isLegacyProviderModified.value = false
  }
}

function isProviderTesting(providerId) {
  return testingProviders.value.includes(providerId)
}

async function testSingleProvider(provider) {
  if (isProviderTesting(provider.id)) return
  if (provider.enable === false) {
    showMessage('该提供商未被用户启用', 'error')
    return
  }
  await testProvider(provider)
}
</script>

<style scoped>
.provider-page {
  --provider-surface: rgb(var(--v-theme-surface));
  --provider-border: rgba(var(--v-theme-on-surface), 0.08);
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  overflow: hidden;
  width: 100%;
}

.provider-page > .v-container {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.provider-tabs-scroll {
  flex: 0 0 auto;
  overflow-x: auto;
  padding: 4px 12px 8px;
  scrollbar-width: none;
}

.provider-tabs-scroll::-webkit-scrollbar {
  display: none;
}

.provider-tabs {
  align-items: center;
  display: inline-flex;
  gap: 2px;
  min-width: max-content;
}

.provider-tab {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 8px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-size: 0.8125rem;
  font-weight: 500;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  white-space: nowrap;
}

.provider-tab:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.provider-tab--active {
  background: rgba(var(--v-theme-on-surface), 0.065);
  color: rgba(var(--v-theme-on-surface), 0.86);
}

.provider-tab--active:hover {
  background: rgba(var(--v-theme-on-surface), 0.09);
  color: rgba(var(--v-theme-on-surface), 0.9);
}

.provider-content {
  display: flex;
  flex: 1;
  margin: 0 auto;
  max-width: 1200px;
  min-height: 0;
  padding: 16px 12px 12px;
  width: 100%;
}

.provider-workbench {
  border: 1px solid var(--provider-border);
  border-radius: 16px;
  background: var(--provider-surface);
  display: grid;
  flex: 1;
  grid-template-columns: minmax(280px, 320px) 1px minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
  width: 100%;
}

.provider-workbench__sidebar,
.provider-workbench__main {
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.provider-workbench__divider {
  background: var(--provider-border);
}

.provider-workbench__main {
  display: flex;
}

.provider-config-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.provider-config-header {
  background: var(--provider-surface);
  display: flex;
  flex: 0 0 auto;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 18px 22px 14px;
  position: relative;
  z-index: 1;
}

.provider-config-shell > :deep(.v-divider) {
  flex: 0 0 auto;
}

.provider-config-headline {
  min-width: 0;
}

.provider-config-title {
  font-size: 21px;
  line-height: 1.1;
  font-weight: 680;
  letter-spacing: -0.03em;
  overflow-wrap: anywhere;
}

.provider-config-subtitle {
  margin-top: 6px;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.provider-config-actions {
  flex-shrink: 0;
}

.provider-config-body {
  flex: 1;
  min-height: 0;
  overscroll-behavior: contain;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.provider-section {
  padding: 18px 22px;
}

.provider-section--models {
  padding-top: 16px;
}

.provider-section--models :deep(.provider-models-list--available) {
  max-height: none;
  overflow: visible;
}

.provider-section-head {
  margin-bottom: 10px;
}

.provider-section-title {
  font-size: 16px;
  font-weight: 650;
  line-height: 1.4;
}

.provider-empty-state {
  flex: 1;
  min-height: 420px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: rgba(var(--v-theme-on-surface), 0.56);
}

@media (max-width: 960px) {
  .provider-workbench {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1px minmax(0, 1fr);
  }

  .provider-workbench__divider {
    height: 1px;
  }

  .provider-config-header {
    flex-direction: column;
    align-items: stretch;
    padding: 16px;
  }

  .provider-config-actions :deep(.v-btn) {
    width: 100%;
  }

  .provider-config-actions {
    align-items: stretch !important;
    flex-direction: column;
    width: 100%;
  }

  .provider-section {
    padding: 16px;
  }
}

@media (max-width: 600px) {
  .provider-tabs-scroll {
    padding-inline: 4px;
  }

  .provider-workbench {
    border-radius: 12px;
  }

  .provider-tab {
    padding-inline: 11px;
  }

  .provider-config-title {
    font-size: 18px;
  }

  .provider-empty-state {
    min-height: 260px;
    padding: 24px;
  }
}
</style>
