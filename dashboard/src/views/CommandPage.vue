<script setup lang="ts">
import axios from 'axios';
import { ref, computed, onMounted, reactive } from 'vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';

interface CommandItem {
  handler_full_name: string;
  handler_name: string;
  plugin: string;
  plugin_display_name: string | null;
  module_path: string;
  description: string;
  type: string;  // "command" | "group" | "sub_command"
  parent_signature: string;
  parent_group_handler: string;
  original_command: string;
  current_fragment: string;
  effective_command: string;
  aliases: string[];
  permission: string;
  enabled: boolean;
  is_group: boolean;
  has_conflict: boolean;
  reserved: boolean;  // 是否是系统插件的指令
  sub_commands: CommandItem[];
}

interface CommandSummary {
  disabled: number;
  conflicts: number;
}

const { t } = useI18n();
const { tm } = useModuleI18n('features/command');

const loading = ref(false);
const commands = ref<CommandItem[]>([]);
const summary = reactive<CommandSummary>({
  disabled: 0,
  conflicts: 0
});

const snackbar = reactive({
  show: false,
  message: '',
  color: 'success'
});

const searchQuery = ref('');
const pluginFilter = ref('all');
const permissionFilter = ref('all');
const statusFilter = ref('all');
const typeFilter = ref('all');
const showSystemPlugins = ref(false);

// Track expanded groups
const expandedGroups = ref<Set<string>>(new Set());

// 检查是否有涉及系统插件的冲突
const hasSystemPluginConflict = computed(() => {
  return commands.value.some(cmd => cmd.has_conflict && cmd.reserved);
});

// 实际是否显示系统插件（如果有系统插件冲突则强制显示）
const effectiveShowSystemPlugins = computed(() => {
  return showSystemPlugins.value || hasSystemPluginConflict.value;
});

// Rename dialog
const renameDialog = reactive({
  show: false,
  command: null as CommandItem | null,
  newName: '',
  loading: false
});

// Details dialog
const detailsDialog = reactive({
  show: false,
  command: null as CommandItem | null
});

// Table headers
const commandHeaders = computed(() => [
  { title: tm('table.headers.command'), key: 'effective_command', minWidth: '100px' },
  { title: tm('table.headers.type'), key: 'type', sortable: false, width: '100px' },
  { title: tm('table.headers.plugin'), key: 'plugin', width: '140px' },
  { title: tm('table.headers.description'), key: 'description', sortable: false },
  { title: tm('table.headers.permission'), key: 'permission', sortable: false, width: '100px' },
  { title: tm('table.headers.status'), key: 'enabled', sortable: false, width: '100px' },
  { title: tm('table.headers.actions'), key: 'actions', sortable: false, width: '140px' }
]);

// Computed: unique plugins for filter (排除系统插件，除非显示系统插件)
const availablePlugins = computed(() => {
  const plugins = new Set(
    commands.value
      .filter(cmd => effectiveShowSystemPlugins.value || !cmd.reserved)
      .map(cmd => cmd.plugin)
  );
  return Array.from(plugins).sort();
});

// Helper: check if a command matches filters
const matchesFilters = (cmd: CommandItem, query: string): boolean => {
  // 系统插件过滤（除非显示系统插件）
  if (!effectiveShowSystemPlugins.value && cmd.reserved) {
    return false;
  }

  // Search filter
  if (query) {
    const matchesSearch = 
      cmd.effective_command?.toLowerCase().includes(query) ||
      cmd.description?.toLowerCase().includes(query) ||
      cmd.plugin?.toLowerCase().includes(query);
    if (!matchesSearch) return false;
  }

  // Plugin filter
  if (pluginFilter.value !== 'all' && cmd.plugin !== pluginFilter.value) {
    return false;
  }

  // Permission filter
  if (permissionFilter.value !== 'all') {
    if (permissionFilter.value === 'everyone') {
      if (cmd.permission !== 'everyone' && cmd.permission !== 'member') return false;
    } else if (cmd.permission !== permissionFilter.value) {
      return false;
    }
  }

  // Status filter
  if (statusFilter.value !== 'all') {
    if (statusFilter.value === 'enabled' && !cmd.enabled) return false;
    if (statusFilter.value === 'disabled' && cmd.enabled) return false;
    if (statusFilter.value === 'conflict' && !cmd.has_conflict) return false;
  }

  // Type filter
  if (typeFilter.value !== 'all') {
    if (typeFilter.value === 'group' && cmd.type !== 'group') return false;
    if (typeFilter.value === 'command' && cmd.type !== 'command') return false;
    if (typeFilter.value === 'sub_command' && cmd.type !== 'sub_command') return false;
  }

  return true;
};

