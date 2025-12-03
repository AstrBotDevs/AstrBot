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
  type: string;
  parent_signature: string;
  original_command: string;
  current_fragment: string;
  effective_command: string;
  aliases: string[];
  permission: string;
  enabled: boolean;
  is_group: boolean;
  has_conflict: boolean;
}

interface CommandSummary {
  total: number;
  disabled: number;
  conflicts: number;
}

const { t } = useI18n();
const { tm } = useModuleI18n('features/command');

const loading = ref(false);
const commands = ref<CommandItem[]>([]);
const summary = reactive<CommandSummary>({
  total: 0,
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
  { title: tm('table.headers.command'), key: 'effective_command', width: '180px' },
  { title: tm('table.headers.plugin'), key: 'plugin', width: '140px' },
  { title: tm('table.headers.description'), key: 'description', sortable: false, maxWidth: '260px' },
  { title: tm('table.headers.permission'), key: 'permission', sortable: false, width: '100px' },
  { title: tm('table.headers.status'), key: 'enabled', sortable: false, width: '120px' },
  { title: tm('table.headers.actions'), key: 'actions', sortable: false, width: '160px' }
]);

// Computed: unique plugins for filter
const availablePlugins = computed(() => {
  const plugins = new Set(commands.value.map(cmd => cmd.plugin));
  return Array.from(plugins).sort();
});

// Computed: filtered commands
const filteredCommands = computed(() => {
  let result = commands.value;

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase();
    result = result.filter(cmd =>
      cmd.effective_command?.toLowerCase().includes(query) ||
      cmd.description?.toLowerCase().includes(query) ||
      cmd.plugin?.toLowerCase().includes(query)
    );
  }

  if (pluginFilter.value !== 'all') {
    result = result.filter(cmd => cmd.plugin === pluginFilter.value);
  }

  if (permissionFilter.value !== 'all') {
    result = result.filter(cmd => cmd.permission === permissionFilter.value);
  }

  if (statusFilter.value !== 'all') {
    if (statusFilter.value === 'enabled') {
      result = result.filter(cmd => cmd.enabled);
    } else if (statusFilter.value === 'disabled') {
      result = result.filter(cmd => !cmd.enabled);
    } else if (statusFilter.value === 'conflict') {
      result = result.filter(cmd => cmd.has_conflict);
    }
  }

  // Sort: conflict commands first, grouped by effective_command
  const conflictCmds: CommandItem[] = [];
  const normalCmds: CommandItem[] = [];
  
  const conflictGroupMap: Map<string, CommandItem[]> = new Map();
  for (const cmd of result) {
    if (cmd.has_conflict) {
      const key = cmd.effective_command || '';
      if (!conflictGroupMap.has(key)) {
        conflictGroupMap.set(key, []);
      }
      conflictGroupMap.get(key)!.push(cmd);
    } else {
      normalCmds.push(cmd);
    }
  }
  
  for (const [_, group] of conflictGroupMap) {
    conflictCmds.push(...group);
  }

  return [...conflictCmds, ...normalCmds];
});

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
      summary.total = s.total || 0;
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
    case 'member': return 'warning';
    default: return 'success';
  }
};

// Get permission label
const getPermissionLabel = (permission: string) => {
  switch (permission) {
    case 'admin': return tm('permission.admin');
    case 'member': return tm('permission.member');
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

// Get row props for conflict highlighting
const getRowProps = ({ item }: { item: CommandItem }) => {
  if (item.has_conflict) {
    return { class: 'conflict-row' };
  }
  return {};
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
            <v-col cols="12" sm="4" md="3">
              <v-select
                v-model="pluginFilter"
                :items="[{ title: tm('filters.all'), value: 'all' }, ...availablePlugins.map(p => ({ title: p, value: p }))]"
                :label="tm('filters.byPlugin')"
                density="compact"
                variant="outlined"
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="4" md="3">
              <v-select
                v-model="permissionFilter"
                :items="[
                  { title: tm('filters.all'), value: 'all' },
                  { title: tm('permission.everyone'), value: 'everyone' },
                  { title: tm('permission.admin'), value: 'admin' },
                  { title: tm('permission.member'), value: 'member' }
                ]"
                :label="tm('filters.byPermission')"
                density="compact"
                variant="outlined"
                hide-details
              />
            </v-col>
            <v-col cols="12" sm="4" md="3">
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
                <span class="text-body-1 font-weight-bold text-primary">{{ summary.total }}</span>
              </div>
              <v-divider vertical class="mx-1" style="height: 20px;" />
              <div class="d-flex align-center">
                <v-icon size="18" color="error" class="mr-1">mdi-close-circle-outline</v-icon>
                <span class="text-body-2 text-medium-emphasis mr-1">{{ tm('summary.disabled') }}:</span>
                <span class="text-body-1 font-weight-bold text-error">{{ summary.disabled }}</span>
              </div>
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
                  <div>
                    <div class="text-subtitle-1 font-weight-medium">
                      <code>{{ item.effective_command }}</code>
                    </div>
                  </div>
                </div>
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
          <v-list-item v-if="detailsDialog.command.aliases.length > 0">
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.aliases') }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip v-for="alias in detailsDialog.command.aliases" :key="alias" size="small" class="mr-1">
                {{ alias }}
              </v-chip>
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
</style>
