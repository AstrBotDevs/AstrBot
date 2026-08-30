<script setup>
import MarkdownIt from 'markdown-it';
import DOMPurify from 'dompurify';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor';
import '@/utils/monacoLoader';
import { ref, computed } from 'vue';
import ConfigItemRenderer from './ConfigItemRenderer.vue';
import TemplateListEditor from './TemplateListEditor.vue';
import PersonaQuickPreview from './PersonaQuickPreview.vue';
import ConfigDocsLink from './ConfigDocsLink.vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { useConfigTextResolver } from '@/composables/useConfigTextResolver';

const props = defineProps({
  metadata: {
    type: Object,
    required: true,
  },
  iterable: {
    type: Object,
    required: true,
  },
  metadataKey: {
    type: String,
    required: true,
  },
  searchKeyword: {
    type: String,
    default: '',
  },
  pluginName: {
    type: String,
    default: '',
  },
  pluginI18n: {
    type: Object,
    default: () => ({}),
  },
  pathPrefix: {
    type: String,
    default: '',
  },
});

const { t } = useI18n();
const { tm: tmConfig } = useModuleI18n('features/config');
const { translateIfKey, resolveConfigText } = useConfigTextResolver(props);

const hintMarkdown = new MarkdownIt({
  linkify: true,
  breaks: true,
});

const renderHint = (value) => {
  const text = translateIfKey(value);
  if (!text) return '';
  return DOMPurify.sanitize(hintMarkdown.renderInline(text));
};

const dialog = ref(false);
const showCollapsedItems = ref(false);
const currentEditingKey = ref('');
const currentEditingLanguage = ref('json');
const currentEditingTheme = ref('vs-light');
let currentEditingKeyIterable = null;

function getValueBySelector(obj, selector) {
  const keys = selector.split('.');
  let current = obj;
  for (const key of keys) {
    if (current && typeof current === 'object' && key in current) {
      current = current[key];
    } else {
      return undefined;
    }
  }
  return current;
}

function setValueBySelector(obj, selector, value) {
  const keys = selector.split('.');
  let current = obj;

  // 创建嵌套对象路径
  for (let i = 0; i < keys.length - 1; i++) {
    const key = keys[i];
    if (!current[key] || typeof current[key] !== 'object') {
      current[key] = {};
    }
    current = current[key];
  }

  // 设置最终值
  current[keys[keys.length - 1]] = value;
}

// 创建一个计算属性来处理 JSON selector 的获取和设置
function createSelectorModel(selector) {
  return computed({
    get() {
      return getValueBySelector(props.iterable, selector);
    },
    set(value) {
      setValueBySelector(props.iterable, selector, value);
    },
  });
}

function getItemPath(key) {
  return props.pathPrefix ? `${props.pathPrefix}.${key}` : key;
}

function getItemDescription(itemKey, itemMeta) {
  return (
    resolveConfigText(
      getItemPath(itemKey),
      'description',
      itemMeta?.description,
    ) || itemKey
  );
}

function getItemHint(itemKey, itemMeta) {
  return resolveConfigText(getItemPath(itemKey), 'hint', itemMeta?.hint);
}

function openEditorDialog(key, value, theme, language) {
  currentEditingKey.value = key;
  currentEditingLanguage.value = language || 'json';
  currentEditingTheme.value = theme || 'vs-light';
  currentEditingKeyIterable = value;
  dialog.value = true;
}

function saveEditedContent() {
  dialog.value = false;
}

function shouldShowItem(itemMeta, itemKey) {
  if (itemMeta?.condition) {
    for (const [conditionKey, expectedValue] of Object.entries(
      itemMeta.condition,
    )) {
      const actualValue = getValueBySelector(props.iterable, conditionKey);
      if (actualValue !== expectedValue) {
        return false;
      }
    }
  }

  const keyword = String(props.searchKeyword || '')
    .trim()
    .toLowerCase();
  if (!keyword) {
    return true;
  }

  const searchableText = [
    itemKey,
    getItemDescription(itemKey, itemMeta),
    getItemHint(itemKey, itemMeta),
  ]
    .join(' ')
    .toLowerCase();

  return searchableText.includes(keyword);
}

function getVisibleItemEntries(collapsed = false) {
  const sectionItems = props.metadata?.[props.metadataKey]?.items || {};
  return Object.entries(sectionItems).filter(([itemKey, itemMeta]) => {
    const isCollapsed = Boolean(itemMeta?.collapsed);
    return isCollapsed === collapsed && shouldShowItem(itemMeta, itemKey);
  });
}

