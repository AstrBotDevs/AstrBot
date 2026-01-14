<template>
    <v-dialog v-model="isOpen" max-width="600">
        <v-card>
            <v-card-title class="d-flex justify-space-between align-center">
                <span>{{ tm('multiChat.selectSessions') }}</span>
                <v-btn icon="mdi-close" variant="text" @click="close" />
            </v-card-title>
            
            <v-card-text>
                <div class="mb-3 text-subtitle-2 text-medium-emphasis">
                    {{ tm('multiChat.selectTip') }}
                </div>
                
                <v-list density="compact" class="session-select-list">
                    <v-list-item 
                        v-for="session in sessions" 
                        :key="session.session_id"
                        @click="toggleSession(session.session_id)"
                        :class="{ 'selected-session': isSelected(session.session_id) }"
                        class="session-item"
                    >
                        <template v-slot:prepend>
                            <v-checkbox
                                :model-value="isSelected(session.session_id)"
                                hide-details
                                class="session-checkbox"
                                @click.stop="toggleSession(session.session_id)"
                            />
                        </template>
                        
                        <v-list-item-title>
                            {{ session.display_name || tm('conversation.newConversation') }}
                        </v-list-item-title>
                        
                        <v-list-item-subtitle class="text-caption">
                            {{ new Date(session.updated_at).toLocaleString() }}
                        </v-list-item-subtitle>
                    </v-list-item>
                </v-list>
                
                <div v-if="sessions.length === 0" class="text-center py-8 text-medium-emphasis">
                    <v-icon size="48" color="grey-lighten-1">mdi-message-text-outline</v-icon>
                    <div class="mt-2">{{ tm('conversation.noHistory') }}</div>
                </div>
            </v-card-text>
            
            <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn variant="text" @click="close">{{ t('core.common.cancel') }}</v-btn>
                <v-btn 
                    variant="text" 
                    color="primary" 
                    @click="confirm"
                    :disabled="selectedSessionIds.length < 2"
                >
                    {{ tm('multiChat.enterMultiMode') }} ({{ selectedSessionIds.length }})
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import type { Session } from '@/composables/useSessions';

interface Props {
    modelValue: boolean;
    sessions: Session[];
}

const props = defineProps<Props>();

const emit = defineEmits<{
    'update:modelValue': [value: boolean];
    'confirm': [sessionIds: string[]];
}>();

const { t } = useI18n();
const { tm } = useModuleI18n('features/chat');

const isOpen = ref(props.modelValue);
const selectedSessionIds = ref<string[]>([]);

watch(() => props.modelValue, (newVal) => {
    isOpen.value = newVal;
    if (newVal) {
        selectedSessionIds.value = [];
    }
});

watch(isOpen, (newVal) => {
    emit('update:modelValue', newVal);
});

function isSelected(sessionId: string): boolean {
    return selectedSessionIds.value.includes(sessionId);
}

function toggleSession(sessionId: string) {
    const index = selectedSessionIds.value.indexOf(sessionId);
    if (index > -1) {
        selectedSessionIds.value.splice(index, 1);
    } else {
        selectedSessionIds.value.push(sessionId);
    }
}

function close() {
    isOpen.value = false;
}

function confirm() {
    if (selectedSessionIds.value.length >= 2) {
        emit('confirm', [...selectedSessionIds.value]);
        close();
    }
}
</script>

<style scoped>
.session-select-list {
    max-height: 400px;
    overflow-y: auto;
}

.session-item {
    cursor: pointer;
    transition: background-color 0.2s;
    border-radius: 8px;
    margin-bottom: 4px;
}

.session-item:hover {
    background-color: rgba(0, 0, 0, 0.04);
}

.selected-session {
    background-color: rgba(103, 58, 183, 0.08);
}

.selected-session:hover {
    background-color: rgba(103, 58, 183, 0.12);
}

.session-checkbox {
    flex: 0 0 auto;
}
</style>
