<template>
    <div class="persona-page">
        <v-container fluid class="pa-0">
            <!-- 页面标题 -->
            <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-8">
                <div>
                    <h1 class="text-h1 font-weight-bold mb-2">
                        <v-icon color="black" class="me-2">mdi-heart</v-icon>{{ t('core.navigation.persona') }}
                    </h1>
                    <p class="text-subtitle-1 text-medium-emphasis mb-4">
                        {{ tm('page.description') }}
                    </p>
                </div>
                <div>
                    <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openCreateDialog"
                        rounded="xl" size="x-large">
                        {{ tm('buttons.create') }}
                    </v-btn>
                </div>
            </v-row>


            <!-- 人格卡片网格 -->
            <v-row>
                <v-col v-for="persona in personas" :key="persona.persona_id" cols="12" md="6" lg="4" xl="3">
                    <v-card class="persona-card" rounded="md" @click="viewPersona(persona)">
                        <v-card-title class="d-flex justify-space-between align-center">
                            <div class="text-truncate ml-2">
                                {{ persona.persona_id }}
                            </div>
                            <v-menu offset-y>
                                <template v-slot:activator="{ props }">
                                    <v-btn icon="mdi-dots-vertical" variant="text" size="small" v-bind="props"
                                        @click.stop />
                                </template>
                                <v-list density="compact">
                                    <v-list-item @click="editPersona(persona)">
                                        <v-list-item-title>
                                            <v-icon class="mr-2" size="small">mdi-pencil</v-icon>
                                            {{ tm('buttons.edit') }}
                                        </v-list-item-title>
                                    </v-list-item>
                                    <v-list-item @click="deletePersona(persona)" class="text-error">
                                        <v-list-item-title>
                                            <v-icon class="mr-2" size="small">mdi-delete</v-icon>
                                            {{ tm('buttons.delete') }}
                                        </v-list-item-title>
                                    </v-list-item>
                                </v-list>
                            </v-menu>
                        </v-card-title>

                        <v-card-text>
                            <div class="system-prompt-preview">
                                {{ truncateText(persona.system_prompt, 100) }}
                            </div>

                            <div class="mt-3" v-if="persona.begin_dialogs && persona.begin_dialogs.length > 0">
                                <v-chip size="small" color="secondary" variant="tonal" prepend-icon="mdi-chat">
                                    {{ tm('labels.presetDialogs', { count: persona.begin_dialogs.length / 2 }) }}
                                </v-chip>
                            </div>

                            <div class="mt-3 text-caption text-medium-emphasis">
                                {{ tm('labels.createdAt') }}: {{ formatDate(persona.created_at) }}
                            </div>
                        </v-card-text>
                    </v-card>
                </v-col>

                <!-- 空状态 -->
                <v-col v-if="personas.length === 0 && !loading" cols="12">
                    <v-card class="text-center pa-8" elevation="0">
                        <v-icon size="64" color="grey-lighten-1" class="mb-4">mdi-account-group</v-icon>
                        <h3 class="text-h5 mb-2">{{ tm('empty.title') }}</h3>
                        <p class="text-body-1 text-medium-emphasis mb-4">{{ tm('empty.description') }}</p>
                        <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openCreateDialog">
                            {{ tm('buttons.createFirst') }}
                        </v-btn>
                    </v-card>
                </v-col>
            </v-row>

            <!-- 加载状态 -->
            <v-row v-if="loading">
                <v-col v-for="n in 6" :key="n" cols="12" md="6" lg="4" xl="3">
                    <v-skeleton-loader type="card" rounded="lg"></v-skeleton-loader>
                </v-col>
            </v-row>
        </v-container>

        <!-- 创建/编辑人格对话框 -->
        <PersonaForm 
            v-model="showPersonaDialog"
            :editing-persona="editingPersona"
            @saved="handlePersonaSaved"
            @error="showError" />

        <!-- 查看人格详情对话框 -->
        <v-dialog v-model="showViewDialog" max-width="700px">
            <v-card v-if="viewingPersona">
                <v-card-title class="d-flex justify-space-between align-center">
                    <span class="text-h5">{{ viewingPersona.persona_id }}</span>
                    <v-btn icon="mdi-close" variant="text" @click="showViewDialog = false" />
                </v-card-title>

                <v-card-text>
                    <div class="mb-4">
                        <h4 class="text-h6 mb-2">{{ tm('form.systemPrompt') }}</h4>
                        <pre class="system-prompt-content">
                            {{ viewingPersona.system_prompt }}
                        </pre>
                    </div>

                    <div v-if="viewingPersona.begin_dialogs && viewingPersona.begin_dialogs.length > 0" class="mb-4">
                        <h4 class="text-h6 mb-2">{{ tm('form.presetDialogs') }}</h4>
                        <div v-for="(dialog, index) in viewingPersona.begin_dialogs" :key="index" class="mb-2">
                            <v-chip :color="index % 2 === 0 ? 'primary' : 'secondary'" variant="tonal" size="small"
                                class="mb-1">
                                {{ index % 2 === 0 ? tm('form.userMessage') : tm('form.assistantMessage') }}
                            </v-chip>
                            <div class="dialog-content ml-2">
                                {{ dialog }}
                            </div>
                        </div>
                    </div>

                    <div class="mb-4">
                        <h4 class="text-h6 mb-2">{{ tm('form.tools') }}</h4>
                        <div v-if="viewingPersona.tools === null" class="text-body-2 text-medium-emphasis">
                            <v-chip size="small" color="success" variant="tonal" prepend-icon="mdi-check-all">
                                {{ tm('form.allToolsAvailable') }}
                            </v-chip>
                        </div>
                        <div v-else-if="viewingPersona.tools && viewingPersona.tools.length > 0"
                            class="d-flex flex-wrap ga-1">
                            <v-chip v-for="toolName in viewingPersona.tools" :key="toolName" size="small"
                                color="primary" variant="tonal">
                                {{ toolName }}
                            </v-chip>
                        </div>
                        <div v-else class="text-body-2 text-medium-emphasis">
                            {{ tm('form.noToolsSelected') }}
                        </div>
                    </div>

                    <div class="text-caption text-medium-emphasis">
                        <div>{{ tm('labels.createdAt') }}: {{ formatDate(viewingPersona.created_at) }}</div>
                        <div v-if="viewingPersona.updated_at">{{ tm('labels.updatedAt') }}: {{
                            formatDate(viewingPersona.updated_at) }}</div>
                    </div>
                </v-card-text>
            </v-card>
        </v-dialog>

        <!-- 消息提示 -->
        <v-snackbar :timeout="3000" elevation="24" :color="messageType" v-model="showMessage" location="top">
            {{ message }}
        </v-snackbar>
    </div>
