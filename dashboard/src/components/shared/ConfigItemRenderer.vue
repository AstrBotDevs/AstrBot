<template>
  <div class="w-100">
    <!-- Special handling for specific metadata types -->
    <template v-if="itemMeta?._special === 'select_provider'">
      <ProviderSelector
        :model-value="modelValue"
        :provider-type="'chat_completion'"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider_stt'">
      <ProviderSelector
        :model-value="modelValue"
        :provider-type="'speech_to_text'"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider_tts'">
      <ProviderSelector
        :model-value="modelValue"
        :provider-type="'text_to_speech'"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_providers'">
      <ProviderSelector
        :model-value="modelValue"
        :provider-type="'chat_completion'"
        :multiple="true"
        @update:model-value="emitUpdate"
      />
    </template>
    <template
      v-else-if="
        getSpecialName(itemMeta?._special) === 'select_agent_runner_provider'
      "
    >
      <ProviderSelector
        :model-value="modelValue"
        :provider-type="'agent_runner'"
        :provider-subtype="getSpecialSubtype(itemMeta?._special)"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'provider_pool'">
      <ProviderSelector
        :model-value="modelValue"
        :provider-type="'chat_completion'"
        :button-text="t('core.shared.providerSelector.selectProviderPool')"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_persona'">
      <PersonaSelector
        :model-value="modelValue"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'persona_pool'">
      <PersonaSelector
        :model-value="modelValue"
        :button-text="t('core.shared.personaSelector.selectPersonaPool')"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_knowledgebase'">
      <KnowledgeBaseSelector
        :model-value="modelValue"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_plugin_set'">
      <PluginSetSelector
        :model-value="modelValue"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 't2i_template'">
      <T2ITemplateEditor />
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

    <v-combobox
      v-else-if="itemMeta?.type === 'list' && itemMeta?.options"
      :model-value="modelValue"
      :items="itemMeta.options"
      :disabled="itemMeta?.readonly"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
      chips
      multiple
      @update:model-value="emitUpdate"
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
        :value="modelValue"
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
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
      @update:model-value="emitUpdate"
    />

    <div
      v-else-if="itemMeta?.type === 'int' || itemMeta?.type === 'float'"
      class="d-flex align-center gap-3"
    >
      <v-slider
        v-if="itemMeta?.slider"
        :model-value="toNumber(modelValue)"
        :min="itemMeta?.slider?.min ?? 0"
        :max="itemMeta?.slider?.max ?? 100"
        :step="itemMeta?.slider?.step ?? 1"
        color="primary"
        density="compact"
        hide-details
        style="flex: 1"
        @update:model-value="(val) => emitUpdate(toNumber(val))"
      />
      <v-text-field
        :model-value="numericTemp ?? modelValue"
        @update:model-value="(val) => (numericTemp = val)"
        @blur="
          () => {
            if (numericTemp != null) {
              emitUpdate(toNumber(numericTemp));
            }
            numericTemp = null;
          }
        "
        density="compact"
        variant="outlined"
        class="config-field"
        type="number"
        hide-details
        style="flex: 1"
      />
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
      :model-value="modelValue"
      :item-meta="itemMeta"
      :plugin-name="pluginName"
      :config-key="configKey"
      class="config-field"
      @update:model-value="emitUpdate"
    />

    <div v-else-if="itemMeta?.type === 'list'" class="config-field">
      <ListConfigItem
        :model-value="modelValue"
        @update:model-value="emitUpdate"
      />
    </div>

    <div v-else-if="itemMeta?.type === 'dict'" class="config-field">
      <ObjectEditor
        :model-value="modelValue"
        :item-meta="itemMeta"
        @update:model-value="emitUpdate"
      />
    </div>

    <v-text-field
      v-else
      :model-value="modelValue"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
      @update:model-value="emitUpdate"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, type PropType } from "vue";

import { VueMonacoEditor } from "@guolao/vue-monaco-editor";
import ListConfigItem from "./ListConfigItem.vue";
import FileConfigItem from "./FileConfigItem.vue";
import ObjectEditor from "./ObjectEditor.vue";
import ProviderSelector from "./ProviderSelector.vue";
import PersonaSelector from "./PersonaSelector.vue";
import KnowledgeBaseSelector from "./KnowledgeBaseSelector.vue";
import PluginSetSelector from "./PluginSetSelector.vue";
import T2ITemplateEditor from "./T2ITemplateEditor.vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";

interface SliderConfig {
  min: number;
  max: number;
  step: number;
}

interface ItemMeta {
  template_schema?: Record<string, unknown>;
  _special?: string;
  type?: string;
  options?: unknown[];
  render_type?: string;
  readonly?: boolean;
  editor_mode?: boolean;
  editor_theme?: string;
  editor_language?: string;
  slider?: SliderConfig;
  labels?: string | string[];
  name?: string;
  description?: string;
  [key: string]: unknown;
}

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
});

const emit = defineEmits([
  "update:modelValue",
  "get-embedding-dim",
  "open-fullscreen",
]);
const { t } = useI18n();
const { getRaw } = useModuleI18n("features/config-metadata");

const numericTemp = ref<number | null>(null);

function emitUpdate(val: unknown) {
  emit("update:modelValue", val);
}

function toNumber(val: unknown): number {
  const n = parseFloat(String(val));
  return isNaN(n) ? 0 : n;
}

function getLabel(itemMeta: ItemMeta, index: number, option: unknown): string {
  const labels = getTranslatedLabels(itemMeta);
  return labels ? String(labels[index] ?? option) : String(option);
}

function getTranslatedLabels(itemMeta: ItemMeta): string[] | null {
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

function getSelectItems(itemMeta: ItemMeta): unknown[] {
  const labels = getTranslatedLabels(itemMeta);
  if (labels && itemMeta.options) {
    return itemMeta.options.map((value, index) => ({
      title: labels[index] || value,
      value: value,
    }));
  }
  return itemMeta.options || [];
}

function parseSpecialValue(
  value: string | undefined,
): { name: string; subtype: string } {
  if (!value || typeof value !== "string") {
    return { name: "", subtype: "" };
  }
  const [name, ...rest] = value.split(":");
  return {
    name,
    subtype: rest.join(":") || "",
  };
}

function getSpecialName(value: string | undefined): string {
  return parseSpecialValue(value).name;
}

function getSpecialSubtype(value: string | undefined): string {
  return parseSpecialValue(value).subtype;
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
</style>
