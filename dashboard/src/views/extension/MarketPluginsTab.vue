<script setup>
import MarketPluginCard from "@/components/extension/MarketPluginCard.vue";
import PluginSortControl from "@/components/extension/PluginSortControl.vue";
import defaultPluginIcon from "/favicon.svg";
import { computed, ref, watch } from "vue";
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
  marketCategoryFilter,
  marketCategoryItems,
  marketPlatformFilter,
  marketPlatformItems,
  getMarketPluginKey,
  normalizeStr,
  toPinyinText,
  toInitials,
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
  openInstallDialog,
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
  checkInstallVersionSupport,
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
  { title: tm("sort.downloads"), value: "downloads" },
  { title: tm("sort.author"), value: "author" },
  { title: tm("sort.updated"), value: "updated" },
]);

// One scrollable chip row at every width; a toggle expands it into wrapped rows
// when the categories do not fit on a single line.
const categoryChipsExpanded = ref(false);
const categoryChipsOverflow = ref(false);
const chipsRowEl = ref(null);

const measureCategoryChips = () => {
  const el = chipsRowEl.value;
  if (!el || marketCategoryItems.value.length === 1) {
    categoryChipsExpanded.value = false;
    categoryChipsOverflow.value = false;
    return;
  }
  // Only the collapsed row can overflow; keep the toggle visible while expanded.
  if (categoryChipsExpanded.value) return;
  // Use the full row width so the toggle's own width cannot keep it visible.
  categoryChipsOverflow.value = el.scrollWidth > el.parentElement.clientWidth;
};

const chipsToggleVisible = computed(
  () => categoryChipsOverflow.value || categoryChipsExpanded.value,
);

// The chip row hides its scrollbar, so a vertical wheel over it scrolls the row
// horizontally. While the row can scroll it also swallows the wheel, so reaching
// the end does not suddenly scroll the whole page; moving the pointer away gives
// the wheel back to the page.
const onCategoryChipsWheel = (event) => {
  const el = chipsRowEl.value;
  if (!el || categoryChipsExpanded.value) return;
  const maxScroll = el.scrollWidth - el.clientWidth;
  if (maxScroll <= 0) return;
  if (Math.abs(event.deltaX) >= Math.abs(event.deltaY)) return;

  const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
  el.scrollLeft = Math.max(0, Math.min(maxScroll, el.scrollLeft + delta));
  event.preventDefault();
};

watch(selectedSource, () => {
  categoryChipsExpanded.value = false;
});

watch(
  [marketCategoryItems, activeTab, categoryChipsExpanded],
  measureCategoryChips,
  { flush: "post" },
);

watch(chipsRowEl, (el, _, onCleanup) => {
  if (!el) return;
  const observer = new ResizeObserver(measureCategoryChips);
  observer.observe(el);
  onCleanup(() => observer.disconnect());
});

// Navigate with the unique market plugin key instead of the metadata name —
// two market entries can share the same `name`.
const openMarketPluginDetail = (plugin) => {
  const pluginKey = getMarketPluginKey(plugin);
  if (!pluginKey) return;
  router.push({
    name: "ExtensionMarketDetails",
    params: { pluginId: pluginKey },
  });
};
</script>

