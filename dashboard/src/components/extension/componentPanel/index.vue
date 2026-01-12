<script setup lang="ts">
/**
 * 组件管理页面 - 主入口
 * 
 * 模块化结构：
 * - types.ts: 类型定义
 * - composables/useComponentData.ts: 数据获取和状态管理
 * - composables/useCommandFilters.ts: 过滤逻辑
 * - composables/useCommandActions.ts: 操作方法
 * - components/CommandFilters.vue: 过滤器组件
 * - components/CommandTable.vue: 表格组件
 * - components/RenameDialog.vue: 重命名对话框
 * - components/DetailsDialog.vue: 详情对话框
 */
import { computed, onActivated, onMounted, ref, watch} from 'vue';
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';

// Composables
import { useComponentData } from './composables/useComponentData';
import { useCommandFilters } from './composables/useCommandFilters';
import { useCommandActions } from './composables/useCommandActions';

// Components
import CommandFilters from './components/CommandFilters.vue';
import CommandTable from './components/CommandTable.vue';
import ToolTable from './components/ToolTable.vue';
import RenameDialog from './components/RenameDialog.vue';
import DetailsDialog from './components/DetailsDialog.vue';

// Types
import type { CommandItem, ToolItem } from './types';

defineOptions({ name: 'ComponentPanel' });
const props = withDefaults(defineProps<{ active?: boolean }>(), {
  active: true
});

const { tm } = useModuleI18n('features/command');
const { tm: tmTool } = useModuleI18n('features/tooluse');

const viewMode = ref<'commands' | 'tools'>('commands');
const toolSearch = ref('');

// 数据管理
const { 
  loading, 
  commands, 
  tools,
  toolsLoading,
  summary, 
  snackbar, 
  toast, 
  fetchCommands,
  fetchTools 
} = useComponentData();

// 过滤逻辑
const {
  searchQuery,
  pluginFilter,
  permissionFilter,
  statusFilter,
  typeFilter,
  showSystemPlugins,
  expandedGroups,
  hasSystemPluginConflict,
  effectiveShowSystemPlugins,
  availablePlugins,
  filteredCommands,
  toggleGroupExpand
} = useCommandFilters(commands);

// 操作方法
const {
  renameDialog,
  detailsDialog,
  toggleCommand,
  openRenameDialog,
  confirmRename,
  openDetailsDialog
} = useCommandActions(toast, () => fetchCommands(tm('messages.loadFailed')));

const filteredTools = computed(() => {
  const query = toolSearch.value.trim().toLowerCase();
  if (!query) return tools.value;
  return tools.value.filter(tool => 
    tool.name?.toLowerCase().includes(query) ||
    tool.description?.toLowerCase().includes(query)
  );
});

// 处理切换指令状态
const handleToggleCommand = async (cmd: CommandItem) => {
  await toggleCommand(cmd, tm('messages.toggleSuccess'), tm('messages.toggleFailed'));
};

const handleToggleTool = async (tool: ToolItem) => {
  const previous = tool.active;
  tool.active = !tool.active;
  try {
    const res = await axios.post('/api/tools/toggle-tool', {
      name: tool.name,
      activate: tool.active
    });
    if (res.data.status === 'ok') {
      toast(res.data.message || tmTool('messages.toggleToolSuccess'));
    } else {
      tool.active = previous;
      toast(res.data.message || tmTool('messages.toggleToolError', { error: '' }), 'error');
    }
  } catch (error: any) {
    tool.active = previous;
    toast(error?.response?.data?.message || error?.message || tmTool('messages.toggleToolError', { error: '' }), 'error');
  }
};

// 处理确认重命名
const handleConfirmRename = async () => {
  await confirmRename(tm('messages.renameSuccess'), tm('messages.renameFailed'));
};

// 生命周期
onMounted(async () => {
  await Promise.all([
    fetchCommands(tm('messages.loadFailed')),
    fetchTools(tmTool('messages.getToolsError', { error: '' }))
  ]);
});

watch(() => props.active, async (isActive) => {
  if (!isActive) return;
  if (viewMode.value === 'commands') {
    await fetchCommands(tm('messages.loadFailed'));
  } else {
    await fetchTools(tmTool('messages.getToolsError', { error: '' }));
  }
});

watch(viewMode, async (mode) => {
  if (mode === 'commands') {
    await fetchCommands(tm('messages.loadFailed'));
  } else {
    await fetchTools(tmTool('messages.getToolsError', { error: '' }));
  }
});
</script>

