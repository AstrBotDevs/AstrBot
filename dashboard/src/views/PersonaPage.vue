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
                    <v-card class="persona-card" elevation="2" rounded="lg" @click="viewPersona(persona)">
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
                        <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreateDialog">
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
        <v-dialog v-model="showPersonaDialog" max-width="800px" persistent>
            <v-card>
                <v-card-title class="text-h5">
                    {{ editingPersona ? tm('dialog.edit.title') : tm('dialog.create.title') }}
                </v-card-title>

                <v-card-text>
                    <v-form ref="personaForm" v-model="formValid">
                        <v-text-field v-model="personaForm.persona_id" :label="tm('form.personaId')"
                            :rules="personaIdRules" :disabled="editingPersona" variant="outlined" density="comfortable"
                            class="mb-4" />

                        <v-textarea v-model="personaForm.system_prompt" :label="tm('form.systemPrompt')"
                            :rules="systemPromptRules" variant="outlined" rows="6" class="mb-4" />

                        <v-expansion-panels v-model="expandedPanels" multiple>
                            <v-expansion-panel value="dialogs">
                                <v-expansion-panel-title>
                                    <v-icon class="mr-2">mdi-chat</v-icon>
                                    {{ tm('form.presetDialogs') }}
                                    <v-chip v-if="personaForm.begin_dialogs.length > 0" size="small" color="primary"
                                        variant="tonal" class="ml-2">
                                        {{ personaForm.begin_dialogs.length / 2 }}
                                    </v-chip>
                                </v-expansion-panel-title>

                                <v-expansion-panel-text>
                                    <div class="mb-3">
                                        <p class="text-body-2 text-medium-emphasis">
                                            {{ tm('form.presetDialogsHelp') }}
                                        </p>
                                    </div>

                                    <div v-for="(dialog, index) in personaForm.begin_dialogs" :key="index" class="mb-3">
                                        <v-textarea v-model="personaForm.begin_dialogs[index]"
                                            :label="index % 2 === 0 ? tm('form.userMessage') : tm('form.assistantMessage')"
                                            :rules="getDialogRules(index)"
                                            variant="outlined" rows="2" density="comfortable">
                                            <template v-slot:append>
                                                <v-btn icon="mdi-delete" variant="text" size="small" color="error"
                                                    @click="removeDialog(index)" />
                                            </template>
                                        </v-textarea>
                                    </div>

                                    <v-btn variant="outlined" prepend-icon="mdi-plus" @click="addDialogPair" block>
                                        {{ tm('buttons.addDialogPair') }}
                                    </v-btn>
                                </v-expansion-panel-text>
                            </v-expansion-panel>
                        </v-expansion-panels>
                    </v-form>
                </v-card-text>

                <v-card-actions>
                    <v-spacer />
                    <v-btn color="grey" variant="text" @click="closePersonaDialog">
                        {{ tm('buttons.cancel') }}
                    </v-btn>
                    <v-btn color="primary" variant="flat" @click="savePersona" :loading="saving" :disabled="!formValid">
                        {{ tm('buttons.save') }}
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>

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
                        <div class="system-prompt-content">
                            {{ viewingPersona.system_prompt }}
                        </div>
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

export default {
    name: 'PersonaPage',
    setup() {
        const { t } = useI18n();
        const { tm } = useModuleI18n('features/persona');
        return { t, tm };
    },
    data() {
        return {
            personas: [],
            loading: false,
            saving: false,
            showPersonaDialog: false,
            showViewDialog: false,
            editingPersona: null,
            viewingPersona: null,
            expandedPanels: [],
            formValid: false,
            personaForm: {
                persona_id: '',
                system_prompt: '',
                begin_dialogs: []
            },
            showMessage: false,
            message: '',
            messageType: 'success',
            personaIdRules: [
                v => !!v || this.tm('validation.required'),
                v => (v && v.length >= 2) || this.tm('validation.minLength', { min: 2 }),
                v => /^[a-zA-Z0-9_-]+$/.test(v) || this.tm('validation.alphanumeric')
            ],
            systemPromptRules: [
                v => !!v || this.tm('validation.required'),
                v => (v && v.length >= 10) || this.tm('validation.minLength', { min: 10 })
            ]
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
            this.personaForm = {
                persona_id: '',
                system_prompt: '',
                begin_dialogs: []
            };
            this.expandedPanels = [];
            this.showPersonaDialog = true;
        },

        editPersona(persona) {
            this.editingPersona = persona;
            this.personaForm = {
                persona_id: persona.persona_id,
                system_prompt: persona.system_prompt,
                begin_dialogs: [...(persona.begin_dialogs || [])]
            };
            this.expandedPanels = [];
            this.showPersonaDialog = true;
        },

        viewPersona(persona) {
            this.viewingPersona = persona;
            this.showViewDialog = true;
        },

        closePersonaDialog() {
            this.showPersonaDialog = false;
            this.editingPersona = null;
            this.personaForm = {
                persona_id: '',
                system_prompt: '',
                begin_dialogs: []
            };
        },

        async savePersona() {
            if (!this.formValid) return;

            // 验证预设对话不能为空
            if (this.personaForm.begin_dialogs.length > 0) {
                for (let i = 0; i < this.personaForm.begin_dialogs.length; i++) {
                    if (!this.personaForm.begin_dialogs[i] || this.personaForm.begin_dialogs[i].trim() === '') {
                        const dialogType = i % 2 === 0 ? this.tm('form.userMessage') : this.tm('form.assistantMessage');
                        this.showError(this.tm('validation.dialogRequired', { type: dialogType }));
                        return;
                    }
                }
            }

            this.saving = true;
            try {
                const url = this.editingPersona ? '/api/persona/update' : '/api/persona/create';
                const response = await axios.post(url, this.personaForm);

                if (response.data.status === 'ok') {
                    this.showSuccess(response.data.message || this.tm('messages.saveSuccess'));
                    this.closePersonaDialog();
                    await this.loadPersonas();
                } else {
                    this.showError(response.data.message || this.tm('messages.saveError'));
                }
            } catch (error) {
                this.showError(error.response?.data?.message || this.tm('messages.saveError'));
            }
            this.saving = false;
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

        addDialogPair() {
            this.personaForm.begin_dialogs.push('', '');
            // 自动展开预设对话面板
            if (!this.expandedPanels.includes('dialogs')) {
                this.expandedPanels.push('dialogs');
            }
        },

        removeDialog(index) {
            // 如果是偶数索引（用户消息），删除用户消息和对应的助手消息
            if (index % 2 === 0 && index + 1 < this.personaForm.begin_dialogs.length) {
                this.personaForm.begin_dialogs.splice(index, 2);
            }
            // 如果是奇数索引（助手消息），删除助手消息和对应的用户消息
            else if (index % 2 === 1 && index - 1 >= 0) {
                this.personaForm.begin_dialogs.splice(index - 1, 2);
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
        },

        getDialogRules(index) {
            const dialogType = index % 2 === 0 ? this.tm('form.userMessage') : this.tm('form.assistantMessage');
            return [
                v => !!v || this.tm('validation.dialogRequired', { type: dialogType }),
                v => (v && v.trim().length > 0) || this.tm('validation.dialogRequired', { type: dialogType })
            ];
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

.persona-card:hover {
    box-shadow: 0 8px 25px 0 rgba(0, 0, 0, 0.15);
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
    background-color: rgba(var(--v-theme-surface-variant), 0.3);
    padding: 12px;
    border-radius: 8px;
    font-family: 'Roboto Mono', monospace;
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
