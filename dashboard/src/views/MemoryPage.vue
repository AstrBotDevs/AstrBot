<template>
    <div class="memory-page">
        <v-container fluid class="pa-0">
            <!-- 页面标题 -->
            <v-row class="d-flex justify-space-between align-center px-4 py-3 pb-8">
                <div>
                    <h1 class="text-h1 font-weight-bold mb-2">
                        <v-icon color="black" class="me-2">mdi-brain</v-icon>{{ t('core.navigation.memory') }}
                    </h1>
                    <p class="text-subtitle-1 text-medium-emphasis mb-4">
                        管理长期记忆系统的配置
                    </p>
                </div>
            </v-row>

            <!-- 加载状态 -->
            <v-row v-if="loading">
                <v-col cols="12">
                    <v-card>
                        <v-card-text class="text-center">
                            <v-progress-circular indeterminate color="primary"></v-progress-circular>
                        </v-card-text>
                    </v-card>
                </v-col>
            </v-row>

            <!-- 主内容 -->
            <v-row v-else>
                <v-col cols="12" md="8" lg="6">
                    <v-card rounded="lg">
                        <v-card-title class="d-flex align-center">
                            <v-icon class="mr-2">mdi-cog</v-icon>
                            记忆系统配置
                        </v-card-title>
                        <v-divider></v-divider>

                        <v-card-text>
                            <!-- 状态显示 -->
                            <v-alert 
                                :type="memoryStatus.initialized ? 'success' : 'info'" 
                                variant="tonal"
                                class="mb-4"
                            >
                                <div class="d-flex align-center">
                                    <v-icon class="mr-2">
                                        {{ memoryStatus.initialized ? 'mdi-check-circle' : 'mdi-information' }}
                                    </v-icon>
                                    <div>
                                        <strong>状态：</strong>
                                        {{ memoryStatus.initialized ? '已初始化' : '未初始化' }}
                                    </div>
                                </div>
                            </v-alert>

                            <!-- 未初始化时显示初始化表单 -->
                            <div v-if="!memoryStatus.initialized">
                                <v-form @submit.prevent="initializeMemory">
                                    <v-select
                                        v-model="selectedEmbeddingProvider"
                                        :items="embeddingProviders"
                                        item-title="text"
                                        item-value="value"
                                        label="Embedding 模型 *"
                                        hint="用于生成向量表示，初始化后不可更改"
                                        persistent-hint
                                        class="mb-4"
                                        required
                                        :disabled="initializing"
                                    ></v-select>

                                    <v-select
                                        v-model="selectedMergeLLM"
                                        :items="llmProviders"
                                        item-title="text"
                                        item-value="value"
                                        label="合并 LLM *"
                                        hint="用于合并相似记忆，可在初始化后更改"
                                        persistent-hint
                                        class="mb-4"
                                        required
                                        :disabled="initializing"
                                    ></v-select>

                                    <v-btn
                                        type="submit"
                                        color="primary"
                                        :loading="initializing"
                                        :disabled="!selectedEmbeddingProvider || !selectedMergeLLM"
                                        block
                                        size="large"
                                    >
                                        初始化记忆系统
                                    </v-btn>
                                </v-form>
                            </div>

                            <!-- 已初始化时显示配置信息 -->
                            <div v-else>
                                <v-list>
                                    <v-list-item>
                                        <template v-slot:prepend>
                                            <v-icon>mdi-vector-triangle</v-icon>
                                        </template>
                                        <v-list-item-title>Embedding 模型</v-list-item-title>
                                        <v-list-item-subtitle>
                                            {{ getProviderName(memoryStatus.embedding_provider_id) }}
                                        </v-list-item-subtitle>
                                    </v-list-item>

                                    <v-divider class="my-2"></v-divider>

                                    <v-list-item>
                                        <template v-slot:prepend>
                                            <v-icon>mdi-robot</v-icon>
                                        </template>
                                        <v-list-item-title>合并 LLM</v-list-item-title>
                                        <v-list-item-subtitle>
                                            {{ getProviderName(memoryStatus.merge_llm_provider_id) }}
                                        </v-list-item-subtitle>
                                    </v-list-item>
                                </v-list>

                                <v-divider class="my-4"></v-divider>

                                <v-form @submit.prevent="updateMergeLLM">
                                    <v-select
                                        v-model="newMergeLLM"
                                        :items="llmProviders"
                                        item-title="text"
                                        item-value="value"
                                        label="更新合并 LLM"
                                        hint="可以更换用于合并记忆的 LLM"
                                        persistent-hint
                                        class="mb-4"
                                        :disabled="updating"
                                    ></v-select>

                                    <v-btn
                                        type="submit"
                                        color="primary"
                                        :loading="updating"
                                        :disabled="!newMergeLLM || newMergeLLM === memoryStatus.merge_llm_provider_id"
                                        block
                                        variant="tonal"
                                    >
                                        更新合并 LLM
                                    </v-btn>
                                </v-form>
                            </div>
                        </v-card-text>
                    </v-card>
                </v-col>

                <!-- 说明卡片 -->
                <v-col cols="12" md="4" lg="6">
                    <v-card rounded="lg">
                        <v-card-title class="d-flex align-center">
                            <v-icon class="mr-2">mdi-information</v-icon>
                            说明
                        </v-card-title>
                        <v-divider></v-divider>
                        <v-card-text>
                            <v-list density="compact">
                                <v-list-item>
                                    <v-list-item-title class="text-wrap">
                                        <strong>Embedding 模型：</strong>用于将文本转换为向量，支持语义相似度搜索。
                                        <v-chip size="x-small" color="warning" class="ml-2">不可更改</v-chip>
                                    </v-list-item-title>
                                </v-list-item>
                                <v-list-item>
                                    <v-list-item-title class="text-wrap">
                                        <strong>合并 LLM：</strong>当检测到相似记忆时，使用此模型合并为一条记忆。
                                        <v-chip size="x-small" color="success" class="ml-2">可更改</v-chip>
                                    </v-list-item-title>
                                </v-list-item>
                                <v-list-item>
                                    <v-list-item-title class="text-wrap">
                                        <strong>注意：</strong>Embedding 模型一旦选择后无法更改，请谨慎选择。
                                    </v-list-item-title>
                                </v-list-item>
                            </v-list>
                        </v-card-text>
                    </v-card>
                </v-col>
            </v-row>
        </v-container>

        <!-- 提示框 -->
        <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000">
            {{ snackbar.message }}
        </v-snackbar>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import axios from 'axios';
