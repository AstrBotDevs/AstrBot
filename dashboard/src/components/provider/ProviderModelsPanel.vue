<template>
  <div class="provider-models-panel">
    <div class="provider-models-toolbar">
      <div class="provider-models-title-wrap">
        <h3 class="provider-models-title">{{ tm('models.title') }}</h3>
        <small class="provider-models-subtitle">{{ tm('models.available') }} {{ availableCount }}</small>
      </div>

      <div class="provider-models-toolbar__actions">
        <v-text-field
          v-model="modelSearchProxy"
          density="compact"
          prepend-inner-icon="mdi-magnify"
          clearable
          hide-details
          variant="solo-filled"
          flat
          class="provider-models-search"
          :placeholder="tm('models.searchPlaceholder')"
        />

        <v-btn
          color="primary"
          prepend-icon="mdi-download"
          :loading="loadingModels"
          variant="tonal"
          rounded="xl"
          @click="emit('fetch-models')"
        >
          {{ isSourceModified ? tm('providerSources.saveAndFetchModels') : tm('providerSources.fetchModels') }}
        </v-btn>

        <v-btn
          color="primary"
          prepend-icon="mdi-pencil-plus"
          variant="text"
          rounded="xl"
          @click="emit('open-manual-model')"
        >
          {{ tm('models.manualAddButton') }}
        </v-btn>
      </div>
    </div>

    <div class="provider-models-sections">
      <section class="provider-models-section">
        <div class="provider-models-section__head">
          <div class="provider-models-section__title">{{ tm('models.configured') }}</div>
          <v-chip size="x-small" variant="tonal" label>{{ configuredEntries.length }}</v-chip>
        </div>

        <div v-if="configuredEntries.length" class="provider-models-list">
          <v-tooltip
            v-for="entry in configuredEntries"
            :key="entry.provider.id"
            location="top"
            max-width="400"
          >
            <template #activator="{ props: tooltipProps }">
              <div v-bind="tooltipProps" class="provider-model-row">
                <button
                  type="button"
                  class="provider-model-row__main"
                  @click="emit('open-provider-edit', entry.provider)"
                >
                  <div class="provider-model-row__title">{{ entry.provider.id }}</div>
                  <div class="provider-model-row__subtitle">{{ entry.provider.model }}</div>
                  <div class="provider-model-row__meta">
                    <span
                      v-for="item in capabilityIcons(entry.metadata)"
                      :key="item.icon"
                      class="provider-model-row__badge"
                    >
                      <v-icon size="14">{{ item.icon }}</v-icon>
                    </span>
                    <span
                      v-if="formatContextLimit(entry.metadata)"
                      class="provider-model-row__badge provider-model-row__badge--text"
                    >
                      {{ formatContextLimit(entry.metadata) }}
                    </span>
                  </div>
                </button>

                <div class="provider-model-row__actions" @click.stop>
                  <v-switch
                    :model-value="entry.provider.enable"
                    density="compact"
                    inset
                    hide-details
                    color="primary"
                    class="provider-model-row__switch"
                    :disabled="isProviderSaving(entry.provider.id)"
                    @update:modelValue="emit('toggle-provider-enable', entry.provider, $event)"
                  ></v-switch>

                  <v-btn
                    icon="mdi-connection"
                    size="small"
                    variant="text"
                    :disabled="!entry.provider.enable || isProviderSaving(entry.provider.id)"
                    :loading="isProviderTesting(entry.provider.id)"
                    @click.stop="emit('test-provider', entry.provider)"
                  ></v-btn>
                  <v-btn
                    icon="mdi-cog-outline"
                    size="small"
                    variant="text"
                    @click.stop="emit('open-provider-edit', entry.provider)"
                  ></v-btn>
                  <v-btn
                    icon="mdi-delete-outline"
                    size="small"
                    variant="text"
                    @click.stop="emit('delete-provider', entry.provider)"
                  ></v-btn>
                </div>
              </div>
            </template>
            <div><strong>{{ tm('models.tooltips.providerId') }}:</strong> {{ entry.provider.id }}</div>
            <div><strong>{{ tm('models.tooltips.modelId') }}:</strong> {{ entry.provider.model }}</div>
          </v-tooltip>
        </div>

        <div v-else class="provider-models-empty">
          <v-icon size="36" color="grey-lighten-1">mdi-package-variant-closed</v-icon>
          <p>{{ tm('models.empty') }}</p>
        </div>
      </section>

      <v-divider></v-divider>

      <section class="provider-models-section provider-models-section--available">
        <div class="provider-models-section__head">
          <div class="provider-models-section__title">{{ tm('models.available') }}</div>
          <v-chip size="x-small" variant="tonal" label>{{ availableEntries.length }}</v-chip>
        </div>

        <div v-if="availableEntries.length" class="provider-models-list provider-models-list--available">
          <v-tooltip
            v-for="entry in availableEntries"
            :key="entry.model"
            location="top"
            max-width="400"
          >
            <template #activator="{ props: tooltipProps }">
              <div v-bind="tooltipProps" class="provider-model-row">
                <button
                  type="button"
                  class="provider-model-row__main"
                  @click="emit('add-model-provider', entry.model)"
                >
                  <div class="provider-model-row__title provider-model-row__title--mono">{{ entry.model }}</div>
                  <div class="provider-model-row__meta">
                    <span
                      v-for="item in capabilityIcons(entry.metadata)"
                      :key="item.icon"
                      class="provider-model-row__badge"
                    >
                      <v-icon size="14">{{ item.icon }}</v-icon>
                    </span>
                    <span
                      v-if="formatContextLimit(entry.metadata)"
                      class="provider-model-row__badge provider-model-row__badge--text"
                    >
                      {{ formatContextLimit(entry.metadata) }}
                    </span>
                  </div>
                </button>

                <div class="provider-model-row__actions">
                  <v-btn
                    icon="mdi-plus"
                    size="small"
                    variant="text"
                    color="primary"
                    @click.stop="emit('add-model-provider', entry.model)"
                  ></v-btn>
                </div>
              </div>
            </template>
            <div><strong>{{ tm('models.tooltips.modelId') }}:</strong> {{ entry.model }}</div>
          </v-tooltip>
        </div>

        <div v-else class="provider-models-empty provider-models-empty--small">
          <v-icon size="36" color="grey-lighten-1">mdi-database-search-outline</v-icon>
          <p>{{ tm('models.noModelsFound') }}</p>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { normalizeTextInput } from '@/utils/inputValue'

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
  supportsAudioInput: {
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
  savingProviders: {
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
  set: (val) => emit('update:modelSearch', normalizeTextInput(val))
})

