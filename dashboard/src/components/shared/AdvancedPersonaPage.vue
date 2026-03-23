<template>
    <div class="advanced-persona-page">
        <v-container fluid class="pa-0">
            <!-- 页面标题和返回按钮 -->
            <div class="d-flex align-center mb-4">
                <v-btn prepend-icon="mdi-arrow-left" @click="goBack" class="mr-4">
                    {{ tm('advancedPersona.back') }}
                </v-btn>
                <div>
                    <h1 class="text-h5">
                        <v-icon color="purple" class="me-2">mdi-star-cog</v-icon>
                        {{ isEditMode ? tm('advancedPersona.editTitle') : tm('advancedPersona.createTitle') }}
                    </h1>
                    <p class="text-grey text-caption">
                        {{ tm('advancedPersona.subtitle') }}
                    </p>
                </div>
                <v-spacer />
                <!-- 高级人格标签 -->
                <v-chip color="purple" variant="flat" size="small">
                    <v-icon start size="small">mdi-star</v-icon>
                    {{ tm('advancedPersona.betaTag') }}
                </v-chip>
            </div>

            <!-- 加载状态 -->
            <v-progress-linear v-if="loading" indeterminate class="mb-4"></v-progress-linear>

            <!-- 错误提示 -->
            <v-alert v-if="error" type="error" class="mb-4" closable @click:close="error = null">
                {{ error }}
            </v-alert>

            <v-row v-if="!loading">
                <!-- 左侧：基础信息卡片 -->
                <v-col cols="12" md="3">
                    <v-card class="mb-4">
                        <v-card-title>{{ tm('advancedPersona.basicInfo') }}</v-card-title>
                        <v-card-text>
                            <v-text-field v-model="personaForm.persona_id"
                                :label="tm('advancedPersona.form.personaId')"
                                :rules="personaIdRules"
                                :disabled="isEditMode"
                                variant="outlined"
                                density="comfortable"
                                class="mb-3" />

                            <v-textarea v-model="personaForm.system_prompt"
                                :label="tm('advancedPersona.form.systemPrompt')"
                                :rules="systemPromptRules"
                                variant="outlined"
                                rows="8" />

                            <v-textarea v-model="personaForm.custom_error_message"
                                :label="tm('advancedPersona.form.customErrorMessage')"
                                variant="outlined"
                                rows="3"
                                clearable />

                            <v-btn v-if="!isEditMode" block variant="tonal" color="purple" class="mt-2"
                                prepend-icon="mdi-auto-fix" @click="fillDefaultConfig">
                                {{ tm('advancedPersona.fillDefault') }}
                            </v-btn>
                        </v-card-text>
                    </v-card>

                    <!-- 工具选择 -->
                    <v-card class="mb-4">
                        <v-card-title>{{ tm('advancedPersona.tools.title') }}</v-card-title>
                        <v-card-text>
                            <v-radio-group v-model="toolSelectValue" hide-details>
                                <v-radio :label="tm('advancedPersona.tools.all')" value="0"></v-radio>
                                <v-radio :label="tm('advancedPersona.tools.select')" value="1"></v-radio>
                            </v-radio-group>

                            <div v-if="toolSelectValue === '1' && availableTools.length > 0" class="mt-3">
                                <v-text-field v-model="toolSearch"
                                    :label="tm('advancedPersona.tools.search')"
                                    prepend-inner-icon="mdi-magnify"
                                    variant="outlined"
                                    density="compact"
                                    hide-details
                                    clearable
                                    class="mb-2" />

                                <div class="tools-list" style="max-height: 200px; overflow-y: auto;">
                                    <v-checkbox v-for="tool in filteredTools" :key="tool.name"
                                        v-model="personaForm.tools"
                                        :label="tool.name"
                                        :value="tool.name"
                                        density="compact"
                                        hide-details />
                                </div>
                            </div>
                        </v-card-text>
                    </v-card>

                    <!-- Skills 选择 -->
                    <v-card class="mb-4">
                        <v-card-title>
                            <v-icon start size="small">mdi-lightning-bolt</v-icon>
                            {{ tm('advancedPersona.skills.title') }}
                        </v-card-title>
                        <v-card-text>
                            <v-radio-group v-model="skillSelectValue" hide-details>
                                <v-radio :label="tm('advancedPersona.skills.all')" value="0"></v-radio>
                                <v-radio :label="tm('advancedPersona.skills.select')" value="1"></v-radio>
                            </v-radio-group>

                            <div v-if="skillSelectValue === '1'" class="mt-3">
                                <v-text-field v-model="skillSearch"
                                    :label="tm('advancedPersona.skills.search')"
                                    prepend-inner-icon="mdi-magnify"
                                    variant="outlined"
                                    density="compact"
                                    hide-details
                                    clearable
                                    class="mb-2" />

                                <div v-if="filteredSkills.length > 0" class="skills-list" style="max-height: 200px; overflow-y: auto;">
                                    <v-checkbox v-for="skill in filteredSkills" :key="skill.name"
                                        v-model="personaForm.skills"
                                        :label="skill.name"
                                        :value="skill.name"
                                        density="compact"
                                        hide-details />
                                </div>

                                <div v-else-if="!loadingSkills && availableSkills.length === 0" class="text-center pa-4">
                                    <v-icon size="48" color="grey-lighten-2" class="mb-2">mdi-lightning-bolt</v-icon>
                                    <p class="text-body-2 text-medium-emphasis">{{ tm('advancedPersona.skills.noSkillsAvailable') }}</p>
                                </div>

                                <div v-else-if="!loadingSkills && filteredSkills.length === 0" class="text-center pa-4">
                                    <v-icon size="48" color="grey-lighten-2" class="mb-2">mdi-magnify</v-icon>
                                    <p class="text-body-2 text-medium-emphasis">{{ tm('advancedPersona.skills.noSkillsFound') }}</p>
                                </div>

                                <div v-if="loadingSkills" class="text-center pa-4">
                                    <v-progress-circular indeterminate color="primary" />
                                    <p class="text-body-2 text-medium-emphasis mt-2">{{ tm('advancedPersona.skills.loading') }}</p>
                                </div>
                            </div>
                        </v-card-text>
                    </v-card>

                    <!-- 操作按钮 -->
                    <v-card>
                        <v-card-text>
                            <v-btn block color="primary" size="large" @click="savePersona" :loading="saving"
                                :disabled="!personaForm.persona_id || !personaForm.system_prompt">
                                <v-icon start>mdi-content-save</v-icon>
                                {{ tm('buttons.save') }}
                            </v-btn>
                            <v-btn v-if="isEditMode" block variant="outlined" color="error" class="mt-2"
                                @click="deletePersona" :loading="saving">
                                <v-icon start>mdi-delete</v-icon>
                                {{ tm('buttons.delete') }}
                            </v-btn>
                        </v-card-text>
                    </v-card>
                </v-col>

                <!-- 右侧：配置区块导航 -->
                <v-col cols="12" md="9">
                    <!-- 配置区块导航 -->
                    <v-card class="mb-4">
                        <v-tabs v-model="activeTab" color="purple" show-arrows>
                            <v-tab value="personality">
                                <v-icon start size="small">mdi-account-heart</v-icon>
                                {{ tm('advancedPersona.tabs.personality') }}
                            </v-tab>
                            <v-tab value="chat">
                                <v-icon start size="small">mdi-chat</v-icon>
                                {{ tm('advancedPersona.tabs.chat') }}
                            </v-tab>
                            <v-tab value="robot">
                                <v-icon start size="small">mdi-robot</v-icon>
                                {{ tm('advancedPersona.tabs.robot') }}
                            </v-tab>
                            <v-tab value="models">
                                <v-icon start size="small">mdi-brain</v-icon>
                                模型配置
                            </v-tab>
                            <v-tab value="dialogs">
                                <v-icon start size="small">mdi-message-text</v-icon>
                                {{ tm('advancedPersona.tabs.dialogs') }}
                            </v-tab>
                        </v-tabs>
                    </v-card>

                    <!-- 配置内容 -->
                    <v-window v-model="activeTab">
                        <!-- 人格设置板块 -->
                        <v-window-item value="personality">
                            <PersonalitySection v-model="personaForm.personality_config" />
                        </v-window-item>

                        <!-- 聊天设置板块 -->
                        <v-window-item value="chat">
                            <ChatSection v-model="personaForm.chat_config" />
                        </v-window-item>

                        <!-- 机器人账号板块 -->
                        <v-window-item value="robot">
                            <RobotSection v-model="personaForm.robot_config" />
                        </v-window-item>

                        <!-- 模型配置板块 -->
                        <v-window-item value="models">
                            <ModelConfigSection
                                v-model="personaForm.llm_model_config"
                                :providers="providers"
                                :loading-providers="loadingProviders"
                                @refresh-providers="loadProviders"
                            />
                        </v-window-item>

                        <!-- 预设对话板块 -->
                        <v-window-item value="dialogs">
                            <DialogsSection v-model="personaForm.begin_dialogs" />
                        </v-window-item>
                    </v-window>
                </v-col>
            </v-row>
        </v-container>
    </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import axios from 'axios';
