<script setup lang="ts">
import { useI18n, useModuleI18n } from '@/i18n/composables';
import type { CommandItem } from '@/domain/commands';
import type { TypeInfo } from '../types';

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
      return {
        text: tm('type.group'),
        color: 'info',
        icon: 'mdi-folder-outline',
      };
    case 'sub_command':
      return {
        text: tm('type.subCommand'),
        color: 'secondary',
        icon: 'mdi-subdirectory-arrow-right',
      };
    default:
      return {
        text: tm('type.command'),
        color: 'primary',
        icon: 'mdi-console-line',
      };
  }
};
</script>

<template>
  <v-dialog
    :model-value="show"
    max-width="500"
    scrollable
    @update:model-value="emit('update:show', $event)"
  >
    <v-card v-if="command" class="command-details-dialog">
      <v-card-title class="text-h5">{{
        tm('dialogs.details.title')
      }}</v-card-title>
      <v-card-text class="command-details-dialog__body">
        <v-list density="compact">
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{
              tm('dialogs.details.type')
            }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip
                :color="getTypeInfo(command.type).color"
                size="small"
                variant="tonal"
              >
                <v-icon start size="14">{{
                  getTypeInfo(command.type).icon
                }}</v-icon>
                {{ getTypeInfo(command.type).text }}
              </v-chip>
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{
              tm('dialogs.details.handler')
            }}</v-list-item-title>
            <v-list-item-subtitle
              ><code>{{ command.handler_name }}</code></v-list-item-subtitle
            >
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{
              tm('dialogs.details.module')
            }}</v-list-item-title>
            <v-list-item-subtitle
              ><code>{{ command.module_path }}</code></v-list-item-subtitle
            >
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{
              tm('dialogs.details.originalCommand')
            }}</v-list-item-title>
            <v-list-item-subtitle
              ><code>{{ command.original_command }}</code></v-list-item-subtitle
            >
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{
              tm('dialogs.details.effectiveCommand')
            }}</v-list-item-title>
            <v-list-item-subtitle
              ><code>{{
                command.effective_command
              }}</code></v-list-item-subtitle
            >
          </v-list-item>
          <v-list-item v-if="command.signature">
            <v-list-item-title class="font-weight-bold">{{
              tm('dialogs.details.signature')
            }}</v-list-item-title>
            <v-list-item-subtitle
              ><code>{{ command.signature }}</code></v-list-item-subtitle
            >
          </v-list-item>
          <v-list-item v-if="command.parent_signature">
            <v-list-item-title class="font-weight-bold">{{
              tm('dialogs.details.parentGroup')
            }}</v-list-item-title>
            <v-list-item-subtitle
              ><code>{{ command.parent_signature }}</code></v-list-item-subtitle
            >
          </v-list-item>
          <v-list-item v-if="command.aliases.length > 0">
            <v-list-item-title class="font-weight-bold">{{
              tm('dialogs.details.aliases')
            }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip
                v-for="alias in command.aliases"
                :key="alias"
                size="small"
                class="mr-1"
              >
                {{ alias }}
              </v-chip>
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item
            v-if="command.is_group && command.sub_commands?.length > 0"
          >
            <v-list-item-title class="font-weight-bold">{{
              tm('dialogs.details.subCommands')
            }}</v-list-item-title>
            <v-list-item-subtitle>
              <div class="d-flex flex-wrap ga-1 mt-1">
                <v-chip
                  v-for="sub in command.sub_commands"
                  :key="sub.command_id"
                  size="small"
                  variant="outlined"
                >
                  {{ sub.signature || sub.current_fragment }}
                </v-chip>
              </div>
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item>
            <v-list-item-title class="font-weight-bold">{{
              tm('dialogs.details.action')
            }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip color="primary" size="small" variant="tonal">
                {{ command.action || '—' }}
              </v-chip>
            </v-list-item-subtitle>
          </v-list-item>
          <v-list-item v-if="command.has_conflict">
            <v-list-item-title class="font-weight-bold">{{
              tm('dialogs.details.conflictStatus')
            }}</v-list-item-title>
            <v-list-item-subtitle>
              <v-chip color="warning" size="small">{{
                tm('status.conflict')
              }}</v-chip>
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions class="command-details-dialog__actions">
        <v-spacer />
        <v-btn
          color="primary"
          variant="text"
          @click="emit('update:show', false)"
        >
          {{ t('core.actions.close') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.command-details-dialog {
  display: flex;
  flex-direction: column;
  max-height: min(80vh, 720px);
  overflow: hidden;
}

.command-details-dialog__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

.command-details-dialog__actions {
  flex: 0 0 auto;
}

code {
  background-color: rgba(var(--v-theme-primary), 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}
</style>
