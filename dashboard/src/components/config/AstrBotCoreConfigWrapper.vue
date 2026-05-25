<template>
    <div :class="$vuetify.display.mobile ? '' : 'd-flex'">
        <v-tabs v-model="tab" :direction="$vuetify.display.mobile ? 'horizontal' : 'vertical'"
            :align-tabs="$vuetify.display.mobile ? 'left' : 'start'" color="deep-purple-accent-4" class="config-tabs">
            <v-tab v-for="section in visibleSections" :key="section.key" :value="section.key"
                style="font-weight: 1000; font-size: 15px">
                {{ tm(section.value['name']) }}
            </v-tab>
        </v-tabs>
        <v-tabs-window v-model="tab" class="config-tabs-window" :style="readonly ? 'pointer-events: none; opacity: 0.6;' : ''">
            <v-tabs-window-item v-for="section in visibleSections" :key="section.key" :value="section.key">
                <v-container fluid>
                    <div v-for="(val2, key2, index2) in section.value['metadata']" :key="key2">
                        <!-- Support both traditional and JSON selector metadata -->
                        <AstrBotConfigV4
                            :metadata="{ [key2]: section.value['metadata'][key2] }"
                            :iterable="config_data"
                            :metadataKey="key2"
                            :search-keyword="searchKeyword"
                        >
                        </AstrBotConfigV4>
                    </div>
                </v-container>
            </v-tabs-window-item>


            <div style="margin-left: 16px; padding-bottom: 16px">
                <small>{{ tm('help.helpPrefix') }}
                    <a href="https://astrbot.app/" target="_blank">{{ tm('help.documentation') }}</a>
                    {{ tm('help.helpMiddle') }}
                    <a href="https://qm.qq.com/cgi-bin/qm/qr?k=EYGsuUTfe00_iOu9JTXS7_TEpMkXOvwv&jump_from=webapi&authKey=uUEMKCROfsseS+8IzqPjzV3y1tzy4AkykwTib2jNkOFdzezF9s9XknqnIaf3CDft"
                        target="_blank">{{ tm('help.support') }}</a>{{ tm('help.helpSuffix') }}
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

<script>
import AstrBotConfigV4 from '@/components/shared/AstrBotConfigV4.vue';
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'AstrBotCoreConfigWrapper',
  components: {
    AstrBotConfigV4
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
    
    const tm = (key) => {
      const metadataResult = tmMetadata(key);
      if (!metadataResult.startsWith('[MISSING:') && !metadataResult.startsWith('[INVALID:')) {
        return metadataResult;
      }
      return tmConfig(key);
    };
    
    return {
      tm
    };
  },
  data() {
    return {
      tab: null, // 当前激活的配置标签页 key
    }
  },
  computed: {
    normalizedSearchKeyword() {
      return String(this.searchKeyword || '').trim().toLowerCase();
    },
    visibleSections() {
      if (!this.metadata || typeof this.metadata !== 'object') {
        return [];
      }
      const allSections = Object.entries(this.metadata).map(([key, value]) => ({ key, value }));
      if (!this.normalizedSearchKeyword) {
        return allSections;
      }
      return allSections.filter((section) => this.sectionHasSearchMatch(section.value));
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
    const sectionKeys = this.visibleSections.map((section) => section.key);
    this.tab = sectionKeys[0] ?? null;
  },
  methods: {
    sectionHasSearchMatch(section) {
      const keyword = this.normalizedSearchKeyword;
      if (!keyword) {
        return true;
      }
      const sectionMetadata = section?.metadata || {};
      return Object.values(sectionMetadata).some((metaItem) => this.metaObjectHasSearchMatch(metaItem, keyword));
    },
    metaObjectHasSearchMatch(metaObject, keyword) {
      if (!metaObject || typeof metaObject !== 'object') {
        return false;
      }
      const target = [
        this.tm(metaObject.description || ''),
        this.tm(metaObject.hint || ''),
        ...Object.entries(metaObject.items || {}).flatMap(([itemKey, itemMeta]) => ([
          itemKey,
          this.tm(itemMeta?.description || ''),
          this.tm(itemMeta?.hint || '')
        ]))
      ]
        .join(' ')
        .toLowerCase();

      return target.includes(keyword);
    }
  }
}
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

  .config-tabs .v-tab {
    justify-content: flex-start !important;
    text-align: left;
    min-height: 48px;
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
</style>
