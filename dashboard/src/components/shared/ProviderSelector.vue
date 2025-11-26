<template>
  <div class="d-flex align-center justify-space-between">
    <span v-if="!modelValue" style="color: rgb(var(--v-theme-primaryText));">
      {{ tm('providerSelector.notSelected') }}
    </span>
    <span v-else>
      {{ modelValue }}
    </span>
    <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
      {{ buttonText }}
    </v-btn>
  </div>

  <!-- Provider Selection Dialog -->
  <v-dialog v-model="dialog" max-width="600px">
    <v-card>
      <v-card-title class="text-h3 py-4" style="font-weight: normal;">
        {{ tm('providerSelector.dialogTitle') }}
      </v-card-title>
      
      <v-card-text class="pa-0" style="max-height: 400px; overflow-y: auto;">
        <v-progress-linear v-if="loading" indeterminate color="primary"></v-progress-linear>
        
        <v-list v-if="!loading && providerList.length > 0" density="compact">
          <!-- 不选择选项 -->
          <v-list-item
            key="none"
            value=""
            @click="selectProvider({ id: '' })"
            :active="selectedProvider === ''"
            rounded="md"
            class="ma-1">
            <v-list-item-title>{{ tm('providerSelector.clearSelection') }}</v-list-item-title>
            <v-list-item-subtitle>{{ tm('providerSelector.clearSelectionSubtitle') }}</v-list-item-subtitle>
            
            <template v-slot:append>
              <v-icon v-if="selectedProvider === ''" color="primary">mdi-check-circle</v-icon>
            </template>
          </v-list-item>
          
          <v-divider class="ma-1"></v-divider>
          
          <v-list-item
            v-for="provider in providerList"
            :key="provider.id"
            :value="provider.id"
            @click="selectProvider(provider)"
            :active="selectedProvider === provider.id"
            rounded="md"
            class="ma-1">
            <v-list-item-title>{{ provider.id }}</v-list-item-title>
            <v-list-item-subtitle>
              {{ provider.type || provider.provider_type || tm('providerSelector.unknownType') }}
              <span v-if="provider.model_config?.model">- {{ provider.model_config.model }}</span>
            </v-list-item-subtitle>
            
            <template v-slot:append>
              <v-icon v-if="selectedProvider === provider.id" color="primary">mdi-check-circle</v-icon>
            </template>
          </v-list-item>
        </v-list>
        
        <div v-else-if="!loading && providerList.length === 0" class="text-center py-8">
          <v-icon size="64" color="grey-lighten-1">mdi-api-off</v-icon>
          <p class="text-grey mt-4">{{ tm('providerSelector.noProviders') }}</p>
        </div>
      </v-card-text>
      
      <v-divider></v-divider>
      
      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelSelection">{{ tm('providerSelector.cancelSelection') }}</v-btn>
        <v-btn 
          color="primary" 
          @click="confirmSelection">
          {{ tm('providerSelector.confirmSelection') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  providerType: {
    type: String,
    default: 'chat_completion'
  },
  providerSubtype: {
    type: String,
    default: ''
  },
  buttonText: {
    type: String,
    default: '选择提供商...'
  }
})

const emit = defineEmits(['update:modelValue'])
const { tm } = useModuleI18n('core.shared')

const dialog = ref(false)
const providerList = ref([])
const loading = ref(false)
const selectedProvider = ref('')

// 监听 modelValue 变化，同步到 selectedProvider
watch(() => props.modelValue, (newValue) => {
  selectedProvider.value = newValue || ''
}, { immediate: true })

async function openDialog() {
  selectedProvider.value = props.modelValue || ''
  dialog.value = true
  await loadProviders()
}

async function loadProviders() {
  loading.value = true
  try {
    const response = await axios.get('/api/config/provider/list', {
      params: {
        provider_type: props.providerType
      }
    })
    if (response.data.status === 'ok') {
      const providers = response.data.data || []
      providerList.value = props.providerSubtype
        ? providers.filter((provider) => matchesProviderSubtype(provider, props.providerSubtype))
        : providers
    }
  } catch (error) {
    console.error('加载提供商列表失败:', error)
    providerList.value = []
  } finally {
    loading.value = false
  }
}

function matchesProviderSubtype(provider, subtype) {
  if (!subtype) {
    return true
  }
  const normalized = String(subtype).toLowerCase()
  const candidates = [provider.type, provider.provider, provider.id]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase())
  return candidates.includes(normalized)
}

function selectProvider(provider) {
  selectedProvider.value = provider.id
}

function confirmSelection() {
  emit('update:modelValue', selectedProvider.value)
  dialog.value = false
}

function cancelSelection() {
  selectedProvider.value = props.modelValue || ''
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