<template>
  <v-tab-item v-show="activeTab === 'market'">
    <div class="mb-6 pt-4 pb-4">
      <div class="market-header-row d-flex align-center">
        <div class="market-header-primary d-flex align-center">
          <v-tabs
            model-value="market"
            bg-color="transparent"
            class="plugin-view-tabs"
            height="42"
          >
            <v-tab
              value="installed"
              :to="{ name: 'Extensions' }"
              class="plugin-view-tab text-none"
              :ripple="false"
            >
              {{ tm("titles.installedAstrBotPlugins") }}
            </v-tab>
            <v-tab
              value="market"
              :to="{ name: 'ExtensionMarketplace' }"
              class="plugin-view-tab text-none"
              :ripple="false"
            >
              {{ tm("tabs.market") }}
            </v-tab>
          </v-tabs>

          <v-tooltip location="top" :text="tm('market.sourceManagement')">
            <template v-slot:activator="{ props }">
              <v-btn
                v-bind="props"
                variant="tonal"
                rounded="md"
                color="primary"
                class="market-source-button text-none px-2"
                @click="openSourceManagerDialog"
              >
                <v-icon size="18" class="mr-1">mdi-source-branch</v-icon>
                <span class="text-truncate" style="max-width: 180px">
                  {{ currentSourceName }}
                </span>
              </v-btn>
            </template>
          </v-tooltip>

          <v-tooltip location="top" :text="tm('market.refresh')">
            <template v-slot:activator="{ props }">
              <v-btn
                v-bind="props"
                icon
                variant="text"
                size="small"
                :loading="loading_ || refreshingMarket"
                :disabled="loading_ || refreshingMarket"
                :aria-label="tm('market.refresh')"
                @click="refreshPluginMarket"
              >
                <v-icon>mdi-refresh</v-icon>
              </v-btn>
            </template>
          </v-tooltip>
        </div>

        <v-text-field
          :model-value="marketSearch"
          @update:model-value="marketSearch = normalizeTextInput($event)"
          class="market-search-field ml-auto"
          density="compact"
          :label="tm('search.marketPlaceholder')"
          prepend-inner-icon="mdi-magnify"
          clearable
          variant="solo-filled"
          flat
          hide-details
          single-line
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

    <div class="mt-4">
      <div class="market-category-row">
        <div
          class="market-category-chips"
          :class="{ 'is-expanded': categoryChipsExpanded }"
        >
          <div
            id="market-category-filters"
            ref="chipsRowEl"
            class="market-category-chips-scroll"
            role="group"
            :aria-label="tm('market.category')"
            @wheel="onCategoryChipsWheel"
          >
            <button
              v-for="item in marketCategoryItems"
              :key="item.value"
              type="button"
              class="market-category-chip"
              :class="{ 'is-active': marketCategoryFilter === item.value }"
              :aria-pressed="marketCategoryFilter === item.value"
              @click="marketCategoryFilter = item.value"
            >
              {{ item.label }}
              <span class="market-category-chip-count">{{ item.count }}</span>
            </button>
          </div>
          <v-btn
            v-if="chipsToggleVisible"
            icon
            size="x-small"
            variant="text"
            class="market-category-chips-toggle"
            aria-controls="market-category-filters"
            :aria-expanded="categoryChipsExpanded"
            :aria-label="
              categoryChipsExpanded
                ? tm('market.collapseCategories')
                : tm('market.expandCategories')
            "
            @click="categoryChipsExpanded = !categoryChipsExpanded"
          >
            <v-icon size="18">
              {{
                categoryChipsExpanded ? "mdi-chevron-up" : "mdi-chevron-down"
              }}
            </v-icon>
          </v-btn>
        </div>

        <div class="market-category-row-controls">
          <v-select
            v-model="marketPlatformFilter"
            :items="marketPlatformItems"
            :label="tm('market.platform')"
            :aria-label="tm('market.platform')"
            :placeholder="tm('market.allPlatforms')"
            persistent-placeholder
            multiple
            clearable
            density="compact"
            variant="outlined"
            hide-details
            class="market-filter-control"
          >
            <template #selection="{ item, index }">
              <span v-if="index === 0" class="text-truncate">
                {{ item.value === "__undeclared__" ? item.title : item.value }}
                <span v-if="marketPlatformFilter.length > 1">
                  (+{{ marketPlatformFilter.length - 1 }})
                </span>
              </span>
            </template>
          </v-select>

          <PluginSortControl
            class="market-sort-control"
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

      <v-row style="min-height: 26rem" dense>
        <v-col v-if="!loading_ && sortedPlugins.length === 0" cols="12">
          <div class="text-center text-medium-emphasis py-8" role="status">
            {{ tm("market.noMatchingPlugins") }}
          </div>
        </v-col>
        <v-col
          v-for="plugin in paginatedPlugins"
          :key="getMarketPluginKey(plugin)"
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
            @open="openMarketPluginDetail"
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

      <v-expand-transition>
        <div v-if="randomPlugins.length > 0">
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

          <v-row class="mb-6" dense>
            <v-col
              v-for="plugin in randomPlugins"
              :key="getMarketPluginKey(plugin)"
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
                @open="openMarketPluginDetail"
              />
            </v-col>
          </v-row>
        </div>
      </v-expand-transition>
    </div>
  </v-tab-item>
