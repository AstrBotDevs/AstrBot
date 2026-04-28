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
                :saving-providers="savingProviderToggles"
                :testing-providers="testingProviders"
                :tm="tm"
                @fetch-models="fetchAvailableModels"
                @open-manual-model="openManualModelDialog"
                @open-provider-edit="openProviderEdit"
                @toggle-provider-enable="toggleProviderEnable"
                @test-provider="testProvider"
                @delete-provider="deleteProvider"
                @add-model-provider="addModelProvider"
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
      <v-card :title="tm('models.manualDialogTitle')">
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
          <v-btn color="primary" @click="confirmManualModel">添加</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="showProviderEditDialog" width="800">
      <v-card :title="providerEditData?.id || tm('dialogs.config.editTitle')">
        <v-card-text class="py-4">
          <small style="color: gray;">不建议修改 ID，可能会导致指向该模型的相关配置（如默认模型、插件相关配置等）失效。旧版本 AstrBot 的 “提供商 ID” 是下方的 “ID”。</small>
          <AstrBotConfig
            v-if="providerEditData"
            :iterable="providerEditData"
            :metadata="configSchema"
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
import { ref } from 'vue'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue'
import ProviderModelsPanel from '@/components/provider/ProviderModelsPanel.vue'
import ProviderSourcesPanel from '@/components/provider/ProviderSourcesPanel.vue'
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
  addModelProvider,
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

const showManualModelDialog = ref(false)
const showProviderEditDialog = ref(false)
const providerEditData = ref(null)
const providerEditOriginalId = ref('')
const savingProviders = ref([])

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
  await addModelProvider(modelId)
  showManualModelDialog.value = false
}

function openProviderEdit(provider) {
  providerEditData.value = JSON.parse(JSON.stringify(provider))
  providerEditOriginalId.value = provider.id
  showProviderEditDialog.value = true
}

async function saveEditedProvider() {
  if (!providerEditData.value) return

  savingProviders.value.push(providerEditData.value.id)
  try {
    const res = await axios.post('/api/config/provider/update', {
      id: providerEditOriginalId.value || providerEditData.value.id,
      config: providerEditData.value
    })

    if (res.data.status === 'error') {
      throw new Error(res.data.message)
    }

    showMessage(res.data.message || tm('providerSources.saveSuccess'))
    showProviderEditDialog.value = false
    await loadConfig()
  } catch (err) {
    showMessage(err.response?.data?.message || err.message || tm('providerSources.saveError'), 'error')
  } finally {
    savingProviders.value = savingProviders.value.filter(id => id !== providerEditData.value?.id)
  }
}
</script>

<style scoped>
.provider-chat-panel {
  flex: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.provider-workbench {
  flex: 1;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 24px;
  background: rgb(var(--v-theme-surface));
  display: grid;
  grid-template-columns: minmax(280px, 320px) 1px minmax(0, 1fr);
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

.provider-workbench__divider {
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.provider-workbench__main {
  display: flex;
  overflow: hidden;
}

.provider-config-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.provider-config-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 18px 22px 14px;
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
  overflow-y: auto;
}

.provider-section {
  padding: 18px 22px;
}

.provider-section--models {
  padding-top: 16px;
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

  .provider-workbench__sidebar,
  .provider-workbench__main,
  .provider-workbench__divider {
    height: auto;
  }

  .provider-workbench__divider {
    min-height: 1px;
  }

  .provider-config-header {
    align-items: stretch;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
  }

  .provider-config-actions :deep(.v-btn) {
    width: 100%;
  }

  .provider-section {
    padding: 16px;
  }
}

@media (max-width: 600px) {
  .provider-chat-panel {
    overflow: auto;
  }

  .provider-workbench {
    border-radius: 16px;
    overflow: visible;
  }

  .provider-workbench--borderless {
    border-radius: 0;
  }

  .provider-workbench__main {
    overflow: visible;
  }

  .provider-config-body {
    overflow-y: visible;
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
