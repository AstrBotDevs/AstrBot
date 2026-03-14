<template>
    <v-card>
        <v-card-title>
            <v-icon start size="small">mdi-brain</v-icon>
            模型配置
<!--          todo要配置国际化支持-->
        </v-card-title>
        <v-card-text>
            <v-alert type="info" variant="tonal" class="mb-4">
                <div class="text-body-2">
                    配置三层模型架构：功能模型（工具调用）、回复模型（生成回复）、思考模型（深度推理）
                </div>
            </v-alert>

            <!-- 功能模型配置 -->
            <v-card variant="outlined" class="mb-4">
                <v-card-title class="text-subtitle-1">
                    <v-icon start size="small" color="primary">mdi-function</v-icon>
                    功能模型
                    <v-chip size="x-small" color="primary" class="ml-2">必需</v-chip>
                </v-card-title>
                <v-card-subtitle class="text-caption">
                    用于工具调用和快速决策，需要支持 Function Calling，建议使用小模型（调用量大）
                </v-card-subtitle>
                <v-card-text>
                    <ModelSelector
                        v-model="localConfig.function_model"
                        label="选择功能模型"
                        :providers="providers"
                        :loading="loadingProviders"
                        @refresh="$emit('refresh-providers')"
                    />
                </v-card-text>
            </v-card>

            <!-- 回复模型配置 -->
            <v-card variant="outlined" class="mb-4">
                <v-card-title class="text-subtitle-1">
                    <v-icon start size="small" color="success">mdi-message-reply-text</v-icon>
                    回复模型
                    <v-chip size="x-small" color="success" class="ml-2">必需</v-chip>
                </v-card-title>
                <v-card-subtitle class="text-caption">
                    用于生成最终回复给用户，可配置独立的提示词和参数
                </v-card-subtitle>
                <v-card-text>
                    <ModelSelector
                        v-model="localConfig.reply_model"
                        label="选择回复模型"
                        :providers="providers"
                        :loading="loadingProviders"
                        @refresh="$emit('refresh-providers')"
                    />
                </v-card-text>
            </v-card>

            <!-- 思考模型配置 -->
            <v-card variant="outlined">
                <v-card-title class="text-subtitle-1">
                    <v-icon start size="small" color="purple">mdi-head-lightbulb</v-icon>
                    思考模型
                    <v-chip size="x-small" color="purple" class="ml-2">可选</v-chip>
                </v-card-title>
                <v-card-subtitle class="text-caption">
                    用于复杂推理和深度思考，可配置多个不同深度的模型
                </v-card-subtitle>
                <v-card-text>
                    <!-- 深度思考模型 -->
                    <div class="mb-4">
                        <div class="d-flex align-center mb-2">
                            <v-icon size="small" color="deep-purple" class="mr-2">mdi-brain</v-icon>
                            <span class="text-subtitle-2">深度思考模型</span>
                            <v-chip size="x-small" variant="outlined" class="ml-2">最强推理</v-chip>
                        </div>
                        <ModelSelector
                            v-model="localConfig.thinking_models.deep"
                            label="选择深度思考模型"
                            :providers="providers"
                            :loading="loadingProviders"
                            @refresh="$emit('refresh-providers')"
                        />
                    </div>

                    <!-- 中度思考模型 -->
                    <div class="mb-4">
                        <div class="d-flex align-center mb-2">
                            <v-icon size="small" color="indigo" class="mr-2">mdi-head-cog</v-icon>
                            <span class="text-subtitle-2">中度思考模型</span>
                            <v-chip size="x-small" variant="outlined" class="ml-2">平衡性能</v-chip>
                        </div>
                        <ModelSelector
                            v-model="localConfig.thinking_models.medium"
                            label="选择中度思考模型"
                            :providers="providers"
                            :loading="loadingProviders"
                            @refresh="$emit('refresh-providers')"
                        />
                    </div>

                    <!-- 快速思考模型 -->
                    <div>
                        <div class="d-flex align-center mb-2">
                            <v-icon size="small" color="blue" class="mr-2">mdi-lightning-bolt</v-icon>
                            <span class="text-subtitle-2">快速思考模型</span>
                            <v-chip size="x-small" variant="outlined" class="ml-2">快速响应</v-chip>
                        </div>
                        <ModelSelector
                            v-model="localConfig.thinking_models.fast"
                            label="选择快速思考模型"
                            :providers="providers"
                            :loading="loadingProviders"
                            @refresh="$emit('refresh-providers')"
                        />
                    </div>
                </v-card-text>
            </v-card>
        </v-card-text>
    </v-card>
</template>

<script lang="ts">
import { defineComponent, ref, watch } from 'vue';
import type { PropType } from 'vue';
import ModelSelector from './ModelSelector.vue';

interface ModelConfig {
    provider_id: string;
    model: string;
    temperature: number;
    max_tokens: number;
    thinking_enabled: boolean;
    thinking_budget?: number;
}

interface ThinkingModels {
    deep: ModelConfig;
    medium: ModelConfig;
    fast: ModelConfig;
}

interface ModelConfigData {
    function_model: ModelConfig;
    reply_model: ModelConfig;
    thinking_models: ThinkingModels;
}

export default defineComponent({
    name: 'ModelConfigSection',
    components: {
        ModelSelector
    },
    props: {
        modelValue: {
            type: Object as PropType<ModelConfigData>,
            default: () => ({
                function_model: {
                    provider_id: '',
                    model: '',
                    temperature: 0.7,
                    max_tokens: 2048,
                    thinking_enabled: false
                },
                reply_model: {
                    provider_id: '',
                    model: '',
                    temperature: 0.8,
                    max_tokens: 2048,
                    thinking_enabled: false
                },
                thinking_models: {
                    deep: {
                        provider_id: '',
                        model: '',
                        temperature: 0.7,
                        max_tokens: 4096,
                        thinking_enabled: false
                    },
                    medium: {
                        provider_id: '',
                        model: '',
                        temperature: 0.7,
                        max_tokens: 4096,
                        thinking_enabled: false
                    },
                    fast: {
                        provider_id: '',
                        model: '',
                        temperature: 0.7,
                        max_tokens: 2048,
                        thinking_enabled: false
                    }
                }
            })
        },
        providers: {
            type: Array as PropType<any[]>,
            default: () => []
        },
        loadingProviders: {
            type: Boolean,
            default: false
        }
    },
    emits: ['update:modelValue', 'refresh-providers'],
    setup(props, { emit }) {
        const localConfig = ref<ModelConfigData>({ ...props.modelValue });

        // 监听输入变化
        watch(localConfig, (newVal) => {
            emit('update:modelValue', newVal);
        }, { deep: true });

        // 监听props变化
        watch(() => props.modelValue, (newVal) => {
            localConfig.value = { ...newVal };
        }, { deep: true });

        return {
            localConfig
        };
    }
});
</script>
