<template>

  <div style="display: flex; flex-direction: column; align-items: center;">
    <div v-if="selectedConfigID || isSystemConfig" class="mt-4 config-panel"
      style="display: flex; flex-direction: column; align-items: start;">

      <!-- 普通配置选择区域 -->
      <div class="d-flex flex-row pr-4"
        style="margin-bottom: 16px; align-items: center; gap: 12px; justify-content: space-between; width: 100%;">
        <div class="d-flex flex-row align-center" style="gap: 12px;" >
          <v-select style="min-width: 130px;" v-model="selectedConfigID" :items="configSelectItems" item-title="name" v-if="!isSystemConfig"
            item-value="id" label="选择配置文件" hide-details density="compact" rounded="md" variant="outlined"
            @update:model-value="onConfigSelect">
            <template v-slot:item="{ props: itemProps, item }">
              <v-list-item v-bind="itemProps"
                :subtitle="item.raw.id === '_%manage%_' ? '管理所有配置文件' : formatUmop(item.raw.umop)"
                :class="item.raw.id === '_%manage%_' ? 'text-primary' : ''">
              </v-list-item>
            </template>
          </v-select>
        </div>

        <v-btn-toggle v-model="configType" mandatory color="primary" variant="outlined" density="comfortable"
          rounded="md" @update:model-value="onConfigTypeToggle">
          <v-btn value="normal" prepend-icon="mdi-cog" size="large" >
            普通
          </v-btn>
          <v-btn value="system" prepend-icon="mdi-cog-outline" size="large">
            系统
          </v-btn>
        </v-btn-toggle>
      </div>

      <v-progress-linear v-if="!fetched" indeterminate color="primary"></v-progress-linear>

      <div v-if="(selectedConfigID || isSystemConfig) && fetched" style="width: 100%;">
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

  <!-- Config Management Dialog -->
  <v-dialog v-model="configManageDialog" max-width="800px">
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span class="text-h4">配置文件管理</span>
        <v-btn icon="mdi-close" variant="text" @click="configManageDialog = false"></v-btn>
      </v-card-title>

      <v-card-text>
        <small>AstrBot 支持针对不同消息平台实例分别设置配置文件。默认会使用 `default` 配置。</small>
        <div class="mt-6 mb-4">
          <v-btn prepend-icon="mdi-plus" @click="startCreateConfig" variant="tonal" color="primary">
            新建配置文件
          </v-btn>
        </div>

        <!-- Config List -->
        <v-list lines="two">
          <v-list-item v-for="config in configInfoList" :key="config.id" :title="config.name">
            <v-list-item-subtitle>当前应用于: {{ formatUmop(config.umop) }} </v-list-item-subtitle>

            <template v-slot:append v-if="config.id !== 'default'">
              <div class="d-flex align-center" style="gap: 8px;">
                <v-btn icon="mdi-pencil" size="small" variant="text" color="warning"
                  @click="startEditConfig(config)"></v-btn>
                <v-btn icon="mdi-delete" size="small" variant="text" color="error"
                  @click="confirmDeleteConfig(config)"></v-btn>
              </div>
            </template>
          </v-list-item>
        </v-list>

        <!-- Create/Edit Form -->
        <v-divider v-if="showConfigForm" class="my-6"></v-divider>

        <div v-if="showConfigForm">
          <h3 class="mb-4">{{ isEditingConfig ? '编辑配置文件' : '新建配置文件' }}</h3>

          <div class="mb-4">
            <small v-if="conflictMessage">⚠ {{ conflictMessage }}</small>
          </div>

          <v-text-field v-model="configFormData.name" label="配置文件名称" variant="outlined" class="mb-4"
            hide-details></v-text-field>

          <v-select v-model="configFormData.umop" :items="platformList" item-title="id" item-value="id" label="应用于平台"
            variant="outlined" hide-details multiple @update:model-value="checkPlatformConflictOnForm">
            <template v-slot:item="{ props: itemProps, item }">
              <v-list-item v-bind="itemProps" :subtitle="item.raw.type"></v-list-item>
            </template>
          </v-select>

          <div class="d-flex justify-end mt-4" style="gap: 8px;">
            <v-btn variant="text" @click="cancelConfigForm">取消</v-btn>
            <v-btn color="primary" @click="saveConfigForm"
              :disabled="!configFormData.name || !configFormData.umop.length || !!conflictMessage">
              {{ isEditingConfig ? '更新' : '创建' }}
            </v-btn>
          </div>
        </div>
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
    configSelectItems() {
      const items = [...this.configInfoList];
      items.push({
        id: '_%manage%_',
        name: '管理配置文件...',
        umop: []
      });
      return items;
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
      configManageDialog: false,
      showConfigForm: false,
      isEditingConfig: false,
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

      tab: 0, // 用于切换配置标签页

      // 配置类型切换
      configType: 'normal', // 'normal' 或 'system'

      // 系统配置开关
      isSystemConfig: false,

      // 多配置文件管理
      selectedConfigID: null, // 用于存储当前选中的配置项信息
      configInfoList: [],
      platformList: [],
      configFormData: {
        name: '',
        umop: [],
      },
      editingConfigId: null,
      conflictMessage: '', // 冲突提示信息
    }
  },
  mounted() {
    this.getConfigInfoList("default");
    // 初始化配置类型状态
    this.configType = this.isSystemConfig ? 'system' : 'normal';
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
      const params = {};

      if (this.isSystemConfig) {
        params.system_config = '1';
      } else {
        params.id = abconf_id || this.selectedConfigID;
      }

      axios.get('/api/config/abconf', {
        params: params
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

      const postData = {
        config: this.config_data
      };

      if (this.isSystemConfig) {
        postData.conf_id = 'default';
      } else {
        postData.conf_id = this.selectedConfigID;
      }

      axios.post('/api/config/astrbot/update', postData).then((res) => {
        if (res.data.status === "ok") {
          this.save_message = res.data.message || this.messages.saveSuccess;
          this.save_message_snack = true;
          this.save_message_success = "success";

          if (this.isSystemConfig) {
            axios.post('/api/stat/restart-core').then(() => {
              this.$refs.wfr.check();
            })
          }
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
    createNewConfig() {
      // 修正为 umo part 形式
      // 暂时只支持 platform:: 形式
      const umo_parts = this.configFormData.umop.map(platform => platform + "::");

      axios.post('/api/config/abconf/new', {
        umo_parts: umo_parts,
        name: this.configFormData.name
      }).then((res) => {
        if (res.data.status === "ok") {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "success";
          this.getConfigInfoList(res.data.data.conf_id);
          this.cancelConfigForm();
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
    onConfigSelect(value) {
      if (value === '_%manage%_') {
        this.configManageDialog = true;
        this.getPlatformList();
        // 重置选择到之前的值
        this.$nextTick(() => {
          this.selectedConfigID = this.selectedConfigInfo.id || 'default';
        });
      } else {
        this.getConfig(value);
      }
    },
    startCreateConfig() {
      this.showConfigForm = true;
      this.isEditingConfig = false;
      this.configFormData = {
        name: '',
        umop: [],
      };
      this.editingConfigId = null;
      this.conflictMessage = '';
    },
    startEditConfig(config) {
      this.showConfigForm = true;
      this.isEditingConfig = true;
      this.editingConfigId = config.id;
      this.configFormData = {
        name: config.name || '',
        umop: config.umop ? config.umop.map(part => part.split("::")[0]).filter(p => p) : [],
      };
      this.conflictMessage = '';
    },
    cancelConfigForm() {
      this.showConfigForm = false;
      this.isEditingConfig = false;
      this.editingConfigId = null;
      this.configFormData = {
        name: '',
        umop: [],
      };
      this.conflictMessage = '';
    },
    saveConfigForm() {
      if (!this.configFormData.name || !this.configFormData.umop.length) {
        this.save_message = "请填写配置名称和选择应用平台";
        this.save_message_snack = true;
        this.save_message_success = "error";
        return;
      }

      if (this.conflictMessage) {
        return;
      }

      if (this.isEditingConfig) {
        this.updateConfigInfo();
      } else {
        this.createNewConfig();
      }
    },
    confirmDeleteConfig(config) {
      if (confirm(`确定要删除配置文件 "${config.name}" 吗？此操作不可恢复。`)) {
        this.deleteConfig(config.id);
      }
    },
    deleteConfig(configId) {
      axios.post('/api/config/abconf/delete', {
        id: configId
      }).then((res) => {
        if (res.data.status === "ok") {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "success";
          // 删除成功后，更新配置列表
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
    },
    checkPlatformConflictOnForm() {
      if (!this.configFormData.umop || this.configFormData.umop.length === 0) {
        this.conflictMessage = '';
        return;
      }

      // 检查与其他配置文件的冲突
      let conflictConfigs = this.checkPlatformConflict(this.configFormData.umop);

      // 如果是编辑模式，排除当前编辑的配置文件
      if (this.isEditingConfig && this.editingConfigId) {
        conflictConfigs = conflictConfigs.filter(config => config.id !== this.editingConfigId);
      }

      if (conflictConfigs.length > 0) {
        const conflictNames = conflictConfigs.map(config => config.name).join(', ');
        this.conflictMessage = `提示：选择的平台与现有配置文件重复：${conflictNames}。AstrBot 将只会应用首个匹配的配置文件。`;
      } else {
        this.conflictMessage = '';
      }
    },
    updateConfigInfo() {
      // 修正为 umo part 形式
      // 暂时只支持 platform:: 形式
      const umo_parts = this.configFormData.umop.map(platform => platform + "::");

      axios.post('/api/config/abconf/update', {
        id: this.editingConfigId,
        name: this.configFormData.name,
        umo_parts: umo_parts
      }).then((res) => {
        if (res.data.status === "ok") {
          this.save_message = res.data.message;
          this.save_message_snack = true;
          this.save_message_success = "success";
          this.getConfigInfoList(this.editingConfigId);
          this.cancelConfigForm();
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
    },
    onConfigTypeToggle() {
      this.isSystemConfig = this.configType === 'system';
      this.tab = 0; // 重置标签页
      this.fetched = false; // 重置加载状态

      if (this.isSystemConfig) {
        // 切换到系统配置
        this.getConfig();
      } else {
        // 切换回普通配置，如果有选中的配置文件则加载，否则加载default
        if (this.selectedConfigID) {
          this.getConfig(this.selectedConfigID);
        } else {
          this.getConfigInfoList("default");
        }
      }
    },
    onSystemConfigToggle() {
      // 保持向后兼容性，更新 configType
      this.configType = this.isSystemConfig ? 'system' : 'normal';

      this.tab = 0; // 重置标签页
      this.fetched = false; // 重置加载状态

      if (this.isSystemConfig) {
        // 切换到系统配置
        this.getConfig();
      } else {
        // 切换回普通配置，如果有选中的配置文件则加载，否则加载default
        if (this.selectedConfigID) {
          this.getConfig(this.selectedConfigID);
        } else {
          this.getConfigInfoList("default");
        }
      }
    }
  },
}

</script>

<style>
.v-tab {
  text-transform: none !important;
}

/* 按钮切换样式优化 */
.v-btn-toggle .v-btn {
  transition: all 0.3s ease !important;
}

.v-btn-toggle .v-btn:not(.v-btn--active) {
  opacity: 0.7;
}

.v-btn-toggle .v-btn.v-btn--active {
  opacity: 1;
  font-weight: 600;
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