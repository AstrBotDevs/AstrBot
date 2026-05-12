<script setup>
import ExtensionCard from "@/components/shared/ExtensionCard.vue";
import PluginImportDialog from "@/components/extension/PluginImportDialog.vue";
import { normalizeTextInput } from "@/utils/inputValue";
import LZString from 'lz-string';
import defaultPluginIcon from "@/assets/images/plugin_icon.png";
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


const showExportCode = ref(false);
const exportCode = ref("");

const EXPORT_BLACKLIST = new Set(["astrbot", "builtin_commands"]);
const exportablePlugins = computed(() =>
  filteredPlugins.value.filter(
    (p) => p?.name && !EXPORT_BLACKLIST.has(p.name),
  ),
);

const exportPlugin = (pluginList) => {
  if (!pluginList || pluginList.length === 0) {
    toast("没有可导出的插件", "warning");
    return;
  }
  showExportCode.value = true;
  const jsonStr = JSON.stringify(
    pluginList.map((plugin) => ({
      name: plugin.name,
      version: plugin.version,
      repo: plugin.repo,
      logo: plugin.logo,
    })),
  );
  exportCode.value = LZString.compressToEncodedURIComponent(jsonStr);
}

const exportFiltered = () => {
  exportPlugin(exportablePlugins.value);
}

const exportPinned = () => {
  const pinnedNames = pinnedExtensionNames.value;
  const pinned = exportablePlugins.value.filter((p) => pinnedNames.includes(p?.name));
  exportPlugin(pinned);
}

const showExportSelectDialog = ref(false);
const exportSelected = ref([]);

const openExportSelectDialog = () => {
  exportSelected.value = exportablePlugins.value.map(() => false);
  showExportSelectDialog.value = true;
}

const selectedExportCount = computed(() =>
  exportSelected.value.filter(Boolean).length,
);

const allExportSelected = computed(
  () =>
    exportablePlugins.value.length > 0 &&
    selectedExportCount.value === exportablePlugins.value.length,
);

const someExportSelected = computed(
  () => selectedExportCount.value > 0 && !allExportSelected.value,
);

const toggleExportSelectAll = () => {
  const next = !allExportSelected.value;
  exportSelected.value = exportablePlugins.value.map(() => next);
}

const confirmExportSelected = () => {
  const picked = exportablePlugins.value.filter((_, i) => exportSelected.value[i]);
  if (picked.length === 0) {
    toast("请至少选择一个插件", "warning");
    return;
  }
  showExportSelectDialog.value = false;
  exportPlugin(picked);
}

const copyExportCode = async () => {
  try {
    await navigator.clipboard.writeText(exportCode.value);
    toast("已复制到剪贴板", "success");
  } catch (err) {
    console.error("复制失败", err);
    toast("复制失败", "error");
  }
}

const showImportDialog = ref(false);

const openImportDialog = () => {
  showImportDialog.value = true;
}

</script>

<template>
  <v-tab-item v-show="activeTab === 'installed'">
    <div class="mb-4 pt-4 pb-4">
      <div class="d-flex align-center flex-wrap" style="gap: 12px">
        <h2 class="text-h2 mb-0">{{ tm("titles.installedAstrBotPlugins") }}</h2>

        <div class="d-flex align-center flex-wrap ml-auto" style="gap: 8px">

          <v-menu>
            <template #activator="{ props: menuProps }">
              <v-btn
                v-bind="menuProps"
                color="primary"
                variant="tonal"
                prepend-icon="mdi-export-variant"
                append-icon="mdi-menu-down"
              >
                导出插件
              </v-btn>
            </template>
            <v-list density="compact">
              <v-list-item prepend-icon="mdi-filter-variant" @click="exportFiltered">
                <v-list-item-title>导出全部筛选出的插件</v-list-item-title>
              </v-list-item>
              <v-list-item prepend-icon="mdi-pin" @click="exportPinned">
                <v-list-item-title>导出置顶的插件</v-list-item-title>
              </v-list-item>
              <v-list-item prepend-icon="mdi-cursor-default-click-outline" @click="openExportSelectDialog">
                <v-list-item-title>挑选插件导出</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>

          <v-btn
            color="primary"
            variant="tonal"
            prepend-icon="mdi-import"
            @click="openImportDialog"
          >
            导入插件
          </v-btn>
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

      <v-expand-transition>
        <v-card v-if="showExportCode" class="mt-3 rounded-lg" variant="outlined">
          <v-card-title class="d-flex align-center pa-3">
            <v-icon class="mr-2" size="small">mdi-code-braces</v-icon>
            <span class="text-body-1">插件码</span>
            <v-spacer />
            <v-btn icon="mdi-content-copy" variant="text" size="small" @click="copyExportCode" />
            <v-btn icon="mdi-close" variant="text" size="small" @click="showExportCode = false" />
          </v-card-title>
          <v-card-text class="pt-0">
            <v-textarea
              :model-value="exportCode"
              readonly
              variant="outlined"
              density="compact"
              auto-grow
              rows="3"
              max-rows="8"
              hide-details
              class="export-code-textarea"
            />
          </v-card-text>
        </v-card>
      </v-expand-transition>
    </div>

    <PluginImportDialog v-model="showImportDialog" />

    <v-dialog v-model="showExportSelectDialog" max-width="640">
      <v-card class="rounded-lg">
        <v-card-title class="d-flex align-center pa-4">
          <v-icon class="mr-2">mdi-cursor-default-click-outline</v-icon>
          <span>挑选插件导出</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showExportSelectDialog = false" />
        </v-card-title>
        <v-card-text>
          <div class="d-flex align-center mb-2">
            <v-checkbox
              :model-value="allExportSelected"
              :indeterminate="someExportSelected"
              density="compact"
              hide-details
              color="primary"
              @update:model-value="toggleExportSelectAll"
            />
            <span class="text-body-2 ml-1">
              共 {{ exportablePlugins.length }} 个插件，已选 {{ selectedExportCount }} 个
            </span>
          </div>
          <v-list density="compact" style="max-height: 400px; overflow-y: auto;">
            <v-list-item
              v-for="(plugin, idx) in exportablePlugins"
              :key="plugin.name || idx"
              class="rounded-lg mb-1"
              border
            >
              <template #prepend>
                <v-checkbox
                  :model-value="!!exportSelected[idx]"
                  density="compact"
                  hide-details
                  color="primary"
                  @update:model-value="exportSelected[idx] = !exportSelected[idx]"
                />

                <v-avatar size="32" class="mr-2" rounded="lg">
                  <v-img
                    :src="plugin.logo || defaultPluginIcon"
                    :alt="plugin.name"
                    cover
                  >
                    <template #error>
                      <v-img :src="defaultPluginIcon" cover />
                    </template>
                  </v-img>
                </v-avatar>
              </template>
              <v-list-item-title class="text-body-2 font-weight-medium">
                {{ plugin.name || "(未命名)" }}
                <span class="text-caption text-medium-emphasis ml-2">
                  v{{ plugin.version || "?" }}
                </span>
              </v-list-item-title>
              <v-list-item-subtitle v-if="plugin.repo" class="text-caption">
                {{ plugin.repo }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" size="small" @click="showExportSelectDialog = false">
            取消
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            size="small"
            :disabled="selectedExportCount === 0"
            @click="confirmExportSelected"
          >
            导出 ({{ selectedExportCount }})
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

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
