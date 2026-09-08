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
        <span>{{ tm(section.value.name) }}</span>
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
              {{ sharedTm('pluginSetSelector.title') }}
            </h2>
            <p class="config-plugin-section__subtitle">
              {{ sharedTm('pluginSetSelector.subtitle') }}
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
              {{ tm(section.value.name) }}
            </h2>
          </header>

          <div class="config-standard-section__groups">
            <AstrBotConfigV4
              v-for="(sectionMetadata, metadataKey) in section.value.metadata"
              :key="metadataKey"
              :metadata="{ [metadataKey]: sectionMetadata }"
              :iterable="config_data"
              :metadata-key="metadataKey"
              :search-keyword="searchKeyword"
            />
          </div>
        </section>
      </template>

      <div v-if="visibleSections.length === 0" class="config-workspace__empty">
        <v-icon size="34">mdi-magnify-close</v-icon>
        <span>{{ tm('search.noResult') }}</span>
      </div>

      <footer v-if="visibleSections.length > 0" class="config-workspace__help">
        {{ tm('help.helpPrefix') }}
        <a href="https://docs.astrbot.app/" target="_blank" rel="noopener noreferrer">
          {{ tm('help.documentation') }}
        </a>
        {{ tm('help.helpMiddle') }}
        <a
          href="https://qm.qq.com/cgi-bin/qm/qr?k=EYGsuUTfe00_iOu9JTXS7_TEpMkXOvwv&jump_from=webapi&authKey=uUEMKCROfsseS+8IzqPjzV3y1tzy4AkykwTib2jNkOFdzezF9s9XknqnIaf3CDft"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ tm('help.support') }}
        </a>{{ tm('help.helpSuffix') }}
      </footer>
    </main>
  </div>
</template>

<script>
import AiConfigPanel from '@/components/config/AiConfigPanel.vue';
import AstrBotConfigV4 from '@/components/shared/AstrBotConfigV4.vue';
import PluginSetSelector from '@/components/shared/PluginSetSelector.vue';
import { useModuleI18n } from '@/i18n/composables';

const SECTION_ORDER = ['ai_group', 'plugin_group', 'platform_group', 'ext_group'];
const SECTION_ICONS = {
  ai_group: 'mdi-auto-fix',
  plugin_group: 'mdi-puzzle-outline',
  platform_group: 'mdi-robot-outline',
  ext_group: 'mdi-tune-variant'
};

export default {
  name: 'AstrBotCoreConfigWrapper',
  components: {
    AiConfigPanel,
    AstrBotConfigV4,
    PluginSetSelector
  },
  props: {
    metadata: {
      type: Object,
      required: true,
      default: () => ({})
    },
    config_data: {
      type: Object,
      required: true,
      default: () => ({})
    },
    readonly: {
      type: Boolean,
      default: false
    },
    searchKeyword: {
      type: String,
      default: ''
    }
  },
  setup() {
    const { tm: tmConfig } = useModuleI18n('features/config');
    const { tm: tmMetadata } = useModuleI18n('features/config-metadata');
    const { tm: sharedTm } = useModuleI18n('core/shared');

    const tm = (key) => {
      const metadataResult = tmMetadata(key);
      if (!metadataResult.startsWith('[MISSING:') && !metadataResult.startsWith('[INVALID:')) {
        return metadataResult;
      }
      return tmConfig(key);
    };

    return { tm, sharedTm };
  },
  data() {
    return {
      tab: null
    };
  },
  computed: {
    normalizedSearchKeyword() {
      return String(this.searchKeyword || '').trim().toLowerCase();
    },
    visibleSections() {
      if (!this.metadata || typeof this.metadata !== 'object') {
        return [];
      }
      const allSections = Object.entries(this.metadata)
        .map(([key, value]) => ({ key, value }))
        .sort((left, right) => {
          const leftIndex = SECTION_ORDER.indexOf(left.key);
          const rightIndex = SECTION_ORDER.indexOf(right.key);
          return (leftIndex === -1 ? SECTION_ORDER.length : leftIndex)
            - (rightIndex === -1 ? SECTION_ORDER.length : rightIndex);
        });
      if (!this.normalizedSearchKeyword) {
        return allSections;
      }
      return allSections.filter((section) => (
        (section.key === 'plugin_group' && this.tab === 'plugin_group')
        || this.sectionHasSearchMatch(section.value)
      ));
    }
  },
  watch: {
    visibleSections(newSections) {
      const sectionKeys = newSections.map((section) => section.key);
      if (!sectionKeys.includes(this.tab)) {
        this.tab = sectionKeys[0] ?? null;
      }
    }
  },
  mounted() {
    this.tab = this.visibleSections[0]?.key ?? null;
  },
  methods: {
    getSectionIcon(sectionKey) {
      return SECTION_ICONS[sectionKey] || 'mdi-cog-outline';
    },
    sectionHasSearchMatch(section) {
      const keyword = this.normalizedSearchKeyword;
      if (!keyword) {
        return true;
      }
      const sectionMetadata = section?.metadata || {};
      return Object.values(sectionMetadata).some((metaItem) => (
        this.metaObjectHasSearchMatch(metaItem, keyword)
      ));
    },
    metaObjectHasSearchMatch(metaObject, keyword) {
      if (!metaObject || typeof metaObject !== 'object') {
        return false;
      }
      const directText = [
        this.tm(metaObject.description || ''),
        this.tm(metaObject.hint || '')
      ].join(' ').toLowerCase();
      if (directText.includes(keyword)) {
        return true;
      }
      return Object.entries(metaObject.items || {}).some(([itemKey, itemMeta]) => (
        itemKey.toLowerCase().includes(keyword)
        || this.metaObjectHasSearchMatch(itemMeta, keyword)
      ));
    }
  }
};
</script>

