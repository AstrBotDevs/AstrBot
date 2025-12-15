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
          <v-tab v-for="type in providerTypes" :key="type.value" :value="type.value" class="font-weight-medium px-3">
            <v-icon start>{{ type.icon }}</v-icon>
            {{ type.label }}
          </v-tab>
        </v-tabs>

        <!-- Chat Completion: 左侧列表 + 右侧上下卡片布局 -->
        <div v-if="selectedProviderType === 'chat_completion'">
          <v-row class="mt-2" style="height: calc(100vh - 300px);">
            <v-col cols="12" md="4" lg="3" class="pr-md-4">
              <v-card class="provider-sources-panel h-100" elevation="0">
                <div class="d-flex align-center justify-space-between px-4 pt-4 pb-2">
                  <div class="d-flex align-center ga-2">
                    <h2 class="mb-0">{{ tm('providerSources.title') }}</h2>
                    <v-chip size="x-small" color="primary" variant="tonal">{{ filteredProviderSources.length }}</v-chip>
                  </div>
                  <v-menu>
                    <template v-slot:activator="{ props }">
                      <v-btn v-bind="props" prepend-icon="mdi-plus" color="primary" variant="tonal" rounded="xl" size="small">
                        新增
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
                </div>

                <div v-if="filteredProviderSources.length > 0">
                  <v-list class="provider-source-list" nav density="compact" lines="two">
                    <v-list-item
                      v-for="source in filteredProviderSources"
                      :key="source.id"
                      :value="source.id"
                      :active="selectedProviderSource?.id === source.id"
                      :class="['provider-source-list-item', { 'provider-source-list-item--active': selectedProviderSource?.id === source.id }]"
                      rounded="lg"
                      @click="selectProviderSource(source)">
                      <template #prepend>
                        <v-avatar size="32" class="bg-grey-lighten-4" rounded="0">
                          <v-img v-if="source?.provider" :src="resolveSourceIcon(source)" alt="logo" cover></v-img>
                          <v-icon v-else size="32">mdi-creation</v-icon>
                        </v-avatar>
                      </template>
                      <v-list-item-title class="font-weight-bold">{{ source.id }}</v-list-item-title>
                      <v-list-item-subtitle class="text-truncate">{{ source.api_base || 'N/A' }}</v-list-item-subtitle>
                      <template #append>
                        <div class="d-flex align-center ga-1">
                          <v-btn icon="mdi-pencil" variant="text" size="x-small" color="primary" @click.stop="openSourceEditor(source)"></v-btn>
                          <v-btn icon="mdi-delete" variant="text" size="x-small" color="error" @click.stop="deleteProviderSource(source)"></v-btn>
                        </div>
                      </template>
                    </v-list-item>
                  </v-list>
                </div>
                <div v-else class="text-center py-8 px-4">
                  <v-icon size="48" color="grey-lighten-1">mdi-api-off</v-icon>
                  <p class="text-grey mt-2">{{ tm('providerSources.empty') }}</p>
                </div>
              </v-card>
            </v-col>

            <v-col cols="12" md="8" lg="9" class="pl-md-2">
              <v-row align="stretch">
                <v-col cols="12">
                  <v-card class="provider-config-card h-100" elevation="0">
                    <v-card-title class="d-flex align-center justify-space-between flex-wrap ga-3 pt-4 pl-5">
                      <div class="d-flex align-center ga-3" v-if="selectedProviderSource">
                        <div>
                          <div class="text-h4 font-weight-bold">{{ selectedProviderSource.id }}</div>
                          <div class="text-caption text-medium-emphasis">{{ selectedProviderSource.api_base || 'N/A' }}</div>
                        </div>
                      </div>
                      <div class="text-medium-emphasis" v-else>
                        {{ tm('providerSources.selectHint') }}
                      </div>

                      <div class="d-flex align-center ga-2" v-if="selectedProviderSource">
                        <v-btn color="primary" prepend-icon="mdi-download" :loading="loadingModels" @click="fetchAvailableModels" variant="tonal">
                          {{ isSourceModified ? tm('providerSources.saveAndFetchModels') : tm('providerSources.fetchModels') }}
                        </v-btn>
                        <v-btn color="success" prepend-icon="mdi-content-save" :loading="savingSource" @click="saveProviderSource" variant="flat">
                          {{ tm('providerSources.save') }}
                        </v-btn>
                      </div>
                    </v-card-title>

                    <v-card-text>
                      <template v-if="selectedProviderSource">
                        <div class="mb-4">
                          <AstrBotConfig v-if="basicSourceConfig" :iterable="basicSourceConfig" :metadata="configSchema"
                            metadataKey="provider" :is-editing="true" />
                        </div>

                        <v-expansion-panels variant="accordion" class="mb-4">
                          <v-expansion-panel elevation="0" class="border rounded-lg">
                            <v-expansion-panel-title>
                              <span class="font-weight-medium">{{ tm('providerSources.advancedConfig') }}</span>
                            </v-expansion-panel-title>
                            <v-expansion-panel-text>
                              <AstrBotConfig v-if="advancedSourceConfig" :iterable="advancedSourceConfig" :metadata="configSchema"
                                metadataKey="provider" :is-editing="true" />
                            </v-expansion-panel-text>
                          </v-expansion-panel>
                        </v-expansion-panels>

                        <div v-if="availableModels.length > 0" class="mt-2">
                          <h3 class="text-h6 font-weight-bold mb-2">{{ tm('models.available') }}</h3>
                          <v-list density="compact" class="rounded-lg border" style="max-height: 200px; overflow-y: auto; font-family:system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;">
                            <v-list-item v-for="model in availableModels" :key="model" @click="addModelProvider(model)" class="cursor-pointer">
                              <v-list-item-title>{{ model }}</v-list-item-title>
                              <template v-slot:append>
                                <v-btn icon="mdi-plus" size="small" variant="text" color="primary"></v-btn>
                              </template>
                            </v-list-item>
                          </v-list>
                        </div>
                      </template>
                      <div v-else class="text-center py-8 text-medium-emphasis">
                        <v-icon size="48" color="grey-lighten-1">mdi-cursor-default-click</v-icon>
                        <p class="mt-2">{{ tm('providerSources.selectHint') }}</p>
                      </div>
                    </v-card-text>
                  </v-card>
                </v-col>

                <v-col cols="12">
                  <v-card class="provider-models-card h-100" elevation="0">
                    <v-card-title class="d-flex align-center ga-3 pt-4 pl-5">
                      <h4 class="mb-0 font-weight-bold">
                        {{ tm('models.configured') }}
                      </h4>
                      <v-chip color="success" variant="tonal" size="small">{{ displayedChatProviders.length }}</v-chip>
                    </v-card-title>

                    <v-card-text class="mt-2">
                      <template v-if="selectedProviderSource">
                        <div v-if="sourceProviders.length > 0">
                          <v-expansion-panels v-model="sourceProviderPanels" variant="accordion" class="mb-2">
                            <v-expansion-panel
                              v-for="provider in sourceProviders"
                              :key="provider.id"
                              :value="provider.id"
                              elevation="0"
                              class="border mb-2 rounded-lg">
                              <v-expansion-panel-title>
                                <div class="d-flex align-center justify-space-between" style="width: 100%;">
                                  <div>
                                    <strong>{{ provider.id }}</strong>
                                    <span class="text-caption text-grey ml-2">{{ provider.model }}</span>
                                  </div>
                                  <div class="d-flex align-center" @click.stop>
                                    <v-switch v-model="provider.enable" density="compact" hide-details color="primary" class="mr-2"></v-switch>
                                    <v-btn icon="mdi-test-tube" size="small" variant="text" color="info"
                                      :loading="testingProviders.includes(provider.id)" @click.stop="testProvider(provider)"
                                      class="mr-1"></v-btn>
                                    <v-btn icon="mdi-content-save" size="small" variant="text" color="success"
                                      :loading="savingProviders.includes(provider.id)" @click.stop="saveSingleProvider(provider)"
                                      class="mr-1"></v-btn>
                                    <v-btn icon="mdi-delete" size="small" variant="text" color="error"
                                      @click.stop="deleteProvider(provider)"></v-btn>
                                  </div>
                                </div>
                              </v-expansion-panel-title>
                              <v-expansion-panel-text>
                                <AstrBotConfig :iterable="provider" :metadata="configSchema" metadataKey="provider"
                                  :is-editing="true" />
                              </v-expansion-panel-text>
                            </v-expansion-panel>
                          </v-expansion-panels>
                        </div>
                        <div v-else class="text-center pa-4 border rounded-lg">
                          <v-icon size="48" color="grey-lighten-1">mdi-package-variant</v-icon>
                          <p class="text-grey mt-2">{{ tm('models.empty') }}</p>
                        </div>
                      </template>
                      <div v-else class="text-center py-8 text-medium-emphasis">
                        <v-icon size="48" color="grey-lighten-1">mdi-cursor-default-click</v-icon>
                        <p class="mt-2">{{ tm('providerSources.selectHint') }}</p>
                      </div>
                    </v-card-text>
                  </v-card>
                </v-col>
              </v-row>
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
import { ref, computed, onMounted, nextTick, watch } from 'vue'
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
const selectedProviderSourceOriginalId = ref(null)
const editableProviderSource = ref(null)
const availableModels = ref([])
const loadingModels = ref(false)
const savingSource = ref(false)
const testingProviders = ref([])
const savingProviders = ref([])
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
const sourceProviderPanels = ref(null)

