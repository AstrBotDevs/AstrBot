<script setup>
import ExtensionCard from '@/components/shared/ExtensionCard.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import axios from 'axios';
import { useCommonStore } from '@/stores/common';
</script>

<template>
    <v-row>
        <v-col cols="12" md="12" v-if="announcement">
            <v-banner color="success" lines="one" :text="announcement" :stacked="false">
            </v-banner>
        </v-col>

        <v-col cols="12" md="12">
            <v-card>

                <v-card-title>
                    <div class="pl-2 pt-2 d-flex align-center pe-2">
                        <h2>✨ 插件市场</h2>
                        <v-btn icon size="small" style="margin-left: 8px" variant="plain" @click="jumpToPluginMarket()">
                            <v-icon size="small">mdi-help</v-icon>
                            <v-tooltip activator="parent" location="start">
                                <span>
                                    如无法显示，请单击此按钮跳转至插件市场，复制想安装插件对应的
                                    `repo`
                                    链接然后点击右下角 + 号安装，或打开链接下载压缩包安装。

                                    如果因为网络问题安装失败，点击设置页选择 GitHub 加速地址。或前往仓库下载压缩包然后本地上传。
                                </span>
                            </v-tooltip>
                        </v-btn>

                        <v-btn icon @click="isListView = !isListView" size="small" style="margin-left: auto;"
                            variant="plain">
                            <v-icon>{{ isListView ? 'mdi-view-grid' : 'mdi-view-list' }}</v-icon>
                        </v-btn>

                        <v-spacer></v-spacer>

                        <v-text-field v-model="marketSearch" density="compact" label="Search"
                            prepend-inner-icon="mdi-magnify" variant="solo-filled" flat hide-details
                            single-line></v-text-field>
                    </div>

                </v-card-title>

                <v-card-text>

                    <div v-if="pinnedPlugins.length > 0" class="mt-4">
                        <h2>🥳 推荐</h2>

                        <v-row style="margin-top: 8px;">
                            <v-col cols="12" md="6" lg="6" v-for="plugin in pinnedPlugins">
                                <ExtensionCard :extension="plugin" market-mode="true" :highlight="true">
                                </ExtensionCard>
                            </v-col>
                        </v-row>
                    </div>

                    

                    <div v-if="isListView" class="mt-4">
                        <h2>📦 全部插件</h2>
                        <v-col cols="12" md="12" style="padding: 0px;">
                            <v-data-table :headers="pluginMarketHeaders" :items="pluginMarketData" item-key="name"
                                :loading="loading_" v-model:search="marketSearch"
                                :filter-keys="['name', 'desc', 'author']">
                                <template v-slot:item.name="{ item }">
                                    <div class="d-flex align-center">
                                        <img v-if="item.logo" :src="item.logo"
                                            style="height: 80px; width: 80px; margin-right: 8px; border-radius: 8px; margin-top: 8px; margin-bottom: 8px;"
                                            alt="logo">
                                        <span v-if="item?.repo"><a :href="item?.repo"
                                                style="color: #000; text-decoration:none">{{
                                                    item.name }}</a></span>
                                        <span v-else>{{ item.name }}</span>

                                    </div>

                                </template>
                                <template v-slot:item.author="{ item }">
                                    <span v-if="item?.social_link"><a :href="item?.social_link">{{ item.author
                                            }}</a></span>
                                    <span v-else>{{ item.author }}</span>
                                </template>
                                <template v-slot:item.tags="{ item }">
                                    <span v-if="item.tags.length === 0">无</span>
                                    <v-chip v-for="tag in item.tags" :key="tag" color="primary" size="small">{{ tag
                                    }}</v-chip>
                                </template>
                                <template v-slot:item.actions="{ item }">
                                    <v-btn v-if="!item.installed" class="text-none mr-2" size="small" text="Read"
                                        variant="flat" border
                                        @click="extension_url = item.repo; newExtension()">安装</v-btn>
                                    <v-btn v-else class="text-none mr-2" size="small" text="Read" variant="flat" border
                                        disabled>已安装</v-btn>
                                </template>
                            </v-data-table>
                        </v-col>
                    </div>
                    <div v-else class="mt-4">
                        <h2>📦 全部插件</h2>
                        <v-row style="margin-top: 16px;">
                            <v-col cols="12" md="6" lg="6" v-for="plugin in filteredPluginMarketData">
                                <ExtensionCard :extension="plugin" market-mode="true">
                                </ExtensionCard>
                            </v-col>
                        </v-row>
                    </div>
                </v-card-text>

            </v-card>

        </v-col>


        <v-col style="margin-bottom: 16px;" cols="12" md="12">
            <small><a href="https://astrbot.app/dev/plugin.html">插件开发文档</a></small> |
            <small> <a href="https://github.com/Soulter/AstrBot_Plugins_Collection">提交插件仓库</a></small>
        </v-col>

    </v-row>

    <v-dialog v-model="dialog" width="700">
        <template v-slot:activator="{ props }">
            <v-btn v-bind="props" icon="mdi-plus" size="x-large" style="position: fixed; right: 52px; bottom: 52px;"
                color="darkprimary">
            </v-btn>
        </template>
        <v-card>
            <v-card-title>
                <span class="text-h5">安装插件</span>
            </v-card-title>
            <v-card-text>
                <v-container>
                    <v-row>
                        <h3>从 GitHub 上在线下载</h3>
                        <v-col cols="12">
                            <small>请输入合法的 GitHub 仓库链接，当前仅支持
                                GitHub。如：https://github.com/Soulter/astrbot_plugin_aiocqhttp</small>
                            <v-text-field label="仓库链接" v-model="extension_url" variant="outlined"
                                required></v-text-field>
                        </v-col>
                    </v-row>
                    <v-row>
                        <h3>从本机上传 .zip 压缩包</h3>
                        <v-col cols="12">
                            <small>请保证插件文件存在压缩包根目录中的第一个文件夹中（即类似于从 GitHub 仓库页上下载的 Zip 压缩包的格式）。</small>
                            <v-file-input label="选择文件" v-model="upload_file" accept=".zip" outlined
                                required></v-file-input>
                        </v-col>
                    </v-row>
                </v-container>

                <br>
                <small>{{ status }}</small>
            </v-card-text>
            <v-card-actions>
                <v-spacer></v-spacer>
                <v-btn color="blue-darken-1" variant="text" @click="dialog = false">
                    关闭
                </v-btn>
                <v-btn color="blue-darken-1" variant="text" :loading="loading_" @click="newExtension()">
                    安装
                </v-btn>
            </v-card-actions>
        </v-card>
    </v-dialog>

    <v-snackbar :timeout="2000" elevation="24" :color="snack_success" v-model="snack_show">
        {{ snack_message }}
    </v-snackbar>

    <WaitingForRestart ref="wfr"></WaitingForRestart>
