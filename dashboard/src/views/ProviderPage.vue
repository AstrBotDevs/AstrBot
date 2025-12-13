<template>
  <div class="provider-page">
    <v-container fluid class="pa-0">
      <!-- 页面标题 -->
      <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-8">
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
          <v-tab
            v-for="type in providerTypes"
            :key="type.value"
            :value="type.value"
            class="font-weight-medium px-3">
            <v-icon start>{{ type.icon }}</v-icon>
            {{ type.label }}
          </v-tab>
        </v-tabs>

        <!-- Chat Completion: 三栏布局 -->
        <!-- Chat Completion: 三栏布局 -->
        <v-row v-if="selectedProviderType === 'chat_completion'" class="fill-height" no-gutters>
          <!-- 左栏：Provider Sources 列表 -->
          <v-col cols="3" class="provider-sources-column">
            <v-card flat class="fill-height rounded-0 border-e">
              <v-card-title class="d-flex align-center justify-space-between pa-4 pb-2">
                <span class="text-subtitle-1 font-weight-bold">{{ tm('providerSources.title') }}</span>
                <v-menu>
                  <template v-slot:activator="{ props }">
                    <v-btn
                      v-bind="props"
                      size="small"
                      icon="mdi-plus"
                      variant="tonal"
                      color="primary">
                    </v-btn>
                  </template>
                  <v-list density="compact">
                    <v-list-item
                      v-for="sourceType in availableSourceTypes"
                      :key="sourceType.value"
                      @click="addProviderSource(sourceType.value)">
                      <v-list-item-title>{{ sourceType.label }}</v-list-item-title>
                    </v-list-item>
                  </v-list>
                </v-menu>
              </v-card-title>
              
              <v-divider></v-divider>
              
              <div class="provider-sources-list pa-2" style="height: calc(100vh - 250px); overflow-y: auto;">
                <v-list v-if="filteredProviderSources.length > 0" density="compact" class="pa-0">
                  <v-list-item
                    v-for="source in filteredProviderSources"
                    :key="source.id"
                    :value="source.id"
                    :active="selectedProviderSource?.id === source.id"
                    @click="selectProviderSource(source)"
                    rounded="lg"
                    class="mb-1">
                    <v-list-item-title>{{ source.id }}</v-list-item-title>
                    <template v-slot:append>
                      <v-btn
                        icon="mdi-delete"
                        size="x-small"
                        variant="text"
                        color="error"
                        @click.stop="deleteProviderSource(source)">
                      </v-btn>
                    </template>
                  </v-list-item>
                </v-list>
                <div v-else class="text-center pa-8">
                  <v-icon size="48" color="grey-lighten-1">mdi-api-off</v-icon>
                  <p class="text-grey mt-2">{{ tm('providerSources.empty') }}</p>
                </div>
              </div>
            </v-card>
          </v-col>

          <!-- 右栏：配置详情 -->
          <v-col cols="9" class="provider-config-column">
            <v-card flat class="fill-height rounded-0 ml-4">
              <div v-if="selectedProviderSource" style="height: calc(100vh - 200px); overflow-y: auto;">
                <!-- Provider Source 配置 -->
                <v-card-title class="pa-4 pb-2 d-flex align-center justify-space-between">
                  <span class="text-h4 font-weight-bold">{{ selectedProviderSource.id }}</span>
                  <v-switch
                    v-model="selectedProviderSource.enable"
                    density="compact"
                    hide-details
                    inset
                    color="primary"
                    @change="isSourceModified = true">
                  </v-switch>
                </v-card-title>
                
                <v-card-text class="pa-4">
                  <!-- 基础配置（默认显示） -->
                  <div class="mb-4">
                    <AstrBotConfig
                      v-if="basicSourceConfig"
                      :iterable="basicSourceConfig"
                      :metadata="configSchema"
                      metadataKey="provider"
                      :is-editing="true" />
                  </div>

                  <!-- 高级配置（可展开） -->
                  <v-expansion-panels variant="accordion" class="mb-4">
                    <v-expansion-panel elevation="0" class="border rounded-lg">
                      <v-expansion-panel-title>
                        <span class="font-weight-medium">{{ tm('providerSources.advancedConfig') }}</span>
                      </v-expansion-panel-title>
                      <v-expansion-panel-text>
                        <AstrBotConfig
                          v-if="advancedSourceConfig"
                          :iterable="advancedSourceConfig"
                          :metadata="configSchema"
                          metadataKey="provider"
                          :is-editing="true" />
                      </v-expansion-panel-text>
                    </v-expansion-panel>
                  </v-expansion-panels>

                  <!-- 获取模型按钮 -->
                  <div class="d-flex align-center mb-4">
                    <v-btn
                      color="primary"
                      prepend-icon="mdi-download"
                      :loading="loadingModels"
                      @click="fetchAvailableModels"
                      variant="tonal">
                      {{ isSourceModified ? tm('providerSources.saveAndFetchModels') : tm('providerSources.fetchModels') }}
                    </v-btn>
                    <v-btn
                      class="ml-2"
                      color="success"
                      prepend-icon="mdi-content-save"
                      :loading="savingSource"
                      @click="saveProviderSource"
                      variant="flat">
                      {{ tm('providerSources.save') }}
                    </v-btn>
                  </div>

                  <!-- 可用模型列表 -->
                  <div v-if="availableModels.length > 0" class="mt-4">
                    <h3 class="text-h5 font-weight-bold mb-3">{{ tm('models.available') }}</h3>
                    <v-list density="compact" class="rounded-lg border" style="max-height: 200px;">
                      <v-list-item
                        v-for="model in availableModels"
                        :key="model"
                        @click="addModelProvider(model)"
                        class="cursor-pointer">
                        <v-list-item-title>{{ model }}</v-list-item-title>
                        <template v-slot:append>
                          <v-btn
                            icon="mdi-plus"
                            size="small"
                            variant="text"
                            color="primary">
                          </v-btn>
                        </template>
                      </v-list-item>
                    </v-list>
                  </div>

                  <!-- 已添加的模型（Providers） -->
                  <div class="mt-4">
                    <h3 class="text-h5 font-weight-bold mb-3">{{ tm('models.configured') }}</h3>
                    <div v-if="sourceProviders.length > 0">
                      <v-expansion-panels variant="accordion" class="mb-2">
                        <v-expansion-panel
                          v-for="provider in sourceProviders"
                          :key="provider.id"
                          elevation="0"
                          class="border mb-2 rounded-lg">
                          <v-expansion-panel-title>
                            <div class="d-flex align-center justify-space-between" style="width: 100%;">
                              <div>
                                <strong>{{ provider.id }}</strong>
                                <span class="text-caption text-grey ml-2">{{ provider.model_config?.model }}</span>
                              </div>
                              <div class="d-flex align-center" @click.stop>
                                <v-switch
                                  v-model="provider.enable"
                                  density="compact"
                                  hide-details
                                  color="primary"
                                  class="mr-2">
                                </v-switch>
                                <v-btn
                                  icon="mdi-test-tube"
                                  size="small"
                                  variant="text"
                                  color="info"
                                  :loading="testingProviders.includes(provider.id)"
                                  @click.stop="testProvider(provider)"
                                  class="mr-1">
                                </v-btn>
                                <v-btn
                                  icon="mdi-delete"
                                  size="small"
                                  variant="text"
                                  color="error"
                                  @click.stop="deleteProvider(provider)">
                                </v-btn>
                              </div>
                            </div>
                          </v-expansion-panel-title>
                          <v-expansion-panel-text>
                            <AstrBotConfig
                              :iterable="provider"
                              :metadata="configSchema"
                              metadataKey="provider"
                              :is-editing="true" />
                          </v-expansion-panel-text>
                        </v-expansion-panel>
                      </v-expansion-panels>
                    </div>
                    <div v-else class="text-center pa-4 border rounded-lg">
                      <v-icon size="48" color="grey-lighten-1">mdi-package-variant</v-icon>
                      <p class="text-grey mt-2">{{ tm('models.empty') }}</p>
                    </div>
                  </div>
                </v-card-text>
              </div>
              <div v-else class="text-center pa-12">
                <v-icon size="96" color="grey-lighten-1">mdi-cursor-default-click</v-icon>
                <p class="text-h5 text-grey mt-4">{{ tm('providerSources.selectHint') }}</p>
              </div>
            </v-card>
          </v-col>
        </v-row>

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
                :loading="isProviderTesting(provider.id)" @toggle-enabled="providerStatusChange"
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
    <AddNewProvider v-model:show="showAddProviderDialog" :metadata="metadata"
      @select-template="selectProviderTemplate" />

    <!-- 配置对话框 -->
    <v-dialog v-model="showProviderCfg" width="900" persistent>
      <v-card
        :title="updatingMode ? tm('dialogs.config.editTitle') : tm('dialogs.config.addTitle') + ` ${newSelectedProviderName} ` + tm('dialogs.config.provider')">
        <v-card-text class="py-4">
          <AstrBotConfig :iterable="newSelectedProviderConfig" :metadata="metadata['provider_group']?.metadata"
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

    <!-- 消息提示 -->
    <v-snackbar
      v-model="snackbar.show"
      :color="snackbar.color"
      :timeout="3000"
      location="top">
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
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue'
import ItemCard from '@/components/shared/ItemCard.vue'
import AddNewProvider from '@/components/provider/AddNewProvider.vue'
import { getProviderIcon } from '@/utils/providerUtils'

