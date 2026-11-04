<script setup>
import ExtensionCard from "@/components/shared/ExtensionCard.vue";
import { normalizeTextInput } from "@/utils/inputValue";
import {
  readPinnedExtensions,
  writePinnedExtensions,
} from "./extensionPreferenceStorage.mjs";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  readPluginOrganizerPreferences,
  writePluginOrganizerPreferences,
} from "./pluginOrganizerStorage.mjs";

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
  sourceBindingDialog,
  selectedSourceBindingCandidate,
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
  editCustomSource,
  removeCustomSource,
  confirmRemoveSource,
  saveCustomSource,
  openPluginSourceBindingDialog,
  closePluginSourceBindingDialog,
  confirmPluginSourceBinding,
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

const openPluginDetail = (extension) => {
  if (!extension?.name) return;
  router.push({
    name: "ExtensionDetails",
    params: { pluginId: extension.name },
  });
};

const openPluginView = (extension) => {
  const pages = extension?.pages;
  if (!Array.isArray(pages) || pages.length === 0 || !extension?.name) return;
  router.push({
    name: "PluginView",
    params: {
      pluginName: extension.name,
      pageName: pages[0],
    },
  });
};

const pinnedExtensionNames = ref(readPinnedExtensions());
const organizerPreferences = ref(readPluginOrganizerPreferences());
const quickFilter = ref("all");
const selectedFolder = ref("*");
const draggedPluginName = ref("");
const dragOverFolder = ref(null);
const organizerAnchor = ref(null);
const organizerElement = ref(null);
const organizerFloating = ref(false);
const organizerPlaceholderHeight = ref(0);
let organizerResizeObserver = null;
const showNewFolderDialog = ref(false);
const newFolderName = ref("");
const pluginFolders = computed(() => organizerPreferences.value.folders);
const folderCards = computed(() => {
  const countForFolder = (folder) =>
    filteredPlugins.value.filter(
      (plugin) =>
        (organizerPreferences.value.assignments[plugin.name] || "") === folder,
    ).length;
  return [
    {
      key: "*",
      title: tm("organizer.all"),
      icon: "mdi-view-grid-outline",
      count: filteredPlugins.value.length,
    },
    {
      key: "",
      title: tm("organizer.uncategorized"),
      icon: "mdi-folder-outline",
      count: countForFolder(""),
    },
    ...pluginFolders.value.map((folder) => ({
      key: folder,
      title: folder,
      icon: "mdi-folder-outline",
      count: countForFolder(folder),
    })),
  ];
});
const organizerFilterOptions = [
  { value: "all", title: tm("organizer.filters.all") },
  { value: "active", title: tm("organizer.filters.active") },
  { value: "stopped", title: tm("organizer.filters.stopped") },
  { value: "updates", title: tm("organizer.filters.updates") },
  { value: "pinned", title: tm("organizer.filters.pinned") },
];
const organizerCounts = computed(() => ({
  total: filteredPlugins.value.length,
  active: filteredPlugins.value.filter((plugin) => plugin.activated).length,
  updates: filteredPlugins.value.filter((plugin) => plugin.has_update).length,
}));

watch(
  organizerPreferences,
  (preferences) => writePluginOrganizerPreferences(preferences),
  { deep: true },
);

const pinnedExtensionOrder = computed(() => {
  const order = new Map();
  pinnedExtensionNames.value.forEach((name, index) => {
    order.set(name, index);
  });
  return order;
});

const visibleInstalledPlugins = computed(() =>
  filteredPlugins.value.filter((plugin) => {
    const assignedFolder =
      organizerPreferences.value.assignments[plugin.name] || "";
    const matchesFolder =
      selectedFolder.value === "*" || assignedFolder === selectedFolder.value;
    const matchesQuickFilter =
      quickFilter.value === "all" ||
      (quickFilter.value === "active" && plugin.activated) ||
      (quickFilter.value === "stopped" && !plugin.activated) ||
      (quickFilter.value === "updates" && plugin.has_update) ||
      (quickFilter.value === "pinned" && isPinnedExtension(plugin));
    return matchesFolder && matchesQuickFilter;
  }),
);

