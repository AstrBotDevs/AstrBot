<script setup>
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { ref, computed } from 'vue'
import ConfigItemRenderer from './ConfigItemRenderer.vue'
import TemplateListEditor from './TemplateListEditor.vue'
import { useI18n } from '@/i18n/composables'
import axios from 'axios'
import { useToast } from '@/utils/toast'

const props = defineProps({
  metadata: {
    type: Object,
    required: true
  },
  iterable: {
    type: Object,
    required: true
  },
  metadataKey: {
    type: String,
    required: true
  },
  isEditing: {
    type: Boolean,
    default: false
  }
})

const { t } = useI18n()

const filteredIterable = computed(() => {
  if (!props.iterable) return {}
  const { hint, ...rest } = props.iterable
  return rest
})

const dialog = ref(false)
const currentEditingKey = ref('')
const currentEditingLanguage = ref('json')
const currentEditingTheme = ref('vs-light')
let currentEditingKeyIterable = null
const loadingEmbeddingDim = ref(false)

function openEditorDialog(key, value, theme, language) {
  currentEditingKey.value = key
  currentEditingLanguage.value = language || 'json'
  currentEditingTheme.value = theme || 'vs-light'
  currentEditingKeyIterable = value
  dialog.value = true
}


function saveEditedContent() {
  dialog.value = false
}

async function getEmbeddingDimensions(providerConfig) {
  if (loadingEmbeddingDim.value) return
  
  loadingEmbeddingDim.value = true
  try {
    const response = await axios.post('/api/config/provider/get_embedding_dim', {
      provider_config: providerConfig
    })
    
    if (response.data.status != "error" && response.data.data?.embedding_dimensions) {
      console.log(response.data.data.embedding_dimensions)
      providerConfig.embedding_dimensions = response.data.data.embedding_dimensions
      useToast().success("获取成功: " + response.data.data.embedding_dimensions)
    } else {
      useToast().error(response.data.message)
    }
  } catch (error) {
    console.error('Error getting embedding dimensions:', error)
  } finally {
    loadingEmbeddingDim.value = false
  }
}

function getValueBySelector(obj, selector) {
  const keys = selector.split('.')
  let current = obj
  for (const key of keys) {
    if (current && typeof current === 'object' && key in current) {
      current = current[key]
    } else {
      return undefined
    }
  }
  return current
}

function shouldShowItem(itemMeta, itemKey) {
  if (!itemMeta?.condition) {
    return true
  }
  for (const [conditionKey, expectedValue] of Object.entries(itemMeta.condition)) {
    const actualValue = getValueBySelector(props.iterable, conditionKey)
    if (actualValue !== expectedValue) {
      return false
    }
  }
  return true
}

function hasVisibleItemsAfter(items, currentIndex) {
  const itemEntries = Object.entries(items)

  // 检查当前索引之后是否还有可见的配置项
  for (let i = currentIndex + 1; i < itemEntries.length; i++) {
    const [itemKey, itemValue] = itemEntries[i]
    const itemMeta = props.metadata[props.metadataKey].items[itemKey]
    if (!itemMeta?.invisible && shouldShowItem(itemMeta, itemKey)) {
      return true
    }
  }

  return false
}
</script>

