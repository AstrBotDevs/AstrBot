<template>
    <div :class="$vuetify.display.mobile ? '' : 'd-flex'">
        <v-tabs v-model="tab" :direction="$vuetify.display.mobile ? 'horizontal' : 'vertical'"
            :align-tabs="$vuetify.display.mobile ? 'left' : 'start'" color="deep-purple-accent-4" class="config-tabs">
            <v-tab v-for="(val, key, index) in metadata" :key="index" :value="index"
                style="font-weight: 1000; font-size: 15px">
                {{ metadata[key]['name'] }}
            </v-tab>
        </v-tabs>
        <v-tabs-window v-model="tab" class="config-tabs-window" :style="readonly ? 'pointer-events: none; opacity: 0.6;' : ''">
            <v-tabs-window-item v-for="(val, key, index) in metadata" v-show="index == tab" :key="index">
                <v-container fluid>
                    <div v-for="(val2, key2, index2) in metadata[key]['metadata']" :key="key2">
                        <!-- Support both traditional and JSON selector metadata -->
                        <AstrBotConfigV4 :metadata="{ [key2]: metadata[key]['metadata'][key2] }" :iterable="config_data"
                            :metadataKey="key2">
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
    }
  },
  setup() {
    const { tm } = useModuleI18n('features/config');
    return {
      tm
    };
  },
  data() {
    return {
      tab: 0, // 用于切换配置标签页
    }
  },
  methods: {
    // 如果需要添加其他方法，可以在这里添加
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