const { tm } = useModuleI18n('features/provider')
const router = useRouter()

// ===== State =====
const config = ref({})
const metadata = ref({})
const providerSources = ref([])
const providers = ref([])
const selectedProviderType = ref('chat_completion')
const selectedProviderSource = ref(null)
const availableModels = ref([])
const loadingModels = ref(false)
const savingSource = ref(false)
const testingProviders = ref([])
const isSourceModified = ref(false)
const configSchema = ref({})
const providerTemplates = ref({})

// 非 chat 类型的状态
const showAddProviderDialog = ref(false)
const showProviderCfg = ref(false)
const newSelectedProviderName = ref('')
const newSelectedProviderConfig = ref({})
const updatingMode = ref(false)
const loading = ref(false)
const providerStatuses = ref([])
const showAgentRunnerDialog = ref(false)

const snackbar = ref({
  show: false,
  message: '',
  color: 'success'
})

// ===== Provider Types =====
const providerTypes = [
  { value: 'chat_completion', label: tm('providers.tabs.chatCompletion'), icon: 'mdi-message-text' },
  { value: 'agent_runner', label: tm('providers.tabs.agentRunner'), icon: 'mdi-robot' },
  { value: 'speech_to_text', label: tm('providers.tabs.speechToText'), icon: 'mdi-microphone-message' },
  { value: 'text_to_speech', label: tm('providers.tabs.textToSpeech'), icon: 'mdi-volume-high' },
  { value: 'embedding', label: tm('providers.tabs.embedding'), icon: 'mdi-code-json' },
  { value: 'rerank', label: tm('providers.tabs.rerank'), icon: 'mdi-compare-vertical' }
]

