import { ref, computed, onMounted, nextTick, watch } from 'vue';
import { providerApi } from '@/api/v1';
import { getProviderIcon } from '@/utils/providerUtils';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { normalizeTextInput } from '@/utils/inputValue';
import {
  isDashboardStepUpRequired,
  type DashboardStepUpTarget,
} from '@/composables/useDashboardStepUp';

type GenericObject = Record<string, unknown>;

interface ProviderModelMetadata {
  modalities?: {
    input?: string[];
  };
  tool_call?: boolean;
  reasoning?: boolean;
  limit?: {
    context?: number;
  };
}

interface ProviderSourceItem extends GenericObject {
  id?: string;
  key?: string;
  api_base?: string;
  enable?: boolean;
  type?: string;
  provider_type?: string;
  provider?: string;
  templateKey?: string;
  isPlaceholder?: boolean;
  ollama_disable_thinking?: boolean;
  responses_state_mode?: 'stateless' | 'previous_response_id' | 'conversation';
  responses_background?: boolean;
  store?: boolean;
  web_search?: Record<string, unknown>;
}

interface ProviderItem extends GenericObject {
  id?: string;
  provider_source_id?: string;
  model?: string;
  enable?: boolean;
  provider_type?: string;
  modalities?: string[];
  max_context_tokens?: number;
  model_metadata?: ProviderModelMetadata | null;
}

interface AvailableModelItem {
  name: string;
  metadata: ProviderModelMetadata | null;
}

interface ConfiguredModelEntry {
  type: 'configured';
  provider: ProviderItem;
  metadata: ProviderModelMetadata | null;
  hasModelMetadata?: boolean;
}

interface AvailableModelEntry {
  type: 'available';
  model: string;
  metadata: ProviderModelMetadata | null;
  hasModelMetadata?: boolean;
}

type MergedModelEntry = ConfiguredModelEntry | AvailableModelEntry;

interface ConfigSchemaProviderItems extends GenericObject {
  id?: GenericObject & { hint?: string };
  key?: GenericObject & { hint?: string };
  api_base?: GenericObject & { hint?: string };
  proxy?: GenericObject & { description?: string; hint?: string };
}

interface ConfigSchemaShape extends GenericObject {
  provider?: {
    items?: ConfigSchemaProviderItems;
    config_template?: Record<string, ProviderSourceItem>;
  };
}

export interface UseProviderSourcesOptions {
  defaultTab?: string;
  tm: (key: string, params?: Record<string, unknown>) => string;
  showMessage: (message: string, color?: string) => void;
  requestStepUp?: (target: DashboardStepUpTarget) => Promise<string | null>;
}

export function resolveDefaultTab(value?: string) {
  const normalized = (value || '').toLowerCase();

  if (
    normalized.startsWith('select_agent_runner_provider') ||
    normalized === 'agent_runner'
  ) {
    return 'agent_runner';
  }

  if (
    normalized === 'select_provider_stt' ||
    normalized === 'speech_to_text' ||
    normalized.includes('stt')
  ) {
    return 'speech_to_text';
  }

  if (
    normalized === 'select_provider_tts' ||
    normalized === 'text_to_speech' ||
    normalized.includes('tts')
  ) {
    return 'text_to_speech';
  }

  if (normalized.includes('embedding')) {
    return 'embedding';
  }

  if (normalized.includes('rerank')) {
    return 'rerank';
  }

  return 'chat_completion';
}

