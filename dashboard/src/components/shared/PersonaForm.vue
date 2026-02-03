<template>
    <v-dialog v-model="showDialog" max-width="500px">
        <v-card>
            <v-card-title class="text-h2">
                {{ editingPersona ? tm('dialog.edit.title') : tm('dialog.create.title') }}
            </v-card-title>

            <v-card-text>
                <!-- 创建位置提示 -->
                <v-alert
                    v-if="!editingPersona"
                    type="info"
                    variant="tonal"
                    density="compact"
                    class="mb-4"
                    icon="mdi-folder-outline"
                >
                    {{ tm('form.createInFolder', { folder: folderDisplayName }) }}
                </v-alert>

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

                        <!-- Skills 选择面板 -->
                        <v-expansion-panel value="skills">
                            <v-expansion-panel-title>
                                <v-icon class="mr-2">mdi-lightning-bolt</v-icon>
                                {{ tm('form.skills') }}
                                <v-chip v-if="Array.isArray(personaForm.skills) && personaForm.skills.length > 0"
                                    size="small" color="primary" variant="tonal" class="ml-2">
                                    {{ personaForm.skills.length }}
                                </v-chip>
                            </v-expansion-panel-title>

                            <v-expansion-panel-text>
                                <div class="mb-3">
                                    <p class="text-body-2 text-medium-emphasis">
                                        {{ tm('form.skillsHelp') }}
                                    </p>
                                </div>

                                <v-radio-group class="mt-2" v-model="skillSelectValue" hide-details="true">
                                    <v-radio :label="tm('form.skillsAllAvailable')" value="0"></v-radio>
                                    <v-radio :label="tm('form.skillsSelectSpecific')" value="1"></v-radio>
                                </v-radio-group>

                                <div v-if="skillSelectValue === '1'" class="mt-3 ml-8">
                                    <v-text-field v-model="skillSearch" :label="tm('form.searchSkills')"
                                        prepend-inner-icon="mdi-magnify" variant="outlined" density="compact"
                                        hide-details clearable class="mb-3" />

                                    <div v-if="filteredSkills.length > 0" class="skills-selection">
                                        <v-virtual-scroll :items="filteredSkills" height="240" item-height="48">
                                            <template v-slot:default="{ item }">
                                                <v-list-item :key="item.name" density="comfortable"
                                                    @click="toggleSkill(item.name)">
                                                    <template v-slot:prepend>
                                                        <v-checkbox-btn :model-value="isSkillSelected(item.name)"
                                                            @click.stop="toggleSkill(item.name)" />
                                                    </template>
                                                    <v-list-item-title>
                                                        {{ item.name }}
                                                    </v-list-item-title>
                                                    <v-list-item-subtitle v-if="item.description">
                                                        {{ truncateText(item.description, 100) }}
                                                    </v-list-item-subtitle>
                                                </v-list-item>
                                            </template>
                                        </v-virtual-scroll>
                                    </div>

                                    <div v-else-if="!loadingSkills && availableSkills.length === 0"
                                        class="text-center pa-4">
                                        <v-icon size="48" color="grey-lighten-2" class="mb-2">mdi-lightning-bolt</v-icon>
                                        <p class="text-body-2 text-medium-emphasis">{{ tm('form.noSkillsAvailable') }}
                                        </p>
                                    </div>

                                    <div v-else-if="!loadingSkills && filteredSkills.length === 0"
                                        class="text-center pa-4">
                                        <v-icon size="48" color="grey-lighten-2" class="mb-2">mdi-magnify</v-icon>
                                        <p class="text-body-2 text-medium-emphasis">{{ tm('form.noSkillsFound') }}
                                        </p>
                                    </div>

                                    <div v-if="loadingSkills" class="text-center pa-4">
                                        <v-progress-circular indeterminate color="primary" />
                                        <p class="text-body-2 text-medium-emphasis mt-2">{{ tm('form.loadingSkills') }}
                                        </p>
                                    </div>

                                    <div class="mt-4">
                                        <h4 class="text-subtitle-2 mb-2">
                                            {{ tm('form.selectedSkills') }}
                                            <span v-if="personaForm.skills === null" class="text-success">
                                                ({{ tm('form.allSelected') }})
                                            </span>
                                            <span v-else-if="Array.isArray(personaForm.skills)">
                                                ({{ personaForm.skills.length }})
                                            </span>
                                        </h4>
                                        <div v-if="Array.isArray(personaForm.skills) && personaForm.skills.length > 0"
                                            class="d-flex flex-wrap ga-1" style="max-height: 100px; overflow-y: auto;">
                                            <v-chip v-for="skillName in personaForm.skills" :key="skillName"
                                                size="small" color="primary" variant="tonal" closable
                                                @click:close="removeSkill(skillName)">
                                                {{ skillName }}
                                            </v-chip>
                                        </div>
                                        <div v-else class="text-body-2 text-medium-emphasis">
                                            {{ tm('form.noSkillsSelected') }}
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
                <v-btn color="grey" variant="text" @click="closeDialog">
                    {{ tm('buttons.cancel') }}
                </v-btn>
                <v-btn color="primary" variant="flat" @click="savePersona" :loading="saving" :disabled="!formValid">
                    {{ tm('buttons.save') }}
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script>
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';

