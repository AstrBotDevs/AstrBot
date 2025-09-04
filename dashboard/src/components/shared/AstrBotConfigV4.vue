<script setup>
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { ref, computed } from 'vue'
import ListConfigItem from './ListConfigItem.vue'
import ProviderSelector from './ProviderSelector.vue'
import PersonaSelector from './PersonaSelector.vue'
import KnowledgeBaseSelector from './KnowledgeBaseSelector.vue'
import PluginSetSelector from './PluginSetSelector.vue'
import T2ITemplateEditor from './T2ITemplateEditor.vue'
import { useI18n } from '@/i18n/composables'


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
  }
})

const { t } = useI18n()

const dialog = ref(false)
const currentEditingKey = ref('')
const currentEditingLanguage = ref('json')
const currentEditingTheme = ref('vs-light')
let currentEditingKeyIterable = null

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

function setValueBySelector(obj, selector, value) {
  const keys = selector.split('.')
  let current = obj

  // 创建嵌套对象路径
  for (let i = 0; i < keys.length - 1; i++) {
    const key = keys[i]
    if (!current[key] || typeof current[key] !== 'object') {
      current[key] = {}
    }
    current = current[key]
  }

  // 设置最终值
  current[keys[keys.length - 1]] = value
}

// 创建一个计算属性来处理 JSON selector 的获取和设置
function createSelectorModel(selector) {
  return computed({
    get() {
      return getValueBySelector(props.iterable, selector)
    },
    set(value) {
      setValueBySelector(props.iterable, selector, value)
    }
  })
}

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
    const [itemKey, itemMeta] = itemEntries[i]
    if (shouldShowItem(itemMeta, itemKey)) {
      return true
    }
  }
  
  return false
}
</script>

