<template>
  <v-dialog v-model="dialog" :max-width="isMobile ? undefined : '1400'" :fullscreen="isMobile" scrollable>
    <v-card class="provider-config-dialog" :class="{ 'mobile-dialog': isMobile }">
      <v-card-title class="d-flex align-center justify-space-between pa-4 pb-0">
        <div class="d-flex align-center ga-2">
          <span class="text-h2 font-weight-bold">{{ tm('title') }}</span>
        </div>
        <v-btn icon variant="text" @click="closeDialog">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>

      <v-card-text class="pa-4 pt-0" :class="{ 'mobile-content': isMobile }"
        :style="isMobile ? {} : { height: 'calc(100vh - 200px); max-height: 800px;' }">
        <div :class="isMobile ? 'mobile-layout' : 'd-flex'" :style="isMobile ? {} : { height: '100%' }">
          <!-- 左侧：Provider Sources 列表 -->
          <div class="provider-sources-column" :class="{ 'mobile-sources': isMobile }"
            :style="isMobile ? {} : { width: '320px', minWidth: '320px', borderRight: '1px solid rgba(var(--v-border-color), var(--v-border-opacity))', overflowY: 'auto' }">
            <ProviderSourcesPanel :displayed-provider-sources="displayedProviderSources"
              :selected-provider-source="selectedProviderSource" :available-source-types="availableSourceTypes" :tm="tm"
              :resolve-source-icon="resolveSourceIcon" :get-source-display-name="getSourceDisplayName"
              @add-provider-source="addProviderSource" @select-provider-source="selectProviderSource"
              @delete-provider-source="deleteProviderSource" />
          </div>

          <!-- 右侧：配置和模型 -->
          <div class="provider-config-column" :class="{ 'mobile-config': isMobile }"
            :style="isMobile ? {} : { flex: 1, overflowY: 'auto', minWidth: 0 }">
            <div v-if="selectedProviderSource" class="pa-4">
              <!-- Provider Source 配置 -->
              <div class="mb-4">
                <div class="d-flex align-center justify-space-between mb-3">
                  <div>
                    <div class="text-h5 font-weight-bold">{{ selectedProviderSource.id }}</div>
                    <div class="text-caption text-medium-emphasis">{{ selectedProviderSource.api_base || 'N/A' }}</div>
                  </div>
                  <v-btn color="success" prepend-icon="mdi-check" :loading="savingSource" :disabled="!isSourceModified"
                    @click="saveProviderSource" variant="flat">
                    {{ tm('providerSources.save') }}
                  </v-btn>
                </div>

                <!-- 基础配置 -->
                <div class="mb-4">
                  <AstrBotConfig v-if="basicSourceConfig" :iterable="basicSourceConfig" :metadata="configSchema"
                    metadataKey="provider" :is-editing="true" />
                </div>

                <!-- 高级配置 -->
                <v-expansion-panels variant="accordion" class="mb-4">
                  <v-expansion-panel elevation="0" class="border rounded-lg">
                    <v-expansion-panel-title>
                      <span class="font-weight-medium">{{ tm('providerSources.advancedConfig') }}</span>
                    </v-expansion-panel-title>
                    <v-expansion-panel-text>
                      <AstrBotConfig v-if="advancedSourceConfig" :iterable="advancedSourceConfig"
                        :metadata="configSchema" metadataKey="provider" :is-editing="true" />
                    </v-expansion-panel-text>
                  </v-expansion-panel>
                </v-expansion-panels>

                <!-- 模型配置 -->
                <ProviderModelsPanel :entries="filteredMergedModelEntries" :available-count="availableModels.length"
                  v-model:model-search="modelSearch" :loading-models="loadingModels"
                  :is-source-modified="isSourceModified" :supports-image-input="supportsImageInput"
                  :supports-tool-call="supportsToolCall" :supports-reasoning="supportsReasoning"
                  :format-context-limit="formatContextLimit" :testing-providers="testingProviders" :tm="tm"
                  @fetch-models="fetchAvailableModels" @open-manual-model="openManualModelDialog"
                  @open-provider-edit="openProviderEdit" @toggle-provider-enable="toggleProviderEnable"
                  @test-provider="testProvider" @delete-provider="deleteProvider"
                  @add-model-provider="addModelProvider" />
              </div>
            </div>
            <div v-else class="d-flex align-center justify-center" style="height: 100%;">
              <div class="text-center text-medium-emphasis">
                <v-icon size="64" color="grey-lighten-1">mdi-cursor-default-click</v-icon>
                <p class="mt-4 text-h6">{{ tm('providerSources.selectHint') }}</p>
              </div>
            </div>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <!-- 手动添加模型对话框 -->
    <v-dialog v-model="showManualModelDialog" max-width="400">
      <v-card :title="tm('models.manualDialogTitle')">
        <v-card-text class="py-4">
          <v-text-field v-model="manualModelId" :label="tm('models.manualDialogModelLabel')" flat variant="solo-filled"
            autofocus clearable></v-text-field>
          <v-text-field :model-value="manualProviderId" flat variant="solo-filled"
            :label="tm('models.manualDialogPreviewLabel')" persistent-hint
            :hint="tm('models.manualDialogPreviewHint')"></v-text-field>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showManualModelDialog = false">取消</v-btn>
          <v-btn color="primary" @click="confirmManualModel">添加</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 已配置模型编辑对话框 -->
    <v-dialog v-model="showProviderEditDialog" width="800">
      <v-card :title="providerEditData?.id || tm('dialogs.config.editTitle')">
        <v-card-text class="py-4">
          <small style="color: gray;">不建议修改 ID，可能会导致指向该模型的相关配置（如默认模型、插件相关配置等）失效。</small>
          <AstrBotConfig v-if="providerEditData" :iterable="providerEditData" :metadata="configSchema"
            metadataKey="provider" :is-editing="true" />
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showProviderEditDialog = false"
            :disabled="savingProviders.includes(providerEditData?.id)">
            {{ tm('dialogs.config.cancel') }}
          </v-btn>
          <v-btn color="primary" @click="saveEditedProvider" :loading="savingProviders.includes(providerEditData?.id)">
            {{ tm('dialogs.config.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-dialog>
</template>

<script setup>
import { ref, watch, computed, onMounted, onBeforeUnmount } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue'
import ProviderModelsPanel from '@/components/provider/ProviderModelsPanel.vue'
import ProviderSourcesPanel from '@/components/provider/ProviderSourcesPanel.vue'
import { useProviderSources } from '@/composables/useProviderSources'
import { getProviderIcon } from '@/utils/providerUtils'
import axios from 'axios'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue'])

const { tm } = useModuleI18n('features/provider')

// 检测是否为手机端
const isMobile = ref(false)

function checkMobile() {
  isMobile.value = window.innerWidth <= 768
}

const dialog = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

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
  testingProviders,
  isSourceModified,
  configSchema,
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
  loadConfig,
  modelAlreadyConfigured,
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

function closeDialog() {
  dialog.value = false
}

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

async function toggleProviderEnable(provider, value) {
  provider.enable = value

  try {
    const res = await axios.post('/api/config/provider/update', {
      id: provider.id,
      config: provider
    })

    if (res.data.status === 'error') {
      throw new Error(res.data.message)
    }
    showMessage(res.data.message || tm('messages.success.statusUpdate'))
  } catch (error) {
    showMessage(error.response?.data?.message || error.message || tm('providerSources.saveError'), 'error')
  } finally {
    await loadConfig()
  }
}

// 监听 dialog 打开，加载配置
watch(dialog, (newVal) => {
  if (newVal) {
    loadConfig()
    checkMobile()
  }
})

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>

<style scoped>
.provider-config-dialog {
  height: calc(100vh - 100px);
  display: flex;
  flex-direction: column;
}

.provider-config-dialog.mobile-dialog {
  height: 100vh;
}

.provider-sources-column {
  overflow-y: auto;
  background-color: var(--v-theme-surface);
}

.provider-config-column {
  background-color: var(--v-theme-background);
}

.border {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

/* 手机端样式 */
.mobile-content {
  padding: 8px !important;
  padding-top: 0 !important;
  height: calc(100vh - 64px) !important;
  max-height: none !important;
}

.mobile-layout {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 16px;
}

.mobile-sources {
  width: 100% !important;
  min-width: 100% !important;
  border-right: none !important;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  max-height: 40vh;
  overflow-y: auto;
}

.mobile-config {
  flex: 1;
  overflow-y: auto;
  min-width: 100% !important;
}

@media (max-width: 768px) {
  .provider-config-dialog :deep(.v-card-title) {
    padding: 12px 16px !important;
  }

  .provider-config-dialog :deep(.v-card-title .text-h2) {
    font-size: 1.5rem !important;
  }
}
</style>
