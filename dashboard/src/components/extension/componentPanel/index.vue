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
import { onMounted, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

// Composables
import { useComponentData } from './composables/useComponentData';
import { useCommandFilters } from './composables/useCommandFilters';
import { useCommandActions } from './composables/useCommandActions';
import { useToolActions } from './composables/useToolActions';

// Components
import CommandFilters from './components/CommandFilters.vue';
import CommandTable from './components/CommandTable.vue';
import ToolTable from './components/ToolTable.vue';
import RenameDialog from './components/RenameDialog.vue';
import DetailsDialog from './components/DetailsDialog.vue';

// Types
import type { CommandItem } from '@/domain/commands';
import type { ToolItem } from '@/domain/tools';

defineOptions({ name: 'ComponentPanel' });
const props = withDefaults(defineProps<{ active?: boolean }>(), {
  active: true,
});

const { tm } = useModuleI18n('features/command');
const { tm: tmTool } = useModuleI18n('features/tooluse');

const viewMode = ref<'commands' | 'tools'>('commands');

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
  fetchTools,
} = useComponentData();

// 过滤逻辑
const {
  searchQuery,
  pluginFilter,
  actionFilter,
  statusFilter,
  typeFilter,
  showSystemPlugins,
  expandedGroups,
  hasSystemPluginConflict,
  effectiveShowSystemPlugins,
  availablePlugins,
  availableActions,
  filteredCommands,
  toggleGroupExpand,
} = useCommandFilters(commands);

// 操作方法
const {
  renameDialog,
  detailsDialog,
  toggleCommand,
  openRenameDialog,
  confirmRename,
  openDetailsDialog,
} = useCommandActions(toast, () => fetchCommands(tm('messages.loadFailed')));

// 工具操作方法
const {
  toolSearch,
  showBuiltinTools,
  filteredTools,
  toolSummary,
  parallelExecutionEnabled,
  toggleTool,
  toggleToolParallel,
  toggleParallelExecution,
} = useToolActions(tools, toast);

// 处理切换指令状态
const handleToggleCommand = async (cmd: CommandItem) => {
  await toggleCommand(
    cmd,
    tm('messages.toggleSuccess'),
    tm('messages.toggleFailed'),
  );
};

const handleToggleTool = async (tool: ToolItem) => {
  await toggleTool(
    tool,
    tmTool('messages.toggleToolReadonly'),
    tmTool('messages.toggleToolSuccess'),
    tmTool('messages.toggleToolError', { error: '' }),
  );
};

const handleToggleToolParallel = async (tool: ToolItem, enabled: boolean) => {
  await toggleToolParallel(
    tool,
    enabled,
    tmTool('functionTools.parallel.blocked'),
  );
};

const handleToggleParallelExecution = async (enabled: boolean) => {
  await toggleParallelExecution(
    enabled,
    tmTool('messages.updateParallelExecutionFailed'),
  );
};

// 处理确认重命名
const handleConfirmRename = async () => {
  await confirmRename(
    tm('messages.renameSuccess'),
    tm('messages.renameFailed'),
  );
};

// 生命周期
onMounted(async () => {
  await Promise.all([
    fetchCommands(tm('messages.loadFailed')),
    fetchTools(tmTool('messages.getToolsError', { error: '' })),
  ]);
});