<template>
  <div class="config-section" v-if="iterable && metadata[metadataKey]?.type === 'object'">
    <v-list-item-title class="config-title">
      {{ metadata[metadataKey]?.description }} <span class="metadata-key">({{ metadataKey }})</span>
    </v-list-item-title>
    <v-list-item-subtitle class="config-hint">
      <span v-if="metadata[metadataKey]?.obvious_hint && metadata[metadataKey]?.hint" class="important-hint">‼️</span>
      {{ metadata[metadataKey]?.hint }}
    </v-list-item-subtitle>
  </div>

  <v-card-text class="px-0 py-1">
    <!-- Object Type Configuration -->
    <div v-if="metadata[metadataKey]?.type === 'object' || metadata[metadataKey]?.config_template" class="object-config">
      <!-- Provider-level hint -->
      <v-alert
        v-if="iterable.hint && !isEditing"
        type="info"
        variant="tonal"
        class="mb-4"
        border="start"
        density="compact"
      >
        {{ iterable.hint }}
      </v-alert>

      <div v-for="(val, key, index) in filteredIterable" :key="key" class="config-item">
        <!-- Nested Object -->
        <div v-if="metadata[metadataKey].items[key]?.type === 'object'" class="nested-object">
          <div v-if="metadata[metadataKey].items[key] && !metadata[metadataKey].items[key]?.invisible && shouldShowItem(metadata[metadataKey].items[key], key)" class="nested-container">
            <v-expand-transition>
              <AstrBotConfig :metadata="metadata[metadataKey].items" :iterable="iterable[key]" :metadataKey="key">
              </AstrBotConfig>
            </v-expand-transition>
          </div>
        </div>

        <!-- Template List -->
        <div v-else-if="metadata[metadataKey].items[key]?.type === 'template_list'" class="nested-object w-100">
          <div v-if="!metadata[metadataKey].items[key]?.invisible && shouldShowItem(metadata[metadataKey].items[key], key)" class="nested-container">
            <div class="config-section mb-2">
              <v-list-item-title class="config-title">
                <span v-if="metadata[metadataKey].items[key]?.description">
                  {{ metadata[metadataKey].items[key]?.description }}
                  <span class="property-key">({{ key }})</span>
                </span>
                <span v-else>{{ key }}</span>
              </v-list-item-title>
              <v-list-item-subtitle class="config-hint">
                <span v-if="metadata[metadataKey].items[key]?.obvious_hint && metadata[metadataKey].items[key]?.hint" class="important-hint">‼️</span>
                {{ metadata[metadataKey].items[key]?.hint }}
              </v-list-item-subtitle>
            </div>
            <TemplateListEditor
              v-model="iterable[key]"
              :templates="metadata[metadataKey].items[key]?.templates || {}"
              class="config-field"
            />
          </div>
        </div>

        <!-- Regular Property -->
        <template v-else>
          <v-row v-if="!metadata[metadataKey].items[key]?.invisible && shouldShowItem(metadata[metadataKey].items[key], key)" class="config-row">
            <v-col cols="12" sm="6" class="property-info">
              <v-list-item density="compact">
                <v-list-item-title class="property-name">
                  <span v-if="metadata[metadataKey].items[key]?.description">
                    {{ metadata[metadataKey].items[key]?.description }}
                    <span class="property-key">({{ key }})</span>
                  </span>
                  <span v-else>{{ key }}</span>
                </v-list-item-title>

                <v-list-item-subtitle class="property-hint">
                  <span v-if="metadata[metadataKey].items[key]?.obvious_hint && metadata[metadataKey].items[key]?.hint"
                        class="important-hint">‼️</span>
                  {{ metadata[metadataKey].items[key]?.hint }}
                </v-list-item-subtitle>
              </v-list-item>
            </v-col>

            <v-col cols="12" sm="6" class="config-input">
              <ConfigItemRenderer
                v-model="iterable[key]"
                :item-meta="metadata[metadataKey].items[key] || null"
                :loading="loadingEmbeddingDim"
                :show-fullscreen-btn="!!metadata[metadataKey].items[key]?.editor_mode"
                @get-embedding-dim="getEmbeddingDimensions(iterable)"
                @open-fullscreen="openEditorDialog(key, iterable, metadata[metadataKey].items[key]?.editor_theme, metadata[metadataKey].items[key]?.editor_language)"
              />
            </v-col>
          </v-row>

          <v-divider
            v-if="hasVisibleItemsAfter(filteredIterable, index) && !metadata[metadataKey].items[key]?.invisible && shouldShowItem(metadata[metadataKey].items[key], key)"
            class="config-divider"
          ></v-divider>
        </template>
      </div>
    </div>

    <!-- Simple Value Configuration -->
    <div v-else class="simple-config">
      <v-row class="config-row">
        <v-col cols="12" sm="7" class="property-info">
          <v-list-item density="compact">
            <v-list-item-title class="property-name">
              {{ metadata[metadataKey]?.description }}
              <span class="property-key">({{ metadataKey }})</span>
            </v-list-item-title>

            <v-list-item-subtitle class="property-hint">
              <span v-if="metadata[metadataKey]?.obvious_hint && metadata[metadataKey]?.hint" class="important-hint">‼️</span>
              {{ metadata[metadataKey]?.hint }}
            </v-list-item-subtitle>
          </v-list-item>
        </v-col>

        <v-col cols="12" sm="5" class="config-input">
          <TemplateListEditor
            v-if="metadata[metadataKey]?.type === 'template_list' && !metadata[metadataKey]?.invisible"
            v-model="iterable[metadataKey]"
            :templates="metadata[metadataKey]?.templates || {}"
            class="config-field"
          />
          <ConfigItemRenderer
            v-else
            v-model="iterable[metadataKey]"
            :item-meta="metadata[metadataKey]"
          />
        </v-col>
      </v-row>

      <v-divider class="my-2 config-divider"></v-divider>
    </div>
  </v-card-text>

  <!-- Full Screen Editor Dialog -->
  <v-dialog v-model="dialog" fullscreen transition="dialog-bottom-transition" scrollable>
    <v-card>
      <v-toolbar color="primary" dark>
        <v-btn icon @click="dialog = false">
          <v-icon>mdi-close</v-icon>
        </v-btn>
        <v-toolbar-title>{{ t('core.common.editor.editingTitle') }} - {{ currentEditingKey }}</v-toolbar-title>
        <v-spacer></v-spacer>
        <v-toolbar-items>
          <v-btn variant="text" @click="saveEditedContent">{{ t('core.common.save') }}</v-btn>
        </v-toolbar-items>
      </v-toolbar>
      <v-card-text class="pa-0">
        <VueMonacoEditor
          :theme="currentEditingTheme"
          :language="currentEditingLanguage"
          style="height: calc(100vh - 64px);"
          v-model:value="currentEditingKeyIterable[currentEditingKey]"
        >
        </VueMonacoEditor>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>



