<script setup lang="ts">
import MarkdownIt from "markdown-it";
import { VueMonacoEditor } from "@guolao/vue-monaco-editor";
import { ref, computed } from "vue";
import ConfigItemRenderer from "./ConfigItemRenderer.vue";
import TemplateListEditor from "./TemplateListEditor.vue";
import PersonaQuickPreview from "./PersonaQuickPreview.vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";

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
    default: "",
  },
});

const { t } = useI18n();
const { tm, getRaw } = useModuleI18n("features/config-metadata");

const hintMarkdown = new MarkdownIt({
  linkify: true,
  breaks: true,
});

// 翻译器函数 - 如果是国际化键则翻译，否则原样返回
const translateIfKey = (value) => {
  if (!value || typeof value !== "string") return value;
  return tm(value);
};

const renderHint = (value) => {
  const text = translateIfKey(value);
  if (!text) return "";
  return hintMarkdown.renderInline(text);
};

// 处理labels翻译 - labels可以是数组或国际化键
const getTranslatedLabels = (itemMeta) => {
  if (!itemMeta?.labels) return null;

  // 如果labels是字符串（国际化键）
  if (typeof itemMeta.labels === "string") {
    const translatedLabels = getRaw(itemMeta.labels);
    // 如果翻译成功且是数组，返回翻译结果
    if (Array.isArray(translatedLabels)) {
      return translatedLabels;
    }
  }

  // 如果labels是数组，直接返回
  if (Array.isArray(itemMeta.labels)) {
    return itemMeta.labels;
  }

  return null;
};

const dialog = ref(false);
const currentEditingKey = ref("");
const currentEditingLanguage = ref("json");
const currentEditingTheme = ref("vs-light");
let currentEditingKeyIterable = null;

function getValueBySelector(obj, selector) {
  const keys = selector.split(".");
  let current = obj;
  for (const key of keys) {
    if (current && typeof current === "object" && key in current) {
      current = current[key];
    } else {
      return undefined;
    }
  }
  return current;
}