function hasCollapsedItems() {
  return getVisibleItemEntries(true).length > 0;
}

function hasVisibleEntriesAfter(entries, currentIndex) {
  return currentIndex < entries.length - 1;
}

function areCollapsedItemsVisible() {
  if (!hasCollapsedItems()) {
    return false;
  }
  if (String(props.searchKeyword || '').trim()) {
    return true;
  }
  return showCollapsedItems.value;
}

function toggleCollapsedItems() {
  showCollapsedItems.value = !showCollapsedItems.value;
}

// 检查最外层的 object 是否应该显示
function shouldShowSection() {
  const sectionMeta = props.metadata[props.metadataKey];
  if (!sectionMeta?.condition) {
    return true;
  }
  for (const [conditionKey, expectedValue] of Object.entries(
    sectionMeta.condition,
  )) {
    const actualValue = getValueBySelector(props.iterable, conditionKey);
    if (actualValue !== expectedValue) {
      return false;
    }
  }

  const sectionItems = props.metadata?.[props.metadataKey]?.items || {};
  const hasVisibleItems = Object.entries(sectionItems).some(
    ([itemKey, itemMeta]) => shouldShowItem(itemMeta, itemKey),
  );
  return hasVisibleItems;
}
</script>

<template>
  <v-card
    v-if="shouldShowSection()"
    class="config-section-card"
    rounded="md"
    variant="outlined"
  >
    <v-card-text
      v-if="metadata[metadataKey]?.type === 'object'"
      class="config-section config-section--object"
    >
      <v-list-item-title class="config-title">
        <span>{{ translateIfKey(metadata[metadataKey]?.description) }}</span>
        <ConfigDocsLink :docs="metadata[metadataKey]?.docs" />
      </v-list-item-title>
      <v-list-item-subtitle class="config-hint">
        <span
          v-if="
            metadata[metadataKey]?.obvious_hint && metadata[metadataKey]?.hint
          "
          class="important-hint"
          >‼️</span
        >
        <!-- eslint-disable-next-line vue/no-v-html -- renderHint sanitizes Markdown with DOMPurify. -->
        <span v-html="renderHint(metadata[metadataKey]?.hint)"></span>
      </v-list-item-subtitle>
    </v-card-text>

    <!-- Object Type Configuration with JSON Selector Support -->
    <div v-if="metadata[metadataKey]?.type === 'object'" class="object-config">
      <div
        v-for="([itemKey, itemMeta], index) in getVisibleItemEntries(false)"
        :key="itemKey"
        class="config-item"
      >
        <v-row v-if="!itemMeta?.invisible" class="config-row">
          <v-col cols="12" sm="6" class="property-info">
            <v-list-item density="compact">
              <v-list-item-title class="property-name">
                {{ getItemDescription(itemKey, itemMeta) }}
                <span class="property-key">({{ itemKey }})</span>
                <ConfigDocsLink :docs="itemMeta?.docs" />
              </v-list-item-title>

              <v-list-item-subtitle class="property-hint">
                <span
                  v-if="itemMeta?.obvious_hint && itemMeta?.hint"
                  class="important-hint"
                  >‼️</span
                >
                <!-- eslint-disable vue/no-v-html -- renderHint sanitizes Markdown with DOMPurify. -->
                <span
                  v-html="renderHint(getItemHint(itemKey, itemMeta))"
                ></span>
                <!-- eslint-enable vue/no-v-html -->
              </v-list-item-subtitle>
            </v-list-item>
          </v-col>
          <v-col cols="12" sm="6" class="config-input">
            <TemplateListEditor
              v-if="itemMeta?.type === 'template_list'"
              v-model="createSelectorModel(itemKey).value"
              :templates="itemMeta?.templates || {}"
              :plugin-name="pluginName"
              :plugin-i18n="pluginI18n"
              :config-path="getItemPath(itemKey)"
              class="config-field"
            />
            <ConfigItemRenderer
              v-else
              v-model="createSelectorModel(itemKey).value"
              :item-meta="itemMeta || null"
              :config-root="iterable"
              :plugin-name="pluginName"
              :plugin-i18n="pluginI18n"
              :config-key="getItemPath(itemKey)"
              :show-fullscreen-btn="!!itemMeta?.editor_mode"
              @open-fullscreen="
                openEditorDialog(
                  itemKey,
                  iterable,
                  itemMeta?.editor_theme,
                  itemMeta?.editor_language,
                )
              "
            />
          </v-col>
        </v-row>

        <v-row
          v-if="
            !itemMeta?.invisible && itemMeta?._special === 'select_plugin_set'
          "
          class="plugin-set-display-row"
        >
          <v-col cols="12" class="plugin-set-display">
            <div
              v-if="
                createSelectorModel(itemKey).value &&
                createSelectorModel(itemKey).value.length > 0
              "
              class="selected-plugins-full-width"
            >
              <div class="plugins-header">
                <small class="text-grey">{{
                  t('core.shared.pluginSetSelector.selectedPluginsLabel')
                }}</small>
              </div>
              <div class="d-flex flex-wrap ga-2 mt-2">
                <v-chip
                  v-for="plugin in createSelectorModel(itemKey).value || []"
                  :key="plugin"
                  size="small"
                  label
                  color="primary"
                  variant="outlined"
                >
                  {{
                    plugin === '*'
                      ? t('core.shared.pluginSetSelector.allPluginsLabel')
                      : plugin
                  }}
                </v-chip>
              </div>
            </div>
          </v-col>
        </v-row>

        <v-row
          v-if="!itemMeta?.invisible && itemMeta?._special === 'select_persona'"
          class="persona-preview-row"
        >
          <v-col cols="12" class="persona-preview-display">
            <PersonaQuickPreview
              :model-value="createSelectorModel(itemKey).value"
            />
          </v-col>
        </v-row>

        <v-divider
          v-if="hasVisibleEntriesAfter(getVisibleItemEntries(false), index)"
          class="config-divider"
        ></v-divider>
      </div>

      <div v-if="hasCollapsedItems()" class="collapsed-config-section">
        <div class="collapsed-config-toggle-row">
          <span class="collapsed-config-toggle" @click="toggleCollapsedItems">
            {{ tmConfig('sections.moreConfig') }}
            <v-icon end size="18">
              {{
                areCollapsedItemsVisible()
                  ? 'mdi-chevron-up'
                  : 'mdi-chevron-down'
              }}
            </v-icon>
          </span>
        </div>
        <div v-if="areCollapsedItemsVisible()">
          <div
            v-for="([itemKey, itemMeta], index) in getVisibleItemEntries(true)"
            :key="itemKey"
            class="config-item"
          >
            <v-row v-if="!itemMeta?.invisible" class="config-row">
              <v-col cols="12" sm="6" class="property-info">
                <v-list-item density="compact">
                  <v-list-item-title class="property-name">
                    {{ getItemDescription(itemKey, itemMeta) }}
                    <span class="property-key">({{ itemKey }})</span>
                    <ConfigDocsLink :docs="itemMeta?.docs" />
                  </v-list-item-title>

                  <v-list-item-subtitle class="property-hint">
                    <span
                      v-if="itemMeta?.obvious_hint && itemMeta?.hint"
                      class="important-hint"
                      >‼️</span
                    >
                    <!-- eslint-disable vue/no-v-html -- renderHint sanitizes Markdown with DOMPurify. -->
                    <span
                      v-html="renderHint(getItemHint(itemKey, itemMeta))"
                    ></span>
                    <!-- eslint-enable vue/no-v-html -->
                  </v-list-item-subtitle>
                </v-list-item>
              </v-col>
              <v-col cols="12" sm="6" class="config-input">
                <TemplateListEditor
                  v-if="itemMeta?.type === 'template_list'"
                  v-model="createSelectorModel(itemKey).value"
                  :templates="itemMeta?.templates || {}"
                  :plugin-name="pluginName"
                  :plugin-i18n="pluginI18n"
                  :config-path="getItemPath(itemKey)"
                  class="config-field"
                />
                <ConfigItemRenderer
                  v-else
                  v-model="createSelectorModel(itemKey).value"
                  :item-meta="itemMeta || null"
                  :config-root="iterable"
                  :plugin-name="pluginName"
                  :plugin-i18n="pluginI18n"
                  :config-key="getItemPath(itemKey)"
                  :show-fullscreen-btn="!!itemMeta?.editor_mode"
                  @open-fullscreen="
                    openEditorDialog(
                      itemKey,
                      iterable,
                      itemMeta?.editor_theme,
                      itemMeta?.editor_language,
                    )
                  "
                />
              </v-col>
            </v-row>

            <v-row
              v-if="
                !itemMeta?.invisible &&
                itemMeta?._special === 'select_plugin_set'
              "
              class="plugin-set-display-row"
            >
              <v-col cols="12" class="plugin-set-display">
                <div
                  v-if="
                    createSelectorModel(itemKey).value &&
                    createSelectorModel(itemKey).value.length > 0
                  "
                  class="selected-plugins-full-width"
                >
                  <div class="plugins-header">
                    <small class="text-grey">{{
                      t('core.shared.pluginSetSelector.selectedPluginsLabel')
                    }}</small>
                  </div>
                  <div class="d-flex flex-wrap ga-2 mt-2">
                    <v-chip
                      v-for="plugin in createSelectorModel(itemKey).value || []"
                      :key="plugin"
                      size="small"
                      label
                      color="primary"
                      variant="outlined"
                    >
                      {{
                        plugin === '*'
                          ? t('core.shared.pluginSetSelector.allPluginsLabel')
                          : plugin
                      }}
                    </v-chip>
                  </div>
                </div>
              </v-col>
            </v-row>

            <v-row
              v-if="
                !itemMeta?.invisible && itemMeta?._special === 'select_persona'
              "
              class="persona-preview-row"
            >
              <v-col cols="12" class="persona-preview-display">
                <PersonaQuickPreview
                  :model-value="createSelectorModel(itemKey).value"
                />
              </v-col>
            </v-row>

            <v-divider
              v-if="hasVisibleEntriesAfter(getVisibleItemEntries(true), index)"
              class="config-divider"
            ></v-divider>
          </div>
        </div>
      </div>
    </div>
  </v-card>

  <!-- Full Screen Editor Dialog -->
  <v-dialog
    v-model="dialog"
    fullscreen
    transition="dialog-bottom-transition"
    scrollable
  >
    <v-card>
      <v-toolbar color="primary">
        <v-btn
          icon
          :aria-label="t('core.common.close')"
          @click="dialog = false"
        >
          <v-icon>mdi-close</v-icon>
        </v-btn>
        <v-toolbar-title
          >{{ t('core.common.editor.editingTitle') }} -
          {{ currentEditingKey }}</v-toolbar-title
        >
        <v-spacer></v-spacer>
        <v-toolbar-items>
          <v-btn variant="text" @click="saveEditedContent">{{
            t('core.common.save')
          }}</v-btn>
        </v-toolbar-items>
      </v-toolbar>
      <v-card-text class="pa-0">
        <VueMonacoEditor
          v-model:value="currentEditingKeyIterable[currentEditingKey]"
          :theme="currentEditingTheme"
          :language="currentEditingLanguage"
          class="config-fullscreen-editor"
        >
        </VueMonacoEditor>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.config-section-card {
  margin-bottom: var(--astrbot-space-4);
  padding-bottom: var(--astrbot-space-2);
  background: rgb(var(--v-theme-background));
}