</template>


<script>

export default {
    name: 'ExtensionPage',
    components: {
        ExtensionCard,
        WaitingForRestart,
        ConsoleDisplayer,
        AstrBotConfig
    },
    data() {
        return {
            extension_data: {
                "data": [],
                "message": ""
            },
            extension_url: "",
            status: "",
            dialog: false,
            snack_message: "",
            snack_show: false,
            snack_success: "success",
            loading_: false,
            upload_file: null,
            pluginMarketData: [],
            loadingDialog: {
                show: false,
                title: "加载中...",
                statusCode: 0, // 0: loading, 1: success, 2: error,
                result: ""
            },

            announcement: "",
            isListView: true,
            pluginMarketHeaders: [
                { title: '名称', key: 'name', maxWidth: '150px' },
                { title: '描述', key: 'desc', maxWidth: '250px' },
                { title: '作者', key: 'author', maxWidth: '60px' },
                { title: '标签', key: 'tags', maxWidth: '60px' },
                { title: '操作', key: 'actions', sortable: false }
            ],
            marketSearch: "",

            commonStore: useCommonStore()
        }
    },
    computed: {
        filteredPluginMarketData() {
            if (!this.marketSearch) {
                return this.pluginMarketData;
            }
            const search = this.marketSearch.toLowerCase();
            return this.pluginMarketData.filter(plugin =>
                plugin.name.toLowerCase().includes(search)
            );
        },
        pinnedPlugins() {
            return this.pluginMarketData.filter(plugin => plugin?.pinned);
        }
    },
    mounted() {
        // 获取本地插件数据
        this.getExtensions();

        // 获取插件市场数据
        this.loading_ = true
        this.commonStore.getPluginCollections().then((data) => {
            this.pluginMarketData = data;
            this.checkAlreadyInstalled();
            this.checkUpdate();
            this.loading_ = false
        }).catch((err) => {
            console.error("获取插件市场数据失败:", err);
        });

        axios.get('https://api.soulter.top/astrbot-announcement-plugin-market').then((res) => {
            let data = res.data.data;
            this.announcement = data.text;
        });
    },
    methods: {
        jumpToPluginMarket() {
            window.open('https://soulter.github.io/AstrBot_Plugins_Collection/plugins.json', '_blank');
        },
        toast(message, success) {
            this.snack_message = message;
            this.snack_show = true;
            this.snack_success = success;
        },
        resetLoadingDialog() {
            this.loadingDialog = {
                show: false,
                title: "加载中...",
                statusCode: 0,
                result: ""
            }
        },
        onLoadingDialogResult(statusCode, result, timeToClose = 2000) {
            this.loadingDialog.statusCode = statusCode;
            this.loadingDialog.result = result;
            if (timeToClose === -1) {
                return
            }
            setTimeout(() => {
                this.resetLoadingDialog()
            }, timeToClose);
        },
        getExtensions() {
            axios.get('/api/plugin/get').then((res) => {
                this.extension_data = res.data;
                this.checkAlreadyInstalled();
                this.checkUpdate()
            });
        },

        checkUpdate() {
            // 创建在线插件的map
            const onlinePluginsMap = new Map();
            const onlinePluginsNameMap = new Map();

            // 将在线插件信息存储到map中
            this.pluginMarketData.forEach(plugin => {
                if (plugin.repo) {
                    onlinePluginsMap.set(plugin.repo.toLowerCase(), plugin);
                }
                onlinePluginsNameMap.set(plugin.name, plugin);
            });

            // 遍历本地插件列表
            this.extension_data.data.forEach(extension => {
                // 通过repo或name查找在线版本
                const repoKey = extension.repo?.toLowerCase();
                const onlinePlugin = repoKey ? onlinePluginsMap.get(repoKey) : null;
                const onlinePluginByName = onlinePluginsNameMap.get(extension.name);
                const matchedPlugin = onlinePlugin || onlinePluginByName;

                if (matchedPlugin) {
                    extension.online_version = matchedPlugin.version;
                    extension.has_update = extension.version !== matchedPlugin.version &&
                        matchedPlugin.version !== "未知";
                } else {
                    extension.has_update = false;
                }
            });
        },

        newExtension() {
            if (this.extension_url === "" && this.upload_file === null) {
                this.toast("请填写插件链接或上传插件文件", "error");
                return;
            }

            if (this.extension_url !== "" && this.upload_file !== null) {
                this.toast("请不要同时填写插件链接和上传插件文件", "error");
                return;
            }
            this.loading_ = true;
            this.loadingDialog.show = true;
            if (this.upload_file !== null) {
                this.toast("正在从文件安装插件", "primary");
                const formData = new FormData();
                formData.append('file', this.upload_file);
                axios.post('/api/plugin/install-upload', formData, {
                    headers: {
                        'Content-Type': 'multipart/form-data'
                    }
                }).then((res) => {
                    this.loading_ = false;
                    if (res.data.status === "error") {
                        this.onLoadingDialogResult(2, res.data.message, -1);
                        return;
                    }
                    this.extension_data = res.data;
                    this.upload_file = "";
                    this.onLoadingDialogResult(1, res.data.message);
                    this.dialog = false;
                    // this.$refs.wfr.check();
                }).catch((err) => {
                    this.loading_ = false;
                    this.onLoadingDialogResult(2, err, -1);
                });
                return;
            } else {
                this.toast("正在从链接 " + this.extension_url + " 安装插件...", "primary");
                axios.post('/api/plugin/install',
                    {
                        url: this.extension_url,
                        proxy: localStorage.getItem('selectedGitHubProxy') || ""
                    }).then((res) => {
                        this.loading_ = false;
                        this.toast(res.data.message, res.data.status === "ok" ? "success" : "error");
                        if (res.data.status === "error") {
                            this.onLoadingDialogResult(2, res.data.message, -1);
                            return;
                        }
                        this.extension_data = res.data;
                        this.extension_url = "";
                        this.onLoadingDialogResult(1, res.data.message);
                        this.dialog = false;
                        // this.$refs.wfr.check();
                    }).catch((err) => {
                        this.loading_ = false;
                        this.toast("安装插件失败: " + err, "error");
                        this.onLoadingDialogResult(2, err, -1);
                    });
            }
        },
        checkAlreadyInstalled() {
            // 创建已安装插件的仓库和名称集合 统一格式
            const installedRepos = new Set(this.extension_data.data.map(ext => ext.repo?.toLowerCase()));
            const installedNames = new Set(this.extension_data.data.map(ext => ext.name));

            // 遍历检查安装状态
            for (let i = 0; i < this.pluginMarketData.length; i++) {
                const plugin = this.pluginMarketData[i];
                plugin.installed = installedRepos.has(plugin.repo?.toLowerCase()) || installedNames.has(plugin.name);
            }

            // 将已安装的插件移动到最后面
            let installed = [];
            let notInstalled = [];
            for (let i = 0; i < this.pluginMarketData.length; i++) {
                if (this.pluginMarketData[i].installed) {
                    installed.push(this.pluginMarketData[i]);
                } else {
                    notInstalled.push(this.pluginMarketData[i]);
                }
            }
            this.pluginMarketData = notInstalled.concat(installed);
        }
    },
}

</script>