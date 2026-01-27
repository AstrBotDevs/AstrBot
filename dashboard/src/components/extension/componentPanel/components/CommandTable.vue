<script setup lang="ts">
import { computed } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import type { CommandItem, TypeInfo, StatusInfo } from '../types';

const { tm } = useModuleI18n('features/command');

// Props
const props = defineProps<{
  items: CommandItem[];
  expandedGroups: Set<string>;
  loading?: boolean;
}>();

// Emits
const emit = defineEmits<{
  (e: 'toggle-expand', cmd: CommandItem): void;
  (e: 'toggle-command', cmd: CommandItem): void;
  (e: 'rename', cmd: CommandItem): void;
  (e: 'view-details', cmd: CommandItem): void;
}>();

// 表格表头
const commandHeaders = computed(() => [
  { title: tm('table.headers.command'), key: 'effective_command', minWidth: '100px' },
  { title: tm('table.headers.type'), key: 'type', sortable: false, width: '100px' },
  { title: tm('table.headers.priority'), key: 'priority', sortable: true, width: '80px' },
  { title: tm('table.headers.plugin'), key: 'plugin', width: '140px' },
  { title: tm('table.headers.description'), key: 'description', sortable: false },
  { title: tm('table.headers.permission'), key: 'permission', sortable: false, width: '100px' },
  { title: tm('table.headers.status'), key: 'enabled', sortable: false, width: '100px' },
  { title: tm('table.headers.actions'), key: 'actions', sortable: false, width: '140px' }
]);

// 检查组是否展开
const isGroupExpanded = (cmd: CommandItem): boolean => {
  return props.expandedGroups.has(cmd.handler_full_name);
};

// 获取类型信息
const getTypeInfo = (type: string): TypeInfo => {
  switch (type) {
    case 'group':
      return { text: tm('type.group'), color: 'info', icon: 'mdi-folder-outline' };
    case 'sub_command':
      return { text: tm('type.subCommand'), color: 'secondary', icon: 'mdi-subdirectory-arrow-right' };
    default:
      return { text: tm('type.command'), color: 'primary', icon: 'mdi-console-line' };
  }
};

// 获取权限颜色
const getPermissionColor = (permission: string): string => {
  switch (permission) {
    case 'admin': return 'error';
    default: return 'success';
  }
};

// 获取权限标签
const getPermissionLabel = (permission: string): string => {
  switch (permission) {
    case 'admin': return tm('permission.admin');
    default: return tm('permission.everyone');
  }
};

// 获取状态信息
const getStatusInfo = (cmd: CommandItem): StatusInfo => {
  if (cmd.has_conflict) {
    return { text: tm('status.conflict'), color: 'warning', variant: 'flat' };
  }
  if (cmd.enabled) {
    return { text: tm('status.enabled'), color: 'success', variant: 'flat' };
  }
  return { text: tm('status.disabled'), color: 'error', variant: 'outlined' };
};

// 获取行属性
const getRowProps = ({ item }: { item: CommandItem }) => {
  const classes: string[] = [];
  if (item.has_conflict) {
    classes.push('conflict-row');
  }
  if (item.type === 'sub_command') {
    classes.push('sub-command-row');
  }
  if (item.is_group) {
    classes.push('group-row');
  }
  return classes.length > 0 ? { class: classes.join(' ') } : {};
};
</script>