<style scoped>
.config-workspace {
  --config-border: rgba(17, 24, 39, 0.13);
  --config-divider: rgba(17, 24, 39, 0.09);
  display: grid;
  grid-template-columns: 126px minmax(0, 1fr);
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
  content: '';
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

.config-plugin-section__subtitle {
  margin: 6px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-size: 0.8rem;
  line-height: 1.45;
}

.config-standard-section__groups,
:deep(.config-product-groups) {
  min-width: 0;
}

.config-standard-section__groups :deep(.v-card),
:deep(.config-product-groups .v-card) {
  margin-bottom: 28px !important;
  overflow: hidden !important;
  border: 1px solid var(--config-border) !important;
  border-radius: 10px !important;
  background: rgb(var(--v-theme-surface)) !important;
  box-shadow: none !important;
}

.config-standard-section__groups :deep(.config-section),
:deep(.config-product-groups .config-section) {
  padding: 16px 16px 8px !important;
}

.config-standard-section__groups :deep(.config-title),
:deep(.config-product-groups .config-title) {
  color: rgb(var(--v-theme-on-surface));
  font-size: 1.04rem;
  font-weight: 760;
  line-height: 1.32;
}

.config-standard-section__groups :deep(.config-hint),
:deep(.config-product-groups .config-hint) {
  margin-top: 5px;
  color: rgba(var(--v-theme-on-surface), 0.64) !important;
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: normal;
}

.config-standard-section__groups :deep(.config-row),
:deep(.config-product-groups .config-row) {
  min-height: 60px;
  padding: 12px 16px;
  border-radius: 0;
}

.config-standard-section__groups :deep(.config-row:hover),
:deep(.config-product-groups .config-row:hover) {
  background: transparent;
}

.config-standard-section__groups :deep(.property-info),
:deep(.config-product-groups .property-info) {
  padding: 0 16px 0 0;
}

.config-standard-section__groups :deep(.property-info .v-list-item),
:deep(.config-product-groups .property-info .v-list-item) {
  padding: 0;
}

.config-standard-section__groups :deep(.property-name),
:deep(.config-product-groups .property-name) {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.88rem;
  font-weight: 700;
  line-height: 1.4;
  white-space: normal;
}

.config-standard-section__groups :deep(.property-hint),
:deep(.config-product-groups .property-hint) {
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.7) !important;
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: normal;
}

.config-standard-section__groups :deep(.config-input),
:deep(.config-product-groups .config-input) {
  display: flex;
  justify-content: flex-end;
  min-width: 0;
  padding: 0;
}

.config-standard-section__groups :deep(.config-input > *),
:deep(.config-product-groups .config-input > *) {
  width: 100%;
  max-width: 270px;
}

.config-standard-section__groups :deep(.config-input .v-switch),
:deep(.config-product-groups .config-input .v-switch) {
  width: auto;
  max-width: none;
  margin-left: auto;
}

.config-standard-section__groups :deep(.config-input .v-switch .v-input__control),
:deep(.config-product-groups .config-input .v-switch .v-input__control) {
  margin-left: auto;
}

.config-standard-section__groups :deep(.config-input .v-switch .v-selection-control),
:deep(.config-product-groups .config-input .v-switch .v-selection-control) {
  justify-content: flex-end;
}

.config-standard-section__groups :deep(.v-field),
:deep(.config-product-groups .v-field) {
  border-radius: 10px;
  background: transparent;
}

.config-standard-section__groups :deep(.config-divider),
:deep(.config-product-groups .config-divider) {
  margin-left: 0;
  border-color: var(--config-divider);
}

.config-standard-section__groups :deep(.collapsed-config-toggle-row),
:deep(.config-product-groups .collapsed-config-toggle-row) {
  padding: 12px 16px 14px;
}

.config-standard-section__groups :deep(.collapsed-config-toggle),
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

  .config-standard-section__groups :deep(.config-row),
  :deep(.config-product-groups .config-row) {
    padding: 14px 16px;
  }

  .config-standard-section__groups :deep(.property-info),
  :deep(.config-product-groups .property-info) {
    padding-right: 0;
  }

  .config-standard-section__groups :deep(.config-input),
  :deep(.config-product-groups .config-input) {
    justify-content: stretch;
    padding-top: 10px;
  }

  .config-standard-section__groups :deep(.config-input > *),
  :deep(.config-product-groups .config-input > *) {
    max-width: none;
  }
}
</style>
