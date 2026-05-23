<script setup>
import ModManagerLayout from "@/components/extension/mod-manager/ModManagerLayout.vue";
import ExtensionCard from "@/components/shared/ExtensionCard.vue";
import { normalizeTextInput } from "@/utils/inputValue";
import {
  readPinnedExtensions,
  writePinnedExtensions,
} from "./extensionPreferenceStorage.mjs";
import { computed, ref, watch } from "vue";

const handlePluginLogoError = (event) => {
  const target = event?.target;
  if (!target || target.dataset.fallbackApplied === "1") return;
  target.dataset.fallbackApplied = "1";
  target.src = defaultPluginIcon;
};

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
  snack_message,
  snack_show,
  snack_success,
  configDialog,
  extension_config,
  pluginMarketData,
  loadingDialog,
  curr_namespace,
  updatingAll,
  reinstallingFailedPluginDirName,
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
  loading_,
  toast,
  resetLoadingDialog,
  onLoadingDialogResult,
  failedPluginItems,
  getExtensions,
  reloadFailedPlugin,
  reinstallFailedPlugin,
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
  isCheckingUpdates,
  checkPluginUpdates,
  handleLocaleChange,
  searchDebounceTimer,
} = props.state;

const VIEW_MODE_KEY = "pluginManager.installedViewMode";
const SHOW_RESERVED_KEY = "showReservedPlugins";

const readInstalledViewMode = () => {
  try {
    return localStorage.getItem(VIEW_MODE_KEY) === "mod" ? "mod" : "legacy";
  } catch {
    return "legacy";
  }
};

const readShowReserved = () => {
  try {
    return localStorage.getItem(SHOW_RESERVED_KEY) === "true";
  } catch {
    return false;
  }
};

const installedViewMode = ref(readInstalledViewMode());
const showReserved = ref(readShowReserved());

watch(installedViewMode, (mode) => {
  try {
    localStorage.setItem(VIEW_MODE_KEY, mode === "mod" ? "mod" : "legacy");
  } catch {
    // Ignore restricted storage environments.
  }
});

watch(showReserved, (value) => {
  try {
    localStorage.setItem(SHOW_RESERVED_KEY, String(Boolean(value)));
  } catch {
    // Ignore restricted storage environments.
  }
});

const setInstalledViewMode = (mode) => {
  installedViewMode.value = mode === "mod" ? "mod" : "legacy";
};

const setShowReserved = (value) => {
  showReserved.value = Boolean(value);
};

const openPluginDetail = (extension) => {
  if (!extension?.name) return;
  router.push({
    name: "ExtensionDetails",
    params: { pluginId: extension.name },
    hash: "#installed",
  });
};

const pinnedExtensionNames = ref(readPinnedExtensions());

const pinnedExtensionOrder = computed(() => {
  const order = new Map();
  pinnedExtensionNames.value.forEach((name, index) => {
    order.set(name, index);
  });
  return order;
});

const sortedInstalledPlugins = computed(() => {
  const order = pinnedExtensionOrder.value;
  return [...filteredPlugins.value].sort((a, b) => {
    const aIndex = order.has(a?.name)
      ? order.get(a.name)
      : Number.POSITIVE_INFINITY;
    const bIndex = order.has(b?.name)
      ? order.get(b.name)
      : Number.POSITIVE_INFINITY;

    if (aIndex !== bIndex) {
      return aIndex - bIndex;
    }
    return 0;
  });
});

const modManagerPlugins = computed(() => {
  if (showReserved.value) {
    return filteredPlugins.value;
  }
  return filteredPlugins.value.filter((plugin) => !plugin?.reserved);
});

watch(
  pinnedExtensionNames,
  (names) => {
    writePinnedExtensions(names);
  },
  { deep: true },
);

const isPinnedExtension = (extension) => {
  const name = extension?.name;
  return !!name && pinnedExtensionOrder.value.has(name);
};

