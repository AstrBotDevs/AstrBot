import { computed, ref, type Ref } from 'vue'
import axios from 'axios'

interface UseProviderModelConfigDialogOptions {
  selectedProviderSource: Ref<any | null>
  configSchema: Ref<Record<string, any>>
  buildModelProviderConfig: (modelId: string) => any
  modelAlreadyConfigured: (modelId: string) => boolean
  loadConfig: () => Promise<void> | void
  tm: (key: string, params?: Record<string, unknown>) => string
  showMessage: (message: string, color?: string) => void
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
    const sourceType = selectedProviderSource.value?.type
    const hiddenKeys = ['id', 'model']

    if (sourceType === 'googlegenai_chat_completion') {
      hiddenKeys.push('custom_extra_body')
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
    providerEditData.value = JSON.parse(JSON.stringify(provider))
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
    if (modelAlreadyConfigured(modelId)) {
      showMessage(tm('models.manualModelExists'), 'error')
      return
    }

    const newProviderConfig = buildModelProviderConfig(modelId)
    if (!newProviderConfig) return

    providerEditData.value = newProviderConfig
    providerEditOriginalId.value = ''
    providerEditMode.value = 'add'
    showProviderEditDialog.value = true
  }

  async function saveEditedProvider() {
    if (!providerEditData.value) return

    savingProviders.value.push(providerEditData.value.id)
    try {
      const isAdding = providerEditMode.value === 'add'
      const res = isAdding
        ? await axios.post('/api/config/provider/new', providerEditData.value)
        : await axios.post('/api/config/provider/update', {
          id: providerEditOriginalId.value || providerEditData.value.id,
          config: providerEditData.value
        })

      if (res.data.status === 'error') {
        throw new Error(res.data.message)
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