const configuredEntries = computed(() =>
  (props.entries || []).filter((entry) => entry.type === 'configured')
)

const availableEntries = computed(() =>
  (props.entries || []).filter((entry) => entry.type === 'available')
)

const capabilityIcons = (metadata) => {
  const icons = []
  if (props.supportsImageInput(metadata)) {
    icons.push({ icon: 'mdi-image-outline' })
  }
  if (props.supportsAudioInput(metadata)) {
    icons.push({ icon: 'mdi-music-note-outline' })
  }
  if (props.supportsToolCall(metadata)) {
    icons.push({ icon: 'mdi-wrench-outline' })
  }
  if (props.supportsReasoning(metadata)) {
    icons.push({ icon: 'mdi-brain' })
  }
  return icons
}

const isProviderTesting = (providerId) => props.testingProviders.includes(providerId)
const isProviderSaving = (providerId) => props.savingProviders.includes(providerId)
</script>

<style scoped>
.provider-models-panel {
  display: grid;
  gap: 18px;
}

.provider-models-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: nowrap;
}

.provider-models-title {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  line-height: 1.3;
}

.provider-models-title-wrap {
  min-width: 0;
  flex-shrink: 0;
}

.provider-models-subtitle {
  display: block;
  margin-top: 6px;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 12px;
}

.provider-models-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  justify-content: flex-end;
  flex-wrap: nowrap;
}

.provider-models-search {
  flex: 0 1 240px;
  min-width: 180px;
  max-width: 260px;
}

.provider-models-sections {
  display: flex;
  flex-direction: column;
}

.provider-models-section {
  padding: 4px 0;
}

.provider-models-section--available {
  padding-top: 22px;
}

.provider-models-section__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.provider-models-section__title {
  font-size: 14px;
  font-weight: 650;
}

.provider-models-list {
  display: flex;
  flex-direction: column;
}

.provider-models-list--available {
  max-height: min(420px, 52vh);
  overflow-y: auto;
  padding-right: 4px;
}

.provider-model-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.provider-model-row:last-child {
  border-bottom: 0;
}

.provider-model-row__main {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  color: inherit;
  padding: 0;
  text-align: left;
  cursor: pointer;
}

.provider-model-row__title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.provider-model-row__title--mono {
  font-family:
    ui-monospace,
    SFMono-Regular,
    Menlo,
    Monaco,
    Consolas,
    "Liberation Mono",
    "Courier New",
    monospace;
}

.provider-model-row__subtitle {
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.provider-model-row__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.provider-model-row__badge {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  color: rgba(var(--v-theme-on-surface), 0.58);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.provider-model-row__badge--text {
  width: auto;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
}

.provider-model-row__actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.provider-model-row__switch {
  margin-right: 2px;
}

.provider-models-empty {
  min-height: 160px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: rgba(var(--v-theme-on-surface), 0.56);
  text-align: center;
  font-size: 13px;
}

.provider-models-empty--small {
  min-height: 120px;
}

@media (max-width: 760px) {
  .provider-models-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .provider-models-title-wrap {
    flex-shrink: 1;
  }

  .provider-models-toolbar__actions {
    align-items: stretch;
    justify-content: stretch;
    flex-wrap: wrap;
  }

  .provider-models-search {
    flex: 1 1 100%;
    min-width: 0;
    max-width: none;
  }

  .provider-models-toolbar__actions :deep(.v-btn) {
    flex: 1 1 160px;
    min-width: 0;
  }

  .provider-models-toolbar__actions :deep(.v-btn__content) {
    white-space: normal;
  }
}

@media (max-width: 600px) {
  .provider-models-panel {
    gap: 14px;
  }

  .provider-model-row {
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
    padding: 14px 0;
  }

  .provider-model-row__actions {
    align-self: flex-end;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
}
</style>
