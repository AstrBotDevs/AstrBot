<template>
  <div class="d-flex align-center justify-space-between">
    <span v-if="!hasSelection" style="color: rgb(var(--v-theme-primaryText));">
      {{ tm('providerSelector.notSelected') }}
    </span>
    <span v-else class="provider-name-text">
      <template v-if="multiple">
        {{ selectedSummary }}
      </template>
      <template v-else>
        {{ modelValue }}
      </template>
    </span>
    <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
      {{ buttonText || tm('providerSelector.buttonText') }}
    </v-btn>
  </div>

  <!-- Provider Selection Dialog -->
  <v-dialog v-model="dialog" max-width="600px">
    <v-card>
      <v-card-title
        class="text-h3 py-4 d-flex align-center justify-space-between gap-4 flex-wrap"
        style="font-weight: normal;"
      >
        <span>{{ tm('providerSelector.dialogTitle') }}</span>
        <v-btn
          size="small"
          color="primary"
          variant="tonal"
          prepend-icon="mdi-plus"
          @click="openProviderDrawer"
        >
          {{ tm('providerSelector.createProvider') }}
        </v-btn>
      </v-card-title>
      
      <v-card-text class="pa-0" style="max-height: 400px; overflow-y: auto;">
        <v-progress-linear v-if="loading" indeterminate color="primary"></v-progress-linear>

        <div v-if="multiple && selectedProviders.length > 0" class="pa-3">
          <div class="text-caption text-medium-emphasis mb-2">
            {{ tm('providerSelector.selectedCount', { count: selectedProviders.length }) }}
          </div>
          <v-list density="compact" class="selected-order-list">
            <v-list-item
              v-for="(providerId, index) in selectedProviders"
              :key="`selected-${providerId}-${index}`"
              rounded="md"
              class="ma-1"
            >
              <v-list-item-title>{{ providerId }}</v-list-item-title>
              <template #append>
                <div class="d-flex ga-1">
                  <v-btn
                    icon="mdi-arrow-up"
                    size="x-small"
                    variant="text"
                    :disabled="index === 0"
                    @click.stop="moveSelected(index, -1)"
                  />
                  <v-btn
                    icon="mdi-arrow-down"
                    size="x-small"
                    variant="text"
                    :disabled="index === selectedProviders.length - 1"
                    @click.stop="moveSelected(index, 1)"
                  />
                  <v-btn
                    icon="mdi-close"
                    size="x-small"
                    variant="text"
                    @click.stop="removeSelected(providerId)"
                  />
                </div>
              </template>
            </v-list-item>
          </v-list>
          <v-divider class="ma-1"></v-divider>
        </div>
        
        <v-list v-if="!loading && providerList.length > 0" density="compact">
          <!-- 不选择选项 -->
          <v-list-item
            v-if="!multiple"
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
            :active="isProviderSelected(provider.id)"
            rounded="md"
            class="ma-1">
            <v-list-item-title>{{ provider.id }}</v-list-item-title>
            <v-list-item-subtitle>
              {{ provider.type || provider.provider_type || tm('providerSelector.unknownType') }}
              <span v-if="provider.model">- {{ provider.model }}</span>
            </v-list-item-subtitle>
            
            <template v-slot:append>
              <v-icon v-if="isProviderSelected(provider.id)" color="primary">mdi-check-circle</v-icon>
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

  <v-overlay
    v-model="providerDrawer"
    class="provider-drawer-overlay"
    location="right"
    transition="slide-x-reverse-transition"
    :scrim="true"
    @click:outside="closeProviderDrawer"
  >
    <v-card class="provider-drawer-card" elevation="12">
      <div class="provider-drawer-header">
        <v-btn icon variant="text" @click="closeProviderDrawer">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </div>
      <div class="provider-drawer-content">
        <ProviderPage :default-tab="defaultTab" />
      </div>
    </v-card>
  </v-overlay>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'
import ProviderPage from '@/views/ProviderPage.vue'

