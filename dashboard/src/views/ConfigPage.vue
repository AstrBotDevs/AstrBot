

<template>
  <v-card style="margin-bottom: 16px;">
    <v-card-text style="padding: 0;">
      <div>
        <v-btn-group variant="outlined" divided>
          <v-btn icon="mdi-text-box-edit-outline" style="width: 80px;" :color="editorTab === 0 ? 'primary' : ''"
            @click="editorTab = 0">
          </v-btn>
          <v-btn icon="mdi-code-json" style="width: 80px;" :color="editorTab === 1 ? 'primary' : ''"
            @click="configToString(); editorTab = 1;"></v-btn>
        </v-btn-group>
        <v-btn v-if="editorTab === 1" style="margin-left: 16px;" size="small" @click="configToString()">{{ tm('editor.revertCode') }}</v-btn>
        <v-btn v-if="editorTab === 1 && config_data_has_changed" style="margin-left: 16px;" size="small"
          @click="applyStrConfig()">{{ tm('editor.applyConfig') }}</v-btn>
        <small v-if="editorTab === 1" style="margin-left: 16px;">💡 {{ tm('editor.applyTip') }}</small>
      </div>

    </v-card-text>
  </v-card>

  <!-- 可视化编辑 -->
  <v-card v-if="editorTab === 0">
    <v-tabs v-model="tab" align-tabs="left" color="deep-purple-accent-4">
      <v-tab v-for="(val, key, index) in metadata" :key="index" :value="index"
        style="font-weight: 1000; font-size: 15px">
        {{ metadata[key]['name'] }}
      </v-tab>
    </v-tabs>
    <v-tabs-window v-model="tab">
      <v-tabs-window-item v-for="(val, key, index) in metadata" v-show="index == tab" :key="index">
        <v-container fluid>

          <div v-for="(val2, key2, index2) in metadata[key]['metadata']">
            <!-- <h3>{{ metadata[key]['metadata'][key2]['description'] }}</h3> -->
            <div v-if="metadata[key]['metadata'][key2]?.config_template"
              v-show="key2 !== 'platform' && key2 !== 'provider'" style="border: 1px solid var(--v-theme-border); padding: 8px; margin-bottom: 16px; border-radius: 10px">
              <!-- 带有 config_template 的配置项 -->
              <v-list-item-title style="font-weight: bold;">
                {{ metadata[key]['metadata'][key2]['description'] }} ({{ key2 }})
              </v-list-item-title>
              <v-tabs style="margin-top: 16px;" align-tabs="left" color="deep-purple-accent-4"
              
                v-model="config_template_tab">
                <v-tab v-if="metadata[key]['metadata'][key2]?.tmpl_display_title"
                  v-for="(item, index) in config_data[key2]" :key="index" :value="index">
                  {{ item[metadata[key]['metadata'][key2]?.tmpl_display_title] }}
                </v-tab>
                <v-tab v-else v-for="(item, index) in config_data[key2]" :key="index + '_'" :value="index">
                  {{ item.id }}({{ item.type }})
                </v-tab>
                <v-menu>
                  <template v-slot:activator="{ props }">
                    <v-btn variant="plain" size="large" v-bind="props">
                      <v-icon>mdi-plus</v-icon>
                    </v-btn>
                  </template>
                  <v-list @update:selected="addFromDefaultConfigTmpl($event, key, key2)">
                    <v-list-item v-for="(item, index) in metadata[key]['metadata'][key2]?.config_template" :key="index"
                      :value="index">
                      <v-list-item-title>{{ index }}</v-list-item-title>
                    </v-list-item>
                  </v-list>
                </v-menu>
              </v-tabs>
              <v-tabs-window v-model="config_template_tab">
                <v-tabs-window-item v-for="(config_item, index) in config_data[key2]"
                  v-show="config_template_tab === index" :key="index" :value="index">
                  <div style="padding: 16px;">
                    <v-btn variant="tonal" rounded="xl" color="error" @click="deleteItem(key2, index)">
                      {{ tm('actions.delete') }}
                    </v-btn>

                    <AstrBotConfig :metadata="metadata[key]['metadata']" :iterable="config_item" :metadataKey="key2">
                    </AstrBotConfig>
                  </div>
                </v-tabs-window-item>
              </v-tabs-window>
            </div>

            <div v-else>
              <!-- 如果配置项是一个 object，那么 iterable 需要取到这个 object 的值，否则取到整个 config_data -->
              <div v-if="metadata[key]['metadata'][key2]['type'] == 'object'" style="border: 1px solid var(--v-theme-border); padding: 8px; margin-bottom: 16px; border-radius: 10px">
                <AstrBotConfig
                  :metadata="metadata[key]['metadata']" :iterable="config_data[key2]" :metadataKey="key2">
                </AstrBotConfig>
              </div>
              <AstrBotConfig v-else :metadata="metadata[key]['metadata']" :iterable="config_data" :metadataKey="key2">
              </AstrBotConfig>
            </div>

          </div>



        </v-container>
      </v-tabs-window-item>


      <div style="margin-left: 16px; padding-bottom: 16px">
        <small>{{ tm('help.helpPrefix') }} 
          <a href="https://astrbot.app/" target="_blank">{{ tm('help.documentation') }}</a>
          {{ tm('help.helpMiddle') }} 
          <a href="https://qm.qq.com/cgi-bin/qm/qr?k=EYGsuUTfe00_iOu9JTXS7_TEpMkXOvwv&jump_from=webapi&authKey=uUEMKCROfsseS+8IzqPjzV3y1tzy4AkykwTib2jNkOFdzezF9s9XknqnIaf3CDft" target="_blank">{{ tm('help.support') }}</a>{{ tm('help.helpSuffix') }}
        </small>
      </div>

    </v-tabs-window>
  </v-card>

  <!-- 代码编辑 -->
  <v-card v-else style="background-color: #1e1e1e;">
    <VueMonacoEditor theme="vs-dark" language="json" height="80vh" style="padding-top: 16px; padding-bottom: 16px;"
      v-model:value="config_data_str">
    </VueMonacoEditor>
  </v-card>

  <v-btn icon="mdi-content-save" size="x-large" style="position: fixed; right: 52px; bottom: 52px;" color="darkprimary"
    @click="updateConfig">
  </v-btn>

  <v-snackbar :timeout="3000" elevation="24" :color="save_message_success" v-model="save_message_snack">
    {{ save_message }}
  </v-snackbar>

  <WaitingForRestart ref="wfr"></WaitingForRestart>
</template>


<script>
import axios from 'axios';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import config from '@/config';
import { useI18n, useModuleI18n } from '@/i18n/composables';

export default {
  name: 'ConfigPage',
  components: {
    AstrBotConfig,
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
      config_data_has_changed: false,
      config_data_str: "",
      config_data: {
        config: {}
      },
      fetched: false,
      metadata: {},
      provider_config_tmpl: {},
      adapter_config_tmpl: {}, // 平台适配器
      save_message_snack: false,
      save_message: "",
      save_message_success: "",
      namespace: "",
      tab: 0,
      editorTab: 0, // 0: visual, 1: code

      config_template_tab: 0,
    }
  },
  mounted() {
    this.getConfig();
  },
  methods: {
    getConfig() {
      // 获取配置
      axios.get('/api/config/get').then((res) => {
        this.config_data = res.data.data.config;
        this.fetched = true
        this.metadata = res.data.data.metadata;
        this.provider_config_tmpl = res.data.data.provider_config_tmpl;
        this.adapter_config_tmpl = res.data.data.adapter_config_tmpl;
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
      // new_tmpl_cfg.id = "new_" + val + "_" + this.config_data[config_item_name].length;
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
</style>