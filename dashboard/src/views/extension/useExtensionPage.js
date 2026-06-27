import { commandApi, pluginApi } from "@/api/v1";
import { pluginSidebarState } from "@/composables/usePluginSidebarItems";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { useCommonStore } from "@/stores/common";
import { resolveErrorMessage } from "@/utils/errorUtils";
import { getValidHashTab, replaceTabRoute } from "@/utils/hashRouteTabs.mjs";
import { getPlatformDisplayName } from "@/utils/platformUtils";
import {
  buildSearchQuery,
  matchesPluginSearch,
  normalizeStr,
  toInitials,
  toPinyinText,
} from "@/utils/pluginSearch";
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

const buildFailedPluginItems = (raw) => {
  return Object.entries(raw || {}).map(([dirName, info]) => {
    const detail = info && typeof info === "object" ? info : {};
    return {
      ...detail,
      dir_name: dirName,
      name: detail.name || dirName,
      display_name: detail.display_name || detail.name || dirName,
      error: detail.error || "",
      traceback: detail.traceback || "",
      reserved: !!detail.reserved,
    };
  });
};

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
      const res = await commandApi.list();
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
  const getLocationHash = () => route.hash || "";
  const extractTabFromHash = (hash) => getValidHashTab(hash, validTabs);
  const syncTabFromHash = (hash) => {
    const tab = extractTabFromHash(hash);
    if (tab) {
      activeTab.value = tab;
      return true;
    }
    return false;
  };
  const extension_data = reactive({
    data: [],
    message: "",
  });

  const snack_message = ref("");
  const snack_show = ref(false);
  const snack_success = ref("success");
  const configDialog = ref(false);
  const extension_config = reactive({
    metadata: {},
    config: {},
    i18n: {},
  });
  const pluginMarketData = ref([]);
  const loadingDialog = reactive({
    show: false,
    title: "",
    statusCode: 0, // 0: loading, 1: success, 2: error,
    result: "",
  });
  const curr_namespace = ref("");
  const currentConfigPlugin = ref("");
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

  const updateConfirmDialog = reactive({
    show: false,
    extensionName: "",
    forceUpdate: false,
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

  const pluginSearch = ref("");
  const loading_ = ref(false);

  // 分页相关
  const currentPage = ref(1);

  // 危险插件确认对话框
  const dangerConfirmDialog = ref(false);
  const selectedDangerPlugin = ref(null);
  const selectedMarketInstallPlugin = ref(null);
  const installSupport = reactive({
    checked: false,
    supported: true,
    message: "",
  });

  // AstrBot 版本范围不兼容警告对话框
  const versionSupportDialog = reactive({
    show: false,
    message: "",
  });

  // 卸载插件确认对话框（列表模式用）
  const showUninstallDialog = ref(false);
  const uninstallTarget = ref(null);

  // 自定义插件源相关
  const showSourceDialog = ref(false);
  const showSourceManagerDialog = ref(false);
  const sourceName = ref("");
  const sourceUrl = ref("");
  const sourceResolving = ref(false);
  const sourceResolvedUrl = ref("");
  const sourceResolveVisible = ref(false);
  const sourceMarketMeta = ref(null);
  const customSources = ref([]);
  const selectedSource = ref(null);
  const showRemoveSourceDialog = ref(false);
  const sourceToRemove = ref(null);
  const editingSource = ref(false);
  const originalSourceUrl = ref("");
  const sourceBindingDialog = reactive({
    show: false,
    loading: false,
    saving: false,
    extension: null,
    candidates: [],
    selectedKey: "",
  });

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
  const marketCategoryFilter = ref("all");

  // 插件市场拼音搜索

  const normalizeMarketCategory = (rawCategory) => {
    const normalized = String(rawCategory || "")
      .trim()
      .toLowerCase();
    if (!normalized) {
      return "other";
    }
    return normalized.replace(/[\s-]+/g, "_");
  };

  const getMarketCategoryLabel = (key, rawCategory = "") => {
    const fallbackMap = {
      all: "All",
      ai_tools: "AI Tools",
      entertainment: "Entertainment",
      productivity: "Productivity",
      integrations: "Integrations",
      utilities: "Utilities",
      other: "Other",
    };
    const i18nKey = `market.categories.${key}`;
    const translated = tm(i18nKey);
    if (translated && !translated.includes("[MISSING:")) {
      return translated;
    }
    if (fallbackMap[key]) {
      return fallbackMap[key];
    }
    const normalizedRaw = String(rawCategory || "").trim();
    if (normalizedRaw) {
      return normalizedRaw;
    }
    return key
      .split(/[_-]+/)
      .filter(Boolean)
      .map((part) => part[0].toUpperCase() + part.slice(1))
      .join(" ");
  };

  const marketCategoryMeta = computed(() => {
    const categories = new Map();

    for (const plugin of pluginMarketData.value) {
      const categoryKey = normalizeMarketCategory(plugin?.category);
      const categoryData = categories.get(categoryKey);
      if (categoryData) {
        categoryData.count += 1;
        continue;
      }
      categories.set(categoryKey, {
        count: 1,
        rawLabel: String(plugin?.category || "").trim(),
      });
    }

    return categories;
  });

  const marketCategoryCounts = computed(() => {
    const counts = { all: pluginMarketData.value.length };
    for (const [
      categoryKey,
      categoryData,
    ] of marketCategoryMeta.value.entries()) {
      counts[categoryKey] = categoryData.count;
    }
    return counts;
  });

  const marketCategoryItems = computed(() => {
    const items = [
      {
        value: "all",
        label: getMarketCategoryLabel("all"),
        count: marketCategoryCounts.value.all || 0,
      },
    ];

    for (const [
      categoryKey,
      categoryData,
    ] of marketCategoryMeta.value.entries()) {
      items.push({
        value: categoryKey,
        label: getMarketCategoryLabel(categoryKey, categoryData.rawLabel),
        count: categoryData.count,
      });
    }

    return items;
  });

  // 过滤要显示的插件
  const filteredExtensions = computed(() => {
    const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
    return data;
  });

  const compareInstalledPluginNames = (left, right) =>
    normalizeStr(left?.name ?? "").localeCompare(
      normalizeStr(right?.name ?? ""),
      undefined,
      {
        sensitivity: "base",
      },
    );

  const compareInstalledFallback = (left, right) => {
    const reservedDiff =
      Number(!!left.plugin?.reserved) - Number(!!right.plugin?.reserved);
    if (reservedDiff !== 0) {
      return reservedDiff;
    }

    const nameCompare = compareInstalledPluginNames(left.plugin, right.plugin);
    return nameCompare !== 0 ? nameCompare : left.index - right.index;
  };

  const sortInstalledPlugins = (plugins) => {
    return plugins
      .map((plugin, index) => ({
        plugin,
        index,
      }))
      .sort(compareInstalledFallback)
      .map((item) => item.plugin);
  };

  // 通过搜索过滤插件
  const filteredPlugins = computed(() => {
    const query = buildSearchQuery(pluginSearch.value);
    const filtered = query
      ? filteredExtensions.value.filter((plugin) =>
          matchesPluginSearch(plugin, query),
        )
      : filteredExtensions.value;

    return sortInstalledPlugins(filtered);
  });

  // 过滤后的插件市场数据（带搜索）
  const filteredMarketPlugins = computed(() => {
    const query = buildSearchQuery(debouncedMarketSearch.value);
    const targetCategory = normalizeMarketCategory(marketCategoryFilter.value);
    const shouldFilterByCategory = marketCategoryFilter.value !== "all";
    if (!query) {
      if (!shouldFilterByCategory) {
        return pluginMarketData.value;
      }
      return pluginMarketData.value.filter(
        (plugin) =>
          normalizeMarketCategory(plugin?.category) === targetCategory,
      );
    }

    return pluginMarketData.value.filter((plugin) => {
      const matchesSearch = matchesPluginSearch(plugin, query);
      const matchesCategory = shouldFilterByCategory
        ? normalizeMarketCategory(plugin?.category) === targetCategory
        : true;
      return matchesSearch && matchesCategory;
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

    const pluginsByName = new Map(
      allPlugins.map((plugin) => [plugin.name, plugin]),
    );
    const selected = randomPluginNames.value
      .map((name) => pluginsByName.get(name))
      .filter(Boolean);

    if (selected.length > 0) {
      return selected;
    }

    return allPlugins.slice(
      0,
      Math.min(RANDOM_PLUGINS_COUNT, allPlugins.length),
    );
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
  const failedPluginItems = computed(() =>
    buildFailedPluginItems(failedPluginsDict.value),
  );

  const getExtensions = async ({ withLoading = true } = {}) => {
    if (withLoading) {
      loading_.value = true;
    }
    try {
      const res = await pluginApi.list();
      Object.assign(extension_data, res.data);

      // 同步插件数据到侧边栏共享状态
      pluginSidebarState.plugins = res.data?.data || [];

      const failRes = await pluginApi.failed();
      failedPluginsDict.value = failRes.data.data || {};

      if (pluginMarketData.value.length > 0) {
        await checkUpdate();
      }
    } catch (err) {
      toast(err, "error");
    } finally {
      if (withLoading) {
        loading_.value = false;
      }
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
      const promises = dirNames.map((dir) => pluginApi.reloadFailed(dir));
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

  const reloadFailedPlugin = async (dirName) => {
    if (!dirName) return;

    try {
      const res = await pluginApi.reloadFailed(dirName);
      if (res.data.status === "error") {
        toast(res.data.message || tm("messages.reloadFailed"), "error");
        return;
      }
      toast(res.data.message || tm("messages.reloadSuccess"), "success");
      await getExtensions();
    } catch (err) {
      toast(resolveErrorMessage(err, tm("messages.reloadFailed")), "error");
    }
  };

  const requestUninstall = (target) => {
    if (!target?.id || !target?.kind) return;
    uninstallTarget.value = target;
    showUninstallDialog.value = true;
  };

  const uninstall = async (
    target,
    { deleteConfig = false, deleteData = false, skipConfirm = false } = {},
  ) => {
    if (!target?.id || !target?.kind) return;

    if (!skipConfirm) {
      requestUninstall(target);
      return;
    }

    const isFailed = target.kind === "failed";
    const options = {
      delete_config: deleteConfig,
      delete_data: deleteData,
    };

    toast(`${tm("messages.uninstalling")} ${target.id}`, "primary");

    try {
      const res = isFailed
        ? await pluginApi.uninstallFailed(target.id, options)
        : await pluginApi.uninstall(target.id, options);
      if (res.data.status === "error") {
        toast(res.data.message, "error");
        return;
      }
      if (!isFailed) {
        Object.assign(extension_data, res.data);
      }
      toast(res.data.message, "success");
      await getExtensions();
    } catch (err) {
      toast(resolveErrorMessage(err, tm("messages.operationFailed")), "error");
    }
  };

  const requestUninstallPlugin = (name) => {
    if (!name) return;
    uninstall({ kind: "normal", id: name }, { skipConfirm: false });
  };

  const requestUninstallFailedPlugin = (dirName) => {
    if (!dirName) return;
    uninstall({ kind: "failed", id: dirName }, { skipConfirm: false });
  };

  const normalizeInstallUrl = (value) =>
    String(value || "")
      .trim()
      .replace(/\/+$/, "");

  const isGithubRepoUrl = (value) =>
    /^https:\/\/github\.com\/[^/\s]+\/[^/\s]+(?:\.git)?(?:\/tree\/[^/\s]+)?$/i.test(
      normalizeInstallUrl(value),
    );

  const normalizeRegistryUrl = (value) =>
    String(value || "")
      .trim()
      .replace(/\/+$/, "");

  const getMarketPluginId = (plugin) => {
    return String(plugin?.market_plugin_id || "").trim();
  };

  const getMarketInstallSourcePayload = () => {
    const plugin = selectedMarketInstallPlugin.value;
    if (
      !plugin ||
      normalizeInstallUrl(plugin.repo) !==
        normalizeInstallUrl(extension_url.value)
    ) {
      return {};
    }

    return {
      install_method: "market",
      registry_url: selectedSource.value || null,
      market_plugin_id: getMarketPluginId(plugin),
    };
  };

  const getInstalledExtensionByName = (extensionName) => {
    const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
    return data.find((extension) => extension.name === extensionName) || null;
  };

  const findMarketPluginForExtension = (extension) => {
    if (!extension) return null;
    if (extension.update_market_plugin) {
      return extension.update_market_plugin;
    }
    const repo = normalizeInstallUrl(extension.repo).toLowerCase();

    if (repo) {
      return (
        pluginMarketData.value.find(
          (plugin) => normalizeInstallUrl(plugin?.repo).toLowerCase() === repo,
        ) || null
      );
    }

    return (
      pluginMarketData.value.find((plugin) => plugin.name === extension.name) ||
      null
    );
  };

  const getUpdateDownloadUrl = (extension) =>
    String(findMarketPluginForExtension(extension)?.download_url || "").trim();

  const buildMarketPluginLookup = (plugins) => {
    const byIdentifier = new Map();
    const byRepo = new Map();
    const byName = new Map();

    plugins.forEach((plugin) => {
      const identifier = getMarketPluginId(plugin);
      if (identifier) {
        byIdentifier.set(identifier, plugin);
      }
      if (plugin.repo) {
        byRepo.set(normalizeInstallUrl(plugin.repo).toLowerCase(), plugin);
      }
      byName.set(normalizeStr(plugin.name), plugin);
    });

    return { byIdentifier, byRepo, byName };
  };

  const checkUpdate = async () => {
    const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
    const sourcePlugins = new Map();

    data.forEach((extension) => {
      extension.online_version = "";
      extension.has_update = false;
      extension.update_market_plugin = null;

      const source = extension.install_source;
      if (
        !extension.updates_enabled ||
        !source ||
        source.install_method !== "market"
      ) {
        return;
      }

      const registryUrl = normalizeRegistryUrl(source.registry_url);
      if (!sourcePlugins.has(registryUrl)) {
        sourcePlugins.set(registryUrl, []);
      }
      sourcePlugins.get(registryUrl).push(extension);
    });

    await Promise.all(
      [...sourcePlugins.entries()].map(async ([registryUrl, extensions]) => {
        let marketPlugins = [];
        try {
          marketPlugins =
            registryUrl === normalizeRegistryUrl(selectedSource.value)
              ? pluginMarketData.value
              : await commonStore.getPluginCollections(
                  false,
                  registryUrl || null,
                );
        } catch (error) {
          console.warn("Failed to load plugin source for update check:", error);
          return;
        }

        const lookup = buildMarketPluginLookup(marketPlugins);
        extensions.forEach((extension) => {
          const source = extension.install_source || {};
          const sourceIdentifier = String(source.market_plugin_id || "").trim();
          const sourceRepo = normalizeInstallUrl(source.repo).toLowerCase();
          const normalizedExtensionName = normalizeStr(
            extension.marketplace_name,
          );
          const matchedPlugin =
            (sourceIdentifier && lookup.byIdentifier.get(sourceIdentifier)) ||
            (sourceRepo && lookup.byRepo.get(sourceRepo)) ||
            lookup.byName.get(normalizedExtensionName);

          if (!matchedPlugin) {
            return;
          }

          extension.update_market_plugin = matchedPlugin;
          const localVersion = String(extension.version || "").trim();
          const onlineVersion = String(matchedPlugin.version || "").trim();
          const isKnownVersion =
            /^v?\d+/.test(localVersion) &&
            /^v?\d+/.test(onlineVersion) &&
            onlineVersion !== tm("status.unknown");
          const versionCompare = isKnownVersion
            ? compareVersions(localVersion, onlineVersion)
            : 0;

          extension.online_version = onlineVersion;
          extension.has_update =
            isKnownVersion &&
            (versionCompare < 0 ||
              (versionCompare === 0 &&
                localVersion.includes("-") &&
                !onlineVersion.includes("-")));
        });
      }),
    );
  };

  const uninstallExtension = async (
    extensionName,
    optionsOrSkipConfirm = false,
  ) => {
    if (!extensionName) return;

    if (typeof optionsOrSkipConfirm === "boolean") {
      return uninstall(
        { kind: "normal", id: extensionName },
        { skipConfirm: optionsOrSkipConfirm },
      );
    }

    return uninstall(
      { kind: "normal", id: extensionName },
      { ...(optionsOrSkipConfirm || {}), skipConfirm: true },
    );
  };

  // 处理卸载确认对话框的确认事件
  const handleUninstallConfirm = async (options) => {
    const target = uninstallTarget.value;
    if (!target) return;

    try {
      await uninstall(target, { ...(options || {}), skipConfirm: true });
    } finally {
      uninstallTarget.value = null;
      showUninstallDialog.value = false;
    }
  };

  const openUpdateConfirmDialog = (extensionName, forceUpdate = false) => {
    updateConfirmDialog.extensionName = extensionName;
    updateConfirmDialog.forceUpdate = forceUpdate;
    updateConfirmDialog.show = true;
  };

  const closeUpdateConfirmDialog = () => {
    updateConfirmDialog.show = false;
    updateConfirmDialog.extensionName = "";
    updateConfirmDialog.forceUpdate = false;
  };

  const updateExtension = async (extension_name, forceUpdate = false) => {
    const ext = getInstalledExtensionByName(extension_name);
    if (ext && ext.updates_enabled === false) {
      toast(
        ext.update_disabled_reason || tm("messages.updateDisabled"),
        "info",
      );
      return;
    }

    // 如果没有检测到更新且不是强制更新，则弹窗确认
    if (!ext?.has_update && !forceUpdate) {
      forceUpdateDialog.extensionName = extension_name;
      forceUpdateDialog.show = true;
      return;
    }

    openUpdateConfirmDialog(extension_name, forceUpdate);
  };

  const confirmUpdatePlugin = async () => {
    const extensionName = updateConfirmDialog.extensionName;
    const ext = getInstalledExtensionByName(extensionName);
    if (!extensionName || !ext) {
      closeUpdateConfirmDialog();
      return;
    }

    closeUpdateConfirmDialog();
    loadingDialog.title = tm("status.loading");
    loadingDialog.statusCode = 0;
    loadingDialog.result = "";
    loadingDialog.show = true;
    try {
      const res = await pluginApi.update(extensionName, {
        proxy: getUpdateDownloadUrl(ext) ? "" : getSelectedGitHubProxy(),
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
            name: extensionName,
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
    if (updatableExtensions.value.length === 0) {
      toast(tm("messages.noUpdatesAvailable"), "info");
      return;
    }
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
    openUpdateConfirmDialog(name, true);
  };

  const updateAllExtensions = async () => {
    if (updatingAll.value) return;
    if (updatableExtensions.value.length === 0) {
      toast(tm("messages.noUpdatesAvailable"), "info");
      return;
    }
    updatingAll.value = true;
    loadingDialog.title = tm("status.loading");
    loadingDialog.statusCode = 0;
    loadingDialog.result = "";
    loadingDialog.show = true;

    const targets = updatableExtensions.value.map((ext) => ext.name);
    try {
      const res = await pluginApi.updateMany({
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
        const detail = failures
          .map((f) => `${f.name}: ${f.message}`)
          .join("\n");
        onLoadingDialogResult(2, `${failureText}\n${detail}`, -1);
      }
    } catch (err) {
      const errorMsg =
        err.response?.data?.message || err.message || String(err);
      onLoadingDialogResult(2, errorMsg, -1);
    } finally {
      updatingAll.value = false;
    }
  };

  const pluginOn = async (extension) => {
    try {
      const res = await pluginApi.setEnabled(extension.name, true);
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
      const res = await pluginApi.setEnabled(extension.name, false);
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
    currentConfigPlugin.value = extension_name;
    configDialog.value = true;
    try {
      const res = await pluginApi.config(extension_name);
      extension_config.metadata = res.data.data.metadata;
      extension_config.config = res.data.data.config;
      extension_config.i18n = res.data.data.i18n || {};
    } catch (err) {
      toast(err, "error");
    }
  };

  const updateConfig = async () => {
    try {
      const res = await pluginApi.updateConfig(
        curr_namespace.value,
        extension_config.config,
      );
      if (res.data.status === "ok") {
        toast(res.data.message, "success");
      } else {
        toast(res.data.message, "error");
      }
      configDialog.value = false;
      currentConfigPlugin.value = "";
      extension_config.metadata = {};
      extension_config.config = {};
      extension_config.i18n = {};
      getExtensions();
    } catch (err) {
      toast(err, "error");
    }
  };

  const showPluginInfo = (plugin) => {
    if (!plugin?.name) return;
    router.push({
      name: "ExtensionDetails",
      params: { pluginId: plugin.name },
      hash: "#plugin-components",
    });
  };

  const reloadPlugin = async (plugin_name) => {
    try {
      const res = await pluginApi.reload(plugin_name);
      if (res.data.status === "error") {
        toast(res.data.message || tm("messages.reloadFailed"), "error");
        return;
      }
      toast(tm("messages.reloadSuccess"), "success");
      await getExtensions();
    } catch (err) {
      toast(resolveErrorMessage(err, tm("messages.reloadFailed")), "error");
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

  const resetInstallDialogState = () => {
    selectedMarketInstallPlugin.value = null;
    extension_url.value = "";
    upload_file.value = null;
    uploadTab.value = "file";
    installSupport.checked = false;
    installSupport.supported = true;
    installSupport.message = "";
  };

  const openInstallDialog = () => {
    resetInstallDialogState();
    dialog.value = true;
  };

  const closeInstallDialog = () => {
    dialog.value = false;
    resetInstallDialogState();
  };

  const selectedInstallDownloadUrl = computed(() => {
    const plugin = selectedMarketInstallPlugin.value;
    const downloadUrl = String(plugin?.download_url || "").trim();
    if (!downloadUrl) return "";
    if (
      normalizeInstallUrl(plugin?.repo) !==
      normalizeInstallUrl(extension_url.value)
    ) {
      return "";
    }
    return downloadUrl;
  });

  const selectedInstallSourceUrl = computed(
    () =>
      selectedInstallDownloadUrl.value ||
      String(extension_url.value || "").trim(),
  );

  const installUsesGithubSource = computed(
    () =>
      !selectedInstallDownloadUrl.value && isGithubRepoUrl(extension_url.value),
  );

  // 为表格视图创建一个处理安装插件的函数
  const handleInstallPlugin = async (plugin) => {
    if (plugin.tags && plugin.tags.includes("danger")) {
      selectedDangerPlugin.value = plugin;
      dangerConfirmDialog.value = true;
    } else {
      selectedMarketInstallPlugin.value = plugin;
      extension_url.value = plugin.repo;
      upload_file.value = null;
      dialog.value = true;
      uploadTab.value = "url";
    }
  };

  // 确认安装危险插件
  const confirmDangerInstall = () => {
    if (selectedDangerPlugin.value) {
      selectedMarketInstallPlugin.value = selectedDangerPlugin.value;
      extension_url.value = selectedDangerPlugin.value.repo;
      upload_file.value = null;
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
      const res = await pluginApi.sources();
      if (res.data.status === "ok") {
        customSources.value = res.data.data?.sources || res.data.data || [];
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
      const res = await pluginApi.replaceSources(customSources.value);
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
    sourceResolvedUrl.value = "";
    sourceResolveVisible.value = false;
    sourceMarketMeta.value = null;
    sourceResolving.value = false;
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

  const sourceResolveCurrent = computed(
    () =>
      Boolean(sourceResolvedUrl.value) &&
      normalizeRegistryUrl(sourceResolvedUrl.value) ===
        normalizeRegistryUrl(sourceUrl.value),
  );

  const openPluginSourceBindingDialog = async (extension) => {
    if (!extension) return;
    sourceBindingDialog.show = true;
    sourceBindingDialog.loading = true;
    sourceBindingDialog.saving = false;
    sourceBindingDialog.extension = extension;
    sourceBindingDialog.candidates = [];
    sourceBindingDialog.selectedKey = "";

    const extensionRepo = normalizeInstallUrl(
      extension.repo || extension.install_source?.repo,
    ).toLowerCase();
    if (!extensionRepo) {
      sourceBindingDialog.loading = false;
      return;
    }

    try {
      await loadCustomSources();
      const sources = [
        { name: tm("market.defaultSource"), url: null },
        ...customSources.value.map((source) => ({
          name: source.name,
          url: source.url,
        })),
      ];
      const currentMarketPluginId = String(
        extension.install_source?.market_plugin_id || "",
      ).trim();
      const currentRegistryUrl = normalizeRegistryUrl(
        extension.install_source?.registry_url,
      );
      const seen = new Set();
      const candidates = [];

      for (const source of sources) {
        let marketPlugins = [];
        try {
          marketPlugins = await commonStore.getPluginCollections(
            false,
            source.url || null,
          );
        } catch (error) {
          console.warn("Failed to load plugin source for binding:", error);
          continue;
        }

        marketPlugins.forEach((plugin) => {
          const marketPluginId = getMarketPluginId(plugin);
          const pluginRepo = normalizeInstallUrl(plugin.repo).toLowerCase();
          if (!marketPluginId || !pluginRepo || pluginRepo !== extensionRepo) {
            return;
          }
          if (
            currentMarketPluginId &&
            marketPluginId !== currentMarketPluginId
          ) {
            return;
          }

          const registryUrl = normalizeRegistryUrl(source.url);
          const key = `${registryUrl}|${marketPluginId}|${pluginRepo}`;
          if (seen.has(key)) {
            return;
          }
          seen.add(key);
          candidates.push({
            key,
            registry_url: registryUrl || null,
            registry_name: source.name,
            market_plugin_id: marketPluginId,
            repo: plugin.repo,
            download_url: plugin.download_url || "",
            version: plugin.version || tm("status.unknown"),
          });
        });
      }

      const currentCandidate = candidates.find((candidate) => {
        return (
          normalizeRegistryUrl(candidate.registry_url) === currentRegistryUrl &&
          (!currentMarketPluginId ||
            candidate.market_plugin_id === currentMarketPluginId) &&
          normalizeInstallUrl(candidate.repo).toLowerCase() === extensionRepo
        );
      });
      sourceBindingDialog.candidates = candidates;
      sourceBindingDialog.selectedKey =
        currentCandidate?.key || candidates[0]?.key || "";
    } finally {
      sourceBindingDialog.loading = false;
    }
  };

  const closePluginSourceBindingDialog = () => {
    sourceBindingDialog.show = false;
    sourceBindingDialog.loading = false;
    sourceBindingDialog.saving = false;
    sourceBindingDialog.extension = null;
    sourceBindingDialog.candidates = [];
    sourceBindingDialog.selectedKey = "";
  };

  const confirmPluginSourceBinding = async () => {
    const extension = sourceBindingDialog.extension;
    const candidate = sourceBindingDialog.candidates.find(
      (item) => item.key === sourceBindingDialog.selectedKey,
    );
    if (!extension || !candidate || sourceBindingDialog.saving) {
      return;
    }

    sourceBindingDialog.saving = true;
    try {
      const res = await pluginApi.bindSource(extension.name, {
        registry_url: candidate.registry_url,
        market_plugin_id: candidate.market_plugin_id,
      });
      if (res.data.status === "error") {
        toast(res.data.message, "error");
        return;
      }

      toast(res.data.message || tm("messages.sourceBindSuccess"), "success");
      closePluginSourceBindingDialog();
      await getExtensions();
      checkAlreadyInstalled();
      await checkUpdate();
    } catch (error) {
      const errorMsg =
        error.response?.data?.message || error.message || String(error);
      toast(errorMsg, "error");
    } finally {
      sourceBindingDialog.saving = false;
    }
  };

  const editCustomSource = (source) => {
    if (!source) return;
    showSourceManagerDialog.value = false;
    editingSource.value = true;
    originalSourceUrl.value = source.url;
    sourceName.value = source.name;
    sourceUrl.value = source.url;
    sourceResolvedUrl.value = source.url;
    sourceResolveVisible.value = false;
    sourceMarketMeta.value = null;
    sourceResolving.value = false;
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

  const resolveCustomSource = async () => {
    const normalizedUrl = sourceUrl.value.trim();

    if (!normalizedUrl) {
      toast(tm("messages.fillSourceUrl"), "error");
      return;
    }

    try {
      new URL(normalizedUrl);
    } catch (e) {
      toast(tm("messages.invalidUrl"), "error");
      return;
    }

    const normalizedRegistryUrl = normalizeRegistryUrl(normalizedUrl);
    const originalRegistryUrl = normalizeRegistryUrl(originalSourceUrl.value);
    if (
      (!editingSource.value || normalizedRegistryUrl !== originalRegistryUrl) &&
      customSources.value.some(
        (source) => normalizeRegistryUrl(source.url) === normalizedRegistryUrl,
      )
    ) {
      toast(tm("market.sourceExists"), "error");
      return;
    }

    sourceResolving.value = true;
    try {
      const res = await pluginApi.market({
        custom_registry: normalizedRegistryUrl,
        force_refresh: true,
      });
      if (res.data.status !== "ok") {
        toast(res.data.message || tm("messages.sourceResolveFailed"), "error");
        return;
      }

      const meta = res.data.data?.$meta;
      sourceMarketMeta.value =
        meta && typeof meta === "object" && !Array.isArray(meta) ? meta : null;

      const metaName = String(sourceMarketMeta.value?.name || "").trim();
      if (metaName && !sourceName.value.trim()) {
        sourceName.value = metaName;
      }
      sourceResolvedUrl.value = normalizedRegistryUrl;
      sourceResolveVisible.value = true;
      toast(tm("market.sourceResolved"), "success");
    } catch (error) {
      toast(
        resolveErrorMessage(error, tm("messages.sourceResolveFailed")),
        "error",
      );
    } finally {
      sourceResolving.value = false;
    }
  };

  const saveCustomSource = () => {
    const normalizedUrl = sourceUrl.value.trim();

    if (!normalizedUrl) {
      toast(tm("messages.fillSourceUrl"), "error");
      return;
    }

    try {
      new URL(normalizedUrl);
    } catch (e) {
      toast(tm("messages.invalidUrl"), "error");
      return;
    }

    if (!sourceResolveCurrent.value) {
      toast(tm("messages.resolveSourceFirst"), "error");
      return;
    }

    if (!sourceName.value.trim()) {
      toast(tm("messages.fillSourceName"), "error");
      return;
    }

    const normalizedRegistryUrl = normalizeRegistryUrl(normalizedUrl);
    const originalRegistryUrl = normalizeRegistryUrl(originalSourceUrl.value);

    if (editingSource.value) {
      const index = customSources.value.findIndex(
        (s) => normalizeRegistryUrl(s.url) === originalRegistryUrl,
      );
      if (index !== -1) {
        customSources.value[index] = {
          name: sourceName.value.trim(),
          url: normalizedRegistryUrl,
        };

        if (
          normalizeRegistryUrl(selectedSource.value) === originalRegistryUrl
        ) {
          selectedSource.value = normalizedRegistryUrl;
          localStorage.setItem("selectedPluginSource", selectedSource.value);
          refreshPluginMarket();
        }
      }
    } else {
      if (
        customSources.value.some(
          (source) =>
            normalizeRegistryUrl(source.url) === normalizedRegistryUrl,
        )
      ) {
        toast(tm("market.sourceExists"), "error");
        return;
      }

      customSources.value.push({
        name: sourceName.value.trim(),
        url: normalizedRegistryUrl,
      });
    }

    saveCustomSources();
    toast(
      editingSource.value
        ? tm("market.sourceUpdated")
        : tm("market.sourceAdded"),
      "success",
    );

    // 重置表单
    sourceName.value = "";
    sourceUrl.value = "";
    sourceResolvedUrl.value = "";
    sourceResolveVisible.value = false;
    sourceMarketMeta.value = null;
    sourceResolving.value = false;
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
    const currentRegistryUrl = normalizeRegistryUrl(selectedSource.value);
    const installedByIdentifier = new Map();
    const installedByRepo = new Map();
    const installedByName = new Map();

    data.forEach((ext) => {
      const source = ext.install_source || {};
      const isCurrentMarketInstall =
        source.install_method === "market" &&
        normalizeRegistryUrl(source.registry_url) === currentRegistryUrl;
      const identifier = String(source.market_plugin_id || "").trim();
      if (isCurrentMarketInstall && identifier) {
        installedByIdentifier.set(identifier, ext);
      }

      const repo = normalizeInstallUrl(ext.repo || source.repo).toLowerCase();
      if (repo) {
        installedByRepo.set(repo, ext);
      } else {
        installedByName.set(
          normalizeStr(ext.marketplace_name || ext.name),
          ext,
        );
      }
    });

    for (let i = 0; i < pluginMarketData.value.length; i++) {
      const plugin = pluginMarketData.value[i];
      const pluginIdentifier = getMarketPluginId(plugin);
      const pluginRepo = normalizeInstallUrl(plugin.repo).toLowerCase();
      const matchedInstalled =
        (pluginIdentifier && installedByIdentifier.get(pluginIdentifier)) ||
        (pluginRepo && installedByRepo.get(pluginRepo)) ||
        installedByName.get(normalizeStr(plugin.name));

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

      plugin.installed = !!matchedInstalled;
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

  const normalizeAstrBotVersionSpec = (value) => String(value || "").trim();

  const normalizeVersionParts = (value) => {
    const version = String(value || "")
      .trim()
      .replace(/^v/i, "")
      .split(/[+-]/)[0];
    const parts = version.split(".").map((part) => {
      const match = part.match(/^\d+/);
      return match ? Number.parseInt(match[0], 10) : 0;
    });
    return parts.length ? parts : [0];
  };

  const compareVersions = (left, right) => {
    const leftParts = normalizeVersionParts(left);
    const rightParts = normalizeVersionParts(right);
    const length = Math.max(leftParts.length, rightParts.length, 3);
    for (let i = 0; i < length; i += 1) {
      const leftPart = leftParts[i] || 0;
      const rightPart = rightParts[i] || 0;
      if (leftPart > rightPart) return 1;
      if (leftPart < rightPart) return -1;
    }
    return 0;
  };

  const getSupportedReleaseUpperBound = (version) => {
    const parts = normalizeVersionParts(version);
    if (parts.length <= 2) {
      return `${(parts[0] || 0) + 1}.0`;
    }
    return `${parts[0] || 0}.${(parts[1] || 0) + 1}.0`;
  };

  const checkVersionConstraint = (currentVersion, constraint) => {
    const match = constraint.match(/^(<=|>=|==|!=|~=|<|>|=)\s*(.+)$/);
    if (!match) return null;

    const [, operator, targetVersion] = match;
    const normalizedTarget = targetVersion.trim();
    if (!normalizedTarget) return null;
    if (!/^v?\d+/.test(normalizedTarget)) return null;

    if (operator === "~=") {
      return (
        compareVersions(currentVersion, normalizedTarget) >= 0 &&
        compareVersions(
          currentVersion,
          getSupportedReleaseUpperBound(normalizedTarget),
        ) < 0
      );
    }

    const comparison = compareVersions(currentVersion, normalizedTarget);
    if (operator === ">" || operator === ">=") {
      return operator === ">" ? comparison > 0 : comparison >= 0;
    }
    if (operator === "<" || operator === "<=") {
      return operator === "<" ? comparison < 0 : comparison <= 0;
    }
    if (operator === "!=") return comparison !== 0;
    return comparison === 0;
  };

  const checkAstrBotVersionSupport = (versionSpec, currentVersion) => {
    const normalizedSpec = normalizeAstrBotVersionSpec(versionSpec);
    if (!normalizedSpec) {
      return { checked: false, supported: true, message: "" };
    }
    if (!currentVersion) {
      return { checked: false, supported: true, message: "" };
    }

    const constraints = normalizedSpec
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (!constraints.length) {
      return { checked: false, supported: true, message: "" };
    }

    for (const constraint of constraints) {
      const supported = checkVersionConstraint(currentVersion, constraint);
      if (supported === null) {
        return {
          checked: true,
          supported: false,
          message:
            "Invalid astrbot_version. Use a PEP 440 range, e.g. >=4.16,<5.",
        };
      }
      if (!supported) {
        return {
          checked: true,
          supported: false,
          message: `AstrBot ${currentVersion} does not satisfy plugin astrbot_version: ${normalizedSpec}`,
        };
      }
    }

    return { checked: true, supported: true, message: "" };
  };

  const annotateMarketVersionSupport = async () => {
    const currentVersion =
      commonStore.astrbotVersion ||
      (await commonStore.fetchAstrBotVersion().catch(() => ""));
    pluginMarketData.value.forEach((plugin) => {
      const result = checkAstrBotVersionSupport(
        plugin?.astrbot_version,
        currentVersion,
      );
      plugin.astrbot_support_checked = result.checked;
      plugin.astrbot_version_supported = result.supported;
      plugin.astrbot_support_message = result.message;
    });
  };

  const showVersionSupportWarning = (message) => {
    versionSupportDialog.message = message;
    versionSupportDialog.show = true;
  };

  const refreshExtensionsAfterInstallFailure = async () => {
    try {
      await getExtensions();
    } catch (error) {
      console.debug(
        "Failed to refresh extensions after install failure:",
        error,
      );
    }
  };

  const continueInstallIgnoringVersionWarning = async () => {
    versionSupportDialog.show = false;
    await newExtension(true);
  };

  const cancelInstallOnVersionWarning = () => {
    versionSupportDialog.show = false;
  };

  const handleInstallResponse = async (resData) => {
    if (
      resData.status === "warning" &&
      resData.data?.warning_type === "astrbot_version_unsupported"
    ) {
      toast(resData.message, "warning");
      showVersionSupportWarning(resData.message);
      await refreshExtensionsAfterInstallFailure();
      return false;
    }

    if (resData.status === "error") {
      toast(resData.message, "error");
      await refreshExtensionsAfterInstallFailure();
      return false;
    }

    return true;
  };

  const performInstallRequest = async ({ source, ignoreVersionCheck }) => {
    const shouldIgnoreVersionCheck = ignoreVersionCheck === true;
    if (source === "file") {
      const formData = new FormData();
      formData.append("file", upload_file.value);
      formData.append("ignore_version_check", String(shouldIgnoreVersionCheck));
      return pluginApi.installUpload(formData);
    }

    const payload = {
      url: extension_url.value,
      download_url: selectedInstallDownloadUrl.value,
      proxy: selectedInstallDownloadUrl.value ? "" : getSelectedGitHubProxy(),
      ignore_version_check: shouldIgnoreVersionCheck,
      ...getMarketInstallSourcePayload(),
    };

    return installUsesGithubSource.value
      ? pluginApi.installGithub(payload)
      : pluginApi.installUrl(payload);
  };

  const finalizeSuccessfulInstall = async (resData, source) => {
    if (source === "file") {
      upload_file.value = null;
    } else {
      extension_url.value = "";
    }

    toast(resData.message, "success");
    dialog.value = false;
    selectedMarketInstallPlugin.value = null;
    await getExtensions();
    checkAlreadyInstalled();
    await checkUpdate();

    viewReadme({
      name: resData.data.name,
      repo: resData.data.repo || null,
    });

    await checkAndPromptConflicts();
  };

  const newExtension = async (ignoreVersionCheck = false) => {
    const shouldIgnoreVersionCheck = ignoreVersionCheck === true;
    if (extension_url.value === "" && upload_file.value === null) {
      toast(tm("messages.fillUrlOrFile"), "error");
      return;
    }

    if (extension_url.value !== "" && upload_file.value !== null) {
      toast(tm("messages.dontFillBoth"), "error");
      return;
    }
    const source = upload_file.value !== null ? "file" : "url";
    loading_.value = true;

    try {
      const res = await performInstallRequest({
        source,
        ignoreVersionCheck: shouldIgnoreVersionCheck,
      });
      loading_.value = false;

      const canContinue = await handleInstallResponse(res.data);
      if (!canContinue) return;

      await finalizeSuccessfulInstall(res.data, source);
    } catch (err) {
      loading_.value = false;
      const message = resolveErrorMessage(err, tm("messages.installFailed"));
      toast(message, "error");
      await refreshExtensionsAfterInstallFailure();
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
    return (
      pluginMarketData.value.find(
        (plugin) => plugin.repo === extension_url.value,
      ) || null
    );
  };

  const selectedInstallPlugin = computed(() => resolveSelectedInstallPlugin());

  const selectedUpdateExtension = computed(() =>
    getInstalledExtensionByName(updateConfirmDialog.extensionName),
  );

  const selectedUpdateMarketPlugin = computed(() =>
    findMarketPluginForExtension(selectedUpdateExtension.value),
  );

  const selectedUpdateDownloadUrl = computed(() =>
    String(selectedUpdateMarketPlugin.value?.download_url || "").trim(),
  );

  const selectedUpdateSourceUrl = computed(
    () =>
      selectedUpdateDownloadUrl.value ||
      String(selectedUpdateExtension.value?.repo || "").trim(),
  );

  const updateUsesGithubSource = computed(
    () =>
      !selectedUpdateDownloadUrl.value &&
      isGithubRepoUrl(selectedUpdateSourceUrl.value),
  );

  const checkInstallVersionSupport = async () => {
    installSupport.checked = false;
    installSupport.supported = true;
    installSupport.message = "";

    const plugin = selectedInstallPlugin.value;
    if (!plugin?.astrbot_version || uploadTab.value !== "url") {
      return;
    }

    const currentVersion =
      commonStore.astrbotVersion ||
      (await commonStore.fetchAstrBotVersion().catch(() => ""));
    const result = checkAstrBotVersionSupport(
      plugin.astrbot_version,
      currentVersion,
    );
    installSupport.checked = result.checked;
    installSupport.supported = result.supported;
    installSupport.message = result.message;
  };

  // 刷新插件市场数据
  const refreshPluginMarket = async () => {
    refreshingMarket.value = true;
    loading_.value = true;
    try {
      // 强制刷新插件市场数据
      const data = await commonStore.getPluginCollections(
        true,
        selectedSource.value,
      );
      pluginMarketData.value = data;
      trimExtensionName();
      checkAlreadyInstalled();
      await annotateMarketVersionSupport();
      await checkUpdate();
      refreshRandomPlugins();
      currentPage.value = 1; // 重置到第一页

      toast(tm("messages.refreshSuccess"), "success");
    } catch (err) {
      toast(tm("messages.refreshFailed") + " " + err, "error");
    } finally {
      refreshingMarket.value = false;
      loading_.value = false;
    }
  };

  // 生命周期
  onMounted(async () => {
    if (!syncTabFromHash(getLocationHash())) {
      await replaceTabRoute(router, route, activeTab.value);
    }
    loading_.value = true;
    try {
      await getExtensions({ withLoading: false });

      // 加载自定义插件源
      await loadCustomSources();

      // 检查是否有 open_config 参数
      const plugin_name = Array.isArray(route.query.open_config)
        ? route.query.open_config[0]
        : route.query.open_config;
      if (plugin_name) {
        console.log(`Opening config for plugin: ${plugin_name}`);
        openExtensionConfig(plugin_name);
      }

      const data = await commonStore.getPluginCollections(
        false,
        selectedSource.value,
      );
      pluginMarketData.value = data;
      trimExtensionName();
      checkAlreadyInstalled();
      await annotateMarketVersionSupport();
      await checkUpdate();
      refreshRandomPlugins();
    } catch (err) {
      toast(tm("messages.getMarketDataFailed") + " " + err, "error");
    } finally {
      loading_.value = false;
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

  watch(
    [() => dialog.value, () => extension_url.value, () => uploadTab.value],
    async ([dialogOpen, _, currentUploadTab]) => {
      if (!dialogOpen || currentUploadTab !== "url") {
        installSupport.checked = false;
        installSupport.supported = true;
        installSupport.message = "";
        if (!dialogOpen) {
          selectedMarketInstallPlugin.value = null;
        }
        return;
      }
      await checkInstallVersionSupport();
    },
  );

  watch(
    () => route.hash,
    (newHash) => {
      const tab = extractTabFromHash(newHash);
      if (tab && tab !== activeTab.value) {
        activeTab.value = tab;
      }
    },
  );

  watch(activeTab, (newTab) => {
    if (!isValidTab(newTab)) return;
    if (route.hash === `#${newTab}`) return;
    void replaceTabRoute(router, route, newTab);
  });

  watch(marketCategoryFilter, () => {
    if (activeTab.value === "market") {
      currentPage.value = 1;
    }
  });

  watch(
    marketCategoryItems,
    (newItems) => {
      const validValues = new Set(newItems.map((item) => item.value));
      if (!validValues.has(marketCategoryFilter.value)) {
        marketCategoryFilter.value = "all";
      }
    },
    { immediate: true },
  );

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
    marketCategoryFilter,
    marketCategoryItems,
    marketCategoryCounts,
    dangerConfirmDialog,
    selectedDangerPlugin,
    selectedMarketInstallPlugin,
    installSupport,
    versionSupportDialog,
    showUninstallDialog,
    uninstallTarget,
    showSourceDialog,
    showSourceManagerDialog,
    sourceName,
    sourceUrl,
    sourceResolving,
    sourceResolveVisible,
    sourceMarketMeta,
    sourceResolveCurrent,
    customSources,
    selectedSource,
    showRemoveSourceDialog,
    sourceToRemove,
    editingSource,
    originalSourceUrl,
    sourceBindingDialog,
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
    failedPluginItems,
    getExtensions,
    handleReloadAllFailed,
    reloadFailedPlugin,
    checkUpdate,
    uninstallExtension,
    requestUninstallPlugin,
    requestUninstallFailedPlugin,
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
    editCustomSource,
    removeCustomSource,
    confirmRemoveSource,
    resolveCustomSource,
    saveCustomSource,
    openPluginSourceBindingDialog,
    closePluginSourceBindingDialog,
    confirmPluginSourceBinding,
    trimExtensionName,
    checkAlreadyInstalled,
    showVersionSupportWarning,
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
    checkInstallVersionSupport,
    refreshPluginMarket,
    handleLocaleChange,
    searchDebounceTimer,
  };
};
