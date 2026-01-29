<template>
    <v-card class="persona-card" :class="{ 'dragging': isDragging }" rounded="lg" @click="$emit('view')" elevation="1" hover
        draggable="true" @dragstart="handleDragStart" @dragend="handleDragEnd">
        <v-card-title class="d-flex justify-space-between align-center">
            <div class="text-truncate ml-2">{{ persona.persona_id }}</div>
            <v-menu offset-y>
                <template v-slot:activator="{ props }">
                    <v-btn icon="mdi-dots-vertical" variant="text" size="small" v-bind="props" @click.stop />
                </template>
                <v-list density="compact">
                    <v-list-item @click.stop="$emit('edit')">
                        <template v-slot:prepend>
                            <v-icon size="small">mdi-pencil</v-icon>
                        </template>
                        <v-list-item-title>{{ tm('buttons.edit') }}</v-list-item-title>
                    </v-list-item>
                    <v-list-item @click.stop="$emit('move')">
                        <template v-slot:prepend>
                            <v-icon size="small">mdi-folder-move</v-icon>
                        </template>
                        <v-list-item-title>{{ tm('persona.contextMenu.moveTo') }}</v-list-item-title>
                    </v-list-item>
                    <v-divider class="my-1" />
                    <v-list-item @click.stop="$emit('delete')" class="text-error">
                        <template v-slot:prepend>
                            <v-icon size="small" color="error">mdi-delete</v-icon>
                        </template>
                        <v-list-item-title>{{ tm('buttons.delete') }}</v-list-item-title>
                    </v-list-item>
                </v-list>
            </v-menu>
        </v-card-title>

        <v-card-text>
            <div class="system-prompt-preview">
                {{ truncateText(persona.system_prompt, 100) }}
            </div>

            <div class="mt-3 d-flex flex-wrap ga-1">
                <v-chip v-if="persona.begin_dialogs && persona.begin_dialogs.length > 0" size="small" color="secondary"
                    variant="tonal" prepend-icon="mdi-chat">
                    {{ tm('labels.presetDialogs', { count: persona.begin_dialogs.length / 2 }) }}
                </v-chip>
                <v-chip v-if="persona.tools === null" size="small" color="success" variant="tonal"
                    prepend-icon="mdi-tools">
                    {{ tm('form.allToolsAvailable') }}
                </v-chip>
                <v-chip v-else-if="persona.tools && persona.tools.length > 0" size="small" color="primary" variant="tonal"
                    prepend-icon="mdi-tools">
                    {{ persona.tools.length }} {{ tm('persona.toolsCount') }}
                </v-chip>
                <v-chip v-if="persona.skills === null" size="small" color="success" variant="tonal"
                    prepend-icon="mdi-lightning-bolt">
                    {{ tm('form.allSkillsAvailable') }}
                </v-chip>
                <v-chip v-else-if="persona.skills && persona.skills.length > 0" size="small" color="primary"
                    variant="tonal" prepend-icon="mdi-lightning-bolt">
                    {{ persona.skills.length }} {{ tm('persona.skillsCount') }}
                </v-chip>
            </div>

            <div class="mt-3 text-caption text-medium-emphasis">
                {{ tm('labels.createdAt') }}: {{ formatDate(persona.created_at) }}
            </div>
        </v-card-text>
    </v-card>

    <!-- Custom Drag Preview -->
    <div ref="dragPreview" class="drag-preview">
        <v-icon size="small" class="mr-2">mdi-account</v-icon>
        <span class="text-subtitle-2">{{ persona.persona_id }}</span>
    </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';
import { useModuleI18n } from '@/i18n/composables';

interface Persona {
    persona_id: string;
    system_prompt: string;
    begin_dialogs?: string[] | null;
    tools?: string[] | null;
    skills?: string[] | null;
    created_at?: string;
    updated_at?: string;
    folder_id?: string | null;
    [key: string]: any;
}

export default defineComponent({
    name: 'PersonaCard',
    props: {
        persona: {
            type: Object as PropType<Persona>,
            required: true
        }
    },
    emits: ['view', 'edit', 'move', 'delete'],
    setup() {
        const { tm } = useModuleI18n('features/persona');
        return { tm };
    },
    data() {
        return {
            isDragging: false
        };
    },
    methods: {
        handleDragStart(event: DragEvent) {
            this.isDragging = true;
            if (event.dataTransfer) {
                event.dataTransfer.effectAllowed = 'move';
                event.dataTransfer.setData('application/json', JSON.stringify({
                    type: 'persona',
                    persona_id: this.persona.persona_id,
                    persona: this.persona
                }));

                // Set custom drag image
                const dragPreview = this.$refs.dragPreview as HTMLElement;
                if (dragPreview) {
                    event.dataTransfer.setDragImage(dragPreview, 15, 15);
                }
            }
        },
        handleDragEnd() {
            this.isDragging = false;
        },
        truncateText(text: string | undefined | null, maxLength: number): string {
            if (!text) return '';
            return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
        },
        formatDate(dateString: string | undefined | null): string {
            if (!dateString) return '';
            return new Date(dateString).toLocaleString();
        }
    }
});
</script>

<style scoped>
.persona-card {
    height: 100%;
    cursor: grab;
    transition: all 0.2s ease;
}

.persona-card:active {
    cursor: grabbing;
}

.persona-card.dragging {
    opacity: 0.5;
    transform: scale(0.95);
}

.persona-card:hover {
    transform: translateY(-2px);
}

.system-prompt-preview {
    font-size: 14px;
    line-height: 1.4;
    color: rgba(var(--v-theme-on-surface), 0.7);
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
}

.drag-preview {
    position: fixed;
    top: -1000px;
    left: -1000px;
    background: rgb(var(--v-theme-surface));
    padding: 12px 20px;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    display: flex;
    align-items: center;
    border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
    z-index: 9999;
    pointer-events: none;
}
</style>