// ===== Computed =====
const availableSourceTypes = computed(() => {
  // 从 providerTemplates 中动态获取可用的 source types
  if (!providerTemplates.value || Object.keys(providerTemplates.value).length === 0) {
    return []
  }
  
  const types = []
  for (const [templateName, template] of Object.entries(providerTemplates.value)) {
    // 根据 provider_type 筛选
    if (template.provider_type === selectedProviderType.value) {
      types.push({
        value: templateName,  // 使用 key 作为 value
        label: templateName
      })
    }
  }
  
  return types
})

const filteredProviderSources = computed(() => {
  if (!providerSources.value) return []
  
  return providerSources.value.filter(source =>
    source.provider_type === selectedProviderType.value ||
    (source.type && isTypeMatchingProviderType(source.type, selectedProviderType.value))
  )
})

const sourceProviders = computed(() => {
  if (!selectedProviderSource.value || !providers.value) return []
  
  return providers.value.filter(p =>
    p.provider_source_id === selectedProviderSource.value.id
  )
})

// 基础配置：只包含常用字段
const basicSourceConfig = computed(() => {
  if (!selectedProviderSource.value) return null
  
  const basicFields = ['id', 'key', 'api_base']
  const basic = {}
  
  for (const [key, value] of Object.entries(selectedProviderSource.value)) {
    if (basicFields.includes(key)) {
      basic[key] = value
    }
  }
  
  return basic
})