// Computed: filtered commands with hierarchy support
const filteredCommands = computed(() => {
  const query = searchQuery.value.toLowerCase();
  const result: CommandItem[] = [];
  const conflictCmds: CommandItem[] = [];
  const normalCmds: CommandItem[] = [];

  for (const cmd of commands.value) {
    // For groups, check if group or any sub-command matches
    if (cmd.is_group) {
      const groupMatches = matchesFilters(cmd, query);
      const matchingSubCmds = (cmd.sub_commands || []).filter(sub => matchesFilters(sub, query));
      
      // If group matches or has matching sub-commands, include it
      if (groupMatches || matchingSubCmds.length > 0) {
        if (cmd.has_conflict) {
          conflictCmds.push(cmd);
        } else {
          normalCmds.push(cmd);
        }
        
        // If group is expanded, add matching sub-commands
        if (expandedGroups.value.has(cmd.handler_full_name)) {
          const subsToShow = query ? matchingSubCmds : (cmd.sub_commands || []);
          for (const sub of subsToShow) {
            if (sub.has_conflict) {
              conflictCmds.push(sub);
            } else {
              normalCmds.push(sub);
            }
          }
        }
      }
    } else if (cmd.type !== 'sub_command') {
      // Regular commands (not sub-commands, they're handled via groups)
      if (matchesFilters(cmd, query)) {
        if (cmd.has_conflict) {
          conflictCmds.push(cmd);
        } else {
          normalCmds.push(cmd);
        }
      }
    }
  }

  // Sort conflicts by effective_command to group them together
  conflictCmds.sort((a, b) => (a.effective_command || '').localeCompare(b.effective_command || ''));

  return [...conflictCmds, ...normalCmds];
});

// Toggle group expansion
const toggleGroupExpand = (cmd: CommandItem) => {
  if (!cmd.is_group) return;
  if (expandedGroups.value.has(cmd.handler_full_name)) {
    expandedGroups.value.delete(cmd.handler_full_name);
  } else {
    expandedGroups.value.add(cmd.handler_full_name);
  }
};

// Check if group is expanded
const isGroupExpanded = (cmd: CommandItem): boolean => {
  return expandedGroups.value.has(cmd.handler_full_name);
};

// Get type display info
const getTypeInfo = (type: string) => {
  switch (type) {
    case 'group':
      return { text: tm('type.group'), color: 'info', icon: 'mdi-folder-outline' };
    case 'sub_command':
      return { text: tm('type.subCommand'), color: 'secondary', icon: 'mdi-subdirectory-arrow-right' };
    default:
      return { text: tm('type.command'), color: 'primary', icon: 'mdi-console-line' };
  }
};

// Toast helper
const toast = (message: string, color: string = 'success') => {
  snackbar.message = message;
  snackbar.color = color;
  snackbar.show = true;
};

// Fetch commands
const fetchCommands = async () => {
  loading.value = true;
  try {
    const res = await axios.get('/api/commands');
    if (res.data.status === 'ok') {
      commands.value = res.data.data.items || [];
      const s = res.data.data.summary || {};
      summary.disabled = s.disabled || 0;
      summary.conflicts = s.conflicts || 0;
    } else {
      toast(res.data.message || tm('messages.loadFailed'), 'error');
    }
  } catch (err: any) {
    toast(err?.message || tm('messages.loadFailed'), 'error');
  } finally {
    loading.value = false;
  }
};

