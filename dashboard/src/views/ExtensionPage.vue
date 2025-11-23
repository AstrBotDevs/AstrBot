<script setup>
import ExtensionCard from '@/components/shared/ExtensionCard.vue';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import ReadmeDialog from '@/components/shared/ReadmeDialog.vue';
import ProxySelector from '@/components/shared/ProxySelector.vue';
import UninstallConfirmDialog from '@/components/shared/UninstallConfirmDialog.vue';
import axios from 'axios';
import { pinyin } from 'pinyin-pro';
import { useCommonStore } from '@/stores/common';
import { useI18n, useModuleI18n } from '@/i18n/composables';

import { ref, computed, onMounted, reactive, inject, watch } from 'vue';


const commonStore = useCommonStore();
const { t } = useI18n();
const { tm } = useModuleI18n('features/extension');
const fileInput = ref(null);
const activeTab = ref('installed');
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
  title: "",
  statusCode: 0, // 0: loading, 1: success, 2: error,
  result: ""
});
const showPluginInfoDialog = ref(false);
const selectedPlugin = ref({});
const curr_namespace = ref("");

const readmeDialog = reactive({
  show: false,
  pluginName: '',
  repoUrl: null
});

// 新增变量支持列表视图
const isListView = ref(false);
const pluginSearch = ref("");
const loading_ = ref(false);

// 分页相关
const currentPage = ref(1);
const itemsPerPage = ref(6); // 每页显示6个卡片 (2行 x 3列，避免滚动)

// 危险插件确认对话框
const dangerConfirmDialog = ref(false);
const selectedDangerPlugin = ref(null);

// 卸载插件确认对话框（列表模式用）
const showUninstallDialog = ref(false);
const pluginToUninstall = ref(null);

// 插件市场相关
const extension_url = ref("");
const dialog = ref(false);
const upload_file = ref(null);
const uploadTab = ref('file');
const showPluginFullName = ref(false);
const marketSearch = ref("");
const debouncedMarketSearch = ref("");
const filterKeys = ['name', 'desc', 'author'];
const refreshingMarket = ref(false);
const sortBy = ref('default'); // default, stars, author, updated
const sortOrder = ref('desc'); // desc (降序) or asc (升序)

// 插件市场拼音搜索
const normalizeStr = (s) => (s ?? '').toString().toLowerCase().trim();
const toPinyinText = (s) => pinyin(s ?? '', { toneType: 'none' }).toLowerCase().replace(/\s+/g, '');
const toInitials = (s) => pinyin(s ?? '', { pattern: 'first', toneType: 'none' }).toLowerCase().replace(/\s+/g, '');
const marketCustomFilter = (value, query, item) => {
  const q = normalizeStr(query);
  if (!q) return true;

  const candidates = new Set();
  if (value != null) candidates.add(String(value));
  if (item?.name) candidates.add(String(item.name));
  if (item?.trimmedName) candidates.add(String(item.trimmedName));
  if (item?.desc) candidates.add(String(item.desc));
  if (item?.author) candidates.add(String(item.author));

  for (const v of candidates) {
    const nv = normalizeStr(v);
    if (nv.includes(q)) return true;
    const pv = toPinyinText(v);
    if (pv.includes(q)) return true;
    const iv = toInitials(v);
    if (iv.includes(q)) return true;
  }
  return false;
};

const plugin_handler_info_headers = computed(() => [
  { title: tm('table.headers.eventType'), key: 'event_type_h' },
  { title: tm('table.headers.description'), key: 'desc', maxWidth: '250px' },
  { title: tm('table.headers.specificType'), key: 'type' },
  { title: tm('table.headers.trigger'), key: 'cmd' },
]);

// 插件表格的表头定义
const pluginHeaders = computed(() => [
  { title: tm('table.headers.name'), key: 'name', width: '200px' },
  { title: tm('table.headers.description'), key: 'desc', maxWidth: '250px' },
  { title: tm('table.headers.version'), key: 'version', width: '100px' },
  { title: tm('table.headers.author'), key: 'author', width: '100px' },
  { title: tm('table.headers.status'), key: 'activated', width: '100px' },
  { title: tm('table.headers.actions'), key: 'actions', sortable: false, width: '220px' }
]);


// 插件市场表头
const pluginMarketHeaders = computed(() => [
  { title: tm('table.headers.name'), key: 'name', maxWidth: '200px' },
  { title: tm('table.headers.description'), key: 'desc', maxWidth: '250px' },
  { title: tm('table.headers.author'), key: 'author', maxWidth: '90px' },
  { title: tm('table.headers.stars'), key: 'stars', maxWidth: '80px' },
  { title: tm('table.headers.lastUpdate'), key: 'updated_at', maxWidth: '100px' },
  { title: tm('table.headers.tags'), key: 'tags', maxWidth: '100px' },
  { title: tm('table.headers.actions'), key: 'actions', sortable: false }
]);


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