// 高级配置：过滤掉基础字段
const advancedSourceConfig = computed(() => {
  if (!selectedProviderSource.value) return null
  
  const basicFields = ['id', 'key', 'api_base', 'enable', 'type', 'provider_type']
  const advanced = {}
  
  for (const [key, value] of Object.entries(selectedProviderSource.value)) {
    if (!basicFields.includes(key)) {
      advanced[key] = value
    }
  }
  
  return advanced
})

// 非 chat 类型的 providers
const filteredProviders = computed(() => {
  if (!config.value.provider || selectedProviderType.value === 'chat_completion') {
    return []
  }

  return config.value.provider.filter(provider => {
    return getProviderType(provider) === selectedProviderType.value
  })
})

// ===== Helper Functions =====
function isTypeMatchingProviderType(type, providerType) {
  // 根据 type 判断是否匹配 provider_type
  if (providerType === 'chat_completion') {
    return type && type.includes('chat_completion')
  }
  return type && type.includes(providerType)
}

function extractSourceFieldsFromProvider(provider) {
  // provider 只保留这些字段，其他都是 source 字段
  const providerOnlyKeys = ['id', 'provider_source_id', 'model', 'modalities', 'custom_extra_body']
  const sourceFields = {}
  
  for (const [key, value] of Object.entries(provider)) {
    if (!providerOnlyKeys.includes(key)) {
      sourceFields[key] = value
    }
  }
  
  return sourceFields
}

// ===== Methods =====
function showMessage(message, color = 'success') {
  snackbar.value = { show: true, message, color }
}

function selectProviderType(type) {
  selectedProviderType.value = type
  selectedProviderSource.value = null
  availableModels.value = []
}

function selectProviderSource(source) {
  selectedProviderSource.value = source
  availableModels.value = []
  isSourceModified.value = false
}


function addProviderSource(templateKey) {
  // 从模板中找到对应的配置，使用 key 而不是 type
  const template = providerTemplates.value[templateKey]
  if (!template) {
    showMessage('未找到对应的模板配置', 'error')
    return
  }
  
  // 使用模板中的默认 ID
  const newId = template.id
  const newSource = {
    id: newId,
    type: template.type,
    provider_type: template.provider_type,
    enable: true,
    // 复制模板中的字段（排除 id, enable, type, provider_type, model_config 等 provider 特有字段）
    ...extractSourceFieldsFromTemplate(template)
  }
  
  providerSources.value.push(newSource)
  selectedProviderSource.value = newSource
  isSourceModified.value = true
}

function extractSourceFieldsFromTemplate(template) {
  // 从模板中提取 source 相关的字段
  const sourceFields = {}
  const excludeKeys = [
    'id', 'enable', 'type', 'provider_type', 'model_config', 'model', 
    'provider_source_id', 'provider', 'hint', 'modalities', 
    'custom_extra_body', 'custom_headers'
  ]
  
  for (const [key, value] of Object.entries(template)) {
    if (!excludeKeys.includes(key)) {
      sourceFields[key] = value
    }
  }
  
  return sourceFields
}

