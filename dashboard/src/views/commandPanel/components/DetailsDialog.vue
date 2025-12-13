<script setup lang="ts">
import { useI18n, useModuleI18n } from '@/i18n/composables';
import type { CommandItem, TypeInfo } from '../types';

const { t } = useI18n();
const { tm } = useModuleI18n('features/command');

// Props
defineProps<{
  show: boolean;
  command: CommandItem | null;
}>();

// Emits
const emit = defineEmits<{
  (e: 'update:show', value: boolean): void;
}>();

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
</script>

<template>
  <v-dialog :model-value="show" @update:model-value="emit('update:show', $event)" max-width="500">
    <v-card v-if="command">
      <v-card-title class="text-h5">{{ tm('dialogs.details.title') }}</v-card-title>
      <v-card-text>
        <v-list density="compact">
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.type') }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip
                :color="getTypeInfo(command.type).color"
                size="small"
                variant="tonal"
              >
                <v-icon start size="14">{{ getTypeInfo(command.type).icon }}</v-icon>
                {{ getTypeInfo(command.type).text }}
              </v-chip>
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.handler') }}</v-list-item-title>
            <v-list-item-subtitle><code>{{ command.handler_name }}</code></v-list-item-subtitle>
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.module') }}</v-list-item-title>
            <v-list-item-subtitle><code>{{ command.module_path }}</code></v-list-item-subtitle>
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.originalCommand') }}</v-list-item-title>
            <v-list-item-subtitle><code>{{ command.original_command }}</code></v-list-item-subtitle>
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.effectiveCommand') }}</v-list-item-title>
            <v-list-item-subtitle><code>{{ command.effective_command }}</code></v-list-item-subtitle>
          </v-list-item>
          <v-list-item v-if="command.parent_signature">
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.parentGroup') }}</v-list-item-title>
            <v-list-item-subtitle><code>{{ command.parent_signature }}</code></v-list-item-subtitle>
          </v-list-item>
          <v-list-item v-if="command.aliases.length > 0">
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.aliases') }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip v-for="alias in command.aliases" :key="alias" size="small" class="mr-1">
                {{ alias }}
              </v-chip>
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item v-if="command.is_group && command.sub_commands?.length > 0">
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.subCommands') }}</v-list-item-title>
            <v-list-item-subtitle>
              <div class="d-flex flex-wrap ga-1 mt-1">
                <v-chip 
                  v-for="sub in command.sub_commands" 
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
              <v-chip :color="getPermissionColor(command.permission)" size="small">
                {{ getPermissionLabel(command.permission) }}
              </v-chip>
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item v-if="command.has_conflict">
            <v-list-item-title class="font-weight-bold">{{ tm('dialogs.details.conflictStatus') }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip color="warning" size="small">{{ tm('status.conflict') }}</v-chip>
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="primary" variant="text" @click="emit('update:show', false)">
          {{ t('core.actions.close') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
code {
  background-color: rgba(var(--v-theme-primary), 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}
</style>