</template>

<style scoped>
.plugin-view-tabs {
  background: transparent;
  flex: 0 0 auto;
}

.plugin-view-tab {
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 1.25rem;
  font-weight: 650;
  min-width: 0;
  padding: 0 10px;
}

.plugin-view-tab:first-child {
  padding-left: 0;
}

.plugin-view-tab.v-tab--selected {
  color: rgba(var(--v-theme-on-surface), 0.92);
}

.plugin-view-tabs :deep(.v-tabs-slider) {
  background: rgba(var(--v-theme-on-surface), 0.5);
  height: 2px;
}

.market-header-row,
.market-header-primary {
  gap: 12px;
}

.market-header-primary {
  min-width: 0;
}

.market-source-button {
  max-width: 220px;
}

.market-search-field {
  flex: 0 1 340px;
  max-width: 340px;
  min-width: 220px;
}

.market-category-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.market-category-row-controls {
  flex: 0 0 auto;
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.market-filter-control {
  min-width: 180px;
  width: 190px;
  max-width: 220px;
}

.market-filter-control :deep(.v-field__input),
.market-filter-control :deep(.v-field-label),
.market-filter-control :deep(.v-select__selection-text),
.market-filter-control :deep(.v-field__prepend-inner) {
  font-size: 0.875rem;
}

.market-category-chips {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.market-category-chips-scroll {
  flex: 1 1 auto;
  display: flex;
  gap: 6px;
  min-width: 0;
  overflow-x: auto;
  /* Pointer scrolling works through the wheel handler, so no scrollbar. */
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.market-category-chips-scroll::-webkit-scrollbar {
  display: none;
}

.market-category-chips.is-expanded .market-category-chips-scroll {
  flex-wrap: wrap;
  overflow: visible;
}

.market-category-chips.is-expanded .market-category-chip {
  max-width: 100%;
  white-space: normal;
  overflow-wrap: anywhere;
}

.market-category-chip {
  flex: 0 0 auto;
  padding: 4px 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.16);
  border-radius: 999px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.75);
  font-size: 0.8125rem;
  white-space: nowrap;
  cursor: pointer;
}

.market-category-chip:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}

.market-category-chip:focus-visible {
  outline: 2px solid rgb(var(--v-theme-on-surface));
  outline-offset: -2px;
}

.market-category-chip.is-active {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
  font-weight: 600;
}

.market-category-chip-count {
  margin-left: 2px;
  opacity: 0.7;
}

.market-category-chips-toggle {
  flex: 0 0 auto;
}

@media (max-width: 700px) {
  .market-header-row {
    align-items: stretch !important;
    flex-direction: column;
  }

  .market-header-primary {
    flex-wrap: wrap;
    gap: 8px;
  }

  .market-search-field {
    flex: none;
    margin-left: 0 !important;
    max-width: none;
    min-width: 0;
    width: 100%;
  }

  /* Small screens: categories keep the first line to themselves and the
     platform and sort controls wrap cleanly below. */
  .market-category-row {
    align-items: center;
    flex-wrap: wrap;
    column-gap: 6px;
    row-gap: 12px;
  }

  .market-category-chips {
    flex: 1 1 100%;
  }

  .market-category-row-controls {
    flex: 1 1 100%;
    flex-wrap: wrap;
    margin-left: 0;
    width: 100%;
  }

  .market-filter-control {
    flex: 1 1 180px;
    max-width: none;
    min-width: 0;
    width: auto;
  }

  .market-category-row-controls :deep(.plugin-sort-control) {
    flex: 1 1 180px;
    flex-wrap: nowrap;
    min-width: 0;
  }

  .market-category-row-controls :deep(.plugin-sort-control__select) {
    flex: 1;
    max-width: none;
    min-width: 0;
    width: auto;
  }

  .plugin-view-tab {
    font-size: 1.125rem;
    padding-inline: 8px;
  }
}
</style>
