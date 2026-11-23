<template>
  <div class="provider-chat-panel">
    <div
      class="provider-workbench"
      :class="{ 'provider-workbench--borderless': !props.showBorder }"
    >
      <div class="provider-workbench__sidebar">
        <ProviderSourcesPanel
          :displayed-provider-sources="displayedProviderSources"
          :selected-provider-source="selectedProviderSource"
          :available-source-types="availableSourceTypes"
          :tm="tm"
          :resolve-source-icon="resolveSourceIcon"
          :is-monochrome-source-icon="isMonochromeSourceIcon"
          :get-source-display-name="getSourceDisplayName"
          @add-provider-source="addProviderSource"
          @select-provider-source="selectProviderSource"
          @delete-provider-source="deleteProviderSource"
        />
      </div>

      <div class="provider-workbench__divider"></div>

      <div class="provider-workbench__main">
        <div v-if="selectedProviderSource" class="provider-config-shell">
          <div class="provider-config-header">
            <div class="provider-config-identity">
              <v-avatar size="42" rounded="lg" class="provider-config-avatar">
                <v-img
                  v-if="selectedProviderSource.provider"
                  :src="resolveSourceIcon(selectedProviderSource)"
                  :class="{ 'provider-icon--monochrome': isMonochromeSourceIcon(selectedProviderSource) }"
                  alt=""
                  width="28"
                  height="28"
                />
                <v-icon v-else size="24">mdi-creation</v-icon>
              </v-avatar>
              <div class="provider-config-headline">
                <div class="provider-config-title">{{ getSourceDisplayName(selectedProviderSource) }}</div>
                <ProviderSourceSubtitle
                  class="provider-config-subtitle"
                  :title="selectedProviderSource.api_base"
                  :api-base="selectedProviderSource.api_base"
                  :sponsor="selectedSponsor"
                  :tm="tm"
                />
              </div>
            </div>

            <div class="provider-config-actions">
              <v-btn
                color="primary"
                prepend-icon="mdi-content-save-outline"
                :loading="savingSource"
                :disabled="!isSourceModified"
                :aria-label="tm('providerSources.save')"
                :title="tm('providerSources.save')"
                variant="tonal"
                rounded="lg"
                @click="saveProviderSource"
              >
                {{ tm('providerSources.save') }}
              </v-btn>
            </div>
          </div>

          <v-divider></v-divider>

          <div class="provider-config-body">
            <section class="provider-section config-form">
              <div class="provider-section-head">
                <div class="provider-section-title">{{ tm('providers.settings') }}</div>
              </div>
              <AstrBotConfig
                v-if="basicSourceConfig"
                :iterable="basicSourceConfig"
                :metadata="providerSourceSchema"
                :field-links="providerSourceFieldLinks"
                metadataKey="provider"
                :is-editing="true"
              />
            </section>

            <v-divider v-if="advancedSourceConfig"></v-divider>

            <details
              v-if="advancedSourceConfig"
              :key="selectedProviderSource.id"
              class="provider-section provider-section--advanced config-form"
            >
              <summary class="provider-section-head provider-section-title">
                {{ tm('providerSources.advancedConfig') }}
                <v-icon class="provider-section-chevron" size="20">mdi-chevron-right</v-icon>
              </summary>
              <div class="provider-section-content">
                <AstrBotConfig
                  :iterable="advancedSourceConfig"
                  :metadata="providerSourceSchema"
                  metadataKey="provider"
                  :is-editing="true"
                />
              </div>
            </details>

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
                :saving-providers="savingProviderToggles"
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
      </div>
    </div>

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
        <v-card-text class="py-4 config-form">
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
import { computed, ref } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue'
import ProviderModelsPanel from '@/components/provider/ProviderModelsPanel.vue'
import ProviderSourceSubtitle from '@/components/provider/ProviderSourceSubtitle.vue'
import ProviderSourcesPanel from '@/components/provider/ProviderSourcesPanel.vue'
import { useProviderModelConfigDialog } from '@/composables/useProviderModelConfigDialog'
import { useProviderSources } from '@/composables/useProviderSources'

