<template>
  <div class="provider-models-panel">
    <div class="provider-models-head">
      <div class="provider-models-title-wrap">
        <h3 class="provider-models-title">{{ tm("models.configured") }}</h3>
        <small v-if="availableCount" class="provider-models-subtitle"
          >{{ tm("models.available") }} {{ availableCount }}</small
        >
      </div>
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
      <div class="provider-models-actions">
        <v-btn
          color="primary"
          prepend-icon="mdi-download"
          :loading="loadingModels"
          @click="emit('fetch-models')"
          variant="tonal"
          size="small"
        >
          {{
            isSourceModified
              ? tm("providerSources.saveAndFetchModels")
              : tm("providerSources.fetchModels")
          }}
        </v-btn>
        <v-btn
          color="primary"
          prepend-icon="mdi-pencil-plus"
          variant="text"
          size="small"
          @click="emit('open-manual-model')"
        >
          {{ tm("models.manualAddButton") }}
        </v-btn>
      </div>
    </div>

    <v-list density="compact" class="provider-models-list">
      <template v-if="entries.length > 0">
        <template
          v-for="entry in entries"
          :key="
            entry.type === 'configured'
              ? `provider-${entry.provider.id}`
              : `model-${entry.model}`
          "
        >
          <v-tooltip
            location="top"
            max-width="400"
            v-if="entry.type === 'configured'"
          >
            <template #activator="{ props }">
              <v-list-item
                v-bind="props"
                class="provider-compact-item"
                @click="emit('open-provider-edit', entry.provider)"
              >
                <v-list-item-title class="font-weight-medium text-truncate">
                  {{ entry.provider.id }}
                </v-list-item-title>
                <v-list-item-subtitle
                  class="provider-model-subtitle d-flex align-center ga-1"
                >
                  <span>{{ entry.provider.model }}</span>
                  <v-icon
                    v-if="supportsImageInput(entry.metadata)"
                    size="14"
                    color="grey"
                  >
                    mdi-eye-outline
                  </v-icon>
                  <v-icon
                    v-if="supportsToolCall(entry.metadata)"
                    size="14"
                    color="grey"
                  >
                    mdi-wrench
                  </v-icon>
                  <v-icon
                    v-if="supportsReasoning(entry.metadata)"
                    size="14"
                    color="grey"
                  >
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
                      @update:modelValue="
                        emit('toggle-provider-enable', entry.provider, $event)
                      "
                    ></v-switch>
                    <v-tooltip location="top" max-width="300">
                      {{ tm("availability.test") }}
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
                      {{ tm("models.configure") }}
                      <template #activator="{ props }">
                        <v-btn
                          icon="mdi-cog"
                          size="small"
                          variant="text"
                          v-bind="props"
                          @click.stop="
                            emit('open-provider-edit', entry.provider)
                          "
                        ></v-btn>
                      </template>
                    </v-tooltip>

                    <v-btn
                      icon="mdi-delete"
                      size="small"
                      variant="text"
                      color="error"
                      @click.stop="emit('delete-provider', entry.provider)"
                    ></v-btn>
                  </div>
                </template>
              </v-list-item>
            </template>
            <div>
              <div>
                <strong>{{ tm("models.tooltips.providerId") }}:</strong>
                {{ entry.provider.id }}
              </div>
              <div>
                <strong>{{ tm("models.tooltips.modelId") }}:</strong>
                {{ entry.provider.model }}
              </div>
            </div>
          </v-tooltip>

          <v-tooltip location="top" max-width="400" v-else>
            <template #activator="{ props }">
              <v-list-item
                v-bind="props"
                class="cursor-pointer"
                @click="emit('add-model-provider', entry.model)"
              >
                <v-list-item-title>{{ entry.model }}</v-list-item-title>
                <v-list-item-subtitle
                  class="provider-model-subtitle d-flex align-center ga-1"
                >
                  <span>{{ entry.model }}</span>
                  <v-icon
                    v-if="supportsImageInput(entry.metadata)"
                    size="14"
                    color="grey"
                  >
                    mdi-eye-outline
                  </v-icon>
                  <v-icon
                    v-if="supportsToolCall(entry.metadata)"
                    size="14"
                    color="grey"
                  >
                    mdi-wrench
                  </v-icon>
                  <v-icon
                    v-if="supportsReasoning(entry.metadata)"
                    size="14"
                    color="grey"
                  >
                    mdi-brain
                  </v-icon>
                  <span v-if="formatContextLimit(entry.metadata)">
                    {{ formatContextLimit(entry.metadata) }}
                  </span>
                </v-list-item-subtitle>
                <template #append>
                  <v-btn
                    icon="mdi-plus"
                    size="small"
                    variant="text"
                    color="primary"
                  ></v-btn>
                </template>
              </v-list-item>
            </template>
            <div>
              <div>
                <strong>{{ tm("models.tooltips.modelId") }}:</strong>
                {{ entry.model }}
              </div>
            </div>
          </v-tooltip>
        </template>
      </template>
      <template v-else>
        <div class="text-center pa-4 text-medium-emphasis">
          <v-icon size="48" color="grey-lighten-1">mdi-package-variant</v-icon>
          <p class="text-grey mt-2">{{ tm("models.empty") }}</p>
        </div>
      </template>
    </v-list>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { normalizeTextInput } from "@/utils/inputValue";