const pinnedPlugins = computed(() => {
  return pluginMarketData.value.filter(plugin => plugin?.pinned);
});

// 过滤后的插件市场数据（带搜索）
const filteredMarketPlugins = computed(() => {
  if (!debouncedMarketSearch.value) {
    return pluginMarketData.value;
  }

  const search = debouncedMarketSearch.value.toLowerCase();
  return pluginMarketData.value.filter(plugin => {
    // 使用自定义过滤器
    return marketCustomFilter(plugin.name, search, plugin) ||
      marketCustomFilter(plugin.desc, search, plugin) ||
      marketCustomFilter(plugin.author, search, plugin);
  });
});

// 所有插件列表，推荐插件排在前面
const sortedPlugins = computed(() => {
  let plugins = [...filteredMarketPlugins.value];

  // 根据排序选项排序
  if (sortBy.value === 'stars') {
    // 按 star 数排序
    plugins.sort((a, b) => {
      const starsA = a.stars ?? 0;
      const starsB = b.stars ?? 0;
      return sortOrder.value === 'desc' ? starsB - starsA : starsA - starsB;
    });
  } else if (sortBy.value === 'author') {
    // 按作者名字典序排序
    plugins.sort((a, b) => {
      const authorA = (a.author ?? '').toLowerCase();
      const authorB = (b.author ?? '').toLowerCase();
      const result = authorA.localeCompare(authorB);
      return sortOrder.value === 'desc' ? -result : result;
    });
  } else if (sortBy.value === 'updated') {
    // 按更新时间排序
    plugins.sort((a, b) => {
      const dateA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
      const dateB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
      return sortOrder.value === 'desc' ? dateB - dateA : dateA - dateB;
    });
  } else {
    // default: 推荐插件排在前面
    const pinned = plugins.filter(plugin => plugin?.pinned);
    const notPinned = plugins.filter(plugin => !plugin?.pinned);
    return [...pinned, ...notPinned];
  }

  return plugins;
});

// 分页计算属性
const displayItemsPerPage = 9; // 固定每页显示6个卡片（2行）

const totalPages = computed(() => {
  return Math.ceil(sortedPlugins.value.length / displayItemsPerPage);
});

const paginatedPlugins = computed(() => {
  const start = (currentPage.value - 1) * displayItemsPerPage;
  const end = start + displayItemsPerPage;
  return sortedPlugins.value.slice(start, end);
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
  loadingDialog.title = tm('dialogs.loading.title');
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
        matchedPlugin.version !== tm('status.unknown');
    } else {
      extension.has_update = false;
    }
  });
};

