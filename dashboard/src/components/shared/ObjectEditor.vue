<template>
  <div v-if="!inline" v-bind="$attrs" class="d-flex align-center justify-space-between">
    <div>
      <span v-if="!modelValue || Object.keys(modelValue).length === 0" style="color: rgb(var(--v-theme-primaryText));">
        {{ t('core.common.objectEditor.noItems') }}
      </span>
      <div v-else class="d-flex flex-wrap ga-2">
        <v-chip v-for="key in displayKeys" :key="key" size="x-small" label color="primary">
          {{ key.length > 20 ? key.slice(0, 20) + '...' : key }}
        </v-chip>
        <v-chip v-if="Object.keys(modelValue).length > maxDisplayItems" size="x-small" label color="grey-lighten-1">
          +{{ Object.keys(modelValue).length - maxDisplayItems }}
        </v-chip>
      </div>
    </div>
    <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
      {{ resolveButtonText }}
    </v-btn>
  </div>

  <!-- Key-Value Management Dialog -->
  <component :is="inline ? 'div' : VDialog" v-bind="inline ? $attrs : {}" :class="{ 'object-editor-inline': inline }" v-model="dialog" :max-width="inline ? undefined : '600px'">
    <component :is="inline ? 'div' : VCard">
      <v-card-title v-if="!inline" class="text-h3 pa-4 pb-0 pl-6">
        {{ resolveDialogTitle }}
      </v-card-title>

      <v-card-text :class="inline ? 'pa-0' : 'pa-4'" :style="inline ? undefined : 'max-height: 400px; overflow-y: auto;'">
        <!-- Template schema fields -->
        <div v-if="hasTemplateSchema" :class="{ 'mt-4': !inline }">
          <v-divider v-if="!inline" class="mb-3"></v-divider>
          <div v-if="!inline" class="text-caption text-grey mb-2">{{ t('core.common.objectEditor.presets') }}</div>
          <div v-for="(template, templateKey) in templateSchema" :key="templateKey" class="template-field" :class="{ 'template-field-inactive': !inline && !isTemplateKeyAdded(templateKey) }">
            <ConfigFieldRow :compact="!inline" :label-columns="inline ? 6 : 4">
              <template #title>{{ getTemplateTitle(template, templateKey) }}</template>
              <template v-if="template.hint" #hint>{{ resolveTemplateText(templateKey, 'hint', template.hint) }}</template>
              <div class="object-editor-value-group">
                <div class="object-editor-value">
                  <ReasoningEffortInput
                    v-if="template.render_type === 'reasoning_effort'"
                    :model-value="getTemplateValue(templateKey)"
                    @update:model-value="updateTemplateValue(templateKey, $event)"
                  />
                  <v-select
                    v-else-if="template.options"
                    :model-value="isTemplateKeyAdded(templateKey) ? getTemplateValue(templateKey) : template.default ?? null"
                    :items="template.options"
                    :aria-label="getTemplateTitle(template, templateKey)"
                    @update:model-value="updateTemplateValue(templateKey, $event)"
                    density="compact"
                    variant="outlined"
                    hide-details
                    clearable
                  ></v-select>
                  <v-text-field
                    v-else-if="template.type === 'string'"
                    :model-value="getTemplateValue(templateKey)"
                    @update:model-value="updateTemplateValue(templateKey, $event)"
                    density="compact"
                    variant="outlined"
                    hide-details
                    :aria-label="getTemplateTitle(template, templateKey)"
                    :clearable="inline"
                    :placeholder="inline ? t('core.common.objectEditor.omitWhenEmpty') : t('core.common.objectEditor.placeholders.stringValue')"
                  ></v-text-field>
                  <ConfigNumberInput
                    v-else-if="['number', 'float', 'int'].includes(template.type)"
                    :model-value="getTemplateValue(templateKey)"
                    @update:model-value="updateTemplateValue(templateKey, $event)"
                    :slider="template.slider"
                    :min="template.min"
                    :max="template.max"
                    :integer="template.integer"
                    :aria-label="getTemplateTitle(template, templateKey)"
                    :placeholder="inline ? t('core.common.objectEditor.omitWhenEmpty') : t('core.common.objectEditor.placeholders.numberValue')"
                  />
                  <v-switch
                    v-else-if="template.type === 'boolean' || template.type === 'bool'"
                    :model-value="getTemplateValue(templateKey)"
                    @update:model-value="updateTemplateValue(templateKey, $event)"
                    density="compact"
                    hide-details
                    color="primary"
                  ></v-switch>
                </div>
                <template v-if="!inline">
                  <v-btn
                    v-if="isTemplateKeyAdded(templateKey)"
                    icon
                    variant="text"
                    size="small"
                    color="error"
                    @click="removeKeyValuePairByKey(templateKey)"
                  >
                    <v-icon>mdi-close</v-icon>
                  </v-btn>
                </template>
              </div>
            </ConfigFieldRow>
            <ConfigFieldDivider v-if="inline" />
            <slot v-if="inline" name="after-template" :template-key="templateKey" />
          </div>
        </div>

        <!-- Regular key-value pairs (non-template) -->
        <div v-if="nonTemplatePairs.length > 0">
          <div v-for="pair in nonTemplatePairs" :key="pair._id" class="key-value-pair">
            <ConfigFieldRow :compact="!inline" :label-columns="inline ? 6 : 4">
              <template #label>
                <v-text-field
                  v-model="pair.key"
                  :class="{ 'config-field--full-width': inline }"
                  density="compact"
                  variant="outlined"
                  hide-details="auto"
                  :rules="[value => !localKeyValuePairs.some(other => other !== pair && other.key === value) || t('core.common.objectEditor.keyExists')]"
                  :placeholder="t('core.common.objectEditor.placeholders.keyName')"
                  @focus="pair._originalKey = pair.key"
                  @blur="onKeyBlur(pair)"
                ></v-text-field>
              </template>
              <template #default>
                <div class="object-editor-value-group">
                  <div class="object-editor-value" :class="{ 'object-editor-value--boolean': pair.type === 'boolean' }">
                    <v-text-field
                      v-if="pair.type === 'string'"
                      v-model="pair.value"
                      density="compact"
                      variant="outlined"
                      hide-details
                      :placeholder="t('core.common.objectEditor.placeholders.stringValue')"
                    ></v-text-field>
                    <ConfigNumberInput
                      v-else-if="['number', 'float', 'int'].includes(pair.type)"
                      v-model="pair.value"
                      :slider="pair.slider"
                      :placeholder="t('core.common.objectEditor.placeholders.numberValue')"
                      required
                    />
                    <div v-else-if="pair.type === 'boolean'" class="object-editor-boolean">
                      <span v-if="inline" class="text-body-1">False</span>
                      <v-switch
                        v-model="pair.value"
                        density="compact"
                        hide-details
                        color="primary"
                        :inset="inline"
                      ></v-switch>
                      <span v-if="inline" class="text-body-1">True</span>
                    </div>
                    <v-text-field
                      v-if="pair.type === 'json'"
                      v-model="pair.value"
                      density="compact"
                      variant="outlined"
                      hide-details="auto"
                      :placeholder="t('core.common.objectEditor.placeholders.jsonValue')"
                      @blur="validateJSON(pair)"
                      :rules="[() => { validateJSON(pair); return pair.jsonError || true }]"
                      :error-messages="pair.jsonError"
                    ></v-text-field>
                  </div>
                  <v-btn
                    icon
                    variant="text"
                    size="small"
                    color="error"
                    :aria-label="t('core.common.delete')"
                    @click="removeKeyValuePairByKey(pair.key)"
                  >
                    <v-icon>mdi-delete</v-icon>
                  </v-btn>
                </div>
              </template>
            </ConfigFieldRow>
            <ConfigFieldDivider v-if="inline" />
          </div>
        </div>

        <div v-if="localKeyValuePairs.length === 0 && !hasTemplateSchema" class="text-center py-8">
          <v-icon size="64" color="grey-lighten-1">mdi-code-json</v-icon>
          <p class="text-grey mt-4">{{ t('core.common.objectEditor.noParams') }}</p>
        </div>
      </v-card-text>

      <!-- Add new key-value pair section -->
      <v-card-text :class="inline ? 'pa-0' : 'pa-4'">
        <ConfigFieldRow :compact="!inline" :label-columns="inline ? 6 : 4">
          <template #label>
            <v-text-field
              v-model="newKey"
              :class="{ 'config-field--full-width': inline }"
              :label="inline ? undefined : t('core.common.objectEditor.newKeyLabel')"
              :placeholder="inline ? t('core.common.objectEditor.customBodyKeyPlaceholder') : undefined"
              :aria-label="inline ? t('core.common.objectEditor.customBodyKeyPlaceholder') : t('core.common.objectEditor.newKeyLabel')"
              density="compact"
              variant="outlined"
              hide-details
            />
          </template>
              <template #default>
            <div class="object-editor-value-group">
              <div class="object-editor-value">
                <v-select
                  v-model="newValueType"
                  :items="['string', 'number', 'boolean', { title: 'raw', value: 'json' }]"
                  :label="t('core.common.objectEditor.valueTypeLabel')"
                  density="compact"
                  variant="outlined"
                  hide-details
                />
              </div>
              <v-btn @click="addKeyValuePair" :icon="inline" :size="inline ? 'small' : 'default'" variant="tonal" color="primary" :aria-label="t('core.common.add')">
                <v-icon>mdi-plus</v-icon>
                <span v-if="!inline">{{ t('core.common.add') }}</span>
              </v-btn>
            </div>
          </template>
        </ConfigFieldRow>
      </v-card-text>

      <v-card-actions v-if="!inline" class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelDialog">{{ t('core.common.cancel') }}</v-btn>
        <v-btn color="primary" variant="tonal" @click="confirmDialog">{{ t('core.common.confirm') }}</v-btn>
      </v-card-actions>
    </component>
  </component>
