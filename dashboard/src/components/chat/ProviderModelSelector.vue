<template>
    <div>
        <!-- 选择提供商和模型按钮 -->
        <v-btn 
            class="text-none" 
            variant="tonal" 
            rounded="xl" 
            size="small" 
            v-if="selectedProviderId && selectedModelName" 
            @click="showDialog = true">
            {{ selectedProviderId }} / {{ selectedModelName }}
        </v-btn>
        <v-btn 
            variant="tonal" 
            rounded="xl" 
            size="small" 
            v-else 
            @click="showDialog = true">
            选择模型
        </v-btn>

        <!-- 选择提供商和模型对话框 -->
        <v-dialog v-model="showDialog" max-width="800" persistent>
            <v-card style="padding: 8px;">
                <v-card-title class="dialog-title">
                    <span>选择提供商和模型</span>
                </v-card-title>
                <v-card-text class="pa-0">
                    <div class="provider-model-container">
                        <!-- 左侧提供商列表 -->
                        <div class="provider-list-panel">
                            <div class="panel-header">
                                <h4>提供商</h4>
                            </div>
                            <v-list density="compact" nav class="provider-list">
                                <v-list-item 
                                    v-for="provider in providerConfigs" 
                                    :key="provider.id"
                                    :value="provider.id"
                                    @click="selectProvider(provider)"
                                    :active="selectedProviderId === provider.id"
                                    rounded="lg"
                                    class="provider-item">
                                    <v-list-item-title>{{ provider.id }}</v-list-item-title>
                                    <v-list-item-subtitle v-if="provider.api_base">{{ provider.api_base }}</v-list-item-subtitle>
                                </v-list-item>
                            </v-list>
                            <div v-if="providerConfigs.length === 0" class="empty-state">
                                <v-icon icon="mdi-cloud-off-outline" size="large" color="grey-lighten-1"></v-icon>
                                <div class="empty-text">暂无可用提供商</div>
                            </div>
                        </div>

                        <!-- 右侧模型列表 -->
                        <div class="model-list-panel">
                            <div class="panel-header">
                                <h4>模型</h4>
                                <v-btn 
                                    v-if="selectedProviderId" 
                                    icon="mdi-refresh" 
                                    size="small" 
                                    variant="text" 
                                    @click="refreshModels"
                                    :loading="loadingModels">
                                </v-btn>
                            </div>
                            <v-list density="compact" nav class="model-list" v-if="selectedProviderId">
                                <v-list-item 
                                    v-for="model in modelList" 
                                    :key="model"
                                    :value="model"
                                    @click="selectModel(model)"
                                    :active="selectedModelName === model"
                                    rounded="lg"
                                    class="model-item">
                                    <v-list-item-title>{{ model }}</v-list-item-title>
                                    <v-list-item-subtitle v-if="model.description">{{ model.description }}</v-list-item-subtitle>
                                </v-list-item>
                            </v-list>
                            <div v-else class="empty-state">
                                <v-icon icon="mdi-robot-outline" size="large" color="grey-lighten-1"></v-icon>
                                <div class="empty-text">请先选择提供商</div>
                            </div>
                            <div v-if="selectedProviderId && modelList.length === 0 && !loadingModels" class="empty-state">
                                <v-icon icon="mdi-robot-off-outline" size="large" color="grey-lighten-1"></v-icon>
                                <div class="empty-text">该提供商暂无可用模型</div>
                            </div>
                        </div>
                    </div>
                </v-card-text>
                <v-card-actions>
                    <v-spacer></v-spacer>
                    <v-btn text @click="closeDialog" color="grey-darken-1">取消</v-btn>
                    <v-btn 
                        text 
                        @click="confirmSelection" 
                        color="primary"
                        :disabled="!selectedProviderId || !selectedModelName">
                        确认选择
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
    </div>
</template>

<script>
import axios from 'axios';

