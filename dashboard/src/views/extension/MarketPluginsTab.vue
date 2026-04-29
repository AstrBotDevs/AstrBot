<script setup lang="ts">
import MarketPluginCard from "@/components/extension/MarketPluginCard.vue";
import PluginSortControl from "@/components/extension/PluginSortControl.vue";
import defaultPluginIcon from "@/assets/images/plugin_icon.png";
import { computed } from "vue";
import { normalizeTextInput } from "@/utils/inputValue";

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
  showRandomPlugins,
  marketCategoryFilter,
  marketCategoryItems,
  normalizeStr,
  toPinyinText,
  toInitials,
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
  toggleRandomPluginsVisibility,
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
  const matched = customSources.value.find(
    (s) => s.url === selectedSource.value,
  );
  return matched?.name || tm("market.defaultSource");
});

const marketSortItems = computed(() => [
  { title: tm("sort.default"), value: "default" },
  { title: tm("sort.stars"), value: "stars" },
  { title: tm("sort.author"), value: "author" },
  { title: tm("sort.updated"), value: "updated" },
]);

const marketCategorySelectItems = computed(() =>
  marketCategoryItems.value.map((item) => ({
    title: `${item.label || ""} (${item.count || 0})`,
    value: item.value,
  })),
);
</script>

<template>
  <div v-show="activeTab === 'market'">
    <div class="mb-6 pt-4 pb-4">
      <div class="d-flex align-center" style="gap: 12px">
        <div class="d-flex align-center" style="gap: 12px; min-width: 0">
          <h2 class="text-h2 mb-0">
            {{ tm("tabs.market") }}
          </h2>

          <v-tooltip location="top" :text="tm('market.sourceManagement')">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                variant="tonal"
                rounded="md"
                color="primary"
                class="text-none px-2"
                @click="openSourceManagerDialog"
              >
                <v-icon size="18" class="mr-1"> mdi-source-branch </v-icon>
                <span class="text-truncate" style="max-width: 180px">
                  {{ currentSourceName }}
                </span>
              </v-btn>
            </template>
          </v-tooltip>

          <v-btn
            color="primary"
            variant="tonal"
            rounded="md"
            class="text-none px-2"
            :prepend-icon="showRandomPlugins ? 'mdi-eye-off' : 'mdi-eye'"
            @click="toggleRandomPluginsVisibility"
          >
            {{
              showRandomPlugins
                ? tm("market.hideRandomPlugins")
                : tm("market.showRandomPlugins")
            }}
          </v-btn>
        </div>

        <v-text-field
          :model-value="marketSearch"
          class="ml-auto"
          density="compact"
          :label="tm('search.marketPlaceholder')"
          prepend-inner-icon="mdi-magnify"
          clearable
          variant="solo-filled"
          flat
          hide-details
          single-line
          style="width: 340px; min-width: 220px; max-width: 340px"
          @update:model-value="marketSearch = normalizeTextInput($event)"
        />
      </div>

      <div
        class="d-flex align-center text-caption text-medium-emphasis mt-2"
        style="color: grey; line-height: 1.4"
      >
        <v-icon size="16" class="mr-1"> mdi-alert-outline </v-icon>
        <span>{{ tm("market.sourceSafetyWarning") }}</span>
      </div>
    </div>

    <!-- <small style="color: var(--v-theme-secondaryText);">每个插件都是作者无偿提供的的劳动成果。如果您喜欢某个插件，请 Star！</small> -->

    <!-- FAB Button -->
    <v-tooltip :text="tm('market.installPlugin')" location="left">
      <template #activator="{ props }">
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
          <span class="v-btn__overlay" />
          <span class="v-btn__underlay" />
          <span class="v-btn__content" data-no-activator="">
            <i
              class="mdi-plus mdi v-icon notranslate v-theme--PurpleThemeDark v-icon--size-default"
              aria-hidden="true"
              style="font-size: 32px"
            />
          </span>
        </button>
      </template>
    </v-tooltip>

    <div class="mt-4">
      <div
        class="d-flex align-center mb-2"
        style="justify-content: space-between; flex-wrap: wrap; gap: 8px"
      >
        <div class="d-flex align-center" style="gap: 6px">
          <h2>
            {{ tm("market.allPlugins") }}
          </h2>
          <v-btn
            icon
            variant="text"
            :loading="loading_ || refreshingMarket"
            :disabled="loading_ || refreshingMarket"
            @click="refreshPluginMarket"
          >
            <v-icon>mdi-refresh</v-icon>
          </v-btn>
        </div>

        <div class="d-flex align-center" style="gap: 8px; flex-wrap: wrap">
          <v-select
            v-if="marketCategoryItems.length > 0"
            v-model="marketCategoryFilter"
            :items="marketCategorySelectItems"
            item-title="title"
            item-value="value"
            :label="tm('market.category')"
            density="compact"
            variant="outlined"
            hide-details
            class="market-filter-control"
            :menu-props="{ openOnHover: true, closeOnContentClick: false }"
          />

          <PluginSortControl
            v-model="sortBy"
            :items="marketSortItems"
            :label="tm('sort.by')"
            :order="sortOrder"
            :ascending-label="tm('sort.ascending')"
            :descending-label="tm('sort.descending')"
            :show-order="sortBy !== 'default'"
            @update:order="sortOrder = $event"
          />
        </div>
      </div>

      <v-row style="min-height: 26rem" density="compact">
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

      <div v-if="totalPages > 1" class="d-flex justify-center mt-4">
        <v-pagination
          v-model="currentPage"
          :length="totalPages"
          :total-visible="7"
          size="small"
        />
      </div>

      <v-expand-transition>
        <div v-if="showRandomPlugins">
          <div
            class="d-flex align-center mb-2 mt-4"
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

          <v-row class="mb-6" density="compact">
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
        </div>
      </v-expand-transition>
    </div>
  </div>
</template>

<style scoped>
.market-filter-control {
  min-width: 190px;
  max-width: 220px;
}

.market-filter-control ::v-deep(.v-field__input),
.market-filter-control ::v-deep(.v-field-label),
.market-filter-control ::v-deep(.v-select__selection-text),
.market-filter-control ::v-deep(.v-field__prepend-inner) {
  font-size: 0.875rem;
}
</style>
