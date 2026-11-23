<template>
  <div class="w-100" :class="{ 'config-field--full-width': itemMeta?.full_width }">
    <!-- Special handling for specific metadata types -->
    <template v-if="itemMeta?._special === 'umo'">
      <UmoSelector
        :model-value="selectorValue"
        :multiple="itemMeta?.type === 'list'"
        :readonly="Boolean(itemMeta?.readonly)"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'sender_id'">
      <SenderSelector
        :model-value="arrayValue"
        :readonly="Boolean(itemMeta?.readonly)"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider'">
      <ProviderSelector :model-value="selectorValue" @update:model-value="emitUpdate" :provider-type="'chat_completion'" />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider_stt'">
      <ProviderSelector
        :model-value="selectorValue"
        :provider-type="'speech_to_text'"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider_tts'">
      <ProviderSelector
        :model-value="selectorValue"
        :provider-type="'text_to_speech'"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_providers'">
      <ProviderSelector
        :model-value="selectorValue"
        :provider-type="'chat_completion'"
        :multiple="true"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'provider_pool'">
      <ProviderSelector
        :model-value="selectorValue"
        :provider-type="'chat_completion'"
        :button-text="t('core.shared.providerSelector.selectProviderPool')"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_agent_configs'">
      <AgentConfigSelector :model-value="stringArrayValue" @update:model-value="emitUpdate" />
    </template>
    <template v-else-if="itemMeta?._special === 'select_persona'">
      <PersonaSelector
        :model-value="stringValue"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'persona_pool'">
      <PersonaSelector
        :model-value="stringValue"
        :button-text="t('core.shared.personaSelector.selectPersonaPool')"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_knowledgebase'">
      <KnowledgeBaseSelector
        :model-value="arrayValue"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_plugin_set'">
      <PluginSetSelector :model-value="arrayValue" :selection-only="itemMeta?.selection_only" @update:model-value="emitUpdate" />
    </template>
    <template v-else-if="itemMeta?._special === 't2i_template'">
      <T2ITemplateEditor />
    </template>
    <template v-else-if="itemMeta?._special === 'dashboard_totp_manager'">
      <DashboardTotpManager
        :model-value="Boolean(modelValue)"
        :config-root="configRoot"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'local_permission_matrix'">
      <LocalPermissionMatrix
        :model-value="objectValue"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'get_embedding_dim'">
      <div class="d-flex align-center gap-2">
        <v-text-field
          :model-value="modelValue"
          density="compact"
          variant="outlined"
          class="config-field"
          type="number"
          hide-details
          @update:model-value="emitUpdate"
        />
        <v-btn
          color="primary"
          variant="tonal"
          size="small"
          :loading="loading"
          class="ml-2"
          @click="$emit('get-embedding-dim')"
        >
          {{ t("core.common.autoDetect") }}
        </v-btn>
      </div>
    </template>

    <div
      v-else-if="
        itemMeta?.type === 'list' &&
        itemMeta?.options &&
        itemMeta?.render_type === 'checkbox'
      "
      class="checkbox-group d-flex flex-wrap gap-20"
    >
      <v-checkbox
        v-for="(option, optionIndex) in itemMeta.options"
        :key="optionIndex"
        :model-value="modelValue"
        :label="getLabel(itemMeta, optionIndex, option)"
        :value="option"
        class="config-checkbox"
        color="primary"
        density="compact"
        hide-details
        @update:model-value="emitUpdate"
      />
    </div>

    <v-autocomplete
      v-else-if="itemMeta?.type === 'list' && itemMeta?.options"
      :model-value="arrayValue"
      @update:model-value="val => { emitUpdate(val); listSearchText = '' }"
      v-model:search="listSearchText"
      :items="listSelectItems"
      item-title="title"
      item-value="value"
      :disabled="itemMeta?.readonly"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
      chips
      multiple
    />

    <v-select
      v-else-if="itemMeta?.options"
      :model-value="modelValue"
      :items="getSelectItems(itemMeta)"
      :disabled="itemMeta?.readonly"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
      @update:model-value="emitUpdate"
    />

    <div v-else-if="itemMeta?.editor_mode" class="editor-container">
      <VueMonacoEditor
        :theme="itemMeta?.editor_theme || 'vs-light'"
        :language="itemMeta?.editor_language || 'json'"
        style="
          min-height: 100px;
          flex-grow: 1;
          border: 1px solid rgba(0, 0, 0, 0.1);
        "
        :value="stringValue"
        @update:value="emitUpdate"
      />
      <v-btn
        v-if="showFullscreenBtn"
        icon
        size="small"
        variant="text"
        color="primary"
        class="editor-fullscreen-btn"
        :title="t('core.common.editor.fullscreen')"
        @click="$emit('open-fullscreen')"
      >
        <v-icon>mdi-fullscreen</v-icon>
      </v-btn>
    </div>

    <v-text-field
      v-else-if="itemMeta?.type === 'string'"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      :type="stringInputType"
      :append-inner-icon="secretToggleIcon"
      :autocomplete="itemMeta?.secret ? 'new-password' : undefined"
      @click:append-inner="secretVisible = !secretVisible"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
    />

    <div v-else-if="itemMeta?.type === 'int' || itemMeta?.type === 'float'" class="d-flex align-center gap-3">
      <div v-if="itemMeta?.slider" style="flex: 3; display: flex; align-items: center; gap: 8px">
        <span style="min-width: 5px; text-align: right;">
          {{ itemMeta?.slider?.min ?? 0 }}
        </span>

        <v-slider :model-value="toNumber(numericTemp ?? modelValue)"
          @update:model-value="val => { numericTemp = val; emitUpdate(toNumber(val)) }"
          @end="numericTemp = null"
          :min="itemMeta?.slider?.min ?? 0"
          :max="itemMeta?.slider?.max ?? 100"
          :step="itemMeta?.slider?.step ?? 1"
          color="primary"
          density="compact"
          hide-details
          style="flex: 1"></v-slider>

        <span style="min-width: 5px; text-align: left;">
          {{ itemMeta?.slider?.max ?? 100 }}
        </span>
      </div>

      <v-text-field
        :model-value="numericTemp ?? modelValue"
        @update:model-value="val => (numericTemp = val)"
        @blur="() => {
          if (numericTemp != null) {
            emitUpdate(itemMeta?.nullable && numericTemp === '' ? null : toNumber(numericTemp))
          }
          numericTemp = null
        }"
        density="compact"
        variant="outlined"
        class="config-field"
        type="number"
        hide-details
        style="flex: 2"
      ></v-text-field>
    </div>

    <v-textarea
      v-else-if="itemMeta?.type === 'text'"
      :model-value="modelValue"
      variant="outlined"
      rows="3"
      class="config-field"
      hide-details
      @update:model-value="emitUpdate"
    />

    <v-switch
      v-else-if="itemMeta?.type === 'bool'"
      :model-value="modelValue"
      color="primary"
      inset
      density="compact"
      hide-details
      @update:model-value="emitUpdate"
    />

    <FileConfigItem
      v-else-if="itemMeta?.type === 'file'"
      :model-value="arrayValue"
      :item-meta="itemMeta"
      :plugin-name="pluginName"
      :config-key="configKey"
      class="config-field"
      @update:model-value="emitUpdate"
    />

    <ListConfigItem
      v-else-if="itemMeta?.type === 'list'"
      :model-value="arrayValue"
      @update:model-value="emitUpdate"
      :secret="Boolean(itemMeta?.secret)"
      class="config-field"
    />

    <ObjectEditor
      v-else-if="itemMeta?.type === 'dict'"
      :model-value="objectValue"
      :item-meta="itemMeta"
      :plugin-name="pluginName"
      :plugin-i18n="pluginI18n"
      :config-key="configKey"
      @update:model-value="emitUpdate"
      class="config-field"
    />

    <v-text-field
      v-else
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      :type="stringInputType"
      :append-inner-icon="secretToggleIcon"
      :autocomplete="itemMeta?.secret ? 'new-password' : undefined"
      @click:append-inner="secretVisible = !secretVisible"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
    />
  </div>
