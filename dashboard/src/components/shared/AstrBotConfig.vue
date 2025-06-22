<script setup>
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { ref } from 'vue'

const dialog = ref(false)
const currentEditingKey = ref('')
const currentEditingLanguage = ref('json')
const currentEditingTheme = ref('vs-light')
let currentEditingKeyIterable = null

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
      <div v-for="(val, key, index) in iterable" :key="key" class="config-item">
        <!-- Nested Object -->
        <div v-if="metadata[metadataKey].items[key]?.type === 'object'" class="nested-object">
          <div v-if="metadata[metadataKey].items[key] && !metadata[metadataKey].items[key]?.invisible" class="nested-container">
            <v-expand-transition>
              <AstrBotConfig :metadata="metadata[metadataKey].items" :iterable="iterable[key]" :metadataKey="key">
              </AstrBotConfig>
            </v-expand-transition>
          </div>
        </div>
        
        <!-- Regular Property -->
        <template v-else>
          <v-row v-if="!metadata[metadataKey].items[key]?.invisible" class="config-row">
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

            <v-col cols="12" sm="1" class="d-flex align-center type-indicator">
              <v-chip v-if="!metadata[metadataKey].items[key]?.invisible" 
                     color="primary" 
                     label 
                     size="x-small" 
                     variant="flat">
                {{ metadata[metadataKey].items[key]?.type || 'string' }}
              </v-chip>
            </v-col>

            <v-col cols="12" sm="5" class="config-input">
              <div v-if="metadata[metadataKey].items[key]" class="w-100">
                <!-- Select input -->
                <v-select
                  v-if="metadata[metadataKey].items[key]?.options && !metadata[metadataKey].items[key]?.invisible"
                  v-model="iterable[key]"
                  :items="metadata[metadataKey].items[key]?.options"
                  :disabled="metadata[metadataKey].items[key]?.readonly"
                  density="compact"
                  variant="outlined"
                  class="config-field"
                  hide-details
                ></v-select>

                <!-- Code Editor with Full Screen Option -->
                <div v-else-if="metadata[metadataKey].items[key]?.editor_mode && !metadata[metadataKey].items[key]?.invisible" class="editor-container">
                  <VueMonacoEditor 
                    :theme="metadata[metadataKey].items[key]?.editor_theme || 'vs-light'" 
                    :language="metadata[metadataKey].items[key]?.editor_language || 'json'"
                    style="min-height: 100px; flex-grow: 1; border: 1px solid rgba(0, 0, 0, 0.1);" 
                    v-model:value="iterable[key]"
                  >
                  </VueMonacoEditor>
                  <v-btn
                    icon
                    size="small"
                    variant="text"
                    color="primary"
                    class="editor-fullscreen-btn"
                    @click="openEditorDialog(key, iterable, metadata[metadataKey].items[key]?.editor_theme, metadata[metadataKey].items[key]?.editor_language)"
                    :title="t('core.common.editor.fullscreen')"
                  >
                    <v-icon>mdi-fullscreen</v-icon>
                  </v-btn>
                </div>
                
                <!-- String input -->
                <v-text-field
                  v-else-if="metadata[metadataKey].items[key]?.type === 'string' && !metadata[metadataKey].items[key]?.invisible"
                  v-model="iterable[key]"
                  density="compact"
                  variant="outlined"
                  class="config-field"
                  hide-details
                ></v-text-field>
                
                <!-- Numeric input -->
                <v-text-field
                  v-else-if="(metadata[metadataKey].items[key]?.type === 'int' || metadata[metadataKey].items[key]?.type === 'float') && !metadata[metadataKey]?.invisible"
                  v-model="iterable[key]"
                  density="compact"
                  variant="outlined"
                  class="config-field"
                  type="number"
                  hide-details
                ></v-text-field>
                
                <!-- Text area -->
                <v-textarea
                  v-else-if="metadata[metadataKey].items[key]?.type === 'text' && !metadata[metadataKey].items[key]?.invisible"
                  v-model="iterable[key]"
                  variant="outlined"
                  rows="3"
                  class="config-field"
                  hide-details
                ></v-textarea>
                
                <!-- Boolean switch -->
                <v-switch
                  v-else-if="metadata[metadataKey].items[key]?.type === 'bool' && !metadata[metadataKey].items[key]?.invisible"
                  v-model="iterable[key]"
                  color="primary"
                  inset
                  density="compact"
                  hide-details
                ></v-switch>
                
                <!-- List item -->
                <ListConfigItem
                  v-else-if="metadata[metadataKey].items[key]?.type === 'list' && !metadata[metadataKey].items[key]?.invisible"
                  :value="iterable[key]"
                  class="config-field"
                />
              </div>
              
              <!-- Fallback for unknown metadata -->
              <div v-else class="w-100">
                <v-text-field 
                  v-model="iterable[key]" 
                  :label="key" 
                  density="compact"
                  variant="outlined"
                  class="config-field"
                  hide-details
                ></v-text-field>
              </div>
            </v-col>
          </v-row>

          <v-divider 
            v-if="index !== Object.keys(iterable).length - 1 && !metadata[metadataKey].items[key]?.invisible"
            class="config-divider"
          ></v-divider>
        </template>
      </div>
    </div>
    
    <!-- Simple Value Configuration -->
    <div v-else class="simple-config">
      <v-row class="config-row">
        <v-col cols="12" sm="6" class="property-info">
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

        <v-col cols="12" sm="1" class="d-flex align-center type-indicator">
          <v-chip v-if="!metadata[metadataKey]?.invisible" 
                 color="primary" 
                 label 
                 size="x-small"
                 variant="flat">
            {{ metadata[metadataKey]?.type }}
          </v-chip>
        </v-col>

        <v-col cols="12" sm="5" class="config-input">
          <div class="w-100">
            <!-- Select input -->
            <v-select
              v-if="metadata[metadataKey]?.options && !metadata[metadataKey]?.invisible"
              v-model="iterable[metadataKey]"
              :items="metadata[metadataKey]?.options"
              :disabled="metadata[metadataKey]?.readonly"
              density="compact"
              variant="outlined"
              class="config-field"
              hide-details
            ></v-select>
            
            <!-- String input -->
            <v-text-field
              v-else-if="metadata[metadataKey]?.type === 'string' && !metadata[metadataKey]?.invisible"
              v-model="iterable[metadataKey]"
              density="compact"
              variant="outlined"
              class="config-field"
              hide-details
            ></v-text-field>
            
            <!-- Numeric input -->
            <v-text-field
              v-else-if="(metadata[metadataKey]?.type === 'int' || metadata[metadataKey]?.type === 'float') && !metadata[metadataKey]?.invisible"
              v-model="iterable[metadataKey]"
              density="compact"
              variant="outlined"
              class="config-field"
              type="number"
              hide-details
            ></v-text-field>
            
            <!-- Text area -->
            <v-textarea
              v-else-if="metadata[metadataKey]?.type === 'text' && !metadata[metadataKey]?.invisible"
              v-model="iterable[metadataKey]"
              variant="outlined"
              auto-grow
              rows="3"
              class="config-field"
              hide-details
            ></v-textarea>
            
            <!-- Boolean switch -->
            <v-switch
              v-else-if="metadata[metadataKey]?.type === 'bool' && !metadata[metadataKey]?.invisible"
              v-model="iterable[metadataKey]"
              color="primary"
              inset
              density="compact"
              hide-details
            ></v-switch>
            
            <!-- List item -->
            <ListConfigItem
              v-else-if="metadata[metadataKey]?.type === 'list' && !metadata[metadataKey]?.invisible"
              :value="iterable[metadataKey]"
              class="config-field"
            />
          </div>
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

<script>
import ListConfigItem from './ListConfigItem.vue';
import { useI18n } from '@/i18n/composables';

export default {
  name: 'AstrBotConfig',
  components: {
    ListConfigItem
  },
  setup() {
    const { t } = useI18n();
    return { t };
  },
  props: {
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
    }
  }
}
</script>

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
  transition: background-color 0.2s;
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
  border-color: rgba(0, 0, 0, 0.1);
  margin: 4px 0;
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