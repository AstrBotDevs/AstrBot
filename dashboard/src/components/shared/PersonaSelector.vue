<template>
  <div class="d-flex align-center justify-space-between">
    <span v-if="!modelValue" style="color: rgb(var(--v-theme-primaryText));">
      未选择
    </span>
    <span v-else>
      {{ modelValue === 'default' ? '默认人格' : modelValue }}
    </span>
    <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
      {{ buttonText }}
    </v-btn>
  </div>

  <!-- Persona Selection Dialog -->
  <v-dialog v-model="dialog" max-width="600px">
    <v-card>
      <v-card-title class="text-h3 py-4" style="font-weight: normal;">
        选择人格
      </v-card-title>
      
      <v-card-text class="pa-0" style="max-height: 400px; overflow-y: auto;">
        <v-progress-linear v-if="loading" indeterminate color="primary"></v-progress-linear>
        
        <v-list v-if="!loading && personaList.length > 0" density="compact">
          <v-list-item
            v-for="persona in personaList"
            :key="persona.persona_id"
            :value="persona.persona_id"
            @click="selectPersona(persona)"
            :active="selectedPersona === persona.persona_id"
            rounded="md"
            class="ma-1">
            <v-list-item-title>{{ persona.persona_id === 'default' ? '默认人格' : persona.persona_id }}</v-list-item-title>
            <v-list-item-subtitle>
              {{ persona.system_prompt ? persona.system_prompt.substring(0, 50) + '...' : '无描述' }}
            </v-list-item-subtitle>
            
            <template v-slot:append>
              <v-icon v-if="selectedPersona === persona.persona_id" color="primary">mdi-check-circle</v-icon>
            </template>
          </v-list-item>
        </v-list>
        
        <div v-else-if="!loading && personaList.length === 0" class="text-center py-8">
          <v-icon size="64" color="grey-lighten-1">mdi-account-off</v-icon>
          <p class="text-grey mt-4">暂无可用的人格</p>
        </div>
      </v-card-text>
      
      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelSelection">取消</v-btn>
        <v-btn 
          color="primary" 
          @click="confirmSelection"
          :disabled="!selectedPersona">
          确认选择
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import axios from 'axios'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  buttonText: {
    type: String,
    default: '选择人格...'
  }
})

const emit = defineEmits(['update:modelValue'])

const dialog = ref(false)
const personaList = ref([])
const loading = ref(false)
const selectedPersona = ref('')

// 监听 modelValue 变化，同步到 selectedPersona
watch(() => props.modelValue, (newValue) => {
  selectedPersona.value = newValue || ''
}, { immediate: true })

async function openDialog() {
  selectedPersona.value = props.modelValue || ''
  dialog.value = true
  await loadPersonas()
}

async function loadPersonas() {
  loading.value = true
  try {
    const response = await axios.get('/api/persona/list')
    if (response.data.status === 'ok') {
      const personas = response.data.data || []
      // 添加默认人格选项
      personaList.value = [
        {
          persona_id: 'default',
          system_prompt: 'You are a helpful and friendly assistant.'
        },
        ...personas
      ]
    }
  } catch (error) {
    console.error('加载人格列表失败:', error)
    personaList.value = [
      {
        persona_id: 'default',
        system_prompt: 'You are a helpful and friendly assistant.'
      }
    ]
  } finally {
    loading.value = false
  }
}

function selectPersona(persona) {
  selectedPersona.value = persona.persona_id
}

function confirmSelection() {
  emit('update:modelValue', selectedPersona.value)
  dialog.value = false
}

function cancelSelection() {
  selectedPersona.value = props.modelValue || ''
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

.v-list-item.v-list-item--active {
  background-color: rgba(var(--v-theme-primary), 0.08);
}
</style>