const uninstallExtension = async (extension_name, optionsOrSkipConfirm = false) => {
  let deleteConfig = false;
  let deleteData = false;
  let skipConfirm = false;

  // 处理参数：可能是布尔值（旧的 skipConfirm）或对象（新的选项）
  if (typeof optionsOrSkipConfirm === 'boolean') {
    skipConfirm = optionsOrSkipConfirm;
  } else if (typeof optionsOrSkipConfirm === 'object' && optionsOrSkipConfirm !== null) {
    deleteConfig = optionsOrSkipConfirm.deleteConfig || false;
    deleteData = optionsOrSkipConfirm.deleteData || false;
    skipConfirm = true; // 如果传递了选项对象，说明已经确认过了
  }

  // 如果没有跳过确认且没有传递选项对象，显示自定义卸载对话框
  if (!skipConfirm) {
    pluginToUninstall.value = extension_name;
    showUninstallDialog.value = true;
    return; // 等待对话框回调
  }

  // 执行卸载
  toast(tm('messages.uninstalling') + " " + extension_name, "primary");
  try {
    const res = await axios.post('/api/plugin/uninstall', {
      name: extension_name,
      delete_config: deleteConfig,
      delete_data: deleteData,
    });
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

// 处理卸载确认对话框的确认事件
const handleUninstallConfirm = (options) => {
  if (pluginToUninstall.value) {
    uninstallExtension(pluginToUninstall.value, options);
    pluginToUninstall.value = null;
  }
};

const updateExtension = async (extension_name) => {
  loadingDialog.title = tm('status.loading');
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
    setTimeout(async () => {
      toast(tm('messages.refreshing'), "info", 2000);
      try {
        await getExtensions();
        toast(tm('messages.refreshSuccess'), "success");

      } catch (error) {
        const errorMsg = error.response?.data?.message || error.message || String(error);
        toast(`${tm('messages.refreshFailed')}: ${errorMsg}`, "error");
      }
    }, 1000);
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
    toast(tm('messages.reloadSuccess'), "success");
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



const open = (link) => {
  if (link) {
    window.open(link, '_blank');
  }
};

// 为表格视图创建一个处理安装插件的函数
const handleInstallPlugin = async (plugin) => {
  if (plugin.tags && plugin.tags.includes('danger')) {
    selectedDangerPlugin.value = plugin;
    dangerConfirmDialog.value = true;
  } else {
    extension_url.value = plugin.repo;
    dialog.value = true;
    uploadTab.value = 'url';
  }
};

// 确认安装危险插件
const confirmDangerInstall = () => {
  if (selectedDangerPlugin.value) {
    extension_url.value = selectedDangerPlugin.value.repo;
    dialog.value = true;
    uploadTab.value = 'url';
  }
  dangerConfirmDialog.value = false;
  selectedDangerPlugin.value = null;
};

// 取消安装危险插件
const cancelDangerInstall = () => {
  dangerConfirmDialog.value = false;
  selectedDangerPlugin.value = null;
};

// 插件市场显示完整插件名称
const trimExtensionName = () => {
  pluginMarketData.value.forEach(plugin => {
    if (plugin.name) {
      let name = plugin.name.trim().toLowerCase();
      if (name.startsWith("astrbot_plugin_")) {
        plugin.trimmedName = name.substring(15);
      } else if (name.startsWith("astrbot_") || name.startsWith("astrbot-")) {
        plugin.trimmedName = name.substring(8);
      } else plugin.trimmedName = plugin.name;
    }
  });
};

const checkAlreadyInstalled = () => {
  const installedRepos = new Set(extension_data.data.map(ext => ext.repo?.toLowerCase()));
  const installedNames = new Set(extension_data.data.map(ext => ext.name));

  for (let i = 0; i < pluginMarketData.value.length; i++) {
    const plugin = pluginMarketData.value[i];
    plugin.installed = installedRepos.has(plugin.repo?.toLowerCase()) || installedNames.has(plugin.name);
  }

  let installed = [];
  let notInstalled = [];
  for (let i = 0; i < pluginMarketData.value.length; i++) {
    if (pluginMarketData.value[i].installed) {
      installed.push(pluginMarketData.value[i]);
    } else {
      notInstalled.push(pluginMarketData.value[i]);
    }
  }
  pluginMarketData.value = notInstalled.concat(installed);
};

const newExtension = async () => {
  if (extension_url.value === "" && upload_file.value === null) {
    toast(tm('messages.fillUrlOrFile'), "error");
    return;
  }

  if (extension_url.value !== "" && upload_file.value !== null) {
    toast(tm('messages.dontFillBoth'), "error");
    return;
  }
  loading_.value = true;
  loadingDialog.title = tm('status.loading');
  loadingDialog.show = true;
  if (upload_file.value !== null) {
    toast(tm('messages.installing'), "primary");
    const formData = new FormData();
    formData.append('file', upload_file.value);
    axios.post('/api/plugin/install-upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    }).then(async (res) => {
      loading_.value = false;
      if (res.data.status === "error") {
        onLoadingDialogResult(2, res.data.message, -1);
        return;
      }
      upload_file.value = null;
      onLoadingDialogResult(1, res.data.message);
      dialog.value = false;
      await getExtensions();

      viewReadme({
        name: res.data.data.name,
        repo: res.data.data.repo || null
      });
    }).catch((err) => {
      loading_.value = false;
      onLoadingDialogResult(2, err, -1);
    });
  } else {
    toast(tm('messages.installingFromUrl') + " " + extension_url.value, "primary");
    axios.post('/api/plugin/install',
      {
        url: extension_url.value,
        proxy: localStorage.getItem('selectedGitHubProxy') || ""
      }).then(async (res) => {
        loading_.value = false;
        toast(res.data.message, res.data.status === "ok" ? "success" : "error");
        if (res.data.status === "error") {
          onLoadingDialogResult(2, res.data.message, -1);
          return;
        }
        extension_url.value = "";
        onLoadingDialogResult(1, res.data.message);
        dialog.value = false;
        await getExtensions();

        viewReadme({
          name: res.data.data.name,
          repo: res.data.data.repo || null
        });
      }).catch((err) => {
        loading_.value = false;
        toast(tm('messages.installFailed') + " " + err, "error");
        onLoadingDialogResult(2, err, -1);
      });
  }
};

// 刷新插件市场数据
const refreshPluginMarket = async () => {
  refreshingMarket.value = true;
  try {
    // 强制刷新插件市场数据
    const data = await commonStore.getPluginCollections(true);
    pluginMarketData.value = data;
    trimExtensionName();
    checkAlreadyInstalled();
    checkUpdate();
    currentPage.value = 1; // 重置到第一页

    toast(tm('messages.refreshSuccess'), "success");
  } catch (err) {
    toast(tm('messages.refreshFailed') + " " + err, "error");
  } finally {
    refreshingMarket.value = false;
  }
};

// 生命周期
onMounted(async () => {
  await getExtensions();

  // 检查是否有 open_config 参数
  let urlParams;
  if (window.location.hash) {
    // For hash mode (#/path?param=value)
    const hashQuery = window.location.hash.split('?')[1] || '';
    urlParams = new URLSearchParams(hashQuery);
  } else {
    // For history mode (/path?param=value)
    urlParams = new URLSearchParams(window.location.search);
  }
  console.log("URL Parameters:", urlParams.toString());
  const plugin_name = urlParams.get('open_config');
  if (plugin_name) {
    console.log(`Opening config for plugin: ${plugin_name}`);
    openExtensionConfig(plugin_name);
  }

  try {
    const data = await commonStore.getPluginCollections();
    pluginMarketData.value = data;
    trimExtensionName();
    checkAlreadyInstalled();
    checkUpdate();
  } catch (err) {
    toast(tm('messages.getMarketDataFailed') + " " + err, "error");
  }
});

// 搜索防抖处理
let searchDebounceTimer = null;
watch(marketSearch, (newVal) => {
  if (searchDebounceTimer) {
    clearTimeout(searchDebounceTimer);
  }

  searchDebounceTimer = setTimeout(() => {
    debouncedMarketSearch.value = newVal;
    // 搜索时重置到第一页
    currentPage.value = 1;
  }, 300); // 300ms 防抖延迟
});


</script>

<template>
  <v-row>
    <v-col cols="12" md="12">
      <v-card variant="flat" style="background-color: transparent">
        <!-- 标签页 -->
        <v-card-text style="padding: 0px 12px;">
          <!-- 标签栏和搜索栏 - 响应式布局 -->
          <div class="mb-4 d-flex flex-wrap">
            <!-- 标签栏 -->
            <v-tabs v-model="activeTab" color="primary">
              <v-tab value="installed">
                <v-icon class="mr-2">mdi-puzzle</v-icon>
                {{ tm('tabs.installed') }}
              </v-tab>
              <v-tab value="market">
                <v-icon class="mr-2">mdi-store</v-icon>
                {{ tm('tabs.market') }}
              </v-tab>
            </v-tabs>

            <!-- 搜索栏 - 在移动端时独占一行 -->
            <div style="flex-grow: 1; min-width: 250px; max-width: 400px; margin-left: auto; margin-top: 8px;">
              <v-text-field v-if="activeTab == 'market'" v-model="marketSearch" density="compact"
                :label="tm('search.marketPlaceholder')" prepend-inner-icon="mdi-magnify" variant="solo-filled" flat
                hide-details single-line>
              </v-text-field>
              <v-text-field v-else v-model="pluginSearch" density="compact" :label="tm('search.placeholder')"
                prepend-inner-icon="mdi-magnify" variant="solo-filled" flat hide-details single-line>
              </v-text-field>
            </div>

          </div>


          <!-- 已安装插件标签页内容 -->
          <v-tab-item v-show="activeTab === 'installed'">
            <v-row class="mb-4">
              <v-col cols="12" class="d-flex align-center flex-wrap ga-2">
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

                <v-btn class="ml-2" variant="tonal" @click="toggleShowReserved">
                  <v-icon>{{ showReserved ? 'mdi-eye-off' : 'mdi-eye' }}</v-icon>
                  {{ showReserved ? tm('buttons.hideSystemPlugins') : tm('buttons.showSystemPlugins') }}
                </v-btn>

                <v-btn class="ml-2" color="primary" variant="tonal" @click="dialog = true">
                  <v-icon>mdi-plus</v-icon>
                  {{ tm('buttons.install') }}
                </v-btn>

                <v-col cols="12" sm="auto" class="ml-auto">
                  <v-dialog max-width="500px" v-if="extension_data.message">
                    <template v-slot:activator="{ props }">
                      <v-btn v-bind="props" icon size="small" color="error" class="ml-2" variant="tonal">
                        <v-icon>mdi-alert-circle</v-icon>
                      </v-btn>
                    </template>
                    <template v-slot:default="{ isActive }">
                      <v-card class="rounded-lg">
                        <v-card-title class="headline d-flex align-center">
                          <v-icon color="error" class="mr-2">mdi-alert-circle</v-icon>
                          {{ tm('dialogs.error.title') }}
                        </v-card-title>
                        <v-card-text>
                          <p class="text-body-1">{{ extension_data.message }}</p>
                          <p class="text-caption mt-2">{{ tm('dialogs.error.checkConsole') }}</p>
                        </v-card-text>
                        <v-card-actions>
                          <v-spacer></v-spacer>
                          <v-btn color="primary" @click="isActive.value = false">{{ tm('buttons.close') }}</v-btn>
                        </v-card-actions>
                      </v-card>
                    </template>
                  </v-dialog>
                </v-col>
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
                        <span class="ml-2">{{ tm('status.loading') }}</span>
                      </v-row>
                    </template>

                    <template v-slot:item.name="{ item }">
                      <div class="d-flex align-center py-2">
                        <div>
                          <div class="text-subtitle-1 font-weight-medium">{{ item.name }}</div>
                          <div v-if="item.reserved" class="d-flex align-center mt-1">
                            <v-chip color="primary" size="x-small" class="font-weight-medium">{{ tm('status.system')
                              }}</v-chip>
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
                          <span>{{ tm('messages.hasUpdate') }} {{ item.online_version }}</span>
                        </v-tooltip>
                      </div>
                    </template>

                    <template v-slot:item.author="{ item }">
                      <div class="text-body-2">{{ item.author }}</div>
                    </template>

                    <template v-slot:item.activated="{ item }">
                      <v-chip :color="item.activated ? 'success' : 'error'" size="small" class="font-weight-medium"
                        :variant="item.activated ? 'flat' : 'outlined'">
                        {{ item.activated ? tm('status.enabled') : tm('status.disabled') }}
                      </v-chip>
                    </template>

                    <template v-slot:item.actions="{ item }">
                      <div class="d-flex align-center">
                        <v-btn-group density="comfortable" variant="text" color="primary">
                          <v-btn v-if="!item.activated" icon size="small" color="success" @click="pluginOn(item)">
                            <v-icon>mdi-play</v-icon>
                            <v-tooltip activator="parent" location="top">{{ tm('tooltips.enable') }}</v-tooltip>
                          </v-btn>
                          <v-btn v-else icon size="small" color="error" @click="pluginOff(item)">
                            <v-icon>mdi-pause</v-icon>
                            <v-tooltip activator="parent" location="top">{{ tm('tooltips.disable') }}</v-tooltip>
                          </v-btn>

                          <v-btn icon size="small" color="info" @click="reloadPlugin(item.name)">
                            <v-icon>mdi-refresh</v-icon>
                            <v-tooltip activator="parent" location="top">{{ tm('tooltips.reload') }}</v-tooltip>
                          </v-btn>

                          <v-btn icon size="small" @click="openExtensionConfig(item.name)">
                            <v-icon>mdi-cog</v-icon>
                            <v-tooltip activator="parent" location="top">{{ tm('tooltips.configure') }}</v-tooltip>
                          </v-btn>

                          <v-btn icon size="small" @click="showPluginInfo(item)">
                            <v-icon>mdi-information</v-icon>
                            <v-tooltip activator="parent" location="top">{{ tm('tooltips.viewInfo') }}</v-tooltip>
                          </v-btn>

                          <v-btn v-if="item.repo" icon size="small" @click="viewReadme(item)">
                            <v-icon>mdi-book-open-page-variant</v-icon>
                            <v-tooltip activator="parent" location="top">{{ tm('tooltips.viewDocs') }}</v-tooltip>
                          </v-btn>

                          <v-btn icon size="small" color="warning" @click="updateExtension(item.name)"
                            :v-show="item.has_update">
                            <v-icon>mdi-update</v-icon>
                            <v-tooltip activator="parent" location="top">{{ tm('tooltips.update') }}</v-tooltip>
                          </v-btn>

                          <v-btn icon size="small" color="error" @click="uninstallExtension(item.name)"
                            :disabled="item.reserved">
                            <v-icon>mdi-delete</v-icon>
                            <v-tooltip activator="parent" location="top">{{ tm('tooltips.uninstall') }}</v-tooltip>
                          </v-btn>
                        </v-btn-group>


                      </div>
                    </template>

                    <template v-slot:no-data>
                      <div class="text-center pa-8">
                        <v-icon size="64" color="info" class="mb-4">mdi-puzzle-outline</v-icon>
                        <div class="text-h5 mb-2">{{ tm('empty.noPlugins') }}</div>
                        <div class="text-body-1 mb-4">{{ tm('empty.noPluginsDesc') }}</div>
                      </div>
                    </template>
                  </v-data-table>
                </v-card>
              </div>

              <!-- 卡片视图 -->
              <div v-else>
                <v-row v-if="filteredPlugins.length === 0" class="text-center">
                  <v-col cols="12" class="pa-2">
                    <v-icon size="64" color="info" class="mb-4">mdi-puzzle-outline</v-icon>
                    <div class="text-h5 mb-2">{{ tm('empty.noPlugins') }}</div>
                    <div class="text-body-1 mb-4">{{ tm('empty.noPluginsDesc') }}</div>
                  </v-col>
                </v-row>

                <v-row>
                  <v-col cols="12" md="6" lg="4" v-for="extension in filteredPlugins" :key="extension.name"
                    class="pb-2">
                    <ExtensionCard :extension="extension" class="rounded-lg"
                      style="background-color: rgb(var(--v-theme-mcpCardBg));"
                      @configure="openExtensionConfig(extension.name)"
                      @uninstall="(ext, options) => uninstallExtension(ext.name, options)"
                      @update="updateExtension(extension.name)" @reload="reloadPlugin(extension.name)"
                      @toggle-activation="extension.activated ? pluginOff(extension) : pluginOn(extension)"
                      @view-handlers="showPluginInfo(extension)" @view-readme="viewReadme(extension)">
                    </ExtensionCard>
                  </v-col>
                </v-row>
              </div>
            </v-fade-transition>
          </v-tab-item>

          <!-- 插件市场标签页内容 -->
          <v-tab-item v-show="activeTab === 'market'">

            <!-- <small style="color: var(--v-theme-secondaryText);">每个插件都是作者无偿提供的的劳动成果。如果您喜欢某个插件，请 Star！</small> -->

            <v-btn icon="mdi-plus" size="x-large" style="position: fixed; right: 52px; bottom: 52px; z-index: 10000"
              @click="dialog = true" color="darkprimary">
            </v-btn>

            <div class="mt-4">
              <div class="d-flex align-center mb-2" style="justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                <div class="d-flex align-center" style="gap: 6px;">
                  <h2>{{ tm('market.allPlugins') }}({{ filteredMarketPlugins.length }})</h2>
                  <v-btn icon variant="text" @click="refreshPluginMarket" :loading="refreshingMarket">
                    <v-icon>mdi-refresh</v-icon>
                  </v-btn>
                </div>

                <div class="d-flex align-center" style="gap: 8px; flex-wrap: wrap;">
                  <v-pagination v-model="currentPage" :length="totalPages" :total-visible="5" size="small"
                    density="comfortable"></v-pagination>

                  <!-- 排序选择器 -->
                  <v-select v-model="sortBy" :items="[
                    { title: tm('sort.default'), value: 'default' },
                    { title: tm('sort.stars'), value: 'stars' },
                    { title: tm('sort.author'), value: 'author' },
                    { title: tm('sort.updated'), value: 'updated' }
                  ]" density="compact" variant="outlined" hide-details style="max-width: 150px;">
                    <template v-slot:prepend-inner>
                      <v-icon size="small">mdi-sort</v-icon>
                    </template>
                  </v-select>

                  <!-- 排序方向切换按钮 -->
                  <v-btn icon v-if="sortBy !== 'default'" @click="sortOrder = sortOrder === 'desc' ? 'asc' : 'desc'"
                    variant="text" density="compact">
                    <v-icon>{{ sortOrder === 'desc' ? 'mdi-sort-descending' : 'mdi-sort-ascending'
                    }}</v-icon>
                    <v-tooltip activator="parent" location="top">
                      {{ sortOrder === 'desc' ? tm('sort.descending') : tm('sort.ascending') }}
                    </v-tooltip>
                  </v-btn>
                  <!-- <v-switch v-model="showPluginFullName" :label="tm('market.showFullName')" hide-details
                    density="compact" style="margin-left: 12px" /> -->
                </div>
              </div>

              <v-row style="min-height: 26rem;">
                <v-col v-for="plugin in paginatedPlugins" :key="plugin.name" cols="12" md="6" lg="4">
                  <v-card class="rounded-lg d-flex flex-column" elevation="0"
                    style=" height: 12rem; position: relative;">

                    <!-- 推荐标记 -->
                    <v-chip v-if="plugin?.pinned" color="warning" size="x-small" label
                      style="position: absolute; right: 8px; top: 8px; z-index: 10; height: 20px; font-weight: bold;">
                      🥳 推荐
                    </v-chip>

                    <v-card-text
                      style="padding: 12px; padding-bottom: 8px; display: flex; gap: 12px; width: 100%; flex: 1; overflow: hidden;">
                      <div v-if="plugin?.logo" style="flex-shrink: 0;">
                        <img :src="plugin.logo" :alt="plugin.name"
                          style="height: 75px; width: 75px; border-radius: 8px; object-fit: cover;" />
                      </div>

                      <div style="flex: 1; overflow: hidden; display: flex; flex-direction: column;">
                        <!-- Display Name -->
                        <div class="font-weight-bold"
                          style="margin-bottom: 4px; line-height: 1.3; font-size: 1.2rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                          <span style="overflow: hidden; text-overflow: ellipsis;">
                            {{ plugin.display_name?.length ? plugin.display_name :
                              (showPluginFullName ? plugin.name : plugin.trimmedName) }}
                          </span>
                        </div>

                        <!-- Author with link -->
                        <div class="d-flex align-center" style="gap: 4px; margin-bottom: 6px;">
                          <v-icon icon="mdi-account" size="x-small"
                            style="color: rgba(var(--v-theme-on-surface), 0.5);"></v-icon>
                          <a v-if="plugin?.social_link" :href="plugin.social_link" target="_blank"
                            class="text-subtitle-2 font-weight-medium"
                            style="text-decoration: none; color: rgb(var(--v-theme-primary)); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            {{ plugin.author }}
                          </a>
                          <span v-else class="text-subtitle-2 font-weight-medium"
                            style="color: rgb(var(--v-theme-primary)); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            {{ plugin.author }}
                          </span>
                          <div class="d-flex align-center text-subtitle-2 ml-2"
                            style="color: rgba(var(--v-theme-on-surface), 0.7);">
                            <v-icon icon="mdi-source-branch" size="x-small" style="margin-right: 2px;"></v-icon>
                            <span>{{ plugin.version }}</span>
                          </div>
                        </div>

                        <!-- Description -->
                        <div class="text-caption"
                          style="overflow: scroll; color: rgba(var(--v-theme-on-surface), 0.6); line-height: 1.3; margin-bottom: 6px; flex: 1;">
                          {{ plugin.desc }}
                        </div>

                        <!-- Stats: Stars & Updated & Version -->
                        <div class="d-flex align-center" style="gap: 8px; margin-top: auto;">
                          <div v-if="plugin.stars !== undefined" class="d-flex align-center text-subtitle-2"
                            style="color: rgba(var(--v-theme-on-surface), 0.7);">
                            <v-icon icon="mdi-star" size="x-small" style="margin-right: 2px;"></v-icon>
                            <span>{{ plugin.stars }}</span>
                          </div>
                          <div v-if="plugin.updated_at" class="d-flex align-center text-subtitle-2"
                            style="color: rgba(var(--v-theme-on-surface), 0.7);">
                            <v-icon icon="mdi-clock-outline" size="x-small" style="margin-right: 2px;"></v-icon>
                            <span>{{ new Date(plugin.updated_at).toLocaleString() }}</span>
                          </div>
                        </div>
                      </div>
                    </v-card-text>

                    <!-- Actions -->
                    <v-card-actions style="gap: 6px; padding: 8px 12px; padding-top: 0;">
                      <v-chip v-for="tag in plugin.tags?.slice(0, 2)" :key="tag"
                        :color="tag === 'danger' ? 'error' : 'primary'" label size="x-small" style="height: 20px;">
                        {{ tag === 'danger' ? tm('tags.danger') : tag }}
                      </v-chip>
                      <v-menu v-if="plugin.tags && plugin.tags.length > 2" open-on-hover offset-y>
                        <template v-slot:activator="{ props: menuProps }">
                          <v-chip v-bind="menuProps" color="grey" label size="x-small"
                            style="height: 20px; cursor: pointer;">
                            +{{ plugin.tags.length - 2 }}
                          </v-chip>
                        </template>
                        <v-list density="compact">
                          <v-list-item v-for="tag in plugin.tags.slice(2)" :key="tag">
                            <v-chip :color="tag === 'danger' ? 'error' : 'primary'" label size="small">
                              {{ tag === 'danger' ? tm('tags.danger') : tag }}
                            </v-chip>
                          </v-list-item>
                        </v-list>
                      </v-menu>
                      <v-spacer></v-spacer>
                      <v-btn v-if="plugin?.repo" color="secondary" size="x-small" variant="tonal" :href="plugin.repo"
                        target="_blank" style="height: 24px;">
                        <v-icon icon="mdi-github" start size="x-small"></v-icon>
                        仓库
                      </v-btn>
                      <v-btn v-if="!plugin?.installed" color="primary" size="x-small"
                        @click="handleInstallPlugin(plugin)" variant="flat" style="height: 24px;">
                        {{ tm('buttons.install') }}
                      </v-btn>
                      <v-chip v-else color="success" size="x-small" label style="height: 20px;">
                        ✓ {{ tm('status.installed') }}
                      </v-chip>
                    </v-card-actions>
                  </v-card>
                </v-col>
              </v-row>

              <!-- 底部分页控件 -->
              <div class="d-flex justify-center mt-4" v-if="totalPages > 1">
                <v-pagination v-model="currentPage" :length="totalPages" :total-visible="7" size="small"></v-pagination>
              </div>
            </div>
          </v-tab-item>

          <v-row v-if="loading_">
            <v-col cols="12" class="d-flex justify-center">
              <v-progress-circular indeterminate color="primary" size="48"></v-progress-circular>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-col>

    <v-col v-if="activeTab === 'market'" cols="12" md="12">
      <small><a href="https://astrbot.app/dev/plugin.html">{{ tm('market.devDocs') }}</a></small> |
      <small> <a href="https://github.com/AstrBotDevs/AstrBot_Plugins_Collection">{{ tm('market.submitRepo')
      }}</a></small>
    </v-col>
  </v-row>

  <!-- 配置对话框 -->
  <v-dialog v-model="configDialog" width="1000">
    <v-card>
      <v-card-title class="text-h5">{{ tm('dialogs.config.title') }}</v-card-title>
      <v-card-text>
        <AstrBotConfig v-if="extension_config.metadata" :metadata="extension_config.metadata"
          :iterable="extension_config.config" :metadataKey="curr_namespace" />
        <p v-else>{{ tm('dialogs.config.noConfig') }}</p>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="updateConfig">{{ tm('buttons.saveAndClose') }}</v-btn>
        <v-btn color="blue-darken-1" variant="text" @click="configDialog = false">{{ tm('buttons.close') }}</v-btn>
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
          <h3>{{ tm('dialogs.loading.logs') }}</h3>
          <ConsoleDisplayer historyNum="10" style="height: 200px; margin-top: 16px; margin-bottom: 24px;">
          </ConsoleDisplayer>
        </div>
      </v-card-text>

      <v-divider></v-divider>

      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="resetLoadingDialog">{{ tm('buttons.close') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 插件信息对话框 -->
  <v-dialog v-model="showPluginInfoDialog" width="1200">
    <v-card>
      <v-card-title class="text-h5">{{ selectedPlugin.name }} {{ tm('buttons.viewInfo') }}</v-card-title>
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
        <v-btn color="blue-darken-1" variant="text" @click="showPluginInfoDialog = false">{{ tm('buttons.close')
          }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-snackbar :timeout="2000" elevation="24" :color="snack_success" v-model="snack_show">
    {{ snack_message }}
  </v-snackbar>

  <ReadmeDialog v-model:show="readmeDialog.show" :plugin-name="readmeDialog.pluginName"
    :repo-url="readmeDialog.repoUrl" />

  <!-- 卸载插件确认对话框（列表模式用） -->
  <UninstallConfirmDialog v-model="showUninstallDialog" @confirm="handleUninstallConfirm" />

  <!-- 危险插件确认对话框 -->
  <v-dialog v-model="dangerConfirmDialog" width="500" persistent>
    <v-card>
      <v-card-title class="text-h5 d-flex align-center">
        <v-icon color="warning" class="mr-2">mdi-alert-circle</v-icon>
        {{ tm('dialogs.danger_warning.title') }}
      </v-card-title>
      <v-card-text>
        <div>{{ tm('dialogs.danger_warning.message') }}</div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" @click="cancelDangerInstall">
          {{ tm('dialogs.danger_warning.cancel') }}
        </v-btn>
        <v-btn color="warning" @click="confirmDangerInstall">
          {{ tm('dialogs.danger_warning.confirm') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 上传插件对话框 -->
  <v-dialog v-model="dialog" width="500">
    <v-card>
      <v-card-title class="text-h5">{{ tm('dialogs.install.title') }}</v-card-title>
      <v-card-text>
        <v-tabs v-model="uploadTab">
          <v-tab value="file">{{ tm('dialogs.install.fromFile') }}</v-tab>
          <v-tab value="url">{{ tm('dialogs.install.fromUrl') }}</v-tab>
        </v-tabs>

        <v-window v-model="uploadTab" class="mt-4">
          <v-window-item value="file">
            <div class="d-flex flex-column align-center justify-center pa-4">
              <v-file-input ref="fileInput" v-model="upload_file" :label="tm('upload.selectFile')" accept=".zip"
                hide-details hide-input class="d-none"></v-file-input>

              <v-btn color="primary" size="large" prepend-icon="mdi-upload" @click="$refs.fileInput.click()">
                {{ tm('buttons.selectFile') }}
              </v-btn>

              <div class="text-body-2 text-medium-emphasis mt-2">
                {{ tm('messages.supportedFormats') }}
              </div>

              <div v-if="upload_file" class="mt-4 text-center">
                <v-chip color="primary" size="large" closable @click:close="upload_file = null">
                  {{ upload_file.name }}
                  <template v-slot:append>
                    <span class="text-caption ml-2">({{ (upload_file.size / 1024).toFixed(1) }}KB)</span>
                  </template>
                </v-chip>
              </div>
            </div>
          </v-window-item>

          <v-window-item value="url">
            <div class="pa-4">
              <v-text-field v-model="extension_url" :label="tm('upload.enterUrl')" variant="outlined"
                prepend-inner-icon="mdi-link" hide-details
                placeholder="https://github.com/username/repo"></v-text-field>
              <div class="mt-4">
                <ProxySelector></ProxySelector>
              </div>
            </div>
          </v-window-item>
        </v-window>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="dialog = false">{{ tm('buttons.cancel') }}</v-btn>
        <v-btn color="primary" variant="text" @click="newExtension">{{ tm('buttons.install') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.plugin-handler-item {
  margin-bottom: 10px;
  padding: 5px;
  border-radius: 5px;
  background-color: #f5f5f5;
}
</style>
