<template>

  <div style="display: flex; flex-direction: column; align-items: center;">
    <div v-if="selectedConfigID" class="mt-4 config-panel"
      style="display: flex; flex-direction: column; align-items: start;">

      <div class="d-flex flex-row pr-4"
        style="margin-bottom: 16px; align-items: center; gap: 12px; justify-content: space-between; width: 100%;">
        <div class="d-flex flex-row align-center" style="gap: 12px;">
          <v-select style="width: 200px;" v-model="selectedConfigID" :items="configInfoList" item-title="name"
            item-value="id" label="选择配置文件" hide-details density="compact" rounded="md" variant="outlined"
            @update:model-value="getConfig">
            <template v-slot:item="{ props: itemProps, item }">
              <v-list-item v-bind="itemProps" :subtitle="formatUmop(item.raw.umop)"></v-list-item>
            </template>
          </v-select>
          <small v-if="selectedConfigInfo">
            {{ formatUmop(selectedConfigInfo.umop) }}
          </small>

        </div>

        <div class="d-flex align-center" style="gap: 8px;">
          <v-btn 
            v-if="selectedConfigID && selectedConfigID !== 'default'" 
            color="warning" 
            @click="onClickEditConfig" 
            variant="tonal" 
            prepend-icon="mdi-pencil"
            size="small">
            编辑信息
          </v-btn>
          <v-btn 
            v-if="selectedConfigID && selectedConfigID !== 'default'" 
            color="error" 
            @click="onClickDeleteConfig" 
            variant="tonal" 
            prepend-icon="mdi-delete"
            size="small">
            删除
          </v-btn>
          <v-btn size="small" color="primary" @click="onClickCreateConfig" variant="tonal" prepend-icon="mdi-plus">新配置文件</v-btn>
        </div>
      </div>

      <div v-if="selectedConfigID && fetched" style="width: 100%;">
        <!-- 可视化编辑 -->
        <div :class="$vuetify.display.mobile ? '' : 'd-flex'">
          <v-tabs v-model="tab" :direction="$vuetify.display.mobile ? 'horizontal' : 'vertical'"
            :align-tabs="$vuetify.display.mobile ? 'left' : 'start'" color="deep-purple-accent-4" class="config-tabs">
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

    </div>
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

  <!-- New Config Dialog -->
  <v-dialog v-model="newConfigDialog" max-width="600px">
    <v-card>
      <v-card-title>
        <span class="text-h4">新建配置文件</span>
      </v-card-title>
      <v-card-text>
        <small>AstrBot 支持针对不同消息平台实例分别设置配置文件。默认会使用 `default` 配置。</small>
        <div class="mt-1">
          <small v-if="conflictMessage">{{ conflictMessage }}</small>
        </div>
        <h3 class="mt-4">名称</h3>

        <v-text-field v-model="newConfigInfo.name" label="Name" variant="outlined" density="compact" rounded="md"
          hide-details class="mt-4"></v-text-field>

        <h3 class="mt-4">应用于</h3>

        <v-select v-model="newConfigInfo.umop" :items="platformList" item-title="id" item-value="id" label="选择应用平台"
          hide-details density="compact" rounded="md" variant="outlined" class="mt-4" multiple
          @update:model-value="checkPlatformConflictOnSelect">
          <template v-slot:item="{ props: itemProps, item }">
            <v-list-item v-bind="itemProps" :subtitle="item.raw.type"></v-list-item>
          </template>
        </v-select>

        

      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="newConfigDialog = false">
          取消
        </v-btn>
        <v-btn color="blue-darken-1" variant="text" @click="createNewConfig">
          创建
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- Edit Config Info Dialog -->
  <v-dialog v-model="editConfigDialog" max-width="600px">
    <v-card>
      <v-card-title>
        <span class="text-h4">编辑配置文件信息</span>
      </v-card-title>
      <v-card-text>
        <div class="mt-1">
          <small v-if="editConflictMessage">{{ editConflictMessage }}</small>
        </div>

        <h3 class="mt-4">名称</h3>

        <v-text-field v-model="editConfigInfo.name" label="Name" variant="outlined" density="compact" rounded="md"
          hide-details class="mt-4"></v-text-field>

        <h3 class="mt-4">应用于</h3>

        <v-select v-model="editConfigInfo.umop" :items="platformList" item-title="id" item-value="id" label="选择应用平台"
          hide-details density="compact" rounded="md" variant="outlined" class="mt-4" multiple
          @update:model-value="checkEditPlatformConflictOnSelect">
          <template v-slot:item="{ props: itemProps, item }">
            <v-list-item v-bind="itemProps" :subtitle="item.raw.type"></v-list-item>
          </template>
        </v-select>



      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="editConfigDialog = false">
          取消
        </v-btn>
        <v-btn color="blue-darken-1" variant="text" @click="updateConfigInfo">
          更新
        </v-btn>
      </v-card-actions>
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
    messages() {
      return {
        loadError: this.tm('messages.loadError'),
        saveSuccess: this.tm('messages.saveSuccess'),
        saveError: this.tm('messages.saveError'),
        configApplied: this.tm('messages.configApplied'),
        configApplyError: this.tm('messages.configApplyError')
      };
    },
    configInfoNameList() {
      return this.configInfoList.map(info => info.name);
    },
    selectedConfigInfo() {
      return this.configInfoList.find(info => info.id === this.selectedConfigID) || {};
    },
  },
  watch: {
    config_data_str: function (val) {
      this.config_data_has_changed = true;
    }
  },
  data() {
    return {
      codeEditorDialog: false,
      newConfigDialog: false,
      editConfigDialog: false,
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
      selectedConfigID: null, // 用于存储当前选中的配置项信息
      configInfoList: [],
      platformList: [],
      newConfigInfo: {
        name: '',
        umop: [],
      },
      editConfigInfo: {
        name: '',
        umop: [],
      },
      conflictMessage: '', // 冲突提示信息
      editConflictMessage: '', // 编辑时的冲突提示信息
    }
  },
  mounted() {
    this.getConfigInfoList("default");
  },
  methods: {
    getConfigInfoList(abconf_id) {
      // 获取配置列表
      axios.get('/api/config/abconfs').then((res) => {
        this.configInfoList = res.data.data.info_list;

        if (abconf_id) {
          for (let i = 0; i < this.configInfoList.length; i++) {
            if (this.configInfoList[i].id === abconf_id) {
              this.selectedConfigID = this.configInfoList[i].id
              this.getConfig(abconf_id);
              break;
            }
          }
        }
      }).catch((err) => {
        this.save_message = this.messages.loadError;
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
    getPlatformList() {
      axios.get('/api/config/platform/list').then((res) => {
        this.platformList = res.data.data.platforms;
      }).catch((err) => {
        console.error(this.t('status.dataError'), err);
      });
    },
    getConfig(abconf_id) {
      this.fetched = false
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
    },
    createNewConfig() {
      if (!this.newConfigInfo.name || !this.newConfigInfo.umop.length) {
        this.save_message = "请填写配置名称和选择应用平台";
        this.save_message_snack = true;
        this.save_message_success = "error";
        return;
      }

      // 如果有冲突，阻止创建
      if (this.conflictMessage) {
        return;
      }

      this.newConfigDialog = false;
      // 修正为 umo part 形式
      // 暂时只支持 platform:: 形式
      for (let i = 0; i < this.newConfigInfo.umop.length; i++) {
        this.newConfigInfo.umop[i] += "::" // 即 platform:: 形式，代表应用于所有该平台的所有会话
      }

      axios.post('/api/config/abconf/new', {
        umo_parts: this.newConfigInfo.umop,
        name: this.newConfigInfo.name
      }).then((res) => {
        if (res.data.status === "ok") {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "success";
          this.getConfigInfoList(res.data.data.conf_id);
        } else {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "error";
        }
      }).catch((err) => {
        console.error(err);
        this.save_message = "新配置文件创建失败";
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
    checkPlatformConflict(newPlatforms) {
      const conflictConfigs = [];

      // 遍历现有的配置文件，排除名为 "default" 的配置
      for (const config of this.configInfoList) {
        if (config.name === 'default') {
          continue; // 跳过 default 配置
        }

        if (config.umop && config.umop.length > 0) {
          // 获取现有配置的平台列表
          const existingPlatforms = config.umop.map(umop => {
            const platformPart = umop.split(":")[0];
            return platformPart === "" ? "*" : platformPart; // 空字符串表示所有平台
          });

          // 检查是否有重复的平台
          const hasConflict = newPlatforms.some(newPlatform => {
            return existingPlatforms.includes(newPlatform) || existingPlatforms.includes("*");
          }) || (newPlatforms.includes("*") && existingPlatforms.length > 0);

          if (hasConflict) {
            conflictConfigs.push(config);
          }
        }
      }

      return conflictConfigs;
    },
    checkPlatformConflictOnSelect() {
      if (!this.newConfigInfo.umop || this.newConfigInfo.umop.length === 0) {
        this.conflictMessage = '';
        return;
      }

      const conflictConfigs = this.checkPlatformConflict(this.newConfigInfo.umop);
      if (conflictConfigs.length > 0) {
        const conflictNames = conflictConfigs.map(config => config.name).join(', ');
        this.conflictMessage = `提示：选择的平台与现有配置文件重复：${conflictNames}。AstrBot 将只会应用首个匹配的配置文件。`;
      } else {
        this.conflictMessage = '';
      }
    },
    onClickCreateConfig() {
      this.newConfigDialog = true;
      this.newConfigInfo = {
        name: '',
        umop: [],
      };
      this.conflictMessage = ''; // 重置冲突信息
      if (!this.platformList.length) {
        this.getPlatformList();
      }
    },
    onClickEditConfig() {
      this.editConfigDialog = true;
      const currentConfig = this.selectedConfigInfo;
      this.editConfigInfo = {
        name: currentConfig.name || '',
        umop: currentConfig.umop ? currentConfig.umop.map(part => part.split("::")[0]).filter(p => p) : [],
      };
      this.editConflictMessage = ''; // 重置冲突信息
      if (!this.platformList.length) {
        this.getPlatformList();
      }
    },
    onClickDeleteConfig() {
      if (confirm(`确定要删除配置文件 "${this.selectedConfigInfo.name}" 吗？此操作不可恢复。`)) {
        axios.post('/api/config/abconf/delete', {
          id: this.selectedConfigID
        }).then((res) => {
          if (res.data.status === "ok") {
            this.save_message = res.data.message;
            this.save_message_snack = true;
            this.save_message_success = "success";
            // 删除成功后，切换到默认配置
            this.getConfigInfoList("default");
          } else {
            this.save_message = res.data.message;
            this.save_message_snack = true;
            this.save_message_success = "error";
          }
        }).catch((err) => {
          console.error(err);
          this.save_message = "删除配置文件失败";
          this.save_message_snack = true;
          this.save_message_success = "error";
        });
      }
    },
    updateConfigInfo() {
      if (!this.editConfigInfo.name || !this.editConfigInfo.umop.length) {
        this.save_message = "请填写配置名称和选择应用平台";
        this.save_message_snack = true;
        this.save_message_success = "error";
        return;
      }

      // 如果有冲突，阻止更新
      if (this.editConflictMessage) {
        return;
      }

      this.editConfigDialog = false;
      // 修正为 umo part 形式
      // 暂时只支持 platform:: 形式
      const umo_parts = this.editConfigInfo.umop.map(platform => platform + "::");

      axios.post('/api/config/abconf/update', {
        id: this.selectedConfigID,
        name: this.editConfigInfo.name,
        umo_parts: umo_parts
      }).then((res) => {
        if (res.data.status === "ok") {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "success";
          this.getConfigInfoList(this.selectedConfigID);
        } else {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "error";
        }
      }).catch((err) => {
        console.error(err);
        this.save_message = "更新配置文件失败";
        this.save_message_snack = true;
        this.save_message_success = "error";
      });
    },
    checkEditPlatformConflictOnSelect() {
      if (!this.editConfigInfo.umop || this.editConfigInfo.umop.length === 0) {
        this.editConflictMessage = '';
        return;
      }

      // 检查与其他配置文件的冲突 (排除当前编辑的配置文件)
      const conflictConfigs = this.checkPlatformConflict(this.editConfigInfo.umop).filter(
        config => config.id !== this.selectedConfigID
      );
      
      if (conflictConfigs.length > 0) {
        const conflictNames = conflictConfigs.map(config => config.name).join(', ');
        this.editConflictMessage = `提示：选择的平台与现有配置文件重复：${conflictNames}。AstrBot 将只会应用首个匹配的配置文件。`;
      } else {
        this.editConflictMessage = '';
      }
    },
    formatUmop(umop) {
      if (!umop) {
        return
      }
      let ret = ""
      for (let i = 0; i < umop.length; i++) {
        let platformPart = umop[i].split(":")[0];
        if (platformPart === "") {
          return "所有平台";
        } else {
          ret += platformPart + ",";
        }
      }
      ret = ret.slice(0, -1);
      return ret;
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