import { useI18n } from '@/i18n/composables';

const { t } = useI18n();

interface MemoryStatus {
    initialized: boolean;
    embedding_provider_id: string | null;
    merge_llm_provider_id: string | null;
}

interface Provider {
    value: string;
    text: string;
}

const loading = ref(true);
const initializing = ref(false);
const updating = ref(false);

const memoryStatus = ref<MemoryStatus>({
    initialized: false,
    embedding_provider_id: null,
    merge_llm_provider_id: null,
});

const embeddingProviders = ref<Provider[]>([]);
const llmProviders = ref<Provider[]>([]);

const selectedEmbeddingProvider = ref<string>('');
const selectedMergeLLM = ref<string>('');
const newMergeLLM = ref<string>('');

const snackbar = ref({
    show: false,
    message: '',
    color: 'success',
});

const showMessage = (message: string, color: string = 'success') => {
    snackbar.value.message = message;
    snackbar.value.color = color;
    snackbar.value.show = true;
};

const getProviderName = (providerId: string | null): string => {
    if (!providerId) return '未设置';
    const embedding = embeddingProviders.value.find(p => p.value === providerId);
    const llm = llmProviders.value.find(p => p.value === providerId);
    return embedding?.text || llm?.text || providerId;
};

const loadProviders = async () => {
    try {
        // Load embedding providers
        const embeddingResponse = await axios.get('/api/config/provider/list', {
            params: { provider_type: 'embedding' }
        });
        if (embeddingResponse.data.status === 'ok') {
            embeddingProviders.value = (embeddingResponse.data.data || []).map((p: any) => ({
                value: p.id,
                text: `${p.embedding_model} (${p.id})`,
            }));
        }

        // Load LLM providers
        const llmResponse = await axios.get('/api/config/provider/list', {
            params: { provider_type: 'chat_completion' }
        });
        if (llmResponse.data.status === 'ok') {
            llmProviders.value = (llmResponse.data.data || []).map((p: any) => ({
                value: p.id,
                text: `${p?.model_config?.model} (${p.id})`,
            }));
        }
    } catch (error) {
        console.error('Failed to load providers:', error);
        showMessage('加载提供商列表失败', 'error');
    }
};

const loadStatus = async () => {
    try {
        const response = await axios.get('/api/memory/status');
        if (response.data.status === 'ok') {
            memoryStatus.value = response.data.data;
            if (memoryStatus.value.merge_llm_provider_id) {
                newMergeLLM.value = memoryStatus.value.merge_llm_provider_id;
            }
        }
    } catch (error) {
        console.error('Failed to load memory status:', error);
        showMessage('加载记忆系统状态失败', 'error');
    }
};

const initializeMemory = async () => {
    if (!selectedEmbeddingProvider.value || !selectedMergeLLM.value) {
        showMessage('请选择 Embedding 模型和合并 LLM', 'warning');
        return;
    }

    initializing.value = true;
    try {
        const response = await axios.post('/api/memory/initialize', {
            embedding_provider_id: selectedEmbeddingProvider.value,
            merge_llm_provider_id: selectedMergeLLM.value,
        });

        if (response.data.status === 'ok') {
            showMessage('记忆系统初始化成功', 'success');
            await loadStatus();
        } else {
            showMessage(response.data.message || '初始化失败', 'error');
        }
    } catch (error: any) {
        console.error('Failed to initialize memory:', error);
        showMessage(error.response?.data?.message || '初始化失败', 'error');
    } finally {
        initializing.value = false;
    }
};

const updateMergeLLM = async () => {
    if (!newMergeLLM.value) {
        showMessage('请选择新的合并 LLM', 'warning');
        return;
    }

    updating.value = true;
    try {
        const response = await axios.post('/api/memory/update_merge_llm', {
            merge_llm_provider_id: newMergeLLM.value,
        });

        if (response.data.status === 'ok') {
            showMessage('合并 LLM 更新成功', 'success');
            await loadStatus();
        } else {
            showMessage(response.data.message || '更新失败', 'error');
        }
    } catch (error: any) {
        console.error('Failed to update merge LLM:', error);
        showMessage(error.response?.data?.message || '更新失败', 'error');
    } finally {
        updating.value = false;
    }
};

onMounted(async () => {
    loading.value = true;
    await Promise.all([loadProviders(), loadStatus()]);
    loading.value = false;
});
</script>

<style scoped>
.memory-page {
    min-height: 100vh;
    padding: 8px;
}
</style>
