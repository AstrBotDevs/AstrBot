<template>
  <div class="d-flex align-center justify-space-between">
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
  <v-dialog v-model="dialog" max-width="600px">
    <v-card>
      <v-card-title class="text-h3 py-4" style="font-weight: normal;">
        {{ resolveDialogTitle }}
      </v-card-title>

      <v-card-text class="pa-4" style="max-height: 400px; overflow-y: auto;">
        <!-- Regular key-value pairs (non-template) -->
        <div v-if="nonTemplatePairs.length > 0">
          <div v-for="pair in nonTemplatePairs" :key="pair._id" class="key-value-pair">
            <v-row no-gutters align="center" class="mb-2">
              <v-col cols="4">
                <v-text-field
                  v-model="pair.key"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :placeholder="t('core.common.objectEditor.placeholders.keyName')"
                  @focus="pair._originalKey = pair.key"
                  @blur="onKeyBlur(pair)"
                ></v-text-field>
              </v-col>
              <v-col cols="7" class="pl-2 d-flex align-center justify-end">
                <v-text-field
                  v-if="pair.type === 'string'"
                  v-model="pair.value"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :placeholder="t('core.common.objectEditor.placeholders.stringValue')"
                ></v-text-field>
                <div v-else-if="pair.type === 'number' || pair.type === 'float' || pair.type === 'int'" class="d-flex align-center gap-2 flex-grow-1">
                  <v-slider
                    v-if="pair.slider"
                    :model-value="Number(pair.value) || 0"
                    @update:model-value="pair.value = $event"
                    :min="pair.slider.min"
                    :max="pair.slider.max"
                    :step="pair.slider.step"
                    color="primary"
                    density="compact"
                    hide-details
                    class="flex-grow-1"
                  ></v-slider>
                  <v-text-field
                    v-model.number="pair.value"
                    type="number"
                    density="compact"
                    variant="outlined"
                    hide-details
                    :placeholder="t('core.common.objectEditor.placeholders.numberValue')"
                    :style="pair.slider ? 'max-width: 120px;' : ''"
                  ></v-text-field>
                </div>
                <v-switch
                  v-else-if="pair.type === 'boolean'"
                  v-model="pair.value"
                  density="compact"
                  hide-details
                  color="primary"
                ></v-switch>
                <v-text-field
                  v-if="pair.type === 'json'"
                  v-model="pair.value"
                  density="compact"
                  variant="outlined"
                  hide-details="auto"
                  :placeholder="t('core.common.objectEditor.placeholders.jsonValue')"
                  @blur="validateJSON(pair)"
                  :error-messages="pair.jsonError"
                ></v-text-field>
              </v-col>
              <v-col cols="1" class="pl-2">
                <v-btn
                  icon
                  variant="text"
                  size="small"
                  color="error"
                  @click="removeKeyValuePairByKey(pair.key)"
                >
                  <v-icon>mdi-delete</v-icon>
                </v-btn>
              </v-col>
            </v-row>
          </div>
        </div>

        <!-- Template schema fields -->
        <div v-if="hasTemplateSchema" class="mt-4">
          <v-divider class="mb-3"></v-divider>
          <div class="text-caption text-grey mb-2">{{ t('core.common.objectEditor.presets') }}</div>
          <div v-for="(template, templateKey) in templateSchema" :key="templateKey" class="template-field" :class="{ 'template-field-disabled': isTemplateKeyDisabled(templateKey) }">
            <v-row no-gutters align="center" class="mb-2">
              <v-col cols="4">
                <div class="d-flex flex-column">
                  <span class="text-caption font-weight-medium">{{ getTemplateTitle(template, templateKey) }}</span>
                  <span v-if="template.hint" class="text-caption text-grey" style="font-size: 0.7rem;">{{ resolveTemplateText(templateKey, 'hint', template.hint) }}</span>
                </div>
              </v-col>
              <v-col cols="6" class="pl-2 d-flex align-center justify-end">
                <v-text-field
                  v-if="template.type === 'string'"
                  :model-value="getTemplateValue(templateKey)"
                  @update:model-value="updateTemplateValue(templateKey, $event)"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :disabled="isTemplateKeyDisabled(templateKey)"
                  :placeholder="t('core.common.objectEditor.placeholders.stringValue')"
                ></v-text-field>
                <div v-else-if="template.type === 'number' || template.type === 'float' || template.type === 'int'" class="d-flex align-center ga-4 flex-grow-1">
                  <v-slider
                    v-if="template.slider"
                    :model-value="Number(getTemplateValue(templateKey)) || 0"
                    @update:model-value="updateTemplateValue(templateKey, $event)"
                    :min="template.slider.min"
                    :max="template.slider.max"
                    :step="template.slider.step"
                    color="primary"
                    density="compact"
                    hide-details
                    :disabled="isTemplateKeyDisabled(templateKey)"
                    class="flex-grow-1"
                  ></v-slider>
                  <v-text-field
                    :model-value="getTemplateValue(templateKey)"
                    @update:model-value="updateTemplateValue(templateKey, $event)"
                    type="number"
                    density="compact"
                    variant="outlined"
                    hide-details
                    :disabled="isTemplateKeyDisabled(templateKey)"
                    :placeholder="t('core.common.objectEditor.placeholders.numberValue')"
                    :style="template.slider ? 'max-width: 120px;' : ''"
                  ></v-text-field>
                </div>
                <v-switch
                  v-else-if="template.type === 'boolean' || template.type === 'bool'"
                  :model-value="getTemplateValue(templateKey)"
                  @update:model-value="updateTemplateValue(templateKey, $event)"
                  density="compact"
                  hide-details
                  :disabled="isTemplateKeyDisabled(templateKey)"
                  color="primary"
                ></v-switch>
              </v-col>
              <v-col cols="2" class="pl-2 d-flex align-center justify-end">
                <v-tooltip :text="t('core.common.objectEditor.resetToDefault')" location="top">
                  <template v-slot:activator="{ props: tooltipProps }">
                    <v-btn
                      v-bind="tooltipProps"
                      icon
                      variant="text"
                      size="small"
                      :disabled="!isTemplateValueModified(templateKey)"
                      @click="resetTemplateKey(templateKey)"
                    >
                      <v-icon>mdi-restore</v-icon>
                    </v-btn>
                  </template>
                </v-tooltip>
                <v-tooltip :text="isTemplateKeyDisabled(templateKey) ? t('core.common.objectEditor.enableParam') : t('core.common.objectEditor.disableParam')" location="top">
                  <template v-slot:activator="{ props: tooltipProps }">
                    <v-checkbox
                      v-bind="tooltipProps"
                      :model-value="!isTemplateKeyDisabled(templateKey)"
                      @update:model-value="toggleTemplateKeyDisabled(templateKey)"
                      density="compact"
                      hide-details
                      color="success"
                      :disabled="nonDisableableKeys.includes(templateKey)"
                      class="ma-0 pa-0"
                    ></v-checkbox>
                  </template>
                </v-tooltip>
              </v-col>
            </v-row>
          </div>
        </div>

        <div v-if="localKeyValuePairs.length === 0 && !hasTemplateSchema" class="text-center py-8">
          <v-icon size="64" color="grey-lighten-1">mdi-code-json</v-icon>
          <p class="text-grey mt-4">{{ t('core.common.objectEditor.noParams') }}</p>
        </div>
      </v-card-text>

      <!-- Add new key-value pair section -->
      <v-card-text class="pa-4">
        <div class="d-flex align-center ga-2">
          <v-text-field
            v-model="newKey"
            :label="t('core.common.objectEditor.newKeyLabel')"
            density="compact"
            variant="outlined"
            hide-details
            class="flex-grow-1"
          ></v-text-field>
          <v-select
            v-model="newValueType"
            :items="['string', 'number', 'boolean', 'json']"
            :label="t('core.common.objectEditor.valueTypeLabel')"
            density="compact"
            variant="outlined"
            hide-details
            style="max-width: 120px;"
          ></v-select>
          <v-btn @click="addKeyValuePair" variant="tonal" color="primary">
            <v-icon>mdi-plus</v-icon>
            {{ t('core.common.add') }}
          </v-btn>
        </div>
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelDialog">{{ t('core.common.cancel') }}</v-btn>
        <v-btn color="primary" @click="confirmDialog">{{ t('core.common.confirm') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '@/i18n/composables'
import { useToast } from '@/utils/toast'
import { useConfigTextResolver } from '@/composables/useConfigTextResolver'

const { t } = useI18n()
const { warning: toastWarning } = useToast()

const props = defineProps({
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

// Disabled keys tracking
const localDisabledKeys = ref([])
const originalDisabledKeys = ref([])

// Template schema support
const templateSchema = computed(() => {
  return props.itemMeta?.template_schema || {}
})

const hasTemplateSchema = computed(() => {
  return Object.keys(templateSchema.value).length > 0
})

// Default disabled keys from metadata
const defaultDisabledKeys = computed(() => {
  return props.itemMeta?.default_disabled_keys || []
})

// Keys that cannot be disabled
const nonDisableableKeys = computed(() => {
  return props.itemMeta?.non_disableable_keys || []
})

// 计算要显示的键名 (exclude _disabled_keys from display)
const displayKeys = computed(() => {
  if (!props.modelValue) return []
  return Object.keys(props.modelValue).filter(k => k !== '_disabled_keys').slice(0, props.maxDisplayItems)
})

// 分离模板字段和普通字段
const nonTemplatePairs = computed(() => {
  return localKeyValuePairs.value.filter(pair => !templateSchema.value[pair.key])
})

// 监听 modelValue 变化，主要用于初始化
watch(() => props.modelValue, (newValue) => {
  // This watch is primarily for initialization or external changes
  // The dialog-based editing handles internal updates
}, { immediate: true })

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

  // Initialize disabled keys from modelValue or defaults
  const existingDisabled = props.modelValue?._disabled_keys
  if (Array.isArray(existingDisabled)) {
    localDisabledKeys.value = existingDisabled.filter(k => !nonDisableableKeys.value.includes(k))
  } else if (Object.keys(props.modelValue || {}).filter(k => k !== '_disabled_keys').length === 0 && defaultDisabledKeys.value.length > 0) {
    // New/empty config: use default disabled keys
    localDisabledKeys.value = defaultDisabledKeys.value.filter(k => !nonDisableableKeys.value.includes(k))
  } else {
    localDisabledKeys.value = []
  }
  originalDisabledKeys.value = [...localDisabledKeys.value]

  for (const [key, value] of Object.entries(props.modelValue || {})) {
    // Skip the internal _disabled_keys field
    if (key === '_disabled_keys') continue

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
        defaultValue = 0
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

    localKeyValuePairs.value.push(createPair({
      key,
      value: defaultValue,
      type: newValueType.value
    }))
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
      pair.value = template.default !== undefined ? template.default : pair.value
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

function isTemplateKeyDisabled(templateKey) {
  return localDisabledKeys.value.includes(templateKey)
}

function isTemplateValueModified(templateKey) {
  const template = templateSchema.value[templateKey]
  if (!template || template.default === undefined) return false
  const pair = localKeyValuePairs.value.find(p => p.key === templateKey)
  if (!pair) return false
  const type = template.type || 'string'
  if (type === 'number' || type === 'float' || type === 'int') {
    const pairNum = Number(pair.value)
    const defaultNum = Number(template.default)
    if (isNaN(pairNum) && isNaN(defaultNum)) return false
    return pairNum !== defaultNum
  }
  return String(pair.value) !== String(template.default)
}

function toggleTemplateKeyDisabled(templateKey) {
  const index = localDisabledKeys.value.indexOf(templateKey)
  if (index >= 0) {
    // Enable: remove from disabled list
    localDisabledKeys.value.splice(index, 1)
  } else {
    // Disable: add to disabled list
    localDisabledKeys.value.push(templateKey)
  }
}

function resetTemplateKey(templateKey) {
  const template = templateSchema.value[templateKey]
  if (template && template.default !== undefined) {
    updateTemplateValue(templateKey, template.default)
  }
}

function getTemplateValue(templateKey) {
  const pair = localKeyValuePairs.value.find(pair => pair.key === templateKey)
  if (pair) {
    return pair.value
  }
  const template = templateSchema.value[templateKey]
  return template?.default !== undefined ? template.default : getDefaultValueForType(template?.type || 'string')
}

function updateTemplateValue(templateKey, newValue) {
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

function removeTemplateKey(templateKey) {
  const index = localKeyValuePairs.value.findIndex(pair => pair.key === templateKey)
  if (index >= 0) {
    localKeyValuePairs.value.splice(index, 1)
  }
}

function getDefaultValueForType(type) {
  switch (type) {
    case 'int':
    case 'float':
    case 'number':
      return 0
    case 'bool':
    case 'boolean':
      return false
    case 'json':
      return '{}'
    case 'string':
    default:
      return ''
  }
}

function confirmDialog() {
  const updatedValue = {}
  for (const pair of localKeyValuePairs.value) {
    if (pair.type === 'json' && pair.jsonError) return
    let convertedValue = pair.value
    // 根据声明的类型进行转换
    switch (pair.type) {
      case 'int':
        convertedValue = parseInt(pair.value) || 0
        break
      case 'float':
      case 'number':
        convertedValue = Number(pair.value)
        break
      case 'bool':
      case 'boolean':
        break
      case 'json':
        convertedValue = JSON.parse(pair.value)
        break
      case 'string':
      default:
        convertedValue = String(pair.value)
        break
    }
    updatedValue[pair.key] = convertedValue
  }
  // Store disabled keys in the value if there are any
  if (localDisabledKeys.value.length > 0) {
    updatedValue['_disabled_keys'] = [...localDisabledKeys.value]
  }
  emit('update:modelValue', updatedValue)
  dialog.value = false
}

function cancelDialog() {
  // Reset to original state
  localKeyValuePairs.value = originalKeyValuePairs.value.map(pair => ({ ...pair }))
  localDisabledKeys.value = [...originalDisabledKeys.value]
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

.template-field-disabled {
  opacity: 0.5;
}
</style>