async function deleteProviderSource(source) {
  if (!confirm(tm('providerSources.deleteConfirm', { id: source.id }))) return
  
  try {
    // 删除关联的 providers
    providers.value = providers.value.filter(p => p.provider_source_id !== source.id)
    // 删除 provider source
    providerSources.value = providerSources.value.filter(s => s.id !== source.id)
    
    if (selectedProviderSource.value?.id === source.id) {
      selectedProviderSource.value = null
    }
    
    await saveConfig()
    showMessage(tm('providerSources.deleteSuccess'))
  } catch (error) {
    showMessage(error.message || tm('providerSources.deleteError'), 'error')
  }
}

async function saveProviderSource() {
  if (!selectedProviderSource.value) return
  
  savingSource.value = true
  try {
    await saveConfig()
    isSourceModified.value = false
    showMessage(tm('providerSources.saveSuccess'))
  } catch (error) {
    showMessage(error.message || tm('providerSources.saveError'), 'error')
  } finally {
    savingSource.value = false
  }
}


async function fetchAvailableModels() {
  if (!selectedProviderSource.value) return
  
  // 如果配置被修改，先保存
  if (isSourceModified.value) {
    await saveProviderSource()
  }
  
  loadingModels.value = true
  try {
    const response = await axios.get(
      `/api/config/provider_sources/${selectedProviderSource.value.id}/models`
    )
    if (response.data.status === 'ok') {
      availableModels.value = response.data.data.models || []
      if (availableModels.value.length === 0) {
        showMessage(tm('models.noModelsFound'), 'info')
      }
    } else {
      throw new Error(response.data.message)
    }
  } catch (error) {
    showMessage(error.response?.data?.message || error.message || tm('models.fetchError'), 'error')
  } finally {
    loadingModels.value = false
  }
}

function addModelProvider(modelName) {
  if (!selectedProviderSource.value) return
  
  const newId = `${selectedProviderSource.value.id}_${modelName}_${Date.now()}`
  const newProvider = {
    id: newId,
    provider_source_id: selectedProviderSource.value.id,
    model: modelName,
    modalities: [],
    custom_extra_body: {}
  }
  
  providers.value.push(newProvider)
  isSourceModified.value = true
  showMessage(tm('models.addSuccess', { model: modelName }))
}

async function deleteProvider(provider) {
  if (!confirm(tm('models.deleteConfirm', { id: provider.id }))) return
  
  try {
    providers.value = providers.value.filter(p => p.id !== provider.id)
    await saveConfig()
    showMessage(tm('models.deleteSuccess'))
  } catch (error) {
    showMessage(error.message || tm('models.deleteError'), 'error')
  }
}

async function testProvider(provider) {
  testingProviders.value.push(provider.id)
  try {
    const response = await axios.get('/api/config/provider/check_one', {
      params: { provider_id: provider.id }
    })
    if (response.data.status === 'ok') {
      showMessage(tm('models.testSuccess', { id: provider.id }))
    } else {
      throw new Error(response.data.message)
    }
  } catch (error) {
    showMessage(error.response?.data?.message || error.message || tm('models.testError'), 'error')
  } finally {
    testingProviders.value = testingProviders.value.filter(id => id !== provider.id)
  }
}

async function saveConfig() {
  try {
    config.value.provider_sources = providerSources.value
    config.value.provider = providers.value
    
    await axios.post('/api/config/astrbot/update', {
      config: config.value,
      conf_id: 'default'
    })
  } catch (error) {
    throw error
  }
}

async function loadConfig() {
  try {
    const response = await axios.get('/api/config/get')
    if (response.data.status === 'ok') {
      config.value = response.data.data.config
      providerSources.value = config.value.provider_sources || []
      providers.value = config.value.provider || []
    }
  } catch (error) {
    showMessage(error.message || 'Failed to load config', 'error')
  }
}


