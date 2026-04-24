<template>
  <div class="provider-sources-panel">
    <div class="provider-sources-head">
      <div class="provider-sources-head__copy">
        <h3 class="provider-sources-title">{{ tm('providerSources.title') }}</h3>
      </div>

      <div class="provider-sources-controls">
        <div class="provider-sources-mobile-select">
          <v-select
            :model-value="selectedSourceValue"
            :items="sourceOptions"
            item-title="title"
            item-value="value"
            density="compact"
            variant="solo-filled"
            flat
            hide-details
            :placeholder="tm('providerSources.selectHint')"
            @update:model-value="selectSourceByValue"
        >
            <template #selection="{ item }">
              <div class="provider-source-select-value">
                <v-avatar size="22" rounded="lg" class="provider-source-avatar">
                  <v-img
                    v-if="item.raw.source?.provider"
                    :src="resolveSourceIcon(item.raw.source)"
                    alt="provider logo"
                    cover
                  ></v-img>
                  <v-icon v-else size="14">mdi-creation</v-icon>
                </v-avatar>
                <span>{{ item.raw.title }}</span>
              </div>
            </template>

            <template #item="{ props: itemProps, item }">
              <v-list-item
                v-bind="itemProps"
                :subtitle="item.raw.subtitle"
              >
                <template #prepend>
                  <v-avatar size="24" rounded="lg" class="provider-source-avatar me-2">
                    <v-img
                      v-if="item.raw.source?.provider"
                      :src="resolveSourceIcon(item.raw.source)"
                      alt="provider logo"
                      cover
                    ></v-img>
                    <v-icon v-else size="14">mdi-creation</v-icon>
                  </v-avatar>
                </template>
              </v-list-item>
            </template>
          </v-select>
        </div>

        <StyledMenu>
          <template #activator="{ props }">
            <v-btn
              v-bind="props"
              prepend-icon="mdi-plus"
              color="primary"
              variant="text"
              size="small"
              rounded="xl"
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
              <v-avatar size="18" rounded="0" class="me-2 provider-source-avatar">
                <v-img
                  v-if="sourceType.icon"
                  :src="sourceType.icon"
                  alt="provider icon"
                  cover
                ></v-img>
                <v-icon v-else size="16">mdi-shape-outline</v-icon>
              </v-avatar>
            </template>
            <v-list-item-title>{{ sourceType.label }}</v-list-item-title>
          </v-list-item>
        </StyledMenu>
      </div>
    </div>

    <div v-if="displayedProviderSources.length > 0" class="provider-sources-list">
      <button
        v-for="source in displayedProviderSources"
        :key="source.isPlaceholder ? `template-${source.templateKey}` : source.id"
        type="button"
        :class="[
          'provider-source-item',
          {
            'provider-source-item--active': isActive(source)
          }
        ]"
        @click="emitSelectSource(source)"
      >
        <v-avatar size="28" rounded="lg" class="provider-source-item__avatar provider-source-avatar">
          <v-img
            v-if="source?.provider"
            :src="resolveSourceIcon(source)"
            alt="provider logo"
            cover
          ></v-img>
          <v-icon v-else size="16">mdi-creation</v-icon>
        </v-avatar>

        <div class="provider-source-item__content">
          <div class="provider-source-item__title">
            {{ getSourceDisplayName(source) }}
          </div>
          <div class="provider-source-item__subtitle">
            {{ source.api_base || sourceBadge(source) }}
          </div>
        </div>

        <div class="provider-source-item__actions">
          <v-btn
            v-if="!source.isPlaceholder"
            icon="mdi-delete-outline"
            variant="text"
            size="small"
            @click.stop="emitDeleteSource(source)"
          ></v-btn>
        </div>
      </button>
    </div>

    <div v-else class="provider-sources-empty">
      <v-icon size="44" color="grey-lighten-1">mdi-api-off</v-icon>
      <p class="provider-sources-empty__text">{{ tm('providerSources.empty') }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
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

const selectedId = computed(() => props.selectedProviderSource?.id || null)

const isActive = (source) => {
  if (source.isPlaceholder) return false
  return selectedId.value !== null && selectedId.value === source.id
}

const sourceBadge = (source) => source.provider || source.templateKey || 'source'

const sourceValue = (source) => (
  source.isPlaceholder ? `template:${source.templateKey}` : `source:${source.id}`
)

const sourceOptions = computed(() =>
  props.displayedProviderSources.map((source) => ({
    title: props.getSourceDisplayName(source),
    subtitle: source.api_base || sourceBadge(source),
    value: sourceValue(source),
    source
  }))
)

const selectedSourceValue = computed(() => {
  if (!props.selectedProviderSource) return null
  return sourceValue(props.selectedProviderSource)
})

const emitAddSource = (type) => emit('add-provider-source', type)
const emitSelectSource = (source) => emit('select-provider-source', source)
const emitDeleteSource = (source) => emit('delete-provider-source', source)

const selectSourceByValue = (value) => {
  const option = sourceOptions.value.find((item) => item.value === value)
  if (option?.source) {
    emitSelectSource(option.source)
  }
}
</script>

<style scoped>
.provider-sources-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.provider-sources-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 20px 20px 12px;
}

.provider-sources-head__copy {
  min-width: 0;
}

.provider-sources-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.provider-sources-title {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.3;
}

.provider-sources-mobile {
  padding: 8px 20px 16px;
}

.provider-sources-mobile-select {
  display: none;
  min-width: 0;
  flex: 1;
}

.provider-source-select-value {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.provider-source-select-value span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-sources-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.provider-source-item {
  width: 100%;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  text-align: left;
}

.provider-source-item:hover,
.provider-source-item--active {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.provider-source-avatar {
  background: transparent !important;
}

.provider-source-item__content {
  min-width: 0;
  flex: 1;
}

.provider-source-item__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 600;
}

.provider-source-item__subtitle {
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 12px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.provider-source-item__actions {
  opacity: 0;
}

.provider-source-item:hover .provider-source-item__actions,
.provider-source-item--active .provider-source-item__actions {
  opacity: 1;
}

.provider-sources-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  text-align: center;
}

.provider-sources-empty__text {
  margin: 0;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 13px;
}

@media (max-width: 960px) {
  .provider-sources-panel {
    height: auto;
  }

  .provider-sources-head {
    padding: 16px 16px 8px;
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
  }

  .provider-sources-mobile-select {
    display: block;
  }

  .provider-sources-controls {
    width: 100%;
  }

  .provider-sources-list {
    display: none;
  }

  .provider-sources-empty {
    min-height: 160px;
  }
}

@media (max-width: 600px) {
  .provider-sources-controls :deep(.v-btn) {
    min-width: max-content;
  }
}
</style>
