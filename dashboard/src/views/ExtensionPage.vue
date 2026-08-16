<script setup>
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import ReadmeDialog from '@/components/shared/ReadmeDialog.vue';
import ProxySelector from '@/components/shared/ProxySelector.vue';
import UninstallConfirmDialog from '@/components/shared/UninstallConfirmDialog.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import McpServersSection from '@/components/extension/McpServersSection.vue';
import SkillsSection from '@/components/extension/SkillsSection.vue';
import ComponentPanel from '@/components/extension/componentPanel/index.vue';
import InstalledPluginsTab from './extension/InstalledPluginsTab.vue';
import MarketPluginsTab from './extension/MarketPluginsTab.vue';
import PluginDetailPage from './extension/PluginDetailPage.vue';
import { useExtensionPage } from './extension/useExtensionPage';
import { computed } from 'vue';
import defaultPluginIcon from '/favicon.svg';
import { usePluginI18n } from '@/utils/pluginI18n';

const pageState = useExtensionPage();
const { pluginName, pluginDesc } = usePluginI18n();

const {
  t,
  tm,
  router,
  route,
  conflictDialog,
  handleConflictConfirm,
  fileInput,
  activeTab,
  extractTabFromHash,
  extension_data,
  snack_message,
  snack_show,
  snack_success,
  configDialog,
  extension_config,
  pluginMarketData,
  loadingDialog,
  curr_namespace,
  readmeDialog,
  forceUpdateDialog,
  updateConfirmDialog,
  updateAllConfirmDialog,
  changelogDialog,
  loading_,
  dangerConfirmDialog,
  selectedMarketInstallPlugin,
  installSupport,
  versionSupportDialog,
  showUninstallDialog,
  showSourceDialog,
  showSourceManagerDialog,
  sourceName,
  sourceUrl,
  customSources,
  selectedSource,
  showRemoveSourceDialog,
  sourceToRemove,
  editingSource,
  extension_url,
  dialog,
  upload_file,
  uploadTab,
  updatableExtensions,
  resetLoadingDialog,
  handleUninstallConfirm,
  closeUpdateConfirmDialog,
  confirmUpdatePlugin,
  confirmUpdateAll,
  cancelUpdateAll,
  confirmForceUpdate,
  updateConfig,
  updatePluginLogLevel,
  pluginLogLevelSaving,
  closeInstallDialog,
  confirmDangerInstall,
  cancelDangerInstall,
  addCustomSource,
  selectPluginSource,
  sourceSelectItems,
  editCustomSource,
  removeCustomSource,
  confirmRemoveSource,
  saveCustomSource,
  continueInstallIgnoringVersionWarning,
  cancelInstallOnVersionWarning,
  newExtension,
  normalizePlatformList,
  getPlatformDisplayList,
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
} = pageState;

const logLevelItems = computed(() => [
  { title: tm('dialogs.config.coreSettings.followGlobal'), value: null },
  { title: 'DEBUG', value: 'DEBUG' },
  { title: 'INFO', value: 'INFO' },
  { title: 'WARNING', value: 'WARNING' },
  { title: 'ERROR', value: 'ERROR' },
  { title: 'CRITICAL', value: 'CRITICAL' },
]);

const selectedPluginId = computed(() => {
  const pluginId = route.params.pluginId;
  return Array.isArray(pluginId) ? pluginId[0] : pluginId || '';
});

const selectedDetailTab = computed(
  () => extractTabFromHash(route.hash) || 'installed',
);

const selectedInstalledPlugin = computed(() => {
  if (!selectedPluginId.value) return null;
  const data = Array.isArray(extension_data?.data) ? extension_data.data : [];
  for (const plugin of data) {
    if (plugin.name === selectedPluginId.value) {
      return plugin;
    }
  }
  return null;
});

const selectedMarketPlugin = computed(() => {
  const market = Array.isArray(pluginMarketData.value)
    ? pluginMarketData.value
    : [];
  const installedPlugin = selectedInstalledPlugin.value;
  const repo = installedPlugin?.repo?.toLowerCase();
  for (const item of market) {
    if (item.name === selectedPluginId.value) {
      return item;
    }
  }
  if (repo) {
    for (const item of market) {
      if (item.repo?.toLowerCase() === repo) {
        return item;
      }
    }
  }
  return null;
});

