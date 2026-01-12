<template>
  <div class="mt-4">
    <div class="d-flex align-center ga-2 mb-2">
      <h3 class="text-h5 font-weight-bold mb-0">{{ tm('models.configured') }}</h3>
      <small style="color: grey;" v-if="availableCount">{{ tm('models.available') }} {{ availableCount }}</small>
      <v-text-field
        v-model="modelSearchProxy"
        density="compact"
        prepend-inner-icon="mdi-magnify"
        hide-details
        variant="solo-filled"
        flat
        class="ml-1"
        style="max-width: 240px;"
        :placeholder="tm('models.searchPlaceholder')"
      />
      <v-spacer></v-spacer>
      <v-btn
        color="primary"
        prepend-icon="mdi-download"
        :loading="loadingModels"
        @click="emit('fetch-models')"
        variant="tonal"
        size="small"
      >
        {{ isSourceModified ? tm('providerSources.saveAndFetchModels') : tm('providerSources.fetchModels') }}
      </v-btn>
      <v-btn
        color="primary"
        prepend-icon="mdi-pencil-plus"
        variant="text"
        size="small"
        class="ml-1"
        @click="emit('open-manual-model')"
      >
        {{ tm('models.manualAddButton') }}
      </v-btn>
    </div>

    <v-list
      density="compact"
      class="rounded-lg border"
      style="max-height: 520px; overflow-y: auto; font-family:system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;"
    >
      <template v-if="entries.length > 0">
        <template v-for="entry in entries" :key="entry.type === 'configured' ? `provider-${entry.provider.id}` : `model-${entry.model}`">
          <v-tooltip location="top" max-width="400" v-if="entry.type === 'configured'">
            <template #activator="{ props }">
              <v-list-item
                v-bind="props"
                class="provider-compact-item"
                @click="emit('open-provider-edit', entry.provider)"
              >
                <v-list-item-title class="font-weight-medium text-truncate">
                  {{ entry.provider.id }}
                </v-list-item-title>
            <v-list-item-subtitle class="text-caption text-grey d-flex align-center ga-1" style="font-family: monospace;">
              <span>{{ entry.provider.model }}</span>
              <v-icon v-if="supportsImageInput(entry.metadata)" size="14" color="grey">
                mdi-eye-outline
              </v-icon>
              <v-icon v-if="supportsToolCall(entry.metadata)" size="14" color="grey">
                mdi-wrench
              </v-icon>
              <v-icon v-if="supportsReasoning(entry.metadata)" size="14" color="grey">
                mdi-brain
              </v-icon>
              <span v-if="formatContextLimit(entry.metadata)">
                {{ formatContextLimit(entry.metadata) }}
              </span>
            </v-list-item-subtitle>
            <template #append>
              <div class="d-flex align-center ga-1" @click.stop>
                <v-switch
                  v-model="entry.provider.enable"
                  density="compact"
                  inset
                  hide-details
                  color="primary"
                  class="mr-1"
                  @update:modelValue="emit('toggle-provider-enable', entry.provider, $event)"
                ></v-switch>
                <v-tooltip location="top" max-width="300">
                  {{ tm('availability.test') }}
                  <template #activator="{ props }">
                    <v-btn
                      icon="mdi-connection"
                      size="small"
                      variant="text"
                      :disabled="!entry.provider.enable"
                      :loading="isProviderTesting(entry.provider.id)"
                      v-bind="props"
                      @click.stop="emit('test-provider', entry.provider)"
                    ></v-btn>
                  </template>
                </v-tooltip>

                <v-tooltip location="top" max-width="300">
                  {{ tm('models.configure') }}
                  <template #activator="{ props }">
                    <v-btn
                      icon="mdi-cog"
                      size="small"
                      variant="text"
                      v-bind="props"
                      @click.stop="emit('open-provider-edit', entry.provider)"
                    ></v-btn>
                  </template>
                </v-tooltip>

                <v-btn icon="mdi-delete" size="small" variant="text" color="error" @click.stop="emit('delete-provider', entry.provider)"></v-btn>
              </div>
            </template>
              </v-list-item>
            </template>
            <div>
              <div><strong>{{ tm('models.tooltips.providerId') }}:</strong> {{ entry.provider.id }}</div>
              <div><strong>{{ tm('models.tooltips.modelId') }}:</strong> {{ entry.provider.model }}</div>
            </div>
          </v-tooltip>

          <v-tooltip location="top" max-width="400" v-else>
            <template #activator="{ props }">
              <v-list-item v-bind="props" class="cursor-pointer" @click="emit('add-model-provider', entry.model)">
                <v-list-item-title>{{ entry.model }}</v-list-item-title>
            <v-list-item-subtitle class="text-caption text-grey d-flex align-center ga-1">
              <span>{{ entry.model }}</span>
              <v-icon v-if="supportsImageInput(entry.metadata)" size="14" color="grey">
                mdi-eye-outline
              </v-icon>
              <v-icon v-if="supportsToolCall(entry.metadata)" size="14" color="grey">
                mdi-wrench
              </v-icon>
              <v-icon v-if="supportsReasoning(entry.metadata)" size="14" color="grey">
                mdi-brain
              </v-icon>
              <span v-if="formatContextLimit(entry.metadata)">
                {{ formatContextLimit(entry.metadata) }}
              </span>
            </v-list-item-subtitle>
                <template #append>
                  <v-btn icon="mdi-plus" size="small" variant="text" color="primary"></v-btn>
                </template>
              </v-list-item>
            </template>
            <div>
              <div><strong>{{ tm('models.tooltips.modelId') }}:</strong> {{ entry.model }}</div>
            </div>
          </v-tooltip>
        </template>
      </template>
      <template v-else>
        <div class="text-center pa-4 text-medium-emphasis">
          <v-icon size="48" color="grey-lighten-1">mdi-package-variant</v-icon>
          <p class="text-grey mt-2">{{ tm('models.empty') }}</p>
        </div>
      </template>
    </v-list>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  entries: {
    type: Array,
    default: () => []
  },
  availableCount: {
    type: Number,
    default: 0
  },
  modelSearch: {
    type: String,
    default: ''
  },
  loadingModels: {
    type: Boolean,
    default: false
  },
  isSourceModified: {
    type: Boolean,
    default: false
  },
  supportsImageInput: {
    type: Function,
    required: true
  },
  supportsToolCall: {
    type: Function,
    required: true
  },
  supportsReasoning: {
    type: Function,
    required: true
  },
  formatContextLimit: {
    type: Function,
    required: true
  },
  testingProviders: {
    type: Array,
    default: () => []
  },
  tm: {
    type: Function,
    required: true
  }
})

const emit = defineEmits([
  'update:modelSearch',
  'fetch-models',
  'open-manual-model',
  'open-provider-edit',
  'toggle-provider-enable',
  'test-provider',
  'delete-provider',
  'add-model-provider'
])

const modelSearchProxy = computed({
  get: () => props.modelSearch,
  set: (val) => emit('update:modelSearch', val)
})

const isProviderTesting = (providerId) => props.testingProviders.includes(providerId)
</script>

<style scoped>
.border {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.cursor-pointer {
  cursor: pointer;
}
</style>
