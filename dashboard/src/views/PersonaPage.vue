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
        <v-dialog v-model="showPersonaDialog" max-width="800px" persistent>
            <v-card>
                <v-card-title class="text-h2">
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
                            <!-- 工具选择面板 -->
                            <v-expansion-panel value="tools">
                                <v-expansion-panel-title>
                                    <v-icon class="mr-2">mdi-tools</v-icon>
                                    {{ tm('form.tools') }}
                                    <v-chip v-if="Array.isArray(personaForm.tools) && personaForm.tools.length > 0"
                                        size="small" color="primary" variant="tonal" class="ml-2">
                                        {{ personaForm.tools.length }}
                                    </v-chip>
                                </v-expansion-panel-title>

                                <v-expansion-panel-text>
                                    <div class="mb-3">
                                        <p class="text-body-2 text-medium-emphasis">
                                            {{ tm('form.toolsHelp') }}
                                        </p>
                                    </div>

                                    <v-radio-group class="mt-2" v-model="toolSelectValue" hide-details="true">
                                        <v-radio label="默认使用全部函数工具" value="0"></v-radio>
                                        <v-radio label="选择指定函数工具" value="1">
                                        </v-radio>
                                    </v-radio-group>

                                    <div v-if="toolSelectValue === '1'" class="mt-3 ml-8">

                                        <!-- 工具搜索 -->
                                        <v-text-field v-model="toolSearch" :label="tm('form.searchTools')"
                                            prepend-inner-icon="mdi-magnify" variant="outlined" density="compact"
                                            hide-details clearable class="mb-3" />


                                        <!-- MCP 服务器 -->
                                        <div v-if="mcpServers.length > 0" class="mb-4">
                                            <h4 class="text-subtitle-2 mb-2">{{ tm('form.mcpServersQuickSelect') }}</h4>
                                            <div class="d-flex flex-wrap ga-2">
                                                <v-chip v-for="server in mcpServers" :key="server.name"
                                                    :color="isServerSelected(server) ? 'primary' : 'default'"
                                                    :variant="isServerSelected(server) ? 'flat' : 'outlined'"
                                                    size="small" clickable @click="toggleMcpServer(server)"
                                                    :disabled="!server.tools || server.tools.length === 0">
                                                    <v-icon start size="small">mdi-server</v-icon>
                                                    {{ server.name }}
                                                    <v-chip-text v-if="server.tools" class="ml-1">
                                                        ({{ server.tools.length }})
                                                    </v-chip-text>
                                                </v-chip>
                                            </div>
                                        </div>

                                        <!-- 工具选择列表 -->
                                        <div v-if="filteredTools.length > 0" class="tools-selection">
                                            <v-virtual-scroll :items="filteredTools" height="300" item-height="48">
                                                <template v-slot:default="{ item }">
                                                    <v-list-item :key="item.name" density="comfortable"
                                                        @click="toggleTool(item.name)">
                                                        <template v-slot:prepend>
                                                            <v-checkbox-btn :model-value="isToolSelected(item.name)"
                                                                @click.stop="toggleTool(item.name)" />
                                                        </template>

                                                        <v-list-item-title>
                                                            {{ item.name }}
                                                            <v-chip v-if="item.mcp_server_name" size="x-small"
                                                                color="secondary" variant="tonal" class="ml-2">
                                                                {{ item.mcp_server_name }}
                                                            </v-chip>
                                                        </v-list-item-title>

                                                        <v-list-item-subtitle v-if="item.description">
                                                            {{ truncateText(item.description, 100) }}
                                                        </v-list-item-subtitle>
                                                    </v-list-item>
                                                </template>
                                            </v-virtual-scroll>
                                        </div>

                                        <div v-else-if="!loadingTools && availableTools.length === 0"
                                            class="text-center pa-4">
                                            <v-icon size="48" color="grey-lighten-2" class="mb-2">mdi-tools</v-icon>
                                            <p class="text-body-2 text-medium-emphasis">{{ tm('form.noToolsAvailable')
                                                }}
                                            </p>
                                        </div>

                                        <div v-else-if="!loadingTools && filteredTools.length === 0"
                                            class="text-center pa-4">
                                            <v-icon size="48" color="grey-lighten-2" class="mb-2">mdi-magnify</v-icon>
                                            <p class="text-body-2 text-medium-emphasis">{{ tm('form.noToolsFound') }}
                                            </p>
                                        </div>

                                        <!-- 加载状态 -->
                                        <div v-if="loadingTools" class="text-center pa-4">
                                            <v-progress-circular indeterminate color="primary" />
                                            <p class="text-body-2 text-medium-emphasis mt-2">{{ tm('form.loadingTools')
                                                }}
                                            </p>
                                        </div>

                                        <!-- 已选择的工具 -->
                                        <div class="mt-4">
                                            <h4 class="text-subtitle-2 mb-2">
                                                {{ tm('form.selectedTools') }}
                                                <span v-if="personaForm.tools === null" class="text-success">
                                                    ({{ tm('form.allSelected') }})
                                                </span>
                                                <span v-else-if="Array.isArray(personaForm.tools)">
                                                    ({{ personaForm.tools.length }})
                                                </span>
                                            </h4>
                                            <div v-if="Array.isArray(personaForm.tools) && personaForm.tools.length > 0"
                                                class="d-flex flex-wrap ga-1"  style="max-height: 100px; overflow-y: auto;">
                                                <v-chip v-for="toolName in personaForm.tools" :key="toolName"
                                                    size="small" color="primary" variant="tonal" closable
                                                    @click:close="removeTool(toolName)">
                                                    {{ toolName }}
                                                </v-chip>
                                            </div>
                                            <div v-else class="text-body-2 text-medium-emphasis">
                                                {{ tm('form.noToolsSelected') }}
                                            </div>
                                        </div>
                                    </div>

                                </v-expansion-panel-text>
                            </v-expansion-panel>

                            <!-- 预设对话面板 -->
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
                                            :rules="getDialogRules(index)" variant="outlined" rows="2"
                                            density="comfortable">
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