</template>

<script setup lang="ts">
import { computed, type PropType, ref } from "vue";
import { LazyMonacoEditor as VueMonacoEditor } from "@/components/shared/LazyMonacoEditor";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { usePluginI18n } from "@/utils/pluginI18n";
import { isRecord, stringArray } from "@/utils/typeGuards";
import AgentConfigSelector from "./AgentConfigSelector.vue";
import DashboardTotpManager from "./DashboardTotpManager.vue";
import FileConfigItem from "./FileConfigItem.vue";
import KnowledgeBaseSelector from "./KnowledgeBaseSelector.vue";
import ListConfigItem from "./ListConfigItem.vue";
import LocalPermissionMatrix from "./LocalPermissionMatrix.vue";
import ObjectEditor from "./ObjectEditor.vue";
import PersonaSelector from "./PersonaSelector.vue";
import PluginSetSelector from "./PluginSetSelector.vue";
import ProviderSelector from "./ProviderSelector.vue";
import SenderSelector from "./SenderSelector.vue";
import T2ITemplateEditor from "./T2ITemplateEditor.vue";
import UmoSelector from "./UmoSelector.vue";

interface SliderConfig {
  min: number;
  max: number;
  step: number;
}

interface ItemMeta {
  template_schema?: Record<string, ItemMeta>;
  runtime_defaults?: Record<string, Record<string, unknown>>;
  _special?: string;
  type?: string;
  options?: unknown[];
  render_type?: string;
  readonly?: boolean;
  selection_only?: boolean;
  editor_mode?: boolean;
  editor_theme?: string;
  editor_language?: string;
  slider?: SliderConfig;
  labels?: string | string[];
  name?: string;
  description?: string;
  [key: string]: unknown;
}

