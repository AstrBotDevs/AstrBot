import axios from "axios";
import { pinyin } from "pinyin-pro";
import { useCommonStore } from "@/stores/common";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import defaultPluginIcon from "@/assets/images/plugin_icon.png";
import { getPlatformDisplayName } from "@/utils/platformUtils";
import { ref, computed, onMounted, onUnmounted, reactive, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

export const useExtensionPage = () => {
  
  
  const commonStore = useCommonStore();
  const { t } = useI18n();
  const { tm } = useModuleI18n("features/extension");
  const router = useRouter();
  const route = useRoute();
  
  const getSelectedGitHubProxy = () => {
    if (typeof window === "undefined" || !window.localStorage) return "";
    return localStorage.getItem("githubProxyRadioValue") === "1"
      ? localStorage.getItem("selectedGitHubProxy") || ""
      : "";
  };
  
  // 检查指令冲突并提示
  const conflictDialog = reactive({
    show: false,
    count: 0,
  });
  const checkAndPromptConflicts = async () => {
    try {
      const res = await axios.get("/api/commands");
      if (res.data.status === "ok") {
        const conflicts = res.data.data.summary?.conflicts || 0;
        if (conflicts > 0) {
          conflictDialog.count = conflicts;
          conflictDialog.show = true;
        }
      }
    } catch (err) {
      console.debug("Failed to check command conflicts:", err);
    }
  };
  const handleConflictConfirm = () => {
    activeTab.value = "commands";
  };
  
  const fileInput = ref(null);
  const activeTab = ref("installed");
  const validTabs = ["installed", "market", "mcp", "skills", "components"];
  const isValidTab = (tab) => validTabs.includes(tab);
  const getLocationHash = () =>
    typeof window !== "undefined" ? window.location.hash : "";
  const extractTabFromHash = (hash) => {
    const lastHashIndex = (hash || "").lastIndexOf("#");
    if (lastHashIndex === -1) return "";
    return hash.slice(lastHashIndex + 1);
  };
  const syncTabFromHash = (hash) => {
    const tab = extractTabFromHash(hash);
    if (isValidTab(tab)) {
      activeTab.value = tab;
      return true;
    }
    return false;
  };
  const extension_data = reactive({
    data: [],
    message: "",
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
  const selectedMarketInstallPlugin = ref(null);
  const installCompat = reactive({
    checked: false,
    compatible: true,
    message: "",
  });
  
  // AstrBot 版本范围不兼容警告对话框
  const versionCompatibilityDialog = reactive({
    show: false,
    message: "",
  });
  
  // 卸载插件确认对话框（列表模式用）
  const showUninstallDialog = ref(false);
  const pluginToUninstall = ref(null);
  
  // 自定义插件源相关
  const showSourceDialog = ref(false);
  const showSourceManagerDialog = ref(false);
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
  const randomPluginNames = ref([]);
  
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
    { title: tm("table.headers.description"), key: "desc", width: "180px" },
    { title: tm("table.headers.version"), key: "version", width: "100px" },
    { title: tm("table.headers.author"), key: "author", width: "100px" },
    {
      title: tm("table.headers.actions"),
      key: "actions",
      sortable: false,
      width: "520px",
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
      const supportPlatforms = Array.isArray(plugin.support_platforms)
        ? plugin.support_platforms.join(" ").toLowerCase()
        : "";
      const astrbotVersion = (plugin.astrbot_version ?? "").toLowerCase();
      return (
        plugin.name?.toLowerCase().includes(search) ||
        plugin.desc?.toLowerCase().includes(search) ||
        plugin.author?.toLowerCase().includes(search) ||
        supportPlatforms.includes(search) ||
        astrbotVersion.includes(search)
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
  
  const RANDOM_PLUGINS_COUNT = 3;
  
  const randomPlugins = computed(() => {
    const allPlugins = pluginMarketData.value;
    if (allPlugins.length === 0) return [];
  
    const pluginsByName = new Map(allPlugins.map((plugin) => [plugin.name, plugin]));
    const selected = randomPluginNames.value
      .map((name) => pluginsByName.get(name))
      .filter(Boolean);
  
    if (selected.length > 0) {
      return selected;
    }
  
    return allPlugins.slice(0, Math.min(RANDOM_PLUGINS_COUNT, allPlugins.length));
  });
  
  const shufflePlugins = (plugins) => {
    const shuffled = [...plugins];
    for (let i = shuffled.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
  };
  
  const refreshRandomPlugins = () => {
    const shuffled = shufflePlugins(pluginMarketData.value);
    randomPluginNames.value = shuffled
      .slice(0, Math.min(RANDOM_PLUGINS_COUNT, shuffled.length))
      .map((plugin) => plugin.name);
  };
  
  // 分页计算属性
  const displayItemsPerPage = 9; // 固定每页显示9个卡片（3行）
  
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
  
  const failedPluginsDict = ref({});
  
  const getExtensions = async () => {
    loading_.value = true;
    try {
      const res = await axios.get("/api/plugin/get");   
      Object.assign(extension_data, res.data);
      
      const failRes = await axios.get("/api/plugin/source/get-failed-plugins");    
      failedPluginsDict.value = failRes.data.data || {};
      
      checkUpdate();
    } catch (err) {
      toast(err, "error");
    } finally {
      loading_.value = false;
    }
  };
  
  const handleReloadAllFailed = async () => {
      const dirNames = Object.keys(failedPluginsDict.value);
      if (dirNames.length === 0) {
          toast("没有需要重载的失败插件", "info");
          return;
      }
  
      loading_.value = true;
      try {
          const promises = dirNames.map(dir => 
              axios.post("/api/plugin/reload-failed", { dir_name: dir })
          );
          await Promise.all(promises);
          
          toast("已尝试重载所有失败插件", "success");
          
          // 清空 message 关闭对话框
          extension_data.message = "";
          
          // 刷新列表
          await getExtensions();
          
      } catch (e) {
          console.error("重载失败:", e);
          toast("批量重载过程中出现错误", "error");
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
      await getExtensions();
      if (res.data.status === "error") {
        toast(res.data.message, "error");
        return;
      }
      toast(tm("messages.reloadSuccess"), "success");
      //getExtensions();
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
  
  // 为表格视图创建一个处理安装插件的函数
  const handleInstallPlugin = async (plugin) => {
    if (plugin.tags && plugin.tags.includes("danger")) {
      selectedDangerPlugin.value = plugin;
      dangerConfirmDialog.value = true;
    } else {
      selectedMarketInstallPlugin.value = plugin;
      extension_url.value = plugin.repo;
      dialog.value = true;
      uploadTab.value = "url";
    }
  };
  
  // 确认安装危险插件
  const confirmDangerInstall = () => {
    if (selectedDangerPlugin.value) {
      selectedMarketInstallPlugin.value = selectedDangerPlugin.value;
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
    showSourceManagerDialog.value = false;
    editingSource.value = false;
    originalSourceUrl.value = "";
    sourceName.value = "";
    sourceUrl.value = "";
    showSourceDialog.value = true;
  };
  
  const openSourceManagerDialog = async () => {
    await loadCustomSources();
    showSourceManagerDialog.value = true;
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
  
  const sourceSelectItems = computed(() => [
    { title: tm("market.defaultSource"), value: "__default__" },
    ...customSources.value.map((source) => ({
      title: source.name,
      value: source.url,
    })),
  ]);
  
  const editCustomSource = (source) => {
    if (!source) return;
    showSourceManagerDialog.value = false;
    editingSource.value = true;
    originalSourceUrl.value = source.url;
    sourceName.value = source.name;
    sourceUrl.value = source.url;
    showSourceDialog.value = true;
  };
  
  const removeCustomSource = (source) => {
    if (!source) return;
    showSourceManagerDialog.value = false;
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
    const installedByRepo = new Map(
      data
        .filter((ext) => ext.repo)
        .map((ext) => [ext.repo.toLowerCase(), ext]),
    );
    const installedByName = new Map(data.map((ext) => [ext.name, ext]));
  
    for (let i = 0; i < pluginMarketData.value.length; i++) {
      const plugin = pluginMarketData.value[i];
      const matchedInstalled =
        (plugin.repo && installedByRepo.get(plugin.repo.toLowerCase())) ||
        installedByName.get(plugin.name);
  
      // 兜底：市场源未提供字段时，回填本地已安装插件中的元数据，便于在市场页直接展示
      if (matchedInstalled) {
        if (
          (!Array.isArray(plugin.support_platforms) ||
            plugin.support_platforms.length === 0) &&
          Array.isArray(matchedInstalled.support_platforms)
        ) {
          plugin.support_platforms = matchedInstalled.support_platforms;
        }
        if (!plugin.astrbot_version && matchedInstalled.astrbot_version) {
          plugin.astrbot_version = matchedInstalled.astrbot_version;
        }
      }
  
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
  
  const showVersionCompatibilityWarning = (message) => {
    versionCompatibilityDialog.message = message;
    versionCompatibilityDialog.show = true;
  };
  
  const continueInstallIgnoringVersionWarning = async () => {
    versionCompatibilityDialog.show = false;
    await newExtension(true);
  };
  
  const cancelInstallOnVersionWarning = () => {
    versionCompatibilityDialog.show = false;
  };
  
  const newExtension = async (ignoreVersionCheck = false) => {
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
      formData.append("ignore_version_check", String(ignoreVersionCheck));
      axios
        .post("/api/plugin/install-upload", formData, {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        })
        .then(async (res) => {
          loading_.value = false;
          if (
            res.data.status === "warning" &&
            res.data.data?.warning_type === "astrbot_version_incompatible"
          ) {
            onLoadingDialogResult(2, res.data.message, -1);
            showVersionCompatibilityWarning(res.data.message);
            return;
          }
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
          ignore_version_check: ignoreVersionCheck,
        })
        .then(async (res) => {
          loading_.value = false;
          if (
            res.data.status === "warning" &&
            res.data.data?.warning_type === "astrbot_version_incompatible"
          ) {
            onLoadingDialogResult(2, res.data.message, -1);
            showVersionCompatibilityWarning(res.data.message);
            return;
          }
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
  
  const normalizePlatformList = (platforms) => {
    if (!Array.isArray(platforms)) return [];
    return platforms.filter((item) => typeof item === "string");
  };
  
  const getPlatformDisplayList = (platforms) => {
    return normalizePlatformList(platforms).map((platformId) =>
      getPlatformDisplayName(platformId),
    );
  };
  
  const resolveSelectedInstallPlugin = () => {
    if (
      selectedMarketInstallPlugin.value &&
      selectedMarketInstallPlugin.value.repo === extension_url.value
    ) {
      return selectedMarketInstallPlugin.value;
    }
    return pluginMarketData.value.find((plugin) => plugin.repo === extension_url.value) || null;
  };
  
  const selectedInstallPlugin = computed(() => resolveSelectedInstallPlugin());
  
  const checkInstallCompatibility = async () => {
    installCompat.checked = false;
    installCompat.compatible = true;
    installCompat.message = "";
  
    const plugin = selectedInstallPlugin.value;
    if (!plugin?.astrbot_version || uploadTab.value !== "url") {
      return;
    }
  
    try {
      const res = await axios.post("/api/plugin/check-compat", {
        astrbot_version: plugin.astrbot_version,
      });
      if (res.data.status === "ok") {
        installCompat.checked = true;
        installCompat.compatible = !!res.data.data?.compatible;
        installCompat.message = res.data.data?.message || "";
      }
    } catch (err) {
      console.debug("Failed to check plugin compatibility:", err);
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
      refreshRandomPlugins();
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
      refreshRandomPlugins();
    } catch (err) {
      toast(tm("messages.getMarketDataFailed") + " " + err, "error");
    }
  });
  
  // 处理语言切换事件，重新加载插件配置以获取插件的 i18n 数据
  const handleLocaleChange = () => {
    // 如果配置对话框是打开的，重新加载当前插件的配置
    if (configDialog.value && currentConfigPlugin.value) {
      openExtensionConfig(currentConfigPlugin.value);
    }
  };
  
  // 监听语言切换事件
  window.addEventListener("astrbot-locale-changed", handleLocaleChange);
  
  // 清理事件监听器
  onUnmounted(() => {
    window.removeEventListener("astrbot-locale-changed", handleLocaleChange);
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
    [() => dialog.value, () => extension_url.value, () => uploadTab.value],
    async ([dialogOpen, _, currentUploadTab]) => {
      if (!dialogOpen || currentUploadTab !== "url") {
        installCompat.checked = false;
        installCompat.compatible = true;
        installCompat.message = "";
        return;
      }
      await checkInstallCompatibility();
    },
  );
  
  watch(
    () => route.fullPath,
    () => {
      const tab = extractTabFromHash(getLocationHash());
      if (isValidTab(tab) && tab !== activeTab.value) {
        activeTab.value = tab;
      }
    },
  );
  
  watch(activeTab, (newTab) => {
    if (!isValidTab(newTab)) return;
    const currentTab = extractTabFromHash(getLocationHash());
    if (currentTab === newTab) return;
    const hash = getLocationHash();
    const lastHashIndex = hash.lastIndexOf("#");
    const nextHash =
      lastHashIndex > 0 ? `${hash.slice(0, lastHashIndex)}#${newTab}` : `#${newTab}`;
    if (typeof window !== "undefined") {
      window.location.hash = nextHash;
    }
  });

  return {
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
    getInitialShowReserved,
    showReserved,
    snack_message,
    snack_show,
    snack_success,
    configDialog,
    extension_config,
    pluginMarketData,
    loadingDialog,
    showPluginInfoDialog,
    selectedPlugin,
    curr_namespace,
    updatingAll,
    readmeDialog,
    forceUpdateDialog,
    updateAllConfirmDialog,
    changelogDialog,
    getInitialListViewMode,
    isListView,
    pluginSearch,
    loading_,
    currentPage,
    dangerConfirmDialog,
    selectedDangerPlugin,
    selectedMarketInstallPlugin,
    installCompat,
    versionCompatibilityDialog,
    showUninstallDialog,
    pluginToUninstall,
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
    marketCustomFilter,
    plugin_handler_info_headers,
    pluginHeaders,
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
    toggleShowReserved,
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
    checkInstallCompatibility,
    refreshPluginMarket,
    handleLocaleChange,
    searchDebounceTimer,
  };
};
