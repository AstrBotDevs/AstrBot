<template>
  <div class="config-workspace">
    <nav class="config-workspace__nav" :aria-label="tm('title')">
      <button
        v-for="section in visibleSections"
        :key="section.key"
        type="button"
        class="config-workspace__nav-item"
        :class="{ 'config-workspace__nav-item--active': tab === section.key }"
        :aria-pressed="tab === section.key"
        @click="tab = section.key"
      >
        <v-icon :icon="getSectionIcon(section.key)" size="16" />
        <span>{{ translate(section.value.name) }}</span>
      </button>
    </nav>

    <main
      class="config-workspace__main"
      :class="{ 'config-workspace__main--readonly': readonly }"
    >
      <template v-for="section in visibleSections" :key="section.key">
        <AiConfigPanel
          v-if="section.key === 'ai_group' && tab === section.key"
          :metadata="section.value.metadata"
          :config-data="config_data"
          :search-keyword="searchKeyword"
        />

        <section
          v-else-if="section.key === 'plugin_group' && tab === section.key"
          class="config-plugin-section"
        >
          <header class="config-standard-section__heading">
            <h2 class="config-standard-section__title">
              {{ sharedTm("pluginSetSelector.title") }}
            </h2>
            <p class="config-plugin-section__subtitle">
              {{ sharedTm("pluginSetSelector.subtitle") }}
            </p>
          </header>

          <PluginSetSelector
            v-model="config_data.plugin_set"
            :search-keyword="searchKeyword"
            inline
          />
        </section>

        <section
          v-else-if="tab === section.key"
          class="config-standard-section"
        >
          <header class="config-standard-section__heading">
            <h2 class="config-standard-section__title">
              {{ translate(section.value.name) }}
            </h2>
          </header>

          <p class="config-standard-section__subtitle">
            {{ tm(`hierarchy.descriptions.${section.key}`) }}
          </p>
          <ConfigGroupTabs
            :metadata="section.value.metadata"
            :config-data="config_data"
            :tabs="section.tabs"
            :label="translate(section.value.name)"
            :search-keyword="searchKeyword"
          />
        </section>
      </template>

      <div v-if="visibleSections.length === 0" class="config-workspace__empty">
        <v-icon size="34">mdi-magnify-close</v-icon>
        <span>{{ tm("search.noResult") }}</span>
      </div>

      <footer v-if="visibleSections.length > 0" class="config-workspace__help">
        {{ tm("help.helpPrefix") }}
        <a
          href="https://docs.astrbot.app/"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ tm("help.documentation") }}
        </a>
        {{ tm("help.helpMiddle") }}
        <a
          href="https://qm.qq.com/cgi-bin/qm/qr?k=EYGsuUTfe00_iOu9JTXS7_TEpMkXOvwv&jump_from=webapi&authKey=uUEMKCROfsseS+8IzqPjzV3y1tzy4AkykwTib2jNkOFdzezF9s9XknqnIaf3CDft"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ tm("help.support") }} </a
        >{{ tm("help.helpSuffix") }}
      </footer>
    </main>
  </div>
</template>

<script setup>
import { computed, provide, ref, shallowRef, watch } from "vue";
import AiConfigPanel from "@/components/config/AiConfigPanel.vue";
import ConfigGroupTabs from "@/components/config/ConfigGroupTabs.vue";
import PluginSetSelector from "@/components/shared/PluginSetSelector.vue";
import { useModuleI18n } from "@/i18n/composables";
import {
  buildConfigHierarchy,
  CONFIG_SECTIONS,
  getVisibleConfigGroups,
} from "@/utils/configHierarchy.mjs";

const props = defineProps({
  metadata: { type: Object, required: true },
  config_data: { type: Object, required: true },
  readonly: { type: Boolean, default: false },
  searchKeyword: { type: String, default: "" },
});
const { tm, getRaw } = useModuleI18n("features/config");
const { tm: metadataTm, getRaw: metadataRaw } = useModuleI18n(
  "features/config-metadata",
);
const { tm: sharedTm } = useModuleI18n("core/shared");
const translate = (value) =>
  getRaw(value) ? tm(value) : metadataRaw(value) ? metadataTm(value) : value;
const tab = ref(null);
// Keep model edits within this profile when filtering unmounts the editor.
provide("modelParameterEditorState", shallowRef(null));
const hierarchy = computed(() => buildConfigHierarchy(props.metadata));
const visibleSections = computed(() => {
  const order = Object.keys(CONFIG_SECTIONS);
  return Object.entries(hierarchy.value)
    .map(([key, value]) => ({
      key,
      value,
      tabs: CONFIG_SECTIONS[key]?.tabs || [],
    }))
    .sort(
      (left, right) =>
        (order.indexOf(left.key) === -1
          ? order.length
          : order.indexOf(left.key)) -
        (order.indexOf(right.key) === -1
          ? order.length
          : order.indexOf(right.key)),
    )
    .filter(
      (section) =>
        !props.searchKeyword.trim() ||
        (section.key === "plugin_group" && tab.value === "plugin_group") ||
        Object.keys(
          getVisibleConfigGroups(
            section.value.metadata,
            props.config_data,
            props.searchKeyword,
            translate,
          ),
        ).length,
    );
});
watch(
  visibleSections,
  (sections) => {
    if (!sections.some((section) => section.key === tab.value))
      tab.value = sections[0]?.key || null;
  },
  { immediate: true },
);
const getSectionIcon = (key) => CONFIG_SECTIONS[key]?.icon || "mdi-cog-outline";
</script>