const numericTemp = ref<number | string | null>(null);
const listSearchText = ref("");
const secretVisible = ref(false);

const props = defineProps({
  modelValue: {
    type: [String, Number, Boolean, Array, Object],
    default: null,
  },
  itemMeta: {
    type: Object as PropType<ItemMeta | null>,
    default: null,
  },
  pluginName: {
    type: String,
    default: "",
  },
  pluginI18n: {
    type: Object,
    default: () => ({}),
  },
  configKey: {
    type: String,
    default: "",
  },
  loading: {
    type: Boolean,
    default: false,
  },
  showFullscreenBtn: {
    type: Boolean,
    default: false,
  },
  configRoot: {
    type: Object,
    default: null,
  },
});

const stringValue = computed(() => (typeof props.modelValue === "string" ? props.modelValue : ""));
const arrayValue = computed(() => (Array.isArray(props.modelValue) ? props.modelValue : []));
const stringArrayValue = computed(() => stringArray(props.modelValue));
const selectorValue = computed(() =>
  typeof props.modelValue === "string" ? props.modelValue : stringArrayValue.value,
);
const objectValue = computed(() => (isRecord(props.modelValue) ? props.modelValue : {}));

const emit = defineEmits(["update:modelValue", "get-embedding-dim", "open-fullscreen"]);
const { t } = useI18n();
const { getRaw } = useModuleI18n("features/config-metadata");
const { configText } = usePluginI18n();

function emitUpdate(rawValue: unknown): void {
  const val = validateNumericConfig(props.itemMeta?.type, rawValue);
  if (
    props.itemMeta?._special === "agent_runtime" &&
    props.configRoot?.agent &&
    typeof val === "string" &&
    props.itemMeta?.runtime_defaults?.[val]
  ) {
    props.configRoot.agent.config = JSON.parse(JSON.stringify(props.itemMeta.runtime_defaults[val]));
  }
  emit("update:modelValue", val);
}

const listSelectItems = computed(() =>
  props.itemMeta?.type === "list" && props.itemMeta?.options ? getSelectItems(props.itemMeta) : [],
);

const stringInputType = computed(() => (props.itemMeta?.secret && !secretVisible.value ? "password" : "text"));
const secretToggleIcon = computed(() => {
  if (!props.itemMeta?.secret) return undefined;
  return secretVisible.value ? "mdi-eye-off-outline" : "mdi-eye-outline";
});

function toNumber(val: unknown): number {
  const n = parseFloat(String(val));
  return Number.isNaN(n) ? 0 : n;
}

