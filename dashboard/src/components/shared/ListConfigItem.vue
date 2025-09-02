<template>
  <div class="d-flex align-center justify-space-between">
    <div>
      <span v-if="!modelValue || modelValue.length === 0" style="color: rgb(var(--v-theme-primaryText));">
        暂无项目
      </span>
      <div v-else class="d-flex flex-wrap ga-2">
        <v-chip v-for="item in displayItems" :key="item" size="x-small" label color="primary">
          {{ item.length > 20 ? item.slice(0, 20) + '...' : item }}
        </v-chip>
        <v-chip v-if="modelValue.length > maxDisplayItems" size="x-small" label color="grey-lighten-1">
          +{{ modelValue.length - maxDisplayItems }}
        </v-chip>
      </div>
    </div>
    <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
      {{ buttonText }}
    </v-btn>
  </div>

  <!-- List Management Dialog -->
  <v-dialog v-model="dialog" max-width="600px">
    <v-card>
      <v-card-title class="text-h3 py-4" style="font-weight: normal;">
        {{ dialogTitle }}
      </v-card-title>
      
      <v-card-text class="pa-0" style="max-height: 400px; overflow-y: auto;">
        <v-list v-if="localItems.length > 0" density="compact">
          <v-list-item
            v-for="(item, index) in localItems"
            :key="index"
            rounded="md"
            class="ma-1">
            <v-list-item-title v-if="editIndex !== index">
              {{ item }}
            </v-list-item-title>
            <v-text-field 
              v-else
              v-model="editItem" 
              hide-details 
              variant="outlined" 
              density="compact"
              @keyup.enter="saveEdit" 
              @keyup.esc="cancelEdit"
              autofocus
            ></v-text-field>
            
            <template v-slot:append>
              <div v-if="editIndex !== index" class="d-flex">
                <v-btn @click="startEdit(index, item)" variant="plain" icon size="small">
                  <v-icon>mdi-pencil</v-icon>
                </v-btn>
                <v-btn @click="removeItem(index)" variant="plain" icon size="small">
                  <v-icon>mdi-close</v-icon>
                </v-btn>
              </div>
              <div v-else class="d-flex">
                <v-btn @click="saveEdit" variant="plain" color="success" icon size="small">
                  <v-icon>mdi-check</v-icon>
                </v-btn>
                <v-btn @click="cancelEdit" variant="plain" color="error" icon size="small">
                  <v-icon>mdi-close</v-icon>
                </v-btn>
              </div>
            </template>
          </v-list-item>
        </v-list>
        
        <div v-else class="text-center py-8">
          <v-icon size="64" color="grey-lighten-1">mdi-format-list-bulleted</v-icon>
          <p class="text-grey mt-4">暂无项目</p>
        </div>
      </v-card-text>

      <!-- Add new item section -->
      <v-card-text class="pa-4">
        <div class="d-flex align-center ga-2">
          <v-text-field 
            v-model="newItem" 
            :label="t('core.common.list.addItemPlaceholder')" 
            @keyup.enter="addItem" 
            clearable 
            hide-details
            variant="outlined" 
            density="compact"
            class="flex-grow-1">
          </v-text-field>
          <v-btn @click="addItem" variant="tonal" color="primary">
            <v-icon>mdi-plus</v-icon>
            {{ t('core.common.list.addButton') }}
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
    type: Array,
    default: () => []
  },
  label: {
    type: String,
    default: ''
  },
  buttonText: {
    type: String,
    default: '修改'
  },
  dialogTitle: {
    type: String,
    default: '修改列表项'
  },
  maxDisplayItems: {
    type: Number,
    default: 1
  }
})

const emit = defineEmits(['update:modelValue'])

const dialog = ref(false)
const localItems = ref([])
const originalItems = ref([])
const newItem = ref('')
const editIndex = ref(-1)
const editItem = ref('')

// 计算要显示的项目
const displayItems = computed(() => {
  return props.modelValue.slice(0, props.maxDisplayItems)
})

// 监听 modelValue 变化，同步到 localItems
watch(() => props.modelValue, (newValue) => {
  localItems.value = [...(newValue || [])]
}, { immediate: true })

function openDialog() {
  localItems.value = [...(props.modelValue || [])]
  originalItems.value = [...(props.modelValue || [])]
  dialog.value = true
  editIndex.value = -1
  editItem.value = ''
  newItem.value = ''
}

function addItem() {
  if (newItem.value.trim() !== '') {
    localItems.value.push(newItem.value.trim())
    newItem.value = ''
  }
}

function removeItem(index) {
  localItems.value.splice(index, 1)
}

function startEdit(index, item) {
  editIndex.value = index
  editItem.value = item
}

function saveEdit() {
  if (editItem.value.trim() !== '') {
    localItems.value[editIndex.value] = editItem.value.trim()
    cancelEdit()
  }
}

function cancelEdit() {
  editIndex.value = -1
  editItem.value = ''
}

function confirmDialog() {
  emit('update:modelValue', [...localItems.value])
  dialog.value = false
}

function cancelDialog() {
  localItems.value = [...originalItems.value]
  editIndex.value = -1
  editItem.value = ''
  newItem.value = ''
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

.v-chip {
  margin: 2px;
}
</style>