<template>
  <div class="w-100">
    <!-- Special handling for specific metadata types -->
    <template v-if="itemMeta?._special === 'select_provider'">
      <ProviderSelector :model-value="modelValue" @update:model-value="emitUpdate" :provider-type="'chat_completion'" />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider_stt'">
      <ProviderSelector :model-value="modelValue" @update:model-value="emitUpdate" :provider-type="'speech_to_text'" />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider_tts'">
      <ProviderSelector :model-value="modelValue" @update:model-value="emitUpdate" :provider-type="'text_to_speech'" />
    </template>
    <template v-else-if="itemMeta?._special === 'select_providers'">
      <ProviderSelector
        :model-value="modelValue"
        @update:model-value="emitUpdate"
        :provider-type="'chat_completion'"
        :multiple="true"
      />
    </template>
    <template v-else-if="getSpecialName(itemMeta?._special) === 'select_agent_runner_provider'">
      <ProviderSelector
        :model-value="modelValue"
        @update:model-value="emitUpdate"
        :provider-type="'agent_runner'"
        :provider-subtype="getSpecialSubtype(itemMeta?._special)"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'provider_pool'">
      <ProviderSelector :model-value="modelValue" @update:model-value="emitUpdate" :provider-type="'chat_completion'"
        :button-text="t('core.shared.providerSelector.selectProviderPool')" />
    </template>
    <template v-else-if="itemMeta?._special === 'select_persona'">
      <PersonaSelector :model-value="modelValue" @update:model-value="emitUpdate" />
    </template>
    <template v-else-if="itemMeta?._special === 'persona_pool'">
      <PersonaSelector :model-value="modelValue" @update:model-value="emitUpdate" :button-text="t('core.shared.personaSelector.selectPersonaPool')" />
    </template>
    <template v-else-if="itemMeta?._special === 'select_knowledgebase'">
      <KnowledgeBaseSelector :model-value="modelValue" @update:model-value="emitUpdate" />
    </template>
    <template v-else-if="itemMeta?._special === 'select_plugin_set'">
      <PluginSetSelector :model-value="modelValue" @update:model-value="emitUpdate" />
    </template>
    <template v-else-if="itemMeta?._special === 't2i_template'">
      <T2ITemplateEditor />
    </template>
    <template v-else-if="itemMeta?._special === 'get_embedding_dim'">
      <div class="d-flex align-center gap-2">
        <v-text-field
          :model-value="modelValue"
          @update:model-value="emitUpdate"
          density="compact"
          variant="outlined"
          class="config-field"
          type="number"
          hide-details
        ></v-text-field>
        <v-btn
          color="primary"
          variant="tonal"
          size="small"
          @click="$emit('get-embedding-dim')"
          :loading="loading"
          class="ml-2"
        >
          {{ t('core.common.autoDetect') }}
        </v-btn>
      </div>
    </template>

    <div
      v-else-if="itemMeta?.type === 'list' && itemMeta?.options && itemMeta?.render_type === 'checkbox'"
      class="checkbox-group d-flex flex-wrap"
    >
      <v-checkbox
        v-for="(option, optionIndex) in itemMeta.options"
        :key="optionIndex"
        :model-value="modelValue"
        @update:model-value="emitUpdate"
        :label="getLabel(itemMeta, optionIndex, option)"
        :value="option"
        class="config-checkbox"
        color="primary"
        density="compact"
        hide-details
      ></v-checkbox>
    </div>

    <v-select
      v-else-if="itemMeta?.type === 'list' && itemMeta?.options"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      :items="getSelectItems(itemMeta)"
      item-title="title"
      item-value="value"
      :disabled="itemMeta?.readonly"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
      chips
      multiple
    ></v-select>

    <v-select
      v-else-if="itemMeta?.options"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      :items="getSelectItems(itemMeta)"
      :disabled="itemMeta?.readonly"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
    ></v-select>

    <div v-else-if="itemMeta?.editor_mode" class="editor-container">
      <VueMonacoEditor
        :theme="itemMeta?.editor_theme || 'vs-light'"
        :language="itemMeta?.editor_language || 'json'"
        style="min-height: 100px; flex-grow: 1; border: 1px solid rgba(0, 0, 0, 0.1);"
        :value="modelValue"
        @update:value="emitUpdate"
      >
      </VueMonacoEditor>
      <v-btn v-if="showFullscreenBtn" icon size="small" variant="text" color="primary" class="editor-fullscreen-btn"
        @click="$emit('open-fullscreen')"
        :title="t('core.common.editor.fullscreen')">
        <v-icon>mdi-fullscreen</v-icon>
      </v-btn>
    </div>

    <v-text-field
      v-else-if="itemMeta?.type === 'string'"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
    ></v-text-field>

    <div
      v-else-if="itemMeta?.type === 'int' || itemMeta?.type === 'float'"
      class="d-flex align-center gap-3"
    >
      <v-slider
        v-if="itemMeta?.slider"
        :model-value="toNumber(numericTemp ?? modelValue)"
        @update:model-value="val => { numericTemp = val; emitUpdate(toNumber(val)) }"
        @end="numericTemp = null"
        :min="itemMeta?.slider?.min ?? 0"
        :max="itemMeta?.slider?.max ?? 100"
        :step="itemMeta?.slider?.step ?? 1"
        color="primary"
        density="compact"
        hide-details
        style="flex: 1"
      ></v-slider>
      <v-text-field
        :model-value="numericTemp ?? modelValue"
        @update:model-value="val => (numericTemp = val)"
        @blur="() => { emitUpdate(toNumber(numericTemp)); numericTemp = null }"
        density="compact"
        variant="outlined"
        class="config-field"
        type="number"
        hide-details
        style="flex: 1"
      ></v-text-field>
    </div>

    <v-textarea
      v-else-if="itemMeta?.type === 'text'"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      variant="outlined"
      rows="3"
      class="config-field"
      hide-details
    ></v-textarea>

    <v-switch
      v-else-if="itemMeta?.type === 'bool'"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      color="primary"
      inset
      density="compact"
      hide-details
    ></v-switch>

    <FileConfigItem
      v-else-if="itemMeta?.type === 'file'"
      :model-value="modelValue"
      :item-meta="itemMeta"
      :plugin-name="pluginName"
      :config-key="configKey"
      @update:model-value="emitUpdate"
      class="config-field"
    />

    <ListConfigItem
      v-else-if="itemMeta?.type === 'list'"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      class="config-field"
    />

    <ObjectEditor
      v-else-if="itemMeta?.type === 'dict'"
      :model-value="modelValue"
      :item-meta="itemMeta"
      @update:model-value="emitUpdate"
      class="config-field"
    />

    <v-text-field
      v-else
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
    ></v-text-field>
  </div>