const selectedDetailPlugin = computed(() => {
  if (selectedDetailTab.value === 'market' && selectedMarketPlugin.value) {
    return selectedMarketPlugin.value;
  }
  return selectedInstalledPlugin.value || selectedMarketPlugin.value;
});

const installDialogPluginName = computed(() =>
  selectedInstallPlugin.value ? pluginName(selectedInstallPlugin.value) : '',
);

const installDialogPluginDesc = computed(() =>
  String(
    selectedInstallPlugin.value
      ? pluginDesc(
          selectedInstallPlugin.value,
          selectedInstallPlugin.value.desc ||
            selectedInstallPlugin.value.description ||
            '',
        )
      : '',
  ).trim(),
);

const installDialogPluginAuthor = computed(() => {
  const author = selectedInstallPlugin.value?.author;
  if (Array.isArray(author)) return author.join(', ');
  if (author && typeof author === 'object') return author.name || '';
  return typeof author === 'string' ? author.trim() : '';
});

const installDialogPluginLogo = computed(() => {
  const logo = selectedInstallPlugin.value?.logo;
  return typeof logo === 'string' && logo.trim() ? logo : defaultPluginIcon;
});

const updateDialogPlugin = computed(
  () => selectedUpdateMarketPlugin.value || selectedUpdateExtension.value,
);

const updateDialogPluginName = computed(() =>
  updateDialogPlugin.value ? pluginName(updateDialogPlugin.value) : '',
);

const updateDialogCurrentVersion = computed(() =>
  String(selectedUpdateExtension.value?.version || '').trim(),
);

const updateDialogTargetVersion = computed(() =>
  String(selectedUpdateMarketPlugin.value?.version || '').trim(),
);