<template>
  <v-card class="rounded-lg overflow-hidden elevation-1">
    <v-data-table
      :headers="commandHeaders"
      :items="items"
      item-key="handler_full_name"
      hover
      :row-props="getRowProps"
      :loading="props.loading"
    >
      <template v-slot:item.effective_command="{ item }">
        <div class="d-flex align-center py-2">
          <!-- 展开/折叠按钮（针对指令组） -->
          <v-btn
            v-if="item.is_group && item.sub_commands?.length > 0"
            icon
            variant="text"
            size="x-small"
            class="mr-1"
            @click.stop="emit('toggle-expand', item)"
          >
            <v-icon size="18">{{ isGroupExpanded(item) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
          </v-btn>
          <!-- 子指令缩进 -->
          <div v-else-if="item.type === 'sub_command'" class="ml-6"></div>
          <div>
            <div class="text-subtitle-1 font-weight-medium">
              <code :class="{ 'sub-command-code': item.type === 'sub_command' }">{{ item.effective_command }}</code>
            </div>
          </div>
        </div>
      </template>

      <template v-slot:item.type="{ item }">
        <v-chip
          :color="getTypeInfo(item.type).color"
          size="small"
          variant="tonal"
        >
          <v-icon start size="14">{{ getTypeInfo(item.type).icon }}</v-icon>
          {{ getTypeInfo(item.type).text }}{{ item.is_group && item.sub_commands?.length > 0 ? `(${item.sub_commands.length})` : '' }}
        </v-chip>
      </template>

      <template v-slot:item.priority="{ item }">
        <div class="text-body-2">{{ item.priority ?? 0 }}</div>
      </template>

      <template v-slot:item.plugin="{ item }">
        <div class="text-body-2">{{ item.plugin_display_name || item.plugin }}</div>
      </template>

      <template v-slot:item.description="{ item }">
        <div class="text-body-2 text-medium-emphasis" style="max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          {{ item.description || '-' }}
        </div>
      </template>

      <template v-slot:item.permission="{ item }">
        <v-chip :color="getPermissionColor(item.permission)" size="small" class="font-weight-medium">
          {{ getPermissionLabel(item.permission) }}
        </v-chip>
      </template>

      <template v-slot:item.enabled="{ item }">
        <v-chip
          :color="getStatusInfo(item).color"
          size="small"
          class="font-weight-medium"
          :variant="getStatusInfo(item).variant"
        >
          {{ getStatusInfo(item).text }}
        </v-chip>
      </template>

      <template v-slot:item.actions="{ item }">
        <div class="d-flex align-center">
          <v-btn-group density="default" variant="text" color="primary">
            <v-btn
              v-if="!item.enabled"
              icon
              size="small"
              color="success"
              @click="emit('toggle-command', item)"
            >
              <v-icon size="22">mdi-play</v-icon>
              <v-tooltip activator="parent" location="top">{{ tm('tooltips.enable') }}</v-tooltip>
            </v-btn>
            <v-btn
              v-else
              icon
              size="small"
              color="error"
              @click="emit('toggle-command', item)"
            >
              <v-icon size="22">mdi-pause</v-icon>
              <v-tooltip activator="parent" location="top">{{ tm('tooltips.disable') }}</v-tooltip>
            </v-btn>

            <v-btn icon size="small" color="warning" @click="emit('rename', item)">
              <v-icon size="22">mdi-pencil</v-icon>
              <v-tooltip activator="parent" location="top">{{ tm('tooltips.rename') }}</v-tooltip>
            </v-btn>

            <v-btn icon size="small" @click="emit('view-details', item)">
              <v-icon size="22">mdi-information</v-icon>
              <v-tooltip activator="parent" location="top">{{ tm('tooltips.viewDetails') }}</v-tooltip>
            </v-btn>
          </v-btn-group>
        </div>
      </template>

      <template v-slot:no-data>
        <div class="text-center pa-8">
          <v-icon size="64" color="info" class="mb-4">mdi-console-line</v-icon>
          <div class="text-h5 mb-2">{{ tm('empty.noCommands') }}</div>
          <div class="text-body-1 mb-4">{{ tm('empty.noCommandsDesc') }}</div>
        </div>
      </template>
    </v-data-table>
  </v-card>
</template>

<style scoped>
code {
  background-color: rgba(var(--v-theme-primary), 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
  white-space: nowrap;
}

code.sub-command-code {
  background-color: rgba(var(--v-theme-secondary), 0.1);
  color: rgb(var(--v-theme-secondary));
}
</style>

<style>
/* 冲突行高亮 */
.v-data-table .conflict-row {
  background: linear-gradient(90deg, rgba(var(--v-theme-warning), 0.15) 0%, rgba(var(--v-theme-warning), 0.05) 100%) !important;
  border-left: 3px solid rgb(var(--v-theme-warning)) !important;
}

.v-data-table .conflict-row:hover {
  background: linear-gradient(90deg, rgba(var(--v-theme-warning), 0.25) 0%, rgba(var(--v-theme-warning), 0.1) 100%) !important;
}

/* 指令组行样式 */
.v-data-table .group-row {
  background-color: rgba(var(--v-theme-info), 0.05);
}

.v-data-table .group-row:hover {
  background-color: rgba(var(--v-theme-info), 0.08) !important;
}

/* 子指令行样式 */
.v-data-table .sub-command-row {
  background-color: rgba(var(--v-theme-info), 0.05);
}

.v-data-table .sub-command-row:hover {
  background-color: rgba(var(--v-theme-info), 0.08) !important;
}
</style>

