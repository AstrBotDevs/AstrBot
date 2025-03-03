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
    <v-col cols="12" md="12">
      <div style="background-color: white; width: 100%; padding: 16px; border-radius: 10px;">
        <div style="display: flex; align-items: center;">
          <h3>🧩 已安装的插件</h3>

          <v-dialog max-width="500px">
            <template v-slot:activator="{ props }">
              <v-btn v-bind="props" v-if="extension_data.message" icon size="small" color="error"
                style="margin-left: auto;" variant="plain">
                <v-icon>mdi-alert-circle</v-icon>
              </v-btn>
            </template>

            <template v-slot:default="{ isActive }">
              <v-card>
                <v-card-title class="headline">错误信息</v-card-title>
                <v-card-text>{{ extension_data.message }}
                  <br>
                  <small>详情请检查控制台</small>
                </v-card-text>

                <v-card-actions>
                  <v-spacer></v-spacer>
                  <v-btn color="primary" text @click="isActive.value = false">关闭</v-btn>
                </v-card-actions>
              </v-card>
            </template>

          </v-dialog>
        </div>
      </div>
    </v-col>
    <v-col cols="12" md="6" lg="3" v-for="extension in extension_data.data">
      <ExtensionCard :key="extension.name" :title="extension.name" :link="extension.repo" :logo="extension?.logo"
        :has_update="extension.has_update" style="margin-bottom: 4px;" :activated="extension.activated">
        <div style="min-height: 140px; max-height: 140px; overflow: auto;">
          <div>
            <span style="font-weight: bold  ;">By @{{ extension.author }}</span>
            <span> | {{ extension.handlers.length }} 个行为</span>
          </div>
          <span> 当前: <v-chip size="small" color="primary">{{ extension.version }}</v-chip>
            <span v-if="extension.online_version">
              | 最新: <v-chip size="small" color="primary">{{ extension.online_version }}</v-chip>
            </span>
            <span v-if="extension.has_update" style="font-weight: bold;">有更新
            </span>
          </span>
          <p style="margin-top: 8px;">{{ extension.desc }}</p>
          <a style="font-size: 12px; cursor: pointer; text-decoration: underline; color: #555;"
            @click="reloadPlugin(extension.name)">重载插件</a>
        </div>
        <div class="d-flex align-center gap-2 " style="overflow-x: auto;">
          <v-btn v-if="!extension.reserved" class="text-none mr-2" size="small" text="Read" variant="flat" border
            @click="openExtensionConfig(extension.name)">配置</v-btn>
          <v-btn v-if="!extension.reserved" class="text-none mr-2" size="small" text="Read" variant="flat" border
            @click="updateExtension(extension.name)">更新</v-btn>
          <v-btn v-if="!extension.reserved" class="text-none mr-2" size="small" text="Read" variant="flat" border
            @click="uninstallExtension(extension.name)">卸载</v-btn>
          <!-- <span v-else>保留插件</span> -->
          <v-btn class="text-none mr-2" size="small" text="Read" variant="flat" border v-if="extension.activated"
            @click="pluginOff(extension)">禁用</v-btn>
          <v-btn class="text-none mr-2" size="small" text="Read" variant="flat" border v-else
            @click="pluginOn(extension)">启用</v-btn>

          <v-btn class="text-none mr-2" size="small" text="Read" variant="flat" border
            @click="showPluginInfo(extension)">行为</v-btn>
        </div>
      </ExtensionCard>
    </v-col>

  </v-row>

  <v-dialog v-model="configDialog" width="1000">
    <template v-slot:activator="{ props }">
    </template>
    <v-card>
      <v-card-title>
        <span class="text-h5">插件配置</span>
      </v-card-title>
      <v-card-text>
        <v-container>
          <AstrBotConfig v-if="extension_config.metadata" :metadata="extension_config.metadata"
            :iterable="extension_config.config" :metadataKey=curr_namespace></AstrBotConfig>
          <p v-else>这个插件没有配置</p>
        </v-container>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="updateConfig">
          保存并关闭
        </v-btn>
        <v-btn color="blue-darken-1" variant="text" @click="configDialog = false">
          关闭
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog v-model="loadingDialog.show" width="700" persistent>
    <v-card>
      <v-card-title>
        <span class="text-h5">{{ loadingDialog.title }}</span>
      </v-card-title>
      <v-card-text>
        <v-container>
          <v-row>
            <v-col cols="12">
              <v-progress-linear indeterminate color="primary"
                v-if="loadingDialog.statusCode === 0"></v-progress-linear>
            </v-col>
          </v-row>
          <div class="py-12 text-center" v-if="loadingDialog.statusCode !== 0">
            <v-icon class="mb-6" color="success" icon="mdi-check-circle-outline" size="128"
              v-if="loadingDialog.statusCode === 1"></v-icon>
            <v-icon class="mb-6" color="error" icon="mdi-alert-circle-outline" size="128"
              v-if="loadingDialog.statusCode === 2"></v-icon>
            <div class="text-h4 font-weight-bold">{{ loadingDialog.result }}</div>
          </div>
          <div style="margin-top: 32px;">
            <h3>日志</h3>
            <ConsoleDisplayer historyNum="10" style="height: 200px; margin-top: 16px;"></ConsoleDisplayer>
          </div>

        </v-container>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="resetLoadingDialog()">
          关闭
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog v-model="showPluginInfoDialog" width="1200">
    <template v-slot:activator="{ props }">
    </template>
    <v-card>
      <v-card-title>
        <span class="text-h5">{{ selectedPlugin.name }} 插件行为</span>
      </v-card-title>
      <v-card-text>
        <v-data-table style="font-size: 17px;" :headers="plugin_handler_info_headers" :items="selectedPlugin.handlers"
          item-key="name">
          <template v-slot:header.id="{ column }">
            <p style="font-weight: bold;">{{ column.title }}</p>
          </template>
          <template v-slot:item.event_type="{ item }">
            {{ item.event_type }}
          </template>
          <template v-slot:item.desc="{ item }">
            {{ item.desc }}
          </template>
          <template v-slot:item.type="{ item }">
            <v-chip color="success">
              {{ item.type }}
            </v-chip>
          </template>
          <template v-slot:item.cmd="{ item }">
            <span style="font-weight: bold;">{{ item.cmd }}</span>
          </template>
        </v-data-table>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="showPluginInfoDialog = false">
          关闭
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
      status: "",
      dialog: false,
      snack_message: "",
      snack_show: false,
      snack_success: "success",
      configDialog: false,
      extension_config: {
        "metadata": {},
        "config": {}
      },
      pluginMarketData: [],
      loadingDialog: {
        show: false,
        title: "加载中...",
        statusCode: 0, // 0: loading, 1: success, 2: error,
        result: ""
      },

      showPluginInfoDialog: false,
      selectedPlugin: {},
      plugin_handler_info_headers: [
        { title: '行为类型', key: 'event_type_h' },
        { title: '描述', key: 'desc', maxWidth: '250px' },
        { title: '具体类型', key: 'type' },
        { title: '触发方式', key: 'cmd' },
      ],

      commonStore: useCommonStore()
    }
  },
  mounted() {
    this.getExtensions();
    // 获取插件市场数据
    this.commonStore.getPluginCollections().then((data) => {
      this.pluginMarketData = data;
      this.checkUpdate();
    }).catch((err) => {
      console.error("获取插件市场数据失败:", err);
    });
  },
  methods: {
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

    uninstallExtension(extension_name) {
      this.toast("正在卸载" + extension_name, "primary");
      axios.post('/api/plugin/uninstall',
        {
          name: extension_name
        }).then((res) => {
          if (res.data.status === "error") {
            this.toast(res.data.message, "error");
            return;
          }
          this.extension_data = res.data;
          this.toast(res.data.message, "success");
          this.dialog = false;
          this.getExtensions();
        }).catch((err) => {
          this.toast(err, "error");
        });
    },
    updateExtension(extension_name) {
      this.loadingDialog.show = true;
      axios.post('/api/plugin/update',
        {
          name: extension_name,
          proxy: localStorage.getItem('selectedGitHubProxy') || ""
        }).then((res) => {
          if (res.data.status === "error") {
            this.onLoadingDialogResult(2, res.data.message, -1);
            return;
          }
          this.extension_data = res.data;
          console.log(this.extension_data);
          this.onLoadingDialogResult(1, res.data.message);
          this.dialog = false;
          this.$refs.wfr.check();
        }).catch((err) => {
          this.toast(err, "error");
        });
    },
    pluginOn(extension) {
      axios.post('/api/plugin/on',
        {
          name: extension.name
        }).then((res) => {
          if (res.data.status === "error") {
            this.toast(res.data.message, "error");
            return;
          }
          this.toast(res.data.message, "success");
          this.getExtensions();
        }).catch((err) => {
          this.toast(err, "error");
        });
    },
    pluginOff(extension) {
      axios.post('/api/plugin/off',
        {
          name: extension.name
        }).then((res) => {
          if (res.data.status === "error") {
            this.toast(res.data.message, "error");
            return;
          }
          this.toast(res.data.message, "success");
          this.getExtensions();
        }).catch((err) => {
          this.toast(err, "error");
        });
    },
    openExtensionConfig(extension_name) {
      this.curr_namespace = extension_name;
      this.configDialog = true;
      axios.get('/api/config/get?plugin_name=' + extension_name).then((res) => {
        this.extension_config = res.data.data;
        console.log(this.extension_config);
      }).catch((err) => {
        this.toast(err, "error");
      });
    },
    updateConfig() {
      axios.post('/api/config/plugin/update?plugin_name=' + this.curr_namespace, this.extension_config.config).then((res) => {
        if (res.data.status === "ok") {
          this.toast(res.data.message, "success");
          this.$refs.wfr.check();
        } else {
          this.toast(res.data.message, "error");
        }
      }).catch((err) => {
        this.toast(err, "error");
      });
    },
    showPluginInfo(plugin) {
      this.selectedPlugin = plugin;
      this.showPluginInfoDialog = true;
    },
    reloadPlugin(plugin_name) {
      axios.post('/api/plugin/reload',
        {
          name: plugin_name
        }).then((res) => {
          if (res.data.status === "error") {
            this.onLoadingDialogResult(2, res.data.message, -1);
            return;
          }
          this.toast("重载成功", "success");
          this.getExtensions();
        }).catch((err) => {
          this.toast(err, "error");
        });
    }
  },
}

</script>