export default {
    name: 'PersonaPage',
    setup() {
        const { t } = useI18n();
        const { tm } = useModuleI18n('features/persona');
        return { t, tm };
    },
    data() {
        return {
            toolSelectValue: '0', // 默认选择全部工具
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
                begin_dialogs: [],
                tools: []
            },
            showMessage: false,
            message: '',
            messageType: 'success',
            personaIdRules: [
                v => !!v || this.tm('validation.required'),
                v => (v && v.length >= 0) || this.tm('validation.minLength', { min: 2 }),
            ],
            systemPromptRules: [
                v => !!v || this.tm('validation.required'),
                v => (v && v.length >= 10) || this.tm('validation.minLength', { min: 10 })
            ],
            mcpServers: [],
            availableTools: [],
            loadingTools: false,
            toolSearch: ''
        }
    },

    computed: {
        filteredTools() {
            if (!this.toolSearch) {
                return this.availableTools;
            }
            const search = this.toolSearch.toLowerCase();
            return this.availableTools.filter(tool =>
                tool.name.toLowerCase().includes(search) ||
                (tool.description && tool.description.toLowerCase().includes(search)) ||
                (tool.mcp_server_name && tool.mcp_server_name.toLowerCase().includes(search))
            );
        }
    },

    watch: {
        toolSearch() {
            // 响应式搜索，无需额外处理
        },
        
        toolSelectValue(newValue) {
            if (newValue === '0') {
                // 选择全部工具
                this.personaForm.tools = null;
            } else if (newValue === '1') {
                // 选择指定工具，如果当前是null，则转换为空数组
                if (this.personaForm.tools === null) {
                    this.personaForm.tools = [];
                }
            }
        }
    },

    mounted() {
        this.loadPersonas();
        this.loadMcpServers();
        this.loadTools();
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

        async loadMcpServers() {
            try {
                const response = await axios.get('/api/tools/mcp/servers');
                if (response.data.status === 'ok') {
                    this.mcpServers = response.data.data;
                } else {
                    this.showError(response.data.message || this.tm('messages.loadError'));
                }
            } catch (error) {
                this.showError(error.response?.data?.message || this.tm('messages.loadError'));
            }
        },

        async loadTools() {
            this.loadingTools = true;
            try {
                const response = await axios.get('/api/tools/list');
                if (response.data.status === 'ok') {
                    this.availableTools = response.data.data;
                } else {
                    this.showError(response.data.message || this.tm('messages.loadError'));
                }
            } catch (error) {
                this.showError(error.response?.data?.message || this.tm('messages.loadError'));
            }
            this.loadingTools = false;
        },

        openCreateDialog() {
            this.editingPersona = null;
            this.personaForm = {
                persona_id: '',
                system_prompt: '',
                begin_dialogs: [],
                tools: []
            };
            this.toolSelectValue = '0';
            this.expandedPanels = [];
            this.showPersonaDialog = true;
        },

        editPersona(persona) {
            this.editingPersona = persona;
            this.personaForm = {
                persona_id: persona.persona_id,
                system_prompt: persona.system_prompt,
                begin_dialogs: [...(persona.begin_dialogs || [])],
                tools: persona.tools === null ? null : [...(persona.tools || [])]
            };
            // 根据 tools 的值设置 toolSelectValue
            this.toolSelectValue = persona.tools === null ? '0' : '1';
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
                begin_dialogs: [],
                tools: []
            };
            this.toolSelectValue = '1'; // 重置为默认值
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

        toggleMcpServer(server) {
            if (!server.tools || server.tools.length === 0) return;

            // 如果当前是全选状态，需要先转换为具体的工具列表
            if (this.personaForm.tools === null) {
                // 从全选状态转换为去除该服务器工具的状态
                this.personaForm.tools = this.availableTools.map(tool => tool.name)
                    .filter(toolName => !server.tools.includes(toolName));
                this.toolSelectValue = '1'; // 切换到指定工具模式
                return;
            }

            // 确保tools是数组
            if (!Array.isArray(this.personaForm.tools)) {
                this.personaForm.tools = [];
                this.toolSelectValue = '1';
            }

            // 检查是否所有服务器的工具都已选中
            const serverTools = server.tools;
            const allSelected = serverTools.every(toolName => this.personaForm.tools.includes(toolName));

            if (allSelected) {
                // 移除所有服务器工具
                this.personaForm.tools = this.personaForm.tools.filter(
                    toolName => !serverTools.includes(toolName)
                );
            } else {
                // 添加所有服务器工具
                serverTools.forEach(toolName => {
                    if (!this.personaForm.tools.includes(toolName)) {
                        this.personaForm.tools.push(toolName);
                    }
                });
            }
        },

        toggleTool(toolName) {
            // 如果当前是全选状态，需要先转换为具体的工具列表
            if (this.personaForm.tools === null) {
                // 如果是全选状态，点击某个工具表示要取消选择该工具
                // 所以创建一个包含所有其他工具的数组
                this.personaForm.tools = this.availableTools.map(tool => tool.name).filter(name => name !== toolName);
                this.toolSelectValue = '1'; // 切换到指定工具模式
            } else if (Array.isArray(this.personaForm.tools)) {
                const index = this.personaForm.tools.indexOf(toolName);
                if (index !== -1) {
                    // 如果工具已选择，移除工具
                    this.personaForm.tools.splice(index, 1);
                } else {
                    // 如果工具未选择，添加工具
                    this.personaForm.tools.push(toolName);
                }
            } else {
                // 如果tools不是数组也不是null，初始化为数组
                this.personaForm.tools = [toolName];
                this.toolSelectValue = '1';
            }
        },

        toggleAllTools() {
            // 如果当前是全选状态，则清空选择
            if (this.isAllToolsSelected()) {
                this.personaForm.tools = [];
            } else {
                // 否则设置为全选（null表示所有工具）
                this.personaForm.tools = null;
            }
        },

        clearAllTools() {
            // 清空所有工具选择
            this.personaForm.tools = [];
        },

        isAllToolsSelected() {
            // 检查是否为全选状态（tools为null）
            return this.personaForm.tools === null;
        },

        isNoToolsSelected() {
            // 检查是否没有选择任何工具
            return Array.isArray(this.personaForm.tools) && this.personaForm.tools.length === 0;
        },

        removeTool(toolName) {
            // 如果当前是全选状态，需要先转换为具体的工具列表
            if (this.personaForm.tools === null) {
                // 创建一个包含所有工具的数组，然后移除指定工具
                this.personaForm.tools = this.availableTools.map(tool => tool.name).filter(name => name !== toolName);
                this.toolSelectValue = '1'; // 切换到指定工具模式
            } else if (Array.isArray(this.personaForm.tools)) {
                const index = this.personaForm.tools.indexOf(toolName);
                if (index !== -1) {
                    this.personaForm.tools.splice(index, 1);
                }
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
        },

        isToolSelected(toolName) {
            // 如果是全选状态，所有工具都被选中
            if (this.personaForm.tools === null) {
                return true;
            }
            return Array.isArray(this.personaForm.tools) && this.personaForm.tools.includes(toolName);
        },

        isServerSelected(server) {
            if (!server.tools || server.tools.length === 0) return false;

            // 如果是全选状态，所有服务器都被选中
            if (this.personaForm.tools === null) {
                return true;
            }

            // 检查服务器的所有工具是否都已选中
            return Array.isArray(this.personaForm.tools) &&
                server.tools.every(toolName => this.personaForm.tools.includes(toolName));
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

.tools-selection {
    max-height: 300px;
    overflow-y: auto;
}

.v-virtual-scroll {
    padding-bottom: 16px;
}
</style>
