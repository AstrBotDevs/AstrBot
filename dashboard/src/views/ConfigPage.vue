<template>
  <div>
    <v-row>
      <v-col v-for="configInfo in configInfoList" :key="configInfo.id" cols="12" md="6" lg="4" xl="3">
        <v-card class="config-info-card" elevation="2" rounded="lg"
          @click="selectedConfigInfo = configInfo; getConfig(configInfo.id);">
          <v-card-title class="d-flex justify-space-between align-center">
            <div class="text-truncate ml-2">
              {{ configInfo.name }}
            </div>
          </v-card-title>

          <v-card-text>
            <div class="system-prompt-preview">
              {{ configInfo.umop }}
            </div>

            <div class="mt-3 text-caption text-medium-emphasis">
              {{ configInfo.path }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>

  <div v-if="selectedConfigInfo" class="mt-4" style="display: flex; flex-direction: column; align-items: center;">

    <!-- 可视化编辑 -->
    <div class="config-panel" :class="$vuetify.display.mobile ? '' : 'd-flex'">
      <v-tabs 
        v-model="tab" 
        :direction="$vuetify.display.mobile ? 'horizontal' : 'vertical'"
        :align-tabs="$vuetify.display.mobile ? 'left' : 'start'"
        color="deep-purple-accent-4"
        class="config-tabs"
      >
        <v-tab v-for="(val, key, index) in metadata" :key="index" :value="index"
          style="font-weight: 1000; font-size: 15px">
          {{ metadata[key]['name'] }}
        </v-tab>
      </v-tabs>
      <v-tabs-window v-model="tab" class="config-tabs-window">
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

    <v-btn icon="mdi-content-save" size="x-large" style="position: fixed; right: 52px; bottom: 52px;"
      color="darkprimary" @click="updateConfig">
    </v-btn>

    <v-btn icon="mdi-code-json" size="x-large" style="position: fixed; right: 52px; bottom: 124px;" color="primary"
      @click="configToString(); codeEditorDialog = true">
    </v-btn>

  </div>

  <!-- Full Screen Editor Dialog -->
  <v-dialog v-model="codeEditorDialog" fullscreen transition="dialog-bottom-transition" scrollable>
    <v-card>
      <v-toolbar color="primary" dark>
        <v-btn icon @click="codeEditorDialog = false">
          <v-icon>mdi-close</v-icon>
        </v-btn>
        <v-toolbar-title>编辑配置文件</v-toolbar-title>
        <v-spacer></v-spacer>
        <v-toolbar-items style="display: flex; align-items: center;">
          <v-btn style="margin-left: 16px;" size="small" @click="configToString()">{{
            tm('editor.revertCode') }}</v-btn>
          <v-btn v-if="config_data_has_changed" style="margin-left: 16px;" size="small" @click="applyStrConfig()">{{
            tm('editor.applyConfig') }}</v-btn>
          <small style="margin-left: 16px;">💡 {{ tm('editor.applyTip') }}</small>
        </v-toolbar-items>
      </v-toolbar>
      <v-card-text class="pa-0">
        <VueMonacoEditor language="json" theme="vs-dark" style="height: calc(100vh - 64px);"
          v-model:value="config_data_str">
        </VueMonacoEditor>
      </v-card-text>
    </v-card>
  </v-dialog>

  <v-snackbar :timeout="3000" elevation="24" :color="save_message_success" v-model="save_message_snack">
    {{ save_message }}
  </v-snackbar>

  <WaitingForRestart ref="wfr"></WaitingForRestart>
</template>


<script>
import axios from 'axios';
import AstrBotConfigV4 from '@/components/shared/AstrBotConfigV4.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { useI18n, useModuleI18n } from '@/i18n/composables';

export default {
  name: 'ConfigPage',
  components: {
    AstrBotConfigV4,
    VueMonacoEditor,
    WaitingForRestart
  },
  setup() {
    const { t } = useI18n();
    const { tm } = useModuleI18n('features/config');

    return {
      t,
      tm
    };
  },

  computed: {
    // 安全访问翻译的计算属性
    messages() {
      return {
        loadError: this.tm('messages.loadError'),
        saveSuccess: this.tm('messages.saveSuccess'),
        saveError: this.tm('messages.saveError'),
        configApplied: this.tm('messages.configApplied'),
        configApplyError: this.tm('messages.configApplyError')
      };
    }
  },
  watch: {
    config_data_str: function (val) {
      this.config_data_has_changed = true;
    }
  },
  data() {
    return {
      codeEditorDialog: false,
      config_data_has_changed: false,
      config_data_str: "",
      config_data: {
        config: {}
      },
      fetched: false,
      metadata: {},
      save_message_snack: false,
      save_message: "",
      save_message_success: "",
      namespace: "",
      tab: 0,

      config_template_tab: 0,

      // 多配置文件管理
      selectedConfigInfo: null, // 用于存储当前选中的配置项信息
      configInfoList: [],
    }
  },
  mounted() {
    this.getConfigInfoList()
  },
  methods: {
    getConfigInfoList() {
      // 获取配置列表
      axios.get('/api/config/abconfs').then((res) => {
        this.configInfoList = res.data.data.info_list;
      }).catch((err) => {
        this.save_message = this.messages.loadError;
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },

    getConfig(abconf_id) {
      axios.get('/api/config/abconf', {
        params: {
          id: abconf_id
        }
      }).then((res) => {
        this.config_data = res.data.data.config;
        this.fetched = true
        this.metadata = res.data.data.metadata;
      }).catch((err) => {
        this.save_message = this.messages.loadError;
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
    updateConfig() {
      if (!this.fetched) return;
      axios.post('/api/config/astrbot/update', this.config_data).then((res) => {
        if (res.data.status === "ok") {
          this.save_message = res.data.message || this.messages.saveSuccess;
          this.save_message_snack = true;
          this.save_message_success = "success";
          this.$refs.wfr.check();
        } else {
          this.save_message = res.data.message || this.messages.saveError;
          this.save_message_snack = true;
          this.save_message_success = "error";
        }
      }).catch((err) => {
        this.save_message = this.messages.saveError;
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
    configToString() {
      this.config_data_str = JSON.stringify(this.config_data, null, 2);
      this.config_data_has_changed = false;
    },
    applyStrConfig() {
      try {
        this.config_data = JSON.parse(this.config_data_str);
        this.config_data_has_changed = false;
        this.save_message_success = "success";
        this.save_message = this.messages.configApplied;
        this.save_message_snack = true;
      } catch (e) {
        this.save_message_success = "error";
        this.save_message = this.messages.configApplyError;
        this.save_message_snack = true;
      }
    },
    addFromDefaultConfigTmpl(val, group_name, config_item_name) {
      console.log(val);

      let tmpl = this.metadata[group_name]['metadata'][config_item_name]['config_template'][val];
      let new_tmpl_cfg = JSON.parse(JSON.stringify(tmpl));
      this.config_data[config_item_name].push(new_tmpl_cfg);
      this.config_template_tab = this.config_data[config_item_name].length - 1;
    },
    deleteItem(config_item_name, index) {
      console.log(config_item_name, index);
      let new_list = [];
      for (let i = 0; i < this.config_data[config_item_name].length; i++) {
        if (i !== index) {
          new_list.push(this.config_data[config_item_name][i]);
        }
      }
      this.config_data[config_item_name] = new_list;

      if (this.config_template_tab > 0) {
        this.config_template_tab -= 1;
      }
    }
  },
}

</script>

<style>
.v-tab {
  text-transform: none !important;
}

@media (min-width: 768px) {
  .config-tabs {
    display: flex;
    max-width: 200px;
    margin: 16px 16px 0 0;
  }

  .config-panel {
    width: 750px;
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

  .v-container {
    padding: 4px;
  }
  
  .config-panel {
    width: 100%;
  }
  
  .config-tabs-window {
    margin-top: 16px;
  }
}
</style>