<script setup>
import ExtensionCard from "@/components/shared/ExtensionCard.vue";
import PluginSortControl from "@/components/extension/PluginSortControl.vue";
import { normalizeTextInput } from "@/utils/inputValue";
import { computed } from "vue";

const props = defineProps({
  state: {
    type: Object,
    required: true,
  },
});

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
  updateAllConfirmDialog,
  changelogDialog,
  pluginSearch,
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
  failedPluginItems,
  getExtensions,
  reloadFailedPlugin,
  checkUpdate,
  uninstallExtension,
  requestUninstallFailedPlugin,
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
  openInstallDialog,
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
  // 已安装插件排序
  installedSortBy,
  installedSortOrder,
  // 已安装插件置顶
  pinnedExtensionNames,
  isPinnedExtension,
  togglePinnedExtension,
  // 已安装插件排序结果
  sortedInstalledPlugins,
  // 批量操作
  batchSelectionMode,
  selectedPluginNames,
  batchOperationInProgress,
  batchConfirmDialog,
  batchDeleteConfig,
  batchDeleteData,
  toggleBatchSelectionMode,
  exitBatchSelectionMode,
  togglePluginSelection,
  selectAllPlugins,
  deselectAllPlugins,
  invertSelection,
  isPluginSelected,
  showBatchConfirm,
  cancelBatchConfirm,
  confirmBatchOperation,
  batchEnablePlugins,
  batchDisablePlugins,
  batchUninstallPlugins,
} = props.state;

const openPluginDetail = (extension) => {
  if (!extension?.name) return;
  router.push({
    name: "ExtensionDetails",
    params: { pluginId: extension.name },
    hash: "#installed",
  });
};

const openPluginWebui = (extension) => {
  const pages = extension?.pages;
  if (!Array.isArray(pages) || pages.length === 0 || !extension?.name) return;
  router.push({
    name: "PluginPage",
    params: {
      pluginName: extension.name,
      pageName: pages[0],
    },
  });
};

const installedSortItems = computed(() => [
  { title: tm("sort.default"), value: "default" },
  { title: tm("sort.name"), value: "name" },
  { title: tm("sort.author"), value: "author" },
  { title: tm("sort.activated"), value: "activated" },
  { title: tm("sort.updateStatus"), value: "updateStatus" },
]);

const handleCardClick = (extension) => {
  if (batchSelectionMode.value) {
    togglePluginSelection(extension.name);
  } else {
    openPluginDetail(extension);
  }
};

const handleCheckboxClick = (extension) => {
  if (!batchSelectionMode.value) {
    batchSelectionMode.value = true;
  }
  togglePluginSelection(extension.name);
};

const batchConfirmIcon = computed(() => {
  switch (batchConfirmDialog.operation) {
    case "enable": return "mdi-check-circle";
    case "disable": return "mdi-close-circle";
    case "uninstall": return "mdi-delete";
    default: return "mdi-help-circle";
  }
});

const batchConfirmColor = computed(() => {
  switch (batchConfirmDialog.operation) {
    case "enable": return "success";
    case "disable": return "warning";
    case "uninstall": return "error";
    default: return "primary";
  }
});

const batchConfirmTitle = computed(() => {
  const op = batchConfirmDialog.operation;
  return tm(`batch.confirmTitle.${op}`) || "";
});

const batchConfirmMessage = computed(() => {
  const op = batchConfirmDialog.operation;
  const opLabel = tm(`batch.confirmTitle.${op}`) || "";
  return tm("batch.confirmMessage", { operation: opLabel, count: batchConfirmDialog.count });
});
</script>

