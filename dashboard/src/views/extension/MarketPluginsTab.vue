<script setup>
import MarketPluginCard from '@/components/extension/MarketPluginCard.vue';
import FloatingActionStack from '@/components/ui/FloatingActionStack.vue';
import PluginSortControl from '@/components/extension/PluginSortControl.vue';
import defaultPluginIcon from '/favicon.svg';
import { computed } from 'vue';
import { normalizeTextInput } from '@/utils/inputValue';

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
  pluginMarketData,
  loading_,
  currentPage,
  customSources,
  selectedSource,
  showPluginFullName,
  marketSearch,
  refreshingMarket,
  sortBy,
  sortOrder,
  marketCategoryFilter,
  marketCategoryItems,
  randomPlugins,
  refreshRandomPlugins,
  totalPages,
  paginatedPlugins,
  openInstallDialog,
  handleInstallPlugin,
  openSourceManagerDialog,
  refreshPluginMarket,
} = props.state;

const currentSourceName = computed(() => {
  if (!selectedSource.value) {
    return tm('market.defaultSource');
  }
  const matched = customSources.value.find(
    (s) => s.url === selectedSource.value,
  );
  return matched?.name || tm('market.defaultSource');
});

const marketSortItems = computed(() => [
  { title: tm('sort.default'), value: 'default' },
  { title: tm('sort.stars'), value: 'stars' },
  { title: tm('sort.downloads'), value: 'downloads' },
  { title: tm('sort.author'), value: 'author' },
  { title: tm('sort.updated'), value: 'updated' },
]);

const marketCategorySelectItems = computed(() =>
  marketCategoryItems.value.map((item) => ({
    title: `${item.label || ''} (${item.count || 0})`,
    value: item.value,
  })),
);

const openMarketPluginDetail = (plugin) => {
  if (!plugin?.name) return;
  router.push({
    name: 'ExtensionDetails',
    params: { pluginId: plugin.name },
    hash: '#market',
  });
};
</script>

<template>
  <div v-show="activeTab === 'market'">
    <div class="market-page-header page-header">
      <div class="market-page-header__title-row">
        <h2 class="page-header__title">{{ tm('tabs.market') }}</h2>

        <v-tooltip location="top" :text="tm('market.sourceManagement')">
          <template #activator="{ props: activatorProps }">
            <v-btn
              v-bind="activatorProps"
              variant="tonal"
              rounded="md"
              color="primary"
              class="market-source-button"
              @click="openSourceManagerDialog"
            >
              <v-icon size="18" class="mr-1">mdi-source-branch</v-icon>
              <span class="market-source-name text-truncate">
                {{ currentSourceName }}
              </span>
            </v-btn>
          </template>
        </v-tooltip>
      </div>

      <v-text-field
        :model-value="marketSearch"
        class="market-search control-search"
        density="compact"
        :label="tm('search.marketPlaceholder')"
        prepend-inner-icon="mdi-magnify"
        clearable
        variant="solo-filled"
        flat
        hide-details
        single-line
        @update:model-value="marketSearch = normalizeTextInput($event)"
      >
      </v-text-field>

      <div class="market-safety-note">
        <v-icon size="16" class="mr-1">mdi-alert-outline</v-icon>
        <span>{{ tm('market.sourceSafetyWarning') }}</span>
      </div>
    </div>

    <div class="mt-4">
      <div class="market-section-header">
        <div class="inline-control-row">
          <h2 class="page-section-title">
            {{ tm('market.allPlugins') }}
          </h2>
          <v-tooltip :text="tm('buttons.refresh')">
            <template #activator="{ props: refreshTooltipProps }">
              <v-btn
                v-bind="refreshTooltipProps"
                :aria-label="tm('buttons.refresh')"
                icon="mdi-refresh"
                variant="text"
                :loading="loading_ || refreshingMarket"
                :disabled="loading_ || refreshingMarket"
                @click="refreshPluginMarket"
              />
            </template>
          </v-tooltip>
        </div>

        <div class="inline-control-row">
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
          ></v-select>

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

      <v-row class="market-plugin-grid" density="comfortable">
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
            @open="openMarketPluginDetail"
          />
        </v-col>
      </v-row>

      <div v-if="totalPages > 1" class="d-flex justify-center mt-4">
        <v-pagination
          v-model="currentPage"
          :length="totalPages"
          :total-visible="7"
          size="small"
        ></v-pagination>
      </div>

      <v-expand-transition>
        <div v-if="randomPlugins.length > 0">
          <div class="market-section-header mt-4 mb-2">
            <h2 class="page-section-title">
              {{ tm('market.randomPlugins') }}
            </h2>
            <v-btn
              color="primary"
              variant="tonal"
              prepend-icon="mdi-shuffle-variant"
              :disabled="pluginMarketData.length === 0"
              @click="refreshRandomPlugins"
            >
              {{ tm('buttons.reshuffle') }}
            </v-btn>
          </div>

          <v-row class="mb-6" density="comfortable">
            <v-col
              v-for="plugin in randomPlugins"
              :key="`random-${plugin.name}`"
              cols="12"
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

    <FloatingActionStack :label="tm('market.installPlugin')">
      <v-tooltip :text="tm('market.installPlugin')" location="left">
        <template #activator="{ props: tooltipProps }">
          <v-btn
            v-bind="tooltipProps"
            :aria-label="tm('market.installPlugin')"
            color="primary"
            icon="mdi-plus"
            variant="elevated"
            @click="openInstallDialog"
          />
        </template>
      </v-tooltip>
    </FloatingActionStack>
  </div>
</template>

<style scoped>
.market-page-header {
  align-items: flex-start;
}

.market-page-header__title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.market-source-button {
  max-width: 260px;
}

.market-source-name {
  max-width: 180px;
}

.market-safety-note {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 13px;
  line-height: 18px;
}

.market-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.market-plugin-grid {
  min-height: 416px;
}

.market-filter-control {
  min-width: 190px;
  max-width: 220px;
}

.market-filter-control :deep(.v-field__input),
.market-filter-control :deep(.v-field-label),
.market-filter-control :deep(.v-select__selection-text),
.market-filter-control :deep(.v-field__prepend-inner) {
  font-size: 0.875rem;
}

@media (max-width: 600px) {
  .market-page-header__title-row {
    width: 100%;
  }

  .market-search {
    width: 100%;
  }
}
</style>