// Toggle command enabled/disabled
const toggleCommand = async (cmd: CommandItem) => {
  try {
    const res = await axios.post('/api/commands/toggle', {
      handler_full_name: cmd.handler_full_name,
      enabled: !cmd.enabled
    });
    if (res.data.status === 'ok') {
      toast(tm('messages.toggleSuccess'), 'success');
      await fetchCommands();
    } else {
      toast(res.data.message || tm('messages.toggleFailed'), 'error');
    }
  } catch (err: any) {
    toast(err?.message || tm('messages.toggleFailed'), 'error');
  }
};

// Open rename dialog
const openRenameDialog = (cmd: CommandItem) => {
  renameDialog.command = cmd;
  renameDialog.newName = cmd.current_fragment || '';
  renameDialog.show = true;
};

// Confirm rename
const confirmRename = async () => {
  if (!renameDialog.command || !renameDialog.newName.trim()) return;

  renameDialog.loading = true;
  try {
    const res = await axios.post('/api/commands/rename', {
      handler_full_name: renameDialog.command.handler_full_name,
      new_name: renameDialog.newName.trim()
    });
    if (res.data.status === 'ok') {
      toast(tm('messages.renameSuccess'), 'success');
      renameDialog.show = false;
      await fetchCommands();
    } else {
      toast(res.data.message || tm('messages.renameFailed'), 'error');
    }
  } catch (err: any) {
    toast(err?.message || tm('messages.renameFailed'), 'error');
  } finally {
    renameDialog.loading = false;
  }
};

// Open details dialog
const openDetailsDialog = (cmd: CommandItem) => {
  detailsDialog.command = cmd;
  detailsDialog.show = true;
};

// Get permission color
const getPermissionColor = (permission: string) => {
  switch (permission) {
    case 'admin': return 'error';
    default: return 'success';
  }
};

// Get permission label
const getPermissionLabel = (permission: string) => {
  switch (permission) {
    case 'admin': return tm('permission.admin');
    default: return tm('permission.everyone');
  }
};

// Get status display
const getStatusInfo = (cmd: CommandItem) => {
  if (cmd.has_conflict) {
    return { text: tm('status.conflict'), color: 'warning', variant: 'flat' as const };
  }
  if (cmd.enabled) {
    return { text: tm('status.enabled'), color: 'success', variant: 'flat' as const };
  }
  return { text: tm('status.disabled'), color: 'error', variant: 'outlined' as const };
};

// Get row props for conflict highlighting and sub-command styling
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

onMounted(async () => {
  await fetchCommands();
});
</script>

