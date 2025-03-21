<template>
    <v-card style="height: 100%;">
        <v-card-text style="padding: 32px; height: 100%;">

            <v-menu>
                <template v-slot:activator="{ props }">
                    <v-btn class="flex-grow-1" variant="tonal" @click="new_platform_dialog = true" size="large"
                        rounded="lg" v-bind="props" color="primary">
                        <template v-slot:default>
                            <v-icon>mdi-plus</v-icon>
                            新增平台适配器
                        </template>
                    </v-btn>
                </template>
                <v-list @update:selected="addFromDefaultConfigTmpl($event)">
                    <v-list-item
                        v-for="(item, index) in metadata['platform_group']['metadata']['platform'].config_template"
                        :key="index" rounded="xl" :value="index">
                        <v-list-item-title>{{ index }}</v-list-item-title>
                    </v-list-item>
                </v-list>
            </v-menu>
            <v-row style="margin-top: 16px;">
                <v-col v-for="(platform, index) in config_data['platform']" :key="index" cols="12" md="6" lg="3">
                    <v-card class="fade-in"
                        style="margin-bottom: 16px; min-height: 250px; max-height: 250px; display: flex; justify-content: space-between; flex-direction: column;">
                        <v-card-title class="d-flex justify-space-between align-center">
                            <span class="text-h4">{{ platform.id }}</span>
                            <v-switch color="primary" hide-details density="compact" v-model="platform['enable']"
                                @update:modelValue="platformStatusChange(platform)"></v-switch>
                        </v-card-title>
                        <v-card-text>
                            <div>
                                <span style="font-size:12px">适配器类型: </span>
                                <v-chip size="small" color="primary" text>{{ platform.type }}</v-chip>
                            </div>
                        </v-card-text>
                        <v-card-actions class="d-flex justify-end">
                            <v-btn color="error" text @click="deletePlatform(platform.id);">
                                删除
                            </v-btn>
                            <v-btn color="blue-darken-1" text
                                @click="configExistingPlatform(platform)">
                                配置
                            </v-btn>
                        </v-card-actions>
                    </v-card>
                </v-col>
            </v-row>
            <v-dialog v-model="showPlatformCfg">
                <v-card>
                    <v-card-title>
                        <span class="text-h4">{{ newSelectedPlatformName }} 配置</span>
                    </v-card-title>
                    <v-card-text>
                        <v-row>
                            <v-col cols="12" md="6">
                                <AstrBotConfig :iterable="newSelectedPlatformConfig"
                                    :metadata="metadata['platform_group']['metadata']" metadataKey="platform" />
                            </v-col>
                            <v-col cols="12" md="6">
                                <v-btn :loading="iframeLoading" @click="refreshIframe" variant="tonal" color="primary" style="float: right;">
                                    <v-icon>mdi-refresh</v-icon>
                                    刷新
                                </v-btn>
                                <iframe v-show="!iframeLoading"
                                    :src="store.getTutorialLink(newSelectedPlatformConfig.type)"
                                    @load="iframeLoading = false" style="width: 100%; border: none; height: 100%;">
                                </iframe>
                            </v-col>
                        </v-row>

                    </v-card-text>
                    <v-card-actions>
                        <v-spacer></v-spacer>
                        <v-btn color="blue-darken-1" variant="text" @click="newPlatform" :loading="loading">
                            保存
                        </v-btn>
                    </v-card-actions>
                </v-card>
            </v-dialog>


            <v-btn style="margin-top: 16px" class="flex-grow-1" variant="tonal" size="large" rounded="lg" color="gray"
                @click="showConsole = !showConsole">
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
import { useCommonStore } from '@/stores/common';

export default {
    name: 'PlatformPage',
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
            showPlatformCfg: false,

            newSelectedPlatformName: '',
            newSelectedPlatformConfig: {},
            updatingMode: false,

            loading: false,

            save_message_snack: false,
            save_message: "",
            save_message_success: "",

            showConsole: false,
            iframeLoading: true,

            store: useCommonStore()
        }
    },

    mounted() {
        this.getConfig();
    },

    methods: {
        refreshIframe() {
            this.iframeLoading = true;
            const iframe = document.querySelector('iframe');
            console.log(iframe.src);
            iframe.src = iframe.src + '?t=' + new Date().getTime();
        },
        getConfig() {
            // 获取配置
            axios.get('/api/config/get').then((res) => {
                this.config_data = res.data.data.config;
                this.fetched = true
                this.metadata = res.data.data.metadata;
            }).catch((err) => {
                this.save_message = err;
                this.save_message_snack = true;
                this.save_message_success = "error";
            });
        },

        addFromDefaultConfigTmpl(index) {
            // 从默认配置模板中添加
            console.log(index);
            this.newSelectedPlatformName = index[0];
            this.showPlatformCfg = true;
            this.updatingMode = false;
            this.newSelectedPlatformConfig = this.metadata['platform_group']['metadata']['platform'].config_template[index[0]];
        },

        newPlatform() {
            // 新建或者更新平台
            this.loading = true;
            if (this.updatingMode) {
                axios.post('/api/config/platform/update', {
                    id: this.newSelectedPlatformName,
                    config: this.newSelectedPlatformConfig
                }).then((res) => {
                    this.loading = false;
                    this.showPlatformCfg = false;
                    this.getConfig();
                    this.$refs.wfr.check();
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
                axios.post('/api/config/platform/new', this.newSelectedPlatformConfig).then((res) => {
                    this.loading = false;
                    this.showPlatformCfg = false;
                    this.getConfig();
                    this.save_message = res.data.message;
                    this.save_message_snack = true;
                    this.save_message_success = "success";
                }).catch((err) => {
                    this.loading = false;
                    this.save_message = err;
                    this.save_message_snack = true;
                    this.save_message_success = "error";
                });
            }
        },

        deletePlatform(platform_id) {
            // 删除平台
            axios.post('/api/config/platform/delete', { id: platform_id }).then((res) => {
                this.getConfig();
                this.$refs.wfr.check();
                this.save_message = res.data.message;
                this.save_message_snack = true;
                this.save_message_success = "success";
            }).catch((err) => {
                this.save_message = err;
                this.save_message_snack = true;
                this.save_message_success = "error";
            });
        },

        platformStatusChange(platform) {
            // 平台状态改变
            axios.post('/api/config/platform/update', {
                id: platform.id,
                config: platform
            }).then((res) => {
                this.getConfig();
                this.$refs.wfr.check();
                this.save_message = res.data.message;
                this.save_message_snack = true;
                this.save_message_success = "success";
            }).catch((err) => {
                this.save_message = err;
                this.save_message_snack = true;
                this.save_message_success = "error";
            });
        },

        configExistingPlatform(platform) {
            // 配置现有平台
            this.newSelectedPlatformName = platform.id;
            this.newSelectedPlatformConfig = {};

            // 比对默认配置模版，看看是否有更新
            let templates = this.metadata['platform_group']['metadata']['platform'].config_template;
            let defaultConfig = {};
            for (let key in templates) {
                if (templates[key]?.type === platform.type) {
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
                mergeConfigWithOrder(this.newSelectedPlatformConfig, platform, defaultConfig);
            }

            this.showPlatformCfg = true;
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