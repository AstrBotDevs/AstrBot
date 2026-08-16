import { commandApi, pluginApi } from '@/api/v1';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import type { ToastColor } from '@/stores/toast';
import { useCommonStore } from '@/stores/common';
import type {
  FailedPluginDetail,
  InstalledPlugin,
  PluginMarketItem,
  PluginSourceItem,
} from '@/types/extensions';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { readSelectedGitHubProxy } from '@/utils/githubProxyStorage';
import { getValidHashTab, replaceTabRoute } from '@/utils/hashRouteTabs';
import { getPlatformDisplayName } from '@/utils/platformUtils';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import {
  buildSearchQuery,
  matchesPluginSearch,
  normalizeStr,
  toInitials,
  toPinyinText,
} from '@/utils/pluginSearch';
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

type ExtensionTab = 'installed' | 'market' | 'mcp' | 'skills' | 'components';
type UploadTab = 'file' | 'url';
type SortBy = 'default' | 'stars' | 'downloads' | 'author' | 'updated';
type SortOrder = 'desc' | 'asc';
type PluginLogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';

const PLUGIN_LOG_LEVELS: readonly PluginLogLevel[] = [
  'DEBUG',
  'INFO',
  'WARNING',
  'ERROR',
  'CRITICAL',
];

interface FailedPluginRecord extends Partial<FailedPluginDetail> {
  [key: string]: unknown;
}

interface UninstallTarget {
  kind: 'normal' | 'failed';
  id: string;
}

interface UninstallOptions {
  deleteConfig?: boolean;
  deleteData?: boolean;
  skipConfirm?: boolean;
}

interface CategoryMeta {
  count: number;
  rawLabel: string;
}

const MARKET_CATEGORY_ALIASES: Record<string, string> = {
  ai_增强: 'ai_tools',
  ai_tools: 'ai_tools',
  entertainment: 'entertainment',
  integrations: 'integrations',
  knowledge_base: 'knowledge_base',
  long_term_memory: 'long_term_memory',
  productivity: 'productivity',
  tools: 'tools',
  utilities: 'utilities',
  三方集成: 'integrations',
  娱乐: 'entertainment',
  工具: 'tools',
  生活: 'utilities',
  生活实用: 'utilities',
  知识库: 'knowledge_base',
  长期记忆: 'long_term_memory',
  外部集成: 'integrations',
  其他: 'other',
  other: 'other',
};

interface LoadingDialogState {
  show: boolean;
  title: string;
  statusCode: number;
  result: string;
}

interface PluginConfigState {
  metadata: Record<string, unknown>;
  config: Record<string, unknown>;
  i18n: Record<string, unknown>;
  log_level: PluginLogLevel | null;
}

interface InstallSupportState {
  checked: boolean;
  supported: boolean;
  message: string;
}

interface VersionSupportResult {
  checked: boolean;
  supported: boolean;
  message: string;
}

interface PluginRouteInfo {
  name: string;
  repo?: string | null;
}

interface InstallResponseData {
  status?: string;
  message?: string | null;
  data?: Record<string, unknown>;
}

const buildFailedPluginItems = (
  raw: Record<string, FailedPluginRecord>,
): FailedPluginDetail[] => {
  return Object.entries(raw || {}).map(([dirName, info]) => {
    const detail = info && typeof info === 'object' ? info : {};
    let displayName = dirName;
    if (typeof detail.display_name === 'string') {
      displayName = detail.display_name;
    } else if (typeof detail.name === 'string') {
      displayName = detail.name;
    }

    return {
      ...detail,
      dir_name: dirName,
      name: typeof detail.name === 'string' ? detail.name : dirName,
      display_name: displayName,
      error: typeof detail.error === 'string' ? detail.error : '',
      traceback: typeof detail.traceback === 'string' ? detail.traceback : '',
      reserved: Boolean(detail.reserved),
    };
  });
};