.config-section--object {
  padding-bottom: var(--astrbot-space-2);
}

.config-fullscreen-editor {
  height: calc(100dvh - 64px);
}

.config-section {
  margin-bottom: 4px;
}

.config-title {
  display: flex;
  align-items: center;
  gap: var(--astrbot-space-2);
  font-size: 1.3rem;
  color: var(--v-theme-on-surface);
}

.config-hint {
  font-size: 0.75rem;
  color: var(--v-theme-on-surface-variant);
  margin-top: 2px;
}

.config-hint :deep(a),
.property-hint :deep(a) {
  color: var(--v-theme-primary);
  text-decoration: underline;
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
  padding: 8px 8px;
  border-radius: 4px;
}

.config-row:hover {
  background-color: rgba(0, 0, 0, 0.03);
}

.property-info {
  padding: 0;
}

.property-name {
  display: flex;
  align-items: center;
  gap: var(--astrbot-space-2);
  font-size: 0.875rem;
  color: var(--v-theme-on-surface);
}

.property-hint {
  font-size: 0.75rem;
  color: var(--v-theme-on-surface-variant);
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

.persona-preview-row {
  margin: 16px;
  margin-top: 0;
}

.persona-preview-display {
  padding: 0 8px;
}

.selected-plugins-full-width {
  background-color: rgba(var(--v-theme-primary), 0.05);
  border: 1px solid rgba(var(--v-theme-primary), 0.1);
  border-radius: 8px;
  padding: 12px;
}

.collapsed-config-section {
  width: 100%;
}

.collapsed-config-toggle-row {
  padding: 8px 8px 4px;
}

.collapsed-config-toggle {
  min-height: auto;
  cursor: pointer;
  margin-left: 16px;
  font-size: 0.875rem;
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

  .type-indicator {
    padding: 4px 8px;
  }

  .config-input {
    padding-left: 16px;
    padding-right: 16px;
  }

  .config-divider {
    display: none;
  }
}
</style>
