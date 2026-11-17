<template>
  <div class="w-100" :class="{ 'config-field--full-width': itemMeta?.full_width }">
    <!-- Special handling for specific metadata types -->
    <template v-if="itemMeta?._special === 'umo'">
      <UmoSelector
        :model-value="modelValue"
        :multiple="itemMeta?.type === 'list'"
        :readonly="Boolean(itemMeta?.readonly)"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'sender_id'">
      <SenderSelector
        :model-value="modelValue"
        :readonly="Boolean(itemMeta?.readonly)"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'select_provider'">
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
    <template v-else-if="itemMeta?._special === 'provider_pool'">
      <ProviderSelector :model-value="modelValue" @update:model-value="emitUpdate" :provider-type="'chat_completion'"
        :button-text="t('core.shared.providerSelector.selectProviderPool')" />
    </template>
    <template v-else-if="itemMeta?._special === 'select_agent_configs'">
      <AgentConfigSelector :model-value="modelValue || []" @update:model-value="emitUpdate" />
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
      <PluginSetSelector :model-value="modelValue" :selection-only="itemMeta?.selection_only" @update:model-value="emitUpdate" />
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
        :model-value="modelValue"
        @update:model-value="emitUpdate"
      />
    </template>
    <template v-else-if="itemMeta?._special === 'get_embedding_dim'">
      <div class="d-flex align-center gap-2">
        <ConfigNumberInput
          :model-value="modelValue"
          @update:model-value="emitUpdate"
          integer
          required
        />
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

    <v-autocomplete
      v-else-if="itemMeta?.type === 'list' && itemMeta?.options"
      :model-value="modelValue"
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
    ></v-autocomplete>

    <v-select
      v-else-if="itemMeta?.options"
      :model-value="modelValue"
      @update:model-value="emitUpdate"
      :items="getSelectItems(itemMeta)"
      :disabled="itemMeta?.readonly"
      :clearable="itemMeta?.omit_when_empty"
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
      :type="stringInputType"
      :append-inner-icon="secretToggleIcon"
      :autocomplete="itemMeta?.secret ? 'new-password' : undefined"
      @click:append-inner="secretVisible = !secretVisible"
      density="compact"
      variant="outlined"
      class="config-field"
      hide-details
    ></v-text-field>

    <ConfigNumberInput
      v-else-if="['int', 'float', 'number'].includes(itemMeta?.type)"
      :model-value="modelValue"
      :slider="itemMeta?.slider"
      :min="itemMeta?.min"
      :max="itemMeta?.max"
      :integer="itemMeta?.integer"
      :required="numericRequired"
      :placeholder="itemMeta?.placeholder ?? (itemMeta?.omit_when_empty ? t('core.common.objectEditor.omitWhenEmpty') : undefined)"
      @update:model-value="emitUpdate"
    />

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
      :secret="Boolean(itemMeta?.secret)"
      class="config-field"
    />

    <ObjectEditor
      v-else-if="itemMeta?.type === 'dict'"
      :inline="itemMeta?.render_type === 'inline'"
      :model-value="modelValue"
      :item-meta="itemMeta"
      :plugin-name="pluginName"
      :plugin-i18n="pluginI18n"
      :config-key="configKey"
      @update:model-value="emitUpdate"
      class="config-field"
    >
      <template #after-template="slotProps">
        <slot name="after-template" v-bind="slotProps" />
      </template>
    </ObjectEditor>

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
    ></v-text-field>
  </div>
</template>

<script setup>
import { LazyMonacoEditor as VueMonacoEditor } from '@/components/shared/LazyMonacoEditor';
import ListConfigItem from './ListConfigItem.vue'
import SenderSelector from './SenderSelector.vue'
import UmoSelector from './UmoSelector.vue'
import FileConfigItem from './FileConfigItem.vue'
import ObjectEditor from './ObjectEditor.vue'
import ProviderSelector from './ProviderSelector.vue'
import PersonaSelector from './PersonaSelector.vue'
import AgentConfigSelector from './AgentConfigSelector.vue'
import KnowledgeBaseSelector from './KnowledgeBaseSelector.vue'
import PluginSetSelector from './PluginSetSelector.vue'
import T2ITemplateEditor from './T2ITemplateEditor.vue'
import DashboardTotpManager from './DashboardTotpManager.vue'
import LocalPermissionMatrix from './LocalPermissionMatrix.vue'
import { computed, ref, watch } from 'vue'
import ConfigNumberInput from './ConfigNumberInput.vue'
import { useI18n, useModuleI18n } from '@/i18n/composables'
import { usePluginI18n } from '@/utils/pluginI18n'