const sortedInstalledPlugins = computed(() => {
  const order = pinnedExtensionOrder.value;
  return [...visibleInstalledPlugins.value].sort((a, b) => {
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

const measureOrganizer = () => {
  if (!organizerElement.value) return;
  if (!organizerFloating.value) {
    organizerPlaceholderHeight.value =
      organizerElement.value.getBoundingClientRect().height;
  }
};

const updateOrganizerPosition = () => {
  const hasRoomForSidebar = window.matchMedia("(min-width: 1500px)").matches;
  const anchor = organizerAnchor.value;
  if (!hasRoomForSidebar || !anchor) {
    organizerFloating.value = false;
    return;
  }
  // Read the in-flow anchor so this works when the dashboard scrolls inside
  // a nested container instead of scrolling the window itself.
  const bounds = anchor.getBoundingClientRect();
  if (!organizerFloating.value && bounds.bottom < 0)
    organizerFloating.value = true;
  else if (organizerFloating.value && bounds.top > 120)
    organizerFloating.value = false;
};

const handleOrganizerResize = () => {
  if (!window.matchMedia("(min-width: 1500px)").matches)
    organizerFloating.value = false;
  requestAnimationFrame(() => {
    measureOrganizer();
    updateOrganizerPosition();
  });
};

onMounted(() => {
  measureOrganizer();
  updateOrganizerPosition();
  window.addEventListener("scroll", updateOrganizerPosition, {
    passive: true,
    capture: true,
  });
  window.addEventListener("resize", handleOrganizerResize, { passive: true });
  organizerResizeObserver = new ResizeObserver(measureOrganizer);
  if (organizerElement.value)
    organizerResizeObserver.observe(organizerElement.value);
});

onBeforeUnmount(() => {
  window.removeEventListener("scroll", updateOrganizerPosition, true);
  window.removeEventListener("resize", handleOrganizerResize);
  organizerResizeObserver?.disconnect();
});

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

const extensionFolder = (extension) =>
  organizerPreferences.value.assignments[extension.name] || "";

const extensionFolderLabel = (extension) =>
  extensionFolder(extension) || tm("organizer.uncategorized");

const setExtensionFolder = (extensionName, folder) => {
  const assignments = { ...organizerPreferences.value.assignments };
  if (folder) assignments[extensionName] = folder;
  else delete assignments[extensionName];
  organizerPreferences.value = { ...organizerPreferences.value, assignments };
};

const handlePluginDragStart = (extension, event) => {
  if (event.target.closest("button, a, input, .v-switch, .v-btn")) {
    event.preventDefault();
    return;
  }
  draggedPluginName.value = extension.name;
  event.dataTransfer?.setData("text/plain", extension.name);
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
};

const handlePluginDrop = (folder, event) => {
  event.preventDefault();
  const pluginName =
    event.dataTransfer?.getData("text/plain") || draggedPluginName.value;
  if (!pluginName) return;
  setExtensionFolder(pluginName, folder === "*" ? "" : folder);
  draggedPluginName.value = "";
  dragOverFolder.value = null;
};

const createPluginFolder = () => {
  const name = newFolderName.value.trim();
  if (!name || pluginFolders.value.includes(name)) return;
  organizerPreferences.value = {
    ...organizerPreferences.value,
    folders: [...pluginFolders.value, name],
  };
  selectedFolder.value = name;
  newFolderName.value = "";
  showNewFolderDialog.value = false;
};

const removeSelectedPluginFolder = () => {
  const folder = selectedFolder.value;
  if (!folder || folder === "*") return;
  const assignments = Object.fromEntries(
    Object.entries(organizerPreferences.value.assignments).filter(
      ([, assignedFolder]) => assignedFolder !== folder,
    ),
  );
  organizerPreferences.value = {
    folders: pluginFolders.value.filter((item) => item !== folder),
    assignments,
  };
  selectedFolder.value = "*";
};
</script>

<template>
  <v-tab-item v-show="activeTab === 'installed'">
    <div class="mb-4 pt-4 pb-4">
      <div class="installed-header-row d-flex align-center flex-wrap">
        <v-tabs
          model-value="installed"
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

        <div class="installed-search-wrap d-flex align-center ml-auto">
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
            class="plugin-search-field"
          >
          </v-text-field>
        </div>
      </div>
      <div
        ref="organizerAnchor"
        class="plugin-organizer-anchor"
        :style="
          organizerFloating
            ? { minHeight: `${organizerPlaceholderHeight + 16}px` }
            : undefined
        "
      >
        <Teleport to="body" :disabled="!organizerFloating">
          <section
            ref="organizerElement"
            class="plugin-organizer mt-4"
            :class="{ 'plugin-organizer--floating': organizerFloating }"
            :aria-label="tm('organizer.title')"
          >
            <div class="plugin-organizer__heading">
              <div>
                <h2 class="text-subtitle-1 font-weight-bold">
                  {{ tm("organizer.title") }}
                </h2>
                <p class="text-body-2 text-medium-emphasis mb-0">
                  {{ tm("organizer.hint") }}
                </p>
              </div>
              <v-btn
                color="primary"
                variant="tonal"
                prepend-icon="mdi-folder-plus-outline"
                @click="showNewFolderDialog = true"
                >{{ tm("organizer.newFolder") }}</v-btn
              >
            </div>

            <div class="plugin-folder-grid">
              <v-card
                v-for="folder in folderCards"
                :key="folder.key || 'uncategorized'"
                class="plugin-folder-card"
                :class="{
                  'plugin-folder-card--all': folder.key === '*',
                  'plugin-folder-card--selected': selectedFolder === folder.key,
                  'plugin-folder-card--drop-target':
                    dragOverFolder === folder.key,
                }"
                variant="outlined"
                :aria-pressed="selectedFolder === folder.key"
                role="button"
                tabindex="0"
                @click="selectedFolder = folder.key"
                @keydown.enter.prevent="selectedFolder = folder.key"
                @keydown.space.prevent="selectedFolder = folder.key"
                @dragover.prevent="
                  folder.key !== '*' && (dragOverFolder = folder.key)
                "
                @dragleave="dragOverFolder = null"
                @drop.prevent="
                  folder.key !== '*' && handlePluginDrop(folder.key, $event)
                "
              >
                <div class="plugin-folder-card__icon">
                  <v-icon :icon="folder.icon" size="24" />
                </div>
                <div class="plugin-folder-card__details">
                  <div class="plugin-folder-card__title">
                    {{ folder.title }}
                  </div>
                  <div
                    class="plugin-folder-card__count text-caption text-medium-emphasis"
                  >
                    {{ tm("organizer.count", { count: folder.count }) }}
                  </div>
                </div>
                <v-icon
                  v-if="selectedFolder === folder.key"
                  icon="mdi-check-circle"
                  color="primary"
                  size="18"
                  class="plugin-folder-card__selected-icon"
                />
              </v-card>
            </div>
            <div class="plugin-organizer__footer">
              <div
                class="plugin-organizer__stats text-body-2 text-medium-emphasis"
              >
                <span>{{
                  tm("organizer.stats.plugins", {
                    count: organizerCounts.total,
                  })
                }}</span>
                <span>{{
                  tm("organizer.stats.running", {
                    count: organizerCounts.active,
                  })
                }}</span>
                <span>{{
                  tm("organizer.stats.updates", {
                    count: organizerCounts.updates,
                  })
                }}</span>
              </div>
              <v-btn-toggle
                v-model="quickFilter"
                color="primary"
                mandatory
                divided
                density="comfortable"
                variant="outlined"
                class="plugin-organizer__filter-toggle"
                :aria-label="tm('organizer.filterLabel')"
              >
                <v-btn
                  v-for="option in organizerFilterOptions"
                  :key="option.value"
                  :value="option.value"
                  size="small"
                  :aria-pressed="quickFilter === option.value"
                  >{{ option.title }}</v-btn
                >
              </v-btn-toggle>
              <v-btn
                v-if="selectedFolder !== '*' && selectedFolder !== ''"
                color="error"
                variant="text"
                prepend-icon="mdi-folder-remove-outline"
                @click="removeSelectedPluginFolder"
                >{{ tm("organizer.deleteFolder") }}</v-btn
              >
            </div>
          </section>
        </Teleport>
      </div>
    </div>

    <v-dialog v-model="showNewFolderDialog" max-width="420">
      <v-card>
        <v-card-title>{{ tm("organizer.newFolderTitle") }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="newFolderName"
            :label="tm('organizer.folderName')"
            prepend-inner-icon="mdi-folder-outline"
            autofocus
            maxlength="40"
            counter
            @keydown.enter="createPluginFolder"
          />
          <div
            v-if="
              newFolderName.trim() &&
              pluginFolders.includes(newFolderName.trim())
            "
            class="text-caption text-error"
          >
            {{ tm("organizer.duplicateFolder") }}
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="showNewFolderDialog = false">{{
            tm("buttons.cancel")
          }}</v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :disabled="
              !newFolderName.trim() ||
              pluginFolders.includes(newFolderName.trim())
            "
            @click="createPluginFolder"
            >{{ tm("organizer.createFolder") }}</v-btn
          >
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

        <v-row
          v-else-if="sortedInstalledPlugins.length === 0"
          class="text-center"
        >
          <v-col cols="12" class="pa-8 text-body-1 text-medium-emphasis">
            {{ tm("organizer.noMatch") }}
          </v-col>
        </v-row>

        <TransitionGroup
          v-if="sortedInstalledPlugins.length > 0"
          name="plugin-list"
          tag="div"
          class="v-row"
        >
          <v-col
            cols="12"
            md="6"
            v-for="extension in sortedInstalledPlugins"
            :key="extension.name"
            class="pb-2"
            :class="{
              'plugin-card-column--dragging':
                draggedPluginName === extension.name,
            }"
            draggable="true"
            @dragstart="handlePluginDragStart(extension, $event)"
            @dragend="
              draggedPluginName = '';
              dragOverFolder = null;
            "
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
              @open-view="openPluginView(extension)"
              @change-source="openPluginSourceBindingDialog(extension)"
            >
              <template #management>
                <div class="plugin-card-folder-label" @click.stop>
                  <v-icon icon="mdi-folder-outline" size="16" />
                  <span>{{ extensionFolderLabel(extension) }}</span>
                  <v-menu location="bottom end">
                    <template #activator="{ props: folderMenuProps }">
                      <v-btn
                        v-bind="folderMenuProps"
                        icon="mdi-folder-move-outline"
                        size="x-small"
                        variant="text"
                        :aria-label="tm('organizer.moveToFolder')"
                      />
                    </template>
                    <v-list density="compact">
                      <v-list-item
                        :title="tm('organizer.uncategorized')"
                        prepend-icon="mdi-folder-outline"
                        @click="setExtensionFolder(extension.name, '')"
                      />
                      <v-list-item
                        v-for="folder in pluginFolders"
                        :key="folder"
                        :title="folder"
                        prepend-icon="mdi-folder-outline"
                        @click="setExtensionFolder(extension.name, folder)"
                      />
                    </v-list>
                  </v-menu>
                </div>
              </template>
            </ExtensionCard>
          </v-col>
        </TransitionGroup>
      </div>
    </v-fade-transition>

    <v-dialog v-model="sourceBindingDialog.show" max-width="680">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
          {{
            sourceBindingDialog.pendingUpdate
              ? tm("dialogs.sourceBinding.selectTitle")
              : tm("dialogs.sourceBinding.title")
          }}
        </v-card-title>
        <v-card-text>
          <div
            v-if="sourceBindingDialog.extension"
            class="text-body-2 text-medium-emphasis mb-3"
          >
            {{
              sourceBindingDialog.extension.display_name ||
              sourceBindingDialog.extension.name
            }}
          </div>

          <v-progress-linear
            v-if="sourceBindingDialog.loading"
            color="primary"
            indeterminate
          />

          <v-alert
            v-else-if="sourceBindingDialog.candidates.length === 0"
            type="info"
            variant="tonal"
            density="comfortable"
          >
            {{ tm("dialogs.sourceBinding.noCandidates") }}
          </v-alert>

          <v-radio-group
            v-else
            v-model="sourceBindingDialog.selectedKey"
            hide-details
          >
            <v-radio
              v-for="candidate in sourceBindingDialog.candidates"
              :key="candidate.key"
              :value="candidate.key"
              color="primary"
            >
              <template #label>
                <div class="py-2">
                  <div class="font-weight-medium">
                    {{ candidate.registry_name }}
                  </div>
                </div>
              </template>
            </v-radio>
          </v-radio-group>
          <div
            v-if="selectedSourceBindingCandidate"
            class="text-caption text-medium-emphasis mt-2"
          >
            <div>
              {{ tm("dialogs.sourceBinding.installDestination") }}:
              {{
                selectedSourceBindingCandidate.download_url ||
                selectedSourceBindingCandidate.repo
              }}
            </div>
            <div class="d-flex align-center" style="gap: 4px">
              <span>{{ tm("table.headers.version") }}:</span>
              <span
                v-if="
                  selectedSourceBindingCandidate.validation_status === 'loading'
                "
                class="d-inline-flex align-center"
                style="height: 16px"
              >
                <v-progress-circular
                  indeterminate
                  size="14"
                  width="1"
                  color="primary"
                />
              </span>
              <span v-else>
                {{
                  selectedSourceBindingCandidate.version || tm("status.unknown")
                }}
              </span>
            </div>
          </div>
          <v-alert
            v-if="selectedSourceBindingCandidate?.validation_status === 'error'"
            type="error"
            variant="tonal"
            density="compact"
            class="mt-3"
          >
            {{ selectedSourceBindingCandidate.validation_message }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="closePluginSourceBindingDialog">
            {{ tm("buttons.cancel") }}
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="sourceBindingDialog.saving"
            :disabled="
              sourceBindingDialog.loading ||
              sourceBindingDialog.candidates.length === 0 ||
              !sourceBindingDialog.selectedKey ||
              (selectedSourceBindingCandidate?.install_method ===
                'repository' &&
                selectedSourceBindingCandidate?.validation_status !== 'valid')
            "
            @click="confirmPluginSourceBinding"
          >
            {{
              sourceBindingDialog.pendingUpdate
                ? tm("dialogs.sourceBinding.confirmAndContinue")
                : tm("dialogs.sourceBinding.confirm")
            }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

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

.installed-header-row {
  gap: 12px;
}

.installed-search-wrap {
  flex: 0 1 340px;
  min-width: 220px;
}

.plugin-search-field {
  width: 100%;
}

.plugin-organizer-anchor {
  display: flow-root;
}

.plugin-organizer {
  padding: 18px 20px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity, 0.12));
  border-radius: 16px;
  background: rgb(var(--v-theme-surface));
}

.plugin-organizer__heading,
.plugin-organizer__footer,
.plugin-organizer__stats {
  display: flex;
  align-items: center;
  gap: 12px;
}

.plugin-organizer__heading,
.plugin-organizer__footer {
  justify-content: space-between;
  flex-wrap: wrap;
}

.plugin-folder-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  grid-auto-rows: 1fr;
  gap: 12px;
  margin-top: 12px;
}

.plugin-folder-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-width: 0;
  min-height: 84px;
  height: 100%;
  box-sizing: border-box;
  padding: 14px;
  border-radius: 14px;
  cursor: pointer;
  transition:
    border-color 160ms ease,
    background-color 160ms ease,
    box-shadow 160ms ease;
}

.plugin-folder-card--all .plugin-folder-card__title {
  white-space: nowrap;
}

.plugin-folder-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.62);
  background: rgba(var(--v-theme-primary), 0.045);
}