<template>
  <v-tab-item v-show="activeTab === 'installed'">
    <div class="mb-4 pt-4 pb-4">
      <!-- 批量操作栏 -->
      <v-expand-transition>
        <div v-if="batchSelectionMode" class="batch-action-bar mb-3">
          <div class="d-flex align-center flex-wrap" style="gap: 8px">
            <v-btn
              icon
              variant="text"
              size="small"
              @click="exitBatchSelectionMode"
            >
              <v-icon>mdi-close</v-icon>
            </v-btn>
            <span class="text-subtitle-1 font-weight-medium">
              {{ tm("batch.selectedCount", { count: selectedPluginNames.size }) }}
            </span>
            <v-spacer></v-spacer>
            <v-btn
              variant="text"
              size="small"
              @click="selectAllPlugins"
            >
              {{ tm("batch.selectAll") }}
            </v-btn>
            <v-btn
              variant="text"
              size="small"
              @click="deselectAllPlugins"
            >
              {{ tm("batch.deselectAll") }}
            </v-btn>
            <v-btn
              variant="text"
              size="small"
              @click="invertSelection"
            >
              {{ tm("batch.invertSelection") }}
            </v-btn>
            <v-divider vertical class="mx-1"></v-divider>
            <v-btn
              color="success"
              variant="tonal"
              size="small"
              prepend-icon="mdi-check-circle"
              :disabled="selectedPluginNames.size === 0 || batchOperationInProgress"
              @click="showBatchConfirm('enable', batchEnablePlugins)"
            >
              {{ tm("batch.enable") }}
            </v-btn>
            <v-btn
              color="warning"
              variant="tonal"
              size="small"
              prepend-icon="mdi-close-circle"
              :disabled="selectedPluginNames.size === 0 || batchOperationInProgress"
              @click="showBatchConfirm('disable', batchDisablePlugins)"
            >
              {{ tm("batch.disable") }}
            </v-btn>
            <v-btn
              color="error"
              variant="tonal"
              size="small"
              prepend-icon="mdi-delete"
              :disabled="selectedPluginNames.size === 0 || batchOperationInProgress"
              @click="showBatchConfirm('uninstall', batchUninstallPlugins)"
            >
              {{ tm("batch.uninstall") }}
            </v-btn>
          </div>
        </div>
      </v-expand-transition>

      <!-- 正常工具栏 -->
      <div v-if="!batchSelectionMode" class="d-flex align-center flex-wrap" style="gap: 12px">
        <h2 class="text-h2 mb-0">{{ tm("titles.installedAstrBotPlugins") }}</h2>

        <div class="d-flex align-center flex-wrap ml-auto" style="gap: 8px">
          <PluginSortControl
            v-model="installedSortBy"
            :items="installedSortItems"
            :label="tm('sort.by')"
            :order="installedSortOrder"
            :ascending-label="tm('sort.ascending')"
            :descending-label="tm('sort.descending')"
            :show-order="installedSortBy !== 'default'"
            @update:order="installedSortOrder = $event"
          />
          <v-text-field
            :model-value="pluginSearch"
            @update:model-value="pluginSearch = normalizeTextInput($event)"
            density="compact"
            :label="tm('search.placeholder')"
            prepend-inner-icon="mdi-magnify"
            clearable
            variant="solo-filled"
            flat
            hide-details
            single-line
            style="min-width: 220px; max-width: 340px"
          >
          </v-text-field>
          <v-tooltip :text="tm('batch.select')" location="top">
            <template v-slot:activator="{ props: batchProps }">
              <v-btn
                v-bind="batchProps"
                icon
                variant="text"
                size="small"
                @click="toggleBatchSelectionMode"
              >
                <v-icon>mdi-checkbox-multiple-marked-outline</v-icon>
              </v-btn>
            </template>
          </v-tooltip>
        </div>
      </div>
    </div>

    <v-card
      v-if="failedPluginItems.length > 0"
      class="mb-4 rounded-lg"
      variant="tonal"
      color="warning"
    >
      <v-card-title class="d-flex align-center">
        <v-icon color="warning" class="mr-2">mdi-alert-circle</v-icon>
        {{ tm("failedPlugins.title", { count: failedPluginItems.length }) }}
      </v-card-title>
      <v-card-text class="pt-0">
        <div class="text-body-2 mb-3">
          {{ tm("failedPlugins.hint") }}
        </div>
        <v-table density="compact">
          <thead>
            <tr>
              <th>{{ tm("failedPlugins.columns.plugin") }}</th>
              <th>{{ tm("failedPlugins.columns.error") }}</th>
              <th class="text-right">{{ tm("buttons.actions") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="plugin in failedPluginItems" :key="plugin.dir_name">
              <td>
                <div class="font-weight-medium">
                  {{ plugin.display_name }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{ plugin.dir_name }}
                </div>
              </td>
              <td style="max-width: 520px">
                <div
                  class="text-caption text-medium-emphasis"
                  style="
                    display: -webkit-box;
                    -webkit-line-clamp: 2;
                    line-clamp: 2;
                    -webkit-box-orient: vertical;
                    overflow: hidden;
                  "
                >
                  {{ plugin.error || tm("status.unknown") }}
                </div>
              </td>
              <td class="text-right">
                <v-btn
                  size="small"
                  variant="tonal"
                  color="primary"
                  class="mr-2"
                  prepend-icon="mdi-refresh"
                  @click="reloadFailedPlugin(plugin.dir_name)"
                >
                  {{ tm("buttons.reload") }}
                </v-btn>
                <v-btn
                  size="small"
                  variant="tonal"
                  color="error"
                  prepend-icon="mdi-delete"
                  :disabled="plugin.reserved"
                  @click="requestUninstallFailedPlugin(plugin.dir_name)"
                >
                  {{ tm("buttons.uninstall") }}
                </v-btn>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
    </v-card>

    <v-fade-transition hide-on-leave>
      <div>
        <v-row v-if="sortedInstalledPlugins.length === 0" class="text-center">
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
            v-for="extension in sortedInstalledPlugins"
            :key="extension.name"
            class="pb-2"
          >
            <ExtensionCard
              :extension="extension"
              :is-pinned="isPinnedExtension(extension)"
              :selectable="batchSelectionMode"
              :selected="isPluginSelected(extension.name)"
              class="rounded-lg"
              style="background-color: rgb(var(--v-theme-mcpCardBg))"
              @click="handleCardClick(extension)"
              @select="handleCheckboxClick(extension)"
              @toggle-pin="togglePinnedExtension(extension)"
              @configure="openExtensionConfig(extension.name)"
              @uninstall="
                (ext, options) => uninstallExtension(ext.name, options)
              "
              @update="updateExtension(extension.name)"
              @reload="reloadPlugin(extension.name)"
              @toggle-activation="
                extension.activated ? pluginOff(extension) : pluginOn(extension)
              "
              @view-handlers="showPluginInfo(extension)"
              @view-readme="viewReadme(extension)"
              @view-changelog="viewChangelog(extension)"
              @open-webui="openPluginWebui(extension)"
            >
            </ExtensionCard>
          </v-col>
        </v-row>
      </div>
    </v-fade-transition>

    <v-tooltip v-if="!batchSelectionMode" :text="tm('market.installPlugin')" location="left">
      <template v-slot:activator="{ props }">
        <button
          v-bind="props"
          type="button"
          class="v-btn v-btn--elevated v-btn--icon v-theme--PurpleThemeDark bg-darkprimary v-btn--density-default v-btn--size-x-large v-btn--variant-elevated fab-button"
          style="
            position: fixed;
            right: 52px;
            bottom: 52px;
            z-index: 10000;
            border-radius: 16px;
          "
          @click="openInstallDialog"
        >
          <span class="v-btn__overlay"></span>
          <span class="v-btn__underlay"></span>
          <span class="v-btn__content" data-no-activator="">
            <i
              class="mdi-plus mdi v-icon notranslate v-theme--PurpleThemeDark v-icon--size-default"
              aria-hidden="true"
              style="font-size: 32px"
            ></i>
          </span>
        </button>
      </template>
    </v-tooltip>

    <v-tooltip v-if="!batchSelectionMode" :text="tm('buttons.updateAll')" location="left">
      <template v-slot:activator="{ props }">
        <v-btn
          v-bind="props"
          color="darkprimary"
          icon="mdi-update"
          size="x-large"
          variant="elevated"
          class="update-all-fab"
          :loading="updatingAll"
          @click="showUpdateAllConfirm"
        />
      </template>
    </v-tooltip>

    <!-- 批量操作确认对话框 -->
    <v-dialog v-model="batchConfirmDialog.show" max-width="480">
      <v-card class="rounded-lg">
        <v-card-title class="d-flex align-center pa-4">
          <v-icon :color="batchConfirmColor" class="mr-2">{{ batchConfirmIcon }}</v-icon>
          {{ batchConfirmTitle }}
        </v-card-title>
        <v-card-text>
          <p>{{ batchConfirmMessage }}</p>
          <v-alert
            v-if="batchConfirmDialog.reservedCount > 0"
            type="info"
            variant="tonal"
            density="compact"
            class="mt-3"
          >
            {{ tm("batch.reservedSkipped", { count: batchConfirmDialog.reservedCount }) }}
          </v-alert>
          <template v-if="batchConfirmDialog.operation === 'uninstall'">
            <v-divider class="my-4" />
            <v-checkbox
              v-model="batchDeleteConfig"
              :label="tm('dialogs.uninstall.deleteConfig')"
              color="warning"
              hide-details
            />
            <v-checkbox
              v-model="batchDeleteData"
              :label="tm('dialogs.uninstall.deleteData')"
              color="error"
              hide-details
            />
          </template>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="cancelBatchConfirm">{{ tm("buttons.cancel") }}</v-btn>
          <v-btn :color="batchConfirmColor" variant="flat" :loading="batchOperationInProgress" @click="confirmBatchOperation">{{ tm("batch.confirmAction") }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-tab-item>
</template>

<style scoped>
.fab-button {
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.fab-button:hover {
  transform: translateY(-4px) scale(1.05);
  box-shadow: 0 12px 20px rgba(var(--v-theme-primary), 0.4);
}

.update-all-fab {
  position: fixed;
  right: 52px;
  bottom: 124px;
  z-index: 10000;
  border-radius: 16px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.update-all-fab:hover {
  transform: translateY(-4px) scale(1.05);
  box-shadow: 0 12px 20px rgba(var(--v-theme-primary), 0.4);
}

.batch-action-bar {
  background-color: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-on-surface), 0.12);
  border-radius: 12px;
  padding: 12px 16px;
}
</style>