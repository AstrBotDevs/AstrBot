<template>
  <v-card
    class="base-folder-card"
    :class="{ 'drag-over': isDragOver }"
    rounded="md"
    elevation="0"
    @click="emit('click')"
    @contextmenu.prevent="emit('contextmenu', $event)"
    @dragover.prevent="handleDragOver"
    @dragleave="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <v-card-text class="d-flex align-center pa-3">
      <v-icon size="40" color="amber-darken-2" class="mr-3">mdi-folder</v-icon>
      <div class="folder-info flex-grow-1 overflow-hidden">
        <div class="text-subtitle-1 font-weight-medium text-truncate">
          {{ folder.name }}
        </div>
        <div
          v-if="folder.description"
          class="text-body-2 text-medium-emphasis text-truncate"
        >
          {{ folder.description }}
        </div>
      </div>
      <v-menu offset-y>
        <template #activator="{ props: activatorProps }">
          <v-btn
            icon="mdi-dots-vertical"
            variant="text"
            size="small"
            v-bind="activatorProps"
            @click.stop
          />
        </template>
        <v-list density="compact">
          <v-list-item @click.stop="emit('open')">
            <template #prepend>
              <v-icon size="small">mdi-folder-open</v-icon>
            </template>
            <v-list-item-title>{{ mergedLabels.open }}</v-list-item-title>
          </v-list-item>
          <v-list-item @click.stop="emit('rename')">
            <template #prepend>
              <v-icon size="small">mdi-pencil</v-icon>
            </template>
            <v-list-item-title>{{ mergedLabels.rename }}</v-list-item-title>
          </v-list-item>
          <v-list-item @click.stop="emit('move')">
            <template #prepend>
              <v-icon size="small">mdi-folder-move</v-icon>
            </template>
            <v-list-item-title>{{ mergedLabels.moveTo }}</v-list-item-title>
          </v-list-item>
          <v-divider class="my-1" />
          <v-list-item class="text-error" @click.stop="emit('delete')">
            <template #prepend>
              <v-icon size="small" color="error">mdi-delete</v-icon>
            </template>
            <v-list-item-title>{{ mergedLabels.delete }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { Folder } from './types';

interface DefaultLabels {
  open: string;
  rename: string;
  moveTo: string;
  delete: string;
}

const defaultLabels: DefaultLabels = {
  open: '打开',
  rename: '重命名',
  moveTo: '移动到...',
  delete: '删除',
};

type DropPayload = {
  id?: string;
  item_id?: string;
  persona_id?: string;
  type?: string;
};

const props = withDefaults(
  defineProps<{
    folder: Folder;
    acceptDropTypes?: string[];
    labels?: Partial<DefaultLabels>;
  }>(),
  {
    acceptDropTypes: () => [],
    labels: () => ({}),
  },
);

const emit = defineEmits<{
  click: [];
  contextmenu: [event: MouseEvent];
  open: [];
  rename: [];
  move: [];
  delete: [];
  'item-dropped': [
    payload: {
      item_id: string;
      item_type: string;
      target_folder_id: string;
      source_data: DropPayload;
    },
  ];
}>();

const isDragOver = ref(false);

const mergedLabels = computed<DefaultLabels>(() => ({
  ...defaultLabels,
  ...props.labels,
}));

function handleDragOver(event: DragEvent) {
  if (!event.dataTransfer) {
    return;
  }
  event.dataTransfer.dropEffect = 'move';
  isDragOver.value = true;
}

function handleDragLeave() {
  isDragOver.value = false;
}

function handleDrop(event: DragEvent) {
  isDragOver.value = false;
  if (!event.dataTransfer) {
    return;
  }

  try {
    const data = JSON.parse(
      event.dataTransfer.getData('application/json'),
    ) as DropPayload;
    const itemType = data.type;
    const itemId = data.id ?? data.persona_id ?? data.item_id;
    if (
      !itemType ||
      !itemId ||
      (props.acceptDropTypes.length > 0 &&
        !props.acceptDropTypes.includes(itemType))
    ) {
      return;
    }
    emit('item-dropped', {
      item_id: itemId,
      item_type: itemType,
      target_folder_id: props.folder.folder_id,
      source_data: data,
    });
  } catch (error) {
    console.error('Failed to parse drop data:', error);
  }
}
</script>

<style scoped>
.base-folder-card {
  cursor: pointer;
  transition: all 0.2s ease;
}

.base-folder-card.drag-over {
  background-color: rgba(var(--v-theme-primary), 0.15);
  border: 2px dashed rgb(var(--v-theme-primary));
  transform: scale(1.02);
}

.folder-info {
  min-width: 0;
}
</style>
