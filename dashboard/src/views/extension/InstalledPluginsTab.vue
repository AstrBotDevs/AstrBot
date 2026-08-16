<script setup>
import ExtensionCard from '@/components/shared/ExtensionCard.vue';
import FloatingActionStack from '@/components/ui/FloatingActionStack.vue';
import { normalizeTextInput } from '@/utils/inputValue';
import {
  readPinnedExtensions,
  writePinnedExtensions,
} from './extensionPreferenceStorage';
import { computed, ref, watch } from 'vue';

const props = defineProps({
  state: {
    type: Object,
    required: true,
  },
});

const {
  tm,
  router,
  activeTab,
  updatingAll,
  pluginSearch,
  filteredPlugins,
  failedPluginItems,
  reloadFailedPlugin,
  uninstallExtension,
  requestUninstallFailedPlugin,
  updateExtension,
  showUpdateAllConfirm,
  pluginOn,
  pluginOff,
  openExtensionConfig,
  showPluginInfo,
  reloadPlugin,
  viewReadme,
  viewChangelog,
  openInstallDialog,
} = props.state;

const openPluginDetail = (extension) => {
  if (!extension?.name) return;
  router.push({
    name: 'ExtensionDetails',
    params: { pluginId: extension.name },
    hash: '#installed',
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
  return Boolean(name) && pinnedExtensionOrder.value.has(name);
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
  <div v-show="activeTab === 'installed'">
    <div class="page-header">
      <h2 class="page-header__title">
        {{ tm('titles.installedAstrBotPlugins') }}
      </h2>

      <div class="inline-control-row">
        <v-text-field
          :model-value="pluginSearch"
          density="compact"
          :label="tm('search.placeholder')"
          prepend-inner-icon="mdi-magnify"
          clearable
          variant="solo-filled"
          flat
          hide-details
          single-line
          class="control-search"
          @update:model-value="pluginSearch = normalizeTextInput($event)"
        >
        </v-text-field>
      </div>
    </div>

    <v-card
      v-if="failedPluginItems.length > 0"
      class="mb-4"
      variant="tonal"
      color="warning"
    >
      <v-card-title class="d-flex align-center">
        <v-icon color="warning" class="mr-2">mdi-alert-circle</v-icon>
        {{ tm('failedPlugins.title', { count: failedPluginItems.length }) }}
      </v-card-title>
      <v-card-text class="pt-0">
        <div class="text-body-2 mb-3">
          {{ tm('failedPlugins.hint') }}
        </div>
        <v-table density="compact">
          <thead>
            <tr>
              <th>{{ tm('failedPlugins.columns.plugin') }}</th>
              <th>{{ tm('failedPlugins.columns.error') }}</th>
              <th class="text-right">{{ tm('buttons.actions') }}</th>
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
              <td class="failed-plugin-error-cell">
                <div
                  class="text-caption text-medium-emphasis truncate-two-lines"
                >
                  {{ plugin.error || tm('status.unknown') }}
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
                  {{ tm('buttons.reload') }}
                </v-btn>
                <v-btn
                  size="small"
                  variant="tonal"
                  color="error"
                  prepend-icon="mdi-delete"
                  :disabled="plugin.reserved"
                  @click="requestUninstallFailedPlugin(plugin.dir_name)"
                >
                  {{ tm('buttons.uninstall') }}
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
            <div class="text-h5 mb-2">{{ tm('empty.noPlugins') }}</div>
            <div class="text-body-1 mb-4">
              {{ tm('empty.noPluginsDesc') }}
            </div>
          </v-col>
        </v-row>

        <v-row>
          <v-col
            v-for="extension in sortedInstalledPlugins"
            :key="extension.name"
            cols="12"
            md="6"
            class="pb-2"
          >
            <ExtensionCard
              :extension="extension"
              :is-pinned="isPinnedExtension(extension)"
              class="surface--extension"
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

    <FloatingActionStack :label="tm('buttons.actions')">
      <v-tooltip :text="tm('market.installPlugin')" location="left">
        <template #activator="{ props: installTooltipProps }">
          <v-btn
            v-bind="installTooltipProps"
            :aria-label="tm('market.installPlugin')"
            color="primary"
            icon="mdi-plus"
            variant="elevated"
            @click="openInstallDialog"
          />
        </template>
      </v-tooltip>

      <v-tooltip :text="tm('buttons.updateAll')" location="left">
        <template #activator="{ props: updateTooltipProps }">
          <v-btn
            v-bind="updateTooltipProps"
            :aria-label="tm('buttons.updateAll')"
            color="secondary"
            icon="mdi-update"
            variant="elevated"
            :loading="updatingAll"
            @click="showUpdateAllConfirm"
          />
        </template>
      </v-tooltip>
    </FloatingActionStack>
  </div>
</template>

<style scoped>
.failed-plugin-error-cell {
  max-width: 520px;
}
</style>