import {
    askForConfirmation as askForConfirmationDialog,
    useConfirmDialog
} from '@/utils/confirmDialog';

// 引入各板块组件
import PersonalitySection from '@/components/shared/advanced/PersonalitySection.vue';
import ChatSection from '@/components/shared/advanced/ChatSection.vue';
import RobotSection from '@/components/shared/advanced/RobotSection.vue';
import ModelConfigSection from '@/components/shared/advanced/ModelConfigSection.vue';
import DialogsSection from '@/components/shared/advanced/DialogsSection.vue';

export default defineComponent({
    name: 'AdvancedPersonaPage',
    components: {
        PersonalitySection,
        ChatSection,
        RobotSection,
        ModelConfigSection,
        DialogsSection
    },
    setup() {
        const router = useRouter();
        const route = useRoute();
        const { t } = useI18n();
        const { tm } = useModuleI18n('features/persona');
        const confirmDialog = useConfirmDialog();

        // 路由参数
        const personaId = computed(() => route.params.personaId as string | undefined);
        const isEditMode = computed(() => !!personaId.value);

        // 状态
        const loading = ref(false);
        const saving = ref(false);
        const error = ref<string | null>(null);
        const activeTab = ref('personality');
        const availableTools = ref<{ name: string; description?: string }[]>([]);
        const toolSearch = ref('');
        const toolSelectValue = ref('0');
        const loadingTools = ref(false);

        // Skills 相关
        const availableSkills = ref<{ name: string; description?: string }[]>([]);
        const skillSearch = ref('');
        const skillSelectValue = ref('0');
        const loadingSkills = ref(false);

        // Providers 相关
        const providers = ref<any[]>([]);
        const loadingProviders = ref(false);

        // 表单数据
        const existingPersonaIds = ref<string[]>([]);

        const personaForm = ref({
            persona_id: '',
            system_prompt: '',
            custom_error_message: '',
            tools: [] as string[],
            skills: [] as string[],
            folder_id: null as string | null,
            // 高级人格配置
            personality_config: {
                traits: '',              // 人格特质
                expression_style: '',    // 表达风格
                recognition_rules: '',   // 识别规则
                mood_tags: [] as { name: string; weight: number }[]  // 心情标签及权重
            },
            chat_config: {
                chat_frequency: 'normal',      // 聊天频率 todo
                dynamic_frequency: 'auto',        // 动态发言频率 todo
                time_based_mode: false,          // 根据时间选择 todo
                message_length: 10         // 消息条数长度（数字）
            },
            robot_config: {
                nickname: '',           // 昵称
                aliases: [] as string[], // 别名
                platforms: [] as string[]  // 启用的平台
            },
            llm_model_config: {
                function_model: {
                    provider_id: '',
                    model: '',
                    temperature: 0.7,
                    max_tokens: 2048,
                    thinking_enabled: false,
                    thinking_budget: undefined
                },
                reply_model: {
                    provider_id: '',
                    model: '',
                    temperature: 0.8,
                    max_tokens: 2048,
                    thinking_enabled: false,
                    thinking_budget: undefined
                },
                thinking_models: {
                    deep: {
                        provider_id: '',
                        model: '',
                        temperature: 0.7,
                        max_tokens: 4096,
                        thinking_enabled: false,
                        thinking_budget: undefined
                    },
                    medium: {
                        provider_id: '',
                        model: '',
                        temperature: 0.7,
                        max_tokens: 3072,
                        thinking_enabled: false,
                        thinking_budget: undefined
                    },
                    fast: {
                        provider_id: '',
                        model: '',
                        temperature: 0.7,
                        max_tokens: 2048,
                        thinking_enabled: false,
                        thinking_budget: undefined
                    }
                },
                image_caption_model: {
                    provider_id: '',
                    model: '',
                    temperature: 0.7,
                    max_tokens: 256,
                    thinking_enabled: false,
                    thinking_budget: undefined,
                    prompt: '请简洁描述这张图片的内容，用一句话概括。'
                }
            },
            begin_dialogs: [] as string[]
        });

        // 验证规则
        const personaIdRules = [
            (v: string) => !!v || tm('validation.required'),
            (v: string) => (v && v.length >= 1) || tm('validation.minLength', { min: 1 }),
            (v: string) => !existingPersonaIds.value.includes(v) || tm('validation.personaIdExists')
        ];

        const systemPromptRules = [
            (v: string) => !!v || tm('validation.required'),
            (v: string) => (v && v.length >= 10) || tm('validation.minLength', { min: 10 })
        ];

        // 计算属性
        const filteredTools = computed(() => {
            if (!toolSearch.value) {
                return availableTools.value;
            }
            const search = toolSearch.value.toLowerCase();
            return availableTools.value.filter(tool =>
                tool.name.toLowerCase().includes(search) ||
                (tool.description && tool.description.toLowerCase().includes(search))
            );
        });

        const filteredSkills = computed(() => {
            if (!skillSearch.value) {
                return availableSkills.value;
            }
            const search = skillSearch.value.toLowerCase();
            return availableSkills.value.filter(skill =>
                skill.name.toLowerCase().includes(search) ||
                (skill.description && skill.description.toLowerCase().includes(search))
            );
        });

        // 监听工具选择模式
        watch(toolSelectValue, (newValue) => {
            if (newValue === '0') {
                personaForm.value.tools = [];
            } else if (newValue === '1' && personaForm.value.tools.length === 0) {
                personaForm.value.tools = [];
            }
        });

        // 监听 Skills 选择模式
        watch(skillSelectValue, (newValue) => {
            if (newValue === '0') {
                personaForm.value.skills = [];
            } else if (newValue === '1' && personaForm.value.skills.length === 0) {
                personaForm.value.skills = [];
            }
        });

        // 方法
        const goBack = () => {
            router.push('/persona');
        };

        const fillDefaultConfig = () => {
            personaForm.value.system_prompt = `你是麦麦，是一个大二在读女大学生，现在正在上网和群友聊天，有时有点攻击性，有时比较温柔。`;
            personaForm.value.personality_config = {
                traits: '是一个大二在读女大学生，现在正在上网和群友聊天，有时有点攻击性，有时比较温柔',
                expression_style: '请不要刻意突出自身学科背景。可以参考贴吧，知乎和微博的回复风格。',
                recognition_rules: '请用中文描述这张图片的内容。如果有文字，请把文字描述概括出来，请留意其主题，直观感受，输出为一段平文本，最多30字，请注意不要分点，就输出一段文本',
                mood_tags: [
                    { name: '温柔', weight: 40 },
                    { name: '攻击性', weight: 30 },
                    { name: '平静', weight: 30 }
                ]
            };
            personaForm.value.chat_config = {
                chat_frequency: 'normal',
                dynamic_frequency: 'auto',
                time_based_mode: true,
                message_length: 10
            };
            personaForm.value.robot_config = {
                nickname: '麦麦',
                aliases: ['麦叠', '牢麦'],
                platforms: []
            };
        };

        const loadTools = async () => {
            loadingTools.value = true;
            try {
                const response = await axios.get('/api/tools/list');
                if (response.data.status === 'ok') {
                    availableTools.value = response.data.data || [];
                }
            } catch (err) {
                console.error('Failed to load tools:', err);
            } finally {
                loadingTools.value = false;
            }
        };

        const loadSkills = async () => {
            loadingSkills.value = true;
            try {
                const response = await axios.get('/api/skills');
                if (response.data.status === 'ok') {
                    const payload = response.data.data || [];
                    if (Array.isArray(payload)) {
                        availableSkills.value = payload.filter(skill => skill.active !== false);
                    } else {
                        const skills = payload.skills || [];
                        availableSkills.value = skills.filter(skill => skill.active !== false);
                    }
                }
            } catch (err) {
                console.error('Failed to load skills:', err);
            } finally {
                loadingSkills.value = false;
            }
        };

        const loadProviders = async () => {
            loadingProviders.value = true;
            try {
                const response = await axios.get('/api/config/provider/list', {
                    params: {
                        provider_type: 'chat_completion'
                    }
                });
                if (response.data.status === 'ok') {
                    const providerList = response.data.data || [];

                    // 为每个 provider 获取模型列表
                    const providersWithModels = await Promise.all(
                        providerList.map(async (provider) => {
                            try {
                                const modelResponse = await axios.get('/api/config/provider/model_list', {
                                    params: {
                                        provider_id: provider.id
                                    }
                                });
                                if (modelResponse.data.status === 'ok') {
                                    return {
                                        ...provider,
                                        models: modelResponse.data.data?.models || []
                                    };
                                }
                            } catch (err) {
                                console.error(`Failed to load models for provider ${provider.id}:`, err);
                            }
                            return {
                                ...provider,
                                models: []
                            };
                        })
                    );

                    providers.value = providersWithModels;
                }
            } catch (err) {
                console.error('Failed to load providers:', err);
            } finally {
                loadingProviders.value = false;
            }
        };

        const loadExistingPersonaIds = async () => {
            try {
                const response = await axios.get('/api/persona/list');
                if (response.data.status === 'ok') {
                    existingPersonaIds.value = (response.data.data || []).map((p: any) => p.persona_id);
                }
            } catch (err) {
                console.error('Failed to load persona list:', err);
            }
        };

        const loadPersona = async (id: string) => {
            loading.value = true;
            try {
                const response = await axios.post('/api/persona/detail', { persona_id: id });
                if (response.data.status === 'ok' && response.data.data) {
                    const data = response.data.data;
                    personaForm.value = {
                        persona_id: data.persona_id || '',
                        system_prompt: data.system_prompt || '',
                        custom_error_message: data.custom_error_message || '',
                        tools: data.tools || [],
                        skills: data.skills || [],
                        folder_id: data.folder_id || null,
                        personality_config: data.personality_config || {
                            traits: '',
                            expression_style: '',
                            recognition_rules: '',
                            mood_tags: []
                        },
                        chat_config: data.chat_config || {
                            chat_frequency: 'normal',
                            dynamic_frequency: 'auto',
                            time_based_mode: false,
                            message_length: 10
                        },
                        robot_config: data.robot_config || {
                            nickname: '',
                            aliases: [],
                            platforms: []
                        },
                        llm_model_config: data.llm_model_config || {
                            function_model: {
                                provider_id: '',
                                model: '',
                                temperature: 0.7,
                                max_tokens: 2048,
                                thinking_enabled: false,
                                thinking_budget: undefined
                            },
                            reply_model: {
                                provider_id: '',
                                model: '',
                                temperature: 0.8,
                                max_tokens: 2048,
                                thinking_enabled: false,
                                thinking_budget: undefined
                            },
                            thinking_models: {
                                deep: {
                                    provider_id: '',
                                    model: '',
                                    temperature: 0.7,
                                    max_tokens: 4096,
                                    thinking_enabled: false,
                                    thinking_budget: undefined
                                },
                                medium: {
                                    provider_id: '',
                                    model: '',
                                    temperature: 0.7,
                                    max_tokens: 3072,
                                    thinking_enabled: false,
                                    thinking_budget: undefined
                                },
                                fast: {
                                    provider_id: '',
                                    model: '',
                                    temperature: 0.7,
                                    max_tokens: 2048,
                                    thinking_enabled: false,
                                    thinking_budget: undefined
                                }
                            },
                            image_caption_model: (data.llm_model_config && data.llm_model_config.image_caption_model) ? data.llm_model_config.image_caption_model : {
                                provider_id: '',
                                model: '',
                                temperature: 0.7,
                                max_tokens: 256,
                                thinking_enabled: false,
                                thinking_budget: undefined,
                                prompt: '请简洁描述这张图片的内容，用一句话概括。'
                            }
                        },
                        begin_dialogs: data.begin_dialogs || []
                    };

                    // 设置工具选择模式
                    toolSelectValue.value = personaForm.value.tools && personaForm.value.tools.length > 0 ? '1' : '0';
                    // 设置 Skills 选择模式
                    skillSelectValue.value = personaForm.value.skills && personaForm.value.skills.length > 0 ? '1' : '0';
                } else {
                    error.value = response.data.message || 'Failed to load persona';
                }
            } catch (err: any) {
                error.value = err.response?.data?.message || 'Failed to load persona';
            } finally {
                loading.value = false;
            }
        };

        const savePersona = async () => {
            if (!personaForm.value.persona_id || !personaForm.value.system_prompt) return;

            saving.value = true;
            error.value = null;

            try {
                // 构建保存数据
                const saveData = {
                    persona_id: personaForm.value.persona_id,
                    system_prompt: personaForm.value.system_prompt,
                    custom_error_message: personaForm.value.custom_error_message,
                    tools: toolSelectValue.value === '0' ? null : personaForm.value.tools,
                    skills: skillSelectValue.value === '0' ? null : personaForm.value.skills,
                    folder_id: personaForm.value.folder_id,
                    // 高级人格配置
                    personality_config: personaForm.value.personality_config,
                    chat_config: personaForm.value.chat_config,
                    robot_config: personaForm.value.robot_config,
                    llm_model_config: personaForm.value.llm_model_config,
                    begin_dialogs: personaForm.value.begin_dialogs,
                    // 标记为高级人格
                    is_advanced: true
                };

                const url = isEditMode.value ? '/api/persona/update' : '/api/persona/create';
                const response = await axios.post(url, saveData);

                if (response.data.status === 'ok') {
                    router.push('/persona');
                } else {
                    error.value = response.data.message || 'Failed to save';
                }
            } catch (err: any) {
                error.value = err.response?.data?.message || 'Failed to save';
            } finally {
                saving.value = false;
            }
        };

        const deletePersona = async () => {
            if (!isEditMode.value) return;

            if (
                !(await askForConfirmationDialog(
                    tm('messages.deleteConfirm', { id: personaForm.value.persona_id }),
                    confirmDialog
                ))
            ) {
                return;
            }

            saving.value = true;
            try {
                const response = await axios.post('/api/persona/delete', {
                    persona_id: personaForm.value.persona_id
                });

                if (response.data.status === 'ok') {
                    router.push('/persona');
                } else {
                    error.value = response.data.message || 'Failed to delete';
                }
            } catch (err: any) {
                error.value = err.response?.data?.message || 'Failed to delete';
            } finally {
                saving.value = false;
            }
        };

        // 初始化
        onMounted(async () => {
            await Promise.all([
                loadTools(),
                loadSkills(),
                loadExistingPersonaIds(),
                loadProviders()
            ]);

            if (isEditMode.value) {
                await loadPersona(personaId.value!);
            }
        });

        return {
            t,
            tm,
            router,
            loading,
            saving,
            error,
            activeTab,
            isEditMode,
            personaForm,
            personaIdRules,
            systemPromptRules,
            availableTools,
            toolSearch,
            toolSelectValue,
            filteredTools,
            availableSkills,
            skillSearch,
            skillSelectValue,
            filteredSkills,
            loadingSkills,
            providers,
            loadingProviders,
            loadProviders,
            goBack,
            fillDefaultConfig,
            savePersona,
            deletePersona
        };
    }
});
</script>

<style scoped>
.advanced-persona-page {
    padding: 20px;
    padding-top: 8px;
}

.tools-list {
    border: 1px solid rgba(var(--v-border-color), 0.2);
    border-radius: 4px;
    padding: 8px;
}

.skills-list {
    border: 1px solid rgba(var(--v-border-color), 0.2);
    border-radius: 4px;
    padding: 8px;
}
</style>