export const useExtensionPage = () => {
  const commonStore = useCommonStore();
  const { t } = useI18n();
  const { tm, getRaw } = useModuleI18n('features/extension');
  const router = useRouter();
  const route = useRoute();
  const getSelectedGitHubProxy = readSelectedGitHubProxy;
  const {
    dialogOpen: stepUpDialogOpen,
    loading: stepUpLoading,
    errorMessage: stepUpErrorMessage,
    requestStepUp,
    submitStepUp,
    cancelStepUp,
  } = useDashboardStepUp();

  const requestPluginInstallStepUp = async (): Promise<string> => {
    const token = await requestStepUp({
      action: 'extension.plugin_install',
      resourceType: 'dashboard-api',
      resourceId: 'post-plugin',
    });
    if (!token) throw new Error('Plugin installation authorization cancelled.');
    return token;
  };

  // 检查指令冲突并提示
  const conflictDialog = reactive({
    show: false,
    count: 0,
  });
  const checkAndPromptConflicts = async () => {
    try {
      const res = await commandApi.list();
      if (res.data.status === 'ok') {
        const conflicts = res.data.data.summary?.conflicts || 0;
        if (conflicts > 0) {
          conflictDialog.count = conflicts;
          conflictDialog.show = true;
        }
      }
    } catch (err) {
      console.debug('Failed to check command conflicts:', err);
    }
  };
  const handleConflictConfirm = () => {
    activeTab.value = 'components';
  };

  const fileInput = ref<HTMLInputElement | null>(null);
  const validTabs = [
    'installed',
    'market',
    'mcp',
    'skills',
    'components',
  ] as const;
  const activeTab = ref<ExtensionTab>('installed');
  const isValidTab = (tab: string): tab is ExtensionTab =>
    validTabs.includes(tab as ExtensionTab);
  const getLocationHash = () => route.hash || '';
  const extractTabFromHash = (hash: string): ExtensionTab | null => {
    const tab = getValidHashTab(hash, validTabs);
    return tab && isValidTab(tab) ? tab : null;
  };
  const syncTabFromHash = (hash: string) => {
    const tab = extractTabFromHash(hash);
    if (tab) {
      activeTab.value = tab;
      return true;
    }
    return false;
  };
  const extension_data = reactive<{
    data: InstalledPlugin[];
    message: '';
  }>({
    data: [],
    message: '',
  });

  const snack_message = ref('');
  const snack_show = ref(false);
  const snack_success = ref<ToastColor>('success');
  const configDialog = ref(false);
  const extension_config = reactive<PluginConfigState>({
    metadata: {},
    config: {},
    i18n: {},
    log_level: null,
  });
  const pluginLogLevelSaving = ref(false);
  const pluginMarketData = ref<PluginMarketItem[]>([]);
  const loadingDialog = reactive<LoadingDialogState>({
    show: false,
    title: '',
    statusCode: 0, // 0: loading, 1: success, 2: error,
    result: '',
  });
  const curr_namespace = ref('');
  const currentConfigPlugin = ref('');
  const updatingAll = ref(false);

  const readmeDialog = reactive({
    show: false,
    pluginName: '',
    repoUrl: null as string | null,
  });

  // 强制更新确认对话框
  const forceUpdateDialog = reactive({
    show: false,
    extensionName: '',
  });

  const updateConfirmDialog = reactive({
    show: false,
    extensionName: '',
    forceUpdate: false,
  });

  // 更新全部插件确认对话框
  const updateAllConfirmDialog = reactive({
    show: false,
  });

  // 插件更新日志对话框（复用 ReadmeDialog）
  const changelogDialog = reactive({
    show: false,
    pluginName: '',
    repoUrl: null as string | null,
  });

  const pluginSearch = ref('');
  const loading_ = ref(false);

  // 分页相关
  const currentPage = ref(1);

  // 危险插件确认对话框
  const dangerConfirmDialog = ref(false);
  const selectedDangerPlugin = ref<PluginMarketItem | null>(null);
  const selectedMarketInstallPlugin = ref<PluginMarketItem | null>(null);
  const installSupport = reactive<InstallSupportState>({
    checked: false,
    supported: true,
    message: '',
  });

  // AstrBot 版本范围不兼容警告对话框
  const versionSupportDialog = reactive({
    show: false,
    message: '',
  });

  // 卸载插件确认对话框（列表模式用）
  const showUninstallDialog = ref(false);
  const uninstallTarget = ref<UninstallTarget | null>(null);

  // 自定义插件源相关
  const showSourceDialog = ref(false);
  const showSourceManagerDialog = ref(false);
  const sourceName = ref('');
  const sourceUrl = ref('');
  const customSources = ref<PluginSourceItem[]>([]);
  const selectedSource = ref<string | null>(null);
  const showRemoveSourceDialog = ref(false);
  const sourceToRemove = ref<PluginSourceItem | null>(null);
  const editingSource = ref(false);
  const originalSourceUrl = ref('');

  // 插件市场相关
  const extension_url = ref('');
  const dialog = ref(false);
  const upload_file = ref<File | null>(null);
  const uploadTab = ref<UploadTab>('file');
  const showPluginFullName = ref(false);
  const marketSearch = ref('');
  const debouncedMarketSearch = ref('');
  const refreshingMarket = ref(false);
  const sortBy = ref<SortBy>('default'); // default, stars, downloads, author, updated
  const sortOrder = ref<SortOrder>('desc'); // desc (降序) or asc (升序)
  const randomPluginNames = ref<string[]>([]);
  const marketCategoryFilter = ref('all');

  // 插件市场拼音搜索

  const normalizeMarketCategory = (rawCategory: unknown): string => {
    const normalized = String(rawCategory || '')
      .trim()
      .toLowerCase();
    if (!normalized) {
      return 'other';
    }
    const normalizedKey = normalized.replace(/[\s-]+/g, '_');
    return MARKET_CATEGORY_ALIASES[normalizedKey] || normalizedKey;
  };

  const getMarketCategoryLabel = (key: string, rawCategory = '') => {
    const fallbackMap: Record<string, string> = {
      all: 'All',
      ai_tools: 'AI Tools',
      entertainment: 'Entertainment',
      productivity: 'Productivity',
      integrations: 'Integrations',
      utilities: 'Utilities',
      tools: 'Tools',
      knowledge_base: 'Knowledge Base',
      long_term_memory: 'Long-term Memory',
      other: 'Other',
    };
    const categoryKey = normalizeMarketCategory(key);
    const i18nKey = `market.categories.${categoryKey}`;
    const translated = getRaw(i18nKey);
    if (typeof translated === 'string') {
      return translated;
    }
    if (fallbackMap[categoryKey]) {
      return fallbackMap[categoryKey];
    }
    const normalizedRaw = String(rawCategory || '').trim();
    if (normalizedRaw) {
      return normalizedRaw;
    }
    return categoryKey
      .split(/[_-]+/)
      .filter(Boolean)
      .map((part: string) => part[0].toUpperCase() + part.slice(1))
      .join(' ');
  };

  const marketCategoryMeta = computed(() => {
    const categories = new Map<string, CategoryMeta>();

    for (const plugin of pluginMarketData.value) {
      const categoryKey = normalizeMarketCategory(plugin?.category);
      const categoryData = categories.get(categoryKey);
      if (categoryData) {
        categoryData.count += 1;
        continue;
      }
      categories.set(categoryKey, {
        count: 1,
        rawLabel: String(plugin?.category || '').trim(),
      });
    }

    return categories;
  });

  const marketCategoryCounts = computed<Record<string, number>>(() => {
    const counts: Record<string, number> = {
      all: pluginMarketData.value.length,
    };
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
        value: 'all',
        label: getMarketCategoryLabel('all'),
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

  const compareInstalledPluginNames = (
    left: InstalledPlugin,
    right: InstalledPlugin,
  ) =>
    normalizeStr(left?.name ?? '').localeCompare(
      normalizeStr(right?.name ?? ''),
      undefined,
      {
        sensitivity: 'base',
      },
    );

  const compareInstalledFallback = (
    left: { plugin: InstalledPlugin; index: number },
    right: { plugin: InstalledPlugin; index: number },
  ) => {
    const reservedDiff =
      Number(Boolean(left.plugin?.reserved)) -
      Number(Boolean(right.plugin?.reserved));
    if (reservedDiff !== 0) {
      return reservedDiff;
    }

    const nameCompare = compareInstalledPluginNames(left.plugin, right.plugin);
    return nameCompare !== 0 ? nameCompare : left.index - right.index;
  };

  const sortInstalledPlugins = (plugins: InstalledPlugin[]) => {
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
    const shouldFilterByCategory = marketCategoryFilter.value !== 'all';
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
    const plugins = [...filteredMarketPlugins.value];

    // 根据排序选项排序
    if (sortBy.value === 'stars') {
      // 按 star 数排序
      plugins.sort((a, b) => {
        const starsA = a.stars ?? 0;
        const starsB = b.stars ?? 0;
        return sortOrder.value === 'desc' ? starsB - starsA : starsA - starsB;
      });
    } else if (sortBy.value === 'downloads') {
      plugins.sort((a, b) => {
        const downloadsA = Number(a.download_count) || 0;
        const downloadsB = Number(b.download_count) || 0;
        return sortOrder.value === 'desc'
          ? downloadsB - downloadsA
          : downloadsA - downloadsB;
      });
    } else if (sortBy.value === 'author') {
      // 按作者名字典序排序
      plugins.sort((a, b) => {
        const authorA = String(a.author ?? '').toLowerCase();
        const authorB = String(b.author ?? '').toLowerCase();
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
      const pinned = plugins.filter((plugin) => plugin?.pinned);
      const notPinned = plugins.filter((plugin) => !plugin?.pinned);
      return [...pinned, ...notPinned];
    }

    return plugins;
  });

  const RANDOM_PLUGINS_COUNT = 3;

  const randomPlugins = computed<PluginMarketItem[]>(() => {
    const allPlugins = pluginMarketData.value;
    if (allPlugins.length === 0) return [];

    const pluginsByName = new Map(
      allPlugins.map((plugin) => [plugin.name, plugin]),
    );
    const selected = randomPluginNames.value
      .map((name) => pluginsByName.get(name))
      .filter((plugin): plugin is PluginMarketItem => Boolean(plugin));

    if (selected.length > 0) {
      return selected;
    }

    return allPlugins.slice(
      0,
      Math.min(RANDOM_PLUGINS_COUNT, allPlugins.length),
    );
  });

  const shufflePlugins = <T>(plugins: T[]): T[] => {
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
  const toast = (message: unknown, success: ToastColor, _duration?: number) => {
    snack_message.value =
      typeof message === 'string'
        ? message
        : resolveErrorMessage(message, String(message ?? ''));
    snack_show.value = true;
    snack_success.value = success;
  };

  const resetLoadingDialog = () => {
    loadingDialog.show = false;
    loadingDialog.title = tm('dialogs.loading.title');
    loadingDialog.statusCode = 0;
    loadingDialog.result = '';
  };

  const onLoadingDialogResult = (
    statusCode: number,
    result: unknown,
    timeToClose = 2000,
  ) => {
    loadingDialog.statusCode = statusCode;
    loadingDialog.result = String(result ?? '');
    if (timeToClose === -1) return;
    setTimeout(resetLoadingDialog, timeToClose);
  };

  const failedPluginsDict = ref<Record<string, FailedPluginRecord>>({});
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

      const failRes = await pluginApi.failed();
      failedPluginsDict.value = failRes.data.data || {};

      // checkUpdate() is called after pluginMarketData is loaded in onMounted
    } catch (err) {
      toast(err, 'error');
    } finally {
      if (withLoading) {
        loading_.value = false;
      }
    }
  };

  const handleReloadAllFailed = async () => {
    const dirNames = Object.keys(failedPluginsDict.value);
    if (dirNames.length === 0) {
      toast('没有需要重载的失败插件', 'info');
      return;
    }

    loading_.value = true;
    try {
      const promises = dirNames.map((dir) => pluginApi.reloadFailed(dir));
      await Promise.all(promises);

      toast('已尝试重载所有失败插件', 'success');

      // 清空 message 关闭对话框
      extension_data.message = '';

      // 刷新列表
      await getExtensions();
    } catch (error) {
      console.error('重载失败:', error);
      toast('批量重载过程中出现错误', 'error');
    } finally {
      loading_.value = false;
    }
  };

  const reloadFailedPlugin = async (dirName: string) => {
    if (!dirName) return;

    try {
      const res = await pluginApi.reloadFailed(dirName);
      if (res.data.status === 'error') {
        toast(res.data.message || tm('messages.reloadFailed'), 'error');
        return;
      }
      toast(res.data.message || tm('messages.reloadSuccess'), 'success');
      await getExtensions();
    } catch (err) {
      toast(resolveErrorMessage(err, tm('messages.reloadFailed')), 'error');
    }
  };

  const requestUninstall = (target: UninstallTarget | null) => {
    if (!target?.id || !target?.kind) return;
    uninstallTarget.value = target;
    showUninstallDialog.value = true;
  };

  const uninstall = async (
    target: UninstallTarget | null,
    {
      deleteConfig = false,
      deleteData = false,
      skipConfirm = false,
    }: UninstallOptions = {},
  ) => {
    if (!target?.id || !target?.kind) return;

    if (!skipConfirm) {
      requestUninstall(target);
      return;
    }

    const isFailed = target.kind === 'failed';
    const options = {
      delete_config: deleteConfig,
      delete_data: deleteData,
    };

    toast(`${tm('messages.uninstalling')} ${target.id}`, 'primary');

    try {
      const res = isFailed
        ? await pluginApi.uninstallFailed(target.id, options)
        : await pluginApi.uninstall(target.id, options);
      if (res.data.status === 'error') {
        toast(res.data.message, 'error');
        return;
      }
      if (!isFailed) {
        Object.assign(extension_data, res.data);
      }
      toast(res.data.message, 'success');
      await getExtensions();
    } catch (err) {
      toast(resolveErrorMessage(err, tm('messages.operationFailed')), 'error');
    }
  };

  const requestUninstallPlugin = (name: string) => {
    if (!name) return;
    void uninstall({ kind: 'normal', id: name }, { skipConfirm: false });
  };

  const requestUninstallFailedPlugin = (dirName: string) => {
    if (!dirName) return;
    void uninstall({ kind: 'failed', id: dirName }, { skipConfirm: false });
  };

  const normalizeInstallUrl = (value: unknown): string =>
    String(value || '')
      .trim()
      .replace(/\/+$/, '');

  const isGithubRepoUrl = (value: unknown): boolean =>
    /^https:\/\/github\.com\/[^/\s]+\/[^/\s]+(?:\.git)?(?:\/tree\/[^/\s]+)?$/i.test(
      normalizeInstallUrl(value),
    );

  const getInstalledExtensionByName = (
    extensionName: string,
  ): InstalledPlugin | null => {
    const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
    return data.find((extension) => extension.name === extensionName) || null;
  };

  const findMarketPluginForExtension = (
    extension: InstalledPlugin | null | undefined,
  ): PluginMarketItem | null => {
    if (!extension) return null;
    const repo = normalizeInstallUrl(extension.repo).toLowerCase();

    if (repo) {
      for (const plugin of pluginMarketData.value) {
        if (normalizeInstallUrl(plugin?.repo).toLowerCase() === repo) {
          return plugin;
        }
      }
      return null;
    }

    for (const plugin of pluginMarketData.value) {
      if (plugin.name === extension.name) {
        return plugin;
      }
    }
    return null;
  };

  const getUpdateDownloadUrl = (
    extension: InstalledPlugin | null | undefined,
  ) =>
    String(findMarketPluginForExtension(extension)?.download_url || '').trim();

  const checkUpdate = () => {
    const onlinePluginsMap = new Map();
    const onlinePluginsNameMap = new Map();

    pluginMarketData.value.forEach((plugin) => {
      if (plugin.repo) {
        onlinePluginsMap.set(
          normalizeInstallUrl(plugin.repo).toLowerCase(),
          plugin,
        );
      }
      const normalizedName = normalizeStr(plugin.name);
      onlinePluginsNameMap.set(normalizedName, plugin);
    });

    const data = Array.isArray(extension_data?.data) ? extension_data.data : [];

    data.forEach((extension) => {
      const repoKey = extension.repo
        ? normalizeInstallUrl(extension.repo).toLowerCase()
        : undefined;
      const onlinePlugin = repoKey ? onlinePluginsMap.get(repoKey) : null;

      // 使用 marketplace_name 进行市场匹配（后端已统一为减号格式）
      const normalizedExtensionName = normalizeStr(extension.marketplace_name);
      const onlinePluginByName = onlinePluginsNameMap.get(
        normalizedExtensionName,
      );

      const matchedPlugin = repoKey ? onlinePlugin : onlinePluginByName;

      if (matchedPlugin) {
        extension.online_version = matchedPlugin.version;
        extension.has_update =
          extension.version !== matchedPlugin.version &&
          matchedPlugin.version !== tm('status.unknown');
      } else {
        extension.online_version = '';
        extension.has_update = false;
      }
    });
  };

  const uninstallExtension = async (
    extensionName: string,
    optionsOrSkipConfirm: boolean | UninstallOptions = false,
  ) => {
    if (!extensionName) return;

    if (typeof optionsOrSkipConfirm === 'boolean') {
      return uninstall(
        { kind: 'normal', id: extensionName },
        { skipConfirm: optionsOrSkipConfirm },
      );
    }

    return uninstall(
      { kind: 'normal', id: extensionName },
      { ...(optionsOrSkipConfirm ?? {}), skipConfirm: true },
    );
  };

  // 处理卸载确认对话框的确认事件
  const handleUninstallConfirm = async (options: UninstallOptions = {}) => {
    const target = uninstallTarget.value;
    if (!target) return;

    try {
      await uninstall(target, { ...(options || {}), skipConfirm: true });
    } finally {
      uninstallTarget.value = null;
      showUninstallDialog.value = false;
    }
  };

  const openUpdateConfirmDialog = (
    extensionName: string,
    forceUpdate = false,
  ) => {
    updateConfirmDialog.extensionName = extensionName;
    updateConfirmDialog.forceUpdate = forceUpdate;
    updateConfirmDialog.show = true;
  };

  const closeUpdateConfirmDialog = () => {
    updateConfirmDialog.show = false;
    updateConfirmDialog.extensionName = '';
    updateConfirmDialog.forceUpdate = false;
  };

  const updateExtension = async (
    extension_name: string,
    forceUpdate = false,
  ) => {
    const ext = getInstalledExtensionByName(extension_name);

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

    const downloadUrl = getUpdateDownloadUrl(ext);
    closeUpdateConfirmDialog();
    loadingDialog.title = tm('status.loading');
    loadingDialog.statusCode = 0;
    loadingDialog.result = '';
    loadingDialog.show = true;
    try {
      const stepUp = await requestPluginInstallStepUp();
      const res = await pluginApi.update(
        extensionName,
        { proxy: downloadUrl ? '' : getSelectedGitHubProxy() },
        stepUp,
      );

      if (res.data.status === 'error') {
        onLoadingDialogResult(2, res.data.message, -1);
        return;
      }

      Object.assign(extension_data, res.data);
      onLoadingDialogResult(1, res.data.message);
      setTimeout(async () => {
        toast(tm('messages.refreshing'), 'info', 2000);
        try {
          await getExtensions();
          toast(tm('messages.refreshSuccess'), 'success');

          // 更新完成后弹出更新日志
          viewChangelog({
            name: extensionName,
            repo: ext?.repo || null,
          });
        } catch (error) {
          const errorMsg = resolveErrorMessage(
            error,
            tm('messages.refreshFailed'),
          );
          toast(`${tm('messages.refreshFailed')}: ${errorMsg}`, 'error');
        }
      }, 1000);
    } catch (err) {
      toast(err, 'error');
    }
  };

  // 确认强制更新
  // 显示更新全部插件确认对话框
  const showUpdateAllConfirm = () => {
    if (updatableExtensions.value.length === 0) {
      toast(tm('messages.noUpdatesAvailable'), 'info');
      return;
    }
    updateAllConfirmDialog.show = true;
  };

  // 确认更新全部插件
  const confirmUpdateAll = () => {
    updateAllConfirmDialog.show = false;
    void updateAllExtensions();
  };

  // 取消更新全部插件
  const cancelUpdateAll = () => {
    updateAllConfirmDialog.show = false;
  };

  const confirmForceUpdate = () => {
    const name = forceUpdateDialog.extensionName;
    forceUpdateDialog.show = false;
    forceUpdateDialog.extensionName = '';
    openUpdateConfirmDialog(name, true);
  };

  const updateAllExtensions = async () => {
    if (updatingAll.value) return;
    if (updatableExtensions.value.length === 0) {
      toast(tm('messages.noUpdatesAvailable'), 'info');
      return;
    }
    updatingAll.value = true;
    loadingDialog.title = tm('status.loading');
    loadingDialog.statusCode = 0;
    loadingDialog.result = '';
    loadingDialog.show = true;

    const targets = updatableExtensions.value.map((ext) => ext.name);
    try {
      const stepUp = await requestPluginInstallStepUp();
      const res = await pluginApi.updateMany(
        {
          names: targets,
          proxy: getSelectedGitHubProxy(),
        },
        stepUp,
      );

      if (res.data.status === 'error') {
        onLoadingDialogResult(
          2,
          res.data.message ||
            tm('messages.updateAllFailed', {
              failed: targets.length,
              total: targets.length,
            }),
          -1,
        );
        return;
      }

      const results = Array.isArray(res.data.data?.results)
        ? res.data.data.results
        : [];
      const failures = results.filter(
        (
          result,
        ): result is { name?: string; status?: string; message?: string } =>
          result?.status !== 'ok',
      );
      try {
        await getExtensions();
      } catch (err) {
        const errorMsg = resolveErrorMessage(err, tm('messages.refreshFailed'));
        failures.push({ name: 'refresh', status: 'error', message: errorMsg });
      }

      if (failures.length === 0) {
        onLoadingDialogResult(1, tm('messages.updateAllSuccess'));
      } else {
        const failureText = tm('messages.updateAllFailed', {
          failed: failures.length,
          total: targets.length,
        });
        const detail = failures
          .map((f) => `${f.name}: ${f.message}`)
          .join('\n');
        onLoadingDialogResult(2, `${failureText}\n${detail}`, -1);
      }
    } catch (err) {
      const errorMsg = resolveErrorMessage(err, tm('messages.updateAllFailed'));
      onLoadingDialogResult(2, errorMsg, -1);
    } finally {
      updatingAll.value = false;
    }
  };

  const pluginOn = async (extension: InstalledPlugin) => {
    const previousActivated = extension.activated;
    extension.activated = true;
    try {
      const res = await pluginApi.setEnabled(extension.name, true);
      if (res.data.status === 'error') {
        extension.activated = previousActivated;
        toast(res.data.message, 'error');
        return;
      }
      toast(res.data.message, 'success');
      await getExtensions();

      await checkAndPromptConflicts();
    } catch (err) {
      extension.activated = previousActivated;
      toast(err, 'error');
    }
  };

  const pluginOff = async (extension: InstalledPlugin) => {
    const previousActivated = extension.activated;
    extension.activated = false;
    try {
      const res = await pluginApi.setEnabled(extension.name, false);
      if (res.data.status === 'error') {
        extension.activated = previousActivated;
        toast(res.data.message, 'error');
        return;
      }
      toast(res.data.message, 'success');
      await getExtensions();
    } catch (err) {
      extension.activated = previousActivated;
      toast(err, 'error');
    }
  };

  const openExtensionConfig = async (extension_name: string) => {
    curr_namespace.value = extension_name;
    currentConfigPlugin.value = extension_name;
    configDialog.value = true;
    extension_config.log_level = null;
    try {
      const res = await pluginApi.config(extension_name);
      if (curr_namespace.value !== extension_name) return;
      extension_config.metadata =
        res.data.data.metadata && typeof res.data.data.metadata === 'object'
          ? (res.data.data.metadata as Record<string, unknown>)
          : {};
      extension_config.config =
        res.data.data.config && typeof res.data.data.config === 'object'
          ? (res.data.data.config as Record<string, unknown>)
          : {};
      extension_config.i18n =
        res.data.data.i18n && typeof res.data.data.i18n === 'object'
          ? (res.data.data.i18n as Record<string, unknown>)
          : {};
      const logLevel = res.data.data.log_level;
      extension_config.log_level = PLUGIN_LOG_LEVELS.includes(
        logLevel as PluginLogLevel,
      )
        ? (logLevel as PluginLogLevel)
        : null;
    } catch (err) {
      toast(resolveErrorMessage(err, tm('messages.operationFailed')), 'error');
    }
  };

  const updatePluginLogLevel = async (level: unknown) => {
    if (pluginLogLevelSaving.value) return;
    const normalizedLevel = PLUGIN_LOG_LEVELS.includes(level as PluginLogLevel)
      ? (level as PluginLogLevel)
      : null;
    const pluginName = curr_namespace.value;
    if (!pluginName) return;

    const previousLevel = extension_config.log_level;
    extension_config.log_level = normalizedLevel;
    pluginLogLevelSaving.value = true;
    try {
      const res = await pluginApi.updateLogLevel(pluginName, normalizedLevel);
      if (res.data.status !== 'ok') {
        if (curr_namespace.value === pluginName) {
          extension_config.log_level = previousLevel;
        }
        toast(res.data.message || tm('messages.operationFailed'), 'error');
        return;
      }
      const serverLevel = res.data.data?.log_level;
      if (curr_namespace.value === pluginName) {
        extension_config.log_level = PLUGIN_LOG_LEVELS.includes(
          serverLevel as PluginLogLevel,
        )
          ? (serverLevel as PluginLogLevel)
          : null;
      }
      toast(tm('messages.logLevelUpdated'), 'success');
    } catch (err) {
      if (curr_namespace.value === pluginName) {
        extension_config.log_level = previousLevel;
      }
      toast(resolveErrorMessage(err, tm('messages.operationFailed')), 'error');
    } finally {
      pluginLogLevelSaving.value = false;
    }
  };

  const updateConfig = async () => {
    const pluginName = curr_namespace.value;
    if (!pluginName) return;
    loadingDialog.title = tm('status.loading');
    loadingDialog.statusCode = 0;
    loadingDialog.result = '';
    loadingDialog.show = true;
    try {
      const res = await pluginApi.updateConfig(
        pluginName,
        extension_config.config,
      );
      if (res.data.status === 'ok') {
        onLoadingDialogResult(
          1,
          res.data.message || tm('messages.saveSuccess'),
        );
        toast(res.data.message, 'success');
        if (curr_namespace.value !== pluginName) return;
        configDialog.value = false;
        currentConfigPlugin.value = '';
        extension_config.metadata = {};
        extension_config.config = {};
        extension_config.i18n = {};
        extension_config.log_level = null;
        void getExtensions();
        return;
      }
      const message = res.data.message || tm('messages.operationFailed');
      onLoadingDialogResult(2, message, -1);
      toast(message, 'error');
    } catch (err) {
      const message = resolveErrorMessage(err, tm('messages.operationFailed'));
      onLoadingDialogResult(2, message, -1);
      toast(message, 'error');
    }
  };

  const showPluginInfo = (plugin: { name?: string } | null | undefined) => {
    if (!plugin?.name) return;
    void router.push({
      name: 'ExtensionDetails',
      params: { pluginId: plugin.name },
      hash: '#plugin-components',
    });
  };

  const reloadPlugin = async (plugin_name: string) => {
    try {
      const res = await pluginApi.reload(plugin_name);
      if (res.data.status === 'error') {
        toast(res.data.message || tm('messages.reloadFailed'), 'error');
        return;
      }
      toast(tm('messages.reloadSuccess'), 'success');
      await getExtensions();
    } catch (err) {
      toast(resolveErrorMessage(err, tm('messages.reloadFailed')), 'error');
    }
  };

  const viewReadme = (plugin: PluginRouteInfo) => {
    readmeDialog.pluginName = plugin.name;
    readmeDialog.repoUrl = plugin.repo ?? null;
    readmeDialog.show = true;
  };

  // 查看更新日志
  const viewChangelog = (plugin: PluginRouteInfo) => {
    changelogDialog.pluginName = plugin.name;
    changelogDialog.repoUrl = plugin.repo ?? null;
    changelogDialog.show = true;
  };

  const resetInstallDialogState = () => {
    selectedMarketInstallPlugin.value = null;
    extension_url.value = '';
    upload_file.value = null;
    uploadTab.value = 'file';
    installSupport.checked = false;
    installSupport.supported = true;
    installSupport.message = '';
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
    const plugin = selectedInstallPlugin.value;
    const downloadUrl = String(plugin?.download_url || '').trim();
    if (!downloadUrl) return '';
    if (
      normalizeInstallUrl(plugin?.repo) !==
      normalizeInstallUrl(extension_url.value)
    ) {
      return '';
    }
    return downloadUrl;
  });

  const selectedInstallSourceUrl = computed(
    () =>
      selectedInstallDownloadUrl.value ||
      String(extension_url.value || '').trim(),
  );

  const installUsesGithubSource = computed(
    () =>
      !selectedInstallDownloadUrl.value && isGithubRepoUrl(extension_url.value),
  );

  // 为表格视图创建一个处理安装插件的函数
  const handleInstallPlugin = async (plugin: PluginMarketItem) => {
    if (plugin.tags?.includes('danger')) {
      selectedDangerPlugin.value = plugin;
      dangerConfirmDialog.value = true;
    } else {
      selectedMarketInstallPlugin.value = plugin;
      extension_url.value = plugin.repo || '';
      upload_file.value = null;
      dialog.value = true;
      uploadTab.value = 'url';
    }
  };

  // 确认安装危险插件
  const confirmDangerInstall = () => {
    if (selectedDangerPlugin.value) {
      selectedMarketInstallPlugin.value = selectedDangerPlugin.value;
      extension_url.value = selectedDangerPlugin.value.repo || '';
      upload_file.value = null;
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

  // 自定义插件源管理方法
  const loadCustomSources = async () => {
    try {
      const res = await pluginApi.sources();
      if (res.data.status === 'ok') {
        customSources.value = Array.isArray(res.data.data) ? res.data.data : [];
      } else {
        toast(res.data.message, 'error');
      }
    } catch (error) {
      console.warn('Failed to load custom sources:', error);
      customSources.value = [];
    }

    // 加载当前选中的插件源
    const currentSource = localStorage.getItem('selectedPluginSource');
    if (currentSource) {
      selectedSource.value = currentSource;
    }
  };

  const saveCustomSources = async () => {
    try {
      const res = await pluginApi.replaceSources(customSources.value);
      if (res.data.status !== 'ok') {
        toast(res.data.message, 'error');
      }
    } catch (error) {
      toast(
        resolveErrorMessage(error, tm('messages.operationFailed')),
        'error',
      );
    }
  };

  const addCustomSource = () => {
    showSourceManagerDialog.value = false;
    editingSource.value = false;
    originalSourceUrl.value = '';
    sourceName.value = '';
    sourceUrl.value = '';
    showSourceDialog.value = true;
  };

  const openSourceManagerDialog = async () => {
    await loadCustomSources();
    showSourceManagerDialog.value = true;
  };

  const selectPluginSource = (sourceUrl: string | null) => {
    selectedSource.value = sourceUrl;
    if (sourceUrl) {
      localStorage.setItem('selectedPluginSource', sourceUrl);
    } else {
      localStorage.removeItem('selectedPluginSource');
    }
    // 重新加载插件市场数据
    void refreshPluginMarket();
  };

  const sourceSelectItems = computed(() => [
    { title: tm('market.defaultSource'), value: '__default__' },
    ...customSources.value.map((source) => ({
      title: source.name,
      value: source.url,
    })),
  ]);

  const editCustomSource = (source: PluginSourceItem | null) => {
    if (!source) return;
    showSourceManagerDialog.value = false;
    editingSource.value = true;
    originalSourceUrl.value = source.url;
    sourceName.value = source.name ?? '';
    sourceUrl.value = source.url;
    showSourceDialog.value = true;
  };

  const removeCustomSource = (source: PluginSourceItem | null) => {
    if (!source) return;
    showSourceManagerDialog.value = false;
    sourceToRemove.value = source;
    showRemoveSourceDialog.value = true;
  };

  const confirmRemoveSource = () => {
    const source = sourceToRemove.value;
    if (source) {
      customSources.value = customSources.value.filter(
        (s) => s.url !== source.url,
      );
      void saveCustomSources();

      // 如果删除的是当前选中的源，切换到默认源
      if (selectedSource.value === source.url) {
        selectedSource.value = null;
        localStorage.removeItem('selectedPluginSource');
        // 重新加载插件市场数据
        void refreshPluginMarket();
      }

      toast(tm('market.sourceRemoved'), 'success');
      showRemoveSourceDialog.value = false;
      sourceToRemove.value = null;
    }
  };

  const saveCustomSource = () => {
    const normalizedUrl = sourceUrl.value.trim();

    if (!sourceName.value.trim() || !normalizedUrl) {
      toast(tm('messages.fillSourceNameAndUrl'), 'error');
      return;
    }

    // 检查URL格式
    try {
      new URL(normalizedUrl);
    } catch (_error) {
      toast(tm('messages.invalidUrl'), 'error');
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
          localStorage.setItem('selectedPluginSource', selectedSource.value);
          // 重新加载插件市场数据
          void refreshPluginMarket();
        }
      }
    } else {
      // 添加模式：检查是否已存在
      if (customSources.value.some((source) => source.url === normalizedUrl)) {
        toast(tm('market.sourceExists'), 'error');
        return;
      }

      customSources.value.push({
        name: sourceName.value.trim(),
        url: normalizedUrl,
      });
    }

    void saveCustomSources();
    toast(
      editingSource.value
        ? tm('market.sourceUpdated')
        : tm('market.sourceAdded'),
      'success',
    );

    // 重置表单
    sourceName.value = '';
    sourceUrl.value = '';
    editingSource.value = false;
    originalSourceUrl.value = '';
    showSourceDialog.value = false;
  };

  // 插件市场显示完整插件名称
  const trimExtensionName = () => {
    pluginMarketData.value.forEach((plugin) => {
      if (plugin.name) {
        const name = plugin.name.trim().toLowerCase();
        if (name.startsWith('astrbot_plugin_')) {
          plugin.trimmedName = name.substring(15);
        } else if (name.startsWith('astrbot_') || name.startsWith('astrbot-')) {
          plugin.trimmedName = name.substring(8);
        } else plugin.trimmedName = plugin.name;
      }
    });
  };

  const checkAlreadyInstalled = () => {
    const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
    // 使用 marketplace_name 进行市场匹配（后端已统一为减号格式）
    // 创建映射用于查询已安装插件的详细信息
    const installedByRepo = new Map(
      data
        .filter((ext) => ext.repo)
        .map((ext) => [normalizeInstallUrl(ext.repo).toLowerCase(), ext]),
    );
    const installedByName = new Map(
      data
        .filter((ext) => !ext.repo)
        .map((ext) => [normalizeStr(ext.marketplace_name || ext.name), ext]),
    );

    for (let i = 0; i < pluginMarketData.value.length; i++) {
      const plugin = pluginMarketData.value[i];
      const repoKey = plugin.repo
        ? normalizeInstallUrl(plugin.repo).toLowerCase()
        : undefined;
      const matchedInstalled =
        (repoKey && installedByRepo.get(repoKey)) ||
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

      plugin.installed = Boolean(matchedInstalled);
    }

    const installed = [];
    const notInstalled = [];
    for (let i = 0; i < pluginMarketData.value.length; i++) {
      if (pluginMarketData.value[i].installed) {
        installed.push(pluginMarketData.value[i]);
      } else {
        notInstalled.push(pluginMarketData.value[i]);
      }
    }
    pluginMarketData.value = notInstalled.concat(installed);
  };

  const normalizeAstrBotVersionSpec = (value: unknown) =>
    String(value || '').trim();

  const normalizeVersionParts = (value: unknown): number[] => {
    const version = String(value || '')
      .trim()
      .replace(/^v/i, '')
      .split(/[+-]/)[0];
    const parts = version.split('.').map((part) => {
      const match = part.match(/^\d+/);
      return match ? Number.parseInt(match[0], 10) : 0;
    });
    return parts.length ? parts : [0];
  };

  const compareVersions = (left: unknown, right: unknown): number => {
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

  const getSupportedReleaseUpperBound = (version: unknown): string => {
    const parts = normalizeVersionParts(version);
    if (parts.length <= 2) {
      return `${(parts[0] || 0) + 1}.0`;
    }
    return `${parts[0] || 0}.${(parts[1] || 0) + 1}.0`;
  };

  const checkVersionConstraint = (
    currentVersion: string,
    constraint: string,
  ): boolean | null => {
    const match = constraint.match(/^(<=|>=|==|!=|~=|<|>|=)\s*(.+)$/);
    if (!match) return null;

    const [, operator, targetVersion] = match;
    const normalizedTarget = targetVersion.trim();
    if (!normalizedTarget) return null;
    if (!/^v?\d+/.test(normalizedTarget)) return null;

    if (operator === '~=') {
      return (
        compareVersions(currentVersion, normalizedTarget) >= 0 &&
        compareVersions(
          currentVersion,
          getSupportedReleaseUpperBound(normalizedTarget),
        ) < 0
      );
    }

    const comparison = compareVersions(currentVersion, normalizedTarget);
    if (operator === '>' || operator === '>=') {
      return operator === '>' ? comparison > 0 : comparison >= 0;
    }
    if (operator === '<' || operator === '<=') {
      return operator === '<' ? comparison < 0 : comparison <= 0;
    }
    if (operator === '!=') return comparison !== 0;
    return comparison === 0;
  };

  const checkAstrBotVersionSupport = (
    versionSpec: unknown,
    currentVersion: string,
  ): VersionSupportResult => {
    const normalizedSpec = normalizeAstrBotVersionSpec(versionSpec);
    if (!normalizedSpec) {
      return { checked: false, supported: true, message: '' };
    }
    if (!currentVersion) {
      return { checked: false, supported: true, message: '' };
    }

    const constraints = normalizedSpec
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
    if (!constraints.length) {
      return { checked: false, supported: true, message: '' };
    }

    for (const constraint of constraints) {
      const supported = checkVersionConstraint(currentVersion, constraint);
      if (supported === null) {
        return {
          checked: true,
          supported: false,
          message:
            'Invalid astrbot_version. Use a PEP 440 range, e.g. >=4.16,<5.',
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

    return { checked: true, supported: true, message: '' };
  };

  const annotateMarketVersionSupport = async () => {
    const currentVersion =
      commonStore.astrbotVersion ||
      (await commonStore.fetchAstrBotVersion().catch(() => ''));
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

  const showVersionSupportWarning = (message: string) => {
    versionSupportDialog.message = message;
    versionSupportDialog.show = true;
  };

  const refreshExtensionsAfterInstallFailure = async () => {
    try {
      await getExtensions();
    } catch (error) {
      console.debug(
        'Failed to refresh extensions after install failure:',
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

  const handleInstallResponse = async (
    resData: InstallResponseData,
  ): Promise<boolean> => {
    if (
      resData.status === 'warning' &&
      resData.data?.warning_type === 'astrbot_version_unsupported'
    ) {
      toast(resData.message, 'warning');
      showVersionSupportWarning(String(resData.message || ''));
      await refreshExtensionsAfterInstallFailure();
      return false;
    }

    if (resData.status === 'error') {
      toast(resData.message, 'error');
      await refreshExtensionsAfterInstallFailure();
      return false;
    }

    return true;
  };

  const performInstallRequest = async ({
    source,
    ignoreVersionCheck,
    stepUp,
  }: {
    source: UploadTab;
    ignoreVersionCheck: boolean;
    stepUp: string;
  }) => {
    const shouldIgnoreVersionCheck = ignoreVersionCheck === true;
    if (source === 'file') {
      if (!upload_file.value) {
        throw new Error('Upload file is required.');
      }
      const formData = new FormData();
      formData.append('file', upload_file.value);
      formData.append('ignore_version_check', String(shouldIgnoreVersionCheck));
      return pluginApi.installUpload(formData, stepUp);
    }

    const urlPayload: Parameters<typeof pluginApi.installUrl>[0] = {
      url: extension_url.value,
      download_url: selectedInstallDownloadUrl.value,
      proxy: selectedInstallDownloadUrl.value ? '' : getSelectedGitHubProxy(),
      ignore_version_check: shouldIgnoreVersionCheck,
    };
    const githubPayload: Parameters<typeof pluginApi.installGithub>[0] = {
      repository: extension_url.value,
      download_url: selectedInstallDownloadUrl.value,
      proxy: selectedInstallDownloadUrl.value ? '' : getSelectedGitHubProxy(),
      ignore_version_check: shouldIgnoreVersionCheck,
    };

    return installUsesGithubSource.value
      ? pluginApi.installGithub(githubPayload, stepUp)
      : pluginApi.installUrl(urlPayload, stepUp);
  };

  const finalizeSuccessfulInstall = async (
    resData: InstallResponseData,
    source: UploadTab,
  ) => {
    if (source === 'file') {
      upload_file.value = null;
    } else {
      extension_url.value = '';
    }

    toast(resData.message, 'success');
    dialog.value = false;
    selectedMarketInstallPlugin.value = null;
    await getExtensions();
    checkAlreadyInstalled();
    checkUpdate();

    viewReadme({
      name: String(resData.data?.name || ''),
      repo: typeof resData.data?.repo === 'string' ? resData.data.repo : null,
    });

    await checkAndPromptConflicts();
  };

  const newExtension = async (ignoreVersionCheck = false) => {
    const shouldIgnoreVersionCheck = ignoreVersionCheck === true;
    if (extension_url.value === '' && upload_file.value === null) {
      toast(tm('messages.fillUrlOrFile'), 'error');
      return;
    }

    if (extension_url.value !== '' && upload_file.value !== null) {
      toast(tm('messages.dontFillBoth'), 'error');
      return;
    }
    const source = upload_file.value !== null ? 'file' : 'url';
    loading_.value = true;

    try {
      const stepUp = await requestPluginInstallStepUp();
      const res = await performInstallRequest({
        source,
        ignoreVersionCheck: shouldIgnoreVersionCheck,
        stepUp,
      });
      loading_.value = false;

      const canContinue = await handleInstallResponse(res.data);
      if (!canContinue) return;

      await finalizeSuccessfulInstall(res.data, source);
    } catch (err) {
      loading_.value = false;
      const message = resolveErrorMessage(err, tm('messages.installFailed'));
      toast(message, 'error');
      await refreshExtensionsAfterInstallFailure();
    }
  };

  const normalizePlatformList = (platforms: unknown): string[] => {
    if (!Array.isArray(platforms)) return [];
    return platforms.filter((item): item is string => typeof item === 'string');
  };

  const getPlatformDisplayList = (platforms: unknown): string[] => {
    return normalizePlatformList(platforms).map((platformId) =>
      getPlatformDisplayName(platformId),
    );
  };

  const resolveSelectedInstallPlugin = () => {
    if (selectedMarketInstallPlugin.value?.repo === extension_url.value) {
      return selectedMarketInstallPlugin.value;
    }
    for (const plugin of pluginMarketData.value) {
      if (plugin.repo === extension_url.value) {
        return plugin;
      }
    }
    return null;
  };

  const selectedInstallPlugin = computed(() => resolveSelectedInstallPlugin());

  const selectedUpdateExtension = computed(() =>
    getInstalledExtensionByName(updateConfirmDialog.extensionName),
  );

  const selectedUpdateMarketPlugin = computed(() =>
    findMarketPluginForExtension(selectedUpdateExtension.value),
  );

  const selectedUpdateDownloadUrl = computed(() =>
    String(selectedUpdateMarketPlugin.value?.download_url || '').trim(),
  );

  const selectedUpdateSourceUrl = computed(
    () =>
      selectedUpdateDownloadUrl.value ||
      String(selectedUpdateExtension.value?.repo || '').trim(),
  );

  const updateUsesGithubSource = computed(
    () =>
      !selectedUpdateDownloadUrl.value &&
      isGithubRepoUrl(selectedUpdateSourceUrl.value),
  );

  const checkInstallVersionSupport = async () => {
    installSupport.checked = false;
    installSupport.supported = true;
    installSupport.message = '';

    const plugin = selectedInstallPlugin.value;
    if (!plugin?.astrbot_version || uploadTab.value !== 'url') {
      return;
    }

    const currentVersion =
      commonStore.astrbotVersion ||
      (await commonStore.fetchAstrBotVersion().catch(() => ''));
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
      checkUpdate();
      refreshRandomPlugins();
      currentPage.value = 1; // 重置到第一页

      toast(tm('messages.refreshSuccess'), 'success');
    } catch (err) {
      toast(`${tm('messages.refreshFailed')} ${err}`, 'error');
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
      void loadCustomSources();

      // 检查是否有 open_config 参数
      const plugin_name = Array.isArray(route.query.open_config)
        ? route.query.open_config[0]
        : route.query.open_config;
      if (plugin_name) {
        console.log(`Opening config for plugin: ${plugin_name}`);
        void openExtensionConfig(plugin_name);
      }

      const data = await commonStore.getPluginCollections(
        false,
        selectedSource.value,
      );
      pluginMarketData.value = data;
      trimExtensionName();
      checkAlreadyInstalled();
      await annotateMarketVersionSupport();
      checkUpdate();
      refreshRandomPlugins();
    } catch (err) {
      toast(`${tm('messages.getMarketDataFailed')} ${err}`, 'error');
    } finally {
      loading_.value = false;
    }
  });

  // 处理语言切换事件，重新加载插件配置以获取插件的 i18n 数据
  const handleLocaleChange = () => {
    // 如果配置对话框是打开的，重新加载当前插件的配置
    if (configDialog.value && currentConfigPlugin.value) {
      void openExtensionConfig(currentConfigPlugin.value);
    }
  };

  // 监听语言切换事件
  window.addEventListener('astrbot-locale-changed', handleLocaleChange);

  // 清理事件监听器
  onUnmounted(() => {
    window.removeEventListener('astrbot-locale-changed', handleLocaleChange);
  });

  // 搜索防抖处理
  let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
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
      if (!dialogOpen || currentUploadTab !== 'url') {
        installSupport.checked = false;
        installSupport.supported = true;
        installSupport.message = '';
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
    if (activeTab.value === 'market') {
      currentPage.value = 1;
    }
  });

  watch(
    marketCategoryItems,
    (newItems) => {
      const validValues = new Set(newItems.map((item) => item.value));
      if (!validValues.has(marketCategoryFilter.value)) {
        marketCategoryFilter.value = 'all';
      }
    },
    { immediate: true },
  );

  return {
    commonStore,
    t,
    tm,
    getRaw,
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
    getMarketCategoryLabel,
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
    updatePluginLogLevel,
    pluginLogLevelSaving,
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
    stepUpDialogOpen,
    stepUpLoading,
    stepUpErrorMessage,
    submitStepUp,
    cancelStepUp,
    checkInstallVersionSupport,
    refreshPluginMarket,
    handleLocaleChange,
    searchDebounceTimer,
  };
};
