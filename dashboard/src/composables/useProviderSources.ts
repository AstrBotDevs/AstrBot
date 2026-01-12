import { ref, computed, onMounted, nextTick, watch } from 'vue'
import axios from 'axios'
import { getProviderIcon } from '@/utils/providerUtils'

export interface UseProviderSourcesOptions {
  defaultTab?: string
  tm: (key: string, params?: Record<string, unknown>) => string
  showMessage: (message: string, color?: string) => void
}

export function resolveDefaultTab(value?: string) {
  const normalized = (value || '').toLowerCase()

  if (normalized.startsWith('select_agent_runner_provider') || normalized === 'agent_runner') {
    return 'agent_runner'
  }

  if (normalized === 'select_provider_stt' || normalized === 'speech_to_text' || normalized.includes('stt')) {
    return 'speech_to_text'
  }

  if (normalized === 'select_provider_tts' || normalized === 'text_to_speech' || normalized.includes('tts')) {
    return 'text_to_speech'
  }

  if (normalized.includes('embedding')) {
    return 'embedding'
  }

  if (normalized.includes('rerank')) {
    return 'rerank'
  }

  return 'chat_completion'
}

export function useProviderSources(options: UseProviderSourcesOptions) {
  const { tm, showMessage } = options

  // ===== State =====
  const config = ref<Record<string, any>>({})
  const metadata = ref<Record<string, any>>({})
  const providerSources = ref<any[]>([])
  const providers = ref<any[]>([])
  const selectedProviderType = ref<string>(resolveDefaultTab(options.defaultTab))
  const selectedProviderSource = ref<any | null>(null)
  const selectedProviderSourceOriginalId = ref<string | null>(null)
  const editableProviderSource = ref<any | null>(null)
  const availableModels = ref<any[]>([])
  const modelMetadata = ref<Record<string, any>>({})
  const loadingModels = ref(false)
  const savingSource = ref(false)
  const testingProviders = ref<string[]>([])
  const isSourceModified = ref(false)
  const configSchema = ref<Record<string, any>>({})
  const providerTemplates = ref<Record<string, any>>({})
  const manualModelId = ref('')
  const modelSearch = ref('')

  let suppressSourceWatch = false

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
    if (!providerTemplates.value || Object.keys(providerTemplates.value).length === 0) {
      return []
    }

    const types: Array<{ value: string; label: string }> = []
    for (const [templateName, template] of Object.entries(providerTemplates.value)) {
      if (template.provider_type === selectedProviderType.value) {
        types.push({ value: templateName, label: templateName })
      }
    }

    return types
  })

  const filteredProviderSources = computed(() => {
    if (!providerSources.value) return []

    return providerSources.value.filter((source) =>
      source.provider_type === selectedProviderType.value ||
      (source.type && isTypeMatchingProviderType(source.type, selectedProviderType.value))
    )
  })

  const displayedProviderSources = computed(() => {
    return filteredProviderSources.value || []
  })

  const sourceProviders = computed(() => {
    if (!selectedProviderSource.value || !providers.value) return []

    return providers.value.filter((p) => p.provider_source_id === selectedProviderSource.value.id)
  })

  const existingModelsForSelectedSource = computed(() => {
    if (!selectedProviderSource.value) return new Set<string>()
    return new Set(sourceProviders.value.map((p: any) => p.model))
  })

  const sortedAvailableModels = computed(() => {
    const existing = existingModelsForSelectedSource.value
    return [...(availableModels.value || [])].sort((a, b) => {
      const aName = typeof a === 'string' ? a : a?.name
      const bName = typeof b === 'string' ? b : b?.name
      const aExists = existing.has(aName)
      const bExists = existing.has(bName)
      if (aExists && !bExists) return -1
      if (!aExists && bExists) return 1
      return 0
    })
  })

  const mergedModelEntries = computed(() => {
    const configuredEntries = (sourceProviders.value || []).map((provider: any) => ({
      type: 'configured',
      provider,
      metadata: getModelMetadata(provider.model)
    }))

    const availableEntries = (sortedAvailableModels.value || [])
      .filter((item: any) => {
        const name = typeof item === 'string' ? item : item?.name
        return !existingModelsForSelectedSource.value.has(name)
      })
      .map((item: any) => {
        const name = typeof item === 'string' ? item : item?.name
        return {
          type: 'available',
          model: name,
          metadata: typeof item === 'object' ? item?.metadata : getModelMetadata(name)
        }
      })

    return [...configuredEntries, ...availableEntries]
  })

  const filteredMergedModelEntries = computed(() => {
    const term = modelSearch.value.trim().toLowerCase()
    if (!term) return mergedModelEntries.value

    return mergedModelEntries.value.filter((entry: any) => {
      if (entry.type === 'configured') {
        const id = entry.provider.id?.toLowerCase() || ''
        const model = entry.provider.model?.toLowerCase() || ''
        return id.includes(term) || model.includes(term)
      }

      const model = entry.model?.toLowerCase() || ''
      return model.includes(term)
    })
  })

  const manualProviderId = computed(() => {
    if (!selectedProviderSource.value) return ''
    const modelId = manualModelId.value.trim()
    if (!modelId) return ''
    return `${selectedProviderSource.value.id}/${modelId}`
  })

  const basicSourceConfig = computed(() => {
    if (!editableProviderSource.value) return null

    const fields = ['id', 'key', 'api_base']
    const basic: Record<string, any> = {}

    fields.forEach((field) => {
      Object.defineProperty(basic, field, {
        get() {
          return editableProviderSource.value![field]
        },
        set(val) {
          editableProviderSource.value![field] = val
        },
        enumerable: true
      })
    })

    return basic
  })

  const advancedSourceConfig = computed(() => {
    if (!editableProviderSource.value) return null

    const excluded = ['id', 'key', 'api_base', 'enable', 'type', 'provider_type', 'provider']
    const advanced: Record<string, any> = {}

    for (const key of Object.keys(editableProviderSource.value)) {
      if (excluded.includes(key)) continue
      Object.defineProperty(advanced, key, {
        get() {
          return editableProviderSource.value![key]
        },
        set(val) {
          editableProviderSource.value![key] = val
        },
        enumerable: true
      })
    }

    return advanced
  })

  const filteredProviders = computed(() => {
    if (!providers.value || selectedProviderType.value === 'chat_completion') {
      return []
    }

    return providers.value.filter((provider: any) => getProviderType(provider) === selectedProviderType.value)
  })

  const providerSourceSchema = computed(() => {
    if (!configSchema.value || !configSchema.value.provider) {
      return configSchema.value
    }

    // 创建一个深拷贝以避免修改原始 schema
    const customSchema = JSON.parse(JSON.stringify(configSchema.value))

    // 为 provider source 的 id 字段添加自定义 hint
    if (customSchema.provider?.items?.id) {
      customSchema.provider.items.id.hint = tm('providerSources.hints.id')
      customSchema.provider.items.key.hint = tm('providerSources.hints.key')
      customSchema.provider.items.api_base.hint = tm('providerSources.hints.apiBase')
    }

    return customSchema
  })

  // ===== Watches =====
  watch(editableProviderSource, () => {
    if (suppressSourceWatch) return
    if (!editableProviderSource.value) return
    isSourceModified.value = true
  }, { deep: true })

  // ===== Helper Functions =====
  function isTypeMatchingProviderType(type?: string, providerType?: string) {
    if (!type || !providerType) return false
    if (providerType === 'chat_completion') {
      return type.includes('chat_completion')
    }
    return type.includes(providerType)
  }

  function resolveSourceIcon(source: any) {
    if (!source) return ''
    return getProviderIcon(source.provider) || ''
  }

  function getSourceDisplayName(source: any) {
    if (!source) return ''
    if (source.isPlaceholder) return source.templateKey || source.id || ''
    return source.id
  }

  function getModelMetadata(modelName?: string) {
    if (!modelName) return null
    return modelMetadata.value?.[modelName] || null
  }

  function supportsImageInput(meta: any) {
    const inputs = meta?.modalities?.input || []
    return inputs.includes('image')
  }

  function supportsToolCall(meta: any) {
    return Boolean(meta?.tool_call)
  }

  function supportsReasoning(meta: any) {
    return Boolean(meta?.reasoning)
  }

  function formatContextLimit(meta: any) {
    const ctx = meta?.limit?.context
    if (!ctx || typeof ctx !== 'number') return ''
    if (ctx >= 1_000_000) return `${Math.round(ctx / 1_000_000)}M`
    if (ctx >= 1_000) return `${Math.round(ctx / 1_000)}K`
    return `${ctx}`
  }

  function getProviderType(provider: any) {
    if (!provider) return undefined
    if (provider.provider_type) {
      return provider.provider_type
    }

    const oldVersionProviderTypeMapping: Record<string, string> = {
      openai_chat_completion: 'chat_completion',
      anthropic_chat_completion: 'chat_completion',
      googlegenai_chat_completion: 'chat_completion',
      zhipu_chat_completion: 'chat_completion',
      dify: 'agent_runner',
      coze: 'agent_runner',
      dashscope: 'chat_completion',
      openai_whisper_api: 'speech_to_text',
      openai_whisper_selfhost: 'speech_to_text',
      sensevoice_stt_selfhost: 'speech_to_text',
      openai_tts_api: 'text_to_speech',
      edge_tts: 'text_to_speech',
      gsvi_tts_api: 'text_to_speech',
      fishaudio_tts_api: 'text_to_speech',
      dashscope_tts: 'text_to_speech',
      azure_tts: 'text_to_speech',
      minimax_tts_api: 'text_to_speech',
      volcengine_tts: 'text_to_speech'
    }
    return oldVersionProviderTypeMapping[provider.type]
  }

  function selectProviderSource(source: any) {
    if (source?.isPlaceholder && source.templateKey) {
      addProviderSource(source.templateKey)
      return
    }

    selectedProviderSource.value = source
    selectedProviderSourceOriginalId.value = source?.id || null
    suppressSourceWatch = true
    editableProviderSource.value = source ? JSON.parse(JSON.stringify(source)) : null
    nextTick(() => {
      suppressSourceWatch = false
    })
    availableModels.value = []
    modelMetadata.value = {}
    isSourceModified.value = false
  }

  function extractSourceFieldsFromTemplate(template: Record<string, any>) {
    const sourceFields: Record<string, any> = {}
    const excludeKeys = ['id', 'enable', 'model', 'provider_source_id', 'modalities', 'custom_extra_body']

    for (const [key, value] of Object.entries(template)) {
      if (!excludeKeys.includes(key)) {
        sourceFields[key] = value
      }
    }

    return sourceFields
  }

  function generateUniqueSourceId(baseId: string) {
    const existingIds = new Set(providerSources.value.map((s: any) => s.id))
    if (!existingIds.has(baseId)) return baseId

    let counter = 1
    let candidate = `${baseId}_${counter}`
    while (existingIds.has(candidate)) {
      counter += 1
      candidate = `${baseId}_${counter}`
    }

    return candidate
  }

  function addProviderSource(templateKey: string) {
    const template = providerTemplates.value[templateKey]
    if (!template) {
      showMessage('未找到对应的模板配置', 'error')
      return
    }

    const newId = generateUniqueSourceId(template.id)
    const newSource = {
      ...extractSourceFieldsFromTemplate(template),
      id: newId,
      type: template.type,
      provider_type: template.provider_type,
      provider: template.provider,
      enable: true
    }

    providerSources.value.push(newSource)
    selectedProviderSource.value = newSource
    selectedProviderSourceOriginalId.value = newId
    editableProviderSource.value = JSON.parse(JSON.stringify(newSource))
    availableModels.value = []
    modelMetadata.value = {}
    isSourceModified.value = true
  }

  async function deleteProviderSource(source: any) {
    if (!confirm(tm('providerSources.deleteConfirm', { id: source.id }))) return

    try {
      await axios.post('/api/config/provider_sources/delete', { id: source.id })

      providers.value = providers.value.filter((p) => p.provider_source_id !== source.id)
      providerSources.value = providerSources.value.filter((s) => s.id !== source.id)

      if (selectedProviderSource.value?.id === source.id) {
        selectedProviderSource.value = null
        selectedProviderSourceOriginalId.value = null
        editableProviderSource.value = null
      }

      showMessage(tm('providerSources.deleteSuccess'))
    } catch (error: any) {
      showMessage(error.message || tm('providerSources.deleteError'), 'error')
    } finally {
      await loadConfig()
    }
  }

  async function saveProviderSource() {
    if (!selectedProviderSource.value) return

    savingSource.value = true
    const originalId = selectedProviderSourceOriginalId.value || selectedProviderSource.value.id
    try {
      const response = await axios.post('/api/config/provider_sources/update', {
        config: editableProviderSource.value,
        original_id: originalId
      })

      if (response.data.status !== 'ok') {
        throw new Error(response.data.message)
      }

      if (editableProviderSource.value!.id !== originalId) {
        providers.value = providers.value.map((p) =>
          p.provider_source_id === originalId
            ? { ...p, provider_source_id: editableProviderSource.value!.id }
            : p
        )
        selectedProviderSourceOriginalId.value = editableProviderSource.value!.id
      }

      const idx = providerSources.value.findIndex((ps) => ps.id === originalId)
      if (idx !== -1) {
        providerSources.value[idx] = JSON.parse(JSON.stringify(editableProviderSource.value))
        selectedProviderSource.value = providerSources.value[idx]
      }

      suppressSourceWatch = true
      editableProviderSource.value = selectedProviderSource.value
      nextTick(() => {
        suppressSourceWatch = false
      })

      isSourceModified.value = false
      showMessage(response.data.message || tm('providerSources.saveSuccess'))
      return true
    } catch (error: any) {
      showMessage(error.response?.data?.message || error.message || tm('providerSources.saveError'), 'error')
      return false
    } finally {
      savingSource.value = false
      loadConfig()
    }
  }

  async function fetchAvailableModels() {
    if (!selectedProviderSource.value) return

    if (isSourceModified.value) {
      const saved = await saveProviderSource()
      if (!saved) {
        return
      }
    }

    loadingModels.value = true
    try {
      const sourceId = editableProviderSource.value?.id || selectedProviderSource.value.id
      const response = await axios.get('/api/config/provider_sources/models', {
        params: { source_id: sourceId }
      })
      if (response.data.status === 'ok') {
        const metadataMap = response.data.data.model_metadata || {}
        modelMetadata.value = metadataMap
        availableModels.value = (response.data.data.models || []).map((model: string) => ({
          name: model,
          metadata: metadataMap?.[model] || null
        }))
        if (availableModels.value.length === 0) {
          showMessage(tm('models.noModelsFound'), 'info')
        }
      } else {
        throw new Error(response.data.message)
      }
    } catch (error: any) {
      modelMetadata.value = {}
      showMessage(error.response?.data?.message || error.message || tm('models.fetchError'), 'error')
    } finally {
      loadingModels.value = false
    }
  }

  async function addModelProvider(modelName: string) {
    if (!selectedProviderSource.value) return

    const sourceId = editableProviderSource.value?.id || selectedProviderSource.value.id
    const newId = `${sourceId}/${modelName}`

    const metadata = getModelMetadata(modelName)
    let modalities: string[]

    if (!metadata) {
      modalities = ['text', 'image', 'tool_use']
    } else {
      modalities = ['text']
      if (supportsImageInput(metadata)) {
        modalities.push('image')
      }
      if (supportsToolCall(metadata)) {
        modalities.push('tool_use')
      }
    }

    let max_context_tokens = 0
    if (metadata?.limit?.context && typeof metadata.limit.context === 'number') {
      max_context_tokens = metadata.limit.context
    }

    const newProvider = {
      id: newId,
      enable: false,
      provider_source_id: sourceId,
      model: modelName,
      modalities,
      custom_extra_body: {},
      max_context_tokens: max_context_tokens
    }

    try {
      const res = await axios.post('/api/config/provider/new', newProvider)
      if (res.data.status === 'error') {
        throw new Error(res.data.message)
      }
      providers.value.push(newProvider)
      showMessage(res.data.message || tm('models.addSuccess', { model: modelName }))
    } catch (error: any) {
      showMessage(error.response?.data?.message || error.message || tm('providerSources.saveError'), 'error')
    } finally {
      await loadConfig()
    }
  }

  function modelAlreadyConfigured(modelName: string) {
    return existingModelsForSelectedSource.value.has(modelName)
  }

  async function deleteProvider(provider: any) {
    if (!confirm(tm('models.deleteConfirm', { id: provider.id }))) return

    try {
      await axios.post('/api/config/provider/delete', { id: provider.id })
      providers.value = providers.value.filter((p) => p.id !== provider.id)
      showMessage(tm('models.deleteSuccess'))
    } catch (error: any) {
      showMessage(error.message || tm('models.deleteError'), 'error')
    } finally {
      await loadConfig()
    }
  }

  async function testProvider(provider: any) {
    testingProviders.value.push(provider.id)
    try {
      const response = await axios.get('/api/config/provider/check_one', { params: { id: provider.id } })
      if (response.data.status === 'ok' && response.data.data.error === null) {
        showMessage(tm('models.testSuccess', { id: provider.id }))
      } else {
        throw new Error(response.data.data.error || tm('models.testError'))
      }
    } catch (error: any) {
      showMessage(error.response?.data?.message || error.message || tm('models.testError'), 'error')
    } finally {
      testingProviders.value = testingProviders.value.filter((id) => id !== provider.id)
    }
  }

  async function loadConfig() {
    loadProviderTemplate()
  }

  async function loadProviderTemplate() {
    try {
      const response = await axios.get('/api/config/provider/template')
      if (response.data.status === 'ok') {
        configSchema.value = response.data.data.config_schema || {}
        if (configSchema.value.provider?.config_template) {
          providerTemplates.value = configSchema.value.provider.config_template
        }
        providerSources.value = response.data.data.provider_sources || []
        providers.value = response.data.data.providers || []
      }
    } catch (error) {
      console.error('Failed to load provider template:', error)
    }
  }

  function updateDefaultTab(value: string) {
    selectedProviderType.value = resolveDefaultTab(value)
  }

  onMounted(async () => {
    await loadProviderTemplate()
  })

  return {
    // state
    config,
    metadata,
    providerSources,
    providers,
    selectedProviderType,
    selectedProviderSource,
    selectedProviderSourceOriginalId,
    editableProviderSource,
    availableModels,
    modelMetadata,
    loadingModels,
    savingSource,
    testingProviders,
    isSourceModified,
    configSchema,
    providerTemplates,
    manualModelId,
    modelSearch,

    // computed
    providerTypes,
    availableSourceTypes,
    displayedProviderSources,
    sourceProviders,
    mergedModelEntries,
    filteredMergedModelEntries,
    filteredProviders,
    basicSourceConfig,
    advancedSourceConfig,
    manualProviderId,
    providerSourceSchema,

    // helpers
    resolveSourceIcon,
    getSourceDisplayName,
    getModelMetadata,
    supportsImageInput,
    supportsToolCall,
    supportsReasoning,
    formatContextLimit,
    getProviderType,

    // methods
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
    loadProviderTemplate
  }
}
