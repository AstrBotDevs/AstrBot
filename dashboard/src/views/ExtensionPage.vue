<script setup>
import AstrBotConfig from "@/components/shared/AstrBotConfig.vue";
import ConsoleDisplayer from "@/components/shared/ConsoleDisplayer.vue";
import ReadmeDialog from "@/components/shared/ReadmeDialog.vue";
import ProxySelector from "@/components/shared/ProxySelector.vue";
import UninstallConfirmDialog from "@/components/shared/UninstallConfirmDialog.vue";
import McpServersSection from "@/components/extension/McpServersSection.vue";
import SkillsSection from "@/components/extension/SkillsSection.vue";
import ComponentPanel from "@/components/extension/componentPanel/index.vue";
import InstalledPluginsTab from "./extension/InstalledPluginsTab.vue";
import MarketPluginsTab from "./extension/MarketPluginsTab.vue";
import PluginDetailPage from "./extension/PluginDetailPage.vue";
import { useExtensionPage } from "./extension/useExtensionPage";
import { computed } from "vue";
import defaultPluginIcon from "@/assets/images/plugin_icon.png";
import { usePluginI18n } from "@/utils/pluginI18n";

const pageState = useExtensionPage();
const { pluginName, pluginDesc } = usePluginI18n();

const {
  commonStore,
  t,
  tm,
  router,
  route,
  getSelectedGitHubProxy,
  conflictDialog,
  checkAndPromptConflicts,
  handleConflictConfirm,
  fileInput,
  activeTab,
  validTabs,
  isValidTab,
  getLocationHash,
  extractTabFromHash,
  syncTabFromHash,
  extension_data,
  snack_message,
  snack_show,
  snack_success,
  configDialog,
  extension_config,
  pluginMarketData,
  loadingDialog,
  curr_namespace,
  updatingAll,
  readmeDialog,
  forceUpdateDialog,
  updateConfirmDialog,
  updateAllConfirmDialog,
  changelogDialog,
  pluginSearch,
  loading_,
  currentPage,
  dangerConfirmDialog,
  selectedDangerPlugin,
  selectedMarketInstallPlugin,
  installCompat,
  versionCompatibilityDialog,
  showUninstallDialog,
  uninstallTarget,
  showSourceDialog,
  showSourceManagerDialog,
  sourceName,
  sourceUrl,
  customSources,
  selectedSource,
  showRemoveSourceDialog,
  sourceToRemove,
  editingSource,
  originalSourceUrl,
  extension_url,
  dialog,
  upload_file,
  uploadTab,
  showPluginFullName,
  marketSearch,
  debouncedMarketSearch,
  refreshingMarket,
  sortBy,
  sortOrder,
  randomPluginNames,
  normalizeStr,
  toPinyinText,
  toInitials,
  filteredExtensions,
  filteredPlugins,
  filteredMarketPlugins,
  sortedPlugins,
  RANDOM_PLUGINS_COUNT,
  randomPlugins,
  shufflePlugins,
  refreshRandomPlugins,
  displayItemsPerPage,
  totalPages,
  paginatedPlugins,
  updatableExtensions,
  toast,
  resetLoadingDialog,
  onLoadingDialogResult,
  failedPluginsDict,
  getExtensions,
  handleReloadAllFailed,
  checkUpdate,
  uninstallExtension,
  handleUninstallConfirm,
  updateExtension,
  closeUpdateConfirmDialog,
  confirmUpdatePlugin,
  showUpdateAllConfirm,
  confirmUpdateAll,
  cancelUpdateAll,
  confirmForceUpdate,
  updateAllExtensions,
  pluginOn,
  pluginOff,
  openExtensionConfig,
  updateConfig,
  showPluginInfo,
  reloadPlugin,
  viewReadme,
  viewChangelog,
  openInstallDialog,
  closeInstallDialog,
  handleInstallPlugin,
  confirmDangerInstall,
  cancelDangerInstall,
  loadCustomSources,
  saveCustomSources,
  addCustomSource,
  openSourceManagerDialog,
  selectPluginSource,
  sourceSelectItems,
  editCustomSource,
  removeCustomSource,
  confirmRemoveSource,
  saveCustomSource,
  trimExtensionName,
  checkAlreadyInstalled,
  showVersionCompatibilityWarning,
  continueInstallIgnoringVersionWarning,
  cancelInstallOnVersionWarning,
  newExtension,
  normalizePlatformList,
  getPlatformDisplayList,
  resolveSelectedInstallPlugin,
  selectedInstallPlugin,
  selectedInstallDownloadUrl,
  selectedInstallSourceUrl,
  installUsesGithubSource,
  selectedUpdateExtension,
  selectedUpdateMarketPlugin,
  selectedUpdateDownloadUrl,
  selectedUpdateSourceUrl,
  updateUsesGithubSource,
  checkInstallCompatibility,
  refreshPluginMarket,
  handleLocaleChange,
  searchDebounceTimer,
} = pageState;

const selectedPluginId = computed(() => {
  const pluginId = route.params.pluginId;
  return Array.isArray(pluginId) ? pluginId[0] : pluginId || "";
});

// 从 localStorage 恢复显示系统插件的状态，默认为 false（隐藏）
const getInitialShowReserved = () => {
  if (typeof window !== "undefined" && window.localStorage) {
    const saved = localStorage.getItem("showReservedPlugins");
    return saved === "true";
  }
  return false;
};
const showReserved = ref(getInitialShowReserved());
const snack_message = ref("");
const snack_show = ref(false);
const snack_success = ref("success");
const configDialog = ref(false);
const extension_config = reactive({
  metadata: {},
  config: {},
});
const pluginMarketData = ref([]);
const loadingDialog = reactive({
  show: false,
  title: "",
  statusCode: 0, // 0: loading, 1: success, 2: error,
  result: "",
});
const showPluginInfoDialog = ref(false);
const selectedPlugin = ref({});
const curr_namespace = ref("");
const updatingAll = ref(false);

const readmeDialog = reactive({
  show: false,
  pluginName: "",
  repoUrl: null,
});

// 强制更新确认对话框
const forceUpdateDialog = reactive({
  show: false,
  extensionName: "",
});

// 更新全部插件确认对话框
const updateAllConfirmDialog = reactive({
  show: false,
});

// 插件更新日志对话框（复用 ReadmeDialog）
const changelogDialog = reactive({
  show: false,
  pluginName: "",
  repoUrl: null,
});

// 扩展页面对话框
const extensionPageDialog = reactive({
  show: false,
  html: "",
  title: "",
});

// 新增变量支持列表视图
// 从 localStorage 恢复显示模式，默认为 false（卡片视图）
const getInitialListViewMode = () => {
  if (typeof window !== "undefined" && window.localStorage) {
    return localStorage.getItem("pluginListViewMode") === "true";
  }
  return false;
};
const isListView = ref(getInitialListViewMode());
const pluginSearch = ref("");
const loading_ = ref(false);

// 分页相关
const currentPage = ref(1);

// 危险插件确认对话框
const dangerConfirmDialog = ref(false);
const selectedDangerPlugin = ref(null);

// 卸载插件确认对话框（列表模式用）
const showUninstallDialog = ref(false);
const pluginToUninstall = ref(null);

// 自定义插件源相关
const showSourceDialog = ref(false);
const sourceName = ref("");
const sourceUrl = ref("");
const customSources = ref([]);
const selectedSource = ref(null);
const showRemoveSourceDialog = ref(false);
const sourceToRemove = ref(null);
const editingSource = ref(false);
const originalSourceUrl = ref("");

// 插件市场相关
const extension_url = ref("");
const dialog = ref(false);
const upload_file = ref(null);
const uploadTab = ref("file");
const showPluginFullName = ref(false);
const marketSearch = ref("");
const debouncedMarketSearch = ref("");
const refreshingMarket = ref(false);
const sortBy = ref("default"); // default, stars, author, updated
const sortOrder = ref("desc"); // desc (降序) or asc (升序)

// 插件市场拼音搜索
const normalizeStr = (s) => (s ?? "").toString().toLowerCase().trim();
const toPinyinText = (s) =>
  pinyin(s ?? "", { toneType: "none" })
    .toLowerCase()
    .replace(/\s+/g, "");
const toInitials = (s) =>
  pinyin(s ?? "", { pattern: "first", toneType: "none" })
    .toLowerCase()
    .replace(/\s+/g, "");
const marketCustomFilter = (value, query, item) => {
  const q = normalizeStr(query);
  if (!q) return true;

  const candidates = new Set();
  if (value != null) candidates.add(String(value));
  if (item?.name) candidates.add(String(item.name));
  if (item?.trimmedName) candidates.add(String(item.trimmedName));
  if (item?.display_name) candidates.add(String(item.display_name));
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
  { title: tm("table.headers.eventType"), key: "event_type_h" },
  { title: tm("table.headers.description"), key: "desc", maxWidth: "250px" },
  { title: tm("table.headers.specificType"), key: "type" },
  { title: tm("table.headers.trigger"), key: "cmd" },
]);

