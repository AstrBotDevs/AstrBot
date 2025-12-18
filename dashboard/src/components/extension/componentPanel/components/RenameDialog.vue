<script setup lang="ts">
import { useModuleI18n } from '@/i18n/composables';
import type { CommandItem } from '../types';

const { tm } = useModuleI18n('features/command');

// Props
defineProps<{
  show: boolean;
  command: CommandItem | null;
  newName: string;
  loading: boolean;
}>();

// Emits
const emit = defineEmits<{
  (e: 'update:show', value: boolean): void;
  (e: 'update:newName', value: string): void;
  (e: 'confirm'): void;
}>();
</script>

<template>
  <v-dialog :model-value="show" @update:model-value="emit('update:show', $event)" max-width="500">
    <v-card>
      <v-card-title class="text-h5">{{ tm('dialogs.rename.title') }}</v-card-title>
      <v-card-text>
        <v-text-field
          :model-value="newName"
          @update:model-value="emit('update:newName', $event)"
          :label="tm('dialogs.rename.newName')"
          variant="outlined"
          density="compact"
          autofocus
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="grey" variant="text" @click="emit('update:show', false)">
          {{ tm('dialogs.rename.cancel') }}
        </v-btn>
        <v-btn
          color="primary"
          variant="text"
          :loading="loading"
          @click="emit('confirm')"
        >
          {{ tm('dialogs.rename.confirm') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