const props = defineProps({
  entries: {
    type: Array,
    default: () => [],
  },
  availableCount: {
    type: Number,
    default: 0,
  },
  modelSearch: {
    type: String,
    default: "",
  },
  loadingModels: {
    type: Boolean,
    default: false,
  },
  isSourceModified: {
    type: Boolean,
    default: false,
  },
  supportsImageInput: {
    type: Function,
    required: true,
  },
  supportsToolCall: {
    type: Function,
    required: true,
  },
  supportsReasoning: {
    type: Function,
    required: true,
  },
  formatContextLimit: {
    type: Function,
    required: true,
  },
  testingProviders: {
    type: Array,
    default: () => [],
  },
  tm: {
    type: Function,
    required: true,
  },
});

const emit = defineEmits([
  "update:modelSearch",
  "fetch-models",
  "open-manual-model",
  "open-provider-edit",
  "toggle-provider-enable",
  "test-provider",
  "delete-provider",
  "add-model-provider",
]);

const modelSearchProxy = computed({
  get: () => props.modelSearch,
  set: (val) => emit("update:modelSearch", normalizeTextInput(val)),
});

const isProviderTesting = (providerId) =>
  props.testingProviders.includes(providerId);
</script>

<style scoped>
.provider-models-panel {
  display: grid;
  gap: 14px;
}

.provider-models-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.provider-models-title-wrap {
  min-width: 0;
}

.provider-models-title {
  margin: 0;
  font-size: 18px;
  line-height: 1.3;
  font-weight: 650;
}

.provider-models-subtitle {
  display: block;
  margin-top: 6px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 12px;
}

.provider-models-search {
  max-width: 240px;
}

.provider-models-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.provider-models-list {
  max-height: 520px;
  overflow-y: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 14px;
  background: rgb(var(--v-theme-surface));
  font-family:
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    Roboto,
    Oxygen,
    Ubuntu,
    Cantarell,
    "Open Sans",
    "Helvetica Neue",
    sans-serif;
}

.provider-compact-item {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.provider-models-list :deep(.v-list-item:last-child) {
  border-bottom: 0;
}

.provider-model-subtitle {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-family:
    ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
    "Courier New", monospace;
}

.cursor-pointer {
  cursor: pointer;
}

@media (max-width: 900px) {
  .provider-models-head {
    align-items: stretch;
  }

  .provider-models-search {
    max-width: none;
    width: 100%;
  }

  .provider-models-actions {
    margin-left: 0;
    width: 100%;
  }
}
</style>
