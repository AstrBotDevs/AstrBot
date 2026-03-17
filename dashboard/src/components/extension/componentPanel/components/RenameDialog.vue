<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import type { CommandItem } from '../types';

const { tm } = useModuleI18n('features/command');

// Props
const props = defineProps<{
  show: boolean;
  command: CommandItem | null;
  newName: string;
  aliases: string[];
  loading: boolean;
}>();

// Emits
const emit = defineEmits<{
  (e: 'update:show', value: boolean): void;
  (e: 'update:newName', value: string): void;
  (e: 'update:aliases', value: string[]): void;
  (e: 'confirm'): void;
}>();

const addAlias = () => {
  emit('update:aliases', [...props.aliases, '']);
};

const removeAlias = (index: number) => {
  const newAliases = [...props.aliases];
  newAliases.splice(index, 1);
  emit('update:aliases', newAliases);
};

const updateAlias = (index: number, value: string) => {
  const newAliases = [...props.aliases];
  newAliases[index] = value;
  emit('update:aliases', newAliases);
};

const hasAliases = computed(() => (props.aliases || []).some(a => (a ?? '').toString().trim()));
const showAliasEditor = ref(false);
const aliasEditorEverOpened = ref(false);

watch(
  () => props.show,
  (open) => {
    if (!open) return;
    // 如果已有别名则默认展开，否则默认收起
    showAliasEditor.value = hasAliases.value;
  },
);

watch(showAliasEditor, (open) => {
  if (open) aliasEditorEverOpened.value = true;
});
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
          class="mb-2"
        />

        <v-card variant="outlined" class="mt-2" elevation="0">
          <div
            class="d-flex align-center justify-space-between px-4 py-3"
            role="button"
            tabindex="0"
            @click="showAliasEditor = !showAliasEditor"
            @keydown.enter.prevent="showAliasEditor = !showAliasEditor"
            @keydown.space.prevent="showAliasEditor = !showAliasEditor"
          >
            <div class="text-subtitle-1">{{ tm('dialogs.rename.aliases') }}</div>
            <v-icon size="20">{{ showAliasEditor ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
          </div>
          <v-divider v-if="showAliasEditor" />
          <v-slide-y-transition>
            <div v-if="aliasEditorEverOpened" v-show="showAliasEditor" class="px-4 py-3">
              <div v-for="(alias, index) in aliases" :key="index" class="d-flex align-center mb-2">
                <v-text-field
                  :model-value="alias"
                  @update:model-value="updateAlias(index, $event)"
                  variant="outlined"
                  density="compact"
                  hide-details
                  class="flex-grow-1 mr-2"
                />
                <v-btn icon="mdi-delete" variant="text" color="error" density="compact" @click="removeAlias(index)" />
              </div>
              <v-btn
                prepend-icon="mdi-plus"
                variant="outlined"
                color="primary"
                block
                size="small"
                class="mt-2"
                @click="addAlias"
              >
                {{ tm('dialogs.rename.addAlias') }}
              </v-btn>
            </div>
          </v-slide-y-transition>
        </v-card>
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
