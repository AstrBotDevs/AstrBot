<script setup lang="ts">
import PluginSortControl from "@/components/extension/PluginSortControl.vue";
import PinnedPluginItem from "@/components/extension/PinnedPluginItem.vue";
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
  tm,
  extension_data,
  showReserved,
  pluginMarketData,
  updatingAll,
  isListView,
  pluginSearch,
  installedStatusFilter,
  installedSortBy,
  installedSortOrder,
  loading_,
  filteredPlugins,
  failedPluginItems,
  reloadFailedPlugin,
  requestUninstallFailedPlugin,
  pluginHeaders,
  pluginOn,
  pluginOff,
  reloadPlugin,
  openExtensionConfig,
  viewReadme,
  showPluginInfo,
  uninstallExtension,
  updateExtension,
  viewChangelog,
  dialog,
  sortedPlugins,
  installedSortItems,
  installedSortUsesOrder,
  updatableExtensions,
  toggleShowReserved,
  showUpdateAllConfirm,
} = props.state;

// 置顶插件（保存在 localStorage）
const PINNED_KEY = "astrbot.pinnedExtensions";
const pinnedNames = ref<string[]>([]);

const loadPinned = () => {
  try {
    const raw = localStorage.getItem(PINNED_KEY);
    pinnedNames.value = raw ? JSON.parse(raw) : [];
  } catch (e) {
    pinnedNames.value = [];
  }
};

const savePinned = () => {
  try {
    localStorage.setItem(PINNED_KEY, JSON.stringify(pinnedNames.value || []));
  } catch (e) {
    // ignore
  }
};

loadPinned();

watch(pinnedNames, () => savePinned(), { deep: true });

const isPinned = (name: string) => {
  return pinnedNames.value.includes(name);
};

const togglePin = (extension: { name: string }) => {
  const name = extension?.name;
  if (!name) return;
  const idx = pinnedNames.value.indexOf(name);
  if (idx === -1) pinnedNames.value.push(name);
  else pinnedNames.value.splice(idx, 1);
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
    toast(tm("exportImport.errors.nothingToExport"), "warning");
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
    toast(tm("exportImport.errors.needOneSelection"), "warning");
    return;
  }
  showExportSelectDialog.value = false;
  exportPlugin(picked);
}

const copyExportCode = async () => {
  try {
    await navigator.clipboard.writeText(exportCode.value);
    toast(tm("exportImport.errors.copySuccess"), "success");
  } catch (err) {
    console.error("Copy failed", err);
    toast(tm("exportImport.errors.copyFailed"), "error");
  }
}

const showImportDialog = ref(false);

const openImportDialog = () => {
  showImportDialog.value = true;
}

</script>