</template>

<script>
import axios from 'axios';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import PersonaForm from '@/components/shared/PersonaForm.vue';

export default {
    name: 'PersonaPage',
    components: {
        PersonaForm
    },
    setup() {
        const { t } = useI18n();
        const { tm } = useModuleI18n('features/persona');
        return { t, tm };
    },
    data() {
        return {
            personas: [],
            loading: false,
            showPersonaDialog: false,
            showViewDialog: false,
            editingPersona: null,
            viewingPersona: null,
            showMessage: false,
            message: '',
            messageType: 'success'
        }
    },

    mounted() {
        this.loadPersonas();
    },

    methods: {
        async loadPersonas() {
            this.loading = true;
            try {
                const response = await axios.get('/api/persona/list');
                if (response.data.status === 'ok') {
                    this.personas = response.data.data;
                } else {
                    this.showError(response.data.message || this.tm('messages.loadError'));
                }
            } catch (error) {
                this.showError(error.response?.data?.message || this.tm('messages.loadError'));
            }
            this.loading = false;
        },

        openCreateDialog() {
            this.editingPersona = null;
            this.showPersonaDialog = true;
        },

        editPersona(persona) {
            this.editingPersona = persona;
            this.showPersonaDialog = true;
        },

        viewPersona(persona) {
            this.viewingPersona = persona;
            this.showViewDialog = true;
        },

        handlePersonaSaved(message) {
            this.showSuccess(message);
            this.loadPersonas();
        },

        async deletePersona(persona) {
            if (!confirm(this.tm('messages.deleteConfirm', { id: persona.persona_id }))) {
                return;
            }

            try {
                const response = await axios.post('/api/persona/delete', {
                    persona_id: persona.persona_id
                });

                if (response.data.status === 'ok') {
                    this.showSuccess(response.data.message || this.tm('messages.deleteSuccess'));
                    await this.loadPersonas();
                } else {
                    this.showError(response.data.message || this.tm('messages.deleteError'));
                }
            } catch (error) {
                this.showError(error.response?.data?.message || this.tm('messages.deleteError'));
            }
        },

        truncateText(text, maxLength) {
            if (!text) return '';
            return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
        },

        formatDate(dateString) {
            if (!dateString) return '';
            return new Date(dateString).toLocaleString();
        },

        showSuccess(message) {
            this.message = message;
            this.messageType = 'success';
            this.showMessage = true;
        },

        showError(message) {
            this.message = message;
            this.messageType = 'error';
            this.showMessage = true;
        }
    }
}
</script>

<style scoped>
.persona-page {
    padding: 20px;
    padding-top: 8px;
}

.persona-card {
    transition: all 0.3s ease;
    height: 100%;
    cursor: pointer;
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

.system-prompt-content {
    max-height: 400px;
    overflow: auto;
    padding: 12px;
    border-radius: 8px;
    font-size: 14px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
}

.dialog-content {
    background-color: rgba(var(--v-theme-surface-variant), 0.3);
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 14px;
    line-height: 1.4;
    margin-bottom: 8px;
    white-space: pre-wrap;
    word-break: break-word;
}
</style>