// 插件表格的表头定义
const pluginHeaders = computed(() => [
  { title: tm("table.headers.name"), key: "name", width: "200px" },
  { title: tm("table.headers.description"), key: "desc", maxWidth: "250px" },
  { title: tm("table.headers.version"), key: "version", width: "100px" },
  { title: tm("table.headers.author"), key: "author", width: "100px" },
  { title: tm("table.headers.status"), key: "activated", width: "100px" },
  {
    title: tm("table.headers.actions"),
    key: "actions",
    sortable: false,
    width: "220px",
  },
]);

// 过滤要显示的插件
const filteredExtensions = computed(() => {
  const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
  if (!showReserved.value) {
    return data.filter((ext) => !ext.reserved);
  }
  return data;
});

// 通过搜索过滤插件
const filteredPlugins = computed(() => {
  if (!pluginSearch.value) {
    return filteredExtensions.value;
  }

  const search = pluginSearch.value.toLowerCase();
  return filteredExtensions.value.filter((plugin) => {
    return (
      plugin.name?.toLowerCase().includes(search) ||
      plugin.desc?.toLowerCase().includes(search) ||
      plugin.author?.toLowerCase().includes(search)
    );
  });
});

// 过滤后的插件市场数据（带搜索）
const filteredMarketPlugins = computed(() => {
  if (!debouncedMarketSearch.value) {
    return pluginMarketData.value;
  }

  const search = debouncedMarketSearch.value.toLowerCase();
  return pluginMarketData.value.filter((plugin) => {
    // 使用自定义过滤器
    return (
      marketCustomFilter(plugin.name, search, plugin) ||
      marketCustomFilter(plugin.desc, search, plugin) ||
      marketCustomFilter(plugin.author, search, plugin)
    );
  });
});

