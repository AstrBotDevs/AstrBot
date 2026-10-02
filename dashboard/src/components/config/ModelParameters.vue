<template>
  <section class="model-parameters" :aria-label="tm('modelParameters.title')">
    <v-progress-linear v-if="loading" indeterminate color="primary" />
    <v-alert v-if="error" type="error" variant="tonal" density="compact">
      {{ error }}
      <v-btn variant="text" @click="draft ? saveParameters() : reload++">{{
        tm("modelParameters.retry")
      }}</v-btn>
    </v-alert>
    <template v-if="draft">
      <div class="model-parameters__heading">
        <strong>{{ tm("modelParameters.title") }}</strong>
        <span>{{ draft.id }}</span>
      </div>
      <p class="model-parameters__hint">
        {{ tm("modelParameters.sharedHint") }}
      </p>
      <v-form v-model="valid" :disabled="saving">
        <div
          v-for="key in ['temperature', 'max_tokens', 'reasoning_effort']"
          :key="key"
          class="model-parameters__row"
        >
          <div>
            <strong>{{ tm(`modelParameters.${key}`) }}</strong>
            <p class="model-parameters__hint">
              {{ tm(`modelParameters.${key}Hint`) }}
            </p>
          </div>
          <div class="model-parameters__control">
            <v-combobox
              v-if="key === 'reasoning_effort'"
              :model-value="
                getConfigTemplateValue(
                  draft.custom_extra_body[key],
                  parameterSchema[key],
                )
              "
              @update:model-value="draft.custom_extra_body[key] = $event"
              :items="effortOptions"
              :disabled="!supportsReasoning"
              :placeholder="tm('modelParameters.default')"
              persistent-placeholder
              :aria-label="tm(`modelParameters.${key}`)"
              clearable
              density="compact"
              variant="outlined"
              hide-details
            />
            <template v-else>
              <v-slider
                v-if="key === 'temperature'"
                :model-value="
                  getConfigTemplateValue(
                    draft.custom_extra_body[key],
                    parameterSchema[key],
                  )
                "
                @update:model-value="draft.custom_extra_body[key] = $event"
                :disabled="!supportsExtraBody"
                :aria-label="tm(`modelParameters.${key}`)"
                :min="parameterSchema[key]?.slider?.min ?? 0"
                :max="parameterSchema[key]?.slider?.max ?? 2"
                :step="parameterSchema[key]?.slider?.step ?? 0.1"
                color="primary"
                density="compact"
                hide-details
              />
              <v-text-field
                :model-value="
                  getConfigTemplateValue(
                    draft.custom_extra_body[key],
                    parameterSchema[key],
                  )
                "
                @update:model-value="draft.custom_extra_body[key] = $event"
                @blur="
                  draft.custom_extra_body[key] != null &&
                    draft.custom_extra_body[key] !== '' &&
                    (draft.custom_extra_body[key] = normalizeConfigValue(
                      draft.custom_extra_body[key],
                      parameterSchema[key],
                    ))
                "
                :disabled="!supportsExtraBody"
                :placeholder="tm('modelParameters.default')"
                persistent-placeholder
                :aria-label="tm(`modelParameters.${key}`)"
                :rules="key === 'temperature' ? temperatureRules : tokenRules"
                :min="key === 'temperature' ? 0 : 1"
                :max="key === 'temperature' ? 2 : undefined"
                :step="key === 'temperature' ? 0.1 : 1"
                type="number"
                clearable
                density="compact"
                variant="outlined"
                hide-details="auto"
              />
            </template>
            <p
              v-if="
                key === 'reasoning_effort' && isAnthropic && !supportsReasoning
              "
              class="model-parameters__hint"
            >
              {{ tm("modelParameters.adaptiveThinkingRequired") }}
            </p>
          </div>
        </div>
        <p v-if="!supportsExtraBody" class="model-parameters__hint">
          {{ tm("modelParameters.unsupported") }}
        </p>
        <div class="model-parameters__row">
          <div>
            <strong>{{ tm("modelParameters.modalities") }}</strong>
            <p class="model-parameters__hint">
              {{ tm("modelParameters.modalitiesHint") }}
            </p>
          </div>
          <ConfigItemRenderer
            v-model="draft.modalities"
            :item-meta="modalitiesMetadata"
            class="model-parameters__control"
          />
        </div>
        <div class="model-parameters__actions">
          <span v-if="saved && !dirty" role="status">{{
            tm("modelParameters.saved")
          }}</span>
          <v-btn
            :disabled="!dirty || valid !== true"
            :loading="saving"
            color="primary"
            variant="tonal"
            @click="saveParameters"
          >
            {{ tm("modelParameters.save") }}
          </v-btn>
        </div>
      </v-form>
    </template>
    <p v-else-if="!loading && !error" class="model-parameters__hint">
      {{ tm("modelParameters.noModel") }}
    </p>
  </section>
</template>