const props = defineProps({
  modelValue: {
    type: [String, Array],
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
    default: ''
  },
  multiple: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue'])
const { tm } = useModuleI18n('core.shared')

const dialog = ref(false)
const providerList = ref([])
const loading = ref(false)
const selectedProvider = ref('')
const selectedProviders = ref([])
const providerDrawer = ref(false)

const hasSelection = computed(() => {
  if (props.multiple) {
    return selectedProviders.value.length > 0
  }
  return Boolean(props.modelValue)
})

const selectedSummary = computed(() => {
  if (!props.multiple) {
    return ''
  }
  const ids = selectedProviders.value
  if (ids.length <= 2) {
    return ids.join(', ')
  }
  return `${ids.slice(0, 2).join(', ')} +${ids.length - 2}`
})

const defaultTab = computed(() => {
  if (props.providerType === 'agent_runner' && props.providerSubtype) {
    return `select_agent_runner_provider:${props.providerSubtype}`
  }
  return props.providerType || 'chat_completion'
})

// 监听 modelValue 变化，同步到 selectedProvider
watch(() => props.modelValue, (newValue) => {
  if (props.multiple) {
    selectedProviders.value = Array.isArray(newValue)
      ? [...newValue.filter((v) => typeof v === 'string' && v)]
      : []
    return
  }
  selectedProvider.value = typeof newValue === 'string' ? newValue : ''
}, { immediate: true })

watch(providerDrawer, (isOpen, wasOpen) => {
  if (!isOpen && wasOpen) {
    loadProviders()
  }
})

async function openDialog() {
  if (props.multiple) {
    selectedProviders.value = Array.isArray(props.modelValue)
      ? [...props.modelValue.filter((v) => typeof v === 'string' && v)]
      : []
  } else {
    selectedProvider.value = typeof props.modelValue === 'string' ? props.modelValue : ''
  }
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
  if (props.multiple) {
    if (!provider.id) {
      selectedProviders.value = []
      return
    }
    const idx = selectedProviders.value.indexOf(provider.id)
    if (idx >= 0) {
      selectedProviders.value.splice(idx, 1)
    } else {
      selectedProviders.value.push(provider.id)
    }
    return
  }
  selectedProvider.value = provider.id
}

function confirmSelection() {
  if (props.multiple) {
    emit('update:modelValue', [...selectedProviders.value])
  } else {
    emit('update:modelValue', selectedProvider.value)
  }
  dialog.value = false
}

function cancelSelection() {
  if (props.multiple) {
    selectedProviders.value = Array.isArray(props.modelValue)
      ? [...props.modelValue.filter((v) => typeof v === 'string' && v)]
      : []
  } else {
    selectedProvider.value = typeof props.modelValue === 'string' ? props.modelValue : ''
  }
  dialog.value = false
}

function isProviderSelected(providerId) {
  if (props.multiple) {
    return selectedProviders.value.includes(providerId)
  }
  return selectedProvider.value === providerId
}

function removeSelected(providerId) {
  const idx = selectedProviders.value.indexOf(providerId)
  if (idx >= 0) {
    selectedProviders.value.splice(idx, 1)
  }
}

function moveSelected(index, delta) {
  const targetIndex = index + delta
  if (
    targetIndex < 0
    || targetIndex >= selectedProviders.value.length
    || index < 0
    || index >= selectedProviders.value.length
  ) {
    return
  }
  const copied = [...selectedProviders.value]
  const [item] = copied.splice(index, 1)
  copied.splice(targetIndex, 0, item)
  selectedProviders.value = copied
}

function openProviderDrawer() {
  providerDrawer.value = true
}

function closeProviderDrawer() {
  providerDrawer.value = false
}
</script>

<style scoped>
.provider-name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: calc(100% - 80px);
  display: inline-block;
}

.selected-order-list {
  background: rgba(var(--v-theme-surface-variant), 0.15);
  border-radius: 10px;
}

.v-list-item {
  transition: all 0.2s ease;
}

.v-list-item:hover {
  background-color: rgba(var(--v-theme-primary), 0.04);
}

.v-list-item.v-list-item--active {
  background-color: rgba(var(--v-theme-primary), 0.08);
}

.provider-drawer-overlay {
  align-items: stretch;
  justify-content: flex-end;
}

.provider-drawer-card {
  width: clamp(360px, 70vw, 1200px);
  height: calc(100vh - 32px);
  margin: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.provider-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px 20px;
}

.provider-drawer-content {
  flex: 1;
  overflow: hidden;
}

.provider-drawer-content > * {
  height: 100%;
  overflow: auto;
}
</style>