<template>


  <v-card style="margin-bottom: 16px; padding-bottom: 8px; background-color: rgb(var(--v-theme-background));" rounded="md" variant="outlined">
    <v-card-text class="config-section" v-if="metadata[metadataKey]?.type === 'object'">
      <v-list-item-title class="config-title">
        {{ metadata[metadataKey]?.description }}
      </v-list-item-title>
      <v-list-item-subtitle class="config-hint">
        <span v-if="metadata[metadataKey]?.obvious_hint && metadata[metadataKey]?.hint" class="important-hint">‼️</span>
        {{ metadata[metadataKey]?.hint }}
      </v-list-item-subtitle>
    </v-card-text>

    <!-- Object Type Configuration with JSON Selector Support -->
    <div v-if="metadata[metadataKey]?.type === 'object'" class="object-config">
      <div v-for="(itemMeta, itemKey, index) in metadata[metadataKey].items" :key="itemKey" class="config-item">
        <!-- Check if itemKey is a JSON selector -->
        <template v-if="shouldShowItem(itemMeta, itemKey)">
          <!-- JSON Selector Property -->
          <v-row v-if="!itemMeta?.invisible" class="config-row">
            <v-col cols="12" sm="6" class="property-info">
              <v-list-item density="compact">
                <v-list-item-title class="property-name">
                  {{ itemMeta?.description || itemKey }}
                  <span class="property-key">({{ itemKey }})</span>
                </v-list-item-title>

                <v-list-item-subtitle class="property-hint">
                  <span v-if="itemMeta?.obvious_hint && itemMeta?.hint" class="important-hint">‼️</span>
                  {{ itemMeta?.hint }}
                </v-list-item-subtitle>
              </v-list-item>
            </v-col>
            <v-col cols="12" sm="6" class="config-input">
              <div class="w-100" v-if="!itemMeta?._special">
                <!-- Select input for JSON selector -->
                <v-select v-if="itemMeta?.options" v-model="createSelectorModel(itemKey).value"
                  :items="itemMeta?.options" :disabled="itemMeta?.readonly" density="compact" variant="outlined"
                  class="config-field" hide-details></v-select>

                <!-- Code Editor for JSON selector -->
                <div v-else-if="itemMeta?.editor_mode" class="editor-container">
                  <VueMonacoEditor :theme="itemMeta?.editor_theme || 'vs-light'"
                    :language="itemMeta?.editor_language || 'json'"
                    style="min-height: 100px; flex-grow: 1; border: 1px solid rgba(0, 0, 0, 0.1);"
                    v-model:value="createSelectorModel(itemKey).value">
                  </VueMonacoEditor>
                  <v-btn icon size="small" variant="text" color="primary" class="editor-fullscreen-btn"
                    @click="openEditorDialog(itemKey, iterable, itemMeta?.editor_theme, itemMeta?.editor_language)"
                    :title="t('core.common.editor.fullscreen')">
                    <v-icon>mdi-fullscreen</v-icon>
                  </v-btn>
                </div>

                <!-- String input for JSON selector -->
                <v-text-field v-else-if="itemMeta?.type === 'string'" v-model="createSelectorModel(itemKey).value"
                  density="compact" variant="outlined" class="config-field" hide-details></v-text-field>

                <!-- Numeric input for JSON selector -->
                <v-text-field v-else-if="itemMeta?.type === 'int' || itemMeta?.type === 'float'"
                  v-model="createSelectorModel(itemKey).value" density="compact" variant="outlined" class="config-field"
                  type="number" hide-details></v-text-field>

                <!-- Text area for JSON selector -->
                <v-textarea v-else-if="itemMeta?.type === 'text'" v-model="createSelectorModel(itemKey).value"
                  variant="outlined" rows="3" class="config-field" hide-details></v-textarea>

                <!-- Boolean switch for JSON selector -->
                <v-switch v-else-if="itemMeta?.type === 'bool'" v-model="createSelectorModel(itemKey).value"
                  color="primary" inset density="compact" hide-details style="display: flex; justify-content: end;"></v-switch>

                <!-- List item for JSON selector -->
                <ListConfigItem 
                  v-else-if="itemMeta?.type === 'list'"
                  v-model="createSelectorModel(itemKey).value"
                  button-text="修改"
                  class="config-field"
                />

                <!-- Fallback for JSON selector -->
                <v-text-field v-else v-model="createSelectorModel(itemKey).value" density="compact" variant="outlined"
                  class="config-field" hide-details></v-text-field>
              </div>

              <!-- Special handling for specific metadata types -->
              <div v-else-if="itemMeta?._special === 'select_provider'">
                <ProviderSelector 
                  v-model="createSelectorModel(itemKey).value"
                  :provider-type="'chat_completion'"
                />
              </div>
              <div v-else-if="itemMeta?._special === 'select_provider_stt'">
                <ProviderSelector 
                  v-model="createSelectorModel(itemKey).value"
                  :provider-type="'speech_to_text'"
                />
              </div>
              <div v-else-if="itemMeta?._special === 'select_provider_tts'">
                <ProviderSelector 
                  v-model="createSelectorModel(itemKey).value"
                  :provider-type="'text_to_speech'"
                />
              </div>
              <div v-else-if="itemMeta?._special === 'provider_pool'">
                <ProviderSelector 
                  v-model="createSelectorModel(itemKey).value"
                  :provider-type="'chat_completion'"
                  button-text="选择提供商池..."
                />
              </div>
              <div v-else-if="itemMeta?._special === 'select_persona'">
                <PersonaSelector 
                  v-model="createSelectorModel(itemKey).value"
                />
              </div>
              <div v-else-if="itemMeta?._special === 'persona_pool'">
                <PersonaSelector 
                  v-model="createSelectorModel(itemKey).value"
                  button-text="选择人格池..."
                />
              </div>
              <div v-else-if="itemMeta?._special === 'select_knowledgebase'">
                <KnowledgeBaseSelector 
                  v-model="createSelectorModel(itemKey).value"
                />
              </div>
              <div v-else-if="itemMeta?._special === 'select_plugin_set'">
                <PluginSetSelector 
                  v-model="createSelectorModel(itemKey).value"
                />
              </div>
              <div v-else-if="itemMeta?._special === 't2i_template'">
                <T2ITemplateEditor />
              </div>
            </v-col>
          </v-row>

          <!-- Plugin Set Selector 全宽显示区域 -->
          <v-row v-if="!itemMeta?.invisible && itemMeta?._special === 'select_plugin_set'" class="plugin-set-display-row">
            <v-col cols="12" class="plugin-set-display">
              <div v-if="createSelectorModel(itemKey).value && createSelectorModel(itemKey).value.length > 0" class="selected-plugins-full-width">
                <div class="plugins-header">
                  <small class="text-grey">已选择的插件：</small>
                </div>
                <div class="d-flex flex-wrap ga-2 mt-2">
                  <v-chip 
                    v-for="plugin in (createSelectorModel(itemKey).value || [])" 
                    :key="plugin" 
                    size="small" 
                    label 
                    color="primary" 
                    variant="outlined"
                  >
                    {{ plugin === '*' ? '所有插件' : plugin }}
                  </v-chip>
                </div>
              </div>
            </v-col>
          </v-row>
        </template>
        <v-divider class="config-divider" v-if="shouldShowItem(itemMeta, itemKey) && hasVisibleItemsAfter(metadata[metadataKey].items, index)"></v-divider>
      </div>

    </div>
  </v-card>

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
        <VueMonacoEditor :theme="currentEditingTheme" :language="currentEditingLanguage"
          style="height: calc(100vh - 64px);" v-model:value="currentEditingKeyIterable[currentEditingKey]">
        </VueMonacoEditor>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>



<style scoped>
.config-section {
  margin-bottom: 4px;
}

.config-title {
  /* font-weight: 600; */
  font-size: 1.3rem;
  color: var(--v-theme-primaryText);
}

.config-hint {
  font-size: 0.75rem;
  color: var(--v-theme-secondaryText);
  margin-top: 2px;
}

.metadata-key,
.property-key {
  font-size: 0.85em;
  opacity: 0.7;
  font-weight: normal;
  display: none;
}

.important-hint {
  opacity: 1;
  margin-right: 4px;
}

.object-config,
.simple-config {
  width: 100%;
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
  padding: 10px 8px;
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
  /* font-weight: 600; */
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
  margin-left: 24px;
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

.plugin-set-display-row {
  margin: 16px;
  margin-top: 0;
}

.plugin-set-display {
  padding: 0 8px;
}

.selected-plugins-full-width {
  background-color: rgba(var(--v-theme-primary), 0.05);
  border: 1px solid rgba(var(--v-theme-primary), 0.1);
  border-radius: 8px;
  padding: 12px;
}

.plugins-header {
  margin-bottom: 4px;
}

@media (max-width: 600px) {
  .nested-object {
    padding-left: 8px;
  }

  .config-row {
    padding: 8px 0;
  }

  .property-info,
  .type-indicator,
  .config-input {
    padding: 4px;
  }
}
</style>
