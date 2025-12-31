<template>
  <div class="d-flex align-center justify-space-between">
    <div>
      <span v-if="!modelValue || Object.keys(modelValue).length === 0" style="color: rgb(var(--v-theme-primaryText));">
        暂无项目
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
      {{ buttonText }}
    </v-btn>
  </div>

  <!-- Key-Value Management Dialog -->
  <v-dialog v-model="dialog" max-width="600px">
    <v-card>
      <v-card-title class="text-h3 py-4" style="font-weight: normal;">
        {{ dialogTitle }}
      </v-card-title>

      <v-card-text class="pa-4" style="max-height: 400px; overflow-y: auto;">
        <!-- Regular key-value pairs (non-template) -->
        <div v-if="nonTemplatePairs.length > 0">
          <div v-for="(pair, index) in nonTemplatePairs" :key="index" class="key-value-pair">
            <v-row no-gutters align="center" class="mb-2">
              <v-col cols="4">
                <v-text-field
                  v-model="pair.key"
                  density="compact"
                  variant="outlined"
                  hide-details
                  placeholder="键名"
                  @blur="updateKey(index, pair.key)"
                ></v-text-field>
              </v-col>
              <v-col cols="7" class="pl-2 d-flex align-center justify-end">
                <v-text-field
                  v-if="pair.type === 'string'"
                  v-model="pair.value"
                  density="compact"
                  variant="outlined"
                  hide-details
                  placeholder="字符串值"
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
                    placeholder="数值"
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
                  placeholder="JSON"
                  @blur="updateJSON(index, pair.value)"
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
          <div class="text-caption text-grey mb-2">预设</div>
          <div v-for="(template, templateKey) in templateSchema" :key="templateKey" class="template-field" :class="{ 'template-field-inactive': !isTemplateKeyAdded(templateKey) }">
            <v-row no-gutters align="center" class="mb-2">
              <v-col cols="4">
                <div class="d-flex flex-column">
                  <span class="text-caption font-weight-medium">{{ template.name || template.description || templateKey }}</span>
                  <span v-if="template.hint" class="text-caption text-grey" style="font-size: 0.7rem;">{{ template.hint }}</span>
                </div>
              </v-col>
              <v-col cols="7" class="pl-2 d-flex align-center justify-end">
                <v-text-field
                  v-if="template.type === 'string'"
                  :model-value="getTemplateValue(templateKey)"
                  @update:model-value="updateTemplateValue(templateKey, $event)"
                  density="compact"
                  variant="outlined"
                  hide-details
                  placeholder="字符串值"
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
                    class="flex-grow-1"
                  ></v-slider>
                  <v-text-field
                    :model-value="getTemplateValue(templateKey)"
                    @update:model-value="updateTemplateValue(templateKey, $event)"
                    type="number"
                    density="compact"
                    variant="outlined"
                    hide-details
                    placeholder="数值"
                    :style="template.slider ? 'max-width: 120px;' : ''"
                  ></v-text-field>
                </div>
                <v-switch
                  v-else-if="template.type === 'boolean' || template.type === 'bool'"
                  :model-value="getTemplateValue(templateKey)"
                  @update:model-value="updateTemplateValue(templateKey, $event)"
                  density="compact"
                  hide-details
                  color="primary"
                ></v-switch>
              </v-col>
              <v-col cols="1" class="pl-2">
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

        <div v-if="localKeyValuePairs.length === 0 && !hasTemplateSchema" class="text-center py-8">
          <v-icon size="64" color="grey-lighten-1">mdi-code-json</v-icon>
          <p class="text-grey mt-4">暂无参数</p>
        </div>
      </v-card-text>

      <!-- Add new key-value pair section -->
      <v-card-text class="pa-4">
        <div class="d-flex align-center ga-2">
          <v-text-field
            v-model="newKey"
            label="新键名"
            density="compact"
            variant="outlined"
            hide-details
            class="flex-grow-1"
          ></v-text-field>
          <v-select
            v-model="newValueType"
            :items="['string', 'number', 'boolean', 'json']"
            label="值类型"
            density="compact"
            variant="outlined"
            hide-details
            style="max-width: 120px;"
          ></v-select>
          <v-btn @click="addKeyValuePair" variant="tonal" color="primary">
            <v-icon>mdi-plus</v-icon>
            添加
          </v-btn>
        </div>
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelDialog">取消</v-btn>
        <v-btn color="primary" @click="confirmDialog">确认</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '@/i18n/composables'

