<script setup>
import ExtensionCard from "@/components/shared/ExtensionCard.vue";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import defaultPluginIcon from "@/assets/images/plugin_icon.png";

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
</script>

<template>
          <v-tab-item v-show="activeTab === 'installed'">
            <div class="mb-4 pt-4 pb-4">
              <div class="d-flex align-center flex-wrap" style="gap: 12px">
                <h2 class="text-h2 mb-0">{{ tm("titles.installedAstrBotPlugins") }}</h2>

                <div class="d-flex align-center flex-wrap ml-auto" style="gap: 8px">
                  <v-text-field
                    v-model="pluginSearch"
                    density="compact"
                    :label="tm('search.placeholder')"
                    prepend-inner-icon="mdi-magnify"
                    variant="solo-filled"
                    flat
                    hide-details
                    single-line
                    style="min-width: 220px; max-width: 340px"
                  >
                  </v-text-field>

                  <v-btn-toggle
                    v-model="isListView"
                    mandatory
                    density="compact"
                    color="primary"
                    class="view-mode-toggle"
                  >
                    <v-btn :value="false" icon="mdi-view-grid"></v-btn>
                    <v-btn :value="true" icon="mdi-view-list"></v-btn>
                  </v-btn-toggle>
                </div>
              </div>
            </div>

            <v-row class="mb-4">
              <v-col cols="12" class="d-flex align-center flex-wrap ga-2">
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
                  class="ml-2"
                  color="warning"
                  variant="tonal"
                  :disabled="updatableExtensions.length === 0"
                  :loading="updatingAll"
                  @click="showUpdateAllConfirm"
                >
                  <v-icon>mdi-update</v-icon>
                  {{ tm("buttons.updateAll") }}
                </v-btn>

                <v-dialog max-width="500px" v-if="extension_data.message">
                  <template v-slot:activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon
                      size="small"
                      color="error"
                      class="ml-auto"
                      variant="tonal"
                    >
                      <v-icon>mdi-alert-circle</v-icon>
                    </v-btn>
                  </template>
                  <template v-slot:default="{ isActive }">
                    <v-card class="rounded-lg">
                      <v-card-title class="headline d-flex align-center">
                        <v-icon color="error" class="mr-2"
                          >mdi-alert-circle</v-icon
                        >
                        {{ tm("dialogs.error.title") }}
                      </v-card-title>
                      <v-card-text>
                        <p class="text-body-1">
                          {{ extension_data.message }}
                        </p>
                        <p class="text-caption mt-2">
                          {{ tm("dialogs.error.checkConsole") }}
                        </p>
                      </v-card-text>
                      <v-card-actions>
                        <v-btn
                            color="error"
                            variant="tonal"
                            prepend-icon="mdi-refresh"
                            @click="handleReloadAllFailed"
                        >
                            尝试一键重载修复
                        </v-btn>
                        <v-spacer></v-spacer>
                        <v-btn
                          color="primary"
                          @click="isActive.value = false"
                          >{{ tm("buttons.close") }}</v-btn
                        >
                      </v-card-actions>
                    </v-card>
                  </template>
                </v-dialog>
              </v-col>
            </v-row>

            <v-fade-transition hide-on-leave>
              <!-- 表格视图 -->
              <div v-if="isListView">
                <v-card class="rounded-lg overflow-hidden elevation-0">
                  <v-data-table
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
                        <v-icon
                          v-if="item.has_update"
                          color="warning"
                          size="small"
                          class="ml-1"
                          >mdi-alert</v-icon
                        >
                        <v-tooltip v-if="item.has_update" activator="parent">
                          <span
                            >{{ tm("messages.hasUpdate") }}
                            {{ item.online_version }}</span
                          >
                        </v-tooltip>
                      </div>
                    </template>

                    <template v-slot:item.author="{ item }">
                      <div class="text-body-2">{{ item.author }}</div>
                    </template>

                    <template v-slot:item.actions="{ item }">
                      <div class="table-action-row d-flex align-center flex-nowrap ga-2 py-1">
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
          </v-tab-item>
</template>

<style scoped>
.view-mode-toggle :deep(.v-btn) {
  min-width: 30px;
  height: 28px;
  padding: 0 8px;
}

.table-action-btn {
  min-height: 34px;
  font-size: 0.9rem;
  font-weight: 600;
}

.table-action-row {
  overflow-x: auto;
  white-space: nowrap;
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
