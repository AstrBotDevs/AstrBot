<script setup>
import ExtensionCard from '@/components/shared/ExtensionCard.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import ReadmeDialog from '@/components/shared/ReadmeDialog.vue';
import axios from 'axios';
import { useCommonStore } from '@/stores/common';

// 将所有状态和方法迁移到 setup 语法中
import { ref, computed, onMounted, reactive } from 'vue';

const commonStore = useCommonStore();
const extension_data = reactive({
  data: [],
  message: ""
});
const showReserved = ref(false);
const snack_message = ref("");
const snack_show = ref(false);
const snack_success = ref("success");
const configDialog = ref(false);
const extension_config = reactive({
  metadata: {},
  config: {}
});
const pluginMarketData = ref([]);
const loadingDialog = reactive({
  show: false,
  title: "加载中...",
  statusCode: 0, // 0: loading, 1: success, 2: error,
  result: ""
});
const showPluginInfoDialog = ref(false);
const selectedPlugin = ref({});
const curr_namespace = ref("");
const wfr = ref(null);

const readmeDialog = reactive({
  show: false,
  pluginName: '',
  repoUrl: null
});
// 平台插件配置
const platformEnableDialog = ref(false);
const platformEnableData = reactive({
  platforms: [],
  plugins: [],
  platform_enable: {}
});
const loadingPlatformData = ref(false);

const plugin_handler_info_headers = [
  { title: '行为类型', key: 'event_type_h' },
  { title: '描述', key: 'desc', maxWidth: '250px' },
  { title: '具体类型', key: 'type' },
  { title: '触发方式', key: 'cmd' },
];

const filteredExtensions = computed(() => {
  if (showReserved.value) {
    return extension_data.data;
  }
  return extension_data?.data?.filter(ext => !ext.reserved);
});

// 方法
const toggleShowReserved = () => {
  showReserved.value = !showReserved.value;
};

const toast = (message, success) => {
  snack_message.value = message;
  snack_show.value = true;
  snack_success.value = success;
};

const resetLoadingDialog = () => {
  loadingDialog.show = false;
  loadingDialog.title = "加载中...";
  loadingDialog.statusCode = 0;
  loadingDialog.result = "";
};

const onLoadingDialogResult = (statusCode, result, timeToClose = 2000) => {
  loadingDialog.statusCode = statusCode;
  loadingDialog.result = result;
  if (timeToClose === -1) return;
  setTimeout(resetLoadingDialog, timeToClose);
};

const getExtensions = async () => {
  try {
    const res = await axios.get('/api/plugin/get');
    Object.assign(extension_data, res.data);
    checkUpdate();
  } catch (err) {
    toast(err, "error");
  }
};

const checkUpdate = () => {
  const onlinePluginsMap = new Map();
  const onlinePluginsNameMap = new Map();

  pluginMarketData.value.forEach(plugin => {
    if (plugin.repo) {
      onlinePluginsMap.set(plugin.repo.toLowerCase(), plugin);
    }
    onlinePluginsNameMap.set(plugin.name, plugin);
  });

  extension_data.data.forEach(extension => {
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
    extension.logo = matchedPlugin?.logo;
  });
};

const uninstallExtension = async (extension_name) => {
  toast("正在卸载" + extension_name, "primary");
  try {
    const res = await axios.post('/api/plugin/uninstall', { name: extension_name });
    if (res.data.status === "error") {
      toast(res.data.message, "error");
      return;
    }
    Object.assign(extension_data, res.data);
    toast(res.data.message, "success");
    getExtensions();
  } catch (err) {
    toast(err, "error");
  }
};

const updateExtension = async (extension_name) => {
  loadingDialog.show = true;
  try {
    const res = await axios.post('/api/plugin/update', {
      name: extension_name,
      proxy: localStorage.getItem('selectedGitHubProxy') || ""
    });
    
    if (res.data.status === "error") {
      onLoadingDialogResult(2, res.data.message, -1);
      return;
    }
    
    Object.assign(extension_data, res.data);
    onLoadingDialogResult(1, res.data.message);
  } catch (err) {
    toast(err, "error");
  }
};

const pluginOn = async (extension) => {
  try {
    const res = await axios.post('/api/plugin/on', { name: extension.name });
    if (res.data.status === "error") {
      toast(res.data.message, "error");
      return;
    }
    toast(res.data.message, "success");
    getExtensions();
  } catch (err) {
    toast(err, "error");
  }
};