<style scoped>
.config-section {
  margin-bottom: 12px;
}

.config-title {
  font-weight: 600;
  font-size: 1rem;
  color: var(--v-theme-primaryText);
}

.config-hint {
  font-size: 0.75rem;
  color: var(--v-theme-secondaryText);
  margin-top: 2px;
}

.metadata-key, .property-key {
  font-size: 0.85em;
  opacity: 0.7;
  font-weight: normal;
  display: none;
}

.important-hint {
  opacity: 1;
  margin-right: 4px;
}

.object-config, .simple-config {
  width: 100%;
}

.config-item {
  margin-bottom: 2px;
}

.nested-object {
  padding-left: 16px;
}

.nested-container {
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  padding: 12px;
  margin: 12px 0;
  background-color: rgba(0, 0, 0, 0.02);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.config-row {
  margin: 0;
  align-items: center;
  padding: 4px 8px;
  border-radius: 4px;
}

.config-row:hover {
  background-color: rgba(0, 0, 0, 0.03);
}

.property-info {
  padding: 0;
}

.property-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--v-theme-primaryText);
}

.property-hint {
  font-size: 0.75rem;
  color: var(--v-theme-secondaryText);
  margin-top: 2px;
}

.type-indicator {
  display: flex;
  justify-content: center;
}

.config-input {
  padding: 4px 8px;
}

.config-field {
  margin-bottom: 0;
}

.config-divider {
  border-color: rgba(0, 0, 0, 0.05);
  margin: 0px 16px;
}

.editor-container {
  position: relative;
  display: flex;
  width: 100%;
}

.editor-fullscreen-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 10;
  background-color: rgba(0, 0, 0, 0.3);
  border-radius: 4px;
}

.editor-fullscreen-btn:hover {
  background-color: rgba(0, 0, 0, 0.5);
}

@media (max-width: 600px) {
  .nested-object {
    padding-left: 8px;
  }

  .config-row {
    padding: 8px 0;
  }

  .property-info, .type-indicator, .config-input {
    padding: 4px;
  }
}
</style>
