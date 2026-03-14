<template><!--          todo要配置国际化支持-->

    <v-card variant="outlined" class="model-selector">
        <v-card-text class="pa-3">
            <!-- 模型选择（Provider + Model 合并） -->
            <v-select
                :model-value="selectedModelId"
                :items="modelItems"
                :label="label || '选择模型'"
                :loading="loading"
                variant="outlined"
                density="comfortable"
                item-title="text"
                item-value="value"
                class="mb-3"
                @update:model-value="onModelSelect"
            >
                <template #append>
                    <v-btn
                        icon="mdi-refresh"
                        size="x-small"
                        variant="text"
                        @click.stop="$emit('refresh')"
                    />
                </template>
            </v-select>

            <!-- 模型名称输入 -->
<!--            <v-text-field-->
<!--                v-model="localModel.model"-->
<!--                label="模型名称"-->
<!--                :hint="modelHint"-->
<!--                variant="outlined"-->
<!--                density="comfortable"-->
<!--                persistent-hint-->
<!--                class="mb-3"-->
<!--            />-->

            <!-- 高级参数折叠面板 -->
            <v-expansion-panels variant="accordion" class="mb-2">
                <v-expansion-panel>
                    <v-expansion-panel-title>
                        <v-icon start size="small">mdi-tune</v-icon>
                        高级参数
                    </v-expansion-panel-title>
                    <v-expansion-panel-text>
                        <!-- Temperature -->
                        <v-slider
                            :model-value="temperature"
                            label="Temperature"
                            :min="0"
                            :max="2"
                            :step="0.1"
                            thumb-label
                            class="mb-2"
                            @update:model-value="updateTemperature"
                        >
                            <template #append>
                                <v-text-field
                                    :model-value="temperature"
                                    type="number"
                                    style="width: 80px"
                                    density="compact"
                                    hide-details
                                    variant="outlined"
                                    @update:model-value="updateTemperature"
                                />
                            </template>
                        </v-slider>

                        <!-- Max Tokens -->
                        <v-text-field
                            :model-value="maxTokens"
                            label="最大 Token 数"
                            type="number"
                            variant="outlined"
                            density="comfortable"
                            class="mb-3"
                            @update:model-value="updateMaxTokens"
                        />

                        <!-- Thinking Enabled -->
                        <v-switch
                            :model-value="thinkingEnabled"
                            label="启用思考模式"
                            color="primary"
                            hide-details
                            class="mb-2"
                            @update:model-value="updateThinkingEnabled"
                        />

                        <!-- Thinking Budget -->
                        <v-text-field
                            v-if="thinkingEnabled"
                            :model-value="thinkingBudget"
                            label="思考预算（可选）"
                            type="number"
                            hint="适用于 o1 类模型"
                            variant="outlined"
                            density="comfortable"
                            persistent-hint
                            @update:model-value="updateThinkingBudget"
                        />
                    </v-expansion-panel-text>
                </v-expansion-panel>
            </v-expansion-panels>

            <!-- 模型状态指示 -->
            <v-alert
                v-if="validationError"
                type="warning"
                variant="tonal"
                density="compact"
                class="mt-2"
            >
                {{ validationError }}
            </v-alert>
        </v-card-text>
    </v-card>
</template>

<script lang="ts">
import { defineComponent, computed, ref } from 'vue';
import type { PropType } from 'vue';

interface ModelConfig {
    provider_id: string;
    model: string;
    temperature: number;
    max_tokens: number;
    thinking_enabled: boolean;
    thinking_budget?: number;
}

interface Provider {
    id: string;
    name?: string;
    type?: string;
    models?: string[];
}

export default defineComponent({
    name: 'ModelSelector',
    props: {
        modelValue: {
            type: Object as PropType<ModelConfig>,
            default: () => ({
                provider_id: '',
                model: '',
                temperature: 0.7,
                max_tokens: 2048,
                thinking_enabled: false,
                thinking_budget: undefined
            })
        },
        label: {
            type: String,
            default: ''
        },
        providers: {
            type: Array as PropType<Provider[]>,
            default: () => []
        },
        loading: {
            type: Boolean,
            default: false
        }
    },
    emits: ['update:modelValue', 'refresh'],
    setup(props, { emit }) {
        const validationError = ref<string>('');

        // 构建模型下拉选项（Provider + Model 组合）
        const modelItems = computed(() => {
            const items: Array<{ text: string; value: string; provider_id: string; model: string }> = [];

            props.providers.forEach(provider => {
                const providerName = provider.name || provider.id;
                const models = provider.models || [];

                models.forEach(model => {
                    items.push({
                        text: `${providerName} - ${model}`,
                        value: `${provider.id}::${model}`,
                        provider_id: provider.id,
                        model: model
                    });
                });
            });

            return items;
        });

        // 当前选中的模型 ID
        const selectedModelId = computed(() => {
            if (!props.modelValue.provider_id || !props.modelValue.model) {
                return '';
            }
            return `${props.modelValue.provider_id}::${props.modelValue.model}`;
        });

        // 各个参数的 computed
        const temperature = computed(() => props.modelValue.temperature);
        const maxTokens = computed(() => props.modelValue.max_tokens);
        const thinkingEnabled = computed(() => props.modelValue.thinking_enabled);
        const thinkingBudget = computed(() => props.modelValue.thinking_budget);

        // 模型选择处理
        const onModelSelect = (value: string) => {
            if (!value) return;

            const [provider_id, model] = value.split('::');

            emit('update:modelValue', {
                ...props.modelValue,
                provider_id,
                model
            });

            validationError.value = '';
        };

        // 更新各个参数
        const updateTemperature = (value: any) => {
            emit('update:modelValue', {
                ...props.modelValue,
                temperature: Number(value)
            });
        };

        const updateMaxTokens = (value: any) => {
            emit('update:modelValue', {
                ...props.modelValue,
                max_tokens: Number(value)
            });
        };

        const updateThinkingEnabled = (value: boolean) => {
            emit('update:modelValue', {
                ...props.modelValue,
                thinking_enabled: value
            });
        };

        const updateThinkingBudget = (value: any) => {
            const numValue = value ? Number(value) : undefined;
            emit('update:modelValue', {
                ...props.modelValue,
                thinking_budget: numValue
            });
        };

        return {
            modelItems,
            selectedModelId,
            temperature,
            maxTokens,
            thinkingEnabled,
            thinkingBudget,
            validationError,
            onModelSelect,
            updateTemperature,
            updateMaxTokens,
            updateThinkingEnabled,
            updateThinkingBudget
        };
    }
});
</script>

<style scoped>
.model-selector {
    background-color: rgba(var(--v-theme-surface), 0.5);
}
</style>
