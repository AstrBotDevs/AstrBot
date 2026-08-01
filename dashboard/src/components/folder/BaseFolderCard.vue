<template>
  <v-card
    class="base-folder-card"
    :class="{ 'drag-over': isDragOver }"
    variant="flat"
    @click="$emit('click')"
    @contextmenu.prevent="$emit('contextmenu', $event)"
    @dragover.prevent="handleDragOver"
    @dragleave="handleDragLeave"
    @drop.prevent="handleDrop"
  >
    <v-card-text class="d-flex align-center pa-3 px-4">
      <v-icon size="20" class="mr-3 folder-icon">mdi-folder-outline</v-icon>
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
        <template v-slot:activator="{ props }">
          <v-btn
            icon="mdi-dots-vertical"
            variant="text"
            size="small"
            v-bind="props"
            @click.stop
          />
        </template>
        <v-list density="compact">
          <v-list-item @click.stop="$emit('open')">
            <template v-slot:prepend>
              <v-icon size="small">mdi-folder-open</v-icon>
            </template>
            <v-list-item-title>{{ mergedLabels.open }}</v-list-item-title>
          </v-list-item>
          <v-list-item @click.stop="$emit('rename')">
            <template v-slot:prepend>
              <v-icon size="small">mdi-pencil</v-icon>
            </template>
            <v-list-item-title>{{ mergedLabels.rename }}</v-list-item-title>
          </v-list-item>
          <v-list-item @click.stop="$emit('move')">
            <template v-slot:prepend>
              <v-icon size="small">mdi-folder-move</v-icon>
            </template>
            <v-list-item-title>{{ mergedLabels.moveTo }}</v-list-item-title>
          </v-list-item>
          <v-divider class="my-1" />
          <v-list-item @click.stop="$emit('delete')" class="text-error">
            <template v-slot:prepend>
              <v-icon size="small" color="error">mdi-delete</v-icon>
            </template>
            <v-list-item-title>{{ mergedLabels.delete }}</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </v-card-text>
  </v-card>
</template>

<script lang="ts">
import { defineComponent, type PropType } from "vue";
import type { Folder } from "./types";

interface DefaultLabels {
  open: string;
  rename: string;
  moveTo: string;
  delete: string;
}

const defaultLabels: DefaultLabels = {
  open: "打开",
  rename: "重命名",
  moveTo: "移动到...",
  delete: "删除",
};

export default defineComponent({
  name: "BaseFolderCard",
  props: {
    folder: {
      type: Object as PropType<Folder>,
      required: true,
    },
    acceptDropTypes: {
      type: Array as PropType<string[]>,
      default: () => [],
    },
    labels: {
      type: Object as PropType<Partial<DefaultLabels>>,
      default: () => ({}),
    },
  },
  emits: [
    "click",
    "contextmenu",
    "open",
    "rename",
    "move",
    "delete",
    "item-dropped",
  ],
  data() {
    return {
      isDragOver: false,
    };
  },
  computed: {
    mergedLabels(): DefaultLabels {
      return { ...defaultLabels, ...this.labels };
    },
  },
  methods: {
    handleDragOver(event: DragEvent) {
      if (!event.dataTransfer) return;
      event.dataTransfer.dropEffect = "move";
      this.isDragOver = true;
    },
    handleDragLeave() {
      this.isDragOver = false;
    },
    handleDrop(event: DragEvent) {
      this.isDragOver = false;
      if (!event.dataTransfer) return;

      try {
        const data = JSON.parse(event.dataTransfer.getData("application/json"));
        if (
          this.acceptDropTypes.length === 0 ||
          this.acceptDropTypes.includes(data.type)
        ) {
          this.$emit("item-dropped", {
            item_id: data.id || data.persona_id || data.item_id,
            item_type: data.type,
            target_folder_id: this.folder.folder_id,
            source_data: data,
          });
        }
      } catch (e) {
        console.error("Failed to parse drop data:", e);
      }
    },
  },
});
</script>

<style scoped>
.base-folder-card {
  height: 100%;
  cursor: pointer;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.11);
  border-radius: 10px;
  transition: background-color 0.12s ease;
}

.base-folder-card:hover {
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.base-folder-card.drag-over {
  background-color: rgba(var(--v-theme-on-surface), 0.07);
  border-style: dashed;
}

.folder-info {
  min-width: 0;
}

.folder-icon {
  color: rgba(var(--v-theme-on-surface), 0.58);
}
</style>