const pluginOff = async (extension) => {
  try {
    const res = await axios.post('/api/plugin/off', { name: extension.name });
    if (res.data.status === "error") {
      toast(res.data.message, "error");
      return;
    }
    toast(res.data.message, "success");
    getExtensions();
  } catch (err) {
    toast(err, "error");
  }
};

const openExtensionConfig = async (extension_name) => {
  curr_namespace.value = extension_name;
  configDialog.value = true;
  try {
    const res = await axios.get('/api/config/get?plugin_name=' + extension_name);
    extension_config.metadata = res.data.data.metadata;
    extension_config.config = res.data.data.config;
    
  } catch (err) {
    toast(err, "error");
  }
};

const updateConfig = async () => {
  try {
    const res = await axios.post('/api/config/plugin/update?plugin_name=' + curr_namespace.value, extension_config.config);
    if (res.data.status === "ok") {
      toast(res.data.message, "success");
    } else {
      toast(res.data.message, "error");
    }
    configDialog.value = false;
    extension_config.metadata = {};
    extension_config.config = {};
    getExtensions();
  } catch (err) {
    toast(err, "error");
  }
};

const showPluginInfo = (plugin) => {
  selectedPlugin.value = plugin;
  showPluginInfoDialog.value = true;
};

const reloadPlugin = async (plugin_name) => {
  try {
    const res = await axios.post('/api/plugin/reload', { name: plugin_name });
    if (res.data.status === "error") {
      toast(res.data.message, "error");
      return;
    }
    toast("重载成功", "success");
    getExtensions();
  } catch (err) {
    toast(err, "error");
  }
};

const viewReadme = (plugin) => {
  readmeDialog.pluginName = plugin.name;
  readmeDialog.repoUrl = plugin.repo;
  readmeDialog.show = true;
};

// 获取插件平台可用性配置
const getPlatformEnableConfig = async () => {
  loadingPlatformData.value = true;
  try {
    const res = await axios.get('/api/plugin/platform_enable/get');
    if (res.data.status === "error") {
      toast(res.data.message, "error");
      return;
    }
    
    platformEnableData.platforms = res.data.data.platforms;
    platformEnableData.plugins = res.data.data.plugins;
    platformEnableData.platform_enable = res.data.data.platform_enable;
    
    // 如果没有平台，给出提示但仍显示对话框
    if (platformEnableData.platforms.length === 0) {
      toast("未添加任何平台适配器，请先在平台管理中添加平台", "warning");
    } else {
      // 确保每个平台都有一个配置对象
      platformEnableData.platforms.forEach(platform => {
        if (!platformEnableData.platform_enable[platform.name]) {
          platformEnableData.platform_enable[platform.name] = {};
        }
        
        // 确保每个插件在每个平台都有一个配置项
        platformEnableData.plugins.forEach(plugin => {
          if (platformEnableData.platform_enable[platform.name][plugin.name] === undefined) {
            platformEnableData.platform_enable[platform.name][plugin.name] = true; // 默认启用
          }
        });
      });
    }
    
    platformEnableDialog.value = true;
  } catch (err) {
    toast("获取平台插件配置失败: " + err, "error");
  } finally {
    loadingPlatformData.value = false;
  }
};

// 保存插件平台可用性配置
const savePlatformEnableConfig = async () => {
  loadingPlatformData.value = true;
  try {
    const res = await axios.post('/api/plugin/platform_enable/set', {
      platform_enable: platformEnableData.platform_enable
    });
    
    if (res.data.status === "error") {
      toast(res.data.message, "error");
      return;
    }
    
    toast(res.data.message, "success");
    platformEnableDialog.value = false;
  } catch (err) {
    toast("保存平台插件配置失败: " + err, "error");
  } finally {
    loadingPlatformData.value = false;
  }
};

// 全选指定平台的所有插件
const selectAllPluginsForPlatform = (platformName, isSelected, onlyReserved = null) => {
  // 确保平台存在于platform_enable中
  if (!platformEnableData.platform_enable[platformName]) {
    platformEnableData.platform_enable[platformName] = {};
  }
  
  // 为所有插件设置相同的状态
  platformEnableData.plugins.forEach(plugin => {
    // 如果onlyReserved为null，处理所有插件
    // 如果onlyReserved为true，只处理系统插件
    // 如果onlyReserved为false，只处理非系统插件
    if (onlyReserved === null || plugin.reserved === onlyReserved) {
      platformEnableData.platform_enable[platformName][plugin.name] = isSelected;
    }
  });
};