function validateNumericConfig(modelType: string | undefined, rawValue: unknown): unknown {
  if (modelType === "int" || modelType === "float") {
    // 如果有滑动条定义，应用边界限制
    const slider = props.itemMeta?.slider;
    if (slider) {
      const min = slider.min ?? 0;
      const max = slider.max ?? 100;
      return Math.max(min, Math.min(max, Number(rawValue)));
    } else {
      return rawValue;
    }
  } else if (modelType === "dict" && rawValue !== null && typeof rawValue === "object" && !Array.isArray(rawValue)) {
    Object.entries(rawValue).forEach(([key, value]) => {
      const templatesSchema = props.itemMeta?.template_schema;
      const templateType = templatesSchema?.[key]?.type;
      const templateSlider = templatesSchema?.[key]?.slider;
      if ((templateType === "int" || templateType === "float") && templateSlider) {
        const min = templateSlider.min ?? 0;
        const max = templateSlider.max ?? 100;
        (rawValue as Record<string, unknown>)[key] = Math.max(min, Math.min(max, Number(value)));
      }
    });
    return rawValue;
  } else {
    return rawValue;
  }
}

function getLabel(itemMeta: ItemMeta, index: number, option: unknown): string {
  const labels = getTranslatedLabels(itemMeta);
  return labels ? String(labels[index] ?? option) : String(option);
}

function getTranslatedLabels(itemMeta: ItemMeta): string[] | null {
  if (props.pluginName && props.configKey && props.pluginI18n && Object.keys(props.pluginI18n).length > 0) {
    const translatedLabels = configText(props.pluginI18n, props.configKey, "labels");
    if (Array.isArray(translatedLabels)) {
      return translatedLabels as string[];
    }
  }
  if (!itemMeta?.labels) return null;
  if (typeof itemMeta.labels === "string") {
    const translatedLabels = getRaw(itemMeta.labels);
    if (Array.isArray(translatedLabels)) {
      return translatedLabels;
    }
  }
  if (Array.isArray(itemMeta.labels)) {
    return itemMeta.labels;
  }
  return null;
}

function getSelectItems(itemMeta: ItemMeta) {
  const labels = getTranslatedLabels(itemMeta);
  let subtitles = itemMeta?.subtitles;
  if (props.pluginName && props.configKey && props.pluginI18n && Object.keys(props.pluginI18n).length > 0) {
    const translatedSubtitles = configText(props.pluginI18n, props.configKey, "subtitles");
    if (Array.isArray(translatedSubtitles)) {
      subtitles = translatedSubtitles;
    }
  }
  if (typeof subtitles === "string") {
    subtitles = getRaw(subtitles);
  }
  const subtitleLabels = Array.isArray(subtitles) ? subtitles : null;

  if ((labels || subtitleLabels) && itemMeta.options) {
    return itemMeta.options.map((value, index) => ({
      title: labels?.[index] || value,
      value: value,
      props: {
        subtitle: typeof subtitleLabels?.[index] === "string" ? subtitleLabels[index] : undefined,
      },
    }));
  }
  return itemMeta.options || [];
}
</script>

<style scoped>
.config-field {
  margin-bottom: 0;
}

.editor-container {
  position: relative;
  display: flex;
  width: 100%;
}

.editor-fullscreen-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 10;
  background-color: rgba(0, 0, 0, 0.3);
  border-radius: 4px;
}

.editor-fullscreen-btn:hover {
  background-color: rgba(0, 0, 0, 0.5);
}

.checkbox-group {
  gap: 6px 12px;
}

.config-checkbox {
  margin-right: 0;
}

.config-checkbox :deep(.v-selection-control) {
  min-height: 28px;
}

.config-checkbox :deep(.v-selection-control__wrapper) {
  width: 18px;
  height: 18px;
}

.config-checkbox :deep(.v-icon) {
  font-size: 18px;
}

.config-checkbox :deep(.v-label) {
  font-size: 0.9rem;
}

::v-deep(.v-field__input) {
  font-size: 14px;
}

:deep(.config-field input[type="number"]::-webkit-inner-spin-button),
:deep(.config-field input[type="number"]::-webkit-outer-spin-button) {
  -webkit-appearance: none;
}

:deep(.config-field input[type="number"]) {
  -moz-appearance: textfield;
}
</style>
