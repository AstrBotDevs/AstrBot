<template>
  <div v-if="inline" class="inline-plugin-selector">
    <v-progress-linear v-if="loading" indeterminate color="primary" />

    <template v-else-if="pluginList.length > 0">
      <div class="inline-plugin-selector__toolbar">
        <v-text-field
          v-model="pluginSearchKeyword"
          class="inline-plugin-selector__search"
          :placeholder="tm('pluginSetSelector.searchPlaceholder')"
          prepend-inner-icon="mdi-magnify"
          variant="outlined"
          density="compact"
          hide-details
          clearable
        />
        <v-checkbox-btn
          :model-value="allPluginsSelected"
          :indeterminate="somePluginsSelected"
          :label="tm('pluginSetSelector.selectAll')"
          color="primary"
          density="compact"
          @update:model-value="toggleAllPlugins"
        />
      </div>

      <div
        v-if="filteredPluginList.length > 0"
        class="inline-plugin-selector__list"
      >
        <div
          v-for="plugin in filteredPluginList"
          :key="plugin.name"
          class="inline-plugin-card"
          @click="toggleInlinePlugin(plugin)"
        >
          <div class="inline-plugin-card__body">
            <div class="inline-plugin-card__title-row">
              <span class="inline-plugin-card__title">{{
                pluginDisplayName(plugin)
              }}</span>
              <span v-if="plugin.reserved" class="inline-plugin-card__preset">
                {{ tm('pluginSetSelector.preset') }}
              </span>
            </div>
            <div
              class="inline-plugin-card__description"
              :title="pluginDescription(plugin)"
            >
              {{
                pluginDescription(plugin) ||
                tm('pluginSetSelector.noDescription')
              }}
            </div>
          </div>

          <v-checkbox-btn
            :model-value="inlinePluginEnabled(plugin)"
            :aria-label="pluginDisplayName(plugin)"
            color="primary"
            density="compact"
            @click.stop
            @update:model-value="toggleInlinePlugin(plugin)"
          />
        </div>
      </div>

      <div
        v-else
        class="inline-plugin-selector__empty inline-plugin-selector__empty--search"
      >
        <v-icon size="38">mdi-magnify-close</v-icon>
        <span>{{ tm('pluginSetSelector.noSearchResults') }}</span>
      </div>
    </template>

    <div v-else class="inline-plugin-selector__empty">
      <v-icon size="38">mdi-puzzle-outline</v-icon>
      <span>{{ tm('pluginSetSelector.noPlugins') }}</span>
    </div>
  </div>

  <div v-else>
    <!-- 顶部操作区域 -->
    <div class="d-flex align-center justify-space-between mb-2">
      <div class="flex-grow-1">
        <span
          v-if="!modelValue || modelValue.length === 0"
          style="color: rgb(var(--v-theme-primaryText))"
        >
          {{ tm('pluginSetSelector.notSelected') }}
        </span>
        <span
          v-else-if="isAllPlugins"
          style="color: rgb(var(--v-theme-primaryText))"
        >
          {{ tm('pluginSetSelector.allPlugins') }}
        </span>
        <span v-else style="color: rgb(var(--v-theme-primaryText))">
          {{
            tm('pluginSetSelector.selectedCount', { count: modelValue.length })
          }}
        </span>
      </div>
      <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
        {{ buttonText || tm('pluginSetSelector.buttonText') }}
      </v-btn>
    </div>
  </div>

  <!-- Plugin Set Selection Dialog -->
  <v-dialog v-model="dialog" max-width="700px" scrollable>
    <v-card class="app-dialog plugin-set-dialog__card">
      <v-card-title class="app-dialog__title">
        {{ tm('pluginSetSelector.dialogTitle') }}
      </v-card-title>

      <v-card-text class="pa-4 plugin-set-dialog__content">
        <v-progress-linear
          v-if="loading"
          indeterminate
          color="primary"
        ></v-progress-linear>

        <div v-if="!loading">
          <!-- 预设选项 -->
          <v-radio-group v-model="selectionMode" class="mb-4" hide-details>
            <v-radio
              value="all"
              :label="tm('pluginSetSelector.enableAll')"
              color="primary"
            ></v-radio>
            <v-radio
              value="none"
              :label="tm('pluginSetSelector.enableNone')"
              color="primary"
            ></v-radio>
            <v-radio
              value="custom"
              :label="tm('pluginSetSelector.customSelect')"
              color="primary"
            ></v-radio>
          </v-radio-group>

          <!-- 自定义选择时显示插件列表 -->
          <div
            v-if="selectionMode === 'custom'"
            style="max-height: 300px; overflow-y: auto"
          >
            <v-list v-if="pluginList.length > 0" density="compact">
              <v-list-item
                v-for="plugin in pluginList"
                :key="plugin.name"
                rounded="md"
                class="ma-1"
              >
                <template #prepend>
                  <v-checkbox
                    v-model="selectedPlugins"
                    :value="plugin.name"
                    color="primary"
                    hide-details
                  ></v-checkbox>
                </template>

                <v-list-item-title>{{
                  pluginDisplayName(plugin)
                }}</v-list-item-title>
                <v-list-item-subtitle>
                  {{
                    pluginDescription(plugin) ||
                    tm('pluginSetSelector.noDescription')
                  }}
                  <v-chip
                    v-if="!plugin.activated"
                    size="x-small"
                    color="grey"
                    class="ml-1"
                  >
                    {{ tm('pluginSetSelector.notActivated') }}
                  </v-chip>
                </v-list-item-subtitle>
              </v-list-item>

              <div class="pl-8 pt-2">
                <small>{{ tm('pluginSetSelector.note') }}</small>
              </div>
            </v-list>

            <div v-else class="text-center py-8">
              <v-icon size="64" color="grey-lighten-1"
                >mdi-puzzle-outline</v-icon
              >
              <p class="text-grey mt-4">
                {{ tm('pluginSetSelector.noPlugins') }}
              </p>
            </div>
          </div>
        </div>
      </v-card-text>

      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelSelection">{{
          tm('pluginSetSelector.cancelSelection')
        }}</v-btn>
        <v-btn color="primary" variant="tonal" @click="confirmSelection">
          {{ tm('pluginSetSelector.confirmSelection') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { pluginApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { usePluginI18n } from '@/utils/pluginI18n';

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  buttonText: {
    type: String,
    default: '',
  },
  maxDisplayItems: {
    type: Number,
    default: 3,
  },
  inline: {
    type: Boolean,
    default: false,
  },
  searchKeyword: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['update:modelValue']);
const { tm } = useModuleI18n('core.shared');
const { pluginName, pluginDesc } = usePluginI18n();

const dialog = ref(false);
const pluginList = ref([]);
const loading = ref(false);
const selectionMode = ref('custom'); // 'all', 'none', 'custom'
const selectedPlugins = ref([]);
const pluginSearchKeyword = ref('');

const pluginDisplayName = (plugin) => pluginName(plugin) || plugin.name;
const pluginDescription = (plugin) => pluginDesc(plugin);

// 判断是否为"所有插件"模式
const isAllPlugins = computed(() => {
  return props.modelValue?.length === 1 && props.modelValue[0] === '*';
});

const filteredPluginList = computed(() => {
  const keywords = [props.searchKeyword, pluginSearchKeyword.value]
    .map((keyword) =>
      String(keyword || '')
        .trim()
        .toLowerCase(),
    )
    .filter(Boolean);
  if (keywords.length === 0) return pluginList.value;
  return pluginList.value.filter((plugin) => {
    const searchableText = [
      plugin.name,
      pluginDisplayName(plugin),
      pluginDescription(plugin),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return keywords.every((keyword) => searchableText.includes(keyword));
  });
});

const selectedPluginCount = computed(() => {
  if (isAllPlugins.value) return pluginList.value.length;
  const selected = new Set(props.modelValue || []);
  return pluginList.value.filter((plugin) => selected.has(plugin.name)).length;
});

const allPluginsSelected = computed(
  () =>
    pluginList.value.length > 0 &&
    selectedPluginCount.value === pluginList.value.length,
);

const somePluginsSelected = computed(
  () => selectedPluginCount.value > 0 && !allPluginsSelected.value,
);

// 监听 modelValue 变化，同步内部状态
watch(
  () => props.modelValue,
  (newValue) => {
    if (!newValue || newValue.length === 0) {
      selectionMode.value = 'none';
      selectedPlugins.value = [];
    } else if (newValue.length === 1 && newValue[0] === '*') {
      selectionMode.value = 'all';
      selectedPlugins.value = [];
    } else {
      selectionMode.value = 'custom';
      selectedPlugins.value = [...newValue];
    }
  },
  { immediate: true },
);

async function openDialog() {
  dialog.value = true;
  await loadPlugins();
}

async function loadPlugins() {
  loading.value = true;
  try {
    const response = await pluginApi.list();
    if (response.data.status === 'ok') {
      const activatedPlugins = (response.data.data || [])
        .filter((plugin) => plugin.activated)
        .sort((a, b) => {
          if (props.inline && Boolean(a.reserved) !== Boolean(b.reserved)) {
            return a.reserved ? -1 : 1;
          }
          const nameA = pluginDisplayName(a) || a.name || '';
          const nameB = pluginDisplayName(b) || b.name || '';
          return nameA.localeCompare(nameB);
        });
      pluginList.value = props.inline
        ? activatedPlugins
        : activatedPlugins.filter((plugin) => !plugin.reserved);
    }
  } catch (error) {
    console.error('加载插件列表失败:', error);
    pluginList.value = [];
  } finally {
    loading.value = false;
  }
}

function inlinePluginEnabled(plugin) {
  return isAllPlugins.value || (props.modelValue || []).includes(plugin.name);
}

function toggleInlinePlugin(plugin) {
  const selected = new Set(
    isAllPlugins.value
      ? pluginList.value.map((item) => item.name)
      : props.modelValue || [],
  );
  if (selected.has(plugin.name)) {
    selected.delete(plugin.name);
  } else {
    selected.add(plugin.name);
  }
  const nextSelection = pluginList.value
    .map((item) => item.name)
    .filter((name) => selected.has(name));
  emit(
    'update:modelValue',
    nextSelection.length === pluginList.value.length &&
      pluginList.value.length > 0
      ? ['*']
      : nextSelection,
  );
}

function toggleAllPlugins() {
  emit('update:modelValue', allPluginsSelected.value ? [] : ['*']);
}

onMounted(() => {
  if (props.inline) {
    void loadPlugins();
  }
});

function confirmSelection() {
  let newValue = [];

  switch (selectionMode.value) {
    case 'all':
      newValue = ['*'];
      break;
    case 'none':
      newValue = [];
      break;
    case 'custom':
      newValue = [...selectedPlugins.value];
      break;
  }

  emit('update:modelValue', newValue);
  dialog.value = false;
}

function cancelSelection() {
  // 恢复到原始状态
  const currentValue = props.modelValue || [];
  if (currentValue.length === 0) {
    selectionMode.value = 'none';
    selectedPlugins.value = [];
  } else if (currentValue.length === 1 && currentValue[0] === '*') {
    selectionMode.value = 'all';
    selectedPlugins.value = [];
  } else {
    selectionMode.value = 'custom';
    selectedPlugins.value = [...currentValue];
  }

  dialog.value = false;
}
</script>

<style scoped>
.v-list-item {
  transition: all 0.2s ease;
}

.v-list-item:hover {
  background-color: rgba(var(--v-theme-primary), 0.04);
}

.inline-plugin-selector__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.inline-plugin-selector__toolbar {
  display: flex;
  min-height: 34px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
}

.inline-plugin-selector__search {
  min-width: 0;
  max-width: 240px;
}

.inline-plugin-selector__search :deep(.v-field) {
  min-height: 36px;
  border-radius: 9px;
}

.inline-plugin-selector__search :deep(.v-field__input) {
  min-height: 36px;
  padding-top: 6px;
  padding-bottom: 6px;
  font-size: 0.78rem;
}

.inline-plugin-selector__toolbar :deep(.v-label) {
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 0.8rem;
  font-weight: 650;
}

.inline-plugin-card {
  display: flex;
  min-height: 76px;
  align-items: center;
  gap: 18px;
  padding: 13px 14px 13px 16px;
  border-radius: 12px;
  background: rgba(var(--v-theme-on-surface), 0.045);
  cursor: pointer;
  transition: background-color 120ms ease;
}

.inline-plugin-card:hover {
  background: rgba(var(--v-theme-on-surface), 0.065);
}

.inline-plugin-card__body {
  min-width: 0;
  flex: 1;
}

.inline-plugin-card__title-row {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.inline-plugin-card__title {
  overflow: hidden;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.94rem;
  font-weight: 740;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inline-plugin-card__preset {
  flex: 0 0 auto;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
  font-size: 0.68rem;
  font-weight: 650;
  line-height: 1.45;
}

.inline-plugin-card__description {
  overflow: hidden;
  margin-top: 5px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 0.76rem;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inline-plugin-card :deep(.v-selection-control) {
  min-height: 32px;
}

.inline-plugin-selector__empty {
  display: flex;
  min-height: 180px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  font-size: 0.82rem;
}

.inline-plugin-selector__empty--search {
  min-height: 150px;
}

@media (max-width: 600px) {
  .inline-plugin-selector__toolbar {
    gap: 10px;
  }

  .inline-plugin-selector__search {
    max-width: none;
  }

  .inline-plugin-card {
    min-height: 70px;
    padding: 11px 10px 11px 13px;
  }
}

.plugin-set-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 820px);
}

.plugin-set-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}
</style>