const togglePinnedExtension = (extension) => {
  const name = extension?.name;
  if (!name) return;

  const next = pinnedExtensionNames.value.filter((item) => item !== name);
  if (next.length === pinnedExtensionNames.value.length) {
    next.unshift(name);
  }
  pinnedExtensionNames.value = next;
};

const pinnedNames = pinnedExtensionNames;
const togglePin = togglePinnedExtension;
</script>

<template>
  <v-tab-item v-show="activeTab === 'installed'">
    <div class="mb-4 pt-4 pb-4">
      <div class="d-flex align-center flex-wrap" style="gap: 12px">
        <h2 class="text-h2 mb-0">{{ tm("titles.installedAstrBotPlugins") }}</h2>

        <div class="d-flex align-center flex-wrap ml-auto" style="gap: 8px">
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

          <v-btn-toggle
            :model-value="installedViewMode"
            @update:model-value="setInstalledViewMode"
            mandatory
            density="compact"
            color="primary"
          >
            <v-btn value="legacy">
              <v-icon size="18">mdi-view-grid</v-icon>
              <v-tooltip activator="parent" location="bottom">{{
                tm("views.card")
              }}</v-tooltip>
            </v-btn>
            <v-btn value="mod">
              <v-icon size="18">mdi-view-dashboard-outline</v-icon>
              <v-tooltip activator="parent" location="bottom">{{
                tm("views.modManager")
              }}</v-tooltip>
            </v-btn>
          </v-btn-toggle>
        </div>
      </div>
    </div>

    <div v-if="installedViewMode === 'mod'" style="height: calc(100vh - 200px)">
      <ModManagerLayout
        :plugins="modManagerPlugins"
        :loading="loading_"
        :show-reserved="showReserved"
        :pinned-names="pinnedNames"
        installed-view-mode="mod"
        :updatable-count="updatableExtensions.length"
        :search="pluginSearch"
        :updating-all="updatingAll"
        :failed-message="extension_data.message"
        @update:search="pluginSearch = $event"
        @update:show-reserved="setShowReserved"
        @update:installed-view-mode="setInstalledViewMode"
        @install="openInstallDialog"
        @update-all="showUpdateAllConfirm"
        @action-enable="pluginOn($event)"
        @action-disable="pluginOff($event)"
        @action-reload="reloadPlugin($event)"
        @action-update="updateExtension($event)"
        @action-uninstall="uninstallExtension($event)"
        @action-configure="openExtensionConfig($event.name)"
        @action-open-readme="viewReadme($event)"
        @action-open-repo="(url) => window.open(url, '_blank')"
        @toggle-pin="togglePin"
        @config-saved="getExtensions"
      />
    </div>

    <template v-else>
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
              </div>
            </div>

            <v-row class="mb-4">
              <v-col cols="12">
                <div class="installed-toolbar">
                  <div class="installed-toolbar__actions">
                    <v-btn variant="tonal" @click="toggleShowReserved">
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
                      color="info"
                      variant="tonal"
                      :loading="isCheckingUpdates"
                      @click="checkPluginUpdates"
                    >
                      <v-icon>mdi-cloud-sync</v-icon>
                      {{ tm("buttons.checkUpdates") }}
                    </v-btn>
                  </div>

                  <div class="installed-toolbar__controls">
                    <v-btn-toggle
                      v-model="installedStatusFilter"
                      mandatory
                      divided
                      density="compact"
                      color="primary"
                      class="installed-status-toggle"
                    >
                      <v-btn value="all" prepend-icon="mdi-filter-variant">
                        {{ tm("filters.all") }}
                      </v-btn>
                      <v-btn value="enabled" prepend-icon="mdi-play-circle-outline">
                        {{ tm("status.enabled") }}
                      </v-btn>
                      <v-btn value="disabled" prepend-icon="mdi-pause-circle-outline">
                        {{ tm("status.disabled") }}
                      </v-btn>
                    </v-btn-toggle>

                    <PluginSortControl
                      v-model="installedSortBy"
                      :items="installedSortItems"
                      :label="tm('sort.by')"
                      :order="installedSortOrder"
                      :ascending-label="tm('sort.ascending')"
                      :descending-label="tm('sort.descending')"
                      :show-order="installedSortUsesOrder"
                      @update:order="installedSortOrder = $event"
                    />
                  </div>
                </div>
              </v-col>
            </v-row>

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
                          :disabled="
                            reinstallingFailedPluginDirName === plugin.dir_name
                          "
                          @click="reloadFailedPlugin(plugin.dir_name)"
                        >
                          {{ tm("buttons.reload") }}
                        </v-btn>
                        <v-btn
                          v-if="plugin.repo"
                          size="small"
                          variant="tonal"
                          color="warning"
                          class="mr-2"
                          prepend-icon="mdi-package-variant-closed-sync"
                          :loading="
                            reinstallingFailedPluginDirName === plugin.dir_name
                          "
                          :disabled="
                            reinstallingFailedPluginDirName === plugin.dir_name
                          "
                          @click="
                            reinstallFailedPlugin(
                              plugin.dir_name,
                              plugin.display_name || plugin.name || plugin.dir_name,
                            )
                          "
                        >
                          {{ tm("card.actions.reinstall") }}
                        </v-btn>
                        <v-btn
                          size="small"
                          variant="tonal"
                          color="error"
                          prepend-icon="mdi-delete"
                          :disabled="
                            plugin.reserved ||
                            reinstallingFailedPluginDirName === plugin.dir_name
                          "
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
              <!-- 表格视图 -->
              <div v-if="isListView">
                <v-card class="rounded-lg overflow-hidden elevation-0">
                  <v-data-table
                    class="plugin-list-table"
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
                            @error="handlePluginLogoError"
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
                          <div class="text-h5" style="font-family: inherit;">
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
                      <div class="py-2">
                        <div
                          class="text-body-2 text-medium-emphasis"
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
                        <div
                          v-if="item.support_platforms?.length"
                          class="d-flex align-center flex-wrap mt-2"
                        >
                          <span class="text-caption text-medium-emphasis mr-2">
                            {{ tm("card.status.supportPlatform") }}:
                          </span>
                          <v-chip
                            v-for="platformId in item.support_platforms"
                            :key="platformId"
                            size="x-small"
                            color="info"
                            variant="outlined"
                            class="mr-1 mb-1"
                          >
                            {{ platformId }}
                          </v-chip>
                        </div>
                        <div
                          v-if="item.astrbot_version"
                          class="d-flex align-center flex-wrap mt-1"
                        >
                          <span class="text-caption text-medium-emphasis mr-2">
                            {{ tm("card.status.astrbotVersion") }}:
                          </span>
                          <v-chip
                            size="x-small"
                            color="secondary"
                            variant="outlined"
                            class="mr-1 mb-1"
                          >
                            {{ item.astrbot_version }}
                          </v-chip>
                        </div>
                      </div>
                    </template>

                    <template v-slot:item.version="{ item }">
                      <div class="d-flex align-center">
                        <span class="text-body-2">{{ item.version }}</span>
                        <v-tooltip v-if="item.has_update" location="top">
                          <template v-slot:activator="{ props: tooltipProps }">
                            <v-icon
                              v-bind="tooltipProps"
                              color="warning"
                              size="small"
                              class="ml-1"
                              style="cursor: pointer"
                              @click.stop="updateExtension(item.name)"
                              >mdi-alert</v-icon
                            >
                          </template>
                          <span
                            >{{ tm("messages.hasUpdate") }}
                            {{ item.online_version }}</span
                          >
                        </v-tooltip>
                        <v-tooltip v-if="item.has_update" location="top">
                          <template v-slot:activator="{ props: tooltipProps }">
                            <span
                              v-bind="tooltipProps"
                              class="ml-1 text-caption text-warning"
                              style="cursor: pointer"
                              @click.stop="updateExtension(item.name)"
                            >
                              {{ item.online_version }}
                            </span>
                          </template>
                          <span>{{ tm("buttons.update") }}</span>
                        </v-tooltip>
                      </div>
                    </template>

                    <template v-slot:item.author="{ item }">
                      <div class="text-body-2">{{ item.author }}</div>
                    </template>

                    <template v-slot:item.actions="{ item }">
                      <div class="table-action-row d-flex align-center flex-nowrap justify-start ga-2 py-1">
                        <v-btn
                          v-if="!item.activated"
                          size="small"
                          variant="tonal"
                          color="success"
                          class="table-action-btn"
                          prepend-icon="mdi-play"
                          @click="pluginOn(item)"
                        >
                          {{ tm("buttons.enable") }}
                        </v-btn>
                        <v-btn
                          v-else
                          size="small"
                          variant="tonal"
                          color="error"
                          class="table-action-btn"
                          prepend-icon="mdi-pause"
                          @click="pluginOff(item)"
                        >
                          {{ tm("buttons.disable") }}
                        </v-btn>

                        <v-btn
                          size="small"
                          variant="tonal"
                          color="primary"
                          class="table-action-btn"
                          prepend-icon="mdi-refresh"
                          @click="reloadPlugin(item.name)"
                        >
                          {{ tm("buttons.reload") }}
                        </v-btn>

                        <v-btn
                          size="small"
                          variant="tonal"
                          color="primary"
                          class="table-action-btn"
                          prepend-icon="mdi-cog"
                          @click="openExtensionConfig(item.name)"
                        >
                          {{ tm("buttons.configure") }}
                        </v-btn>

                        <v-btn
                          size="small"
                          variant="tonal"
                          color="info"
                          class="table-action-btn"
                          prepend-icon="mdi-book-open-page-variant"
                          :disabled="!item.repo"
                          @click="item.repo && viewReadme(item)"
                        >
                          {{ tm("buttons.viewDocs") }}
                        </v-btn>

                        <StyledMenu location="bottom end" offset="8">
                          <template #activator="{ props: menuProps }">
                            <v-btn
                              v-bind="menuProps"
                              icon="mdi-dots-horizontal"
                              size="small"
                              variant="tonal"
                              color="secondary"
                              class="table-action-btn"
                            ></v-btn>
                          </template>

                          <v-list-item
                            class="styled-menu-item"
                            prepend-icon="mdi-information"
                            @click="showPluginInfo(item)"
                        >
                          <v-list-item-title>{{ tm("buttons.viewInfo") }}</v-list-item-title>
                        </v-list-item>

                          <v-list-item
                            class="styled-menu-item"
                            prepend-icon="mdi-update"
                            @click="updateExtension(item.name)"
                          >
                            <v-list-item-title>{{ tm("buttons.update") }}</v-list-item-title>
                          </v-list-item>

                          <v-list-item
                            class="styled-menu-item"
                            prepend-icon="mdi-delete"
                            :disabled="item.reserved"
                            @click="uninstallExtension(item.name)"
                          >
                            <v-list-item-title>{{ tm("buttons.uninstall") }}</v-list-item-title>
                          </v-list-item>
                        </StyledMenu>
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
                    >
                    </ExtensionCard>
                  </v-col>
                </v-row>
              </div>
            </v-fade-transition>

            <v-tooltip :text="tm('market.installPlugin')" location="left">
              <template v-slot:activator="{ props }">
                <button
                  v-bind="props"
                  type="button"
                  class="v-btn v-btn--elevated v-btn--icon v-theme--PurpleThemeDark bg-darkprimary v-btn--density-default v-btn--size-x-large v-btn--variant-elevated fab-button"
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
              class="rounded-lg"
              style="background-color: rgb(var(--v-theme-mcpCardBg))"
              @click="openPluginDetail(extension)"
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
            >
            </ExtensionCard>
          </v-col>
        </v-row>
      </div>
    </v-fade-transition>

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

    <v-tooltip :text="tm('buttons.updateAll')" location="left">
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
    </template>
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
</style>