export default {
    name: 'PersonaForm',
    props: {
        modelValue: {
            type: Boolean,
            default: false
        },
        editingPersona: {
            type: Object,
            default: null
        },
        currentFolderId: {
            type: String,
            default: null
        },
        currentFolderName: {
            type: String,
            default: null
        }
    },
    emits: ['update:modelValue', 'saved', 'error'],
    setup() {
        const { tm } = useModuleI18n('features/persona');
        return { tm };
    },
    data() {
        return {
            toolSelectValue: '0', // 默认选择全部工具
            saving: false,
            expandedPanels: [],
            formValid: false,
            mcpServers: [],
            availableTools: [],
            loadingTools: false,
            availableSkills: [],
            loadingSkills: false,
            existingPersonaIds: [], // 已存在的人格ID列表
            personaForm: {
                persona_id: '',
                system_prompt: '',
                begin_dialogs: [],
                tools: [],
                skills: [],
                folder_id: null
            },
            personaIdRules: [
                v => !!v || this.tm('validation.required'),
                v => (v && v.length >= 1) || this.tm('validation.minLength', { min: 1 }),
                v => !this.existingPersonaIds.includes(v) || this.tm('validation.personaIdExists'),
            ],
            systemPromptRules: [
                v => !!v || this.tm('validation.required'),
                v => (v && v.length >= 10) || this.tm('validation.minLength', { min: 10 })
            ],
            toolSearch: '',
            skillSearch: '',
            skillSelectValue: '0'
        }
    },

    computed: {
        showDialog: {
            get() {
                return this.modelValue;
            },
            set(value) {
                this.$emit('update:modelValue', value);
            }
        },
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
        },
        filteredSkills() {
            if (!this.skillSearch) {
                return this.availableSkills;
            }
            const search = this.skillSearch.toLowerCase();
            return this.availableSkills.filter(skill =>
                skill.name.toLowerCase().includes(search) ||
                (skill.description && skill.description.toLowerCase().includes(search))
            );
        },
        folderDisplayName() {
            // 优先使用传入的文件夹名称
            if (this.currentFolderName) {
                return this.currentFolderName;
            }
            // 如果没有文件夹 ID，显示根目录
            if (!this.currentFolderId) {
                return this.tm('form.rootFolder');
            }
            // 否则显示文件夹 ID（作为备用）
            return this.currentFolderId;
        }
    },

    watch: {
        modelValue(newValue) {
            if (newValue) {
                // 只有在不是编辑状态时才初始化空表单
                if (this.editingPersona) {
                    this.initFormWithPersona(this.editingPersona);
                } else {
                    this.initForm();
                    // 只在创建新人格时加载已存在的人格列表
                    this.loadExistingPersonaIds();
                }
                this.loadMcpServers();
                this.loadTools();
                this.loadSkills();
            }
        },
        editingPersona: {
            immediate: true,
            handler(newPersona) {
                // 只有在对话框打开时才处理editingPersona的变化
                if (this.modelValue) {
                    if (newPersona) {
                        this.initFormWithPersona(newPersona);
                    } else {
                        this.initForm();
                    }
                }
            }
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
        },
        skillSelectValue(newValue) {
            if (newValue === '0') {
                this.personaForm.skills = null;
            } else if (newValue === '1') {
                if (this.personaForm.skills === null) {
                    this.personaForm.skills = [];
                }
            }
        }
    },

    methods: {
        initForm() {
            this.personaForm = {
                persona_id: '',
                system_prompt: '',
                begin_dialogs: [],
                tools: [],
                skills: [],
                folder_id: this.currentFolderId
            };
            this.toolSelectValue = '0';
            this.skillSelectValue = '0';
            this.expandedPanels = [];
        },

        initFormWithPersona(persona) {
            this.personaForm = {
                persona_id: persona.persona_id,
                system_prompt: persona.system_prompt,
                begin_dialogs: [...(persona.begin_dialogs || [])],
                tools: persona.tools === null ? null : [...(persona.tools || [])],
                skills: persona.skills === null ? null : [...(persona.skills || [])],
                folder_id: persona.folder_id
            };
            // 根据 tools 的值设置 toolSelectValue
            this.toolSelectValue = persona.tools === null ? '0' : '1';
            this.skillSelectValue = persona.skills === null ? '0' : '1';
            this.expandedPanels = [];
        },

        closeDialog() {
            this.showDialog = false;
        },

        async loadMcpServers() {
            try {
                const response = await axios.get('/api/tools/mcp/servers');
                if (response.data.status === 'ok') {
                    this.mcpServers = response.data.data || [];
                } else {
                    this.$emit('error', response.data.message || 'Failed to load MCP servers');
                }
            } catch (error) {
                this.$emit('error', error.response?.data?.message || 'Failed to load MCP servers');
                this.mcpServers = [];
            }
        },

        async loadTools() {
            this.loadingTools = true;
            try {
                const response = await axios.get('/api/tools/list');
                if (response.data.status === 'ok') {
                    this.availableTools = response.data.data || [];
                } else {
                    this.$emit('error', response.data.message || 'Failed to load tools');
                }
            } catch (error) {
                this.$emit('error', error.response?.data?.message || 'Failed to load tools');
                this.availableTools = [];
            } finally {
                this.loadingTools = false;
            }
        },

        async loadSkills() {
            this.loadingSkills = true;
            try {
                const response = await axios.get('/api/skills');
                if (response.data.status === 'ok') {
                    const skills = response.data.data || [];
                    this.availableSkills = skills.filter(skill => skill.active !== false);
                } else {
                    this.$emit('error', response.data.message || 'Failed to load skills');
                }
            } catch (error) {
                this.$emit('error', error.response?.data?.message || 'Failed to load skills');
                this.availableSkills = [];
            } finally {
                this.loadingSkills = false;
            }
        },

        async loadExistingPersonaIds() {
            try {
                const response = await axios.get('/api/persona/list');
                if (response.data.status === 'ok') {
                    this.existingPersonaIds = (response.data.data || []).map(p => p.persona_id);
                }
            } catch (error) {
                // 加载失败不影响表单使用，只是无法进行前端重名校验
                this.existingPersonaIds = [];
            }
        },

        async savePersona() {
            if (!this.formValid) return;

            // 验证预设对话不能为空
            if (this.personaForm.begin_dialogs.length > 0) {
                for (let i = 0; i < this.personaForm.begin_dialogs.length; i++) {
                    if (!this.personaForm.begin_dialogs[i] || this.personaForm.begin_dialogs[i].trim() === '') {
                        const dialogType = i % 2 === 0 ? this.tm('form.userMessage') : this.tm('form.assistantMessage');
                        this.$emit('error', this.tm('validation.dialogRequired', { type: dialogType }));
                        return;
                    }
                }
            }

            this.saving = true;
            try {
                const url = this.editingPersona ? '/api/persona/update' : '/api/persona/create';
                const response = await axios.post(url, this.personaForm);

                if (response.data.status === 'ok') {
                    this.$emit('saved', response.data.message || this.tm('messages.saveSuccess'));
                    this.closeDialog();
                } else {
                    this.$emit('error', response.data.message || this.tm('messages.saveError'));
                }
            } catch (error) {
                this.$emit('error', error.response?.data?.message || this.tm('messages.saveError'));
            }
            this.saving = false;
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

        toggleSkill(skillName) {
            if (this.personaForm.skills === null) {
                this.personaForm.skills = this.availableSkills.map(skill => skill.name)
                    .filter(name => name !== skillName);
                this.skillSelectValue = '1';
            } else if (Array.isArray(this.personaForm.skills)) {
                const index = this.personaForm.skills.indexOf(skillName);
                if (index !== -1) {
                    this.personaForm.skills.splice(index, 1);
                } else {
                    this.personaForm.skills.push(skillName);
                }
            } else {
                this.personaForm.skills = [skillName];
                this.skillSelectValue = '1';
            }
        },

        removeSkill(skillName) {
            if (this.personaForm.skills === null) {
                this.personaForm.skills = this.availableSkills.map(skill => skill.name)
                    .filter(name => name !== skillName);
                this.skillSelectValue = '1';
            } else if (Array.isArray(this.personaForm.skills)) {
                const index = this.personaForm.skills.indexOf(skillName);
                if (index !== -1) {
                    this.personaForm.skills.splice(index, 1);
                }
            }
        },

        truncateText(text, maxLength) {
            if (!text) return '';
            return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
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

        isSkillSelected(skillName) {
            if (this.personaForm.skills === null) {
                return true;
            }
            return Array.isArray(this.personaForm.skills) && this.personaForm.skills.includes(skillName);
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
.tools-selection {
    max-height: 300px;
    overflow-y: auto;
}

.skills-selection {
    max-height: 300px;
    overflow-y: auto;
}

.v-virtual-scroll {
    padding-bottom: 16px;
}
</style>