const updateDialogPluginLogo = computed(() => {
  const logo =
    selectedUpdateMarketPlugin.value?.logo ||
    selectedUpdateExtension.value?.logo;
  return typeof logo === 'string' && logo.trim() ? logo : defaultPluginIcon;
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
          selectedDetailTab === 'market'
            ? tm('tabs.market')
            : tm('titles.installedAstrBotPlugins')
        }}
        <v-icon icon="mdi-chevron-right" size="24" class="mx-1" />
        {{ selectedPluginId }}
      </h2>
    </div>
    <v-alert type="warning" variant="tonal">
      {{ tm('detail.notFound') }}
    </v-alert>
  </div>

  <v-row v-else class="extension-page">
    <v-col cols="12" md="12">
      <v-card variant="flat" class="extension-page__content">
        <!-- 标签页 -->
        <v-card-text class="extension-page__body">
          <!-- 已安装插件标签页内容 -->
          <InstalledPluginsTab :state="pageState" />

          <!-- 指令面板标签页内容 -->
          <div v-if="activeTab === 'components'">
            <div class="mb-4 pt-4 pb-4">
              <div class="inline-control-row">
                <h2 class="text-h2 mb-0">{{ tm('tabs.handlersOperation') }}</h2>
              </div>
            </div>
            <v-card class="extension-page__section" variant="flat">
              <v-card-text class="pa-0">
                <ComponentPanel :active="activeTab === 'components'" />
              </v-card-text>
            </v-card>
          </div>

          <!-- 已安装的 MCP 服务器标签页内容 -->
          <div v-if="activeTab === 'mcp'">
            <div class="extension-detail-width">
              <div class="mb-4 pt-4 pb-4">
                <div class="extension-page__section-heading">
                  <h2 class="text-h2 mb-0">
                    {{ tm('tabs.installedMcpServers') }}
                  </h2>
                  <div class="text-body-2 text-medium-emphasis">
                    {{ t('features.tooluse.mcpServers.description') }}
                  </div>
                </div>
              </div>
              <v-card class="extension-page__section" variant="flat">
                <v-card-text class="pa-0">
                  <McpServersSection />
                </v-card-text>
              </v-card>
            </div>
          </div>

          <!-- Skills 标签页内容 -->
          <div v-if="activeTab === 'skills'">
            <div class="extension-detail-width">
              <div class="mb-4 pt-4 pb-4">
                <div class="extension-page__section-heading">
                  <h2 class="text-h2 mb-0">{{ tm('tabs.skills') }}</h2>
                  <div class="text-body-2 text-medium-emphasis">
                    {{ tm('skills.runtimeHint') }}
                  </div>
                </div>
              </div>
              <v-card class="extension-page__section" variant="flat">
                <v-card-text class="pa-0">
                  <SkillsSection />
                </v-card-text>
              </v-card>
            </div>
          </div>

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
          {{ tm('market.devDocs') }}
        </v-btn>
        <div class="extension-page__market-divider"></div>
        <v-btn
          variant="text"
          prepend-icon="mdi-github"
          href="https://github.com/AstrBotDevs/AstrBot_Plugins_Collection"
          target="_blank"
          color="primary"
          class="text-none"
        >
          {{ tm('market.submitRepo') }}
        </v-btn>
      </div>
    </v-col>
  </v-row>

  <!-- 配置对话框 -->
  <v-dialog v-model="configDialog" max-width="900" scrollable>
    <v-card class="app-dialog extension-config-dialog__card">
      <v-card-title class="text-h2 pa-4 pl-6 pb-0">{{
        tm('dialogs.config.title')
      }}</v-card-title>
      <v-card-text class="extension-config-dialog__content">
        <div
          class="d-flex align-center justify-space-between flex-wrap ga-3 mb-4"
        >
          <div>
            <div class="text-subtitle-1 font-weight-medium">
              {{ tm('dialogs.config.coreSettings.logLevel') }}
            </div>
            <div class="text-caption text-medium-emphasis">
              {{ tm('dialogs.config.coreSettings.logLevelHint') }}
            </div>
          </div>
          <v-select
            :model-value="extension_config.log_level"
            :items="logLevelItems"
            :loading="pluginLogLevelSaving"
            density="compact"
            variant="outlined"
            hide-details
            class="extension-config-dialog__log-level"
            @update:model-value="updatePluginLogLevel"
          />
        </div>
        <v-divider class="mb-4" />
        <div class="extension-config-dialog__panel">
          <AstrBotConfig
            v-if="extension_config.metadata"
            :metadata="extension_config.metadata"
            :iterable="extension_config.config"
            :metadata-key="curr_namespace"
            :plugin-name="curr_namespace"
            :plugin-i18n="extension_config.i18n"
            enable-default-reset
          />
          <p v-else>{{ tm('dialogs.config.noConfig') }}</p>
        </div>
      </v-card-text>
      <v-card-actions class="extension-config-dialog__actions">
        <v-spacer></v-spacer>
        <v-btn color="primary" variant="text" @click="updateConfig">{{
          tm('buttons.saveAndClose')
        }}</v-btn>
        <v-btn color="primary" variant="text" @click="configDialog = false">{{
          tm('buttons.close')
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 加载对话框 -->
  <v-dialog
    v-model="loadingDialog.show"
    width="700"
    persistent
    transition="dialog-transition"
  >
    <v-card class="app-dialog">
      <v-card-title class="text-h5">{{ loadingDialog.title }}</v-card-title>
      <v-card-text class="extension-loading-dialog__content">
        <v-progress-linear
          v-if="loadingDialog.statusCode === 0"
          indeterminate
          color="primary"
          class="mb-4"
        ></v-progress-linear>

        <v-fade-transition>
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
            <div class="text-h4 font-weight-bold">
              {{ loadingDialog.result }}
            </div>
          </div>
        </v-fade-transition>

        <div class="extension-loading-dialog__logs">
          <h3>{{ tm('dialogs.loading.logs') }}</h3>
          <ConsoleDisplayer
            history-num="10"
            class="extension-loading-dialog__console"
          >
          </ConsoleDisplayer>
        </div>
      </v-card-text>

      <v-divider></v-divider>

      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn color="primary" variant="text" @click="resetLoadingDialog">{{
          tm('buttons.close')
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-snackbar
    v-model="snack_show"
    :timeout="2000"
    elevation="4"
    :color="snack_success"
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

  <DashboardStepUpDialog
    v-model="stepUpDialogOpen"
    :loading="stepUpLoading"
    :error-message="stepUpErrorMessage"
    @confirm="submitStepUp"
    @cancel="cancelStepUp"
  />

  <!-- 更新全部插件确认对话框 -->
  <v-dialog v-model="updateAllConfirmDialog.show" max-width="420">
    <v-card class="app-dialog">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon color="warning" class="mr-2">mdi-update</v-icon>
        {{ tm('dialogs.updateAllConfirm.title') }}
      </v-card-title>
      <v-card-text>
        <p class="text-body-1">
          {{
            tm('dialogs.updateAllConfirm.message', {
              count: updatableExtensions.length,
            })
          }}
        </p>
      </v-card-text>
      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelUpdateAll">{{
          tm('buttons.cancel')
        }}</v-btn>
        <v-btn color="warning" variant="flat" @click="confirmUpdateAll">{{
          tm('dialogs.updateAllConfirm.confirm')
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 指令冲突提示对话框 -->
  <v-dialog v-model="conflictDialog.show" max-width="420">
    <v-card class="app-dialog">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon color="warning" class="mr-2">mdi-alert-circle</v-icon>
        {{ tm('conflicts.title') }}
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
          <span class="ml-2 text-body-1">{{ tm('conflicts.pairs') }}</span>
        </div>
        <p class="text-body-2 text-medium-emphasis">
          {{ tm('conflicts.message') }}
        </p>
      </v-card-text>
      <v-card-actions class="pa-4 pt-2">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="conflictDialog.show = false">{{
          tm('conflicts.later')
        }}</v-btn>
        <v-btn color="warning" variant="flat" @click="handleConflictConfirm">
          {{ tm('conflicts.goToManage') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

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
        <v-btn @click="cancelDangerInstall">
          {{ tm('dialogs.danger_warning.cancel') }}
        </v-btn>
        <v-btn color="warning" @click="confirmDangerInstall">
          {{ tm('dialogs.danger_warning.confirm') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 版本不兼容警告对话框 -->
  <v-dialog v-model="versionSupportDialog.show" width="520" persistent>
    <v-card>
      <v-card-title class="text-h5 d-flex align-center">
        <v-icon color="warning" class="mr-2">mdi-alert</v-icon>
        {{ tm('dialogs.versionSupport.title') }}
      </v-card-title>
      <v-card-text>
        <div class="mb-2">{{ tm('dialogs.versionSupport.message') }}</div>
        <div class="text-medium-emphasis">
          {{ versionSupportDialog.message }}
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn @click="cancelInstallOnVersionWarning">
          {{ tm('dialogs.versionSupport.cancel') }}
        </v-btn>
        <v-btn color="warning" @click="continueInstallIgnoringVersionWarning">
          {{ tm('dialogs.versionSupport.confirm') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 上传插件对话框 -->
  <v-dialog v-model="dialog" width="500">
    <v-card class="app-dialog">
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ tm('dialogs.install.title') }}
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
                {{ tm('detail.info.author') }}: {{ installDialogPluginAuthor }}
              </div>
            </div>
          </div>

          <v-divider class="my-4" />

          <div
            v-if="installDialogPluginDesc"
            class="market-install-confirm__section"
          >
            <div class="market-install-confirm__section-title">
              {{ tm('table.headers.description') }}
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
              {{ tm('card.status.astrbotVersion') }}:
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
              {{ tm('card.status.supportPlatform') }}:
              {{
                getPlatformDisplayList(
                  selectedInstallPlugin.support_platforms,
                ).join(', ')
              }}
            </v-chip>
            <v-alert
              v-if="
                selectedInstallPlugin.astrbot_version &&
                installSupport.checked &&
                !installSupport.supported
              "
              type="warning"
              variant="tonal"
              density="comfortable"
              class="market-install-alert mt-2 mb-3"
            >
              {{ installSupport.message }}
            </v-alert>
          </div>

          <div
            v-if="selectedInstallSourceUrl"
            class="market-install-confirm__section-title mt-4"
          >
            {{ tm('dialogs.install.sectionTitle') }}
          </div>
          <div
            v-if="selectedInstallSourceUrl"
            class="market-install-source text-caption text-medium-emphasis mb-3"
          >
            <div>{{ tm('dialogs.install.downloadSource') }}</div>
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
            {{ tm('dialogs.install.githubSecurityWarning') }}
          </v-alert>

          <ProxySelector v-if="!selectedInstallDownloadUrl" class="mt-4" />
        </div>

        <template v-else>
          <v-tabs v-model="uploadTab" color="primary">
            <v-tab value="file">{{ tm('dialogs.install.fromFile') }}</v-tab>
            <v-tab value="url">{{ tm('dialogs.install.fromUrl') }}</v-tab>
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
                  elevation="2"
                  @click="$refs.fileInput.click()"
                >
                  {{ tm('buttons.selectFile') }}
                </v-btn>

                <div class="text-body-2 text-medium-emphasis mt-2">
                  {{ tm('messages.supportedFormats') }}
                </div>

                <div v-if="upload_file" class="mt-4 text-center">
                  <v-chip
                    color="primary"
                    size="large"
                    closable
                    @click:close="upload_file = null"
                  >
                    {{ upload_file.name }}
                    <template #append>
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
                  class="mb-4"
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
                    {{ tm('card.status.astrbotVersion') }}:
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
                    {{ tm('card.status.supportPlatform') }}:
                    {{
                      getPlatformDisplayList(
                        selectedInstallPlugin.support_platforms,
                      ).join(', ')
                    }}
                  </v-chip>
                  <v-alert
                    v-if="
                      selectedInstallPlugin.astrbot_version &&
                      installSupport.checked &&
                      !installSupport.supported
                    "
                    type="warning"
                    variant="tonal"
                    density="comfortable"
                    class="market-install-alert mt-2 mb-3"
                  >
                    {{ installSupport.message }}
                  </v-alert>
                </div>

                <div
                  v-if="selectedInstallSourceUrl"
                  class="market-install-confirm__section-title mt-4"
                >
                  {{ tm('dialogs.install.sectionTitle') }}
                </div>
                <div
                  v-if="selectedInstallSourceUrl"
                  class="market-install-source text-caption text-medium-emphasis mb-3"
                >
                  <div>{{ tm('dialogs.install.downloadSource') }}</div>
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
                  {{ tm('dialogs.install.githubSecurityWarning') }}
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
        <v-btn variant="text" @click="closeInstallDialog">{{
          tm('buttons.cancel')
        }}</v-btn>
        <v-btn
          color="primary"
          variant="text"
          :loading="loading_"
          :disabled="loading_"
          @click="newExtension()"
          >{{ tm('buttons.install') }}</v-btn
        >
      </div>
    </v-card>
  </v-dialog>

  <!-- 插件源管理对话框 -->
  <v-dialog v-model="showSourceManagerDialog" width="640" scrollable>
    <v-card class="app-dialog source-manager-dialog__card">
      <v-card-title class="text-h3 pa-4 pl-6">{{
        tm('market.sourceManagement')
      }}</v-card-title>
      <v-card-text class="source-manager-dialog__content">
        <v-select
          :model-value="selectedSource || '__default__'"
          :items="sourceSelectItems"
          :label="tm('market.currentSource')"
          variant="outlined"
          prepend-inner-icon="mdi-source-branch"
          hide-details
          class="mb-4"
          @update:model-value="
            selectPluginSource($event === '__default__' ? null : $event)
          "
        ></v-select>

        <div class="d-flex align-center justify-space-between mb-2">
          <div class="text-subtitle-2">{{ tm('market.availableSources') }}</div>
          <v-btn
            size="small"
            color="primary"
            variant="tonal"
            prepend-icon="mdi-plus"
            @click="addCustomSource"
          >
            {{ tm('market.addSource') }}
          </v-btn>
        </div>

        <v-list density="compact" nav class="pa-0">
          <v-list-item
            rounded="md"
            color="primary"
            :active="selectedSource === null"
            @click="selectPluginSource(null)"
          >
            <template #prepend>
              <v-icon
                icon="mdi-shield-check"
                size="small"
                class="mr-2"
              ></v-icon>
            </template>
            <v-list-item-title>{{
              tm('market.defaultSource')
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
            <template #prepend>
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
            <template #append>
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
      <v-card-actions class="source-manager-dialog__actions">
        <v-spacer></v-spacer>
        <v-btn
          color="primary"
          variant="text"
          @click="showSourceManagerDialog = false"
          >{{ tm('buttons.close') }}</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 添加/编辑自定义插件源对话框 -->
  <v-dialog v-model="showSourceDialog" width="500">
    <v-card>
      <v-card-title class="text-h5">{{
        editingSource ? tm('market.editSource') : tm('market.addSource')
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
            {{ tm('messages.enterJsonUrl') }}
          </div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="showSourceDialog = false">{{
          tm('buttons.cancel')
        }}</v-btn>
        <v-btn color="primary" variant="text" @click="saveCustomSource">{{
          tm('buttons.save')
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 删除插件源确认对话框 -->
  <v-dialog v-model="showRemoveSourceDialog" width="400">
    <v-card>
      <v-card-title class="text-h5 d-flex align-center">
        <v-icon color="warning" class="mr-2">mdi-alert-circle</v-icon>
        {{ tm('dialogs.uninstall.title') }}
      </v-card-title>
      <v-card-text>
        <div>{{ tm('market.confirmRemoveSource') }}</div>
        <div v-if="sourceToRemove" class="mt-2">
          <strong>{{ sourceToRemove.name }}</strong>
          <div class="text-caption">{{ sourceToRemove.url }}</div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="showRemoveSourceDialog = false">{{
          tm('buttons.cancel')
        }}</v-btn>
        <v-btn color="error" variant="text" @click="confirmRemoveSource">{{
          tm('buttons.deleteSource')
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Update plugin confirmation dialog -->
  <v-dialog v-model="updateConfirmDialog.show" width="500">
    <v-card class="app-dialog">
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ tm('dialogs.update.title') }}
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
                  {{ updateDialogCurrentVersion || tm('status.unknown') }}
                  <v-icon icon="mdi-arrow-right" size="14" class="mx-1" />
                  {{ updateDialogTargetVersion }}
                </template>
                <template v-else>
                  {{ tm('detail.info.version') }}:
                  {{ updateDialogCurrentVersion || tm('status.unknown') }}
                </template>
              </div>
            </div>
          </div>

          <v-divider class="my-4" />

          <div
            v-if="selectedUpdateSourceUrl"
            class="market-install-confirm__section-title"
          >
            {{ tm('dialogs.update.sectionTitle') }}
          </div>
          <div
            v-if="selectedUpdateSourceUrl"
            class="market-install-source text-caption text-medium-emphasis mb-3"
          >
            <div>{{ tm('dialogs.update.downloadSource') }}</div>
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
            {{ tm('dialogs.install.githubSecurityWarning') }}
          </v-alert>

          <ProxySelector v-if="!selectedUpdateDownloadUrl" class="mt-4" />
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="closeUpdateConfirmDialog">
          {{ tm('buttons.cancel') }}
        </v-btn>
        <v-btn color="primary" variant="flat" @click="confirmUpdatePlugin">
          {{ tm('dialogs.update.confirm') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 强制更新确认对话框 -->
  <v-dialog v-model="forceUpdateDialog.show" max-width="420">
    <v-card class="app-dialog">
      <v-card-title class="text-h6 d-flex align-center">
        <v-icon color="info" class="mr-2">mdi-information-outline</v-icon>
        {{ tm('dialogs.forceUpdate.title') }}
      </v-card-title>
      <v-card-text>
        {{ tm('dialogs.forceUpdate.message') }}
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="forceUpdateDialog.show = false">{{
          tm('buttons.cancel')
        }}</v-btn>
        <v-btn color="primary" variant="flat" @click="confirmForceUpdate">{{
          tm('dialogs.forceUpdate.confirm')
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.extension-page__content,
.extension-page__section {
  background: transparent;
}

.extension-page__body {
  padding: 0 var(--astrbot-space-3);
}

.extension-page__section-heading {
  display: flex;
  flex-direction: column;
  gap: var(--astrbot-space-2);
}

.extension-page__market-divider {
  width: 1px;
  height: 24px;
  background: rgb(var(--v-theme-outline-variant));
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
  border-radius: 8px;
  height: 64px;
  object-fit: cover;
  width: 64px;
}

.market-install-confirm__meta {
  min-width: 0;
}

.market-install-confirm__name {
  color: rgb(var(--v-theme-on-surface));
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-install-confirm__author,
.market-install-confirm__desc {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 14px;
  line-height: 20px;
}

.market-install-confirm__section-title {
  color: rgb(var(--v-theme-on-surface));
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  margin-bottom: var(--astrbot-space-2);
}

.market-install-alert {
  font-size: 13px;
  line-height: 18px;
}

.market-install-source {
  min-width: 0;
}

.market-install-source__url {
  overflow-x: auto;
  white-space: nowrap;
}

.source-manager-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 960px);
}

.extension-config-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 960px);
}

.extension-config-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.extension-config-dialog__panel {
  min-height: 0;
  padding-right: 8px;
}

.extension-config-dialog__log-level {
  min-width: 180px;
  max-width: 220px;
}

.extension-config-dialog__actions {
  flex-shrink: 0;
}

.source-manager-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.source-manager-dialog__actions {
  flex-shrink: 0;
}

.extension-loading-dialog__content {
  max-height: calc(100dvh - 200px);
  overflow-y: auto;
}

.extension-loading-dialog__logs {
  margin-top: var(--astrbot-space-8);
}

.extension-loading-dialog__console {
  height: 200px;
  margin: var(--astrbot-space-4) 0 var(--astrbot-space-6);
}
</style>
