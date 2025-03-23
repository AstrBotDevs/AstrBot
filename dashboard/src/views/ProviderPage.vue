<template>
    <v-card style="height: 100%;">
        <v-card-text style="padding: 32px; height: 100%;">

            <v-menu>
                <template v-slot:activator="{ props }">
                    <v-btn class="flex-grow-1" variant="tonal" @click="new_provider_dialog = true" size="large"
                        rounded="lg" v-bind="props" color="primary">
                        <template v-slot:default>
                            <v-icon>mdi-plus</v-icon>
                            新增服务提供商
                        </template>
                    </v-btn>
                </template>
                <v-list @update:selected="addFromDefaultConfigTmpl($event)">
                    <v-list-item
                        v-for="(item, index) in metadata['provider_group']['metadata']['provider'].config_template"
                        :key="index" rounded="xl" :value="index">
                        <v-list-item-title>{{ index }}</v-list-item-title>
                    </v-list-item>
                </v-list>
            </v-menu>
            <v-row style="margin-top: 16px;">
                <v-col v-for="(provider, index) in config_data['provider']" :key="index" cols="12" md="6" lg="3">
                    <v-card class="fade-in" style="margin-bottom: 16px; min-height: 250px; max-height: 250px; display: flex; justify-content: space-between; flex-direction: column;">
                        <v-card-title class="d-flex justify-space-between align-center">
                            <span class="text-h4">{{ provider.id }}</span>
                            <v-switch color="primary" hide-details density="compact" v-model="provider['enable']"
                                @update:modelValue="providerStatusChange(provider)"></v-switch>
                        </v-card-title>
                        <v-card-text>
                            <div>
                                <span style="font-size:12px">适配器类型: </span> <v-chip size="small" color="primary" text>{{ provider.type }}</v-chip>
                            </div>
                            <div v-if="provider?.api_base" style="margin-top: 8px;">
                                <span style="font-size:12px">API Base: </span> <v-chip size="small" color="primary" text>{{ provider?.api_base }}</v-chip>
                            </div>
                        </v-card-text>
                        <v-card-actions class="d-flex justify-end">
                            <v-btn color="error" text @click="deleteprovider(provider.id);">
                                删除
                            </v-btn>
                            <v-btn color="blue-darken-1" text
                                @click="configExistingProvider(provider)">
                                配置
                            </v-btn>
                        </v-card-actions>
                    </v-card>
                </v-col>
            </v-row>
            <v-dialog v-model="showproviderCfg" width="900">
                <v-card>
                    <v-card-title>
                        <span class="text-h4">{{ newSelectedproviderName }} 配置</span>
                    </v-card-title>
                    <v-card-text>
                        <AstrBotConfig :iterable="newSelectedproviderConfig"
                            :metadata="metadata['provider_group']['metadata']" metadataKey="provider" />
                    </v-card-text>
                    <v-card-actions>
                        <v-spacer></v-spacer>
                        <v-btn color="blue-darken-1" variant="text" @click="newprovider" :loading="loading">
                            保存
                        </v-btn>
                    </v-card-actions>
                </v-card>
            </v-dialog>

            <v-btn style="margin-top: 16px" class="flex-grow-1" variant="tonal"  size="large" rounded="lg" color="gray" @click="showConsole = !showConsole">
                <template v-slot:default>
                    <v-icon>mdi-console-line</v-icon>
                    {{ showConsole ? '隐藏' : '显示' }}日志
                </template>
            </v-btn>

            <div v-if="showConsole" style="margin-top: 32px">
                <ConsoleDisplayer style="background-color: #000; height: 300px"></ConsoleDisplayer>
            </div>

        </v-card-text>
    </v-card>

    <v-snackbar :timeout="3000" elevation="24" :color="save_message_success" v-model="save_message_snack">
        {{ save_message }}
    </v-snackbar>
    <WaitingForRestart ref="wfr"></WaitingForRestart>
</template>
<script>

import axios from 'axios';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';