let suppressSourceWatch = false

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

const chatProviders = computed(() => {
  if (!providers.value) return []

  return providers.value.filter(provider => {
    const type = getProviderType(provider)
    if (type === 'chat_completion') return true

    const source = providerSources.value.find(s => s.id === provider.provider_source_id)
    if (!source) return false

    return source.provider_type === 'chat_completion' || isTypeMatchingProviderType(source.type, 'chat_completion')
  })
})

const displayedChatProviders = computed(() => {
  if (!chatProviders.value) return []

  if (selectedProviderSource.value) {
    return chatProviders.value.filter(p => p.provider_source_id === selectedProviderSource.value.id)
  }

  return chatProviders.value
})

// 基础配置：只包含常用字段
const basicSourceConfig = computed(() => {
  if (!editableProviderSource.value) return null

  const fields = ['id', 'key', 'api_base']
  const basic = {}

  fields.forEach(field => {
    Object.defineProperty(basic, field, {
      get() {
        return editableProviderSource.value[field]
      },
      set(val) {
        editableProviderSource.value[field] = val
      },
      enumerable: true
    })
  })

  return basic
})

// 高级配置：过滤掉基础字段
const advancedSourceConfig = computed(() => {
  if (!editableProviderSource.value) return null

  const excluded = ['id', 'key', 'api_base', 'enable', 'type', 'provider_type', "provider"]
  const advanced = {}

  for (const key of Object.keys(editableProviderSource.value)) {
    if (excluded.includes(key)) continue
    Object.defineProperty(advanced, key, {
      get() {
        return editableProviderSource.value[key]
      },
      set(val) {
        editableProviderSource.value[key] = val
      },
      enumerable: true
    })
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

function resolveSourceIcon(source) {
  if (!source) return ''

  return getProviderIcon(source.provider) || ''
}

function editProviderSourceFromModel(provider) {
  if (!provider) return

  const source = providerSources.value.find(s => s.id === provider.provider_source_id)
  if (!source) {
    showMessage(tm('providerSources.empty'), 'error')
    return
  }

  openSourceEditor(source)
  nextTick(() => {
    sourceProviderPanels.value = provider.id
  })
}

// ===== Methods =====
function showMessage(message, color = 'success') {
  snackbar.value = { show: true, message, color }
}

function selectProviderType(type) {
  selectedProviderType.value = type
  selectedProviderSource.value = null
  selectedProviderSourceOriginalId.value = null
  editableProviderSource.value = null
  availableModels.value = []
  sourceProviderPanels.value = null
}

function selectProviderSource(source) {
  selectedProviderSource.value = source
  selectedProviderSourceOriginalId.value = source?.id || null
  suppressSourceWatch = true
  editableProviderSource.value = source ? JSON.parse(JSON.stringify(source)) : null
  nextTick(() => {
    suppressSourceWatch = false
  })
  availableModels.value = []
  isSourceModified.value = false
  sourceProviderPanels.value = null
}

function openSourceEditor(source) {
  selectProviderSource(source)
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
    provider: template.provider,
    enable: true,
    // 复制模板中的字段（排除 id, enable, type, provider_type 等 provider 特有字段）
    ...extractSourceFieldsFromTemplate(template)
  }

  providerSources.value.push(newSource)
  selectedProviderSource.value = newSource
  selectedProviderSourceOriginalId.value = newId
  editableProviderSource.value = JSON.parse(JSON.stringify(newSource))
  isSourceModified.value = true
}

function extractSourceFieldsFromTemplate(template) {
  // 从模板中提取 source 相关的字段
  const sourceFields = {}
  const excludeKeys = [
    'id', 'enable', 'type', 'provider_type', 'model',
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
      selectedProviderSourceOriginalId.value = null
      editableProviderSource.value = null
      sourceProviderPanels.value = null
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
  const originalId = selectedProviderSourceOriginalId.value || selectedProviderSource.value.id
  try {
    const response = await axios.post(
      `/api/config/provider_sources/${originalId}/update`,
      {
        config: editableProviderSource.value,
        original_id: originalId
      }
    )

    if (response.data.status !== 'ok') {
      throw new Error(response.data.message)
    }

    if (editableProviderSource.value.id !== originalId) {
      providers.value = providers.value.map(p =>
        p.provider_source_id === originalId
          ? { ...p, provider_source_id: editableProviderSource.value.id }
          : p
      )
      selectedProviderSourceOriginalId.value = editableProviderSource.value.id
    }

    // 同步列表中的当前 source，并保持选中
    const idx = providerSources.value.findIndex(ps => ps.id === originalId)
    if (idx !== -1) {
      providerSources.value[idx] = JSON.parse(JSON.stringify(editableProviderSource.value))
      selectedProviderSource.value = providerSources.value[idx]
    }

    // 重新建立可编辑副本
    suppressSourceWatch = true
    editableProviderSource.value = selectedProviderSource.value
    nextTick(() => {
      suppressSourceWatch = false
    })

    isSourceModified.value = false
    showMessage(response.data.message || tm('providerSources.saveSuccess'))
    return true
  } catch (error) {
    showMessage(error.response?.data?.message || error.message || tm('providerSources.saveError'), 'error')
    return false
  } finally {
    savingSource.value = false
  }
}


async function fetchAvailableModels() {
  if (!selectedProviderSource.value) return

  // 如果配置被修改，先保存
  if (isSourceModified.value) {
    const saved = await saveProviderSource()
    if (!saved) {
      return
    }
  }

  loadingModels.value = true
  try {
    const sourceId = editableProviderSource.value?.id || selectedProviderSource.value.id
    const response = await axios.get(
      `/api/config/provider_sources/${sourceId}/models`
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

  const sourceId = editableProviderSource.value?.id || selectedProviderSource.value.id
  const newId = `${sourceId}/${modelName}`
  const newProvider = {
    id: newId,
    provider_source_id: sourceId,
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
    await axios.post('/api/config/provider/delete', { id: provider.id })
    providers.value = providers.value.filter(p => p.id !== provider.id)
    showMessage(tm('models.deleteSuccess'))
  } catch (error) {
    showMessage(error.message || tm('models.deleteError'), 'error')
  }
}

async function testProvider(provider) {
  testingProviders.value.push(provider.id)
  try {
    const response = await axios.get('/api/config/provider/check_one', {
      params: { id: provider.id }
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

async function saveSingleProvider(provider) {
  if (!provider) return

  const exists = (config.value.provider || []).some(p => p.id === provider.id)
  savingProviders.value.push(provider.id)
  try {
    const url = exists ? '/api/config/provider/update' : '/api/config/provider/new'
    const payload = exists ? { id: provider.id, config: provider } : provider
    const res = await axios.post(url, payload)
    if (res.data.status === 'error') {
      throw new Error(res.data.message)
    }
    showMessage(res.data.message || tm('providerSources.saveSuccess'))
    await loadConfig()
  } catch (err) {
    showMessage(err.response?.data?.message || err.message || tm('providerSources.saveError'), 'error')
  } finally {
    savingProviders.value = savingProviders.value.filter(id => id !== provider.id)
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

// 跟踪编辑中的 provider source 是否被修改
watch(editableProviderSource, () => {
  if (suppressSourceWatch) return
  if (!editableProviderSource.value) return
  isSourceModified.value = true
}, { deep: true })

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

.provider-sources-panel {
  min-height: 320px;
}

.provider-source-list {
  max-height: 620px;
  overflow-y: auto;
  padding: 6px 8px;
}

.provider-source-list-item {
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.provider-source-list-item--active {
  background-color: #E8F0FE;
  border: 1px solid rgba(var(--v-theme-primary), 0.25);
}

.provider-config-card,
.provider-models-card {
  min-height: 280px;
}

.cursor-pointer {
  cursor: pointer;
}

.border {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

@media (max-width: 960px) {
  .provider-source-list {
    max-height: none;
  }

  .provider-sources-panel,
  .provider-config-card,
  .provider-models-card {
    min-height: auto;
  }
}
</style>