</template>

<script setup>
import { ref, computed, watch, toRaw } from 'vue'
import { VCard, VDialog } from 'vuetify/components'
import ConfigNumberInput from './ConfigNumberInput.vue'
import ConfigFieldRow from './ConfigFieldRow.vue'
import ConfigFieldDivider from './ConfigFieldDivider.vue'
import { useI18n } from '@/i18n/composables'
import { useToast } from '@/utils/toast'
import { useConfigTextResolver } from '@/composables/useConfigTextResolver'
import ReasoningEffortInput from '../provider/ReasoningEffortInput.vue'

const { t } = useI18n()
const { warning: toastWarning } = useToast()

defineOptions({ inheritAttrs: false })

const props = defineProps({
  inline: {
    type: Boolean,
    default: false
  },
  modelValue: {
    type: Object,
    required: true
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
  buttonText: {
    type: String,
    default: ''
  },
  dialogTitle: {
    type: String,
    default: ''
  },
  maxDisplayItems: {
    type: Number,
    default: 1
  }
})

const { translateIfKey, resolveConfigText } = useConfigTextResolver(props)

const emit = defineEmits(['update:modelValue'])

const resolveButtonText = computed(() => props.buttonText || t('core.common.list.modifyButton'))
const resolveDialogTitle = computed(() => props.dialogTitle || t('core.common.objectEditor.dialogTitle'))

const dialog = ref(false)
const localKeyValuePairs = ref([])
const originalKeyValuePairs = ref([])
const newKey = ref('')
const newValueType = ref('string')
const nextPairId = ref(0)

// Template schema support
const templateSchema = computed(() => {
  return props.itemMeta?.template_schema || {}
})

const hasTemplateSchema = computed(() => {
  return Object.keys(templateSchema.value).length > 0
})

// 计算要显示的键名
const displayKeys = computed(() => {
  return Object.keys(props.modelValue).slice(0, props.maxDisplayItems)
})

// Keep custom rows visible until a key rename has been validated on blur.
const nonTemplatePairs = computed(() => {
  return localKeyValuePairs.value.filter(pair => !pair.template)
})

// Keep inline drafts in sync without rebuilding fields on our own emitted updates.
let lastEmittedValue
watch(() => props.modelValue, (newValue) => {
  if (props.inline && toRaw(newValue) !== lastEmittedValue) {
    initializeLocalKeyValuePairs()
    newKey.value = ''
    newValueType.value = 'string'
  }
}, { immediate: true })

watch(localKeyValuePairs, () => {
  if (props.inline) confirmDialog()
}, { deep: true })

function createPair({ key, value, type, slider, template, jsonError = '', _originalKey }) {
  return {
    _id: nextPairId.value++,
    key,
    value,
    type,
    slider,
    template,
    jsonError,
    _originalKey
  }
}

function initializeLocalKeyValuePairs() {
  localKeyValuePairs.value = []
  nextPairId.value = 0
  for (const [key, value] of Object.entries(props.modelValue || {})) {
    let _type = (typeof value) === 'object' ? 'json':(typeof value)
    let _value = _type === 'json' ? JSON.stringify(value) : value

    // Check if this key has a template schema
    const template = templateSchema.value[key]
    if (template) {
      // Use template type if available
      _type = template.type || _type
      // Use template default if value is missing
      if (_value === undefined || _value === null) {
        _value = template.default !== undefined ? template.default : _value
      }
    }

    localKeyValuePairs.value.push(createPair({
      key,
      value: _value,
      type: _type,
      slider: template?.slider,
      template
    }))
  }
}

function openDialog() {
  initializeLocalKeyValuePairs()
  originalKeyValuePairs.value = localKeyValuePairs.value.map(pair => ({ ...pair }))
  newKey.value = ''
  newValueType.value = 'string'
  dialog.value = true
}

function addKeyValuePair() {
  const key = newKey.value.trim()
  if (key !== '') {
    const isKeyExists = localKeyValuePairs.value.some(pair => pair.key === key)
    if (isKeyExists) {
      toastWarning(t('core.common.objectEditor.keyExists'))
      return
    }

    let defaultValue
    switch (newValueType.value) {
      case 'number':
        defaultValue = 1
        break
      case 'boolean':
        defaultValue = false
        break
      case 'json':
        defaultValue = '{}'
        break
      default: // string
        defaultValue = ''
        break
    }

    const template = templateSchema.value[key]
    if (template) {
      updateTemplateValue(key, template.default ?? defaultValue)
    } else {
      localKeyValuePairs.value.push(createPair({
        key,
        value: defaultValue,
        type: newValueType.value
      }))
    }
    newKey.value = ''
  }
}

function validateJSON(pair) {
  try {
    JSON.parse(pair.value)
    pair.jsonError = ''
  } catch (e) {
    pair.jsonError = t('core.common.objectEditor.invalidJson')
  }
}

function removeKeyValuePairByKey(key) {
  const index = localKeyValuePairs.value.findIndex(pair => pair.key === key)
  if (index >= 0) {
    localKeyValuePairs.value.splice(index, 1)
  }
}

function onKeyBlur(pair) {
  const originalKey = pair._originalKey
  const newKey = pair.key
  if (originalKey === undefined || originalKey === newKey) return

  const isKeyExists = localKeyValuePairs.value.some(p => p !== pair && p.key === newKey)
  if (isKeyExists) {
    toastWarning(t('core.common.objectEditor.keyExists'))
    pair.key = originalKey
    return
  }

  const template = templateSchema.value[newKey]
  if (template) {
    pair.type = template.type || pair.type
    if (pair.value === undefined || pair.value === null || pair.value === '') {
      if (template.default === undefined) {
        removeKeyValuePairByKey(newKey)
        return
      }
      pair.value = template.default
    }
    pair.slider = template.slider
    pair.template = template
  } else {
    pair.slider = undefined
    pair.template = undefined
  }
}

function isTemplateKeyAdded(templateKey) {
  return localKeyValuePairs.value.some(pair => pair.key === templateKey)
}

function getTemplateValue(templateKey) {
  const pair = localKeyValuePairs.value.find(pair => pair.key === templateKey)
  if (pair) {
    return pair.value
  }
  const template = templateSchema.value[templateKey]
  return template?.default ?? ''
}

function updateTemplateValue(templateKey, newValue) {
  if (newValue === '' || newValue === null || newValue === undefined) {
    removeKeyValuePairByKey(templateKey)
    return
  }
  const existingIndex = localKeyValuePairs.value.findIndex(pair => pair.key === templateKey)
  const template = templateSchema.value[templateKey]

  if (existingIndex >= 0) {
    // 更新现有值
    localKeyValuePairs.value[existingIndex].value = newValue
  } else {
    // 添加新字段
    const valueType = template?.type || 'string'
    localKeyValuePairs.value.push(createPair({
      key: templateKey,
      value: newValue,
      type: valueType,
      slider: template?.slider,
      template
    }))
  }
}

function confirmDialog() {
  const updatedValue = {}
  for (const pair of localKeyValuePairs.value) {
    if (Object.hasOwn(updatedValue, pair.key)) return
    if (['int', 'float', 'number'].includes(pair.type) && (pair.value === '' || pair.value == null)) return
    if (pair.type === 'json') {
      validateJSON(pair)
      if (pair.jsonError) return
    }
    let convertedValue = pair.value
    // 根据声明的类型进行转换
    switch (pair.type) {
      case 'int':
        convertedValue = parseInt(pair.value) || 0
        break
      case 'float':
      case 'number':
        // 尝试转换为数字，如果失败则保持原值（或设为默认值0）
        convertedValue = Number(pair.value)
        // 可选：检查是否为有效数字，无效则设为0或报错
        // if (isNaN(convertedValue)) convertedValue = 0;
        break
      case 'bool':
      case 'boolean':
        // 布尔值通常由 v-switch 正确处理，但为保险起见可以显式转换
        // 注意：在 JavaScript 中，只有严格的 false, 0, '', null, undefined, NaN 会被转换为 false
        // 这里直接赋值 pair.value 应该是安全的，因为 v-model 绑定的就是布尔值
        // convertedValue = Boolean(pair.value)
        break
      case 'json':
        convertedValue = JSON.parse(pair.value)
        break
      case 'string':
      default:
        // 默认转换为字符串
        convertedValue = String(pair.value)
        break
    }
    updatedValue[pair.key] = convertedValue
  }
  lastEmittedValue = updatedValue
  emit('update:modelValue', updatedValue)
  dialog.value = false
}

function cancelDialog() {
  // Reset to original state
  localKeyValuePairs.value = originalKeyValuePairs.value.map(pair => ({ ...pair }))
  dialog.value = false
}

function getTemplateTitle(template, templateKey) {
  return resolveTemplateText(templateKey, 'name', template?.name || template?.description || templateKey)
}

function resolveTemplateText(templateKey, attr, fallback) {
  if (!props.configKey) {
    return translateIfKey(fallback) || ''
  }
  return resolveConfigText(`${props.configKey}.template_schema.${templateKey}`, attr, fallback)
}
</script>

<style scoped>
.key-value-pair {
  width: 100%;
}

.template-field {
  transition: opacity 0.2s;
}

.template-field-inactive {
  opacity: 0.8;
}

.object-editor-value-group {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.object-editor-value {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  align-items: center;
}

.object-editor-boolean {
  display: flex;
  align-items: center;
  gap: 8px;
}

.object-editor-value-group > .v-btn {
  flex: 0 0 auto;
}

.object-editor-inline .config-field--full-width {
  width: 100%;
}

.object-editor-inline .object-editor-boolean {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  width: 100%;
}

.object-editor-inline .object-editor-boolean > span:last-child {
  text-align: right;
}

.object-editor-inline .object-editor-value--boolean :deep(.v-switch),
.object-editor-inline .object-editor-value--boolean :deep(.v-input__control) {
  margin-left: 0 !important;
}

</style>
