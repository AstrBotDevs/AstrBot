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
  tm,
  router,
  pluginSearch,
  filteredPlugins,
  openExtensionConfig,
  updateExtension,
  reloadPlugin,
  uninstallExtension,
  pluginOn,
  pluginOff,
  showPluginInfo,
  viewReadme,
  viewChangelog,
  openPluginSourceBindingDialog,
} = props.state;

// Open the plugin page inline within the current plugin pages tab. Used by
// both the card body and the webui button so they never leave this tab.
const openPluginPageInline = (extension) => {
  const pages = extension?.pages;
  if (!Array.isArray(pages) || pages.length === 0 || !extension?.name) return;
  if (!extension.activated) return;
  router.push({
    name: "ExtensionPluginPages",
    params: {
      pluginName: extension.name,
      pageName: pages[0],
    },
  });
};

// Left-click opens inline; middle-click (auxclick) or ctrl/cmd/shift+click
// opens the same plugin page in a new browser tab.
const openPluginPage = (extension, event) => {
  const pages = extension?.pages;
  if (!Array.isArray(pages) || pages.length === 0 || !extension?.name) return;
  if (!extension.activated) return;

  const openInNewTab =
    event.button === 1 || event.ctrlKey || event.metaKey || event.shiftKey;

  if (event.type === "auxclick" && !openInNewTab) {
    // Right-click (button === 2): leave the native context menu alone.
    return;
  }

  if (openInNewTab) {
    const url = router.resolve({
      name: "ExtensionPluginPages",
      params: {
        pluginName: extension.name,
        pageName: pages[0],
      },
    }).href;
    window.open(url, "_blank", "noopener");
    return;
  }

  openPluginPageInline(extension);
};

const pinnedExtensionNames = ref(readPinnedExtensions());

const pinnedExtensionOrder = computed(() => {
  const order = new Map();
  pinnedExtensionNames.value.forEach((name, index) => {
    order.set(name, index);
  });
  return order;
});

const sortedPagePlugins = computed(() => {
  const order = pinnedExtensionOrder.value;
  return filteredPlugins.value
    .filter((plugin) => Array.isArray(plugin?.pages) && plugin.pages.length > 0)
    .sort((a, b) => {
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
</script>

<template>
  <div>
    <div class="mb-4 pt-4 pb-4">
      <div class="installed-header-row d-flex align-center flex-wrap">
        <v-tabs
          model-value="pluginPages"
          bg-color="transparent"
          class="plugin-view-tabs"
          height="42"
        >
          <v-tab
            value="pluginPages"
            class="plugin-view-tab text-none"
            :ripple="false"
          >
            {{ tm("titles.pluginPages") }}
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
    </div>

    <v-fade-transition hide-on-leave>
      <div>
        <v-row v-if="sortedPagePlugins.length === 0" class="text-center">
          <v-col cols="12" class="pa-2">
            <v-icon size="64" color="info" class="mb-4"
              >mdi-monitor-dashboard</v-icon
            >
            <div class="text-h5 mb-2">{{ tm("empty.noPluginPages") }}</div>
            <div class="text-body-1 mb-4">
              {{ tm("empty.noPluginPagesDesc") }}
            </div>
          </v-col>
        </v-row>

        <v-row>
          <v-col
            cols="12"
            md="6"
            v-for="extension in sortedPagePlugins"
            :key="extension.name"
            class="pb-2"
          >
            <ExtensionCard
              :extension="extension"
              :is-pinned="isPinnedExtension(extension)"
              class="rounded-lg"
              style="background-color: rgb(var(--v-theme-mcpCardBg))"
              @click="openPluginPage(extension, $event)"
              @auxclick="openPluginPage(extension, $event)"
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
              @open-webui="openPluginPageInline(extension)"
              @change-source="openPluginSourceBindingDialog(extension)"
            >
            </ExtensionCard>
          </v-col>
        </v-row>
      </div>
    </v-fade-transition>
  </div>
</template>

<style scoped>
/* Mirrors the installed plugins tab: same heading style, same search
   alignment as the "已安装" view. */
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

@media (max-width: 700px) {
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
</style>
