<template>
  <div class="template-list-editor">
    <div class="top-bar d-flex align-center justify-end mb-3">
      <v-menu transition="fade-transition">
        <template #activator="{ props: menuProps }">
          <v-btn
            color="primary"
            variant="tonal"
            size="small"
            v-bind="menuProps"
            prepend-icon="mdi-plus"
          >
            {{ addButtonText }}
          </v-btn>
        </template>
        <v-list density="compact">
          <v-list-item
            v-for="option in templateOptions"
            :key="option.value"
            @click="addEntry(option.value)"
          >
            <v-list-item-title>{{ option.label }}</v-list-item-title>
            <v-list-item-subtitle v-if="option.hint">{{ option.hint }}</v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-menu>
    </div>

    <v-alert
      v-if="!modelValue || modelValue.length === 0"
      type="info"
      variant="tonal"
      density="compact"
      class="mb-3"
    >
      {{ emptyHintText }}
    </v-alert>

    <v-card
      v-for="(entry, entryIndex) in modelValue"
      :key="entryIndex"
      variant="outlined"
      class="mb-3"
    >
      <v-card-title 
        class="d-flex align-center justify-space-between entry-header"
        @click="toggleEntry(entryIndex)"
      >
        <div class="d-flex align-center ga-2">
          <v-btn
            icon
            size="small"
            variant="text"
            :title="expandedEntries[entryIndex] ? (t('core.common.collapse') || '收起') : (t('core.common.expand') || '展开')"
          >
            <v-icon>{{ expandedEntries[entryIndex] ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
          </v-btn>
          <div class="d-flex flex-column">
            <v-list-item-title class="property-name">{{ templateLabel(entry.__template_key) }}</v-list-item-title>
            <v-list-item-subtitle class="property-hint" v-if="getTemplate(entry)?.hint || getTemplate(entry)?.description">
              {{ getTemplate(entry)?.hint || getTemplate(entry)?.description }}
            </v-list-item-subtitle>
          </div>
        </div>
        <div class="d-flex align-center ga-1">
          <v-btn icon size="small" variant="text" color="error" @click.stop="removeEntry(entryIndex)">
            <v-icon>mdi-delete</v-icon>
          </v-btn>
        </div>
      </v-card-title>
      <v-expand-transition>
        <v-card-text v-show="expandedEntries[entryIndex]" class="px-0 py-1">
          <div v-if="!getTemplate(entry)" class="px-4 py-2">
            <v-alert type="error" variant="tonal" density="compact">{{ t('core.common.templateList.missingTemplate') || '找不到对应模板，请删除后重新添加。' }}</v-alert>
          </div>
          <div v-else class="template-entry-body">
            <template v-for="(itemMeta, itemKey, metaIndex) in getTemplate(entry).items" :key="itemKey">
              <!-- Nested Object -->
              <div
                v-if="itemMeta?.type === 'object' && !itemMeta?.invisible && shouldShowItem(itemMeta, entry)"
                class="nested-container mx-4"
              >
                <div class="config-section mb-2">
                  <v-list-item-title class="config-title">
                    {{ itemMeta?.description || itemKey }}
                  </v-list-item-title>
                  <v-list-item-subtitle class="config-hint" v-if="itemMeta?.hint">
                    {{ itemMeta.hint }}
                  </v-list-item-subtitle>
                </div>
                <div v-for="(childMeta, childKey, childIndex) in itemMeta.items" :key="childKey">
                  <template v-if="!childMeta?.invisible && shouldShowItem(childMeta, entry)">
                    <v-row class="config-row">
                      <v-col cols="12" sm="6" class="property-info">
                        <v-list-item density="compact">
                          <v-list-item-title class="property-name">
                            {{ childMeta?.description || childKey }}
                          </v-list-item-title>
                          <v-list-item-subtitle class="property-hint">
                            {{ childMeta?.hint }}
                          </v-list-item-subtitle>
                        </v-list-item>
                      </v-col>
                      <v-col cols="12" sm="6" class="config-input">
                        <div class="w-100">
                          <template v-if="childMeta?._special === 'select_provider'">
                            <ProviderSelector v-model="entry[itemKey][childKey]" :provider-type="'chat_completion'" />
                          </template>
                          <template v-else-if="childMeta?._special === 'select_provider_stt'">
                            <ProviderSelector v-model="entry[itemKey][childKey]" :provider-type="'speech_to_text'" />
                          </template>
                          <template v-else-if="childMeta?._special === 'select_provider_tts'">
                            <ProviderSelector v-model="entry[itemKey][childKey]" :provider-type="'text_to_speech'" />
                          </template>
                          <template v-else-if="childMeta?._special === 'select_persona'">
                            <PersonaSelector v-model="entry[itemKey][childKey]" />
                          </template>
                          <template v-else-if="childMeta?._special === 'select_knowledgebase'">
                            <KnowledgeBaseSelector v-model="entry[itemKey][childKey]" />
                          </template>
                          <div
                            v-else-if="childMeta?.type === 'list' && childMeta?.options && childMeta?.render_type === 'checkbox'"
                            class="d-flex flex-wrap gap-20"
                          >
                            <v-checkbox
                              v-for="(option, optionIndex) in childMeta.options"
                              :key="optionIndex"
                              v-model="entry[itemKey][childKey]"
                              :label="childMeta.labels ? childMeta.labels[optionIndex] : option"
                              :value="option"
                              class="mr-2"
                              color="primary"
                              hide-details
                            ></v-checkbox>
                          </div>
                          <v-combobox
                            v-else-if="childMeta?.type === 'list' && childMeta?.options"
                            v-model="entry[itemKey][childKey]"
                            :items="childMeta.options"
                            :disabled="childMeta?.readonly"
                            density="compact"
                            variant="outlined"
                            class="config-field"
                            hide-details
                            chips
                            multiple
                          ></v-combobox>
                          <v-select
                            v-else-if="childMeta?.options"
                            v-model="entry[itemKey][childKey]"
                            :items="childMeta.options"
                            :disabled="childMeta?.readonly"
                            density="compact"
                            variant="outlined"
                            class="config-field"
                            hide-details
                          ></v-select>
                          <div v-else-if="childMeta?.editor_mode" class="editor-container">
                            <VueMonacoEditor
                              :theme="childMeta?.editor_theme || 'vs-light'"
                              :language="childMeta?.editor_language || 'json'"
                              style="min-height: 100px; flex-grow: 1; border: 1px solid rgba(0, 0, 0, 0.1);"
                              v-model:value="entry[itemKey][childKey]"
                            >
                            </VueMonacoEditor>
                          </div>
                          <v-text-field
                            v-else-if="childMeta?.type === 'string'"
                            v-model="entry[itemKey][childKey]"
                            density="compact"
                            variant="outlined"
                            class="config-field"
                            hide-details
                          ></v-text-field>
                          <div
                            v-else-if="childMeta?.type === 'int' || childMeta?.type === 'float'"
                            class="d-flex align-center gap-3"
                          >
                            <v-slider
                              v-if="childMeta?.slider"
                              v-model.number="entry[itemKey][childKey]"
                              :min="childMeta?.slider?.min ?? 0"
                              :max="childMeta?.slider?.max ?? 100"
                              :step="childMeta?.slider?.step ?? 1"
                              color="primary"
                              density="compact"
                              hide-details
                              class="flex-grow-1"
                            ></v-slider>
                            <v-text-field
                              v-model.number="entry[itemKey][childKey]"
                              density="compact"
                              variant="outlined"
                              class="config-field"
                              type="number"
                              hide-details
                              style="max-width: 140px;"
                            ></v-text-field>
                          </div>
                          <v-textarea
                            v-else-if="childMeta?.type === 'text'"
                            v-model="entry[itemKey][childKey]"
                            variant="outlined"
                            rows="3"
                            class="config-field"
                            hide-details
                          ></v-textarea>
                          <v-switch
                            v-else-if="childMeta?.type === 'bool'"
                            v-model="entry[itemKey][childKey]"
                            color="primary"
                            inset
                            density="compact"
                            hide-details
                          ></v-switch>
                          <ListConfigItem
                            v-else-if="childMeta?.type === 'list'"
                            v-model="entry[itemKey][childKey]"
                            class="config-field"
                          />
                          <ObjectEditor
                            v-else-if="childMeta?.type === 'dict'"
                            v-model="entry[itemKey][childKey]"
                            class="config-field"
                          />
                          <v-text-field
                            v-else
                            v-model="entry[itemKey][childKey]"
                            density="compact"
                            variant="outlined"
                            class="config-field"
                            hide-details
                          ></v-text-field>
                        </div>
                      </v-col>
                    </v-row>
                    <v-divider
                      v-if="hasVisibleItemsAfter(Object.entries(itemMeta.items), childIndex, entry)"
                      class="config-divider"
                    ></v-divider>
                  </template>
                </div>
              </div>

              <!-- Regular Property -->
              <template v-else-if="!itemMeta?.invisible && shouldShowItem(itemMeta, entry)">
                <v-row class="config-row">
                  <v-col cols="12" sm="6" class="property-info">
                    <v-list-item density="compact">
                      <v-list-item-title class="property-name">
                        <span v-if="itemMeta?.description">{{ itemMeta?.description }} <span class="property-key">({{ itemKey }})</span></span>
                        <span v-else>{{ itemKey }}</span>
                      </v-list-item-title>
                      <v-list-item-subtitle class="property-hint">
                        {{ itemMeta?.hint }}
                      </v-list-item-subtitle>
                    </v-list-item>
                  </v-col>
                  <v-col cols="12" sm="6" class="config-input">
                    <div class="w-100">
                      <template v-if="itemMeta?._special === 'select_provider'">
                        <ProviderSelector v-model="entry[itemKey]" :provider-type="'chat_completion'" />
                      </template>
                      <template v-else-if="itemMeta?._special === 'select_provider_stt'">
                        <ProviderSelector v-model="entry[itemKey]" :provider-type="'speech_to_text'" />
                      </template>
                      <template v-else-if="itemMeta?._special === 'select_provider_tts'">
                        <ProviderSelector v-model="entry[itemKey]" :provider-type="'text_to_speech'" />
                      </template>
                      <template v-else-if="itemMeta?._special === 'select_persona'">
                        <PersonaSelector v-model="entry[itemKey]" />
                      </template>
                      <template v-else-if="itemMeta?._special === 'select_knowledgebase'">
                        <KnowledgeBaseSelector v-model="entry[itemKey]" />
                      </template>

                      <div
                        v-else-if="itemMeta?.type === 'list' && itemMeta?.options && itemMeta?.render_type === 'checkbox'"
                        class="d-flex flex-wrap gap-20"
                      >
                        <v-checkbox
                          v-for="(option, optionIndex) in itemMeta.options"
                          :key="optionIndex"
                          v-model="entry[itemKey]"
                          :label="itemMeta.labels ? itemMeta.labels[optionIndex] : option"
                          :value="option"
                          class="mr-2"
                          color="primary"
                          hide-details
                        ></v-checkbox>
                      </div>
                      <v-combobox
                        v-else-if="itemMeta?.type === 'list' && itemMeta?.options"
                        v-model="entry[itemKey]"
                        :items="itemMeta.options"
                        :disabled="itemMeta?.readonly"
                        density="compact"
                        variant="outlined"
                        class="config-field"
                        hide-details
                        chips
                        multiple
                      ></v-combobox>
                      <v-select
                        v-else-if="itemMeta?.options"
                        v-model="entry[itemKey]"
                        :items="itemMeta.options"
                        :disabled="itemMeta?.readonly"
                        density="compact"
                        variant="outlined"
                        class="config-field"
                        hide-details
                      ></v-select>
                      <div v-else-if="itemMeta?.editor_mode" class="editor-container">
                        <VueMonacoEditor
                          :theme="itemMeta?.editor_theme || 'vs-light'"
                          :language="itemMeta?.editor_language || 'json'"
                          style="min-height: 100px; flex-grow: 1; border: 1px solid rgba(0, 0, 0, 0.1);"
                          v-model:value="entry[itemKey]"
                        >
                        </VueMonacoEditor>
                      </div>
                      <v-text-field
                        v-else-if="itemMeta?.type === 'string'"
                        v-model="entry[itemKey]"
                        density="compact"
                        variant="outlined"
                        class="config-field"
                        hide-details
                      ></v-text-field>
                      <div
                        v-else-if="itemMeta?.type === 'int' || itemMeta?.type === 'float'"
                        class="d-flex align-center gap-3"
                      >
                        <v-slider
                          v-if="itemMeta?.slider"
                          v-model.number="entry[itemKey]"
                          :min="itemMeta?.slider?.min ?? 0"
                          :max="itemMeta?.slider?.max ?? 100"
                          :step="itemMeta?.slider?.step ?? 1"
                          color="primary"
                          density="compact"
                          hide-details
                          class="flex-grow-1"
                        ></v-slider>
                        <v-text-field
                          v-model.number="entry[itemKey]"
                          density="compact"
                          variant="outlined"
                          class="config-field"
                          type="number"
                          hide-details
                          style="max-width: 140px;"
                        ></v-text-field>
                      </div>
                      <v-textarea
                        v-else-if="itemMeta?.type === 'text'"
                        v-model="entry[itemKey]"
                        variant="outlined"
                        rows="3"
                        class="config-field"
                        hide-details
                      ></v-textarea>
                      <v-switch
                        v-else-if="itemMeta?.type === 'bool'"
                        v-model="entry[itemKey]"
                        color="primary"
                        inset
                        density="compact"
                        hide-details
                      ></v-switch>
                      <ListConfigItem
                        v-else-if="itemMeta?.type === 'list'"
                        v-model="entry[itemKey]"
                        class="config-field"
                      />
                      <ObjectEditor
                        v-else-if="itemMeta?.type === 'dict'"
                        v-model="entry[itemKey]"
                        class="config-field"
                      />
                      <v-text-field
                        v-else
                        v-model="entry[itemKey]"
                        density="compact"
                        variant="outlined"
                        class="config-field"
                        hide-details
                      ></v-text-field>
                    </div>
                  </v-col>
                </v-row>
                <v-divider
                  v-if="hasVisibleItemsAfter(Object.entries(getTemplate(entry).items), metaIndex, entry)"
                  class="config-divider"
                ></v-divider>
              </template>
            </template>
          </div>
        </v-card-text>
      </v-expand-transition>
    </v-card>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import ListConfigItem from './ListConfigItem.vue'
import ObjectEditor from './ObjectEditor.vue'
import ProviderSelector from './ProviderSelector.vue'
import PersonaSelector from './PersonaSelector.vue'
import KnowledgeBaseSelector from './KnowledgeBaseSelector.vue'
import { useI18n } from '@/i18n/composables'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  templates: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()

const expandedEntries = ref({})

const safeText = (val, fallback) => (val && typeof val === 'string' ? val : fallback)
const addButtonText = computed(() => safeText(t('core.common.templateList.addEntry'), '添加条目'))
const emptyHintText = computed(() => safeText(t('core.common.templateList.empty'), '暂无条目，请先选择模板并添加。'))
const defaultValueMap = {
  int: 0,
  float: 0.0,
  bool: false,
  string: '',
  text: '',
  list: [],
  object: {},
  template_list: []
}

const templateOptions = computed(() => {
  return Object.entries(props.templates || {}).map(([value, meta]) => ({
    label: meta?.name || value,
    value,
    hint: meta?.hint || meta?.description || ''
  }))
})

function templateLabel(key) {
  if (!key) return t('core.common.templateList.unknownTemplate') || '未指定模板'
  return props.templates?.[key]?.name || key
}

function buildDefaults(itemsMeta = {}) {
  const result = {}
  for (const [k, meta] of Object.entries(itemsMeta)) {
    if (!meta || !meta.type) continue
    const fallback = Object.prototype.hasOwnProperty.call(meta, 'default')
      ? meta.default
      : defaultValueMap[meta.type]

    if (meta.type === 'object') {
      result[k] = buildDefaults(meta.items || {})
    } else {
      result[k] = fallback
    }
  }
  return result
}

function applyDefaults(target, itemsMeta = {}) {
  for (const [k, meta] of Object.entries(itemsMeta)) {
    if (!meta || !meta.type) continue
    const hasDefault = Object.prototype.hasOwnProperty.call(meta, 'default')
    const fallback = hasDefault ? meta.default : defaultValueMap[meta.type]

    if (meta.type === 'object') {
      if (!target[k] || typeof target[k] !== 'object') {
        target[k] = buildDefaults(meta.items || {})
      } else {
        applyDefaults(target[k], meta.items || {})
      }
    } else if (!(k in target)) {
      target[k] = fallback
    }
  }
}

function ensureEntryDefaults() {
  if (!Array.isArray(props.modelValue)) return
  props.modelValue.forEach((entry, idx) => {
    const template = getTemplate(entry)
    if (!template || !template.items) return
    applyDefaults(entry, template.items)
    if (!Object.prototype.hasOwnProperty.call(entry, '__template_key')) {
      entry.__template_key = ''
    }
    if (!(idx in expandedEntries.value)) {
      expandedEntries.value[idx] = false
    }
  })
}

watch(
  () => props.modelValue,
  () => ensureEntryDefaults(),
  { immediate: true, deep: true }
)

function addEntry(templateKey) {
  if (!templateKey) return
  const template = props.templates?.[templateKey]
  if (!template) return
  const newEntry = {
    __template_key: templateKey,
    ...buildDefaults(template.items || {})
  }
  emit('update:modelValue', [...(props.modelValue || []), newEntry])
  expandedEntries.value[props.modelValue.length] = true
}

function removeEntry(index) {
  const next = [...(props.modelValue || [])]
  next.splice(index, 1)
  const rebuilt = {}
  next.forEach((_, idx) => {
    const sourceIdx = idx >= index ? idx + 1 : idx
    rebuilt[idx] = expandedEntries.value[sourceIdx] ?? false
  })
  expandedEntries.value = rebuilt
  emit('update:modelValue', next)
}

function toggleEntry(index) {
  expandedEntries.value[index] = !expandedEntries.value[index]
}

function getTemplate(entry) {
  if (!entry) return null
  const key = entry.__template_key
  if (!key) return null
  return props.templates?.[key] || null
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

function shouldShowItem(itemMeta, entry) {
  if (!itemMeta?.condition) {
    return true
  }
  for (const [conditionKey, expectedValue] of Object.entries(itemMeta.condition)) {
    const actualValue = getValueBySelector(entry, conditionKey)
    if (actualValue !== expectedValue) {
      return false
    }
  }
  return true
}

function hasVisibleItemsAfter(entries, currentIndex, entry) {
  for (let i = currentIndex + 1; i < entries.length; i++) {
    const [k, meta] = entries[i]
    if (!meta?.invisible && shouldShowItem(meta, entry)) {
      return true
    }
  }
  return false
}
</script>

<style scoped>
.template-list-editor {
  width: 100%;
}

.entry-header {
  cursor: pointer;
  user-select: none;
}

.entry-header:hover {
  background-color: rgba(0, 0, 0, 0.02);
}

.top-bar {
  margin-bottom: 8px;
}

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

.template-entry-body {
  margin-top: 4px;
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

.property-key {
  font-size: 0.85em;
  opacity: 0.7;
  font-weight: normal;
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

.nested-container {
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  padding: 12px;
  margin: 12px 0;
  background-color: rgba(0, 0, 0, 0.02);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.editor-container {
  position: relative;
  display: flex;
  width: 100%;
}
</style>
