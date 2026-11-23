import { computed, getCurrentScope, onScopeDispose, type Ref, ref } from "vue";
import { providerApi } from "@/api/v1";

interface UseProviderModelConfigDialogOptions {
  selectedProviderSource: Ref<any | null>;
  configSchema: Ref<Record<string, any>>;
  buildModelProviderConfig?: (modelId: string) => any;
  modelAlreadyConfigured?: (modelId: string) => boolean;
  loadConfig: () => Promise<void> | void;
  tm: (key: string, params?: Record<string, string | number>) => string;
  showMessage: (message: string, color?: string) => void;
}

// Quick-add templates for `custom_extra_body` on Gemini providers. They use the
// Gemini SDK parameter names (max_output_tokens instead of OpenAI's max_tokens).
// Other parameters can still be added by key; the Gemini SDK validates them.
const GEMINI_EXTRA_BODY_TEMPLATE = {
  temperature: {
    name: "Temperature",
    description: "温度参数",
    hint: "控制输出的随机性，范围通常为 0-2。值越高越随机。",
    type: "float",
    default: 1.0,
    slider: { min: 0, max: 2, step: 0.1 },
  },
  top_p: {
    name: "Top-p",
    description: "Top-p 采样",
    hint: "核采样参数，范围通常为 0-1。控制模型考虑的概率质量。",
    type: "float",
    default: 1.0,
    slider: { min: 0, max: 1, step: 0.01 },
  },
  max_output_tokens: {
    name: "Max Output Tokens",
    description: "最大输出词元（Tokens）数",
    hint: "生成的最大词元（Tokens）数。",
    type: "int",
    default: 8192,
  },
};

// Fallback only. Avoid actually depending on this.
const GEMINI_4_DEFAULT_REASONING_LEVELS = ["auto", "low", "medium", "high", "xhigh"];

const GEMINI_4_REASONING_LEVELS = {
  "gemini-4-carbon": ["auto", "low", "medium", "high"],
  "gemini-4-argon": ["auto", "low", "medium", "high"],
  "gemini-4-neon": ["auto", "low", "medium", "high", "xhigh"],
  "gemini-4-hydrogen": ["auto", "low", "medium", "high", "xhigh"],
};

export function useProviderModelConfigDialog(options: UseProviderModelConfigDialogOptions) {
  const {
    selectedProviderSource,
    configSchema,
    buildModelProviderConfig,
    modelAlreadyConfigured,
    loadConfig,
    tm,
    showMessage,
  } = options;

  const showProviderEditDialog = ref(false);
  const providerEditData = ref<any | null>(null);
  const providerEditOriginalId = ref("");
  const providerEditMode = ref<"add" | "edit">("edit");
  const savingProviders = ref<string[]>([]);
  let editGeneration = 0;
  let disposed = false;

  if (getCurrentScope()) {
    onScopeDispose(() => {
      disposed = true;
      editGeneration += 1;
    });
  }

  const providerModelConfigSchema = computed(() => {
    if (!configSchema.value?.provider?.items) {
      return configSchema.value;
    }

    const schema = JSON.parse(JSON.stringify(configSchema.value));
    const hiddenKeys = ["id", "model"];
    const modelName = providerEditData.value?.model?.toLowerCase().split("/").pop() || "";
    const extraBodySchema = schema.provider.items.custom_extra_body;

    if (selectedProviderSource.value?.type === "googlegenai_chat_completion") {
      extraBodySchema.template_schema = { ...GEMINI_EXTRA_BODY_TEMPLATE };
      if (modelName.startsWith("gemini-4")) {
        const modelLevels = Object.entries(GEMINI_4_REASONING_LEVELS).find(
          ([modelId]) => modelName === modelId || modelName.startsWith(`${modelId}-`),
        )?.[1];
        extraBodySchema.template_schema.reasoning_effort = {
          name: "Reasoning Effort",
          type: "string",
          options: modelLevels ?? GEMINI_4_DEFAULT_REASONING_LEVELS,
        };
      }
    } else if (modelName.startsWith("gemini-")) {
      delete extraBodySchema.template_schema?.reasoning_effort?.default;
    }

    for (const key of hiddenKeys) {
      if (schema.provider.items[key]) {
        schema.provider.items[key].invisible = true;
      }
    }
    return schema;
  });

  const providerEditDialogTitle = computed(() => {
    const actionTitle =
      providerEditMode.value === "add" ? tm("dialogs.config.addTitle") : tm("dialogs.config.editTitle");
    const providerId = providerEditData.value?.id;
    return providerId ? `${actionTitle} ${providerId}` : actionTitle;
  });

  function openProviderEdit(provider: any) {
    const editableProvider = JSON.parse(JSON.stringify(provider));
    if (editableProvider.provider_source_id) {
      delete editableProvider.reasoning;
    }
    if (selectedProviderSource.value?.type === "googlegenai_chat_completion") {
      editableProvider.custom_extra_body ??= {};
    }
    editGeneration += 1;
    providerEditData.value = editableProvider;
    providerEditOriginalId.value = provider.id;
    providerEditMode.value = "edit";
    showProviderEditDialog.value = true;
  }

  function openModelAddDialog(modelId: string) {
    if (!selectedProviderSource.value) {
      showMessage(tm("providerSources.selectHint"), "error");
      return;
    }
    if (!modelId) return;
    if (modelAlreadyConfigured?.(modelId)) {
      showMessage(tm("models.manualModelExists"), "error");
      return;
    }

    const newProviderConfig = buildModelProviderConfig?.(modelId);
    if (!newProviderConfig) return;

    editGeneration += 1;
    providerEditData.value = newProviderConfig;
    providerEditOriginalId.value = "";
    providerEditMode.value = "add";
    showProviderEditDialog.value = true;
  }

  async function saveEditedProvider() {
    const editorData = providerEditData.value;
    if (!editorData || disposed) return;

    const snapshot = JSON.stringify(editorData);
    const payload = JSON.parse(snapshot);
    const providerId = payload.id;
    const originalId = providerEditOriginalId.value || providerId;
    const selectedSourceId = selectedProviderSource.value?.id;
    const sourceId = payload.provider_source_id || selectedSourceId;
    const isAdding = providerEditMode.value === "add";
    const generation = editGeneration;
    if (savingProviders.value.includes(providerId)) return;

    const isCurrentEditor = () =>
      !disposed &&
      editGeneration === generation &&
      providerEditData.value === editorData &&
      selectedProviderSource.value?.id === selectedSourceId &&
      JSON.stringify(editorData) === snapshot;

    savingProviders.value.push(providerId);
    try {
      if (isAdding && !sourceId) {
        throw new Error(tm("providerSources.selectHint"));
      }
      const res = isAdding
        ? await providerApi.createInSource(sourceId, payload)
        : await providerApi.update(originalId, payload);

      if (res.data.status === "error") {
        throw new Error(res.data.message || tm("providerSources.saveError"));
      }

      if (!isCurrentEditor()) return;

      showMessage(
        res.data.message ||
          (isAdding ? tm("models.addSuccess", { model: payload.model }) : tm("providerSources.saveSuccess")),
      );
      showProviderEditDialog.value = false;
      await loadConfig();
    } catch (err: any) {
      if (isCurrentEditor()) {
        showMessage(err.response?.data?.message || err.message || tm("providerSources.saveError"), "error");
      }
    } finally {
      savingProviders.value = savingProviders.value.filter((id) => id !== providerId);
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
    saveEditedProvider,
  };
}