.plugin-folder-card--selected {
  border-color: rgb(var(--v-theme-primary)) !important;
  background: rgba(var(--v-theme-primary), 0.09);
  box-shadow: 0 0 0 1px rgba(var(--v-theme-primary), 0.18);
}

.plugin-folder-card--drop-target {
  border: 2px dashed rgb(var(--v-theme-primary)) !important;
  background: rgba(var(--v-theme-primary), 0.14);
}

.plugin-folder-card:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.plugin-folder-card__icon {
  display: grid;
  flex: 0 0 44px;
  width: 44px;
  height: 44px;
  place-items: center;
  border-radius: 12px;
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
}

.plugin-folder-card__details {
  min-width: 0;
  flex: 1 1 auto;
}

.plugin-folder-card__title {
  font-weight: 650;
  line-height: 1.3;
  overflow-wrap: anywhere;
  white-space: normal;
}

.plugin-folder-card__count {
  margin-top: 3px;
  white-space: nowrap;
}

.plugin-folder-card__selected-icon {
  flex: 0 0 auto;
  margin-left: auto;
}

.plugin-organizer__stats {
  flex-wrap: wrap;
}

.plugin-organizer__stats span + span::before {
  content: "·";
  margin-right: 12px;
  color: rgba(var(--v-theme-on-surface), 0.4);
}

