<script setup>
import ExtensionCard from "@/components/shared/ExtensionCard.vue";
import { normalizeTextInput } from "@/utils/inputValue";
import {
  readPinnedExtensions,
  writePinnedExtensions,
} from "./extensionPreferenceStorage.mjs";
import { computed, ref, watch } from "vue";

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
  showPluginInfoDialog,
  selectedPlugin,
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
  plugin_handler_info_headers,
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
    const aIndex = order.has(a?.name) ? order.get(a.name) : Number.POSITIVE_INFINITY;
    const bIndex = order.has(b?.name) ? order.get(b.name) : Number.POSITIVE_INFINITY;

    if (aIndex !== bIndex) {
      return aIndex - bIndex;
    }
    return 0;
  });
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
                      v-for="extension in filteredPlugins"
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
