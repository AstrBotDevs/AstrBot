<template>
    <BaseFolderCard
        :folder="folder"
        :accept-drop-types="['persona']"
        :labels="{
            open: tm('folder.contextMenu.open'),
            rename: tm('folder.contextMenu.rename'),
            moveTo: tm('folder.contextMenu.moveTo'),
            delete: tm('folder.contextMenu.delete')
        }"
        @click="$emit('click')"
        @contextmenu.native.prevent="$emit('contextmenu', $event)"
        @open="$emit('open')"
        @rename="$emit('rename')"
        @move="$emit('move')"
        @delete="$emit('delete')"
        @item-dropped="onItemDropped"
    />
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import BaseFolderCard from '@/components/folder/BaseFolderCard.vue';
import type { Folder } from '@/components/folder/types';

export default defineComponent({
    name: 'FolderCard',
    components: { BaseFolderCard },
    props: {
        folder: {
            type: Object as PropType<Folder>,
            required: true
        }
    },
    emits: ['click', 'contextmenu', 'open', 'rename', 'move', 'delete', 'persona-dropped'],
    setup() {
        const { tm } = useModuleI18n('features/persona');
        return { tm };
    },
    methods: {
        onItemDropped(data: { item_id: string; item_type: string; target_folder_id: string | null; source_data?: any }) {
            if (data.item_type === 'persona') {
                this.$emit('persona-dropped', {
                    persona_id: data.item_id,
                    target_folder_id: data.target_folder_id ?? this.folder.folder_id
                });
            }
        }
    }
});
</script>

<style scoped>
.folder-card {
    cursor: pointer;
    transition: all 0.2s ease;
}

.folder-card:hover {
    transform: translateY(-2px);
}

.folder-card.drag-over {
    background-color: rgba(var(--v-theme-primary), 0.15);
    border: 2px dashed rgb(var(--v-theme-primary));
    transform: scale(1.02);
}

.folder-info {
    min-width: 0;
}
</style>
