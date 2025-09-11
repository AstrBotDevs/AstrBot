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
        <div v-if="localKeyValuePairs.length > 0">
          <div v-for="(pair, index) in localKeyValuePairs" :key="index" class="key-value-pair">
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
              <v-col cols="7" class="pl-2">
                <v-text-field
                  v-if="pair.type === 'string'"
                  v-model="pair.value"
                  density="compact"
                  variant="outlined"
                  hide-details
                  placeholder="字符串值"
                ></v-text-field>
                <v-text-field
                  v-else-if="pair.type === 'number'"
                  v-model.number="pair.value"
                  type="number"
                  density="compact"
                  variant="outlined"
                  hide-details
                  placeholder="数值"
                ></v-text-field>
                <v-switch
                  v-else-if="pair.type === 'boolean'"
                  v-model="pair.value"
                  density="compact"
                  hide-details
                  color="primary"
                ></v-switch>
              </v-col>
              <v-col cols="1" class="pl-2">
                <v-btn
                  icon
                  variant="text"
                  size="small"
                  color="error"
                  @click="removeKeyValuePair(index)"
                >
                  <v-icon>mdi-delete</v-icon>
                </v-btn>
              </v-col>
            </v-row>
          </div>
        </div>
        <div v-else class="text-center py-8">
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
            :items="['string', 'number', 'boolean']"
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

// 计算要显示的键名
const displayKeys = computed(() => {
  return Object.keys(props.modelValue).slice(0, props.maxDisplayItems)
})

// 监听 modelValue 变化，主要用于初始化
watch(() => props.modelValue, (newValue) => {
  // This watch is primarily for initialization or external changes
  // The dialog-based editing handles internal updates
}, { immediate: true })

function initializeLocalKeyValuePairs() {
  localKeyValuePairs.value = []
  for (const [key, value] of Object.entries(props.modelValue)) {
    localKeyValuePairs.value.push({
      key: key,
      value: value,
      type: typeof value // Store the original type
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
  if (newKey.value.trim() !== '') {
    let defaultValue
    switch (newValueType.value) {
      case 'number':
        defaultValue = 0
        break
      case 'boolean':
        defaultValue = false
        break
      default: // string
        defaultValue = ""
        break
    }

    localKeyValuePairs.value.push({
      key: newKey.value.trim(),
      value: defaultValue,
      type: newValueType.value
    })
    newKey.value = ''
  }
}

function removeKeyValuePair(index) {
  localKeyValuePairs.value.splice(index, 1)
}

function updateKey(index, newKey) {
  // 如果键名没有改变，则不执行任何操作
  if (localKeyValuePairs.value[index].key === newKey) return

  // 检查新键名是否已存在
  const isKeyExists = localKeyValuePairs.value.some((pair, i) => i !== index && pair.key === newKey)
  if (isKeyExists) {
    // 如果键名已存在，添加一个后缀使其唯一
    let uniqueKey = newKey
    let counter = 1
    while (localKeyValuePairs.value.some((pair, i) => i !== index && pair.key === uniqueKey)) {
      uniqueKey = `${newKey}_${counter}`
      counter++
    }
    newKey = uniqueKey
  }

  // 更新本地副本
  localKeyValuePairs.value[index].key = newKey
}

function confirmDialog() {
  const updatedValue = {}
  for (const pair of localKeyValuePairs.value) {
    updatedValue[pair.key] = pair.value
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
</style>