<template>
  <v-row>
    <v-col cols="12">
      <v-card variant="flat" style="background-color: transparent">
        <v-card-text style="padding: 0px 12px;">
          <!-- Filters Row (Top) -->
          <v-row class="mb-4" align="center">
            <v-col cols="12" sm="6" md="3">
              <v-select
                v-model="pluginFilter"
                :items="[{ title: tm('filters.all'), value: 'all' }, ...availablePlugins.map(p => ({ title: p, value: p }))]"
                :label="tm('filters.byPlugin')"
                density="compact"
                variant="outlined"
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="6" md="2">
              <v-select
                v-model="typeFilter"
                :items="[
                  { title: tm('filters.all'), value: 'all' },
                  { title: tm('type.group'), value: 'group' },
                  { title: tm('type.command'), value: 'command' },
                  { title: tm('type.subCommand'), value: 'sub_command' }
                ]"
                :label="tm('filters.byType')"
                density="compact"
                variant="outlined"
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="6" md="2">
              <v-select
                v-model="permissionFilter"
                :items="[
                  { title: tm('filters.all'), value: 'all' },
                  { title: tm('permission.everyone'), value: 'everyone' },
                  { title: tm('permission.admin'), value: 'admin' }
                ]"
                :label="tm('filters.byPermission')"
                density="compact"
                variant="outlined"
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="6" md="2">
              <v-select
                v-model="statusFilter"
                :items="[
                  { title: tm('filters.all'), value: 'all' },
                  { title: tm('filters.enabled'), value: 'enabled' },
                  { title: tm('filters.disabled'), value: 'disabled' },
                  { title: tm('filters.conflict'), value: 'conflict' }
                ]"
                :label="tm('filters.byStatus')"
                density="compact"
                variant="outlined"
                hide-details
              />
            </v-col>
          </v-row>

          <!-- Search Bar + Summary Stats Row -->
          <div class="mb-4 d-flex flex-wrap align-center ga-4">
            <div style="min-width: 200px; max-width: 350px; flex: 1; border: 1px solid #B9B9B9; border-radius: 16px;">
              <v-text-field
                v-model="searchQuery"
                density="compact"
                :label="tm('search.placeholder')"
                prepend-inner-icon="mdi-magnify"
                variant="solo-filled"
                flat
                hide-details
                single-line
              />
            </div>
            <div class="d-flex align-center ga-4">
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
              <v-divider vertical class="mx-1" style="height: 20px;" />
              <v-checkbox
                :model-value="effectiveShowSystemPlugins"
                @update:model-value="showSystemPlugins = !!$event"
                :label="tm('filters.showSystemPlugins')"
                density="compact"
                hide-details
                :disabled="hasSystemPluginConflict"
                class="system-plugin-checkbox"
              >
                <template v-slot:label>
                  <span class="text-body-2">{{ tm('filters.showSystemPlugins') }}</span>
                  <v-tooltip v-if="hasSystemPluginConflict" location="top">
                    <template v-slot:activator="{ props }">
                      <v-icon v-bind="props" size="16" color="warning" class="ml-1">mdi-alert-circle</v-icon>
                    </template>
                    {{ tm('filters.systemPluginConflictHint') }}
                  </v-tooltip>
                </template>
              </v-checkbox>
            </div>
          </div>
          
          <!-- Conflict Warning Alert -->
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

          <!-- Commands Table -->
          <v-card class="rounded-lg overflow-hidden elevation-1">
            <v-data-table
              :headers="commandHeaders"
              :items="filteredCommands"
              :loading="loading"
              item-key="handler_full_name"
              hover
              :row-props="getRowProps"
            >
              <template v-slot:loader>
                <v-row class="py-8 d-flex align-center justify-center">
                  <v-progress-circular indeterminate color="primary" />
                  <span class="ml-2">{{ t('core.status.loading') }}</span>
                </v-row>
              </template>

              <template v-slot:item.effective_command="{ item }">
                <div class="d-flex align-center py-2">
                  <!-- Expand/collapse button for groups -->
                  <v-btn
                    v-if="item.is_group && item.sub_commands?.length > 0"
                    icon
                    variant="text"
                    size="x-small"
                    class="mr-1"
                    @click.stop="toggleGroupExpand(item)"
                  >
                    <v-icon size="18">{{ isGroupExpanded(item) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}</v-icon>
                  </v-btn>
                  <!-- Indent for sub-commands -->
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
                      @click="toggleCommand(item)"
                    >
                      <v-icon size="22">mdi-play</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('tooltips.enable') }}</v-tooltip>
                    </v-btn>
                    <v-btn
                      v-else
                      icon
                      size="small"
                      color="error"
                      @click="toggleCommand(item)"
                    >
                      <v-icon size="22">mdi-pause</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('tooltips.disable') }}</v-tooltip>
                    </v-btn>

                    <v-btn icon size="small" color="warning" @click="openRenameDialog(item)">
                      <v-icon size="22">mdi-pencil</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('tooltips.rename') }}</v-tooltip>
                    </v-btn>

                    <v-btn icon size="small" @click="openDetailsDialog(item)">
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
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>

  <!-- Rename Dialog -->
  <v-dialog v-model="renameDialog.show" max-width="500">
    <v-card>
      <v-card-title class="text-h5">{{ tm('dialogs.rename.title') }}</v-card-title>
      <v-card-text>
        <v-text-field
          v-model="renameDialog.newName"
          :label="tm('dialogs.rename.newName')"
          variant="outlined"
          density="compact"
          autofocus
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="grey" variant="text" @click="renameDialog.show = false">
          {{ tm('dialogs.rename.cancel') }}
        </v-btn>
        <v-btn
          color="primary"
          variant="text"
          :loading="renameDialog.loading"
          @click="confirmRename"
        >
          {{ tm('dialogs.rename.confirm') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Details Dialog -->
  <v-dialog v-model="detailsDialog.show" max-width="500">
    <v-card v-if="detailsDialog.command">
      <v-card-title class="text-h5">{{ tm('dialogs.details.title') }}</v-card-title>
      <v-card-text>
        <v-list density="compact">
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.type') }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip
                :color="getTypeInfo(detailsDialog.command.type).color"
                size="small"
                variant="tonal"
              >
                <v-icon start size="14">{{ getTypeInfo(detailsDialog.command.type).icon }}</v-icon>
                {{ getTypeInfo(detailsDialog.command.type).text }}
              </v-chip>
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.handler') }}</v-list-item-title>
            <v-list-item-subtitle><code>{{ detailsDialog.command.handler_name }}</code></v-list-item-subtitle>
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.module') }}</v-list-item-title>
            <v-list-item-subtitle><code>{{ detailsDialog.command.module_path }}</code></v-list-item-subtitle>
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.originalCommand') }}</v-list-item-title>
            <v-list-item-subtitle><code>{{ detailsDialog.command.original_command }}</code></v-list-item-subtitle>
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.effectiveCommand') }}</v-list-item-title>
            <v-list-item-subtitle><code>{{ detailsDialog.command.effective_command }}</code></v-list-item-subtitle>
          </v-list-item>
          <v-list-item v-if="detailsDialog.command.parent_signature">
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.parentGroup') }}</v-list-item-title>
            <v-list-item-subtitle><code>{{ detailsDialog.command.parent_signature }}</code></v-list-item-subtitle>
          </v-list-item>
          <v-list-item v-if="detailsDialog.command.aliases.length > 0">
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.aliases') }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip v-for="alias in detailsDialog.command.aliases" :key="alias" size="small" class="mr-1">
                {{ alias }}
              </v-chip>
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item v-if="detailsDialog.command.is_group && detailsDialog.command.sub_commands?.length > 0">
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.subCommands') }}</v-list-item-title>
            <v-list-item-subtitle>
              <div class="d-flex flex-wrap ga-1 mt-1">
                <v-chip 
                  v-for="sub in detailsDialog.command.sub_commands" 
                  :key="sub.handler_full_name" 
                  size="small"
                  variant="outlined"
                >
                  {{ sub.current_fragment }}
                </v-chip>
              </div>
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.permission') }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip :color="getPermissionColor(detailsDialog.command.permission)" size="small">
                {{ getPermissionLabel(detailsDialog.command.permission) }}
              </v-chip>
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item v-if="detailsDialog.command.has_conflict">
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.conflictStatus') }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip color="warning" size="small">{{ tm('status.conflict') }}</v-chip>
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="primary" variant="text" @click="detailsDialog.show = false">
          {{ t('core.actions.close') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Snackbar -->
  <v-snackbar :timeout="2000" elevation="24" :color="snackbar.color" v-model="snackbar.show">
    {{ snackbar.message }}
  </v-snackbar>
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

.system-plugin-checkbox {
  flex: none;
}

.system-plugin-checkbox :deep(.v-selection-control) {
  min-height: auto;
}
</style>

<style>
/* Conflict row highlighting */
.v-data-table .conflict-row {
  background: linear-gradient(90deg, rgba(var(--v-theme-warning), 0.15) 0%, rgba(var(--v-theme-warning), 0.05) 100%) !important;
  border-left: 3px solid rgb(var(--v-theme-warning)) !important;
}

.v-data-table .conflict-row:hover {
  background: linear-gradient(90deg, rgba(var(--v-theme-warning), 0.25) 0%, rgba(var(--v-theme-warning), 0.1) 100%) !important;
}

/* Group row styling */
.v-data-table .group-row {
  background-color: rgba(var(--v-theme-info), 0.05);
}

.v-data-table .group-row:hover {
  background-color: rgba(var(--v-theme-info), 0.08) !important;
}

/* Sub-command row styling */
.v-data-table .sub-command-row {
  background-color: rgba(var(--v-theme-info), 0.05);
}

.v-data-table .sub-command-row:hover {
  background-color: rgba(var(--v-theme-info), 0.08) !important;
}
</style>