// 反选指定平台的所有插件
const toggleAllPluginsForPlatform = (platformName) => {
  // 确保平台存在于platform_enable中
  if (!platformEnableData.platform_enable[platformName]) {
    platformEnableData.platform_enable[platformName] = {};
  }
  
  // 对每个插件进行反选操作
  platformEnableData.plugins.forEach(plugin => {
    const currentState = platformEnableData.platform_enable[platformName][plugin.name];
    platformEnableData.platform_enable[platformName][plugin.name] = !currentState;
  });
};

// 生命周期
onMounted(async () => {
  await getExtensions();
  
  try {
    const data = await commonStore.getPluginCollections();
    pluginMarketData.value = data;
    checkUpdate();
  } catch (err) {
    console.error("获取插件市场数据失败:", err);
  }
});
</script>

<template>
  <v-row>
    <v-col cols="12" md="12">
      <div style="background-color: white; width: 100%; padding: 16px; border-radius: 10px;">
        <div style="display: flex; align-items: center;">
          <h3>🧩 已安装的插件</h3>
          <v-btn class="text-none ml-2" size="small" variant="flat" border @click="toggleShowReserved">
            {{ showReserved ? '隐藏系统保留插件' : '显示系统保留插件' }}
          </v-btn>
          <v-btn class="text-none ml-2" size="small" variant="flat" color="primary" border @click="getPlatformEnableConfig">
            平台命令配置
          </v-btn>
          <v-dialog max-width="500px" v-if="extension_data.message">
            <template v-slot:activator="{ props }">
              <v-btn v-bind="props" icon size="small" color="error" style="margin-left: auto;" variant="plain">
                <v-icon>mdi-alert-circle</v-icon>
              </v-btn>
            </template>
            <template v-slot:default="{ isActive }">
              <v-card>
                <v-card-title class="headline">错误信息</v-card-title>
                <v-card-text>
                  {{ extension_data.message }}<br>
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
    
    <v-col cols="10" md="6" lg="6" v-for="extension in filteredExtensions" :key="extension.name">
      <ExtensionCard :extension="extension" 
        @configure="openExtensionConfig(extension.name)"
        @uninstall="uninstallExtension(extension.name)"
        @update="updateExtension(extension.name)"
        @reload="reloadPlugin(extension.name)"
        @toggle-activation="extension.activated ? pluginOff(extension) : pluginOn(extension)"
        @view-handlers="showPluginInfo(extension)"
        @view-readme="viewReadme(extension)">
      </ExtensionCard>
    </v-col>
  </v-row>

  <!-- 插件平台配置对话框 -->
  <v-dialog v-model="platformEnableDialog" max-width="800" persistent>
    <v-card>
      <v-card-title>
        <span class="headline">平台命令可用性配置</span>
      </v-card-title>
      <v-card-subtitle>
        设置每个插件在不同平台上的可用性，勾选表示启用
      </v-card-subtitle>
      <v-card-text>
        <v-overlay
          :model-value="loadingPlatformData"
          class="align-center justify-center"
          persistent
        >
          <v-progress-circular
            color="primary"
            indeterminate
            size="64"
          ></v-progress-circular>
        </v-overlay>
        
        <div v-if="platformEnableData.platforms.length === 0" class="text-center pa-4">
          <v-icon icon="mdi-alert" color="warning" size="64" class="mb-4"></v-icon>
          <div class="text-h6 mb-2">未找到平台适配器</div>
          <div class="text-body-1 mb-4">请先在 <strong>平台管理</strong> 中添加并配置平台适配器，然后再设置插件的平台可用性</div>
          <v-btn color="primary" to="/platforms">前往平台管理</v-btn>
        </div>
        
        <v-table v-else>
          <thead>
            <tr>
              <th>插件名称</th>
              <th v-for="platform in platformEnableData.platforms" :key="platform.name">
                <div class="d-flex align-center">
                  {{ platform.display_name }}
                  <v-menu>
                    <template v-slot:activator="{ props }">
                      <v-btn
                        icon
                        density="compact"
                        variant="text"
                        size="small"
                        v-bind="props"
                        class="ms-1"
                      >
                        <v-icon>mdi-dots-vertical</v-icon>
                      </v-btn>
                    </template>
                    <v-list>
                      <v-list-item @click="selectAllPluginsForPlatform(platform.name, true)">
                        <v-list-item-title>全选</v-list-item-title>
                      </v-list-item>
                      <v-list-item @click="selectAllPluginsForPlatform(platform.name, true, false)">
                        <v-list-item-title>全选普通插件</v-list-item-title>
                      </v-list-item>
                      <v-list-item @click="selectAllPluginsForPlatform(platform.name, true, true)">
                        <v-list-item-title>全选系统插件</v-list-item-title>
                      </v-list-item>
                      <v-list-item @click="selectAllPluginsForPlatform(platform.name, false)">
                        <v-list-item-title>全不选</v-list-item-title>
                      </v-list-item>
                      <v-list-item @click="toggleAllPluginsForPlatform(platform.name)">
                        <v-list-item-title>反选</v-list-item-title>
                      </v-list-item>
                    </v-list>
                  </v-menu>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="plugin in platformEnableData.plugins" :key="plugin.name">
              <td>
                <div class="d-flex align-center">
                  {{ plugin.name }}
                  <v-chip v-if="plugin.reserved" color="primary" size="x-small" class="ml-2">系统</v-chip>
                </div>
                <div class="text-caption text-grey">{{ plugin.desc }}</div>
              </td>
              <td v-for="platform in platformEnableData.platforms" :key="platform.name">
                <v-checkbox
                  v-model="platformEnableData.platform_enable[platform.name][plugin.name]"
                  hide-details
                  density="compact"
                ></v-checkbox>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" text @click="platformEnableDialog = false">关闭</v-btn>
        <v-btn v-if="platformEnableData.platforms.length > 0" color="primary" @click="savePlatformEnableConfig">保存</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 配置对话框 -->
  <v-dialog v-model="configDialog" width="1000">
    <v-card>
      <v-card-title class="text-h5">插件配置</v-card-title>
      <v-card-text>
        <AstrBotConfig v-if="extension_config.metadata" :metadata="extension_config.metadata"
          :iterable="extension_config.config" :metadataKey="curr_namespace" />
        <p v-else>这个插件没有配置</p>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="updateConfig">保存并关闭</v-btn>
        <v-btn color="blue-darken-1" variant="text" @click="configDialog = false">关闭</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 加载对话框 -->
  <v-dialog v-model="loadingDialog.show" width="700" persistent>
    <v-card>
      <v-card-title class="text-h5">{{ loadingDialog.title }}</v-card-title>
      <v-card-text>
        <v-progress-linear v-if="loadingDialog.statusCode === 0" indeterminate color="primary" class="mb-4"></v-progress-linear>
        
        <div v-if="loadingDialog.statusCode !== 0" class="py-8 text-center">
          <v-icon class="mb-6" :color="loadingDialog.statusCode === 1 ? 'success' : 'error'" 
            :icon="loadingDialog.statusCode === 1 ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'" 
            size="128"></v-icon>
          <div class="text-h4 font-weight-bold">{{ loadingDialog.result }}</div>
        </div>
        
        <div style="margin-top: 32px;">
          <h3>日志</h3>
          <ConsoleDisplayer historyNum="10" style="height: 200px; margin-top: 16px;"></ConsoleDisplayer>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="resetLoadingDialog">关闭</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 插件信息对话框 -->
  <v-dialog v-model="showPluginInfoDialog" width="1200">
    <v-card>
      <v-card-title class="text-h5">{{ selectedPlugin.name }} 插件行为</v-card-title>
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
        <v-btn color="blue-darken-1" variant="text" @click="showPluginInfoDialog = false">关闭</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-snackbar :timeout="2000" elevation="24" :color="snack_success" v-model="snack_show">
    {{ snack_message }}
  </v-snackbar>

  <WaitingForRestart ref="wfr"></WaitingForRestart>
  
  <ReadmeDialog
    v-model:show="readmeDialog.show"
    :plugin-name="readmeDialog.pluginName"
    :repo-url="readmeDialog.repoUrl"
  />
</template>

<style scoped>
.plugin-handler-item {
  margin-bottom: 10px;
  padding: 5px;
  border-radius: 5px;
  background-color: #f5f5f5;
}
</style>