export default {
    name: 'ProviderPage',
    components: {
        AstrBotConfig,
        WaitingForRestart,
        ConsoleDisplayer
    },
    data() {
        return {
            config_data: {},
            fetched: false,
            metadata: {},
            showproviderCfg: false,

            newSelectedproviderName: '',
            newSelectedproviderConfig: {},
            updatingMode: false,

            loading: false,

            save_message_snack: false,
            save_message: "",
            save_message_success: "",

            showConsole: false,
        }
    },

    mounted() {
        this.getConfig();
    },

    methods: {
        getConfig() {
            // 获取配置
            axios.get('/api/config/get').then((res) => {
                this.config_data = res.data.data.config;
                this.fetched = true
                this.metadata = res.data.data.metadata;
            }).catch((err) => {
                save_message = err;
                save_message_snack = true;
                save_message_success = "error";
            });
        },

        addFromDefaultConfigTmpl(index) {
            // 从默认配置模板中添加
            console.log(index);
            this.newSelectedproviderName = index[0];
            this.showproviderCfg = true;
            this.updatingMode = false;
            this.newSelectedproviderConfig = this.metadata['provider_group']['metadata']['provider'].config_template[index[0]];
        },

        newprovider() {
            // 新建或者更新平台
            this.loading = true;
            if (this.updatingMode) {
                axios.post('/api/config/provider/update', {
                    id: this.newSelectedproviderName,
                    config: this.newSelectedproviderConfig
                }).then((res) => {
                    this.loading = false;
                    this.showproviderCfg = false;
                    this.getConfig();
                    // this.$refs.wfr.check();
                    this.save_message = res.data.message;
                    this.save_message_snack = true;
                    this.save_message_success = "success";
                }).catch((err) => {
                    this.loading = false;
                    this.save_message = err;
                    this.save_message_snack = true;
                    this.save_message_success = "error";
                });
                this.updatingMode = false;
            } else {
                axios.post('/api/config/provider/new', this.newSelectedproviderConfig).then((res) => {
                    this.loading = false;
                    this.showproviderCfg = false;
                    this.getConfig();
                }).catch((err) => {
                    this.loading = false;
                    this.save_message = err;
                    this.save_message_snack = true;
                    this.save_message_success = "error";
                });
            }
        },

        deleteprovider(provider_id) {
            // 删除平台
            axios.post('/api/config/provider/delete', { id: provider_id }).then((res) => {
                this.getConfig();
                // this.$refs.wfr.check();
                this.save_message = res.data.message;
                this.save_message_snack = true;
                this.save_message_success = "success";
            }).catch((err) => {
                this.save_message = err;
                this.save_message_snack = true;
                this.save_message_success = "error";
            });
        },

        providerStatusChange(provider) {
            // 平台状态改变
            axios.post('/api/config/provider/update', {
                id: provider.id,
                config: provider
            }).then((res) => {
                this.getConfig();
                // this.$refs.wfr.check();
                this.save_message = res.data.message;
                this.save_message_snack = true;
                this.save_message_success = "success";
            }).catch((err) => {
                this.save_message = err;
                this.save_message_snack = true;
                this.save_message_success = "error";
            });
        },

        configExistingProvider(provider) {
            // 配置现有平台
            this.newSelectedproviderName = provider.id;
            this.newSelectedproviderConfig = {};

            // 比对默认配置模版，看看是否有更新
            let templates = this.metadata['provider_group']['metadata']['provider'].config_template;
            let defaultConfig = {};
            for (let key in templates) {
                if (templates[key]?.type === provider.type) {
                    defaultConfig = templates[key];
                    break;
                }
            }
            const mergeConfigWithOrder = (target, source, reference) => {
                // 首先复制所有source中的属性到target
                if (source && typeof source === 'object' && !Array.isArray(source)) {
                    for (let key in source) {
                        if (source.hasOwnProperty(key)) {
                            if (typeof source[key] === 'object' && source[key] !== null) {
                                target[key] = Array.isArray(source[key]) ? [...source[key]] : {...source[key]};
                            } else {
                                target[key] = source[key];
                            }
                        }
                    }
                }
                
                // 然后根据reference的结构添加或覆盖属性
                for (let key in reference) {
                    if (typeof reference[key] === 'object' && reference[key] !== null) {
                        if (!(key in target)) {
                            target[key] = Array.isArray(reference[key]) ? [] : {};
                        }
                        mergeConfigWithOrder(
                            target[key], 
                            source && source[key] ? source[key] : {}, 
                            reference[key]
                        );
                    } else if (!(key in target)) {
                        // 只有当target中不存在该键时才从reference复制
                        target[key] = reference[key];
                    }
                }
            };
            if (defaultConfig) {
                mergeConfigWithOrder(this.newSelectedproviderConfig, provider, defaultConfig);
            }

            this.showproviderCfg = true;
            this.updatingMode = true;
        }

    }
}

</script>

<style>
@keyframes fadeIn {
    from {
        opacity: 0;
    }

    to {
        opacity: 1;
    }
}

.fade-in {
    animation: fadeIn 0.2s ease-in-out;
}
</style>