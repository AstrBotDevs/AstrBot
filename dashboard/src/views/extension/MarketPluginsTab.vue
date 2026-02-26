<script setup>
import MarketPluginCard from "@/components/extension/MarketPluginCard.vue";
import defaultPluginIcon from "@/assets/images/plugin_icon.png";
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
} = props.state;

const currentSourceName = computed(() => {
  if (!selectedSource.value) {
    return tm("market.defaultSource");
  }
  const matched = customSources.value.find((s) => s.url === selectedSource.value);
  return matched?.name || tm("market.defaultSource");
});
</script>

<template>
          <v-tab-item v-show="activeTab === 'market'">
            <div class="mb-6 pt-4 pb-4">
              <div class="d-flex align-center flex-wrap" style="gap: 12px">
                <h2 class="text-h2 mb-0">{{ tm("tabs.market") }}</h2>

                <v-tooltip location="top" :text="tm('market.sourceManagement')">
                  <template v-slot:activator="{ props }">
                    <v-btn
                      v-bind="props"
                      variant="tonal"
                      rounded="md"
                      color="primary"
                      class="text-none px-2"
                      @click="openSourceManagerDialog"
                    >
                      <v-icon size="18" class="mr-1">mdi-source-branch</v-icon>
                      <span class="text-truncate" style="max-width: 180px">
                        {{ currentSourceName }}
                      </span>
                    </v-btn>
                  </template>
                </v-tooltip>

                <v-text-field
                  v-model="marketSearch"
                  density="compact"
                  :label="tm('search.marketPlaceholder')"
                  prepend-inner-icon="mdi-magnify"
                  variant="solo-filled"
                  flat
                  hide-details
                  single-line
                  style="min-width: 220px; max-width: 340px"
                >
                </v-text-field>
              </div>

              <div
                class="d-flex align-center text-caption text-medium-emphasis mt-2"
                style="color: grey; line-height: 1.4"
              >
                <v-icon size="16" class="mr-1">mdi-alert-outline</v-icon>
                <span>{{ tm("market.sourceSafetyWarning") }}</span>
              </div>
            </div>

            <!-- <small style="color: var(--v-theme-secondaryText);">每个插件都是作者无偿提供的的劳动成果。如果您喜欢某个插件，请 Star！</small> -->

            <!-- FAB Button -->
            <v-tooltip :text="tm('market.installPlugin')" location="left">
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
                  @click="dialog = true"
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

            <div class="mt-4">
              <div
                class="d-flex align-center mb-2"
                style="justify-content: space-between; flex-wrap: wrap; gap: 8px"
              >
                <h2>
                  {{ tm("market.randomPlugins") }}
                </h2>
                <v-btn
                  color="primary"
                  variant="tonal"
                  prepend-icon="mdi-shuffle-variant"
                  :disabled="pluginMarketData.length === 0"
                  @click="refreshRandomPlugins"
                >
                  {{ tm("buttons.reshuffle") }}
                </v-btn>
              </div>

              <v-row class="mb-6" dense>
                <v-col
                  v-for="plugin in randomPlugins"
                  :key="`random-${plugin.name}`"
                  cols="12"
                  md="6"
                  lg="4"
                  class="pb-2"
                >
                  <MarketPluginCard
                    :plugin="plugin"
                    :default-plugin-icon="defaultPluginIcon"
                    :show-plugin-full-name="showPluginFullName"
                    @install="handleInstallPlugin"
                  />
                </v-col>
              </v-row>

              <div
                class="d-flex align-center mb-2"
                style="
                  justify-content: space-between;
                  flex-wrap: wrap;
                  gap: 8px;
                "
              >
                <div class="d-flex align-center" style="gap: 6px">
                  <h2>
                    {{ tm("market.allPlugins") }}({{
                      filteredMarketPlugins.length
                    }})
                  </h2>
                  <v-btn
                    icon
                    variant="text"
                    @click="refreshPluginMarket"
                    :loading="refreshingMarket"
                  >
                    <v-icon>mdi-refresh</v-icon>
                  </v-btn>
                </div>

                <div
                  class="d-flex align-center"
                  style="gap: 8px; flex-wrap: wrap"
                >
                  <v-select
                    v-model="sortBy"
                    :items="[
                      { title: tm('sort.default'), value: 'default' },
                      { title: tm('sort.stars'), value: 'stars' },
                      { title: tm('sort.author'), value: 'author' },
                      { title: tm('sort.updated'), value: 'updated' },
                    ]"
                    density="compact"
                    variant="outlined"
                    hide-details
                    style="max-width: 150px"
                  >
                    <template v-slot:prepend-inner>
                      <v-icon size="small">mdi-sort</v-icon>
                    </template>
                  </v-select>

                  <v-btn
                    icon
                    v-if="sortBy !== 'default'"
                    @click="sortOrder = sortOrder === 'desc' ? 'asc' : 'desc'"
                    variant="text"
                    density="compact"
                  >
                    <v-icon>{{
                      sortOrder === "desc"
                        ? "mdi-sort-descending"
                        : "mdi-sort-ascending"
                    }}</v-icon>
                    <v-tooltip activator="parent" location="top">
                      {{
                        sortOrder === "desc"
                          ? tm("sort.descending")
                          : tm("sort.ascending")
                      }}
                    </v-tooltip>
                  </v-btn>
                </div>
              </div>

              <v-row style="min-height: 26rem" dense>
                <v-col
                  v-for="plugin in paginatedPlugins"
                  :key="plugin.name"
                  cols="12"
                  md="6"
                  lg="4"
                  class="pb-2"
                >
                  <MarketPluginCard
                    :plugin="plugin"
                    :default-plugin-icon="defaultPluginIcon"
                    :show-plugin-full-name="showPluginFullName"
                    @install="handleInstallPlugin"
                  />
                </v-col>
              </v-row>

              <div class="d-flex justify-center mt-4" v-if="totalPages > 1">
                <v-pagination
                  v-model="currentPage"
                  :length="totalPages"
                  :total-visible="7"
                  size="small"
                ></v-pagination>
              </div>
            </div>
          </v-tab-item>
</template>
