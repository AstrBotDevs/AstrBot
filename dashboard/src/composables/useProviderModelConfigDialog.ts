import { computed, ref, type Ref } from 'vue'
import { providerApi } from '@/api/v1'

interface UseProviderModelConfigDialogOptions {
  selectedProviderSource: Ref<any | null>
  configSchema: Ref<Record<string, any>>
  buildModelProviderConfig?: (modelId: string) => any
  modelAlreadyConfigured?: (modelId: string) => boolean
  loadConfig: () => Promise<void> | void
  tm: (key: string, params?: Record<string, string | number>) => string
  showMessage: (message: string, color?: string) => void
}

// Fallback for Gemini 4 models without a known list of reasoning levels.
const GEMINI_4_DEFAULT_REASONING_LEVELS = ['auto', 'low', 'medium', 'high', 'xhigh']

const GEMINI_4_REASONING_LEVELS = {
  'gemini-4-carbon': ['auto', 'low', 'medium', 'high'],
  'gemini-4-argon': ['auto', 'low', 'medium', 'high'],
  'gemini-4-neon': ['auto', 'low', 'medium', 'high', 'xhigh'],
  'gemini-4-hydrogen': ['auto', 'low', 'medium', 'high', 'xhigh']
}

export function useProviderModelConfigDialog(options: UseProviderModelConfigDialogOptions) {
  const {
    selectedProviderSource,
    configSchema,
    buildModelProviderConfig,
    modelAlreadyConfigured,
    loadConfig,
    tm,
    showMessage
  } = options

  const providerEditForm = ref<{ validate: () => Promise<{ valid: boolean }> } | null>(null)
  const showProviderEditDialog = ref(false)
  const providerEditData = ref<any | null>(null)
  const providerEditOriginalId = ref('')
  const providerEditMode = ref<'add' | 'edit'>('edit')
  const savingProviders = ref<string[]>([])

  const providerModelConfigSchema = computed(() => {
    if (!configSchema.value?.provider?.items) {
      return configSchema.value
    }

    const schema = JSON.parse(JSON.stringify(configSchema.value))
    const hiddenKeys = ['id', 'model']
    const modelName = providerEditData.value?.model?.toLowerCase().split('/').pop() || ''

    if (schema.provider.items.max_context_tokens) {
      schema.provider.items.max_context_tokens.required = false
      schema.provider.items.max_context_tokens.placeholder = 'Use default.'
      schema.provider.items.max_context_tokens.min = 0
      schema.provider.items.max_context_tokens.integer = true
    }

    const extraBody = schema.provider.items.custom_extra_body
    if (extraBody?.template_schema) {
      extraBody.render_type = 'inline'
      for (const [key, constraints] of Object.entries({
        max_tokens: { min: 1, integer: true },
        temperature: { min: 0, max: 2 },
        top_p: { min: 0, max: 1 }
      })) {
        if (extraBody.template_schema?.[key]) {
          Object.assign(extraBody.template_schema[key], constraints)
        }
      }
      if (selectedProviderSource.value?.type === 'googlegenai_chat_completion') {
        // Gemini uses its SDK parameter name and supports reasoning effort on Gemini 4.
        const { max_tokens, temperature, top_p, reasoning_effort } = extraBody.template_schema
        extraBody.template_schema = {
          max_output_tokens: { ...max_tokens, name: 'Max Output Tokens' },
          temperature,
          top_p
        }
        if (modelName.startsWith('gemini-4')) {
          const modelLevels = Object.entries(GEMINI_4_REASONING_LEVELS).find(([modelId]) =>
            modelName === modelId || modelName.startsWith(`${modelId}-`)
          )?.[1]
          extraBody.template_schema = {
            reasoning_effort: {
              ...reasoning_effort,
              name: 'Reasoning Effort',
              type: 'string',
              options: modelLevels ?? GEMINI_4_DEFAULT_REASONING_LEVELS
            },
            ...extraBody.template_schema
          }
          extraBody.inline_fields_after = { reasoning_effort: 'max_context_tokens' }
        }
      } else if (extraBody.template_schema?.reasoning_effort) {
        if (modelName.startsWith('gemini-')) {
          delete extraBody.template_schema.reasoning_effort.default
        }
        extraBody.template_schema.reasoning_effort.render_type = 'reasoning_effort'
        extraBody.inline_fields_after = { reasoning_effort: 'max_context_tokens' }
      }
    }

    for (const key of hiddenKeys) {
      if (schema.provider.items[key]) {
        schema.provider.items[key].invisible = true
      }
    }
    return schema
  })

  const providerEditDialogTitle = computed(() => {
    const actionTitle = providerEditMode.value === 'add'
      ? tm('dialogs.config.addTitle')
      : tm('dialogs.config.editTitle')
    const providerId = providerEditData.value?.id
    return providerId ? `${actionTitle} ${providerId}` : actionTitle
  })

  function openProviderEdit(provider: any) {
    const editableProvider = JSON.parse(JSON.stringify(provider))
    const providerType = editableProvider.provider_type
      || selectedProviderSource.value?.provider_type
      || (editableProvider.provider_source_id ? 'chat_completion' : undefined)
    if (providerType === 'chat_completion') {
      // Omitted values still need an editable field when the dialog is reopened.
      editableProvider.max_context_tokens ??= ''
    }
    if (selectedProviderSource.value?.type === 'googlegenai_chat_completion') {
      editableProvider.custom_extra_body ??= {}
    }
    // Keep model fields together without introducing fields on other provider types.
    for (const key of ['modalities', 'max_context_tokens', 'custom_extra_body']) {
      if (key in editableProvider) {
        const value = editableProvider[key]
        delete editableProvider[key]
        editableProvider[key] = value
      }
    }
    if (editableProvider.provider_source_id) {
      delete editableProvider.reasoning
    }
    providerEditData.value = editableProvider
    providerEditOriginalId.value = provider.id
    providerEditMode.value = 'edit'
    showProviderEditDialog.value = true
  }

  function openModelAddDialog(modelId: string) {
    if (!selectedProviderSource.value) {
      showMessage(tm('providerSources.selectHint'), 'error')
      return
    }
    if (!modelId) return
    if (modelAlreadyConfigured?.(modelId)) {
      showMessage(tm('models.manualModelExists'), 'error')
      return
    }

    const newProviderConfig = buildModelProviderConfig?.(modelId)
    if (!newProviderConfig) return

    for (const key of ['modalities', 'max_context_tokens', 'custom_extra_body']) {
      if (key in newProviderConfig) {
        const value = newProviderConfig[key]
        delete newProviderConfig[key]
        newProviderConfig[key] = value
      }
    }
    providerEditData.value = newProviderConfig
    providerEditOriginalId.value = ''
    providerEditMode.value = 'add'
    showProviderEditDialog.value = true
  }

  async function saveEditedProvider() {
    if (!providerEditData.value) return
    if (providerEditForm.value && !(await providerEditForm.value.validate()).valid) return

    savingProviders.value.push(providerEditData.value.id)
    try {
      const isAdding = providerEditMode.value === 'add'
      const sourceId = providerEditData.value.provider_source_id || selectedProviderSource.value?.id
      if (isAdding && !sourceId) {
        throw new Error(tm('providerSources.selectHint'))
      }
      const providerConfig = { ...providerEditData.value }
      if (providerConfig.max_context_tokens === '' || providerConfig.max_context_tokens == null) {
        delete providerConfig.max_context_tokens
      }
      const res = isAdding
        ? await providerApi.createInSource(sourceId, providerConfig)
        : await providerApi.update(
          providerEditOriginalId.value || providerEditData.value.id,
          providerConfig
      )

      if (res.data.status === 'error') {
        throw new Error(res.data.message || tm('providerSources.saveError'))
      }

      showMessage(
        res.data.message || (
          isAdding
            ? tm('models.addSuccess', { model: providerEditData.value.model })
            : tm('providerSources.saveSuccess')
        )
      )
      showProviderEditDialog.value = false
      await loadConfig()
    } catch (err: any) {
      showMessage(err.response?.data?.message || err.message || tm('providerSources.saveError'), 'error')
    } finally {
      savingProviders.value = savingProviders.value.filter(id => id !== providerEditData.value?.id)
    }
  }

  return {
    providerEditForm,
    showProviderEditDialog,
    providerEditData,
    savingProviders,
    providerModelConfigSchema,
    providerEditDialogTitle,
    openProviderEdit,
    openModelAddDialog,
    saveEditedProvider
  }
}