const props = defineProps({
  showBorder: {
    type: Boolean,
    default: true
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
  selectedProviderSource,
  selectedSponsor,
  availableModels,
  loadingModels,
  savingSource,
  savingProviderToggles,
  testingProviders,
  isSourceModified,
  configSchema,
  providerSourceSchema,
  manualModelId,
  modelSearch,
  availableSourceTypes,
  displayedProviderSources,
  filteredMergedModelEntries,
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
  selectProviderSource,
  addProviderSource,
  deleteProviderSource,
  saveProviderSource,
  fetchAvailableModels,
  buildModelProviderConfig,
  deleteProvider,
  testProvider,
  toggleProviderEnable,
  loadConfig,
  modelAlreadyConfigured
} = useProviderSources({
  defaultTab: 'chat_completion',
  tm,
  showMessage
})

const providerSourceFieldLinks = computed(() => (
  selectedProviderSource.value?.provider === 'ssycloud'
    ? {
        key: {
          label: tm('providerSources.getApiKey'),
          href: 'https://www.shengsuanyun.com/?from=CH_T70U2X9L'
        }
      }
    : {}
))

const showManualModelDialog = ref(false)

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

</script>

<style scoped>
.provider-chat-panel {
  container: provider-workbench / inline-size;
  flex: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.provider-workbench {
  flex: 1;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 24px;
  background: rgb(var(--v-theme-surface));
  display: grid;
  grid-template-columns: 264px 1px minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
}

.provider-workbench--borderless {
  border: 0;
  border-radius: 0;
  background: transparent;
}

.provider-workbench__sidebar,
.provider-workbench__main {
  min-width: 0;
  min-height: 0;
}

.provider-workbench__sidebar,
.provider-workbench__main,
.provider-workbench__divider {
  height: 100%;
}

.provider-workbench__sidebar {
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.provider-workbench__divider {
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.provider-workbench__main {
  display: flex;
  overflow: auto;
}

.provider-config-shell {
  container: provider-config / inline-size;
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.provider-config-header {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 22px 28px;
  flex: 0 0 auto;
}

.provider-config-identity {
  display: flex;
  align-items: center;
  gap: 14px;
  flex: 1;
  min-width: 0;
}

.provider-config-avatar {
  flex-shrink: 0;
  padding: 9px;
  background: rgba(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.provider-config-headline {
  min-width: 0;
}

.provider-config-title {
  font-size: 22px;
  line-height: 1.25;
  font-weight: 650;
  letter-spacing: -0.02em;
  overflow-wrap: anywhere;
}

.provider-config-subtitle {
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.provider-config-actions {
  flex-shrink: 0;
}

.provider-config-actions :deep(.v-btn--disabled) {
  color: rgba(var(--v-theme-on-surface), 0.5) !important;
  opacity: 1;
}

.provider-config-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(var(--v-theme-on-surface), 0.2) transparent;
}

.provider-section {
  padding: 24px 28px;
}

.provider-section--models {
  padding-top: 24px;
}

.provider-section-head {
  margin-bottom: 8px;
}

.provider-section-title {
  font-size: 15px;
  font-weight: 650;
  line-height: 1.4;
}

.provider-section.config-form :deep(.config-row) {
  padding: 14px 0;
}

.provider-section.config-form :deep(.property-name) {
  font-weight: 600;
}

.provider-section.config-form :deep(.property-hint) {
  color: rgba(var(--v-theme-on-surface), 0.55) !important;
}

.provider-section.config-form :deep(.config-input > :not(.config-field--full-width)) {
  max-width: 360px;
}

.provider-section.config-form :deep(.v-field) {
  background: rgba(var(--v-theme-on-surface), 0.025);
  --v-field-border-opacity: 0.2;
}

.provider-section--advanced {
  padding-block: 16px;
  background: rgba(var(--v-theme-on-surface), 0.015);
}

.provider-section--advanced > summary {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  list-style: none;
}

.provider-section--advanced > summary:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 6px;
  border-radius: 4px;
}

.provider-section-chevron {
  margin-left: auto;
  color: rgba(var(--v-theme-on-surface), 0.45);
}

.provider-section--advanced > summary::-webkit-details-marker {
  display: none;
}

.provider-section--advanced:not([open]) > summary {
  margin-bottom: 0;
}

.provider-section--advanced[open] .provider-section-chevron {
  transform: rotate(90deg);
}

.provider-section-content {
  /* Restore Vuetify's inherited box sizing across the native details content boundary. */
  box-sizing: border-box;
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

@container provider-workbench (max-width: 960px) {
  .provider-workbench {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto 1px minmax(0, 1fr);
  }

  .provider-workbench__sidebar,
  .provider-workbench__main,
  .provider-workbench__divider {
    height: auto;
  }

  .provider-workbench__divider {
    min-height: 1px;
  }

  .provider-config-header {
    gap: 12px;
    padding: 20px 24px;
  }

  .provider-section {
    padding: 20px 24px;
  }

  .provider-section--advanced {
    padding-block: 16px;
  }
}

@container provider-workbench (max-width: 600px) {
  .provider-workbench {
    border-radius: 16px;
  }

  .provider-workbench--borderless {
    border-radius: 0;
  }

  .provider-config-title {
    font-size: 18px;
  }

  .provider-config-header,
  .provider-section {
    padding: 16px 20px;
  }

  .provider-config-identity {
    gap: 10px;
  }

  .provider-config-subtitle :deep(span) {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .provider-section.config-form :deep(.config-row) {
    padding: 10px 0;
  }

  .provider-section.config-form :deep(.config-input > :not(.config-field--full-width)) {
    max-width: none;
  }

  .provider-config-actions :deep(.v-btn) {
    min-width: 40px;
    width: 40px;
    height: 40px;
    padding: 0;
  }

  .provider-config-actions :deep(.v-btn__prepend) {
    margin: 0;
  }

  .provider-config-actions :deep(.v-btn__content) {
    display: none;
  }

  .provider-empty-state {
    min-height: 260px;
    padding: 24px;
  }
}
</style>

<style scoped src="@/styles/config-form.css"></style>