<script setup>
import {
  computed,
  inject,
  reactive,
  ref,
  shallowRef,
  toRefs,
  watch,
} from "vue";
import { providerApi } from "@/api/v1";
import {
  getConfigTemplateValue,
  normalizeConfigValue,
} from "@/utils/configValue.mjs";
import ConfigItemRenderer from "@/components/shared/ConfigItemRenderer.vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps({ providerId: { type: String, default: "" } });
const { tm } = useModuleI18n("features/config");
const editorState = inject("modelParameterEditorState", shallowRef(null));
editorState.value ||= reactive({
  draft: null,
  original: "",
  loading: false,
  saving: false,
  saved: false,
  error: "",
  sourceType: "",
  thinkingConfig: {},
  modelSchema: {},
});
const {
  draft,
  original,
  loading,
  saving,
  saved,
  error,
  sourceType,
  thinkingConfig,
  modelSchema,
} = toRefs(editorState.value);
const valid = ref(false);
const reload = ref(0);
const parameterSchema = computed(
  () => modelSchema.value.custom_extra_body?.template_schema || {},
);
const supportsExtraBody = computed(
  () => sourceType.value !== "googlegenai_chat_completion",
);
const isAnthropic = computed(() =>
  [
    "anthropic_chat_completion",
    "kimi_code_chat_completion",
    "minimax_token_plan",
    "xiaomi_token_plan",
  ].includes(sourceType.value),
);
const supportsReasoning = computed(
  () =>
    supportsExtraBody.value &&
    (!isAnthropic.value || thinkingConfig.value.type === "adaptive"),
);
const effortOptions = computed(() =>
  Array.from(
    new Set(
      [
        "low",
        "medium",
        "high",
        ...(isAnthropic.value ? ["max"] : []),
        getConfigTemplateValue(
          draft.value?.custom_extra_body?.reasoning_effort,
          parameterSchema.value.reasoning_effort,
        ),
      ].filter(Boolean),
    ),
  ),
);
const modalitiesMetadata = computed(
  () =>
    modelSchema.value.modalities || {
      type: "list",
      render_type: "checkbox",
      options: ["text", "image", "audio", "tool_use"],
      labels: ["text", "image", "audio", "tool_use"].map((key) =>
        tm(`modelParameters.${key}`),
      ),
    },
);
const dirty = computed(
  () => draft.value && JSON.stringify(draft.value) !== original.value,
);
const temperatureRules = [
  (value) =>
    value == null ||
    value === "" ||
    (Number.isFinite(Number(value)) &&
      Number(value) >= 0 &&
      Number(value) <= 2) ||
    tm("modelParameters.invalidTemperature"),
];
const tokenRules = [
  (value) =>
    value == null ||
    value === "" ||
    (Number.isSafeInteger(Number(value)) && Number(value) > 0) ||
    tm("modelParameters.invalidTokens"),
];

watch(
  [() => props.providerId, reload],
  async ([providerId], _, onCleanup) => {
    // Search and tab navigation may remount this editor while edits or a save remain pending.
    if (
      providerId &&
      draft.value?.id === providerId &&
      (dirty.value || saving.value)
    )
      return;
    let cancelled = false;
    onCleanup(() => {
      cancelled = true;
    });
    draft.value = null;
    loading.value = false;
    error.value = "";
    saved.value = false;
    // Configuration order does not identify the runtime's automatic model selection.
    if (!providerId) return;
    loading.value = true;
    try {
      const response = await providerApi.schema();
      if (cancelled) return;
      if (response.data.status === "error")
        throw new Error(response.data.message);
      const data = response.data.data;
      const providers = data.providers || [];
      const provider = providers.find((item) => item.id === providerId);
      if (!provider) return;
      const source = data.provider_sources?.find(
        (item) => item.id === provider.provider_source_id,
      );
      const effectiveProvider = { ...source, ...provider };
      sourceType.value = effectiveProvider.type;
      thinkingConfig.value = effectiveProvider.anth_thinking_config || {};
      modelSchema.value = data.config_schema?.provider?.items || {};
      const extraBody = effectiveProvider.custom_extra_body || {};
      // Keep only the editable fields; fetch the latest full configuration when saving.
      draft.value = {
        id: provider.id,
        modalities: [...(effectiveProvider.modalities || ["text"])],
        custom_extra_body: Object.fromEntries(
          ["temperature", "max_tokens", "reasoning_effort"].map((key) => [
            key,
            extraBody[key],
          ]),
        ),
      };
      // Native request parameters override aliases in the backend adapters.
      if (sourceType.value === "openai_responses") {
        if ("max_output_tokens" in extraBody)
          draft.value.custom_extra_body.max_tokens =
            extraBody.max_output_tokens;
        if ("reasoning" in extraBody)
          draft.value.custom_extra_body.reasoning_effort =
            extraBody.reasoning?.effort;
      } else if (isAnthropic.value) {
        draft.value.custom_extra_body.reasoning_effort =
          "output_config" in extraBody
            ? extraBody.output_config?.effort
            : thinkingConfig.value.effort;
      }
      original.value = JSON.stringify(draft.value);
    } catch (err) {
      if (!cancelled)
        error.value = err.message || tm("modelParameters.loadError");
    } finally {
      if (!cancelled) loading.value = false;
    }
  },
  { immediate: true },
);

