<template>
    <div class="persona-page">
        <v-container fluid class="pa-0">
            <!-- 页面标题 -->
            <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-6">
                <div>
                    <h1 class="text-h1 font-weight-bold mb-2">
                        <v-icon color="black" class="me-2">mdi-heart</v-icon>{{ t('core.navigation.persona') }}
                    </h1>
                    <p class="text-subtitle-1 text-medium-emphasis mb-0">
                        {{ tm('page.description') }}
                    </p>
                </div>
                <div class="d-flex ga-2">
                    <v-btn color="secondary" variant="tonal" prepend-icon="mdi-import" @click="triggerImport"
                        rounded="xl" size="x-large">
                        {{ tm('buttons.import') || '导入' }}
                    </v-btn>
                    <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openCreateDialog"
                        rounded="xl" size="x-large">
                        {{ tm('buttons.create') }}
                    </v-btn>
                    <input type="file" ref="importInput" style="display: none" accept=".json" @change="handleImport">
                </div>
            </v-row>

            <!-- 主容器组件 -->
            <PersonaManager />

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
                                    <v-list-item @click.stop="downloadPersonaJson(persona)">
                                        <v-list-item-title>
                                            <v-icon class="mr-2" size="small">mdi-content-copy</v-icon>
                                            {{ tm('buttons.export') || '导出 JSON' }}
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

            <!-- 主容器组件 -->
            <PersonaManager />
        </v-container>
    </div>
</template>

<script>
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { PersonaManager } from '@/views/persona';

export default {
    name: 'PersonaPage',
    components: {
        PersonaManager
    },
    setup() {
        const { t } = useI18n();
        const { tm } = useModuleI18n('features/persona');
        return { t, tm };
    }
};
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
        },

        async downloadPersonaJson(persona) {
            try {
                // 创建清洁副本，排除系统字段
                const cleanPersona = {
                    persona_id: persona.persona_id,
                    system_prompt: persona.system_prompt,
                    begin_dialogs: persona.begin_dialogs,
                    tools: persona.tools
                };

                // 格式化 JSON
                const jsonString = JSON.stringify(cleanPersona, null, 4);

                // 创建 Blob 对象
                const blob = new Blob([jsonString], { type: 'application/json' });

                // 创建下载链接
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `${persona.persona_id}.json`;

                // 触发下载
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);

                // 清理 URL 对象
                URL.revokeObjectURL(url);

                // 显示成功消息
                this.showSuccess(this.tm('messages.downloadSuccess') || 'JSON 文件已下载');
            } catch (error) {
                // 显示错误消息
                this.showError(error.message || this.tm('messages.downloadError') || '下载 JSON 文件失败');
            }
        },

        triggerImport() {
            this.$refs.importInput.click();
        },

        async handleImport(event) {
            const file = event.target.files[0];
            if (!file) return;

            try {
                const text = await file.text();
    const parsedData = JSON.parse(text);

    console.log("Parsed Data:", parsedData);

    // 验证必需字段
    if (!parsedData.persona_id || !parsedData.system_prompt) {
        this.showError('人格 JSON 缺少必需字段喵！');
        event.target.value = '';
        return;
    }

    // 检查重复 ID
    const id = parsedData.persona_id;
    const exists = this.personas.some(persona => persona.persona_id === id);
    if (exists) {
        this.showError('人格 ID [' + id + '] 已存在喵！');
        event.target.value = '';
        return;
    }

    // 白名单过滤字段
    const allowedFields = ['persona_id', 'system_prompt', 'begin_dialogs', 'tools'];
    const filteredData = {};
    allowedFields.forEach(field => {
        if (parsedData.hasOwnProperty(field)) {
            filteredData[field] = parsedData[field];
        }
    });

    // 调用 API 保存（使用正确的端点）
    const response = await axios.post('/api/persona/create', filteredData);

                if (response.data.status === 'ok') {
                    this.showSuccess(response.data.message || '导入成功喵！');
                    await this.loadPersonas();
                } else {
                    this.showError(response.data.message || '导入失败喵！');
                }
            } catch (error) {
                console.error("Import Error:", error);
                if (error instanceof SyntaxError) {
                    this.showError('JSON 格式错误喵！' + error.message);
                } else {
                    this.showError('导入失败喵！' + (error.response?.data?.message || error.message));
                }
            }

            // 清理文件输入
            event.target.value = '';
        }
    }
};
</script>

<style scoped>
.persona-page {
    padding: 20px;
    padding-top: 8px;
}
</style>