<template>
  <v-row>
    <v-col cols="12">
      <v-card variant="flat" style="background-color: transparent">
        <v-card-text style="padding: 20px 12px; padding-top: 0px;">
          <div class="d-flex justify-space-between align-center mb-6 flex-wrap ga-3">
            <v-btn-toggle v-model="viewMode" color="primary" variant="outlined" density="comfortable" mandatory>
              <v-btn value="commands">
                <v-icon size="18" class="mr-1">mdi-console-line</v-icon>
                {{ tm('type.command') }}
              </v-btn>
              <v-btn value="tools">
                <v-icon size="18" class="mr-1">mdi-function-variant</v-icon>
                {{ tmTool('functionTools.title') }}
              </v-btn>
            </v-btn-toggle>
            <v-progress-linear
              v-if="viewMode === 'commands' && loading"
              indeterminate
              color="primary"
              style="max-width: 220px; flex: 1;"
            />
            <v-progress-linear
              v-else-if="viewMode === 'tools' && toolsLoading"
              indeterminate
              color="primary"
              style="max-width: 220px; flex: 1;"
            />
          </div>

          <div v-if="viewMode === 'commands'">
            <CommandFilters
              :plugin-filter="pluginFilter"
              @update:plugin-filter="pluginFilter = $event"
              :type-filter="typeFilter"
              @update:type-filter="typeFilter = $event"
              :permission-filter="permissionFilter"
              @update:permission-filter="permissionFilter = $event"
              :status-filter="statusFilter"
              @update:status-filter="statusFilter = $event"
              :show-system-plugins="showSystemPlugins"
              @update:show-system-plugins="showSystemPlugins = $event"
              :search-query="searchQuery"
              @update:search-query="searchQuery = $event"
              :available-plugins="availablePlugins"
              :has-system-plugin-conflict="hasSystemPluginConflict"
              :effective-show-system-plugins="effectiveShowSystemPlugins"
            >
              <template #stats>
                <div class="d-flex align-center">
                  <v-icon size="18" color="primary" class="mr-1">mdi-console-line</v-icon>
                  <span class="text-body-2 text-medium-emphasis mr-1">{{ tm('summary.total') }}:</span>
                  <span class="text-body-1 font-weight-bold text-primary">{{ filteredCommands.length }}</span>
                </div>
                <v-divider vertical class="mx-1" style="height: 20px;" />
                <div class="d-flex align-center">
                  <v-icon size="18" color="error" class="mr-1">mdi-close-circle-outline</v-icon>
                  <span class="text-body-2 text-medium-emphasis mr-1">{{ tm('summary.disabled') }}:</span>
                  <span class="text-body-1 font-weight-bold text-error">{{ summary.disabled }}</span>
                </div>
              </template>
            </CommandFilters>
            
            <v-alert
              v-if="summary.conflicts > 0"
              type="error"
              variant="tonal"
              class="mb-4"
              prominent
              border="start"
            >
              <template v-slot:prepend>
                <v-icon size="28">mdi-alert-circle</v-icon>
              </template>
              <v-alert-title class="text-subtitle-1 font-weight-bold">
                {{ tm('conflictAlert.title') }}
              </v-alert-title>
              <div class="text-body-2 mt-1">
                {{ tm('conflictAlert.description', { count: summary.conflicts }) }}
              </div>
              <div class="text-body-2 mt-2">
                <v-icon size="16" class="mr-1">mdi-lightbulb-outline</v-icon>
                {{ tm('conflictAlert.hint') }}
              </div>
            </v-alert>

            <CommandTable
              :items="filteredCommands"
              :expanded-groups="expandedGroups"
              :loading="loading"
              @toggle-expand="toggleGroupExpand"
              @toggle-command="handleToggleCommand"
              @rename="openRenameDialog"
              @view-details="openDetailsDialog"
            />
          </div>

          <div v-else>
            <div class="d-flex flex-wrap align-center ga-3 mb-4">
              <div style="min-width: 240px; max-width: 380px; flex: 1;">
                <v-text-field
                  v-model="toolSearch"
                  prepend-inner-icon="mdi-magnify"
                  :label="tmTool('functionTools.search')"
                  variant="outlined"
                  density="compact"
                  hide-details
                  clearable
                />
              </div>
              <div class="d-flex align-center ga-2">
                <div class="d-flex align-center">
                  <v-icon size="18" color="primary" class="mr-1">mdi-function-variant</v-icon>
                  <span class="text-body-2 text-medium-emphasis mr-1">{{ tm('summary.total') }}:</span>
                  <span class="text-body-1 font-weight-bold text-primary">{{ filteredTools.length }}</span>
                </div>
                <v-divider vertical class="mx-1" style="height: 20px;" />
                <div class="d-flex align-center">
                  <v-icon size="18" color="success" class="mr-1">mdi-check-circle-outline</v-icon>
                  <span class="text-body-2 text-medium-emphasis mr-1">{{ tm('status.enabled') }}:</span>
                  <span class="text-body-1 font-weight-bold text-success">{{ filteredTools.filter(t => t.active).length }}</span>
                </div>
              </div>
            </div>

            <ToolTable
              :items="filteredTools"
              :loading="toolsLoading"
              @toggle-tool="handleToggleTool"
            />
          </div>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>

  <!-- 重命名对话框 -->
  <RenameDialog
    :show="renameDialog.show"
    @update:show="renameDialog.show = $event"
    :new-name="renameDialog.newName"
    @update:new-name="renameDialog.newName = $event"
    :aliases="renameDialog.aliases"
    @update:aliases="renameDialog.aliases = $event"
    :command="renameDialog.command"
    :loading="renameDialog.loading"
    @confirm="handleConfirmRename"
  />

  <!-- 详情对话框 -->
  <DetailsDialog
    :show="detailsDialog.show"
    @update:show="detailsDialog.show = $event"
    :command="detailsDialog.command"
  />

  <!-- Snackbar -->
  <v-snackbar :timeout="2000" elevation="24" :color="snackbar.color" v-model="snackbar.show">
    {{ snackbar.message }}
  </v-snackbar>
</template>
