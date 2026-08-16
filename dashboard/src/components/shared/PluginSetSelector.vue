<template>
  <div class="plugin-set-selector">
    <div>
      <!-- 顶部操作区域 -->
      <div class="d-flex align-center justify-space-between mb-2">
        <div class="flex-grow-1">
          <span
            v-if="!modelValue || modelValue.length === 0"
            class="selector-empty-label"
          >
            {{ tm('pluginSetSelector.notSelected') }}
          </span>
          <span v-else-if="isAllPlugins" class="selector-empty-label">
            {{ tm('pluginSetSelector.allPlugins') }}
          </span>
          <span v-else class="selector-empty-label">
            {{
              tm('pluginSetSelector.selectedCount', {
                count: modelValue.length,
              })
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
              class="selector-scroll-region"
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
                      color="secondary"
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
                <v-icon size="64" color="secondary">mdi-puzzle-outline</v-icon>
                <p class="text-medium-emphasis mt-4">
                  {{ tm('pluginSetSelector.noPlugins') }}
                </p>
              </div>
            </div>
          </div>
        </v-card-text>

        <v-card-actions class="pa-4 plugin-set-dialog__actions">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="cancelSelection">{{
            tm('pluginSetSelector.cancelSelection')
          }}</v-btn>
          <v-btn color="primary" @click="confirmSelection">
            {{ tm('pluginSetSelector.confirmSelection') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
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
});

const emit = defineEmits(['update:modelValue']);
const { tm } = useModuleI18n('core.shared');
const { pluginName, pluginDesc } = usePluginI18n();

const dialog = ref(false);
const pluginList = ref([]);
const loading = ref(false);
const selectionMode = ref('custom'); // 'all', 'none', 'custom'
const selectedPlugins = ref([]);

const pluginDisplayName = (plugin) => pluginName(plugin) || plugin.name;
const pluginDescription = (plugin) => pluginDesc(plugin);

// 判断是否为"所有插件"模式
const isAllPlugins = computed(() => {
  return props.modelValue?.length === 1 && props.modelValue[0] === '*';
});

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
      // 只显示已激活且非系统的插件，并按名称排序
      pluginList.value = (response.data.data || [])
        .filter((plugin) => plugin.activated && !plugin.reserved)
        .sort((a, b) => {
          const nameA = a.name || '';
          const nameB = b.name || '';
          return nameA.localeCompare(nameB);
        });
    }
  } catch (error) {
    console.error('加载插件列表失败:', error);
    pluginList.value = [];
  } finally {
    loading.value = false;
  }
}

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

.plugin-set-dialog__actions {
  flex-shrink: 0;
}
</style>
