<template>
  <v-card class="provider-sources-panel h-100" elevation="0">
    <div class="d-flex align-center justify-space-between px-4 pt-4 pb-2">
      <div class="d-flex align-center ga-2">
        <h3 class="mb-0">{{ tm('providerSources.title') }}</h3>
      </div>
      <StyledMenu>
        <template #activator="{ props }">
          <v-btn
            v-bind="props"
            prepend-icon="mdi-plus"
            color="primary"
            variant="tonal"
            rounded="xl"
            size="small"
          >
            {{ tm('providerSources.add') }}
          </v-btn>
        </template>
        <v-list-item
          v-for="sourceType in availableSourceTypes"
          :key="sourceType.value"
          class="styled-menu-item"
          @click="emitAddSource(sourceType.value)"
        >
          <template #prepend>
            <v-avatar size="18" rounded="0" class="me-2">
              <v-img v-if="sourceType.icon" :src="sourceType.icon" alt="provider icon" cover></v-img>
              <v-icon v-else size="16">mdi-shape-outline</v-icon>
            </v-avatar>
          </template>
          <v-list-item-title>{{ sourceType.label }}</v-list-item-title>
        </v-list-item>
      </StyledMenu>
    </div>

    <div v-if="isMobile && displayedProviderSources.length > 0" class="px-4 pb-3">
      <div class="d-flex align-center ga-2">
        <v-select
          :model-value="selectedId"
          :items="mobileSourceItems"
          item-title="label"
          item-value="value"
          :label="tm('providerSources.selectCreated')"
          variant="solo-filled"
          density="comfortable"
          flat
          hide-details
          class="mobile-source-select"
          @update:model-value="onMobileSourceChange"
        >
          <template #item="{ props: itemProps, item }">
            <v-list-item v-bind="itemProps">
              <template #prepend>
                <v-avatar size="18" rounded="0" class="me-2">
                  <v-img v-if="item.raw.icon" :src="item.raw.icon" alt="provider icon" cover></v-img>
                  <v-icon v-else size="16">mdi-shape-outline</v-icon>
                </v-avatar>
              </template>
            </v-list-item>
          </template>
        </v-select>
        <v-btn
          v-if="selectedProviderSource"
          icon="mdi-delete"
          variant="text"
          size="small"
          color="error"
          @click.stop="emitDeleteSource(selectedProviderSource)"
        ></v-btn>
      </div>
    </div>

    <div v-else-if="displayedProviderSources.length > 0">
      <v-list class="provider-source-list" nav density="compact" lines="two">
        <v-list-item
          v-for="source in displayedProviderSources"
          :key="source.isPlaceholder ? `template-${source.templateKey}` : source.id"
          :value="source.id"
          :active="isActive(source)"
          :class="['provider-source-list-item', { 'provider-source-list-item--active': isActive(source) }]"
          rounded="lg"
          @click="emitSelectSource(source)"
        >
          <template #prepend>
            <v-avatar size="32" class="bg-grey-lighten-4" rounded="0">
              <v-img v-if="source?.provider" :src="resolveSourceIcon(source)" alt="logo" cover></v-img>
              <v-icon v-else size="32">mdi-creation</v-icon>
            </v-avatar>
          </template>
          <v-list-item-title class="font-weight-bold mb-1" style="font-family: Arial, Helvetica, sans-serif; font-size: 16px;">{{ getSourceDisplayName(source) }}</v-list-item-title>
          <v-list-item-subtitle class="text-truncate">{{ source.api_base || 'N/A' }}</v-list-item-subtitle>
          <template #append>
            <div class="d-flex align-center ga-1">
              <v-btn
                v-if="!source.isPlaceholder"
                icon="mdi-delete"
                variant="text"
                size="x-small"
                color="error"
                @click.stop="emitDeleteSource(source)"
              ></v-btn>
            </div>
          </template>
        </v-list-item>
      </v-list>
    </div>
    <div v-else class="text-center py-8 px-4">
      <v-icon size="48" color="grey-lighten-1">mdi-api-off</v-icon>
      <p class="text-grey mt-2">{{ tm('providerSources.empty') }}</p>
    </div>
  </v-card>
</template>

<script setup>
import { computed } from 'vue'
import { useDisplay } from 'vuetify'
import StyledMenu from '@/components/shared/StyledMenu.vue'

const props = defineProps({
  displayedProviderSources: {
    type: Array,
    default: () => []
  },
  selectedProviderSource: {
    type: Object,
    default: null
  },
  availableSourceTypes: {
    type: Array,
    default: () => []
  },
  tm: {
    type: Function,
    required: true
  },
  resolveSourceIcon: {
    type: Function,
    required: true
  },
  getSourceDisplayName: {
    type: Function,
    required: true
  }
})

const emit = defineEmits([
  'add-provider-source',
  'select-provider-source',
  'delete-provider-source'
])

const { smAndDown } = useDisplay()
const selectedId = computed(() => props.selectedProviderSource?.id || null)
const isMobile = computed(() => smAndDown.value)
const mobileSourceItems = computed(() =>
  (props.displayedProviderSources || []).map((source) => ({
    value: source.id,
    label: props.getSourceDisplayName(source),
    icon: props.resolveSourceIcon(source),
    source
  }))
)

const isActive = (source) => {
  if (source.isPlaceholder) return false
  return selectedId.value !== null && selectedId.value === source.id
}

const onMobileSourceChange = (sourceId) => {
  const matched = mobileSourceItems.value.find((item) => item.value === sourceId)
  if (matched?.source) {
    emitSelectSource(matched.source)
  }
}

const emitAddSource = (type) => emit('add-provider-source', type)
const emitSelectSource = (source) => emit('select-provider-source', source)
const emitDeleteSource = (source) => emit('delete-provider-source', source)
</script>

<style scoped>
.provider-sources-panel {
  min-height: 320px;
}

.provider-source-list {
  max-height: calc(100vh - 335px);
  overflow-y: auto;
  padding: 6px 8px;
}

.provider-source-list-item {
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.provider-source-list-item--active {
  background-color: #E8F0FE;
  border: 1px solid rgba(var(--v-theme-primary), 0.25);
}

@media (max-width: 960px) {
  .provider-source-list {
    max-height: none;
  }

  .provider-sources-panel {
    min-height: auto;
  }
}
</style>

<style>
.v-theme--PurpleThemeDark .provider-source-list-item--active {
  background-color: #2d2d2d;
  border: none;
}
</style>
