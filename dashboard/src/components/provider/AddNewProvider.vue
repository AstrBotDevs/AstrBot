<template>
    <v-dialog v-model="showDialog" max-width="1100px" min-height="95%">
        <v-card :title="tm('dialogs.addProvider.title')">
            <v-card-text style="overflow-y: auto;">
                <v-tabs v-model="activeProviderTab" grow>
                    <v-tab value="agent_runner" class="font-weight-medium px-3">
                        <v-icon start>mdi-cogs</v-icon>
                        {{ tm('dialogs.addProvider.tabs.agentRunner') }}
                    </v-tab>
                    <v-tab value="speech_to_text" class="font-weight-medium px-3">
                        <v-icon start>mdi-microphone-message</v-icon>
                        {{ tm('dialogs.addProvider.tabs.speechToText') }}
                    </v-tab>
                    <v-tab value="text_to_speech" class="font-weight-medium px-3">
                        <v-icon start>mdi-volume-high</v-icon>
                        {{ tm('dialogs.addProvider.tabs.textToSpeech') }}
                    </v-tab>
                    <v-tab value="embedding" class="font-weight-medium px-3">
                        <v-icon start>mdi-code-json</v-icon>
                        {{ tm('dialogs.addProvider.tabs.embedding') }}
                    </v-tab>
                    <v-tab value="rerank" class="font-weight-medium px-3">
                        <v-icon start>mdi-compare-vertical</v-icon>
                        {{ tm('dialogs.addProvider.tabs.rerank') }}
                    </v-tab>
                </v-tabs>

                <v-window v-model="activeProviderTab" class="mt-4">
                    <v-window-item
                        v-for="tabType in ['chat_completion', 'agent_runner', 'speech_to_text', 'text_to_speech', 'embedding', 'rerank']"
                        :key="tabType" :value="tabType">
                        <v-row class="mt-1">
                            <v-col v-for="(template, name) in getTemplatesByType(tabType)" :key="name" cols="12" sm="6"
                                md="4">
                                <v-card variant="outlined" hover class="provider-card"
                                    @click="selectProviderTemplate(name)">
                                    <div class="provider-card-content">
                                        <div class="provider-card-text">
                                            <v-card-title class="provider-card-title">{{ name }}</v-card-title>
                                            <v-card-text
                                                class="text-caption text-medium-emphasis provider-card-description">
                                                {{ getProviderDescription(template, name) }}
                                            </v-card-text>
                                        </div>
                                        <div class="provider-card-logo">
                                            <img :src="getProviderIcon(template.provider)"
                                                v-if="getProviderIcon(template.provider)" class="provider-logo-img">
                                            <div v-else class="provider-logo-fallback">
                                                {{ name[0].toUpperCase() }}
                                            </div>
                                        </div>
                                    </div>
                                </v-card>
                            </v-col>
                            <v-col v-if="Object.keys(getTemplatesByType(tabType)).length === 0" cols="12">
                                <v-alert type="info" variant="tonal">
                                    {{ tm('dialogs.addProvider.noTemplates') }}
                                </v-alert>
                            </v-col>
                        </v-row>
                    </v-window-item>
                </v-window>
            </v-card-text>
            <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn text @click="closeDialog">{{ tm('dialogs.config.cancel') }}</v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>
</template>

<script>
import { useModuleI18n } from '@/i18n/composables';
import { getProviderIcon, getProviderDescription } from '@/utils/providerUtils';

export default {
    name: 'AddNewProvider',
    props: {
        show: {
            type: Boolean,
            default: false
        },
        metadata: {
            type: Object,
            default: () => ({})
        }
    },
    emits: ['update:show', 'select-template'],
    setup() {
        const { tm } = useModuleI18n('features/provider');
        return { tm };
    },
    data() {
        return {
            activeProviderTab: 'chat_completion'
        };
    },
    computed: {
        showDialog: {
            get() {
                return this.show;
            },
            set(value) {
                this.$emit('update:show', value);
            }
        },
    },
    methods: {
        closeDialog() {
            this.showDialog = false;
        },

        // 按提供商类型获取模板列表
        getTemplatesByType(type) {
            const templates = this.metadata.provider.config_template || {};
            const filtered = {};

            for (const [name, template] of Object.entries(templates)) {
                if (template.provider_type === type) {
                    filtered[name] = template;
                }
            }

            return filtered;
        },

        // 从工具函数导入
        getProviderIcon,

        // 获取提供商简介
        getProviderDescription(template, name) {
            return getProviderDescription(template, name, this.tm);
        },

        // 选择提供商模板
        selectProviderTemplate(name) {
            this.$emit('select-template', name);
            this.closeDialog();
        }
    }
}
</script>

<style scoped>
.provider-card {
    transition: all 0.3s ease;
    height: 100%;
    cursor: pointer;
    overflow: hidden;
    position: relative;
}

.provider-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 4px 25px 0 rgba(0, 0, 0, 0.05);
    border-color: var(--v-primary-base);
}

.provider-card-content {
    display: flex;
    align-items: center;
    height: 100px;
    padding: 16px;
    position: relative;
    z-index: 2;
}

.provider-card-text {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
}

.provider-card-title {
    font-size: 15px;
    font-weight: 600;
    margin-bottom: 4px;
    padding: 0;
}

.provider-card-description {
    padding: 0;
    margin: 0;
}

.provider-card-logo {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    width: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1;
}

.provider-logo-img {
    width: 60px;
    height: 60px;
    opacity: 0.6;
    object-fit: contain;
}

.provider-logo-fallback {
    width: 50px;
    height: 50px;
    border-radius: 50%;
    background-color: var(--v-primary-base);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    font-weight: bold;
    opacity: 0.3;
}
</style>