export function useProviderSources(options: UseProviderSourcesOptions) {
  const { tm, showMessage } = options;

  const confirmDialog = useConfirmDialog();

  async function askForConfirmation(message: string) {
    return askForConfirmationDialog(message, confirmDialog);
  }

  // ===== State =====
  const config = ref<GenericObject>({});
  const metadata = ref<GenericObject>({});
  const providerSources = ref<ProviderSourceItem[]>([]);
  const providers = ref<ProviderItem[]>([]);
  const selectedProviderType = ref<string>(
    resolveDefaultTab(options.defaultTab),
  );
  const selectedProviderSource = ref<ProviderSourceItem | null>(null);
  const selectedProviderSourceOriginalId = ref<string | null>(null);
  const editableProviderSource = ref<ProviderSourceItem | null>(null);
  const availableModels = ref<AvailableModelItem[]>([]);
  const modelMetadata = ref<Record<string, ProviderModelMetadata | null>>({});
  const loadingModels = ref(false);
  const savingSource = ref(false);
  const savingProviderToggles = ref<string[]>([]);
  const testingProviders = ref<string[]>([]);
  const isSourceModified = ref(false);
  const configSchema = ref<ConfigSchemaShape>({});
  const providerTemplates = ref<Record<string, ProviderSourceItem>>({});
  const manualModelId = ref('');
  const modelSearch = ref('');

  let suppressSourceWatch = false;
  const unsavedProviderSourceIds = new Set<string>();

  const providerTypes = computed(() => [
    {
      value: 'chat_completion',
      label: tm('providers.tabs.chatCompletion'),
      icon: 'mdi-message-text',
    },
    {
      value: 'agent_runner',
      label: tm('providers.tabs.agentRunner'),
      icon: 'mdi-robot',
    },
    {
      value: 'speech_to_text',
      label: tm('providers.tabs.speechToText'),
      icon: 'mdi-microphone-message',
    },
    {
      value: 'text_to_speech',
      label: tm('providers.tabs.textToSpeech'),
      icon: 'mdi-volume-high',
    },
    {
      value: 'embedding',
      label: tm('providers.tabs.embedding'),
      icon: 'mdi-code-json',
    },
    {
      value: 'rerank',
      label: tm('providers.tabs.rerank'),
      icon: 'mdi-compare-vertical',
    },
  ]);

  // ===== Computed =====
  const availableSourceTypes = computed(() => {
    if (
      !providerTemplates.value ||
      Object.keys(providerTemplates.value).length === 0
    ) {
      return [];
    }

    const types: Array<{ value: string; label: string; icon: string }> = [];
    for (const [templateName, template] of Object.entries(
      providerTemplates.value,
    )) {
      if (template.provider_type === selectedProviderType.value) {
        types.push({
          value: templateName,
          label: templateName,
          icon: getProviderIcon(template.provider || ''),
        });
      }
    }

    return types;
  });

  const filteredProviderSources = computed(() => {
    if (!providerSources.value) return [];

    return providerSources.value.filter(
      (source) => source.provider_type === selectedProviderType.value,
    );
  });

  const displayedProviderSources = computed(() => {
    return filteredProviderSources.value || [];
  });

  const sourceProviders = computed(() => {
    const selectedSource = selectedProviderSource.value;
    if (!selectedSource || !providers.value) return [];

    return providers.value.filter(
      (provider) => provider.provider_source_id === selectedSource.id,
    );
  });

  const existingModelsForSelectedSource = computed(() => {
    if (!selectedProviderSource.value) return new Set<string>();
    return new Set(
      sourceProviders.value.map((provider) => provider.model || ''),
    );
  });

  const sortedAvailableModels = computed(() => {
    const existing = existingModelsForSelectedSource.value;
    return [...(availableModels.value || [])].sort((a, b) => {
      const aName = a.name;
      const bName = b.name;
      const aExists = existing.has(aName);
      const bExists = existing.has(bName);
      if (aExists && !bExists) return -1;
      if (!aExists && bExists) return 1;
      return 0;
    });
  });

  function buildMetadataFromProvider(
    provider: ProviderItem | null | undefined,
  ) {
    if (!provider) return null;
    const mods = provider.modalities || [];
    if (!mods.length && !provider.max_context_tokens) return null;
    const input: string[] = [];
    if (mods.includes('image')) input.push('image');
    if (mods.includes('audio')) input.push('audio');
    return {
      modalities: { input },
      tool_call: mods.includes('tool_use'),
      limit: { context: provider.max_context_tokens || 0 },
    };
  }

  const mergedModelEntries = computed<MergedModelEntry[]>(() => {
    const configuredEntries: ConfiguredModelEntry[] = (
      sourceProviders.value || []
    ).map((provider) => {
      const modelMetadataForProvider = getModelMetadata(provider.model) || null;
      return {
        type: 'configured',
        provider,
        metadata:
          modelMetadataForProvider || buildMetadataFromProvider(provider),
        hasModelMetadata: Boolean(modelMetadataForProvider),
      };
    });

    const availableEntries: AvailableModelEntry[] = (
      sortedAvailableModels.value || []
    )
      .filter((item) => {
        return !existingModelsForSelectedSource.value.has(item.name);
      })
      .map((item) => {
        const name = item.name;
        const metadata = item.metadata || getModelMetadata(name);
        return {
          type: 'available',
          model: name,
          metadata,
          hasModelMetadata: Boolean(metadata),
        };
      });

    return [...configuredEntries, ...availableEntries];
  });

  const filteredMergedModelEntries = computed(() => {
    const term = normalizeTextInput(modelSearch.value).trim().toLowerCase();
    if (!term) return mergedModelEntries.value;

    return mergedModelEntries.value.filter((entry) => {
      if (entry.type === 'configured') {
        const id = entry.provider.id?.toLowerCase() || '';
        const model = entry.provider.model?.toLowerCase() || '';
        return id.includes(term) || model.includes(term);
      }

      const model = entry.model?.toLowerCase() || '';
      return model.includes(term);
    });
  });

  const manualProviderId = computed(() => {
    if (!selectedProviderSource.value) return '';
    const modelId = manualModelId.value.trim();
    if (!modelId) return '';
    return `${selectedProviderSource.value.id}/${modelId}`;
  });

  const basicSourceConfig = computed(() => {
    if (!editableProviderSource.value) return null;

    const fields = ['id', 'key', 'api_base'];
    const basic: GenericObject = {};

    fields.forEach((field) => {
      Object.defineProperty(basic, field, {
        get() {
          return editableProviderSource.value![field];
        },
        set(val) {
          editableProviderSource.value![field] = val;
        },
        enumerable: true,
      });
    });

    return basic;
  });

  const advancedSourceConfig = computed(() => {
    if (!editableProviderSource.value) return null;

    const excluded = new Set([
      'id',
      'key',
      'api_base',
      'enable',
      'type',
      'provider_type',
      'provider',
    ]);
    const advanced: GenericObject = {};

    for (const key of Object.keys(editableProviderSource.value)) {
      Object.defineProperty(advanced, key, {
        get() {
          return editableProviderSource.value![key];
        },
        set(val) {
          editableProviderSource.value![key] = val;
        },
        enumerable: !excluded.has(key),
      });
    }

    return advanced;
  });

  const filteredProviders = computed(() => {
    if (!providers.value || selectedProviderType.value === 'chat_completion') {
      return [];
    }

    return providers.value.filter(
      (provider) => provider.provider_type === selectedProviderType.value,
    );
  });

  const providerSourceSchema = computed(() => {
    if (!configSchema.value?.provider) {
      return configSchema.value;
    }

    // 创建一个深拷贝以避免修改原始 schema
    const customSchema = JSON.parse(
      JSON.stringify(configSchema.value),
    ) as ConfigSchemaShape;

    // 为 provider source 的 id 字段添加自定义 hint
    if (customSchema.provider?.items?.id) {
      customSchema.provider.items.id.hint = tm('providerSources.hints.id');
      if (customSchema.provider.items.key) {
        customSchema.provider.items.key.hint = tm('providerSources.hints.key');
      }
      if (customSchema.provider.items.api_base) {
        customSchema.provider.items.api_base.hint = tm(
          'providerSources.hints.apiBase',
        );
      }
    }
    // 为 proxy 字段添加描述和提示
    if (customSchema.provider?.items?.proxy) {
      customSchema.provider.items.proxy.description = tm(
        'providerSources.labels.proxy',
      );
      customSchema.provider.items.proxy.hint = tm(
        'providerSources.hints.proxy',
      );
    }

    return customSchema;
  });

  // ===== Watches =====
  watch(
    editableProviderSource,
    () => {
      if (suppressSourceWatch) return;
      if (!editableProviderSource.value) return;
      isSourceModified.value = true;
    },
    { deep: true },
  );

  // ===== Helper Functions =====
  function resolveSourceIcon(source: ProviderSourceItem | null | undefined) {
    if (!source) return '';
    return getProviderIcon(source.provider || '') || '';
  }

  function getSourceDisplayName(source: ProviderSourceItem | null | undefined) {
    if (!source) return '';
    if (source.isPlaceholder) return source.templateKey || source.id || '';
    if (source.id === 'ssycloud') return 'ssycloud(胜算云)';
    return source.id || '';
  }

  function getModelMetadata(modelName?: string) {
    if (!modelName) return null;
    return modelMetadata.value?.[modelName] || null;
  }

  function supportsImageInput(meta: ProviderModelMetadata | null | undefined) {
    const inputs = meta?.modalities?.input || [];
    return inputs.includes('image');
  }

  function supportsAudioInput(meta: ProviderModelMetadata | null | undefined) {
    const inputs = meta?.modalities?.input || [];
    return inputs.includes('audio');
  }

  function supportsToolCall(meta: ProviderModelMetadata | null | undefined) {
    return Boolean(meta?.tool_call);
  }

  function supportsReasoning(meta: ProviderModelMetadata | null | undefined) {
    return Boolean(meta?.reasoning);
  }

  function formatContextLimit(meta: ProviderModelMetadata | null | undefined) {
    const ctx = meta?.limit?.context;
    if (!ctx || typeof ctx !== 'number') return '';
    if (ctx >= 1_000_000) return `${Math.round(ctx / 1_000_000)}M`;
    if (ctx >= 1_000) return `${Math.round(ctx / 1_000)}K`;
    return `${ctx}`;
  }

  function selectProviderSource(source: ProviderSourceItem | null | undefined) {
    if (source?.isPlaceholder && source.templateKey) {
      addProviderSource(source.templateKey);
      return;
    }

    const resolvedSource = source || null;
    selectedProviderSource.value = resolvedSource;
    selectedProviderSourceOriginalId.value = source?.id || null;
    suppressSourceWatch = true;
    editableProviderSource.value = resolvedSource
      ? ensureProviderSourceDefaults(
          JSON.parse(JSON.stringify(resolvedSource)) as ProviderSourceItem,
        )
      : null;
    void nextTick(() => {
      suppressSourceWatch = false;
    });
    availableModels.value = [];
    modelMetadata.value = {};
    isSourceModified.value = false;
  }

  function ensureProviderSourceDefaults(
    source: ProviderSourceItem | null | undefined,
  ): ProviderSourceItem | null {
    if (!source || typeof source !== 'object') {
      return null;
    }

    if (
      source.provider === 'ollama' &&
      source.ollama_disable_thinking === undefined
    ) {
      source.ollama_disable_thinking = false;
    }

    return source;
  }

  function extractSourceFieldsFromTemplate(template: ProviderSourceItem) {
    const sourceFields: ProviderSourceItem = {};
    const excludeKeys = [
      'id',
      'enable',
      'model',
      'provider_source_id',
      'modalities',
      'custom_extra_body',
    ];

    for (const [key, value] of Object.entries(template)) {
      if (!excludeKeys.includes(key)) {
        sourceFields[key] = value;
      }
    }

    return sourceFields;
  }

  function generateUniqueSourceId(baseId: string) {
    const existingIds = new Set(
      providerSources.value.map((source) => source.id),
    );
    if (!existingIds.has(baseId)) return baseId;

    let counter = 1;
    let candidate = `${baseId}_${counter}`;
    while (existingIds.has(candidate)) {
      counter += 1;
      candidate = `${baseId}_${counter}`;
    }

    return candidate;
  }

  function removeProviderSourceFromLocalState(sourceId: string) {
    providers.value = providers.value.filter(
      (provider) =>
        provider.provider_source_id === null ||
        String(provider.provider_source_id) !== sourceId,
    );
    providerSources.value = providerSources.value.filter(
      (providerSource) =>
        providerSource.id === null || String(providerSource.id) !== sourceId,
    );

    if (String(selectedProviderSource.value?.id || '') === sourceId) {
      selectedProviderSource.value = null;
      selectedProviderSourceOriginalId.value = null;
      editableProviderSource.value = null;
      availableModels.value = [];
      modelMetadata.value = {};
      isSourceModified.value = false;
    }
  }

  function addProviderSource(templateKey: string) {
    const template = providerTemplates.value[templateKey];
    if (!template) {
      showMessage('未找到对应的模板配置', 'error');
      return;
    }

    const newId = generateUniqueSourceId(template.id || templateKey);
    const newSource = ensureProviderSourceDefaults({
      ...extractSourceFieldsFromTemplate(template),
      id: newId,
      type: template.type,
      provider_type: template.provider_type,
      provider: template.provider,
      enable: true,
    });
    if (!newSource) {
      return;
    }

    unsavedProviderSourceIds.add(newId);
    providerSources.value.push(newSource);
    selectedProviderSource.value = newSource;
    selectedProviderSourceOriginalId.value = newId;
    editableProviderSource.value = JSON.parse(
      JSON.stringify(newSource),
    ) as ProviderSourceItem;
    availableModels.value = [];
    modelMetadata.value = {};
    isSourceModified.value = true;
  }

  async function deleteProviderSource(source: ProviderSourceItem) {
    if (!source.id) {
      showMessage(tm('providerSources.deleteError'), 'error');
      return;
    }
    const confirmed = await askForConfirmation(
      tm('providerSources.deleteConfirm', { id: source.id }),
    );
    if (!confirmed) return;

    const sourceId = String(source.id);
    if (unsavedProviderSourceIds.delete(sourceId)) {
      removeProviderSourceFromLocalState(sourceId);
      showMessage(tm('providerSources.deleteSuccess'));
      return;
    }

    try {
      await providerApi.deleteSource(sourceId);
      removeProviderSourceFromLocalState(sourceId);
      showMessage(tm('providerSources.deleteSuccess'));
      await loadConfig();
    } catch (error: unknown) {
      showMessage(
        resolveErrorMessage(error, tm('providerSources.deleteError')),
        'error',
      );
    }
  }

  async function saveProviderSource() {
    if (!selectedProviderSource.value || !editableProviderSource.value)
      return false;

    if (
      editableProviderSource.value.type === 'openai_responses' &&
      editableProviderSource.value.responses_background &&
      (editableProviderSource.value.responses_state_mode === 'stateless' ||
        !editableProviderSource.value.store)
    ) {
      showMessage(tm('providerSources.responsesBackgroundConflict'), 'error');
      return false;
    }

    savingSource.value = true;
    const sourceBeingSaved = selectedProviderSource.value;
    const originalId = String(
      selectedProviderSourceOriginalId.value || sourceBeingSaved.id || '',
    );
    const editableSource = editableProviderSource.value;
    try {
      let response;
      try {
        response = await providerApi.upsertSource(originalId, editableSource);
      } catch (error: unknown) {
        if (!isDashboardStepUpRequired(error) || !options.requestStepUp) {
          throw error;
        }

        const stepUp = await options.requestStepUp({
          action: 'provider.credentials.write',
          resourceType: 'provider-source',
          resourceId: originalId,
          configId: 'default',
        });
        if (!stepUp) return false;
        response = await providerApi.upsertSource(
          originalId,
          editableSource,
          stepUp,
        );
      }

      if (response.data.status !== 'ok') {
        throw new Error(
          response.data.message || tm('providerSources.saveError'),
        );
      }

      if (editableSource.id !== originalId) {
        providers.value = providers.value.map((p) =>
          p.provider_source_id === originalId
            ? { ...p, provider_source_id: editableSource.id }
            : p,
        );
        selectedProviderSourceOriginalId.value = editableSource.id || null;
      }

      unsavedProviderSourceIds.delete(originalId);
      if (editableSource.id) {
        unsavedProviderSourceIds.delete(String(editableSource.id));
      }

      const idx = providerSources.value.findIndex((ps) => ps.id === originalId);
      if (idx !== -1) {
        providerSources.value[idx] = JSON.parse(
          JSON.stringify(editableSource),
        ) as ProviderSourceItem;
        selectedProviderSource.value = providerSources.value[idx];
      }

      suppressSourceWatch = true;
      editableProviderSource.value = selectedProviderSource.value || null;
      void nextTick(() => {
        suppressSourceWatch = false;
      });

      isSourceModified.value = false;
      showMessage(response.data.message || tm('providerSources.saveSuccess'));
      return true;
    } catch (error: unknown) {
      showMessage(
        resolveErrorMessage(error, tm('providerSources.saveError')),
        'error',
      );
      return false;
    } finally {
      savingSource.value = false;
      await loadConfig();
    }
  }

  async function fetchAvailableModels() {
    if (!selectedProviderSource.value) return;

    if (isSourceModified.value) {
      const saved = await saveProviderSource();
      if (!saved) {
        return;
      }
    }

    loadingModels.value = true;
    try {
      const sourceId = String(
        editableProviderSource.value?.id ||
          selectedProviderSource.value.id ||
          '',
      );
      const response = await providerApi.sourceModels(sourceId);
      if (response.data.status === 'ok') {
        const metadataMap = (response.data.data.model_metadata || {}) as Record<
          string,
          ProviderModelMetadata | null
        >;
        modelMetadata.value = metadataMap;
        availableModels.value = (response.data.data.models || []).map(
          (model: string): AvailableModelItem => ({
            name: model,
            metadata: metadataMap?.[model] || null,
          }),
        );
        if (availableModels.value.length === 0) {
          showMessage(tm('models.noModelsFound'), 'info');
        }
      } else {
        throw new Error(response.data.message || tm('models.fetchError'));
      }
    } catch (error: unknown) {
      modelMetadata.value = {};
      showMessage(resolveErrorMessage(error, tm('models.fetchError')), 'error');
    } finally {
      loadingModels.value = false;
    }
  }

  function buildModelProviderConfig(modelName: string) {
    if (!selectedProviderSource.value) return;

    const sourceId =
      editableProviderSource.value?.id || selectedProviderSource.value.id;
    const newId = `${sourceId}/${modelName}`;

    const metadata = getModelMetadata(modelName);
    let modalities: string[];

    if (!metadata) {
      modalities =
        selectedProviderSource.value?.type === 'openai_responses'
          ? ['text', 'image', 'tool_use']
          : ['text', 'image', 'audio', 'tool_use'];
    } else {
      modalities = ['text'];
      if (supportsImageInput(metadata)) {
        modalities.push('image');
      }
      if (
        selectedProviderSource.value?.type !== 'openai_responses' &&
        supportsAudioInput(metadata)
      ) {
        modalities.push('audio');
      }
      if (supportsToolCall(metadata)) {
        modalities.push('tool_use');
      }
    }

    let max_context_tokens = 0;
    if (
      metadata?.limit?.context &&
      typeof metadata.limit.context === 'number'
    ) {
      max_context_tokens = metadata.limit.context;
    }

    return {
      id: newId,
      enable: true,
      provider_source_id: sourceId,
      model: modelName,
      modalities,
      custom_extra_body: {},
      max_context_tokens,
    };
  }

  async function addModelProvider(modelName: string) {
    const newProvider = buildModelProviderConfig(modelName);
    if (!newProvider) return;

    try {
      const res = await providerApi.createInSource(
        String(newProvider.provider_source_id),
        newProvider,
      );
      if (res.data.status === 'error') {
        throw new Error(res.data.message || tm('providerSources.saveError'));
      }
      providers.value.push(newProvider);
      showMessage(
        res.data.message || tm('models.addSuccess', { model: modelName }),
      );
    } catch (error: unknown) {
      showMessage(
        resolveErrorMessage(error, tm('providerSources.saveError')),
        'error',
      );
    } finally {
      await loadConfig();
    }
  }

  function modelAlreadyConfigured(modelName: string) {
    return existingModelsForSelectedSource.value.has(modelName);
  }

  async function deleteProvider(provider: ProviderItem) {
    if (!provider.id) {
      showMessage(tm('models.deleteError'), 'error');
      return;
    }
    const confirmed = await askForConfirmation(
      tm('models.deleteConfirm', { id: provider.id }),
    );
    if (!confirmed) return;

    try {
      await providerApi.delete(String(provider.id));
      providers.value = providers.value.filter((p) => p.id !== provider.id);
      showMessage(tm('models.deleteSuccess'));
    } catch (error: unknown) {
      showMessage(
        resolveErrorMessage(error, tm('models.deleteError')),
        'error',
      );
    } finally {
      await loadConfig();
    }
  }

  async function toggleProviderEnable(provider: ProviderItem, value: boolean) {
    const providerId = provider.id || '';
    if (!providerId || savingProviderToggles.value.includes(providerId)) {
      return false;
    }

    savingProviderToggles.value.push(providerId);
    try {
      const response = await providerApi.setEnabled(providerId, {
        enabled: Boolean(value),
      });
      if (response.data.status === 'error') {
        throw new Error(
          response.data.message || tm('providerSources.saveError'),
        );
      }
      provider.enable = Boolean(value);
      showMessage(response.data.message || tm('messages.success.statusUpdate'));
      return true;
    } catch (error: unknown) {
      showMessage(
        resolveErrorMessage(error, tm('providerSources.saveError')),
        'error',
      );
      return false;
    } finally {
      await loadConfig();
      savingProviderToggles.value = savingProviderToggles.value.filter(
        (id) => id !== providerId,
      );
    }
  }

  async function testProvider(provider: ProviderItem) {
    const providerId = provider.id || '';
    if (!providerId) {
      showMessage(tm('models.testError'), 'error');
      return;
    }
    testingProviders.value.push(providerId);
    try {
      const startTime = performance.now();
      const response = await providerApi.test(providerId);
      if (response.data.status === 'ok' && response.data.data.error === null) {
        const latency = Math.max(0, Math.round(performance.now() - startTime));
        showMessage(
          tm('models.testSuccessWithLatency', { id: providerId, latency }),
        );
      } else {
        throw new Error(response.data.data.error || tm('models.testError'));
      }
    } catch (error: unknown) {
      showMessage(resolveErrorMessage(error, tm('models.testError')), 'error');
    } finally {
      testingProviders.value = testingProviders.value.filter(
        (id) => id !== providerId,
      );
    }
  }

  async function loadConfig() {
    await loadProviderTemplate();
  }

  async function loadProviderTemplate() {
    try {
      const response = await providerApi.schema();
      if (response.data.status === 'ok') {
        const payload = response.data.data;
        configSchema.value = payload.config_schema || {};
        if (configSchema.value.provider?.config_template) {
          providerTemplates.value = configSchema.value.provider.config_template;
        }
        providerSources.value = payload.provider_sources || [];
        modelMetadata.value = (payload.model_metadata || {}) as Record<
          string,
          ProviderModelMetadata | null
        >;
        providers.value = payload.providers || [];
      }
    } catch (error) {
      console.error('Failed to load provider template:', error);
    }
  }

  function updateDefaultTab(value: string) {
    selectedProviderType.value = resolveDefaultTab(value);
  }

  onMounted(async () => {
    await loadProviderTemplate();
  });

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
    savingProviderToggles,
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
    supportsAudioInput,
    supportsToolCall,
    supportsReasoning,
    formatContextLimit,

    // methods
    updateDefaultTab,
    selectProviderSource,
    addProviderSource,
    deleteProviderSource,
    saveProviderSource,
    fetchAvailableModels,
    buildModelProviderConfig,
    addModelProvider,
    deleteProvider,
    modelAlreadyConfigured,
    toggleProviderEnable,
    testProvider,
    loadConfig,
    loadProviderTemplate,
  };
}
