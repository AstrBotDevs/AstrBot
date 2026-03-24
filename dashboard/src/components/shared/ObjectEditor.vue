<template>
  <div class="d-flex align-center justify-space-between">
    <div>
      <span
        v-if="!modelValue || Object.keys(modelValue).length === 0"
        style="color: rgb(var(--v-theme-primaryText));"
      >
        {{ t('core.common.objectEditor.noItems') }}
      </span>
      <div
        v-else
        class="d-flex flex-wrap ga-2"
      >
        <v-chip
          v-for="key in displayKeys"
          :key="key"
          size="x-small"
          label
          color="primary"
        >
          {{ key.length > 20 ? key.slice(0, 20) + '...' : key }}
        </v-chip>
        <v-chip
          v-if="Object.keys(modelValue).length > maxDisplayItems"
          size="x-small"
          label
          color="grey-lighten-1"
        >
          +{{ Object.keys(modelValue).length - maxDisplayItems }}
        </v-chip>
      </div>
    </div>
    <v-btn
      size="small"
      color="primary"
      variant="tonal"
      @click="openDialog"
    >
      {{ resolveButtonText }}
    </v-btn>
  </div>

  <!-- Key-Value Management Dialog -->
  <v-dialog
    v-model="dialog"
    max-width="600px"
  >
    <v-card>
      <v-card-title
        class="text-h3 py-4"
        style="font-weight: normal;"
      >
        {{ resolveDialogTitle }}
      </v-card-title>

      <v-card-text
        class="pa-4"
        style="max-height: 400px; overflow-y: auto;"
      >
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
              <v-col
                cols="7"
                class="pl-2 d-flex align-center justify-end"
              >
                <v-text-field
                  v-if="pair.type === 'string'"
                  v-model="pair.value"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :placeholder="t('core.common.objectEditor.placeholders.stringValue')"
                />
                <div
                  v-else-if="pair.type === 'number' || pair.type === 'float' || pair.type === 'int'"
                  class="d-flex align-center gap-2 flex-grow-1"
                >
                  <v-slider
                    v-if="pair.slider"
                    :model-value="Number(pair.value) || 0"
                    :min="pair.slider.min"
                    :max="pair.slider.max"
                    :step="pair.slider.step"
                    color="primary"
                    density="compact"
                    hide-details
                    class="flex-grow-1"
                    @update:model-value="pair.value = $event"
                  />
                  <v-text-field
                    v-model.number="pair.value"
                    type="number"
                    density="compact"
                    variant="outlined"
                    hide-details
                    :placeholder="t('core.common.objectEditor.placeholders.numberValue')"
                    :style="pair.slider ? 'max-width: 120px;' : ''"
                  />
                </div>
                <v-switch
                  v-else-if="pair.type === 'boolean'"
                  v-model="pair.value"
                  density="compact"
                  hide-details
                  color="primary"
                />
                <v-text-field
                  v-if="pair.type === 'json'"
                  v-model="pair.value"
                  density="compact"
                  variant="outlined"
                  hide-details="auto"
                  :placeholder="t('core.common.objectEditor.placeholders.jsonValue')"
                  @blur="validateJSON(pair)"
                  :error-messages="pair.jsonError"
                />
              </v-col>
              <v-col
                cols="1"
                class="pl-2"
              >
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
        <div
          v-if="hasTemplateSchema"
          class="mt-4"
        >
          <v-divider class="mb-3" />
          <div class="text-caption text-grey mb-2">
            {{ t('core.common.objectEditor.presets') }}
          </div>
          <div
            v-for="(template, templateKey) in templateSchema"
            :key="templateKey"
            class="template-field"
            :class="{ 'template-field-inactive': !isTemplateKeyAdded(templateKey) }"
          >
            <v-row
              no-gutters
              align="center"
              class="mb-2"
            >
              <v-col cols="4">
                <div class="d-flex flex-column">
                  <span class="text-caption font-weight-medium">{{ getTemplateTitle(template, templateKey) }}</span>
                  <span
                    v-if="template.hint"
                    class="text-caption text-grey"
                    style="font-size: 0.7rem;"
                  >{{ translateIfKey(template.hint) }}</span>
                </div>
              </v-col>
              <v-col
                cols="7"
                class="pl-2 d-flex align-center justify-end"
              >
                <v-text-field
                  v-if="template.type === 'string'"
                  :model-value="getTemplateValue(templateKey)"
                  density="compact"
                  variant="outlined"
                  hide-details
                  :placeholder="t('core.common.objectEditor.placeholders.stringValue')"
                  @update:model-value="updateTemplateValue(templateKey, $event)"
                />
                <div
                  v-else-if="template.type === 'number' || template.type === 'float' || template.type === 'int'"
                  class="d-flex align-center ga-4 flex-grow-1"
                >
                  <v-slider
                    v-if="template.slider"
                    :model-value="Number(getTemplateValue(templateKey)) || 0"
                    :min="template.slider.min"
                    :max="template.slider.max"
                    :step="template.slider.step"
                    color="primary"
                    density="compact"
                    hide-details
                    class="flex-grow-1"
                    @update:model-value="updateTemplateValue(templateKey, $event)"
                  />
                  <v-text-field
                    :model-value="getTemplateValue(templateKey)"
                    type="number"
                    density="compact"
                    variant="outlined"
                    hide-details
                    :placeholder="t('core.common.objectEditor.placeholders.numberValue')"
                    :style="template.slider ? 'max-width: 120px;' : ''"
                    @update:model-value="updateTemplateValue(templateKey, $event)"
                  />
                </div>
                <v-switch
                  v-else-if="template.type === 'boolean' || template.type === 'bool'"
                  :model-value="getTemplateValue(templateKey)"
                  density="compact"
                  hide-details
                  color="primary"
                  @update:model-value="updateTemplateValue(templateKey, $event)"
                />
              </v-col>
              <v-col
                cols="1"
                class="pl-2"
              >
                <v-btn
                  v-if="isTemplateKeyAdded(templateKey)"
                  icon
                  variant="text"
                  size="small"
                  color="error"
                  @click="removeTemplateKey(templateKey)"
                >
                  <v-icon>mdi-close</v-icon>
                </v-btn>
              </v-col>
            </v-row>
          </div>
        </div>

        <div
          v-if="localKeyValuePairs.length === 0 && !hasTemplateSchema"
          class="text-center py-8"
        >
          <v-icon
            size="64"
            color="grey-lighten-1"
          >
            mdi-code-json
          </v-icon>
          <p class="text-grey mt-4">
            {{ t('core.common.objectEditor.noParams') }}
          </p>
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
          />
          <v-select
            v-model="newValueType"
            :items="['string', 'number', 'boolean', 'json']"
            :label="t('core.common.objectEditor.valueTypeLabel')"
            density="compact"
            variant="outlined"
            hide-details
            style="max-width: 120px;"
          />
          <v-btn
            variant="tonal"
            color="primary"
            @click="addKeyValuePair"
          >
            <v-icon>mdi-plus</v-icon>
            {{ t('core.common.add') }}
          </v-btn>
        </div>
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn
          variant="text"
          @click="cancelDialog"
        >
          {{ t('core.common.cancel') }}
        </v-btn>
        <v-btn
          color="primary"
          @click="confirmDialog"
        >
          {{ t('core.common.confirm') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n, useModuleI18n } from '@/i18n/composables'
import { useToast } from '@/utils/toast'

const { t } = useI18n()
const { tm, getRaw } = useModuleI18n('features/config-metadata')
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
  for (const [key, value] of Object.entries(props.modelValue)) {
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
  emit('update:modelValue', updatedValue)
  dialog.value = false
}

function cancelDialog() {
  // Reset to original state
  localKeyValuePairs.value = originalKeyValuePairs.value.map(pair => ({ ...pair }))
  dialog.value = false
}

function translateIfKey(value) {
  if (!value || typeof value !== 'string') return value
  return getRaw(value) ? tm(value) : value
}

function getTemplateTitle(template, templateKey) {
  return translateIfKey(template?.name || template?.description || templateKey)
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
</style>

