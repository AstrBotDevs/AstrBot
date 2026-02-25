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
import { useExtensionPage } from "./extension/useExtensionPage";

const pageState = useExtensionPage();

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
} = pageState;
</script>

<template>
  <v-row>
    <v-col cols="12" md="12">
      <v-card variant="flat" style="background-color: transparent">
        <!-- 标签页 -->
        <v-card-text style="padding: 0px 12px">
          <!-- 已安装插件标签页内容 -->
          <InstalledPluginsTab :state="pageState" />

          <!-- 指令面板标签页内容 -->
          <v-tab-item v-show="activeTab === 'components'">
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
          <v-tab-item v-show="activeTab === 'mcp'">
            <div class="mb-4 pt-4 pb-4">
              <div class="d-flex align-center flex-wrap" style="gap: 12px">
                <h2 class="text-h2 mb-0">{{ tm("tabs.installedMcpServers") }}</h2>
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
          </v-tab-item>

          <!-- Skills 标签页内容 -->
          <v-tab-item v-show="activeTab === 'skills'">
            <div class="mb-4 pt-4 pb-4">
              <div class="d-flex align-center flex-wrap" style="gap: 12px">
                <h2 class="text-h2 mb-0">{{ tm("tabs.skills") }}</h2>
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
          </v-tab-item>

          <!-- 插件市场标签页内容 -->
          <MarketPluginsTab :state="pageState" />

          <v-row v-if="loading_">
            <v-col cols="12" class="d-flex justify-center">
              <v-progress-circular
                indeterminate
                color="primary"
                size="48"
              ></v-progress-circular>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-col>

    <v-col v-if="activeTab === 'market'" cols="12" md="12">
      <div class="d-flex align-center justify-center mt-4 mb-4 gap-4">
        <v-btn
          variant="text"
          prepend-icon="mdi-book-open-variant"
          href="https://astrbot.app/dev/plugin.html"
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

  <!-- 插件信息对话框 -->
  <v-dialog v-model="showPluginInfoDialog" width="1200">
    <v-card>
      <v-card-title class="text-h5"
        >{{ selectedPlugin.name }} {{ tm("buttons.viewInfo") }}</v-card-title
      >
      <v-card-text>
        <v-data-table
          style="font-size: 17px"
          :headers="plugin_handler_info_headers"
          :items="selectedPlugin.handlers"
          item-key="name"
        >
          <template v-slot:header.id="{ column }">
            <p style="font-weight: bold">{{ column.title }}</p>
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
            <span style="font-weight: bold">{{ item.cmd }}</span>
          </template>
        </v-data-table>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn
          color="blue-darken-1"
          variant="text"
          @click="showPluginInfoDialog = false"
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
          {{ tm("dialogs.updateAllConfirm.message", { count: updatableExtensions.length }) }}
        </p>
      </v-card-text>
      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn
          variant="text"
          @click="cancelUpdateAll"
        >{{ tm("buttons.cancel") }}</v-btn>
        <v-btn
          color="warning"
          variant="flat"
          @click="confirmUpdateAll"
        >{{ tm("dialogs.updateAllConfirm.confirm") }}</v-btn>
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
      <div class="v-card__loader">
        <v-progress-linear
          :indeterminate="loading_"
          color="primary"
          height="2"
          :active="loading_"
        ></v-progress-linear>
      </div>

      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ tm("dialogs.install.title") }}
      </v-card-title>

      <div class="v-card-text">
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
                  v-if="normalizePlatformList(selectedInstallPlugin.support_platforms).length"
                  size="small"
                  color="info"
                  variant="outlined"
                  class="mb-2"
                >
                  {{ tm("card.status.supportPlatform") }}:
                  {{
                    getPlatformDisplayList(selectedInstallPlugin.support_platforms).join(
                      ", ",
                    )
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
                  class="mt-2"
                >
                  {{ installCompat.message }}
                </v-alert>
              </div>

              <ProxySelector></ProxySelector>
            </div>
          </v-window-item>
        </v-window>
      </div>

      <div class="v-card-actions">
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="dialog = false">{{
          tm("buttons.cancel")
        }}</v-btn>
        <v-btn color="primary" variant="text" @click="newExtension">{{
          tm("buttons.install")
        }}</v-btn>
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
              <v-icon icon="mdi-shield-check" size="small" class="mr-2"></v-icon>
            </template>
            <v-list-item-title>{{ tm("market.defaultSource") }}</v-list-item-title>
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
              <v-icon icon="mdi-link-variant" size="small" class="mr-2"></v-icon>
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
        <v-btn color="primary" variant="text" @click="showSourceManagerDialog = false">{{
          tm("buttons.close")
        }}</v-btn>
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
</style>