function setValueBySelector(obj, selector, value) {
  const keys = selector.split(".");
  let current = obj;

  // 创建嵌套对象路径
  for (let i = 0; i < keys.length - 1; i++) {
    const key = keys[i];
    if (!current[key] || typeof current[key] !== "object") {
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

function openEditorDialog(key, value, theme, language) {
  currentEditingKey.value = key;
  currentEditingLanguage.value = language || "json";
  currentEditingTheme.value = theme || "vs-light";
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

  const keyword = String(props.searchKeyword || "")
    .trim()
    .toLowerCase();
  if (!keyword) {
    return true;
  }

  const searchableText = [
    itemKey,
    translateIfKey(itemMeta?.description || ""),
    translateIfKey(itemMeta?.hint || ""),
  ]
    .join(" ")
    .toLowerCase();

  return searchableText.includes(keyword);
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

function hasVisibleItemsAfter(items, currentIndex) {
  const itemEntries = Object.entries(items);

  // 检查当前索引之后是否还有可见的配置项
  for (let i = currentIndex + 1; i < itemEntries.length; i++) {
    const [itemKey, itemMeta] = itemEntries[i];
    if (shouldShowItem(itemMeta, itemKey)) {
      return true;
    }
  }

  return false;
}

function parseSpecialValue(value) {
  if (!value || typeof value !== "string") {
    return { name: "", subtype: "" };
  }
  const [name, ...rest] = value.split(":");
  return {
    name,
    subtype: rest.join(":") || "",
  };
}

function getSpecialName(value) {
  return parseSpecialValue(value).name;
}

function getSpecialSubtype(value) {
  return parseSpecialValue(value).subtype;
}
</script>

<template>
  <v-card
    v-if="shouldShowSection()"
    class="config-reactor-card"
  >
    <v-card-text
      v-if="metadata[metadataKey]?.type === 'object'"
      class="config-section"
    >
      <v-list-item-title class="config-title">
        <span class="title-glow-bar" />
        {{ translateIfKey(metadata[metadataKey]?.description) }}
      </v-list-item-title>
      <v-list-item-subtitle class="config-hint">
        <span
          v-if="
            metadata[metadataKey]?.obvious_hint && metadata[metadataKey]?.hint
          "
          class="important-hint"
          >⚠️</span
        >
        <span v-html="renderHint(metadata[metadataKey]?.hint)" />
      </v-list-item-subtitle>
    </v-card-text>

    <!-- Object Type Configuration with JSON Selector Support -->
    <div v-if="metadata[metadataKey]?.type === 'object'" class="object-config">
      <div
        v-for="(itemMeta, itemKey, index) in metadata[metadataKey].items"
        :key="itemKey"
        class="config-item"
      >
        <!-- Check if itemKey is a JSON selector -->
        <template v-if="shouldShowItem(itemMeta, itemKey)">
          <!-- JSON Selector Property -->
          <v-row v-if="!itemMeta?.invisible" class="config-row">
            <v-col cols="12" sm="6" class="property-info">
              <v-list-item density="compact">
                <v-list-item-title class="property-name">
                  {{ translateIfKey(itemMeta?.description) || itemKey }}
                  <span class="property-key">({{ itemKey }})</span>
                </v-list-item-title>

                <v-list-item-subtitle class="property-hint">
                  <span
                    v-if="itemMeta?.obvious_hint && itemMeta?.hint"
                    class="important-hint"
                    >‼️</span
                  >
                  <span v-html="renderHint(itemMeta?.hint)" />
                </v-list-item-subtitle>
              </v-list-item>
            </v-col>
            <v-col cols="12" sm="6" class="config-input">
              <TemplateListEditor
                v-if="itemMeta?.type === 'template_list'"
                v-model="createSelectorModel(itemKey).value"
                :templates="itemMeta?.templates || {}"
                class="config-field"
              />
              <ConfigItemRenderer
                v-else
                v-model="createSelectorModel(itemKey).value"
                :item-meta="itemMeta || null"
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

          <!-- Plugin Set Selector 全宽显示区域 -->
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
                    t("core.shared.pluginSetSelector.selectedPluginsLabel")
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
                      plugin === "*"
                        ? t("core.shared.pluginSetSelector.allPluginsLabel")
                        : plugin
                    }}
                  </v-chip>
                </div>
              </div>
            </v-col>
          </v-row>

          <!-- Default Persona Quick Preview 全宽显示区域 -->
          <v-row
            v-if="
              !itemMeta?.invisible &&
              itemMeta?._special === 'select_persona' &&
              itemKey === 'provider_settings.default_personality'
            "
            class="persona-preview-row"
          >
            <v-col cols="12" class="persona-preview-display">
              <PersonaQuickPreview
                :model-value="createSelectorModel(itemKey).value"
              />
            </v-col>
          </v-row>
        </template>
        <v-divider
          v-if="
            shouldShowItem(itemMeta, itemKey) &&
            hasVisibleItemsAfter(metadata[metadataKey].items, index)
          "
          class="config-divider"
        />
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
      <v-toolbar color="primary" dark>
        <v-btn icon @click="dialog = false">
          <v-icon>mdi-close</v-icon>
        </v-btn>
        <v-toolbar-title
          >{{ t("core.common.editor.editingTitle") }} -
          {{ currentEditingKey }}</v-toolbar-title
        >
        <v-spacer />
        <v-toolbar-items>
          <v-btn variant="text" @click="saveEditedContent">
            {{ t("core.common.save") }}
          </v-btn>
        </v-toolbar-items>
      </v-toolbar>
      <v-card-text class="pa-0">
        <VueMonacoEditor
          v-model:value="currentEditingKeyIterable[currentEditingKey]"
          :theme="currentEditingTheme"
          :language="currentEditingLanguage"
          style="height: calc(100vh - 64px)"
        />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<style scoped>
/* === Reactor glassmorphism card === */
.config-reactor-card {
  margin-bottom: 16px;
  padding-bottom: 8px;
  background: rgba(15, 15, 22, 0.45) !important;
  backdrop-filter: blur(20px) saturate(1.2);
  border: 1px solid rgba(0, 242, 255, 0.08) !important;
  border-radius: 24px !important;
  box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.6) !important;
}

.config-section {
  margin-bottom: 4px;
  padding-bottom: 8px;
}

.config-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: rgba(0, 242, 255, 0.9) !important;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-glow-bar {
  display: inline-block;
  width: 3px;
  height: 1.1em;
  background: linear-gradient(180deg, #00F2FF 0%, rgba(0, 242, 255, 0.2) 100%);
  border-radius: 2px;
  flex-shrink: 0;
  box-shadow: 0 0 8px rgba(0, 242, 255, 0.6);
}

.config-hint {
  font-size: 0.75rem;
  color: rgba(228, 225, 230, 0.5);
  margin-top: 4px;
  line-height: 1.5;
}

.config-hint ::v-deep(a),
.property-hint ::v-deep(a) {
  color: rgba(0, 242, 255, 0.7);
  text-decoration: none;
  border-bottom: 1px solid rgba(0, 242, 255, 0.3);
  transition: border-color 0.2s;
}
.config-hint ::v-deep(a:hover),
.property-hint ::v-deep(a:hover) {
  border-bottom-color: #00F2FF;
}

.metadata-key,
.property-key {
  font-size: 0.8em;
  opacity: 0.45;
  font-weight: normal;
  font-family: "JetBrains Mono", monospace;
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
  border: 1px solid rgba(0, 242, 255, 0.06);
  border-radius: 12px;
  padding: 12px;
  margin: 12px 0;
  background: rgba(0, 0, 0, 0.2);
}

.config-row {
  margin: 0;
  align-items: center;
  padding: 10px 12px;
  border-radius: 6px;
  transition: background 0.2s;
}

.config-row:hover {
  background: rgba(0, 242, 255, 0.03);
}

.property-info {
  padding: 0;
}

.property-name {
  font-size: 0.875rem;
  font-weight: 500;
  color: rgba(228, 225, 230, 0.85);
}

.property-hint {
  font-size: 0.72rem;
  color: rgba(228, 225, 230, 0.4);
  margin-top: 2px;
  line-height: 1.4;
}

.type-indicator {
  display: flex;
  justify-content: center;
}

.config-input {
  padding: 2px 8px;
}

.config-field {
  margin-bottom: 0;
}

.config-divider {
  border-color: rgba(255, 255, 255, 0.04) !important;
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
  background: rgba(0, 242, 255, 0.04);
  border: 1px solid rgba(0, 242, 255, 0.08);
  border-radius: 10px;
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
  .type-indicator {
    padding: 4px 8px;
  }

  .config-input {
    padding-left: 24px;
    padding-right: 24px;
  }
}
</style>