</template>

<script setup>
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import ListConfigItem from './ListConfigItem.vue'
import FileConfigItem from './FileConfigItem.vue'
import ObjectEditor from './ObjectEditor.vue'
import ProviderSelector from './ProviderSelector.vue'
import PersonaSelector from './PersonaSelector.vue'
import KnowledgeBaseSelector from './KnowledgeBaseSelector.vue'
import PluginSetSelector from './PluginSetSelector.vue'
import T2ITemplateEditor from './T2ITemplateEditor.vue'
import { ref } from 'vue'
import { useI18n, useModuleI18n } from '@/i18n/composables'

const numericTemp = ref(null)

const props = defineProps({
  modelValue: {
    type: [String, Number, Boolean, Array, Object],
    default: null
  },
  itemMeta: {
    type: Object,
    default: null
  },
  pluginName: {
    type: String,
    default: ''
  },
  configKey: {
    type: String,
    default: ''
  },
  loading: {
    type: Boolean,
    default: false
  },
  showFullscreenBtn: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'get-embedding-dim', 'open-fullscreen'])
const { t } = useI18n()
const { getRaw } = useModuleI18n('features/config-metadata')

function emitUpdate(val) {
  emit('update:modelValue', val)
}

function toNumber(val) {
  const n = parseFloat(val)
  return isNaN(n) ? 0 : n
}

function getLabel(itemMeta, index, option) {
  const labels = getTranslatedLabels(itemMeta)
  return labels ? labels[index] : option
}

function getTranslatedLabels(itemMeta) {
  if (!itemMeta?.labels) return null
  if (typeof itemMeta.labels === 'string') {
    const translatedLabels = getRaw(itemMeta.labels)
    if (Array.isArray(translatedLabels)) {
      return translatedLabels
    }
  }
  if (Array.isArray(itemMeta.labels)) {
    return itemMeta.labels
  }
  return null
}

function getSelectItems(itemMeta) {
  const labels = getTranslatedLabels(itemMeta)
  if (labels && itemMeta.options) {
    return itemMeta.options.map((value, index) => ({
      title: labels[index] || value,
      value: value
    }))
  }
  return itemMeta.options || []
}

function parseSpecialValue(value) {
  if (!value || typeof value !== 'string') {
    return { name: '', subtype: '' }
  }
  const [name, ...rest] = value.split(':')
  return {
    name,
    subtype: rest.join(':') || ''
  }
}

function getSpecialName(value) {
  return parseSpecialValue(value).name
}

function getSpecialSubtype(value) {
  return parseSpecialValue(value).subtype
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

:deep(.v-field__input) {
  font-size: 14px;
}

:deep(.config-field input[type='number']::-webkit-inner-spin-button),
:deep(.config-field input[type='number']::-webkit-outer-spin-button) {
  -webkit-appearance: none;
}

:deep(.config-field input[type='number']) {
  -moz-appearance: textfield;
}
</style>
