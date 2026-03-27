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
      class="d-flex flex-wrap gap-20"
    >
      <v-checkbox
        v-for="(option, optionIndex) in itemMeta.options"
        :key="optionIndex"
        :model-value="modelValue"
        :label="getLabel(itemMeta, optionIndex, option)"
        :value="option"
        class="mr-2"
        color="primary"
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
        :model-value="modelValue"
        density="compact"
        variant="outlined"
        class="config-field"
        type="number"
        hide-details
        style="flex: 1"
        @update:model-value="(val) => emitUpdate(toNumber(val))"
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

    <ListConfigItem
      v-else-if="itemMeta?.type === 'list'"
      :model-value="modelValue"
      class="config-field"
      @update:model-value="emitUpdate"
    />

    <ObjectEditor
      v-else-if="itemMeta?.type === 'dict'"
      :model-value="modelValue"
      :item-meta="itemMeta"
      class="config-field"
      @update:model-value="emitUpdate"
    />

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

const props = defineProps({
  modelValue: {
    type: [String, Number, Boolean, Array, Object],
    default: null,
  },
  itemMeta: {
    type: Object,
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

function emitUpdate(val) {
  emit("update:modelValue", val);
}

function toNumber(val) {
  const n = parseFloat(val);
  return isNaN(n) ? 0 : n;
}

function getLabel(itemMeta, index, option) {
  const labels = getTranslatedLabels(itemMeta);
  return labels ? labels[index] : option;
}

function getTranslatedLabels(itemMeta) {
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

function getSelectItems(itemMeta) {
  const labels = getTranslatedLabels(itemMeta);
  if (labels && itemMeta.options) {
    return itemMeta.options.map((value, index) => ({
      title: labels[index] || value,
      value: value,
    }));
  }
  return itemMeta.options || [];
}

function parseSpecialValue(value) {
  if (!value || typeof value !== "string") {
    return { name: "", subtype: "" };
  }
  const [name, ...rest] = value.split(":");
  return {
    name,
    subtype: rest.join(":") || "",
  };
}

function getSpecialName(value) {
  return parseSpecialValue(value).name;
}

function getSpecialSubtype(value) {
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

.gap-20 {
  gap: 20px;
}

::v-deep(.v-field__input) {
  font-size: 14px;
}
</style>
