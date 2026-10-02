<template>
  <div class="config-group-tabs">
    <v-tabs
      v-if="visibleTabs.length > 1 && !searchKeyword.trim()"
      v-model="activeTab"
      color="primary"
      density="compact"
      class="config-group-tabs__nav"
      :aria-label="label"
    >
      <v-tab v-for="item in visibleTabs" :key="item" :value="item">
        {{ tm(`hierarchy.tabs.${item}`) }}
      </v-tab>
    </v-tabs>

    <div class="config-product-groups" role="region" :aria-label="label">
      <AstrBotConfigV4
        v-for="(group, key) in displayedGroups"
        :key="key"
        :metadata="{ [key]: group }"
        :metadata-key="key"
        :iterable="configData"
        :search-keyword="searchKeyword"
        show-all-fields
      >
        <template #after-field="slotProps">
          <slot name="after-field" v-bind="slotProps" />
        </template>
      </AstrBotConfigV4>
    </div>
    <p
      v-if="showEmpty && !Object.keys(displayedGroups).length"
      class="config-group-tabs__empty"
      role="status"
    >
      {{ tm("search.noResult") }}
    </p>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import AstrBotConfigV4 from "@/components/shared/AstrBotConfigV4.vue";
import { useModuleI18n } from "@/i18n/composables";
import { getVisibleConfigGroups } from "@/utils/configHierarchy.mjs";

const props = defineProps({
  metadata: { type: Object, required: true },
  configData: { type: Object, required: true },
  tabs: { type: Array, default: () => [] },
  label: { type: String, default: "" },
  searchKeyword: { type: String, default: "" },
  showEmpty: { type: Boolean, default: true },
});
const { tm, getRaw } = useModuleI18n("features/config");
const { tm: metadataTm, getRaw: metadataRaw } = useModuleI18n(
  "features/config-metadata",
);
const translate = (value) =>
  getRaw(value) ? tm(value) : metadataRaw(value) ? metadataTm(value) : value;
const activeTab = ref(props.tabs[0] || null);
const visibleGroups = computed(() =>
  getVisibleConfigGroups(
    props.metadata,
    props.configData,
    props.searchKeyword,
    translate,
  ),
);
const visibleTabs = computed(() =>
  props.tabs.filter((tab) =>
    Object.values(visibleGroups.value).some((group) => group.tab === tab),
  ),
);
const displayedGroups = computed(() =>
  Object.fromEntries(
    Object.entries(visibleGroups.value).filter(
      ([, group]) =>
        props.searchKeyword.trim() ||
        !group.tab ||
        !visibleTabs.value.length ||
        group.tab === activeTab.value,
    ),
  ),
);
watch(
  visibleTabs,
  (tabs) => {
    if (!tabs.includes(activeTab.value)) activeTab.value = tabs[0] || null;
  },
  { immediate: true },
);
</script>

<style scoped>
.config-group-tabs__nav {
  margin-bottom: 18px;
}
.config-group-tabs__empty {
  padding: 24px 0;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
</style>