export default {
    name: 'ProviderModelSelector',
    props: {
        initialProvider: {
            type: String,
            default: ''
        },
        initialModel: {
            type: String,
            default: ''
        }
    },
    emits: ['selection-changed'],
    data() {
        return {
            showDialog: false,
            providerConfigs: [],
            modelList: [],
            selectedProviderId: '',
            selectedModelName: '',
            loadingModels: false
        };
    },
    mounted() {
        // 从localStorage加载保存的选择
        this.loadFromStorage();
        // 获取提供商列表
        this.loadProviderConfigs();
        // 如果有保存的选择，加载对应的模型列表
        if (this.selectedProviderId) {
            this.getProviderModels(this.selectedProviderId);
        }
    },
    methods: {
        // 从localStorage加载保存的选择
        loadFromStorage() {
            const savedProvider = localStorage.getItem('selectedProvider');
            const savedModel = localStorage.getItem('selectedModel');
            
            if (savedProvider) {
                this.selectedProviderId = savedProvider;
            } else if (this.initialProvider) {
                this.selectedProviderId = this.initialProvider;
            }
            
            if (savedModel) {
                this.selectedModelName = savedModel;
            } else if (this.initialModel) {
                this.selectedModelName = this.initialModel;
            }
        },

        // 保存到localStorage
        saveToStorage() {
            if (this.selectedProviderId) {
                localStorage.setItem('selectedProvider', this.selectedProviderId);
            }
            if (this.selectedModelName) {
                localStorage.setItem('selectedModel', this.selectedModelName);
            }
        },

        // 获取提供商配置列表
        loadProviderConfigs() {
            axios.get('/api/config/provider/list', {
                params: {
                    provider_type: 'chat_completion'
                }
            })
                .then(response => {
                    if (response.data.status === 'ok') {
                        this.providerConfigs = response.data.data || [];
                    } else {
                        console.error('获取聊天完成提供商列表失败:', response.data.message);
                    }
                })
                .catch(error => {
                    console.error('获取聊天完成提供商列表失败:', error);
                });
        },

        // 获取指定提供商的模型列表
        getProviderModels(providerId) {
            this.loadingModels = true;
            axios.get('/api/config/provider/model_list', {
                params: {
                    provider_id: providerId
                }
            })
                .then(response => {
                    if (response.data.status === 'ok') {
                        this.modelList = response.data.data.models || [];
                    } else {
                        console.error('获取模型列表失败:', response.data.message);
                        this.modelList = [];
                    }
                })
                .catch(error => {
                    console.error('获取模型列表失败:', error);
                    this.modelList = [];
                })
                .finally(() => {
                    this.loadingModels = false;
                });
        },

        // 选择提供商
        selectProvider(provider) {
            this.selectedProviderId = provider.id;
            this.selectedModelName = ''; // 清空已选择的模型
            this.modelList = []; // 清空模型列表
            this.getProviderModels(provider.id); // 获取该提供商的模型列表
        },

        // 选择模型
        selectModel(model) {
            this.selectedModelName = model;
        },

        // 刷新模型列表
        refreshModels() {
            if (this.selectedProviderId) {
                this.getProviderModels(this.selectedProviderId);
            }
        },

        // 确认选择
        confirmSelection() {
            if (this.selectedProviderId && this.selectedModelName) {
                // 保存到localStorage
                this.saveToStorage();
                
                // 触发事件通知父组件
                this.$emit('selection-changed', {
                    providerId: this.selectedProviderId,
                    modelName: this.selectedModelName
                });
                
                this.closeDialog();
            }
        },

        // 关闭对话框
        closeDialog() {
            this.showDialog = false;
        },

        // 公开方法：获取当前选择
        getCurrentSelection() {
            return {
                providerId: this.selectedProviderId,
                modelName: this.selectedModelName
            };
        }
    }
};
</script>

<style scoped>
/* 对话框标题样式 */
.dialog-title {
    font-size: 18px;
    font-weight: 500;
    padding-bottom: 8px;
}

/* 提供商和模型选择对话框样式 */
.provider-model-container {
    display: flex;
    height: 500px;
    border: 1px solid var(--v-theme-border);
    border-radius: 8px;
    overflow: hidden;
}

.provider-list-panel,
.model-list-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    background-color: var(--v-theme-surface);
}

.provider-list-panel {
    border-right: 1px solid var(--v-theme-border);
}

.panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px;
    border-bottom: 1px solid var(--v-theme-border);
    background-color: var(--v-theme-containerBg);
}

.panel-header h4 {
    margin: 0;
    font-size: 16px;
    font-weight: 500;
    color: var(--v-theme-primaryText);
}

.provider-list,
.model-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
}

.provider-item,
.model-item {
    margin-bottom: 4px;
    border-radius: 8px !important;
    transition: all 0.2s ease;
    cursor: pointer;
}

.provider-item:hover,
.model-item:hover {
    background-color: rgba(103, 58, 183, 0.05);
}

.provider-item.v-list-item--active,
.model-item.v-list-item--active {
    background-color: rgba(103, 58, 183, 0.1);
    color: var(--v-theme-secondary);
}

.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 200px;
    opacity: 0.6;
    gap: 12px;
}

.empty-text {
    font-size: 14px;
    color: var(--v-theme-secondaryText);
}
</style>