const { t } = useI18n()

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
    default: '修改'
  },
  dialogTitle: {
    type: String,
    default: '修改键值对'
  },
  maxDisplayItems: {
    type: Number,
    default: 1
  }
})

const emit = defineEmits(['update:modelValue'])

const dialog = ref(false)
const localKeyValuePairs = ref([])
const originalKeyValuePairs = ref([])
const newKey = ref('')
const newValueType = ref('string')

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

function initializeLocalKeyValuePairs() {
  localKeyValuePairs.value = []
  for (const [key, value] of Object.entries(props.modelValue)) {
    let _type = (typeof value) === 'object' ? 'json':(typeof value)
    let _value = _type === 'json'?JSON.stringify(value):value
    
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
    
    localKeyValuePairs.value.push({
      key: key,
      value: _value,
      type: _type,
      slider: template?.slider,
      template: template
    })
  }
}

function openDialog() {
  initializeLocalKeyValuePairs()
  originalKeyValuePairs.value = JSON.parse(JSON.stringify(localKeyValuePairs.value)) // Deep copy
  newKey.value = ''
  newValueType.value = 'string'
  dialog.value = true
}

function addKeyValuePair() {
  const key = newKey.value.trim()
  if (key !== '') {
    const isKeyExists = localKeyValuePairs.value.some(pair => pair.key === key)
    if (isKeyExists) {
      alert('键名已存在')
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
        defaultValue = "{}"
        break
      default: // string
        defaultValue = ""
        break
    }

    localKeyValuePairs.value.push({
      key: key,
      value: defaultValue,
      type: newValueType.value
    })
    newKey.value = ''
  }
}

function updateJSON(index, newValue) {
  try {
    JSON.parse(newValue)
    localKeyValuePairs.value[index].jsonError = ''
  } catch (e) {
    localKeyValuePairs.value[index].jsonError = 'JSON 格式错误'
  }
}

function removeKeyValuePairByKey(key) {
  const index = localKeyValuePairs.value.findIndex(pair => pair.key === key)
  if (index >= 0) {
    localKeyValuePairs.value.splice(index, 1)
  }
}

function updateKey(index, newKey) {
  const originalKey = localKeyValuePairs.value[index].key
  // 如果键名没有改变，则不执行任何操作
  if (originalKey === newKey) return

  // 检查新键名是否已存在
  const isKeyExists = localKeyValuePairs.value.some((pair, i) => i !== index && pair.key === newKey)
  if (isKeyExists) {
    // 如果键名已存在，提示用户并恢复原值
    alert('键名已存在')
    // 将键名恢复为修改前的原始值
    localKeyValuePairs.value[index].key = originalKey
    return
  }

  // 检查新键名是否有模板
  const template = templateSchema.value[newKey]
  if (template) {
    // 更新类型和默认值
    localKeyValuePairs.value[index].type = template.type || localKeyValuePairs.value[index].type
    if (localKeyValuePairs.value[index].value === undefined || localKeyValuePairs.value[index].value === null || localKeyValuePairs.value[index].value === '') {
      localKeyValuePairs.value[index].value = template.default !== undefined ? template.default : localKeyValuePairs.value[index].value
    }
    localKeyValuePairs.value[index].slider = template.slider
    localKeyValuePairs.value[index].template = template
  } else {
    // 清除模板信息
    localKeyValuePairs.value[index].slider = undefined
    localKeyValuePairs.value[index].template = undefined
  }

  // 更新本地副本
  localKeyValuePairs.value[index].key = newKey
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
    let valueType = template?.type || 'string'
    localKeyValuePairs.value.push({
      key: templateKey,
      value: newValue,
      type: valueType,
      slider: template?.slider,
      template: template
    })
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
      return "{}"
    case 'string':
    default:
      return ""
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
        // 注意：在 JavaScript 中，只有严格的 false, 0, "", null, undefined, NaN 会被转换为 false
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
  localKeyValuePairs.value = JSON.parse(JSON.stringify(originalKeyValuePairs.value))
  dialog.value = false
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