.plugin-organizer__filter-toggle {
  flex-wrap: wrap;
  height: auto;
}

.plugin-organizer__filter-toggle :deep(.v-btn) {
  min-height: 38px;
  letter-spacing: 0;
  text-transform: none;
}

.plugin-list-enter-active,
.plugin-list-leave-active,
.plugin-list-move {
  transition:
    opacity 180ms ease,
    transform 180ms ease;
}

.plugin-list-enter-from,
.plugin-list-leave-to {
  opacity: 0;
  transform: translateY(10px);
}

@media (prefers-reduced-motion: reduce) {
  .plugin-list-enter-active,
  .plugin-list-leave-active,
  .plugin-list-move {
    transition: none;
  }
}

.plugin-card-column--dragging {
  opacity: 0.48;
}

.plugin-card-folder-label {
  display: flex;
  align-items: center;
  gap: 6px;
  width: fit-content;
  margin: 10px 0 0 auto;
  padding: 3px 5px 3px 9px;
  border-radius: 999px;
  background: rgba(var(--v-theme-primary), 0.08);
  color: rgba(var(--v-theme-on-surface), 0.72);
  font-size: 12px;
}
@media (min-width: 1500px) {
  .plugin-organizer--floating {
    position: fixed;
    z-index: 1000;
    top: 88px;
    right: 24px;
    width: 360px;
    max-width: calc(100vw - 32px);
    box-sizing: border-box;
    max-height: calc(100vh - 112px);
    overflow-y: auto;
    border-color: rgba(var(--v-theme-primary), 0.2);
    background: rgb(var(--v-theme-surface));
    box-shadow: 0 16px 42px rgba(15, 23, 42, 0.16);
  }

  .plugin-organizer--floating .plugin-folder-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .plugin-organizer--floating .plugin-folder-card {
    grid-column: auto;
    min-height: 68px;
  }

  .plugin-organizer--floating .plugin-organizer__heading {
    align-items: flex-start;
  }

  .plugin-organizer--floating .plugin-organizer__heading .v-btn {
    width: 100%;
  }

  .plugin-organizer--floating .plugin-organizer__stats {
    gap: 6px 10px;
  }

  .plugin-organizer--floating .plugin-organizer__filter-toggle {
    width: 100%;
  }

  .plugin-organizer--floating .plugin-organizer__filter-toggle :deep(.v-btn) {
    flex: 1 1 30%;
    padding-inline: 8px;
  }
}

@media (max-width: 700px) {
  .plugin-organizer {
    padding: 15px 14px;
  }

  .plugin-organizer__heading,
  .plugin-organizer__footer {
    align-items: flex-start;
  }

  .plugin-organizer__stats,
  .plugin-organizer__filter-toggle {
    width: 100%;
  }

  .plugin-organizer__filter-toggle :deep(.v-btn) {
    flex: 1 1 auto;
    padding-inline: 8px;
  }

  .plugin-folder-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .plugin-folder-card--all .plugin-folder-card__title {
    white-space: normal;
  }

  .plugin-folder-card {
    min-height: 76px;
    gap: 9px;
    padding: 11px;
  }

  .plugin-folder-card__icon {
    flex-basis: 38px;
    width: 38px;
    height: 38px;
  }

  .installed-header-row {
    align-items: stretch !important;
    flex-direction: column;
  }

  .installed-search-wrap {
    flex: none;
    margin-left: 0 !important;
    min-width: 0;
    width: 100%;
  }

  .plugin-view-tab {
    font-size: 1.125rem;
    padding-inline: 8px;
  }
}

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