/**
 * Save native model parameters while preserving the latest unrelated settings.
 *
 * Returns:
 *     Resolves after saving or displaying the API error in the form.
 */
async function saveParameters() {
  if (
    saving.value ||
    !props.providerId ||
    draft.value?.id !== props.providerId ||
    !dirty.value ||
    valid.value !== true
  )
    return;
  const currentDraft = draft.value;
  const snapshot = JSON.stringify(currentDraft);
  const edited = JSON.parse(snapshot);
  const baseline = JSON.parse(original.value);
  const changedParameters = [
    "temperature",
    "max_tokens",
    "reasoning_effort",
  ].filter(
    (key) => edited.custom_extra_body[key] !== baseline.custom_extra_body[key],
  );
  const extraBodyEnabled = supportsExtraBody.value;
  const anthropic = isAnthropic.value;
  const providerType = sourceType.value;
  const schema = parameterSchema.value;
  saving.value = true;
  error.value = "";
  saved.value = false;
  try {
    const [response, mergedResponse] = await Promise.all([
      providerApi.get(currentDraft.id),
      providerApi.get(currentDraft.id, true),
    ]);
    for (const result of [response, mergedResponse]) {
      if (result.data.status === "error") throw new Error(result.data.message);
    }
    const provider = response.data.data.provider;
    const effectiveProvider = mergedResponse.data.data.provider;
    if (!provider || !effectiveProvider)
      throw new Error(tm("modelParameters.noModel"));
    if (
      JSON.stringify(edited.modalities) !== JSON.stringify(baseline.modalities)
    )
      provider.modalities = [...edited.modalities];
    if (extraBodyEnabled && changedParameters.length) {
      // Copy only editable source defaults so credentials and other source fields stay inherited.
      provider.custom_extra_body = { ...effectiveProvider.custom_extra_body };
      // Preserve newer values from other editors for fields unchanged in this draft.
      for (const key of changedParameters) {
        const value = edited.custom_extra_body[key];
        const cleared = value == null || value === "";
        const normalized = cleared
          ? undefined
          : normalizeConfigValue(value, schema[key]);
        const extraBody = provider.custom_extra_body;
        let target = extraBody;
        let parameter = key;
        if (anthropic && key === "reasoning_effort") {
          delete extraBody.reasoning_effort;
          if (effectiveProvider.anth_thinking_config?.type !== "adaptive")
            continue;
          target = provider.anth_thinking_config = {
            ...effectiveProvider.anth_thinking_config,
          };
          parameter = "effort";
          // Existing native body overrides must agree with the thinking configuration.
          if ("output_config" in extraBody) {
            extraBody.output_config = { ...extraBody.output_config };
            if (cleared) delete extraBody.output_config.effort;
            else extraBody.output_config.effort = normalized;
            if (!Object.keys(extraBody.output_config).length)
              delete extraBody.output_config;
          }
        } else if (
          providerType === "openai_responses" &&
          key === "reasoning_effort"
        ) {
          delete extraBody.reasoning_effort;
          target = extraBody.reasoning = { ...extraBody.reasoning };
          parameter = "effort";
        } else if (
          providerType === "openai_responses" &&
          key === "max_tokens"
        ) {
          delete extraBody.max_tokens;
          parameter = "max_output_tokens";
        }
        if (cleared) delete target[parameter];
        else target[parameter] = normalized;
        if (
          providerType === "openai_responses" &&
          key === "reasoning_effort" &&
          !Object.keys(target).length
        )
          delete extraBody.reasoning;
      }
    }
    const result = await providerApi.update(currentDraft.id, provider);
    if (result.data.status === "error") throw new Error(result.data.message);
    if (draft.value === currentDraft) {
      original.value = snapshot;
      saved.value = true;
    }
  } catch (err) {
    if (draft.value === currentDraft)
      error.value =
        err.response?.data?.message ||
        err.message ||
        tm("modelParameters.saveError");
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.model-parameters {
  margin: 8px 20px 20px;
  padding: 16px;
  border-radius: 10px;
  background: rgba(var(--v-theme-primary), 0.035);
}
.model-parameters__heading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.model-parameters__heading span,
.model-parameters__hint {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 0.78rem;
}
.model-parameters__hint {
  margin: 5px 0 0;
  line-height: 1.5;
}
.model-parameters__row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: center;
  margin-top: 18px;
}
.model-parameters__row strong {
  font-size: 0.88rem;
}
.model-parameters__control {
  min-width: 0;
}
.model-parameters__actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  font-size: 0.78rem;
}
@media (max-width: 600px) {
  .model-parameters {
    margin: 8px 12px 16px;
  }
  .model-parameters__row {
    grid-template-columns: 1fr;
    gap: 10px;
  }
}
</style>
