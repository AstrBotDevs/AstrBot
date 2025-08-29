<template>
  <div>
    <!-- 顶部操作区域 -->
    <div class="d-flex align-center justify-space-between mb-2">
      <div class="flex-grow-1">
        <span v-if="!modelValue || modelValue.length === 0" style="color: rgb(var(--v-theme-primaryText));">
          未启用任何插件
        </span>
        <span v-else-if="isAllPlugins" style="color: rgb(var(--v-theme-primaryText));">
          启用所有插件 (*)
        </span>
        <span v-else style="color: rgb(var(--v-theme-primaryText));">
          已选择 {{ modelValue.length }} 个插件
        </span>
      </div>
      <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
        {{ buttonText }}
      </v-btn>
    </div>
  </div>

  <!-- Plugin Set Selection Dialog -->
  <v-dialog v-model="dialog" max-width="700px">
    <v-card>
      <v-card-title class="text-h3 py-4" style="font-weight: normal;">
        选择插件集合
      </v-card-title>
      
      <v-card-text class="pa-4">
        <v-progress-linear v-if="loading" indeterminate color="primary"></v-progress-linear>
        
        <div v-if="!loading">
          <!-- 预设选项 -->
          <v-radio-group v-model="selectionMode" class="mb-4" hide-details>
            <v-radio 
              value="all" 
              label="启用所有插件" 
              color="primary"
            ></v-radio>
            <v-radio 
              value="none" 
              label="不启用任何插件" 
              color="primary"
            ></v-radio>
            <v-radio 
              value="custom" 
              label="自定义选择" 
              color="primary"
            ></v-radio>
          </v-radio-group>

          <!-- 自定义选择时显示插件列表 -->
          <div v-if="selectionMode === 'custom'" style="max-height: 300px; overflow-y: auto;">
            <v-list v-if="pluginList.length > 0" density="compact">
              <v-list-item
                v-for="plugin in pluginList"
                :key="plugin.name"
                rounded="md"
                class="ma-1">
                <template v-slot:prepend>
                  <v-checkbox
                    v-model="selectedPlugins"
                    :value="plugin.name"
                    color="primary"
                    hide-details
                  ></v-checkbox>
                </template>
                
                <v-list-item-title>{{ plugin.name }}</v-list-item-title>
                <v-list-item-subtitle>
                  {{ plugin.desc || '无描述' }}
                  <v-chip v-if="!plugin.activated" size="x-small" color="grey" class="ml-1">
                    未激活
                  </v-chip>
                </v-list-item-subtitle>
              </v-list-item>

              <div class="pl-8 pt-2">
                <small>*不显示系统插件和已经在插件页禁用的插件。</small>
              </div>
            </v-list>

            <div v-else class="text-center py-8">
              <v-icon size="64" color="grey-lighten-1">mdi-puzzle-outline</v-icon>
              <p class="text-grey mt-4">暂无可用的插件</p>
            </div>
          </div>
        </div>
      </v-card-text>
            
      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelSelection">取消</v-btn>
        <v-btn 
          color="primary" 
          @click="confirmSelection">
          确认选择
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import axios from 'axios'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  buttonText: {
    type: String,
    default: '选择插件集合...'
  },
  maxDisplayItems: {
    type: Number,
    default: 3
  }
})

const emit = defineEmits(['update:modelValue'])

const dialog = ref(false)
const pluginList = ref([])
const loading = ref(false)
const selectionMode = ref('custom') // 'all', 'none', 'custom'
const selectedPlugins = ref([])

// 判断是否为"所有插件"模式
const isAllPlugins = computed(() => {
  return props.modelValue && props.modelValue.length === 1 && props.modelValue[0] === '*'
})

// 移除插件
function removePlugin(pluginName) {
  if (props.modelValue && props.modelValue.length > 0) {
    const newValue = props.modelValue.filter(name => name !== pluginName)
    emit('update:modelValue', newValue)
  }
}

// 监听 modelValue 变化，同步内部状态
watch(() => props.modelValue, (newValue) => {
  if (!newValue || newValue.length === 0) {
    selectionMode.value = 'none'
    selectedPlugins.value = []
  } else if (newValue.length === 1 && newValue[0] === '*') {
    selectionMode.value = 'all'
    selectedPlugins.value = []
  } else {
    selectionMode.value = 'custom'
    selectedPlugins.value = [...newValue]
  }
}, { immediate: true })

async function openDialog() {
  dialog.value = true
  await loadPlugins()
}

async function loadPlugins() {
  loading.value = true
  try {
    const response = await axios.get('/api/plugin/get')
    if (response.data.status === 'ok') {
      // 只显示已激活且非系统的插件，并按名称排序
      pluginList.value = (response.data.data || [])
        .filter(plugin => plugin.activated && !plugin.reserved)
        .sort((a, b) => a.name.localeCompare(b.name))
    }
  } catch (error) {
    console.error('加载插件列表失败:', error)
    pluginList.value = []
  } finally {
    loading.value = false
  }
}

function confirmSelection() {
  let newValue = []
  
  switch (selectionMode.value) {
    case 'all':
      newValue = ['*']
      break
    case 'none':
      newValue = []
      break
    case 'custom':
      newValue = [...selectedPlugins.value]
      break
  }
  
  emit('update:modelValue', newValue)
  dialog.value = false
}

function cancelSelection() {
  // 恢复到原始状态
  const currentValue = props.modelValue || []
  if (currentValue.length === 0) {
    selectionMode.value = 'none'
    selectedPlugins.value = []
  } else if (currentValue.length === 1 && currentValue[0] === '*') {
    selectionMode.value = 'all'
    selectedPlugins.value = []
  } else {
    selectionMode.value = 'custom'
    selectedPlugins.value = [...currentValue]
  }
  
  dialog.value = false
}
</script>

<style scoped>
.v-list-item {
  transition: all 0.2s ease;
}

.v-list-item:hover {
  background-color: rgba(var(--v-theme-primary), 0.04);
}
</style>