// 所有插件列表，推荐插件排在前面
const sortedPlugins = computed(() => {
  let plugins = [...filteredMarketPlugins.value];

  // 根据排序选项排序
  if (sortBy.value === "stars") {
    // 按 star 数排序
    plugins.sort((a, b) => {
      const starsA = a.stars ?? 0;
      const starsB = b.stars ?? 0;
      return sortOrder.value === "desc" ? starsB - starsA : starsA - starsB;
    });
  } else if (sortBy.value === "author") {
    // 按作者名字典序排序
    plugins.sort((a, b) => {
      const authorA = (a.author ?? "").toLowerCase();
      const authorB = (b.author ?? "").toLowerCase();
      const result = authorA.localeCompare(authorB);
      return sortOrder.value === "desc" ? -result : result;
    });
  } else if (sortBy.value === "updated") {
    // 按更新时间排序
    plugins.sort((a, b) => {
      const dateA = a.updated_at ? new Date(a.updated_at).getTime() : 0;
      const dateB = b.updated_at ? new Date(b.updated_at).getTime() : 0;
      return sortOrder.value === "desc" ? dateB - dateA : dateA - dateB;
    });
  } else {
    // default: 推荐插件排在前面
    const pinned = plugins.filter((plugin) => plugin?.pinned);
    const notPinned = plugins.filter((plugin) => !plugin?.pinned);
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

const updatableExtensions = computed(() => {
  const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
  return data.filter((ext) => ext.has_update);
});

// 方法
const toggleShowReserved = () => {
  showReserved.value = !showReserved.value;
  // 保存到 localStorage
  if (typeof window !== "undefined" && window.localStorage) {
    localStorage.setItem("showReservedPlugins", showReserved.value.toString());
  }
};

const toast = (message, success) => {
  snack_message.value = message;
  snack_show.value = true;
  snack_success.value = success;
};

const resetLoadingDialog = () => {
  loadingDialog.show = false;
  loadingDialog.title = tm("dialogs.loading.title");
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
    const res = await axios.get("/api/plugin/get");
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

  pluginMarketData.value.forEach((plugin) => {
    if (plugin.repo) {
      onlinePluginsMap.set(plugin.repo.toLowerCase(), plugin);
    }
    onlinePluginsNameMap.set(plugin.name, plugin);
  });

  const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
  data.forEach((extension) => {
    const repoKey = extension.repo?.toLowerCase();
    const onlinePlugin = repoKey ? onlinePluginsMap.get(repoKey) : null;
    const onlinePluginByName = onlinePluginsNameMap.get(extension.name);
    const matchedPlugin = onlinePlugin || onlinePluginByName;

    if (matchedPlugin) {
      extension.online_version = matchedPlugin.version;
      extension.has_update =
        extension.version !== matchedPlugin.version &&
        matchedPlugin.version !== tm("status.unknown");
    } else {
      extension.has_update = false;
    }
  });
};

const uninstallExtension = async (
  extension_name,
  optionsOrSkipConfirm = false,
) => {
  let deleteConfig = false;
  let deleteData = false;
  let skipConfirm = false;

  // 处理参数：可能是布尔值（旧的 skipConfirm）或对象（新的选项）
  if (typeof optionsOrSkipConfirm === "boolean") {
    skipConfirm = optionsOrSkipConfirm;
  } else if (
    typeof optionsOrSkipConfirm === "object" &&
    optionsOrSkipConfirm !== null
  ) {
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
  toast(tm("messages.uninstalling") + " " + extension_name, "primary");
  try {
    const res = await axios.post("/api/plugin/uninstall", {
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

const updateExtension = async (extension_name, forceUpdate = false) => {
  // 查找插件信息
  const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
  const ext = data.find((e) => e.name === extension_name);

  // 如果没有检测到更新且不是强制更新，则弹窗确认
  if (!ext?.has_update && !forceUpdate) {
    forceUpdateDialog.extensionName = extension_name;
    forceUpdateDialog.show = true;
    return;
  }

  loadingDialog.title = tm("status.loading");
  loadingDialog.show = true;
  try {
    const res = await axios.post("/api/plugin/update", {
      name: extension_name,
      proxy: getSelectedGitHubProxy(),
    });

    if (res.data.status === "error") {
      onLoadingDialogResult(2, res.data.message, -1);
      return;
    }

    Object.assign(extension_data, res.data);
    onLoadingDialogResult(1, res.data.message);
    setTimeout(async () => {
      toast(tm("messages.refreshing"), "info", 2000);
      try {
        await getExtensions();
        toast(tm("messages.refreshSuccess"), "success");

        // 更新完成后弹出更新日志
        viewChangelog({
          name: extension_name,
          repo: ext?.repo || null,
        });
      } catch (error) {
        const errorMsg =
          error.response?.data?.message || error.message || String(error);
        toast(`${tm("messages.refreshFailed")}: ${errorMsg}`, "error");
      }
    }, 1000);
  } catch (err) {
    toast(err, "error");
  }
};

// 确认强制更新
// 显示更新全部插件确认对话框
const showUpdateAllConfirm = () => {
  if (updatableExtensions.value.length === 0) return;
  updateAllConfirmDialog.show = true;
};

// 确认更新全部插件
const confirmUpdateAll = () => {
  updateAllConfirmDialog.show = false;
  updateAllExtensions();
};

// 取消更新全部插件
const cancelUpdateAll = () => {
  updateAllConfirmDialog.show = false;
};

const confirmForceUpdate = () => {
  const name = forceUpdateDialog.extensionName;
  forceUpdateDialog.show = false;
  forceUpdateDialog.extensionName = "";
  updateExtension(name, true);
};

const updateAllExtensions = async () => {
  if (updatingAll.value || updatableExtensions.value.length === 0) return;
  updatingAll.value = true;
  loadingDialog.title = tm("status.loading");
  loadingDialog.statusCode = 0;
  loadingDialog.result = "";
  loadingDialog.show = true;

  const targets = updatableExtensions.value.map((ext) => ext.name);
  try {
    const res = await axios.post("/api/plugin/update-all", {
      names: targets,
      proxy: getSelectedGitHubProxy(),
    });

    if (res.data.status === "error") {
      onLoadingDialogResult(
        2,
        res.data.message ||
          tm("messages.updateAllFailed", {
            failed: targets.length,
            total: targets.length,
          }),
        -1,
      );
      return;
    }

    const results = res.data.data?.results || [];
    const failures = results.filter((r) => r.status !== "ok");
    try {
      await getExtensions();
    } catch (err) {
      const errorMsg =
        err.response?.data?.message || err.message || String(err);
      failures.push({ name: "refresh", status: "error", message: errorMsg });
    }

    if (failures.length === 0) {
      onLoadingDialogResult(1, tm("messages.updateAllSuccess"));
    } else {
      const failureText = tm("messages.updateAllFailed", {
        failed: failures.length,
        total: targets.length,
      });
      const detail = failures.map((f) => `${f.name}: ${f.message}`).join("\n");
      onLoadingDialogResult(2, `${failureText}\n${detail}`, -1);
    }
  } catch (err) {
    const errorMsg = err.response?.data?.message || err.message || String(err);
    onLoadingDialogResult(2, errorMsg, -1);
  } finally {
    updatingAll.value = false;
  }
};

const pluginOn = async (extension) => {
  try {
    const res = await axios.post("/api/plugin/on", { name: extension.name });
    if (res.data.status === "error") {
      toast(res.data.message, "error");
      return;
    }
    toast(res.data.message, "success");
    await getExtensions();

    await checkAndPromptConflicts();
  } catch (err) {
    toast(err, "error");
  }
};

const pluginOff = async (extension) => {
  try {
    const res = await axios.post("/api/plugin/off", { name: extension.name });
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
    const res = await axios.get(
      "/api/config/get?plugin_name=" + extension_name,
    );
    extension_config.metadata = res.data.data.metadata;
    extension_config.config = res.data.data.config;
  } catch (err) {
    toast(err, "error");
  }
};

const updateConfig = async () => {
  try {
    const res = await axios.post(
      "/api/config/plugin/update?plugin_name=" + curr_namespace.value,
      extension_config.config,
    );
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
    const res = await axios.post("/api/plugin/reload", { name: plugin_name });
    if (res.data.status === "error") {
      toast(res.data.message, "error");
      return;
    }
    toast(tm("messages.reloadSuccess"), "success");
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

// 查看更新日志
const viewChangelog = (plugin) => {
  changelogDialog.pluginName = plugin.name;
  changelogDialog.repoUrl = plugin.repo;
  changelogDialog.show = true;
};

// 打开扩展页面
const openExtensionPage = async (plugin) => {
  extensionPageDialog.html = "";
  extensionPageDialog.title = `${plugin.display_name || plugin.name} - 扩展页面`;
  extensionPageDialog.show = true;
  await fetchExtensionPage(plugin.name);
};

// 获取扩展页面内容
async function fetchExtensionPage(pluginName) {
  try {
    // 使用 encodeURIComponent 对插件名称进行 URL 编码，防止特殊字符破坏 URL
    const res = await axios.get(
      `/api/plugin/extension_page?name=${encodeURIComponent(pluginName)}`
    );
    if (res.data.status === "ok") {
      extensionPageDialog.html = res.data.data.html;
      extensionPageDialog.title = res.data.data.title;
    } else {
      toast(res.data.message, "error");
      extensionPageDialog.show = false;
    }
  } catch (err) {
    toast("获取扩展页面失败: " + err.message, "error");
    extensionPageDialog.show = false;
  }
}

// 为表格视图创建一个处理安装插件的函数
const handleInstallPlugin = async (plugin) => {
  if (plugin.tags && plugin.tags.includes("danger")) {
    selectedDangerPlugin.value = plugin;
    dangerConfirmDialog.value = true;
  } else {
    extension_url.value = plugin.repo;
    dialog.value = true;
    uploadTab.value = "url";
  }
};

// 确认安装危险插件
const confirmDangerInstall = () => {
  if (selectedDangerPlugin.value) {
    extension_url.value = selectedDangerPlugin.value.repo;
    dialog.value = true;
    uploadTab.value = "url";
  }
  dangerConfirmDialog.value = false;
  selectedDangerPlugin.value = null;
};

// 取消安装危险插件
const cancelDangerInstall = () => {
  dangerConfirmDialog.value = false;
  selectedDangerPlugin.value = null;
};

// 自定义插件源管理方法
const loadCustomSources = async () => {
  try {
    const res = await axios.get("/api/plugin/source/get");
    if (res.data.status === "ok") {
      customSources.value = res.data.data;
    } else {
      toast(res.data.message, "error");
    }
  } catch (e) {
    console.warn("Failed to load custom sources:", e);
    customSources.value = [];
  }

  // 加载当前选中的插件源
  const currentSource = localStorage.getItem("selectedPluginSource");
  if (currentSource) {
    selectedSource.value = currentSource;
  }
};

const saveCustomSources = async () => {
  try {
    const res = await axios.post("/api/plugin/source/save", {
      sources: customSources.value,
    });
    if (res.data.status !== "ok") {
      toast(res.data.message, "error");
    }
  } catch (e) {
    toast(e, "error");
  }
};

const addCustomSource = () => {
  editingSource.value = false;
  originalSourceUrl.value = "";
  sourceName.value = "";
  sourceUrl.value = "";
  showSourceDialog.value = true;
};

const selectPluginSource = (sourceUrl) => {
  selectedSource.value = sourceUrl;
  if (sourceUrl) {
    localStorage.setItem("selectedPluginSource", sourceUrl);
  } else {
    localStorage.removeItem("selectedPluginSource");
  }
  // 重新加载插件市场数据
  refreshPluginMarket();
};

// 获取当前选中的源对象
const selectedSourceObj = computed(() => {
  if (!selectedSource.value) return null;
  return (
    customSources.value.find((s) => s.url === selectedSource.value) || null
  );
});

const editCustomSource = (source) => {
  if (!source) return;
  editingSource.value = true;
  originalSourceUrl.value = source.url;
  sourceName.value = source.name;
  sourceUrl.value = source.url;
  showSourceDialog.value = true;
};

const removeCustomSource = (source) => {
  if (!source) return;
  sourceToRemove.value = source;
  showRemoveSourceDialog.value = true;
};

const confirmRemoveSource = () => {
  if (sourceToRemove.value) {
    customSources.value = customSources.value.filter(
      (s) => s.url !== sourceToRemove.value.url,
    );
    saveCustomSources();

    // 如果删除的是当前选中的源，切换到默认源
    if (selectedSource.value === sourceToRemove.value.url) {
      selectedSource.value = null;
      localStorage.removeItem("selectedPluginSource");
      // 重新加载插件市场数据
      refreshPluginMarket();
    }

    toast(tm("market.sourceRemoved"), "success");
    showRemoveSourceDialog.value = false;
    sourceToRemove.value = null;
  }
};

const saveCustomSource = () => {
  const normalizedUrl = sourceUrl.value.trim();

  if (!sourceName.value.trim() || !normalizedUrl) {
    toast(tm("messages.fillSourceNameAndUrl"), "error");
    return;
  }

  // 检查URL格式
  try {
    new URL(normalizedUrl);
  } catch (e) {
    toast(tm("messages.invalidUrl"), "error");
    return;
  }

  if (editingSource.value) {
    // 编辑模式：更新现有源
    const index = customSources.value.findIndex(
      (s) => s.url === originalSourceUrl.value,
    );
    if (index !== -1) {
      customSources.value[index] = {
        name: sourceName.value.trim(),
        url: normalizedUrl,
      };

      // 如果编辑的是当前选中的源，更新选中源
      if (selectedSource.value === originalSourceUrl.value) {
        selectedSource.value = normalizedUrl;
        localStorage.setItem("selectedPluginSource", selectedSource.value);
        // 重新加载插件市场数据
        refreshPluginMarket();
      }
    }
  } else {
    // 添加模式：检查是否已存在
    if (customSources.value.some((source) => source.url === normalizedUrl)) {
      toast(tm("market.sourceExists"), "error");
      return;
    }

    customSources.value.push({
      name: sourceName.value.trim(),
      url: normalizedUrl,
    });
  }

  saveCustomSources();
  toast(
    editingSource.value ? tm("market.sourceUpdated") : tm("market.sourceAdded"),
    "success",
  );

  // 重置表单
  sourceName.value = "";
  sourceUrl.value = "";
  editingSource.value = false;
  originalSourceUrl.value = "";
  showSourceDialog.value = false;
};

// 插件市场显示完整插件名称
const trimExtensionName = () => {
  pluginMarketData.value.forEach((plugin) => {
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
  const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
  const installedRepos = new Set(data.map((ext) => ext.repo?.toLowerCase()));
  const installedNames = new Set(data.map((ext) => ext.name));

  for (let i = 0; i < pluginMarketData.value.length; i++) {
    const plugin = pluginMarketData.value[i];
    plugin.installed =
      installedRepos.has(plugin.repo?.toLowerCase()) ||
      installedNames.has(plugin.name);
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
    toast(tm("messages.fillUrlOrFile"), "error");
    return;
  }

  if (extension_url.value !== "" && upload_file.value !== null) {
    toast(tm("messages.dontFillBoth"), "error");
    return;
  }
  loading_.value = true;
  loadingDialog.title = tm("status.loading");
  loadingDialog.show = true;
  if (upload_file.value !== null) {
    toast(tm("messages.installing"), "primary");
    const formData = new FormData();
    formData.append("file", upload_file.value);
    axios
      .post("/api/plugin/install-upload", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      })
      .then(async (res) => {
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
          repo: res.data.data.repo || null,
        });

        await checkAndPromptConflicts();
      })
      .catch((err) => {
        loading_.value = false;
        onLoadingDialogResult(2, err, -1);
      });
  } else {
    toast(
      tm("messages.installingFromUrl") + " " + extension_url.value,
      "primary",
    );
    axios
      .post("/api/plugin/install", {
        url: extension_url.value,
        proxy: getSelectedGitHubProxy(),
      })
      .then(async (res) => {
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
          repo: res.data.data.repo || null,
        });

        await checkAndPromptConflicts();
      })
      .catch((err) => {
        loading_.value = false;
        toast(tm("messages.installFailed") + " " + err, "error");
        onLoadingDialogResult(2, err, -1);
      });
  }
};

// 刷新插件市场数据
const refreshPluginMarket = async () => {
  refreshingMarket.value = true;
  try {
    // 强制刷新插件市场数据
    const data = await commonStore.getPluginCollections(
      true,
      selectedSource.value,
    );
    pluginMarketData.value = data;
    trimExtensionName();
    checkAlreadyInstalled();
    checkUpdate();
    currentPage.value = 1; // 重置到第一页

    toast(tm("messages.refreshSuccess"), "success");
  } catch (err) {
    toast(tm("messages.refreshFailed") + " " + err, "error");
  } finally {
    refreshingMarket.value = false;
  }
};

// 生命周期
onMounted(async () => {
  if (!syncTabFromHash(getLocationHash())) {
    if (typeof window !== "undefined") {
      window.location.hash = `#${activeTab.value}`;
    }
  }
  await getExtensions();

  // 加载自定义插件源
  loadCustomSources();

  // 检查是否有 open_config 参数
  let urlParams;
  if (window.location.hash) {
    // For hash mode (#/path?param=value)
    const hashQuery = window.location.hash.split("?")[1] || "";
    urlParams = new URLSearchParams(hashQuery);
  } else {
    // For history mode (/path?param=value)
    urlParams = new URLSearchParams(window.location.search);
  }
  console.log("URL Parameters:", urlParams.toString());
  const plugin_name = urlParams.get("open_config");
  if (plugin_name) {
    console.log(`Opening config for plugin: ${plugin_name}`);
    openExtensionConfig(plugin_name);
  }

  try {
    const data = await commonStore.getPluginCollections(
      false,
      selectedSource.value,
    );
    pluginMarketData.value = data;
    trimExtensionName();
    checkAlreadyInstalled();
    checkUpdate();
  } catch (err) {
    toast(tm("messages.getMarketDataFailed") + " " + err, "error");
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

// 监听显示模式变化并保存到 localStorage
watch(isListView, (newVal) => {
  if (typeof window !== "undefined" && window.localStorage) {
    localStorage.setItem("pluginListViewMode", String(newVal));
  }
});

watch(
  () => route.fullPath,
  () => {
    const tab = extractTabFromHash(getLocationHash());
    if (isValidTab(tab) && tab !== activeTab.value) {
      activeTab.value = tab;
    }
  },
);

const selectedInstalledPlugin = computed(() => {
  if (!selectedPluginId.value) return null;
  const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
  return data.find((plugin) => plugin.name === selectedPluginId.value) || null;
});

const selectedMarketPlugin = computed(() => {
  const market = Array.isArray(pluginMarketData.value)
    ? pluginMarketData.value
    : [];
  const installedPlugin = selectedInstalledPlugin.value;
  const repo = installedPlugin?.repo?.toLowerCase();
  return (
    market.find((item) => item.name === selectedPluginId.value) ||
    market.find((item) => repo && item.repo?.toLowerCase() === repo) ||
    null
  );
});

const selectedDetailPlugin = computed(() => {
  if (selectedDetailTab.value === "market" && selectedMarketPlugin.value) {
    return selectedMarketPlugin.value;
  }
  return selectedInstalledPlugin.value || selectedMarketPlugin.value;
});

const installDialogPluginName = computed(() =>
  selectedInstallPlugin.value ? pluginName(selectedInstallPlugin.value) : "",
);

const installDialogPluginDesc = computed(() =>
  String(
    selectedInstallPlugin.value
      ? pluginDesc(
          selectedInstallPlugin.value,
          selectedInstallPlugin.value.desc ||
            selectedInstallPlugin.value.description ||
            "",
        )
      : "",
  ).trim(),
);

const installDialogPluginAuthor = computed(() => {
  const author = selectedInstallPlugin.value?.author;
  if (Array.isArray(author)) return author.join(", ");
  if (author && typeof author === "object") return author.name || "";
  return typeof author === "string" ? author.trim() : "";
});

const installDialogPluginLogo = computed(() => {
  const logo = selectedInstallPlugin.value?.logo;
  return typeof logo === "string" && logo.trim() ? logo : defaultPluginIcon;
});

const updateDialogPlugin = computed(
  () => selectedUpdateMarketPlugin.value || selectedUpdateExtension.value,
);

const updateDialogPluginName = computed(() =>
  updateDialogPlugin.value ? pluginName(updateDialogPlugin.value) : "",
);

const updateDialogCurrentVersion = computed(() =>
  String(selectedUpdateExtension.value?.version || "").trim(),
);

const updateDialogTargetVersion = computed(() =>
  String(selectedUpdateMarketPlugin.value?.version || "").trim(),
);

const updateDialogPluginLogo = computed(() => {
  const logo =
    selectedUpdateMarketPlugin.value?.logo || selectedUpdateExtension.value?.logo;
  return typeof logo === "string" && logo.trim() ? logo : defaultPluginIcon;
});
</script>

<template>
  <PluginDetailPage
    v-if="selectedPluginId && selectedDetailPlugin"
    :plugin="selectedDetailPlugin"
    :market-plugin="selectedMarketPlugin"
    :source-tab="selectedDetailTab"
    :state="pageState"
  />

  <div v-else-if="selectedPluginId && loading_" class="pa-4">
    <v-progress-linear indeterminate color="primary" />
  </div>

  <div v-else-if="selectedPluginId" class="pa-4">
    <div class="d-flex align-center mb-6">
      <v-btn
        icon="mdi-arrow-left"
        variant="text"
        density="comfortable"
        @click="
          router.push({ name: 'Extensions', hash: `#${selectedDetailTab}` })
        "
      />
      <h2 class="text-h3 mb-0 ml-2">
        {{
          selectedDetailTab === "market"
            ? tm("tabs.market")
            : tm("titles.installedAstrBotPlugins")
        }}
        <v-icon icon="mdi-chevron-right" size="24" class="mx-1" />
        {{ selectedPluginId }}
      </h2>
    </div>
    <v-alert type="warning" variant="tonal">
      {{ tm("detail.notFound") }}
    </v-alert>
  </div>

  <v-row v-else class="extension-page">
    <v-col cols="12" md="12">
      <v-card variant="flat" style="background-color: transparent">
        <!-- 标签页 -->
        <v-card-text style="padding: 0px 12px">
          <!-- 已安装插件标签页内容 -->
          <v-tab-item v-show="activeTab === 'installed'">
            <v-row class="mb-4">
              <v-col cols="12" class="d-flex align-center flex-wrap ga-2">
                <v-btn-group
                  variant="outlined"
                  density="comfortable"
                  color="primary"
                >
                  <v-btn
                    @click="isListView = false"
                    :color="!isListView ? 'primary' : undefined"
                    :variant="!isListView ? 'flat' : 'outlined'"
                  >
                    <v-icon>mdi-view-grid</v-icon>
                  </v-btn>
                  <v-btn
                    @click="isListView = true"
                    :color="isListView ? 'primary' : undefined"
                    :variant="isListView ? 'flat' : 'outlined'"
                  >
                    <v-icon>mdi-view-list</v-icon>
                  </v-btn>
                </v-btn-group>

                <v-btn class="ml-2" variant="tonal" @click="toggleShowReserved">
                  <v-icon>{{
                    showReserved ? "mdi-eye-off" : "mdi-eye"
                  }}</v-icon>
                  {{
                    showReserved
                      ? tm("buttons.hideSystemPlugins")
                      : tm("buttons.showSystemPlugins")
                  }}
                </v-btn>

                <v-btn
                  class="ml-2"
                  color="warning"
                  variant="tonal"
                  :disabled="updatableExtensions.length === 0"
                  :loading="updatingAll"
                  @click="showUpdateAllConfirm"
                >
                  <v-icon>mdi-update</v-icon>
                  {{ tm("buttons.updateAll") }}
                </v-btn>

                <v-btn
                  class="ml-2"
                  color="primary"
                  variant="tonal"
                  @click="dialog = true"
                >
                  <v-icon>mdi-plus</v-icon>
                  {{ tm("buttons.install") }}
                </v-btn>

                <v-col cols="12" sm="auto" class="ml-auto">
                  <v-dialog max-width="500px" v-if="extension_data.message">
                    <template v-slot:activator="{ props }">
                      <v-btn
                        v-bind="props"
                        icon
                        size="small"
                        color="error"
                        class="ml-2"
                        variant="tonal"
                      >
                        <v-icon>mdi-alert-circle</v-icon>
                      </v-btn>
                    </template>
                    <template v-slot:default="{ isActive }">
                      <v-card class="rounded-lg">
                        <v-card-title class="headline d-flex align-center">
                          <v-icon color="error" class="mr-2"
                            >mdi-alert-circle</v-icon
                          >
                          {{ tm("dialogs.error.title") }}
                        </v-card-title>
                        <v-card-text>
                          <p class="text-body-1">
                            {{ extension_data.message }}
                          </p>
                          <p class="text-caption mt-2">
                            {{ tm("dialogs.error.checkConsole") }}
                          </p>
                        </v-card-text>
                        <v-card-actions>
                          <v-spacer></v-spacer>
                          <v-btn
                            color="primary"
                            @click="isActive.value = false"
                            >{{ tm("buttons.close") }}</v-btn
                          >
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
                  <v-data-table
                    :headers="pluginHeaders"
                    :items="filteredPlugins"
                    :loading="loading_"
                    item-key="name"
                    hover
                  >
                    <template v-slot:loader>
                      <v-row class="py-8 d-flex align-center justify-center">
                        <v-progress-circular
                          indeterminate
                          color="primary"
                        ></v-progress-circular>
                        <span class="ml-2">{{ tm("status.loading") }}</span>
                      </v-row>
                    </template>

                    <template v-slot:item.name="{ item }">
                      <div class="d-flex align-center py-2">
                        <div
                          v-if="item.logo"
                          class="mr-3"
                          style="flex-shrink: 0"
                        >
                          <img
                            :src="item.logo"
                            :alt="item.name"
                            style="
                              height: 40px;
                              width: 40px;
                              border-radius: 8px;
                              object-fit: cover;
                            "
                          />
                        </div>
                        <div v-else class="mr-3" style="flex-shrink: 0">
                          <img
                            :src="defaultPluginIcon"
                            :alt="item.name"
                            style="
                              height: 40px;
                              width: 40px;
                              border-radius: 8px;
                              object-fit: cover;
                            "
                          />
                        </div>
                        <div>
                          <div class="text-subtitle-1 font-weight-medium">
                            {{
                              item.display_name && item.display_name.length
                                ? item.display_name
                                : item.name
                            }}
                          </div>
                          <div
                            v-if="item.display_name && item.display_name.length"
                            class="text-caption text-medium-emphasis mt-1"
                          >
                            {{ item.name }}
                          </div>
                          <div
                            v-if="item.reserved"
                            class="d-flex align-center mt-1"
                          >
                            <v-chip
                              color="primary"
                              size="x-small"
                              class="font-weight-medium"
                              >{{ tm("status.system") }}</v-chip
                            >
                          </div>
                        </div>
                      </div>
                    </template>

                    <template v-slot:item.desc="{ item }">
                      <div
                        class="text-body-2 text-medium-emphasis mt-2 mb-2"
                        style="
                          display: -webkit-box;
                          -webkit-line-clamp: 3;
                          line-clamp: 3;
                          -webkit-box-orient: vertical;
                          overflow: hidden;
                          text-overflow: ellipsis;
                        "
                      >
                        {{ item.desc }}
                      </div>
                    </template>

                    <template v-slot:item.version="{ item }">
                      <div class="d-flex align-center">
                        <span class="text-body-2">{{ item.version }}</span>
                        <v-icon
                          v-if="item.has_update"
                          color="warning"
                          size="small"
                          class="ml-1"
                          >mdi-alert</v-icon
                        >
                        <v-tooltip v-if="item.has_update" activator="parent">
                          <span
                            >{{ tm("messages.hasUpdate") }}
                            {{ item.online_version }}</span
                          >
                        </v-tooltip>
                      </div>
                    </template>

                    <template v-slot:item.author="{ item }">
                      <div class="text-body-2">{{ item.author }}</div>
                    </template>

                    <template v-slot:item.activated="{ item }">
                      <v-chip
                        :color="item.activated ? 'success' : 'error'"
                        size="small"
                        class="font-weight-medium"
                        :variant="item.activated ? 'flat' : 'outlined'"
                      >
                        {{
                          item.activated
                            ? tm("status.enabled")
                            : tm("status.disabled")
                        }}
                      </v-chip>
                    </template>

                    <template v-slot:item.actions="{ item }">
                      <div class="d-flex align-center">
                        <v-btn-group
                          density="comfortable"
                          variant="text"
                          color="primary"
                        >
                          <v-btn
                            v-if="!item.activated"
                            icon
                            size="small"
                            color="success"
                            @click="pluginOn(item)"
                          >
                            <v-icon>mdi-play</v-icon>
                            <v-tooltip activator="parent" location="top">{{
                              tm("tooltips.enable")
                            }}</v-tooltip>
                          </v-btn>
                          <v-btn
                            v-else
                            icon
                            size="small"
                            color="error"
                            @click="pluginOff(item)"
                          >
                            <v-icon>mdi-pause</v-icon>
                            <v-tooltip activator="parent" location="top">{{
                              tm("tooltips.disable")
                            }}</v-tooltip>
                          </v-btn>

                          <v-btn
                            icon
                            size="small"
                            @click="reloadPlugin(item.name)"
                          >
                            <v-icon>mdi-refresh</v-icon>
                            <v-tooltip activator="parent" location="top">{{
                              tm("tooltips.reload")
                            }}</v-tooltip>
                          </v-btn>

                          <v-btn
                            icon
                            size="small"
                            @click="openExtensionConfig(item.name)"
                          >
                            <v-icon>mdi-cog</v-icon>
                            <v-tooltip activator="parent" location="top">{{
                              tm("tooltips.configure")
                            }}</v-tooltip>
                          </v-btn>

                          <v-btn
                            icon
                            size="small"
                            @click="showPluginInfo(item)"
                          >
                            <v-icon>mdi-information</v-icon>
                            <v-tooltip activator="parent" location="top">{{
                              tm("tooltips.viewInfo")
                            }}</v-tooltip>
                          </v-btn>

                          <v-btn
                            v-if="item.repo"
                            icon
                            size="small"
                            @click="viewReadme(item)"
                          >
                            <v-icon>mdi-book-open-page-variant</v-icon>
                            <v-tooltip activator="parent" location="top">{{
                              tm("tooltips.viewDocs")
                            }}</v-tooltip>
                          </v-btn>

                          <v-btn
                            icon
                            size="small"
                            @click="updateExtension(item.name)"
                          >
                            <v-icon>mdi-update</v-icon>
                            <v-tooltip activator="parent" location="top">{{
                              tm("tooltips.update")
                            }}</v-tooltip>
                          </v-btn>

                          <v-btn
                            icon
                            size="small"
                            color="error"
                            @click="uninstallExtension(item.name)"
                            :disabled="item.reserved"
                          >
                            <v-icon>mdi-delete</v-icon>
                            <v-tooltip activator="parent" location="top">{{
                              tm("tooltips.uninstall")
                            }}</v-tooltip>
                          </v-btn>
                        </v-btn-group>
                      </div>
                    </template>

                    <template v-slot:no-data>
                      <div class="text-center pa-8">
                        <v-icon size="64" color="info" class="mb-4"
                          >mdi-puzzle-outline</v-icon
                        >
                        <div class="text-h5 mb-2">
                          {{ tm("empty.noPlugins") }}
                        </div>
                        <div class="text-body-1 mb-4">
                          {{ tm("empty.noPluginsDesc") }}
                        </div>
                      </div>
                    </template>
                  </v-data-table>
                </v-card>
              </div>

              <!-- 卡片视图 -->
              <div v-else>
                <v-row v-if="filteredPlugins.length === 0" class="text-center">
                  <v-col cols="12" class="pa-2">
                    <v-icon size="64" color="info" class="mb-4"
                      >mdi-puzzle-outline</v-icon
                    >
                    <div class="text-h5 mb-2">{{ tm("empty.noPlugins") }}</div>
                    <div class="text-body-1 mb-4">
                      {{ tm("empty.noPluginsDesc") }}
                    </div>
                  </v-col>
                </v-row>

                <v-row>
                  <v-col
                    cols="12"
                    md="6"
                    lg="4"
                    v-for="extension in filteredPlugins"
                    :key="extension.name"
                    class="pb-2"
                  >
                    <ExtensionCard
                      :extension="extension"
                      class="rounded-lg"
                      style="background-color: rgb(var(--v-theme-mcpCardBg))"
                      @configure="openExtensionConfig(extension.name)"
                      @uninstall="
                        (ext, options) => uninstallExtension(ext.name, options)
                      "
                      @update="updateExtension(extension.name)"
                      @reload="reloadPlugin(extension.name)"
                      @toggle-activation="
                        extension.activated
                          ? pluginOff(extension)
                          : pluginOn(extension)
                      "
                      @view-handlers="showPluginInfo(extension)"
                      @view-readme="viewReadme(extension)"
                      @view-changelog="viewChangelog(extension)"
                      @view-extension-page="openExtensionPage(extension)"
                    >
                    </ExtensionCard>
                  </v-col>
                </v-row>
              </div>
            </v-fade-transition>
          </v-tab-item>

          <!-- 指令面板标签页内容 -->
          <v-tab-item v-if="activeTab === 'components'">
            <div class="mb-4 pt-4 pb-4">
              <div class="d-flex align-center flex-wrap" style="gap: 12px">
                <h2 class="text-h2 mb-0">{{ tm("tabs.handlersOperation") }}</h2>
              </div>
            </div>
            <v-card
              class="rounded-lg"
              variant="flat"
              style="background-color: transparent"
            >
              <v-card-text class="pa-0">
                <ComponentPanel :active="activeTab === 'components'" />
              </v-card-text>
            </v-card>
          </v-tab-item>

          <!-- 已安装的 MCP 服务器标签页内容 -->
          <v-tab-item v-if="activeTab === 'mcp'">
            <div class="extension-detail-width">
              <div class="mb-4 pt-4 pb-4">
                <div class="d-flex flex-column" style="gap: 6px">
                  <h2 class="text-h2 mb-0">
                    {{ tm("tabs.installedMcpServers") }}
                  </h2>
                  <div class="text-body-2 text-medium-emphasis">
                    {{ t("features.tooluse.mcpServers.description") }}
                  </div>
                </div>
              </div>
              <v-card
                class="rounded-lg"
                variant="flat"
                style="background-color: transparent"
              >
                <v-card-text class="pa-0">
                  <McpServersSection />
                </v-card-text>
              </v-card>
            </div>
          </v-tab-item>

          <!-- Skills 标签页内容 -->
          <v-tab-item v-if="activeTab === 'skills'">
            <div class="extension-detail-width">
              <div class="mb-4 pt-4 pb-4">
                <div class="d-flex flex-column" style="gap: 6px">
                  <h2 class="text-h2 mb-0">{{ tm("tabs.skills") }}</h2>
                  <div class="text-body-2 text-medium-emphasis">
                    {{ tm("skills.runtimeHint") }}
                  </div>
                </div>
              </div>
              <v-card
                class="rounded-lg"
                variant="flat"
                style="background-color: transparent"
              >
                <v-card-text class="pa-0">
                  <SkillsSection />
                </v-card-text>
              </v-card>
            </div>
          </v-tab-item>

          <!-- 插件市场标签页内容 -->
          <MarketPluginsTab :state="pageState" />
        </v-card-text>
      </v-card>
    </v-col>

    <v-col v-if="activeTab === 'market'" cols="12" md="12">
      <div class="d-flex align-center justify-center mt-4 mb-4 gap-4">
        <v-btn
          variant="text"
          prepend-icon="mdi-book-open-variant"
          href="https://docs.astrbot.app/dev/star/plugin-new.html"
          rel="noopener noreferrer"
          target="_blank"
          color="primary"
          class="text-none"
        >
          {{ tm("market.devDocs") }}
        </v-btn>
        <div
          style="
            height: 24px;
            width: 1px;
            background-color: rgba(var(--v-theme-on-surface), 0.12);
          "
        ></div>
        <v-btn
          variant="text"
          prepend-icon="mdi-github"
          href="https://github.com/AstrBotDevs/AstrBot_Plugins_Collection"
          target="_blank"
          color="primary"
          class="text-none"
        >
          {{ tm("market.submitRepo") }}
        </v-btn>
      </div>
    </v-col>
  </v-row>

  <!-- 配置对话框 -->
  <v-dialog v-model="configDialog" max-width="900">
    <v-card>
      <v-card-title class="text-h2 pa-4 pl-6 pb-0">{{
        tm("dialogs.config.title")
      }}</v-card-title>
      <v-card-text>
        <div style="max-height: 60vh; overflow-y: auto; padding-right: 8px">
          <AstrBotConfig
            v-if="extension_config.metadata"
            :metadata="extension_config.metadata"
            :iterable="extension_config.config"
            :metadataKey="curr_namespace"
            :pluginName="curr_namespace"
            :pluginI18n="extension_config.i18n"
          />
          <p v-else>{{ tm("dialogs.config.noConfig") }}</p>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="updateConfig">{{
          tm("buttons.saveAndClose")
        }}</v-btn>
        <v-btn
          color="blue-darken-1"
          variant="text"
          @click="configDialog = false"
          >{{ tm("buttons.close") }}</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 加载对话框 -->
  <v-dialog v-model="loadingDialog.show" width="700" persistent>
    <v-card>
      <v-card-title class="text-h5">{{ loadingDialog.title }}</v-card-title>
      <v-card-text style="max-height: calc(100vh - 200px); overflow-y: auto">
        <v-progress-linear
          v-if="loadingDialog.statusCode === 0"
          indeterminate
          color="primary"
          class="mb-4"
        ></v-progress-linear>

        <div v-if="loadingDialog.statusCode !== 0" class="py-8 text-center">
          <v-icon
            class="mb-6"
            :color="loadingDialog.statusCode === 1 ? 'success' : 'error'"
            :icon="
              loadingDialog.statusCode === 1
                ? 'mdi-check-circle-outline'
                : 'mdi-alert-circle-outline'
            "
            size="128"
          ></v-icon>
          <div class="text-h4 font-weight-bold">{{ loadingDialog.result }}</div>
        </div>

        <div style="margin-top: 32px">
          <h3>{{ tm("dialogs.loading.logs") }}</h3>
          <ConsoleDisplayer
            historyNum="10"
            style="height: 200px; margin-top: 16px; margin-bottom: 24px"
          >
          </ConsoleDisplayer>
        </div>
      </v-card-text>

      <v-divider></v-divider>

      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn
          color="blue-darken-1"
          variant="text"
          @click="resetLoadingDialog"
          >{{ tm("buttons.close") }}</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-snackbar
    :timeout="2000"
    elevation="24"
    :color="snack_success"
    v-model="snack_show"
    location="bottom center"
  >
    {{ snack_message }}
  </v-snackbar>

  <ReadmeDialog
    v-model:show="readmeDialog.show"
    :plugin-name="readmeDialog.pluginName"
    :repo-url="readmeDialog.repoUrl"
  />

  <!-- 插件更新日志对话框（复用 ReadmeDialog） -->
  <ReadmeDialog
    v-model:show="changelogDialog.show"
    :plugin-name="changelogDialog.pluginName"
    :repo-url="changelogDialog.repoUrl"
    mode="changelog"
  />

  <!-- 卸载插件确认对话框（列表模式用） -->
  <UninstallConfirmDialog
    v-model="showUninstallDialog"
    @confirm="handleUninstallConfirm"
  />

  <!-- 更新全部插件确认对话框 -->
  <v-dialog v-model="updateAllConfirmDialog.show" max-width="420">
    <v-card class="rounded-lg">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon color="warning" class="mr-2">mdi-update</v-icon>
        {{ tm("dialogs.updateAllConfirm.title") }}
      </v-card-title>
      <v-card-text>
        <p class="text-body-1">
          {{
            tm("dialogs.updateAllConfirm.message", {
              count: updatableExtensions.length,
            })
          }}
        </p>
      </v-card-text>
      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelUpdateAll">{{
          tm("buttons.cancel")
        }}</v-btn>
        <v-btn color="warning" variant="flat" @click="confirmUpdateAll">{{
          tm("dialogs.updateAllConfirm.confirm")
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 指令冲突提示对话框 -->
  <v-dialog v-model="conflictDialog.show" max-width="420">
    <v-card class="rounded-lg">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon color="warning" class="mr-2">mdi-alert-circle</v-icon>
        {{ tm("conflicts.title") }}
      </v-card-title>
      <v-card-text class="px-4 pb-2">
        <div class="d-flex align-center mb-3">
          <v-chip
            color="warning"
            variant="tonal"
            size="large"
            class="font-weight-bold"
          >
            {{ conflictDialog.count }}
          </v-chip>
          <span class="ml-2 text-body-1">{{ tm("conflicts.pairs") }}</span>
        </div>
        <p
          class="text-body-2"
          style="color: rgba(var(--v-theme-on-surface), 0.7)"
        >
          {{ tm("conflicts.message") }}
        </p>
      </v-card-text>
      <v-card-actions class="pa-4 pt-2">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="conflictDialog.show = false">{{
          tm("conflicts.later")
        }}</v-btn>
        <v-btn color="warning" variant="flat" @click="handleConflictConfirm">
          {{ tm("conflicts.goToManage") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 危险插件确认对话框 -->
  <v-dialog v-model="dangerConfirmDialog" width="500" persistent>
    <v-card>
      <v-card-title class="text-h5 d-flex align-center">
        <v-icon color="warning" class="mr-2">mdi-alert-circle</v-icon>
        {{ tm("dialogs.danger_warning.title") }}
      </v-card-title>
      <v-card-text>
        <div>{{ tm("dialogs.danger_warning.message") }}</div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" @click="cancelDangerInstall">
          {{ tm("dialogs.danger_warning.cancel") }}
        </v-btn>
        <v-btn color="warning" @click="confirmDangerInstall">
          {{ tm("dialogs.danger_warning.confirm") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 版本不兼容警告对话框 -->
  <v-dialog v-model="versionCompatibilityDialog.show" width="520" persistent>
    <v-card>
      <v-card-title class="text-h5 d-flex align-center">
        <v-icon color="warning" class="mr-2">mdi-alert</v-icon>
        {{ tm("dialogs.versionCompatibility.title") }}
      </v-card-title>
      <v-card-text>
        <div class="mb-2">{{ tm("dialogs.versionCompatibility.message") }}</div>
        <div class="text-medium-emphasis">
          {{ versionCompatibilityDialog.message }}
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" @click="cancelInstallOnVersionWarning">
          {{ tm("dialogs.versionCompatibility.cancel") }}
        </v-btn>
        <v-btn color="warning" @click="continueInstallIgnoringVersionWarning">
          {{ tm("dialogs.versionCompatibility.confirm") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 上传插件对话框 -->
  <v-dialog v-model="dialog" width="500">
    <div
      class="v-card v-card--density-default rounded-lg v-card--variant-elevated"
    >
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ tm("dialogs.install.title") }}
      </v-card-title>

      <div class="v-card-text">
        <div v-if="selectedMarketInstallPlugin" class="market-install-confirm">
          <div class="market-install-confirm__header">
            <img
              :src="installDialogPluginLogo"
              :alt="installDialogPluginName"
              class="market-install-confirm__logo"
            />
            <div class="market-install-confirm__meta">
              <div class="market-install-confirm__name">
                {{ installDialogPluginName }}
              </div>
              <div
                v-if="installDialogPluginAuthor"
                class="market-install-confirm__author"
              >
                {{ tm("detail.info.author") }}: {{ installDialogPluginAuthor }}
              </div>
            </div>
          </div>

          <v-divider class="my-4" />

          <div
            v-if="installDialogPluginDesc"
            class="market-install-confirm__section"
          >
            <div class="market-install-confirm__section-title">
              {{ tm("table.headers.description") }}
            </div>
            <div class="market-install-confirm__desc">
              {{ installDialogPluginDesc }}
            </div>
          </div>

          <div v-if="selectedInstallPlugin" class="mt-4">
            <v-chip
              v-if="selectedInstallPlugin.astrbot_version"
              size="small"
              color="secondary"
              variant="outlined"
              class="mr-2 mb-2"
            >
              {{ tm("card.status.astrbotVersion") }}:
              {{ selectedInstallPlugin.astrbot_version }}
            </v-chip>
            <v-chip
              v-if="
                normalizePlatformList(selectedInstallPlugin.support_platforms)
                  .length
              "
              size="small"
              color="info"
              variant="outlined"
              class="mb-2"
            >
              {{ tm("card.status.supportPlatform") }}:
              {{
                getPlatformDisplayList(
                  selectedInstallPlugin.support_platforms,
                ).join(", ")
              }}
            </v-chip>
            <v-alert
              v-if="
                selectedInstallPlugin.astrbot_version &&
                installCompat.checked &&
                !installCompat.compatible
              "
              type="warning"
              variant="tonal"
              density="comfortable"
              class="market-install-alert mt-2 mb-3"
            >
              {{ installCompat.message }}
            </v-alert>
          </div>

          <div
            v-if="selectedInstallSourceUrl"
            class="market-install-confirm__section-title mt-4"
          >
            {{ tm("dialogs.install.sectionTitle") }}
          </div>
          <div
            v-if="selectedInstallSourceUrl"
            class="market-install-source text-caption text-medium-emphasis mb-3"
          >
            <div>{{ tm("dialogs.install.downloadSource") }}</div>
            <div class="market-install-source__url">
              {{ selectedInstallSourceUrl }}
            </div>
          </div>

          <v-alert
            v-if="installUsesGithubSource"
            type="warning"
            variant="tonal"
            density="comfortable"
            class="market-install-alert mt-4 mb-4"
          >
            {{ tm("dialogs.install.githubSecurityWarning") }}
          </v-alert>

          <ProxySelector v-if="!selectedInstallDownloadUrl" class="mt-4" />
        </div>

        <template v-else>
          <v-tabs v-model="uploadTab" color="primary">
            <v-tab value="file">{{ tm("dialogs.install.fromFile") }}</v-tab>
            <v-tab value="url">{{ tm("dialogs.install.fromUrl") }}</v-tab>
          </v-tabs>

          <v-window v-model="uploadTab" class="mt-4">
            <v-window-item value="file">
              <div class="d-flex flex-column align-center justify-center pa-4">
                <v-file-input
                  ref="fileInput"
                  v-model="upload_file"
                  :label="tm('upload.selectFile')"
                  accept=".zip"
                  hide-details
                  hide-input
                  class="d-none"
                ></v-file-input>

                <v-btn
                  color="primary"
                  size="large"
                  prepend-icon="mdi-upload"
                  @click="$refs.fileInput.click()"
                  elevation="2"
                >
                  {{ tm("buttons.selectFile") }}
                </v-btn>

                <div class="text-body-2 text-medium-emphasis mt-2">
                  {{ tm("messages.supportedFormats") }}
                </div>

                <div v-if="upload_file" class="mt-4 text-center">
                  <v-chip
                    color="primary"
                    size="large"
                    closable
                    @click:close="upload_file = null"
                  >
                    {{ upload_file.name }}
                    <template v-slot:append>
                      <span class="text-caption ml-2"
                        >({{ (upload_file.size / 1024).toFixed(1) }}KB)</span
                      >
                    </template>
                  </v-chip>
                </div>
              </div>
            </v-window-item>

            <v-window-item value="url">
              <div class="pa-4">
                <v-text-field
                  v-model="extension_url"
                  :label="tm('upload.enterUrl')"
                  variant="outlined"
                  prepend-inner-icon="mdi-link"
                  hide-details
                  class="rounded-lg mb-4"
                  placeholder="https://github.com/username/repo"
                ></v-text-field>

                <div v-if="selectedInstallPlugin" class="mb-3">
                  <v-chip
                    v-if="selectedInstallPlugin.astrbot_version"
                    size="small"
                    color="secondary"
                    variant="outlined"
                    class="mr-2 mb-2"
                  >
                    {{ tm("card.status.astrbotVersion") }}:
                    {{ selectedInstallPlugin.astrbot_version }}
                  </v-chip>
                  <v-chip
                    v-if="
                      normalizePlatformList(
                        selectedInstallPlugin.support_platforms,
                      ).length
                    "
                    size="small"
                    color="info"
                    variant="outlined"
                    class="mb-2"
                  >
                    {{ tm("card.status.supportPlatform") }}:
                    {{
                      getPlatformDisplayList(
                        selectedInstallPlugin.support_platforms,
                      ).join(", ")
                    }}
                  </v-chip>
                  <v-alert
                    v-if="
                      selectedInstallPlugin.astrbot_version &&
                      installCompat.checked &&
                      !installCompat.compatible
                    "
                    type="warning"
                    variant="tonal"
                    density="comfortable"
                    class="market-install-alert mt-2 mb-3"
                  >
                    {{ installCompat.message }}
                  </v-alert>
                </div>

                <div
                  v-if="selectedInstallSourceUrl"
                  class="market-install-confirm__section-title mt-4"
                >
                  {{ tm("dialogs.install.sectionTitle") }}
                </div>
                <div
                  v-if="selectedInstallSourceUrl"
                  class="market-install-source text-caption text-medium-emphasis mb-3"
                >
                  <div>{{ tm("dialogs.install.downloadSource") }}</div>
                  <div class="market-install-source__url">
                    {{ selectedInstallSourceUrl }}
                  </div>
                </div>

                <v-alert
                  v-if="installUsesGithubSource"
                  type="warning"
                  variant="tonal"
                  density="comfortable"
                  class="market-install-alert mb-4"
                >
                  {{ tm("dialogs.install.githubSecurityWarning") }}
                </v-alert>

                <ProxySelector
                  v-if="!selectedInstallDownloadUrl"
                ></ProxySelector>
              </div>
            </v-window-item>
          </v-window>
        </template>
      </div>

      <div class="v-card-actions">
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="closeInstallDialog">{{
          tm("buttons.cancel")
        }}</v-btn>
        <v-btn
          color="primary"
          variant="text"
          :loading="loading_"
          :disabled="loading_"
          @click="newExtension"
          >{{ tm("buttons.install") }}</v-btn
        >
      </div>
    </div>
  </v-dialog>

  <!-- 插件源管理对话框 -->
  <v-dialog v-model="showSourceManagerDialog" width="640">
    <v-card>
      <v-card-title class="text-h3 pa-4 pl-6">{{
        tm("market.sourceManagement")
      }}</v-card-title>
      <v-card-text>
        <v-select
          :model-value="selectedSource || '__default__'"
          @update:model-value="
            selectPluginSource($event === '__default__' ? null : $event)
          "
          :items="sourceSelectItems"
          :label="tm('market.currentSource')"
          variant="outlined"
          prepend-inner-icon="mdi-source-branch"
          hide-details
          class="mb-4"
        ></v-select>

        <div class="d-flex align-center justify-space-between mb-2">
          <div class="text-subtitle-2">{{ tm("market.availableSources") }}</div>
          <v-btn
            size="small"
            color="primary"
            variant="tonal"
            prepend-icon="mdi-plus"
            @click="addCustomSource"
          >
            {{ tm("market.addSource") }}
          </v-btn>
        </div>

        <v-list density="compact" nav class="pa-0">
          <v-list-item
            rounded="md"
            color="primary"
            :active="selectedSource === null"
            @click="selectPluginSource(null)"
          >
            <template v-slot:prepend>
              <v-icon
                icon="mdi-shield-check"
                size="small"
                class="mr-2"
              ></v-icon>
            </template>
            <v-list-item-title>{{
              tm("market.defaultSource")
            }}</v-list-item-title>
          </v-list-item>

          <v-list-item
            v-for="source in customSources"
            :key="source.url"
            rounded="md"
            color="primary"
            :active="selectedSource === source.url"
            @click="selectPluginSource(source.url)"
          >
            <template v-slot:prepend>
              <v-icon
                icon="mdi-link-variant"
                size="small"
                class="mr-2"
              ></v-icon>
            </template>
            <v-list-item-title>{{ source.name }}</v-list-item-title>
            <v-list-item-subtitle class="text-caption">{{
              source.url
            }}</v-list-item-subtitle>
            <template v-slot:append>
              <v-btn
                icon="mdi-pencil-outline"
                size="small"
                variant="text"
                color="medium-emphasis"
                @click.stop="editCustomSource(source)"
              ></v-btn>
              <v-btn
                icon="mdi-trash-can-outline"
                size="small"
                variant="text"
                color="error"
                @click.stop="removeCustomSource(source)"
              ></v-btn>
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn
          color="primary"
          variant="text"
          @click="showSourceManagerDialog = false"
          >{{ tm("buttons.close") }}</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 添加/编辑自定义插件源对话框 -->
  <v-dialog v-model="showSourceDialog" width="500">
    <v-card>
      <v-card-title class="text-h5">{{
        editingSource ? tm("market.editSource") : tm("market.addSource")
      }}</v-card-title>
      <v-card-text>
        <div class="pa-2">
          <v-text-field
            v-model="sourceName"
            :label="tm('market.sourceName')"
            variant="outlined"
            prepend-inner-icon="mdi-rename-box"
            hide-details
            class="mb-4"
            placeholder="我的插件源"
          ></v-text-field>

          <v-text-field
            v-model="sourceUrl"
            :label="tm('market.sourceUrl')"
            variant="outlined"
            prepend-inner-icon="mdi-link"
            hide-details
            placeholder="https://example.com/plugins.json"
          ></v-text-field>

          <div class="text-caption text-medium-emphasis mt-2">
            {{ tm("messages.enterJsonUrl") }}
          </div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="showSourceDialog = false">{{
          tm("buttons.cancel")
        }}</v-btn>
        <v-btn color="primary" variant="text" @click="saveCustomSource">{{
          tm("buttons.save")
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 删除插件源确认对话框 -->
  <v-dialog v-model="showRemoveSourceDialog" width="400">
    <v-card>
      <v-card-title class="text-h5 d-flex align-center">
        <v-icon color="warning" class="mr-2">mdi-alert-circle</v-icon>
        {{ tm("dialogs.uninstall.title") }}
      </v-card-title>
      <v-card-text>
        <div>{{ tm("market.confirmRemoveSource") }}</div>
        <div v-if="sourceToRemove" class="mt-2">
          <strong>{{ sourceToRemove.name }}</strong>
          <div class="text-caption">{{ sourceToRemove.url }}</div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn
          color="grey"
          variant="text"
          @click="showRemoveSourceDialog = false"
          >{{ tm("buttons.cancel") }}</v-btn
        >
        <v-btn color="error" variant="text" @click="confirmRemoveSource">{{
          tm("buttons.deleteSource")
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Update plugin confirmation dialog -->
  <v-dialog v-model="updateConfirmDialog.show" width="500">
    <v-card class="rounded-lg">
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ tm("dialogs.update.title") }}
      </v-card-title>
      <v-card-text>
        <div class="market-install-confirm">
          <div class="market-install-confirm__header">
            <img
              :src="updateDialogPluginLogo"
              :alt="updateDialogPluginName"
              class="market-install-confirm__logo"
            />
            <div class="market-install-confirm__meta">
              <div class="market-install-confirm__name">
                {{ updateDialogPluginName }}
              </div>
              <div
                v-if="updateDialogCurrentVersion || updateDialogTargetVersion"
                class="market-install-confirm__author"
              >
                <template v-if="updateDialogTargetVersion">
                  {{ updateDialogCurrentVersion || tm("status.unknown") }}
                  <v-icon icon="mdi-arrow-right" size="14" class="mx-1" />
                  {{ updateDialogTargetVersion }}
                </template>
                <template v-else>
                  {{ tm("detail.info.version") }}:
                  {{ updateDialogCurrentVersion || tm("status.unknown") }}
                </template>
              </div>
            </div>
          </div>

          <v-divider class="my-4" />

          <div
            v-if="selectedUpdateSourceUrl"
            class="market-install-confirm__section-title"
          >
            {{ tm("dialogs.update.sectionTitle") }}
          </div>
          <div
            v-if="selectedUpdateSourceUrl"
            class="market-install-source text-caption text-medium-emphasis mb-3"
          >
            <div>{{ tm("dialogs.update.downloadSource") }}</div>
            <div class="market-install-source__url">
              {{ selectedUpdateSourceUrl }}
            </div>
          </div>

          <v-alert
            v-if="updateUsesGithubSource"
            type="warning"
            variant="tonal"
            density="comfortable"
            class="market-install-alert mt-4 mb-4"
          >
            {{ tm("dialogs.install.githubSecurityWarning") }}
          </v-alert>

          <ProxySelector v-if="!selectedUpdateDownloadUrl" class="mt-4" />
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="closeUpdateConfirmDialog">
          {{ tm("buttons.cancel") }}
        </v-btn>
        <v-btn color="primary" variant="flat" @click="confirmUpdatePlugin">
          {{ tm("dialogs.update.confirm") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 强制更新确认对话框 -->
  <v-dialog v-model="forceUpdateDialog.show" max-width="420">
    <v-card class="rounded-lg">
      <v-card-title class="text-h6 d-flex align-center">
        <v-icon color="info" class="mr-2">mdi-information-outline</v-icon>
        {{ tm("dialogs.forceUpdate.title") }}
      </v-card-title>
      <v-card-text>
        {{ tm("dialogs.forceUpdate.message") }}
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="forceUpdateDialog.show = false">{{
          tm("buttons.cancel")
        }}</v-btn>
        <v-btn color="primary" variant="flat" @click="confirmForceUpdate">{{
          tm("dialogs.forceUpdate.confirm")
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 扩展页面对话框 -->
  <v-dialog v-model="extensionPageDialog.show" fullscreen>
    <v-card>
      <v-toolbar color="primary" dark>
        <v-btn icon @click="extensionPageDialog.show = false">
          <v-icon>mdi-close</v-icon>
        </v-btn>
        <v-toolbar-title>{{ extensionPageDialog.title }}</v-toolbar-title>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="extensionPageDialog.show = false">
          关闭
        </v-btn>
      </v-toolbar>
      <v-card-text style="padding: 0; height: calc(100vh - 64px);">
        <iframe
          :srcdoc="extensionPageDialog.html"
          style="width: 100%; height: 100%; border: none;"
          sandbox="allow-scripts allow-forms allow-same-origin"
        ></iframe>
      </v-card-text>
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

.fab-button {
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.fab-button:hover {
  transform: translateY(-4px) scale(1.05);
  box-shadow: 0 12px 20px rgba(var(--v-theme-primary), 0.4);
}

.extension-detail-width {
  margin: 0 auto;
  max-width: 1040px;
  width: 100%;
}

.market-install-confirm {
  padding: 8px;
}

.market-install-confirm__header {
  align-items: center;
  display: flex;
  gap: 16px;
}

.market-install-confirm__logo {
  border-radius: 14px;
  height: 64px;
  object-fit: cover;
  width: 64px;
}

.market-install-confirm__meta {
  min-width: 0;
}

.market-install-confirm__name {
  color: rgba(var(--v-theme-on-surface), 0.92);
  font-size: 1.25rem;
  font-weight: 700;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-install-confirm__author,
.market-install-confirm__desc {
  color: rgba(var(--v-theme-on-surface), 0.64);
  line-height: 1.55;
  font-size: 0.875rem;
}

.market-install-confirm__section-title {
  color: rgba(var(--v-theme-on-surface), 0.92);
  font-weight: 700;
  margin-bottom: 8px;
}

.market-install-alert {
  font-size: 0.8125rem;
  line-height: 1.45;
}

.market-install-source {
  min-width: 0;
}

.market-install-source__url {
  overflow-x: auto;
  white-space: nowrap;
}
</style>

<style>
.v-theme--PurpleThemeDark .extension-page .plugin-handler-item {
  background-color: rgb(var(--v-theme-mcpCardBg));
}
</style>