<template>
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
                {{ tm("exportImport.exportPlugin") }}
              </v-btn>
            </template>
            <v-list density="compact">
              <v-list-item prepend-icon="mdi-filter-variant" @click="exportFiltered">
                <v-list-item-title>{{ tm("exportImport.exportFiltered") }}</v-list-item-title>
              </v-list-item>
              <v-list-item prepend-icon="mdi-pin" @click="exportPinned">
                <v-list-item-title>{{ tm("exportImport.exportPinned") }}</v-list-item-title>
              </v-list-item>
              <v-list-item prepend-icon="mdi-cursor-default-click-outline" @click="openExportSelectDialog">
                <v-list-item-title>{{ tm("exportImport.exportSelected") }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>

          <v-btn
            color="primary"
            variant="tonal"
            prepend-icon="mdi-import"
            @click="openImportDialog"
          >
            {{ tm("exportImport.importPlugin") }}
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
            <span class="text-body-1">{{ tm("exportImport.pluginCode") }}</span>
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
  </div>

    <PluginImportDialog v-model="showImportDialog" :proxy="getSelectedGitHubProxy()" @done="getExtensions" />

    <v-dialog v-model="showExportSelectDialog" max-width="640">
      <v-card class="rounded-lg">
        <v-card-title class="d-flex align-center pa-4">
          <v-icon class="mr-2">mdi-cursor-default-click-outline</v-icon>
          <span>{{ tm("exportImport.exportSelected") }}</span>
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
              {{ tm("exportImport.exportSummary", { total: exportablePlugins.length, selected: selectedExportCount }) }}
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
                {{ plugin.name || tm("exportImport.unnamed") }}
                <span class="text-caption text-medium-emphasis ml-2">
                  v{{ plugin.version || "?" }}
                </span>
              </v-list-item-title>
              <v-list-item-subtitle v-if="plugin.repo" class="text-caption">
                <a
                  :href="plugin.repo"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="repo-link"
                  @click.stop
                >
                  {{ plugin.repo }}
                </a>
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions class="pa-4 pt-0">
          <v-spacer />
          <v-btn variant="text" size="small" @click="showExportSelectDialog = false">
            {{ tm("exportImport.cancel") }}
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            size="small"
            :disabled="selectedExportCount === 0"
            @click="confirmExportSelected"
          >
            {{ tm("exportImport.export") }} ({{ selectedExportCount }})
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

  <!-- 置顶插件列表 -->
  <v-row class="mb-4">
    <v-col cols="12">
      <v-card class="rounded-lg overflow-hidden elevation-0" variant="flat">
        <v-card-text class="pa-4">
          <div class="d-flex align-center justify-space-between">
            <h3 class="text-h6 mb-0">{{ tm("titles.pinnedPlugins") }}</h3>
          </div>

          <v-row
            class="mt-3 relative"
            density="compact"
            align="center"
            style="gap: 12px"
          >
            <template v-if="!pinnedPlugins || pinnedPlugins.length === 0">
              <v-col v-for="n in 4" :key="n" cols="auto" />
            </template>

            <transition-group name="list" class="v-row v-row-density-compact">
              <v-col
                v-for="(p, index) in pinnedPlugins"
                :key="p.name"
                cols="auto"
              >
                <PinnedPluginItem
                  :plugin="p"
                  :is-pinned="isPinned(p.name)"
                  :tm="tm"
                  :dragged="draggedIndex === index"
                  @toggle-pin="togglePin"
                  @view-readme="viewReadme"
                  @open-config="openExtensionConfig"
                  @reload="reloadPlugin"
                  @update="updateExtension"
                  @show-info="showPluginInfo"
                  @uninstall="uninstallExtension"
                  @dragstart="onDragStart(index)"
                  @dragover="onDragOver($event)"
                  @dragenter="onDragEnter($event, index)"
                  @dragend="onDragEnd($event)"
                  @drop="onDrop($event)"
                />
              </v-col>
            </transition-group>
          </v-row>
        </v-card-text>
      </v-card>
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
          <template #item.name="{ item }">
            <div class="d-flex">
              <div class="mr-3" style="flex-shrink: 0">
                <img
                  :src="
                    typeof item.logo === 'string' && item.logo.trim()
                      ? item.logo
                      : defaultPluginIcon
                  "
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
                <div class="text-h5" style="font-family: inherit">
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

                <div v-if="item.reserved" class="d-flex align-center mt-1">
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

            <!-- 置顶插件列表 -->
            <v-row v-if="pinnedPlugins.length > 0" class="mb-4">
              <v-col cols="12">
                <v-card class="rounded-lg overflow-hidden elevation-0" variant="flat">
                  <v-card-text class="pa-4">
                    <div class="d-flex align-center justify-space-between">
                      <h3 class="text-h6 mb-0">{{ tm('titles.pinnedPlugins') }}</h3>
                    </div>

                    <v-row class="mt-3 relative" dense align="center" style="gap:12px">
                      <transition-group name="list" class="v-row v-row--dense">
                        <v-col
                          cols="auto"
                          v-for="(p, index) in pinnedPlugins"
                          :key="p.name"
                        >
                          <PinnedPluginItem
                            :plugin="p"
                            :is-pinned="isPinned(p.name)"
                            :tm="tm"
                            :dragged="draggedIndex === index"
                            @toggle-pin="togglePin"
                            @view-readme="viewReadme"
                            @open-config="openExtensionConfig"
                            @reload="reloadPlugin"
                            @update="updateExtension"
                            @show-info="showPluginInfo"
                            @uninstall="uninstallExtension"
                            @dragstart="onDragStart(index)"
                            @dragover="onDragOver($event)"
                            @dragenter="onDragEnter($event, index)"
                            @dragend="onDragEnd($event)"
                            @drop="onDrop($event)"
                          />
                        </v-col>
                      </transition-group>
                    </v-row>
                  </v-card-text>
                </v-card>
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
                    <template v-slot:item.name="{ item }">
                      <div class="d-flex">
                        <div class="mr-3" style="flex-shrink: 0">
                          <img
                            :src="(typeof item.logo === 'string' && item.logo.trim()) ? item.logo : defaultPluginIcon"
                            :alt="item.name"
                            style="height: 40px; width: 40px; border-radius: 8px; object-fit: cover;"
                          />
                        </div>

                        <div>
                          <div class="text-h5" style="font-family: inherit;">
                            {{ item.display_name && item.display_name.length ? item.display_name : item.name }}
                          </div>

                          <div v-if="item.display_name && item.display_name.length" class="text-caption text-medium-emphasis mt-1">
                            {{ item.name }}
                          </div>

                          <div v-if="item.reserved" class="d-flex align-center mt-1">
                            <v-chip color="primary" size="x-small" class="font-weight-medium">{{ tm("status.system") }}</v-chip>
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
                      <a
                        v-if="getAuthorHomepageUrl(item.repo)"
                        :href="getAuthorHomepageUrl(item.repo)"
                        target="_blank"
                        @click.stop
                        class="text-body-2"
                        style="text-decoration: none; color: rgb(var(--v-theme-primary))"
                      >
                        {{ item.author }}
                      </a>
                      <div v-else class="text-body-2">{{ item.author }}</div>
                    </template>

                    <template v-slot:item.actions="{ item }">
                      <div class="table-action-row d-flex align-center flex-nowrap justify-start ga-2 py-1">
                        <v-btn
                          icon
                          size="small"
                          variant="tonal"
                          color="secondary"
                          class="table-action-btn pin-action"
                          @click.stop="togglePin(item)"
                          :title="isPinned(item.name) ? tm('buttons.unpin') : tm('buttons.pin')"
                        >
                          <v-icon size="18">{{ isPinned(item.name) ? 'mdi-pin' : 'mdi-pin-outline' }}</v-icon>
                        </v-btn>

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
                            prepend-icon="mdi-file-document-edit-outline"
                            @click="viewChangelog(item)"
                          >
                            <v-list-item-title>{{ tm("buttons.viewChangelog") }}</v-list-item-title>
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

          <template #item.version="{ item }">
            <div class="d-flex align-center">
              <span class="text-body-2">{{ item.version }}</span>
              <v-tooltip v-if="item.has_update" location="top">
                <template #activator="{ props: tooltipProps }">
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
                <template #activator="{ props: tooltipProps }">
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

          <template #item.author="{ item }">
            <div class="text-body-2">{{ item.author }}</div>
          </template>

          <template #item.actions="{ item }">
            <div
              class="table-action-row d-flex align-center flex-nowrap justify-start ga-2 py-1"
            >
              <v-btn
                icon
                size="small"
                variant="tonal"
                color="secondary"
                class="table-action-btn pin-action"
                :title="
                  isPinned(item.name) ? tm('buttons.unpin') : tm('buttons.pin')
                "
                @click.stop="togglePin(item)"
              >
                <v-icon size="18">{{
                  isPinned(item.name) ? "mdi-pin" : "mdi-pin-outline"
                }}</v-icon>
              </v-btn>

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
                  />
                </template>

                <v-list-item
                  class="styled-menu-item"
                  prepend-icon="mdi-information"
                  @click="showPluginInfo(item)"
                >
                  <v-list-item-title>{{
                    tm("buttons.viewInfo")
                  }}</v-list-item-title>
                </v-list-item>

                <v-list-item
                  class="styled-menu-item"
                  prepend-icon="mdi-update"
                  @click="updateExtension(item.name)"
                >
                  <v-list-item-title>{{
                    tm("buttons.update")
                  }}</v-list-item-title>
                </v-list-item>

                <v-list-item
                  class="styled-menu-item"
                  prepend-icon="mdi-delete"
                  :disabled="item.reserved"
                  @click="uninstallExtension(item.name)"
                >
                  <v-list-item-title>{{
                    tm("buttons.uninstall")
                  }}</v-list-item-title>
                </v-list-item>
              </StyledMenu>
            </div>
          </template>

          <template #no-data>
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
          v-for="extension in filteredPlugins"
          :key="extension.name"
          cols="12"
          md="6"
          lg="4"
          class="pb-2"
        >
          <ExtensionCard
            :extension="extension"
            :pinned="isPinned(extension.name)"
            class="rounded-lg"
            style="background-color: rgb(var(--v-theme-mcpCardBg))"
            @toggle-pin="() => togglePin(extension)"
            @configure="openExtensionConfig(extension.name)"
            @uninstall="(ext, options) => uninstallExtension(ext.name, options)"
            @update="updateExtension(extension.name)"
            @reload="reloadPlugin(extension.name)"
            @toggle-activation="
              extension.activated ? pluginOff(extension) : pluginOn(extension)
            "
            @view-handlers="showPluginInfo(extension)"
            @view-readme="viewReadme(extension)"
            @view-changelog="viewChangelog(extension)"
          />
        </v-col>
      </v-row>
    </div>
  </v-fade-transition>

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
</template>

<style scoped>
.repo-link {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
  word-break: break-all;
}

.repo-link:hover {
  text-decoration: underline;
}

.fab-button {
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.fab-button:hover {
  transform: translateY(-4px) scale(1.05);
  box-shadow: 0 12px 20px rgba(var(--v-theme-primary), 0.4);
}

.pinned-plugins h3 {
  font-weight: 600;
}

.pinned-list {
  gap: 12px;
}

.pinned-item {
  flex: 1 1 180px;
  max-width: 320px;
  height: 76px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.04);
  box-shadow: 0 1px 4px rgba(16, 24, 40, 0.04);
}

.pinned-avatar {
  display: inline-flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  cursor: pointer;
  border-radius: 12px;
}

.pinned-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.pinned-card-wrapper {
  position: relative;
  display: inline-block;
  width: 72px;
  height: 72px;
}

.pin-btn {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 5;
}

.pinned-item-skeleton {
  width: 72px;
  height: 72px;
  border-radius: 10px;
}

.pinned-item {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition:
    transform 0.2s ease,
    opacity 0.2s ease;
}

.is-dragging {
  opacity: 0.5;
  transform: scale(0.95);
  cursor: grabbing;
}

[draggable="true"] {
  cursor: grab;
}

[draggable="true"]:active {
  cursor: grabbing;
}

.list-move,
.list-enter-active,
.list-leave-active {
  transition: all 0.3s ease;
}

.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: scale(0.6);
}

.list-leave-active {
  position: absolute;
}
</style>