const listSearchText = ref('')
const secretVisible = ref(false)

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
  pluginI18n: {
    type: Object,
    default: () => ({})
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
  },
  configRoot: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:modelValue', 'get-embedding-dim', 'open-fullscreen'])
const { t } = useI18n()
const { getRaw } = useModuleI18n('features/config-metadata')
const { configText } = usePluginI18n()
const numericRequired = computed(() => !props.itemMeta?.omit_when_empty && props.itemMeta?.required !== false)

watch(
  () => props.itemMeta?.omit_when_empty && props.modelValue === '',
  (empty) => { if (empty) emit('update:modelValue', undefined) },
  { immediate: true }
)

async function emitUpdate(val) {
  const type = props.itemMeta?.type
  if (props.itemMeta?.omit_when_empty && (val === '' || val == null)) {
    val = undefined
  } else if (['int', 'float', 'number'].includes(type) && (val === '' || val == null)) {
    // Keep an empty required field in the input draft, even if the form hides it later.
    if (numericRequired.value) return
    val = ''
  } else {
    val = validateNumericConfig(type, val)
  }
  if (
    props.itemMeta?._special === 'agent_runtime'
    && props.configRoot?.agent
    && props.itemMeta?.runtime_defaults?.[val]
  ) {
    props.configRoot.agent.config = JSON.parse(
      JSON.stringify(props.itemMeta.runtime_defaults[val])
    )
  }
  emit('update:modelValue', val)
}

const listSelectItems = computed(() =>
  props.itemMeta?.type === 'list' && props.itemMeta?.options
    ? getSelectItems(props.itemMeta)
    : []
)

const stringInputType = computed(() =>
  props.itemMeta?.secret && !secretVisible.value ? 'password' : 'text'
)
const secretToggleIcon = computed(() => {
  if (!props.itemMeta?.secret) return undefined
  return secretVisible.value ? 'mdi-eye-off-outline' : 'mdi-eye-outline'
})

function validateNumericConfig(modelType, rawValue) {
  if (modelType === 'int' || modelType === 'float') {
    // 如果有滑动条定义，应用边界限制
    const slider = props.itemMeta?.slider
    if (slider) {
      const min = slider.min ?? 0
      const max = slider.max ?? 100
      return Math.max(min, Math.min(max, rawValue))
    } else {
      return rawValue
    }
  } else if (modelType === 'dict') {
    Object.entries(rawValue).forEach(([key, value]) => {
      const templatesSchema = props.itemMeta?.template_schema
      const templateType = templatesSchema?.[key]?.type
      const templateSlider = templatesSchema?.[key]?.slider
      if ((templateType === 'int' || templateType === 'float') && templateSlider) {
        const min = templateSlider.min ?? 0
        const max = templateSlider.max ?? 100
        rawValue[key] = Math.max(min, Math.min(max, value))
      }
    })
    return rawValue
  } else {
    return rawValue
  }
}

function getLabel(itemMeta, index, option) {
  const labels = getTranslatedLabels(itemMeta)
  return labels ? labels[index] : option
}

function getTranslatedLabels(itemMeta) {
  if (
    props.pluginName
    && props.configKey
    && props.pluginI18n
    && Object.keys(props.pluginI18n).length > 0
  ) {
    const translatedLabels = configText(props.pluginI18n, props.configKey, 'labels', null)
    if (Array.isArray(translatedLabels)) {
      return translatedLabels
    }
  }
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
  let subtitles = itemMeta?.subtitles
  if (
    props.pluginName
    && props.configKey
    && props.pluginI18n
    && Object.keys(props.pluginI18n).length > 0
  ) {
    const translatedSubtitles = configText(props.pluginI18n, props.configKey, 'subtitles', null)
    if (Array.isArray(translatedSubtitles)) {
      subtitles = translatedSubtitles
    }
  }
  if (typeof subtitles === 'string') {
    subtitles = getRaw(subtitles)
  }
  if (!Array.isArray(subtitles)) subtitles = null

  if ((labels || subtitles) && itemMeta.options) {
    return itemMeta.options.map((value, index) => ({
      title: labels?.[index] || value,
      value: value,
      props: {
        subtitle: typeof subtitles?.[index] === 'string' ? subtitles[index] : undefined
      }
    }))
  }
  return itemMeta.options || []
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
  appearance: textfield;
}
</style>
