<template>
  <div class="config-workspace">
    <nav class="config-workspace__nav" :aria-label="tm('title')">
      <button
        v-for="section in visibleSections"
        :key="section.key"
        type="button"
        class="config-tab config-workspace__nav-item"
        :class="{ 'config-workspace__nav-item--active': tab === section.key }"
        :aria-pressed="tab === section.key"
        @click="tab = section.key"
      >
        <v-icon :icon="getSectionIcon(section.key)" size="16" />
        <span>{{ tm(section.value.name || section.key) }}</span>
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
          :config-data="normalizedConfigData"
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
            v-model="pluginSet"
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
              {{ tm(section.value.name || section.key) }}
            </h2>
          </header>

          <div class="config-standard-section__groups">
            <AstrBotConfigV4
              v-for="(sectionMetadata, metadataKey) in section.value.metadata"
              :key="String(metadataKey)"
              :metadata="{ [metadataKey]: sectionMetadata }"
              :iterable="normalizedConfigData"
              :metadata-key="String(metadataKey)"
              :search-keyword="searchKeyword"
            />
          </div>
        </section>
      </template>

      <div v-if="visibleSections.length === 0" class="config-workspace__empty">
        <v-icon size="34">mdi-magnify-close</v-icon>
        <span>{{ tm('search.noResult') }}</span>
      </div>

      <div v-if="currentTabDocsHref" class="config-tabs-help">
        <small>
          {{ tm('help.helpPrefix') }}
          <a
            :href="currentTabDocsHref"
            target="_blank"
            rel="noopener noreferrer"
            >{{ tm('help.documentation') }}</a
          >{{ tm('help.helpSuffix') }}
        </small>
      </div>
    </main>
  </div>
  <v-container v-if="visibleSections.length === 0" fluid class="px-0">
    <v-alert type="info" variant="tonal">
      {{ tm('search.noResult') }}
    </v-alert>
  </v-container>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import AiConfigPanel from '@/components/config/AiConfigPanel.vue';
import AstrBotConfigV4 from '@/components/shared/AstrBotConfigV4.vue';
import PluginSetSelector from '@/components/shared/PluginSetSelector.vue';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { configDocsHref } from '@/utils/docsHref';

interface ConfigMetadataItem {
  description?: string;
  hint?: string;
  docs?: string;
  items?: Record<string, ConfigMetadataItem>;
}

interface ConfigSectionValue {
  name?: string;
  docs?: string;
  metadata?: Record<string, ConfigMetadataItem>;
}

interface ConfigSectionEntry {
  key: string;
  value: ConfigSectionValue;
}

const SECTION_ICONS: Record<string, string> = {
  ai_group: 'mdi-auto-fix',
  plugin_group: 'mdi-puzzle-outline',
  platform_group: 'mdi-robot-outline',
  ext_group: 'mdi-tune-variant',
};

const props = withDefaults(
  defineProps<{
    metadata?: unknown;
    configData?: unknown;
    readonly?: boolean;
    searchKeyword?: string;
  }>(),
  {
    metadata: () => ({}),
    configData: () => ({}),
    readonly: false,
    searchKeyword: '',
  },
);

const { locale } = useI18n();
const { tm: tmConfig } = useModuleI18n('features/config');
const { tm: tmMetadata } = useModuleI18n('features/config-metadata');
const { tm: sharedTm } = useModuleI18n('core/shared');

const tab = ref<string | null>(null);

const tm = (key: string) => {
  const metadataResult = tmMetadata(key);
  if (
    !metadataResult.startsWith('[MISSING:') &&
    !metadataResult.startsWith('[INVALID:')
  ) {
    return metadataResult;
  }
  return tmConfig(key);
};

const normalizedMetadata = computed<Record<string, ConfigSectionValue>>(() => {
  if (!props.metadata || typeof props.metadata !== 'object') {
    return {};
  }
  return props.metadata as Record<string, ConfigSectionValue>;
});

const normalizedConfigData = computed<Record<string, unknown>>(() => {
  if (!props.configData || typeof props.configData !== 'object') {
    return {};
  }
  return props.configData as Record<string, unknown>;
});

const pluginSet = computed<string[]>({
  get() {
    const value = normalizedConfigData.value.plugin_set;
    return Array.isArray(value) ? value.map(String) : [];
  },
  set(value) {
    normalizedConfigData.value.plugin_set = value;
  },
});

const normalizedSearchKeyword = computed(() =>
  String(props.searchKeyword || '')
    .trim()
    .toLowerCase(),
);

function metaObjectHasSearchMatch(
  metaObject: ConfigMetadataItem | undefined,
  keyword: string,
) {
  if (!metaObject || typeof metaObject !== 'object') {
    return false;
  }
  const target = [
    tm(metaObject.description || ''),
    tm(metaObject.hint || ''),
    ...Object.entries(metaObject.items || {}).flatMap(([itemKey, itemMeta]) => [
      itemKey,
      tm(itemMeta.description || ''),
      tm(itemMeta.hint || ''),
    ]),
  ]
    .join(' ')
    .toLowerCase();

  return target.includes(keyword);
}

function sectionHasSearchMatch(section: ConfigSectionValue) {
  const keyword = normalizedSearchKeyword.value;
  if (!keyword) {
    return true;
  }
  const sectionMetadata = section.metadata || {};
  return Object.values(sectionMetadata).some((metaItem) =>
    metaObjectHasSearchMatch(metaItem, keyword),
  );
}

const visibleSections = computed<ConfigSectionEntry[]>(() => {
  const allSections = Object.entries(normalizedMetadata.value).map(
    ([key, value]) => ({
      key,
      value,
    }),
  );
  if (!normalizedSearchKeyword.value) {
    return allSections;
  }
  return allSections.filter((section) => sectionHasSearchMatch(section.value));
});

watch(
  visibleSections,
  (newSections) => {
    const sectionKeys = newSections.map((section) => section.key);
    if (!sectionKeys.includes(tab.value || '')) {
      tab.value = sectionKeys[0] ?? null;
    }
  },
  { immediate: true },
);

const currentTabDocsHref = computed(() => {
  const current = visibleSections.value.find(
    (section) => section.key === tab.value,
  );
  return configDocsHref(current?.value.docs, locale.value);
});

function getSectionIcon(sectionKey: string) {
  return SECTION_ICONS[sectionKey] || 'mdi-cog-outline';
}
</script>

<style>
.config-workspace {
  display: flex;
  gap: 20px;
  min-width: 0;
}

.config-workspace__nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 168px;
}

.config-workspace__nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: rgb(var(--v-theme-on-surface));
  font-size: 14px;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}

.config-workspace__nav-item--active {
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
}

.config-workspace__main {
  flex: 1;
  min-width: 0;
}

.config-workspace__main--readonly {
  pointer-events: none;
  opacity: 0.6;
}

.config-workspace__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 48px 16px;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.config-standard-section__heading,
.config-plugin-section .config-standard-section__heading {
  margin-bottom: 16px;
}

.config-standard-section__title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}

.config-plugin-section__subtitle {
  margin: 6px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.config-standard-section__groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.config-tabs-help {
  margin-top: var(--astrbot-space-4);
  padding-bottom: var(--astrbot-space-4);
  pointer-events: auto;
}

@media (max-width: 767px) {
  .config-workspace {
    flex-direction: column;
  }

  .config-workspace__nav {
    flex-direction: row;
    flex-wrap: wrap;
    min-width: 0;
  }

  .config-workspace__nav-item {
    width: auto;
  }
}
</style>