watch(
  () => props.active,
  async (isActive) => {
    if (!isActive) return;
    if (viewMode.value === 'commands') {
      await fetchCommands(tm('messages.loadFailed'));
    } else {
      await fetchTools(tmTool('messages.getToolsError', { error: '' }));
    }
  },
);

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
      <v-card variant="flat" class="component-panel">
        <v-card-text class="component-panel__body">
          <div
            class="d-flex justify-space-between align-center mb-6 flex-wrap ga-3"
          >
            <v-btn-toggle
              v-model="viewMode"
              color="primary"
              variant="outlined"
              density="comfortable"
              mandatory
            >
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
              class="component-panel__progress"
            />
            <v-progress-linear
              v-else-if="viewMode === 'tools' && toolsLoading"
              indeterminate
              color="primary"
              class="component-panel__progress"
            />
          </div>

          <div v-if="viewMode === 'commands'">
            <CommandFilters
              :plugin-filter="pluginFilter"
              :type-filter="typeFilter"
              :action-filter="actionFilter"
              :available-actions="availableActions"
              :status-filter="statusFilter"
              :show-system-plugins="showSystemPlugins"
              :search-query="searchQuery"
              :available-plugins="availablePlugins"
              :has-system-plugin-conflict="hasSystemPluginConflict"
              :effective-show-system-plugins="effectiveShowSystemPlugins"
              @update:plugin-filter="pluginFilter = $event"
              @update:type-filter="typeFilter = $event"
              @update:action-filter="actionFilter = $event"
              @update:status-filter="statusFilter = $event"
              @update:show-system-plugins="showSystemPlugins = $event"
              @update:search-query="searchQuery = $event"
            >
              <template #stats>
                <div class="d-flex align-center">
                  <v-icon size="18" color="primary" class="mr-1"
                    >mdi-console-line</v-icon
                  >
                  <span class="text-body-2 text-medium-emphasis mr-1"
                    >{{ tm('summary.total') }}:</span
                  >
                  <span class="text-body-1 font-weight-bold text-primary">{{
                    filteredCommands.length
                  }}</span>
                </div>
                <v-divider vertical class="component-summary-divider mx-1" />
                <div class="d-flex align-center">
                  <v-icon size="18" color="error" class="mr-1"
                    >mdi-close-circle-outline</v-icon
                  >
                  <span class="text-body-2 text-medium-emphasis mr-1"
                    >{{ tm('summary.disabled') }}:</span
                  >
                  <span class="text-body-1 font-weight-bold text-error">{{
                    summary.disabled
                  }}</span>
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
              <template #prepend>
                <v-icon size="28">mdi-alert-circle</v-icon>
              </template>
              <v-alert-title class="text-subtitle-1 font-weight-bold">
                {{ tm('conflictAlert.title') }}
              </v-alert-title>
              <div class="text-body-2 mt-1">
                {{
                  tm('conflictAlert.description', { count: summary.conflicts })
                }}
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
            <div class="d-flex flex-wrap align-center ga-4 mb-4">
              <div class="component-panel__tool-search">
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

              <div class="d-flex align-center ga-4">
                <div class="d-flex align-center">
                  <v-icon size="18" color="primary" class="mr-1"
                    >mdi-function-variant</v-icon
                  >
                  <span class="text-body-2 text-medium-emphasis mr-1"
                    >{{ tmTool('functionTools.summary.total') }}:</span
                  >
                  <span class="text-body-1 font-weight-bold text-primary">{{
                    toolSummary.total
                  }}</span>
                </div>
                <v-divider vertical class="component-summary-divider mx-1" />
                <div class="d-flex align-center">
                  <v-icon size="18" color="success" class="mr-1"
                    >mdi-check-circle-outline</v-icon
                  >
                  <span class="text-body-2 text-medium-emphasis mr-1"
                    >{{ tmTool('functionTools.summary.active') }}:</span
                  >
                  <span class="text-body-1 font-weight-bold text-success">{{
                    toolSummary.active
                  }}</span>
                </div>
                <v-divider vertical class="component-summary-divider mx-1" />
                <div class="d-flex align-center">
                  <v-icon size="18" color="error" class="mr-1"
                    >mdi-close-circle-outline</v-icon
                  >
                  <span class="text-body-2 text-medium-emphasis mr-1"
                    >{{ tmTool('functionTools.summary.inactive') }}:</span
                  >
                  <span class="text-body-1 font-weight-bold text-error">{{
                    toolSummary.inactive
                  }}</span>
                </div>

                <v-divider vertical class="component-summary-divider mx-1" />
                <v-checkbox
                  v-model="showBuiltinTools"
                  :label="tmTool('functionTools.filter.showBuiltin')"
                  density="compact"
                  hide-details
                  class="builtin-tools-checkbox"
                />
                <v-switch
                  :model-value="parallelExecutionEnabled"
                  :label="tmTool('functionTools.parallel.enabled')"
                  color="primary"
                  density="compact"
                  hide-details
                  inset
                  @update:model-value="
                    handleToggleParallelExecution($event === true)
                  "
                />
              </div>
            </div>

            <ToolTable
              :items="filteredTools"
              :loading="toolsLoading"
              @toggle-tool="handleToggleTool"
              @toggle-parallel="handleToggleToolParallel"
            />
          </div>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>

  <!-- 重命名对话框 -->
  <RenameDialog
    :show="renameDialog.show"
    :new-name="renameDialog.newName"
    :aliases="renameDialog.aliases"
    :command="renameDialog.command"
    :loading="renameDialog.loading"
    @update:show="renameDialog.show = $event"
    @update:new-name="renameDialog.newName = $event"
    @update:aliases="renameDialog.aliases = $event"
    @confirm="handleConfirmRename"
  />

  <!-- 详情对话框 -->
  <DetailsDialog
    :show="detailsDialog.show"
    :command="detailsDialog.command"
    @update:show="detailsDialog.show = $event"
  />

  <!-- Snackbar -->
  <v-snackbar
    :timeout="2000"
    elevation="4"
    :color="snackbar.color"
    v-model="snackbar.show"
  >
    {{ snackbar.message }}
  </v-snackbar>
</template>

<style scoped>
.builtin-tools-checkbox {
  flex: none;
}

.component-panel {
  background: transparent;
}

.component-panel__body {
  padding: 0 var(--astrbot-space-3) var(--astrbot-space-4);
}

.component-panel__progress {
  flex: 1;
  max-width: 220px;
}

.component-summary-divider {
  height: 20px;
}

.component-panel__tool-search {
  min-width: 240px;
  max-width: 380px;
  flex: 1;
}
</style>
