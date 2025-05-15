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

// 新增变量支持列表视图
const isListView = ref(false);
const pluginSearch = ref("");
const loading_ = ref(false);

const plugin_handler_info_headers = [
  { title: '行为类型', key: 'event_type_h' },
  { title: '描述', key: 'desc', maxWidth: '250px' },
  { title: '具体类型', key: 'type' },
  { title: '触发方式', key: 'cmd' },
];

// 插件表格的表头定义
const pluginHeaders = [
  { title: '名称', key: 'name', width: '200px' },
  { title: '描述', key: 'desc', maxWidth: '250px' },
  { title: '版本', key: 'version', width: '100px' },
  { title: '作者', key: 'author', width: '100px' },
  { title: '状态', key: 'status', width: '80px' },
  { title: '操作', key: 'actions', sortable: false, width: '220px' }
];

// 过滤要显示的插件
const filteredExtensions = computed(() => {
  if (!showReserved.value) {
    return extension_data?.data?.filter(ext => !ext.reserved) || [];
  }
  return extension_data.data || [];
});

// 通过搜索过滤插件
const filteredPlugins = computed(() => {
  if (!pluginSearch.value) {
    return filteredExtensions.value;
  }

  const search = pluginSearch.value.toLowerCase();
  return filteredExtensions.value.filter(plugin => {
    return plugin.name?.toLowerCase().includes(search) ||
      plugin.desc?.toLowerCase().includes(search) ||
      plugin.author?.toLowerCase().includes(search);
  });
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
  loading_.value = true;
  try {
    const res = await axios.get('/api/plugin/get');
    Object.assign(extension_data, res.data);
    checkUpdate();
  } catch (err) {
    toast(err, "error");
  } finally {
    loading_.value = false;
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
      <v-card variant="flat" class="rounded-xl">
        <v-card-item>
          <template v-slot:prepend>
            <div class="plugin-page-icon d-flex justify-center align-center rounded-lg mr-4">
              <v-icon size="36" color="primary">mdi-puzzle</v-icon>
            </div>
          </template>
          <v-card-title class="text-h4 font-weight-bold">
            已安装的插件
          </v-card-title>
          <v-card-subtitle class="text-subtitle-1 mt-1 text-medium-emphasis">
            管理已经安装的所有插件
          </v-card-subtitle>
        </v-card-item>

        <v-card-text class="pt-2">
          <v-row class="mb-4">
            <v-col cols="12" sm="6" md="6" class="d-flex align-center">
              <v-btn-group variant="outlined" density="comfortable" color="primary">
                <v-btn @click="isListView = false" :color="!isListView ? 'primary' : undefined"
                  :variant="!isListView ? 'flat' : 'outlined'">
                  <v-icon>mdi-view-grid</v-icon>
                </v-btn>
                <v-btn @click="isListView = true" :color="isListView ? 'primary' : undefined"
                  :variant="isListView ? 'flat' : 'outlined'">
                  <v-icon>mdi-view-list</v-icon>
                </v-btn>
              </v-btn-group>

              <v-btn class="ml-2" @click="toggleShowReserved" prepend-icon="mdi-eye-settings-outline"
                :color="showReserved ? 'primary' : undefined" :variant="showReserved ? 'flat' : 'outlined'">
                {{ showReserved ? '隐藏系统插件' : '显示系统插件' }}
              </v-btn>

              <v-btn class="ml-2" prepend-icon="mdi-tune-vertical" color="primary" variant="outlined"
                @click="getPlatformEnableConfig">
                平台命令配置
              </v-btn>
            </v-col>

            <v-col cols="12" sm="auto" md="6" class="ml-auto">
              <div class="search-container rounded-lg">

                <v-text-field v-model="pluginSearch" density="compact" label="Search" prepend-inner-icon="mdi-magnify"
                  variant="solo-filled" flat hide-details single-line></v-text-field>
              </div>



              <v-dialog max-width="500px" v-if="extension_data.message">
                <template v-slot:activator="{ props }">
                  <v-btn v-bind="props" icon size="small" color="error" class="ml-2" variant="tonal">
                    <v-icon>mdi-alert-circle</v-icon>
                    <v-badge dot color="error" floating></v-badge>
                  </v-btn>
                </template>
                <template v-slot:default="{ isActive }">
                  <v-card class="rounded-lg">
                    <v-card-title class="headline d-flex align-center">
                      <v-icon color="error" class="mr-2">mdi-alert-circle</v-icon>
                      错误信息
                    </v-card-title>
                    <v-card-text>
                      <p class="text-body-1">{{ extension_data.message }}</p>
                      <p class="text-caption mt-2">详情请检查控制台</p>
                    </v-card-text>
                    <v-card-actions>
                      <v-spacer></v-spacer>
                      <v-btn color="primary" @click="isActive.value = false">关闭</v-btn>
                    </v-card-actions>
                  </v-card>
                </template>
              </v-dialog>
            </v-col>
          </v-row>

          <v-fade-transition hide-on-leave>
            <!-- 表格视图 -->
            <div v-if="isListView">
              <v-card class="rounded-lg overflow-hidden elevation-1">
                <v-data-table :headers="pluginHeaders" :items="filteredPlugins" :loading="loading_" item-key="name"
                  hover>
                  <template v-slot:loader>
                    <v-row class="py-8 d-flex align-center justify-center">
                      <v-progress-circular indeterminate color="primary"></v-progress-circular>
                      <span class="ml-2">加载中...</span>
                    </v-row>
                  </template>

                  <template v-slot:item.name="{ item }">
                    <div class="d-flex align-center py-2">
                      <div>
                        <div class="text-subtitle-1 font-weight-medium">{{ item.name }}</div>
                        <div v-if="item.reserved" class="d-flex align-center mt-1">
                          <v-chip color="primary" size="x-small" class="font-weight-medium">系统</v-chip>
                        </div>
                      </div>
                    </div>
                  </template>

                  <template v-slot:item.desc="{ item }">
                    <div class="text-body-2 text-medium-emphasis">{{ item.desc }}</div>
                  </template>

                  <template v-slot:item.version="{ item }">
                    <div class="d-flex align-center">
                      <span class="text-body-2">{{ item.version }}</span>
                      <v-icon v-if="item.has_update" color="warning" size="small" class="ml-1">mdi-alert</v-icon>
                      <v-tooltip v-if="item.has_update" activator="parent">
                        <span>有新版本: {{ item.online_version }}</span>
                      </v-tooltip>
                    </div>
                  </template>

                  <template v-slot:item.author="{ item }">
                    <div class="text-body-2">{{ item.author }}</div>
                  </template>

                  <template v-slot:item.status="{ item }">
                    <v-chip :color="item.activated ? 'success' : 'error'" size="small" class="font-weight-medium"
                      :variant="item.activated ? 'flat' : 'outlined'">
                      {{ item.activated ? '启用' : '禁用' }}
                    </v-chip>
                  </template>

                  <template v-slot:item.actions="{ item }">
                    <div class="d-flex align-center">
                      <v-btn-group density="comfortable" variant="text" color="primary">
                        <v-btn v-if="!item.activated" icon size="small" color="success" @click="pluginOn(item)">
                          <v-icon>mdi-play</v-icon>
                          <v-tooltip activator="parent" location="top">点击启用</v-tooltip>
                        </v-btn>
                        <v-btn v-else icon size="small" color="error" @click="pluginOff(item)">
                          <v-icon>mdi-pause</v-icon>
                          <v-tooltip activator="parent" location="top">点击禁用</v-tooltip>
                        </v-btn>

                        <v-btn icon size="small" color="info" @click="reloadPlugin(item.name)">
                          <v-icon>mdi-refresh</v-icon>
                          <v-tooltip activator="parent" location="top">重载</v-tooltip>
                        </v-btn>

                        <v-btn icon size="small" @click="openExtensionConfig(item.name)">
                          <v-icon>mdi-cog</v-icon>
                          <v-tooltip activator="parent" location="top">配置</v-tooltip>
                        </v-btn>

                        <v-btn icon size="small" @click="showPluginInfo(item)">
                          <v-icon>mdi-information</v-icon>
                          <v-tooltip activator="parent" location="top">行为</v-tooltip>
                        </v-btn>

                        <v-btn v-if="item.repo" icon size="small" @click="viewReadme(item)">
                          <v-icon>mdi-book-open-page-variant</v-icon>
                          <v-tooltip activator="parent" location="top">文档</v-tooltip>
                        </v-btn>

                        <v-btn icon size="small" color="warning"
                          @click="updateExtension(item.name)" :v-show="item.has_update">
                          <v-icon>mdi-update</v-icon>
                          <v-tooltip activator="parent" location="top">更新</v-tooltip>
                        </v-btn>

                        <v-btn icon size="small" color="error"
                          @click="uninstallExtension(item.name)" :disabled="item.reserved">
                          <v-icon>mdi-delete</v-icon>
                          <v-tooltip activator="parent" location="top">卸载</v-tooltip>
                        </v-btn>
                      </v-btn-group>


                    </div>
                  </template>

                  <template v-slot:no-data>
                    <div class="text-center pa-8">
                      <v-icon size="64" color="info" class="mb-4">mdi-puzzle-outline</v-icon>
                      <div class="text-h5 mb-2">暂无插件</div>
                      <div class="text-body-1 mb-4">尝试安装插件或者显示系统插件</div>
                    </div>
                  </template>
                </v-data-table>
              </v-card>
            </div>

            <!-- 卡片视图 -->
            <div v-else>
              <v-row v-if="filteredPlugins.length === 0" class="text-center">
                <v-col cols="12" class="pa-8">
                  <v-icon size="64" color="info" class="mb-4">mdi-puzzle-outline</v-icon>
                  <div class="text-h5 mb-2">暂无插件</div>
                  <div class="text-body-1 mb-4">尝试安装插件或者显示系统插件</div>
                </v-col>
              </v-row>

              <v-row>
                <v-col cols="12" md="6" lg="4" v-for="extension in filteredPlugins" :key="extension.name" class="pb-4">
                  <ExtensionCard :extension="extension" class="h-120 rounded-lg"
                    @configure="openExtensionConfig(extension.name)" @uninstall="uninstallExtension(extension.name)"
                    @update="updateExtension(extension.name)" @reload="reloadPlugin(extension.name)"
                    @toggle-activation="extension.activated ? pluginOff(extension) : pluginOn(extension)"
                    @view-handlers="showPluginInfo(extension)" @view-readme="viewReadme(extension)">
                  </ExtensionCard>
                </v-col>
              </v-row>
            </div>
          </v-fade-transition>

          <v-row v-if="loading_">
            <v-col cols="12" class="d-flex justify-center">
              <v-progress-circular indeterminate color="primary" size="48"></v-progress-circular>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-col>
  </v-row>

  <!-- 插件平台配置对话框 -->
  <v-dialog v-model="platformEnableDialog" max-width="900" persistent>
    <v-card class="rounded-lg">
      <v-toolbar color="primary" density="comfortable" flat>
        <v-toolbar-title class="text-white">平台命令可用性配置</v-toolbar-title>
        <v-spacer></v-spacer>
        <v-btn icon @click="platformEnableDialog = false" variant="text" color="white">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-toolbar>

      <v-card-text class="pt-4">
        <p class="text-body-2 mb-4">设置每个插件在不同平台上的可用性，勾选表示启用</p>

        <v-overlay :model-value="loadingPlatformData" class="align-center justify-center" persistent>
          <v-progress-circular color="primary" indeterminate size="64"></v-progress-circular>
        </v-overlay>

        <div v-if="platformEnableData.platforms.length === 0" class="text-center pa-8">
          <v-icon icon="mdi-alert" color="warning" size="64" class="mb-4"></v-icon>
          <div class="text-h5 mb-2">未找到平台适配器</div>
          <div class="text-body-1 mb-4">请先在 <strong>平台管理</strong> 中添加并配置平台适配器，然后再设置插件的平台可用性</div>
          <v-btn color="primary" to="/platforms" variant="elevated">前往平台管理</v-btn>
        </div>

        <v-sheet v-else class="rounded-lg overflow-hidden">
          <v-table hover class="elevation-1">
            <thead>
              <tr>
                <th class="text-left">插件名称</th>
                <th v-for="platform in platformEnableData.platforms" :key="platform.name">
                  <div class="d-flex align-center">
                    {{ platform.display_name }}
                    <v-menu>
                      <template v-slot:activator="{ props }">
                        <v-btn icon density="compact" variant="text" size="small" v-bind="props" class="ms-1">
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
                  <v-checkbox v-model="platformEnableData.platform_enable[platform.name][plugin.name]" hide-details
                    density="compact"></v-checkbox>
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-sheet>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" text @click="platformEnableDialog = false">关闭</v-btn>
        <v-btn v-if="platformEnableData.platforms.length > 0" color="primary"
          @click="savePlatformEnableConfig">保存</v-btn>
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
        <v-progress-linear v-if="loadingDialog.statusCode === 0" indeterminate color="primary"
          class="mb-4"></v-progress-linear>

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

  <ReadmeDialog v-model:show="readmeDialog.show" :plugin-name="readmeDialog.pluginName"
    :repo-url="readmeDialog.repoUrl" />
</template>

<style scoped>
.plugin-handler-item {
  margin-bottom: 10px;
  padding: 5px;
  border-radius: 5px;
  background-color: #f5f5f5;
}
</style>