<style scoped>
.config-workspace {
  --config-border: rgba(17, 24, 39, 0.13);
  --config-divider: rgba(17, 24, 39, 0.09);
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 34px;
  align-items: start;
  min-width: 0;
}

.config-workspace__nav {
  position: sticky;
  top: calc(var(--v-layout-top, 64px) + 52px);
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-top: 2px;
}

.config-workspace__nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 34px;
  padding: 6px 9px 6px 12px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.64);
  cursor: pointer;
  font: inherit;
  font-size: 0.84rem;
  font-weight: 680;
  line-height: 1.25;
  text-align: left;
}

.config-workspace__nav-item:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
  color: rgb(var(--v-theme-on-surface));
}

.config-workspace__nav-item--active {
  background: rgba(var(--v-theme-on-surface), 0.07);
  color: rgb(var(--v-theme-on-surface));
  font-weight: 760;
}

.config-workspace__nav-item--active::before {
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: 0;
  width: 2px;
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.52);
  content: "";
}

.config-workspace__main {
  width: 100%;
  max-width: 680px;
  min-width: 0;
}

.config-workspace__main--readonly {
  pointer-events: none;
  opacity: 0.6;
}

.config-standard-section__heading {
  margin-bottom: 22px;
}

.config-standard-section__title {
  margin: 0;
  color: rgb(var(--v-theme-on-surface));
  font-size: 1.34rem;
  font-weight: 780;
  letter-spacing: 0;
  line-height: 1.25;
}

.config-plugin-section__subtitle,
.config-standard-section__subtitle {
  margin: 6px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 0.8rem;
  line-height: 1.45;
}

:deep(.config-product-groups) {
  min-width: 0;
}

:deep(.config-product-groups .v-card) {
  margin-bottom: 28px !important;
  overflow: hidden !important;
  border: 1px solid var(--config-border) !important;
  border-radius: 10px !important;
  background: rgb(var(--v-theme-surface)) !important;
  box-shadow: none !important;
}

:deep(.config-product-groups .config-section) {
  padding: 16px 16px 8px !important;
}

:deep(.config-product-groups .config-title) {
  color: rgb(var(--v-theme-on-surface));
  font-size: 1.04rem;
  font-weight: 760;
  line-height: 1.32;
}

:deep(.config-product-groups .config-hint) {
  margin-top: 5px;
  color: rgba(var(--v-theme-on-surface), 0.64) !important;
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: normal;
}

:deep(.config-product-groups .config-row) {
  min-height: 60px;
  padding: 12px 16px;
  border-radius: 0;
}

:deep(.config-product-groups .config-row:hover) {
  background: transparent;
}

:deep(.config-product-groups .property-info) {
  padding: 0 16px 0 0;
}

:deep(.config-product-groups .property-info .v-list-item) {
  padding: 0;
}

:deep(.config-product-groups .property-name) {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.88rem;
  font-weight: 700;
  line-height: 1.4;
  white-space: normal;
}

:deep(.config-product-groups .property-hint) {
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.7) !important;
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: normal;
}

:deep(.config-product-groups .config-input) {
  display: flex;
  justify-content: flex-end;
  min-width: 0;
  padding: 0;
}

:deep(.config-product-groups .config-input > :not(.config-field--full-width)) {
  width: 100%;
  max-width: 270px;
}

:deep(.config-product-groups .config-input .v-switch) {
  width: auto;
  max-width: none;
  margin-left: auto;
}

:deep(.config-product-groups .config-input .v-switch .v-input__control) {
  margin-left: auto;
}

:deep(.config-product-groups .config-input .v-switch .v-selection-control) {
  justify-content: flex-end;
}

:deep(.config-product-groups .v-field) {
  border-radius: 10px;
  background: transparent;
}

:deep(.config-product-groups .config-divider) {
  margin-left: 0;
  border-color: var(--config-divider);
}

:deep(.config-product-groups .collapsed-config-toggle-row) {
  padding: 12px 16px 14px;
}

:deep(.config-product-groups .collapsed-config-toggle) {
  margin-left: 0;
}

.config-workspace__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 64px 24px;
  color: rgba(var(--v-theme-on-surface), 0.54);
  font-size: 0.84rem;
}

.config-workspace__help {
  margin-top: 8px;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 0.76rem;
  line-height: 1.5;
}

.config-workspace__help a {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}

@media (max-width: 720px) {
  .config-workspace {
    grid-template-columns: 1fr;
    gap: 22px;
  }

  .config-workspace__nav {
    position: static;
    flex-direction: row;
    gap: 6px;
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .config-workspace__main {
    max-width: none;
  }

  .config-workspace__nav-item {
    flex: 0 0 auto;
    width: auto;
    border: 1px solid var(--config-border);
    background: rgb(var(--v-theme-surface));
  }

  :deep(.config-product-groups .config-row) {
    padding: 14px 16px;
  }

  :deep(.config-product-groups .property-info) {
    padding-right: 0;
  }

  :deep(.config-product-groups .config-input) {
    justify-content: stretch;
    padding-top: 10px;
  }

  :deep(.config-product-groups .config-input > *) {
    max-width: none;
  }
}
</style>
