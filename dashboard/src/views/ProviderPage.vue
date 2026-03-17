<template>
  <div class="provider-page">
    <v-container fluid class="pa-0">
      <!-- 页面标题 -->
      <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-4">
        <div>
          <h1 class="text-h1 font-weight-bold mb-2">
            <v-icon color="black" class="me-2">mdi-creation</v-icon>{{ tm('title') }}
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-4">
            {{ tm('subtitle') }}
          </p>
        </div>
        <div v-if="selectedProviderType !== 'chat_completion'">
          <v-btn color="primary" prepend-icon="mdi-plus" variant="tonal" @click="showAddProviderDialog = true"
            rounded="xl" size="x-large">
            {{ tm('providers.addProvider') }}
          </v-btn>
        </div>
      </v-row>

      <div>
        <!-- Provider Type 标签页 -->
        <v-tabs v-model="selectedProviderType" bg-color="transparent" class="mb-4">
          <v-tab v-for="type in providerTypes" :key="type.value" :value="type.value" class="font-weight-medium px-3">
            <v-icon start>{{ type.icon }}</v-icon>
            {{ type.label }}
          </v-tab>
        </v-tabs>

        <!-- Chat Completion: 左侧列表 + 右侧上下卡片布局 -->
        <div v-if="selectedProviderType === 'chat_completion'" class="d-flex align-center justify-center">
          <v-row style="max-width: 1500px; ">
            <v-col cols="12" md="4" lg="3" class="pr-md-4">
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
            </v-col>

            <v-col cols="12" md="8" lg="9">
              <v-card class="provider-config-card h-100" elevation="0" style="overflow-y: auto;">
                <v-card-title class="d-flex align-center justify-space-between flex-wrap ga-3 pt-4 pl-5">
                  <div class="d-flex align-center ga-3" v-if="selectedProviderSource">
                    <div>
                      <div class="text-h4 font-weight-bold">{{ selectedProviderSource.id }}</div>
                      <div class="text-caption text-medium-emphasis">{{ selectedProviderSource.api_base || 'N/A' }}
                      </div>
                    </div>
                  </div>

                  <div class="d-flex align-center ga-2" v-if="selectedProviderSource">
                    <v-btn color="success" prepend-icon="mdi-check" :loading="savingSource"
                      :disabled="!isSourceModified" @click="saveProviderSource" variant="flat">
                      {{ tm('providerSources.save') }}
                    </v-btn>
                  </div>
                </v-card-title>

                <v-card-text>
                  <template v-if="selectedProviderSource">
                    <div>
                      <AstrBotConfig v-if="basicSourceConfig" :iterable="basicSourceConfig" :metadata="providerSourceSchema"
                        metadataKey="provider" :is-editing="true" />
                    </div>

                    <v-expansion-panels variant="accordion" class="mb-2">
                      <v-expansion-panel elevation="0" class="border rounded-lg">
                        <v-expansion-panel-title>
                          <span class="font-weight-medium">{{ tm('providerSources.advancedConfig') }}</span>
                        </v-expansion-panel-title>
                        <v-expansion-panel-text>
                          <AstrBotConfig v-if="advancedSourceConfig" :iterable="advancedSourceConfig"
                            :metadata="providerSourceSchema" metadataKey="provider" :is-editing="true" />
                        </v-expansion-panel-text>
                      </v-expansion-panel>
                    </v-expansion-panels>

                    <ProviderModelsPanel
                      :entries="filteredMergedModelEntries"
                      :available-count="availableModels.length"
                      v-model:model-search="modelSearch"
                      :loading-models="loadingModels"
                      :is-source-modified="isSourceModified"
                      :supports-image-input="supportsImageInput"
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
                      @add-model-provider="addModelProvider"
                    />
                  </template>
                  <div v-else class="text-center py-8 text-medium-emphasis">
                    <v-icon size="48" color="grey-lighten-1">mdi-cursor-default-click</v-icon>
                    <p class="mt-2">{{ tm('providerSources.selectHint') }}</p>
                  </div>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
        </div>

        <!-- 其他类型: 卡片布局 -->
        <template v-else>
          <v-row v-if="filteredProviders.length === 0">
            <v-col cols="12" class="text-center pa-8">
              <v-icon size="64" color="grey-lighten-1">mdi-api-off</v-icon>
              <p class="text-grey mt-4">{{ getEmptyText() }}</p>
            </v-col>
          </v-row>
          <v-row v-else>
            <v-col v-for="(provider, index) in filteredProviders" :key="index" cols="12" md="6" lg="4" xl="3">
              <item-card :item="provider" title-field="id" enabled-field="enable"
                :loading="isProviderTesting(provider.id)" @toggle-enabled="toggleProviderEnable(provider, !provider.enable)"
                :bglogo="getProviderIcon(provider.provider)" @delete="deleteProvider" @edit="configExistingProvider"
                @copy="copyProvider" :show-copy-button="true">

                <template #item-details="{ item }">
                  <!-- 测试状态 chip -->
                  <v-tooltip v-if="getProviderStatus(item.id)" location="top" max-width="300">
                    <template v-slot:activator="{ props }">
                      <v-chip v-bind="props" :color="getStatusColor(getProviderStatus(item.id).status)" size="small">
                        <v-icon start size="small">
                          {{ getProviderStatus(item.id).status === 'available' ? 'mdi-check-circle' :
                            getProviderStatus(item.id).status === 'unavailable' ? 'mdi-alert-circle' :
                              'mdi-clock-outline' }}
                        </v-icon>
                        {{ getStatusText(getProviderStatus(item.id).status) }}
                      </v-chip>
                    </template>
                    <span v-if="getProviderStatus(item.id).status === 'unavailable'">
                      {{ getProviderStatus(item.id).error }}
                    </span>
                    <span v-else>{{ getStatusText(getProviderStatus(item.id).status) }}</span>
                  </v-tooltip>
                </template>
                <template #actions="{ item }">
                  <v-btn style="z-index: 100000;" variant="tonal" color="info" rounded="xl" size="small"
                    :loading="isProviderTesting(item.id)" @click="testSingleProvider(item)">
                    {{ tm('availability.test') }}
                  </v-btn>
                </template>
              </item-card>
            </v-col>
          </v-row>
        </template>
      </div>
    </v-container>

    <!-- 添加提供商对话框 -->
    <AddNewProvider v-model:show="showAddProviderDialog" :metadata="configSchema"
      @select-template="selectProviderTemplate" />

    <!-- 手动添加模型对话框 -->
    <v-dialog v-model="showManualModelDialog" max-width="400">
      <v-card :title="tm('models.manualDialogTitle')">
        <v-card-text class="py-4">
          <v-text-field v-model="manualModelId" :label="tm('models.manualDialogModelLabel')" flat variant="solo-filled" autofocus clearable></v-text-field>
          <v-text-field :model-value="manualProviderId" flat variant="solo-filled" :label="tm('models.manualDialogPreviewLabel')" persistent-hint
            :hint="tm('models.manualDialogPreviewHint')"></v-text-field>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showManualModelDialog = false">取消</v-btn>
          <v-btn color="primary" @click="confirmManualModel">添加</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 配置对话框 -->
    <v-dialog v-model="showProviderCfg" width="900" persistent>
      <v-card
        :title="updatingMode ? tm('dialogs.config.editTitle') : tm('dialogs.config.addTitle') + ` ${newSelectedProviderName} ` + tm('dialogs.config.provider')">
        <v-card-text class="py-4">
          <AstrBotConfig :iterable="newSelectedProviderConfig" :metadata="configSchema"
            metadataKey="provider" :is-editing="updatingMode" />
        </v-card-text>

        <v-divider></v-divider>

        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showProviderCfg = false" :disabled="loading">
            {{ tm('dialogs.config.cancel') }}
          </v-btn>
          <v-btn color="primary" @click="newProvider" :loading="loading">
            {{ tm('dialogs.config.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 已配置模型编辑对话框 -->
    <v-dialog v-model="showProviderEditDialog" width="800">
      <v-card :title="providerEditData?.id || tm('dialogs.config.editTitle')">
        <v-card-text class="py-4">
          <small style="color: gray;">不建议修改 ID，可能会导致指向该模型的相关配置（如默认模型、插件相关配置等）失效。旧版本 AstrBot 的 “提供商 ID” 是下方的 “ID”。</small>
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

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="top">
      {{ snackbar.message }}
    </v-snackbar>

    <!-- Agent Runner 测试提示对话框 -->
    <v-dialog v-model="showAgentRunnerDialog" max-width="520" persistent>
      <v-card>
        <v-card-title class="text-h3 d-flex align-center">
          <v-icon start class="me-2">mdi-information</v-icon>
          请前往「配置文件」页测试 Agent 执行器
        </v-card-title>
        <v-card-text class="py-4 text-body-1 text-medium-emphasis">
          Agent 执行器的测试请在「配置文件」页进行。
          <ol class="ml-4 mt-4 mb-4">
            <li>找到对应的配置文件并打开。</li>
            <li>找到 Agent 执行方式部分，修改执行器后点击保存。</li>
            <li>点击右下角的 💬 聊天按钮进行测试。</li>
          </ol>
          要让机器人应用这个 Agent 执行器，你也需要前往修改 Agent 执行器。
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="showAgentRunnerDialog = false">好的</v-btn>
          <v-btn color="primary" variant="flat" @click="goToConfigPage">点击前往</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue'
import ItemCard from '@/components/shared/ItemCard.vue'
import AddNewProvider from '@/components/provider/AddNewProvider.vue'
import ProviderModelsPanel from '@/components/provider/ProviderModelsPanel.vue'
import ProviderSourcesPanel from '@/components/provider/ProviderSourcesPanel.vue'
import { useProviderSources } from '@/composables/useProviderSources'
import { getProviderIcon } from '@/utils/providerUtils'

const props = defineProps({
  defaultTab: {
    type: String,
    default: 'chat_completion'
  }
})

const { tm } = useModuleI18n('features/provider')
const router = useRouter()

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
  getSourceDisplayName,
  supportsImageInput,
  supportsToolCall,
  supportsReasoning,
  formatContextLimit,
  updateDefaultTab,
  selectProviderSource,
  addProviderSource,
  deleteProviderSource,
  saveProviderSource,
  fetchAvailableModels,
  addModelProvider,
  deleteProvider,
  modelAlreadyConfigured,
  testProvider,
  loadConfig,
} = useProviderSources({
  defaultTab: props.defaultTab,
  tm,
  showMessage
})

// 非 chat 类型的状态
const showAddProviderDialog = ref(false)
const showProviderCfg = ref(false)
const newSelectedProviderName = ref('')
const newSelectedProviderConfig = ref({})
const newProviderOriginalId = ref('')
const updatingMode = ref(false)
const loading = ref(false)
const providerStatuses = ref([])
const showAgentRunnerDialog = ref(false)
const showProviderEditDialog = ref(false)
const providerEditData = ref(null)
const providerEditOriginalId = ref('')
const showManualModelDialog = ref(false)

const savingProviders = ref([])

function openProviderEdit(provider) {
  providerEditData.value = JSON.parse(JSON.stringify(provider))
  providerEditOriginalId.value = provider.id
  showProviderEditDialog.value = true
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

watch(() => props.defaultTab, (val) => {
  updateDefaultTab(val)
})

// ===== 非 chat 类型的方法 =====
function getEmptyText() {
  return tm('providers.empty.typed', { type: selectedProviderType.value })
}

function selectProviderTemplate(name) {
  newSelectedProviderName.value = name
  newProviderOriginalId.value = ''
  showProviderCfg.value = true
  updatingMode.value = false
  newSelectedProviderConfig.value = JSON.parse(JSON.stringify(
    configSchema.value.provider.config_template[name] || {}
  ))
}

function configExistingProvider(provider) {
  newSelectedProviderName.value = provider.id
  newProviderOriginalId.value = provider.id
  newSelectedProviderConfig.value = {}

  // 比对默认配置模版，看看是否有更新
  let templates = configSchema.value.provider.config_template || {}
  let defaultConfig = {}
  for (let key in templates) {
    if (templates[key]?.type === provider.type) {
      defaultConfig = templates[key]
      break
    }
  }

  const mergeConfigWithOrder = (target, source, reference) => {
    if (source && typeof source === 'object' && !Array.isArray(source)) {
      for (let key in source) {
        if (source.hasOwnProperty(key)) {
          if (typeof source[key] === 'object' && source[key] !== null) {
            target[key] = Array.isArray(source[key]) ? [...source[key]] : { ...source[key] }
          } else {
            target[key] = source[key]
          }
        }
      }
    }

    for (let key in reference) {
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

  showProviderCfg.value = true
  updatingMode.value = true
}

async function newProvider() {
  loading.value = true
  const wasUpdating = updatingMode.value
  try {
    if (wasUpdating) {
      const res = await axios.post('/api/config/provider/update', {
        id: newProviderOriginalId.value || newSelectedProviderName.value,
        config: newSelectedProviderConfig.value
      })
      if (res.data.status === 'error') {
        showMessage(res.data.message || "更新失败!", 'error')
        return
      }
      showMessage(res.data.message || "更新成功!")
      if (wasUpdating) {
        updatingMode.value = false
      }
    } else {
      const res = await axios.post('/api/config/provider/new', newSelectedProviderConfig.value)
      if (res.data.status === 'error') {
        showMessage(res.data.message || "添加失败!", 'error')
        return
      }
      showMessage(res.data.message || "添加成功!")
    }
    showProviderCfg.value = false
  } catch (err) {
    showMessage(err.response?.data?.message || err.message, 'error')
  } finally {
    loading.value = false
    await loadConfig()
  }
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

async function copyProvider(providerToCopy) {
  const newProviderConfig = JSON.parse(JSON.stringify(providerToCopy))

  const generateUniqueId = (baseId) => {
    let newId = `${baseId}_copy`
    let counter = 1
    const existingIds = providers.value.map(p => p.id)
    while (existingIds.includes(newId)) {
      newId = `${baseId}_copy_${counter}`
      counter++
    }
    return newId
  }
  newProviderConfig.id = generateUniqueId(providerToCopy.id)
  newProviderConfig.enable = false

  loading.value = true
  try {
    const res = await axios.post('/api/config/provider/new', newProviderConfig)
    showMessage(res.data.message || `成功复制并创建了 ${newProviderConfig.id}`)
    await loadConfig()
  } catch (err) {
    showMessage(err.response?.data?.message || err.message, 'error')
  } finally {
    loading.value = false
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

function isProviderTesting(providerId) {
  return testingProviders.value.includes(providerId)
}

function getProviderStatus(providerId) {
  return providerStatuses.value.find(s => s.id === providerId)
}

async function testSingleProvider(provider) {
  if (isProviderTesting(provider.id)) return

  testingProviders.value.push(provider.id)

  const statusIndex = providerStatuses.value.findIndex(s => s.id === provider.id)
  const pendingStatus = {
    id: provider.id,
    name: provider.id,
    status: 'pending',
    error: null
  }
  if (statusIndex !== -1) {
    providerStatuses.value.splice(statusIndex, 1, pendingStatus)
  } else {
    providerStatuses.value.unshift(pendingStatus)
  }

  try {
    if (!provider.enable) {
      throw new Error('该提供商未被用户启用')
    }
    if (provider.provider_type === 'agent_runner') {
      showAgentRunnerDialog.value = true
      providerStatuses.value = providerStatuses.value.filter(s => s.id !== provider.id)
      return
    }

    const res = await axios.get(`/api/config/provider/check_one?id=${provider.id}`)
    if (res.data && res.data.status === 'ok') {
      const index = providerStatuses.value.findIndex(s => s.id === provider.id)
      if (index !== -1) {
        providerStatuses.value.splice(index, 1, res.data.data)
      }
    } else {
      throw new Error(res.data?.message || `Failed to check status for ${provider.id}`)
    }
  } catch (err) {
    const errorMessage = err.response?.data?.message || err.message || 'Unknown error'
    const index = providerStatuses.value.findIndex(s => s.id === provider.id)
    const failedStatus = {
      id: provider.id,
      name: provider.id,
      status: 'unavailable',
      error: errorMessage
    }
    if (index !== -1) {
      providerStatuses.value.splice(index, 1, failedStatus)
    }
  } finally {
    const index = testingProviders.value.indexOf(provider.id)
    if (index > -1) {
      testingProviders.value.splice(index, 1)
    }
  }
}

function getStatusColor(status) {
  switch (status) {
    case 'available':
      return 'success'
    case 'unavailable':
      return 'error'
    case 'pending':
      return 'grey'
    default:
      return 'default'
  }
}

function getStatusText(status) {
  const messages = {
    available: tm('availability.available'),
    unavailable: tm('availability.unavailable'),
    pending: tm('availability.pending')
  }
  return messages[status] || status
}

function goToConfigPage() {
  router.push('/config')
  showAgentRunnerDialog.value = false
}

</script>

<style scoped>
.provider-page {
  padding: 20px;
  padding-top: 8px;
  padding-bottom: 40px;
}

.provider-config-card {
  min-height: 280px;
}

@media (max-width: 960px) {
  .provider-config-card {
    min-height: auto;
  }
}
</style>