async function loadProviderTemplate() {
  try {
    const response = await axios.get('/api/config/provider/template')
    if (response.data.status === 'ok') {
      configSchema.value = response.data.data.config_schema || {}
      // 从 config_schema 中提取 provider templates
      if (configSchema.value.provider?.config_template) {
        providerTemplates.value = configSchema.value.provider.config_template
      }
    }
  } catch (error) {
    console.error('Failed to load provider template:', error)
  }
}

// ===== Lifecycle =====
onMounted(async () => {
  await loadConfig()
  await loadProviderTemplate()
  await loadMetadata()
})

// ===== 非 chat 类型的方法 =====
function getProviderType(provider) {
  if (!provider) return undefined
  if (provider.provider_type) {
    return provider.provider_type
  }
  // 兼容旧版本的 mapping
  const oldVersionProviderTypeMapping = {
    "openai_chat_completion": "chat_completion",
    "anthropic_chat_completion": "chat_completion",
    "googlegenai_chat_completion": "chat_completion",
    "zhipu_chat_completion": "chat_completion",
    "dify": "agent_runner",
    "coze": "agent_runner",
    "dashscope": "chat_completion",
    "openai_whisper_api": "speech_to_text",
    "openai_whisper_selfhost": "speech_to_text",
    "sensevoice_stt_selfhost": "speech_to_text",
    "openai_tts_api": "text_to_speech",
    "edge_tts": "text_to_speech",
    "gsvi_tts_api": "text_to_speech",
    "fishaudio_tts_api": "text_to_speech",
    "dashscope_tts": "text_to_speech",
    "azure_tts": "text_to_speech",
    "minimax_tts_api": "text_to_speech",
    "volcengine_tts": "text_to_speech",
  }
  return oldVersionProviderTypeMapping[provider.type]
}

function getEmptyText() {
  return tm('providers.empty.typed', { type: selectedProviderType.value })
}

function selectProviderTemplate(name) {
  newSelectedProviderName.value = name
  showProviderCfg.value = true
  updatingMode.value = false
  newSelectedProviderConfig.value = JSON.parse(JSON.stringify(
    metadata.value['provider_group']?.metadata?.provider?.config_template[name] || {}
  ))
}

function configExistingProvider(provider) {
  newSelectedProviderName.value = provider.id
  newSelectedProviderConfig.value = {}

  // 比对默认配置模版，看看是否有更新
  let templates = metadata.value['provider_group']?.metadata?.provider?.config_template || {}
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
        id: newSelectedProviderName.value,
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

async function copyProvider(providerToCopy) {
  const newProviderConfig = JSON.parse(JSON.stringify(providerToCopy))

  const generateUniqueId = (baseId) => {
    let newId = `${baseId}_copy`
    let counter = 1
    const existingIds = config.value.provider.map(p => p.id)
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

function providerStatusChange(provider) {
  provider.enable = !provider.enable

  axios.post('/api/config/provider/update', {
    id: provider.id,
    config: provider
  }).then((res) => {
    if (res.data.status === 'error') {
      showMessage(res.data.message, 'error')
      return
    }
    loadConfig()
    showMessage(res.data.message || tm('messages.success.statusUpdate'))
  }).catch((err) => {
    provider.enable = !provider.enable
    showMessage(err.response?.data?.message || err.message, 'error')
  })
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

async function loadMetadata() {
  try {
    const response = await axios.get('/api/config/get')
    if (response.data.status === 'ok') {
      metadata.value = response.data.data.metadata
    }
  } catch (error) {
    console.error('Failed to load metadata:', error)
  }
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

.provider-sources-column,
.provider-config-column {
  height: calc(100vh - 200px);
}

.cursor-pointer {
  cursor: pointer;
}

.border {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.border-e {
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
