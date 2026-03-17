<template>
    <v-menu v-model="menuOpen" :close-on-content-click="false" location="top" @update:model-value="handleMenuToggle">
        <template v-slot:activator="{ props: menuProps }">
            <v-chip v-bind="menuProps" class="text-none provider-chip" variant="tonal" :size="chipSize">
                <v-icon start size="14">mdi-creation</v-icon>
                <span v-if="selectedProviderId">
                    {{ selectedProviderId }}
                </span>
                <span v-else>Model</span>
            </v-chip>
        </template>
        <v-card class="provider-menu-card" min-width="280" max-width="400">
            <v-card-text class="pa-2">
                <v-text-field
                    v-model="searchQuery"
                    placeholder="Search..."
                    hide-details
                    variant="plain"
                    flat
                    density="compact"
                    prepend-inner-icon="mdi-magnify"
                    class="ml-2 mb-2 mr-2"
                    clearable
                />
                <v-list density="compact" nav class="provider-menu-list">
                    <v-list-item v-for="provider in filteredProviders" :key="provider.id"
                        :active="selectedProviderId === provider.id" @click="selectProvider(provider)" rounded="lg"
                        class="provider-menu-item">
                        <v-list-item-title class="text-body-2">{{ provider.id }}</v-list-item-title>
                        <v-list-item-subtitle class="provider-subtitle">
                            <span class="model-name">{{ provider.model }}</span>
                            <span class="meta-icons">
                                <v-tooltip text="支持图像输入" location="top" v-if="supportsImageInput(provider)">
                                    <template v-slot:activator="{ props: tipProps }">
                                        <v-icon v-bind="tipProps" size="12" color="grey">mdi-eye-outline</v-icon>
                                    </template>
                                </v-tooltip>
                                <v-tooltip text="支持工具调用" location="top" v-if="supportsToolCall(provider)">
                                    <template v-slot:activator="{ props: tipProps }">
                                        <v-icon v-bind="tipProps" size="12" color="grey">mdi-wrench</v-icon>
                                    </template>
                                </v-tooltip>
                                <v-tooltip text="支持推理" location="top" v-if="supportsReasoning(provider)">
                                    <template v-slot:activator="{ props: tipProps }">
                                        <v-icon v-bind="tipProps" size="12" color="grey">mdi-brain</v-icon>
                                    </template>
                                </v-tooltip>
                            </span>
                        </v-list-item-subtitle>
                    </v-list-item>
                </v-list>
                <div v-if="providerConfigs.length === 0" class="empty-hint">
                    No available models
                </div>
            </v-card-text>
        </v-card>
    </v-menu>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useDisplay } from 'vuetify';
import axios from 'axios';

interface ModelMetadata {
    modalities?: { input?: string[] };
    tool_call?: boolean;
    reasoning?: boolean;
}

interface ProviderConfig {
    id: string;
    model: string;
    api_base?: string;
    model_metadata?: ModelMetadata;
    enable?: boolean;
}

const { mobile } = useDisplay();

const providerConfigs = ref<ProviderConfig[]>([]);
const selectedProviderId = ref('');
const searchQuery = ref('');
const menuOpen = ref(false);

const chipSize = computed(() => mobile.value ? 'x-small' : 'small');

const filteredProviders = computed(() => {
    if (!searchQuery.value) {
        return providerConfigs.value;
    }
    const query = searchQuery.value.toLowerCase();
    return providerConfigs.value.filter(p => 
        p.id.toLowerCase().includes(query) || 
        p.model.toLowerCase().includes(query)
    );
});

function loadFromStorage() {
    const savedProvider = localStorage.getItem('selectedProvider');
    if (savedProvider) {
        selectedProviderId.value = savedProvider;
    }
}

function saveToStorage() {
    if (selectedProviderId.value) {
        localStorage.setItem('selectedProvider', selectedProviderId.value);
    }
}

function loadProviderConfigs() {
    axios.get('/api/config/provider/list', {
        params: { provider_type: 'chat_completion' }
    }).then(response => {
        if (response.data.status === 'ok') {
            // 过滤掉 enable 为 false 的配置
            providerConfigs.value = (response.data.data || []).filter(
                (p: ProviderConfig) => p.enable !== false
            );
        }
    }).catch(error => {
        console.error('获取提供商列表失败:', error);
    });
}

function selectProvider(provider: ProviderConfig) {
    selectedProviderId.value = provider.id;
    saveToStorage();
}

function supportsImageInput(provider: ProviderConfig): boolean {
    const inputs = provider.model_metadata?.modalities?.input || [];
    return inputs.includes('image');
}

function supportsToolCall(provider: ProviderConfig): boolean {
    return Boolean(provider.model_metadata?.tool_call);
}

function supportsReasoning(provider: ProviderConfig): boolean {
    return Boolean(provider.model_metadata?.reasoning);
}

function getCurrentSelection() {
    const provider = providerConfigs.value.find(p => p.id === selectedProviderId.value);
    return {
        providerId: selectedProviderId.value,
        modelName: provider?.model || ''
    };
}

function handleMenuToggle(isOpen: boolean) {
    if (isOpen) {
        // 每次打开菜单时重新获取数据
        loadProviderConfigs();
    }
}

onMounted(() => {
    loadFromStorage();
    loadProviderConfigs();
});

defineExpose({
    getCurrentSelection
});
</script>

<style scoped>
.provider-chip {
    cursor: pointer;
}

.provider-menu-card {
    border-radius: 12px !important;
}

.provider-menu-list {
    max-height: 280px;
    overflow-y: auto;
}

.provider-menu-item {
    margin-bottom: 2px;
    border-radius: 8px !important;
    min-height: 44px !important;
}

.provider-menu-item:hover {
    background-color: rgba(103, 58, 183, 0.05);
}

.provider-menu-item.v-list-item--active {
    background-color: rgba(103, 58, 183, 0.1);
}

.provider-subtitle {
    display: flex;
    align-items: center;
    gap: 8px;
}

.model-name {
    font-size: 12px;
    color: var(--v-theme-secondaryText);
}

.meta-icons {
    display: flex;
    align-items: center;
    gap: 4px;
}

.empty-hint {
    font-size: 12px;
    color: var(--v-theme-secondaryText);
    text-align: center;
    padding: 16px;
    opacity: 0.6;
}
</style>
