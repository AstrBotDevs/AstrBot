<template>
  <div :class="mobile ? '' : 'd-flex'">
    <v-tabs
      v-model="tab"
      :direction="mobile ? 'horizontal' : 'vertical'"
      :align-tabs="'start'"
      color="secondary"
      class="config-tabs"
    >
      <v-tab
        v-for="section in visibleSections"
        :key="section.key"
        :value="section.key"
        class="config-tab"
      >
        {{ tm(section.value['name'] || section.key) }}
      </v-tab>
    </v-tabs>
    <v-tabs-window
      v-model="tab"
      class="config-tabs-window"
      :class="{ 'config-tabs-window--readonly': readonly }"
    >
      <v-tabs-window-item
        v-for="section in visibleSections"
        :key="section.key"
        :value="section.key"
      >
        <v-container fluid>
          <div
            v-for="(val2, key2) in section.value['metadata'] || {}"
            :key="key2"
          >
            <!-- Support both traditional and JSON selector metadata -->
            <AstrBotConfigV4
              :metadata="{ [key2]: (section.value['metadata'] || {})[key2] }"
              :iterable="normalizedConfigData"
              :metadata-key="key2"
              :search-keyword="searchKeyword"
            >
            </AstrBotConfigV4>
          </div>
        </v-container>
      </v-tabs-window-item>

      <div class="config-tabs-help">
        <small
          >{{ tm('help.helpPrefix') }}
          <a href="https://docs.astrbot.app/" target="_blank">{{
            tm('help.documentation')
          }}</a>
          {{ tm('help.helpMiddle') }}
          <a
            href="https://qm.qq.com/cgi-bin/qm/qr?k=EYGsuUTfe00_iOu9JTXS7_TEpMkXOvwv&jump_from=webapi&authKey=uUEMKCROfsseS+8IzqPjzV3y1tzy4AkykwTib2jNkOFdzezF9s9XknqnIaf3CDft"
            target="_blank"
            >{{ tm('help.support') }}</a
          >{{ tm('help.helpSuffix') }}
        </small>
      </div>
    </v-tabs-window>
  </div>
  <v-container v-if="visibleSections.length === 0" fluid class="px-0">
    <v-alert type="info" variant="tonal">
      {{ tm('search.noResult') }}
    </v-alert>
  </v-container>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useDisplay } from 'vuetify';
import AstrBotConfigV4 from '@/components/shared/AstrBotConfigV4.vue';
import { useModuleI18n } from '@/i18n/composables';

interface ConfigMetadataItem {
  description?: string;
  hint?: string;
  items?: Record<string, ConfigMetadataItem>;
}

interface ConfigSectionValue {
  name?: string;
  metadata?: Record<string, ConfigMetadataItem>;
}

interface ConfigSectionEntry {
  key: string;
  value: ConfigSectionValue;
}

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

const { tm: tmConfig } = useModuleI18n('features/config');
const { tm: tmMetadata } = useModuleI18n('features/config-metadata');
const { mobile } = useDisplay();

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
</script>

<style>
@media (min-width: 768px) {
  .config-tabs {
    display: flex;
    margin: 16px 16px 0 0;
  }

  .config-tabs-window {
    flex: 1;
  }

  .config-tab {
    justify-content: flex-start;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
  }
}

@media (max-width: 767px) {
  .config-tabs {
    width: 100%;
  }

  .config-tabs-window {
    margin-top: 16px;
  }
}

.config-tabs-help {
  margin-left: var(--astrbot-space-4);
  padding-bottom: var(--astrbot-space-4);
}

.config-tabs-window--readonly {
  pointer-events: none;
  opacity: 0.6;
}
</style>
