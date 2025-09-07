<template>

  <div style="display: flex; flex-direction: column; align-items: center;">
    <div v-if="selectedConfigID || isSystemConfig" class="mt-4 config-panel"
      style="display: flex; flex-direction: column; align-items: start;">

      <!-- 普通配置选择区域 -->
      <div class="d-flex flex-row pr-4"
        style="margin-bottom: 16px; align-items: center; gap: 12px; justify-content: space-between; width: 100%;">
        <div class="d-flex flex-row align-center" style="gap: 12px;">
          <v-select style="min-width: 130px;" v-model="selectedConfigID" :items="configSelectItems" item-title="name"
            v-if="!isSystemConfig" item-value="id" label="选择配置文件" hide-details density="compact" rounded="md"
            variant="outlined" @update:model-value="onConfigSelect">
            <template v-slot:item="{ props: itemProps, item }">
              <v-list-item v-bind="itemProps"
                :subtitle="item.raw.id === '_%manage%_' ? '管理所有配置文件' : formatUmop(item.raw.umop)"
                :class="item.raw.id === '_%manage%_' ? 'text-primary' : ''">
              </v-list-item>
            </template>
          </v-select>
          <a style="color: inherit;" href="https://blog.astrbot.app/posts/what-is-changed-in-4.0.0/#%E5%A4%9A%E9%85%8D%E7%BD%AE%E6%96%87%E4%BB%B6" target="_blank"><v-btn icon="mdi-help-circle" size="small" variant="plain"></v-btn></a>

        </div>

        <v-btn-toggle v-model="configType" mandatory color="primary" variant="outlined" density="comfortable"
          rounded="md" @update:model-value="onConfigTypeToggle">
          <v-btn value="normal" prepend-icon="mdi-cog" size="large">
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
            <div v-if="conflictMessage" class="text-warning">
              <div v-html="conflictMessage" style="font-size: 0.875rem; line-height: 1.4;"></div>
            </div>
          </div>

          <h4>名称</h4>

          <v-text-field v-model="configFormData.name" label="填写配置文件名称" variant="outlined" class="mt-4 mb-4"
            hide-details></v-text-field>

          <h4>应用于</h4>

          <v-radio-group class="mt-2" v-model="appliedToRadioValue" hide-details="true">
            <v-radio value="0">
              <template v-slot:label>
                <span>指定消息平台...</span>
              </template>
            </v-radio>
            <v-select v-if="appliedToRadioValue === '0'" v-model="configFormData.umop" :items="platformList" item-title="id" item-value="id"
                  label="选择已配置的消息平台(可多选)" variant="outlined" hide-details multiple class="ma-2"
                  @update:model-value="checkPlatformConflictOnForm">
                  <template v-slot:item="{ props: itemProps, item }">
                    <v-list-item v-bind="itemProps" :subtitle="item.raw.type"></v-list-item>
                  </template>
            </v-select>
            <v-radio value="1" label="自定义规则(实验性)">
            </v-radio>
            
            <!-- 自定义规则界面 -->
            <div v-if="appliedToRadioValue === '1'" class="ma-2">
              <small class="text-medium-emphasis mb-4 d-block">UMO 格式: [platform_id]:[message_type]:[session_id]。通配符 * 或留空表示全部。使用 /sid 查看某个聊天的 UMO。</small>
              
              <!-- 输入方式切换 -->
              <v-btn-toggle v-model="customRuleInputMode" mandatory color="primary" variant="outlined" density="compact"
                rounded="md" class="mb-4">
                <v-btn value="builder" prepend-icon="mdi-tune" size="x-small">
                  可视化
                </v-btn>
                <v-btn value="manual" prepend-icon="mdi-code-tags" size="x-small">
                  手动编辑
                </v-btn>
              </v-btn-toggle>
              
              <!-- 快速规则构建 -->
              <div v-if="customRuleInputMode === 'builder'" class="mb-4">
                <div v-for="(rule, index) in customRules" :key="index" class="d-flex align-center mb-2" style="gap: 8px;">
                  <v-select 
                    v-model="rule.platform" 
                    :items="[{ id: '*', type: '所有平台' }, ...platformList]" 
                    item-title="id" 
                    item-value="id"
                    label="平台" 
                    variant="outlined" 
                    density="compact"
                    style="min-width: 120px;"
                    @update:model-value="updateCustomRule(index)">
                    <template v-slot:item="{ props: itemProps, item }">
                      <v-list-item v-bind="itemProps" :subtitle="item.raw.type"></v-list-item>
                    </template>
                  </v-select>
                  
                  <v-select 
                    v-model="rule.messageType" 
                    :items="messageTypeOptions" 
                    item-title="label" 
                    item-value="value"
                    label="消息类型" 
                    variant="outlined" 
                    density="compact"
                    style="min-width: 130px;"
                    @update:model-value="updateCustomRule(index)">
                  </v-select>
                  
                  <v-text-field 
                    v-model="rule.sessionId" 
                    label="会话ID" 
                    variant="outlined" 
                    density="compact"
                    placeholder="* 或留空表示全部"
                    style="min-width: 120px;"
                    @update:model-value="updateCustomRule(index)">
                  </v-text-field>
                  
                  <v-btn 
                    icon="mdi-delete" 
                    size="small" 
                    variant="text" 
                    color="error"
                    @click="removeCustomRule(index)"
                    :disabled="customRules.length === 1">
                  </v-btn>
                </div>
                
                <v-btn 
                  prepend-icon="mdi-plus" 
                  size="small" 
                  variant="tonal" 
                  color="primary"
                  @click="addCustomRule">
                  添加规则
                </v-btn>
              </div>
              
              <!-- 手动输入 -->
              <div v-if="customRuleInputMode === 'manual'" class="mb-4">
                <v-textarea 
                  v-model="manualRulesText" 
                  label="手动输入规则(每行一个)" 
                  variant="outlined"
                  rows="4"
                  placeholder="每行一个规则，例如：&#10;platform1:GroupMessage:*&#10;*:FriendMessage:session123&#10;*:*:*"
                  @update:model-value="updateManualRules">
                </v-textarea>
              </div>
              
              <!-- 规则预览 -->
              <div class="mb-2">
                <small class="text-medium-emphasis">
                  <strong>预览:</strong> 
                  <span v-if="!configFormData.umop.length" class="text-error">未配置任何规则</span>
                  <div v-else class="mt-1">
                    <v-chip 
                      v-for="(rule, index) in configFormData.umop" 
                      :key="index" 
                      size="x-small" 
                      rounded="sm"
                      class="mr-1">
                      {{ rule }}
                    </v-chip>
                  </div>
                  <small>这些规则对应的会话将使用此配置文件。</small>
                </small>
              </div>
            </div>
          </v-radio-group>



          <div class="d-flex justify-end mt-4" style="gap: 8px;">
            <v-btn variant="text" @click="cancelConfigForm">取消</v-btn>
            <v-btn color="primary" @click="saveConfigForm"
              :disabled="!configFormData.name || !configFormData.umop.length">
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
    },
    customRuleInputMode: function (newVal) {
      if (newVal === 'builder') {
        // 切换到快速构建，从手动输入同步数据
        this.syncCustomRulesFromManual();
      } else if (newVal === 'manual') {
        // 切换到手动输入，从快速构建同步数据
        this.syncManualRulesText();
      }
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
      appliedToRadioValue: '0',
      selectedConfigID: null, // 用于存储当前选中的配置项信息
      configInfoList: [],
      platformList: [],
      configFormData: {
        name: '',
        umop: [],
      },
      editingConfigId: null,
      conflictMessage: '', // 冲突提示信息
      
      // 自定义规则相关
      customRuleInputMode: 'builder', // 'builder' 或 'manual'
      customRules: [
        {
          platform: '*',
          messageType: '*',
          sessionId: '*'
        }
      ],
      manualRulesText: '',
      messageTypeOptions: [
        { label: '所有消息类型', value: '*' },
        { label: '群组消息', value: 'GroupMessage' },
        { label: '私聊消息', value: 'FriendMessage' }
      ],
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
        config: JSON.parse(JSON.stringify(this.config_data)),
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
      let umo_parts = [];
      
      if (this.appliedToRadioValue === '0') {
        // 修正为 umo part 形式 - 指定平台
        umo_parts = this.configFormData.umop.map(platform => platform + "::");
      } else if (this.appliedToRadioValue === '1') {
        // 自定义规则
        umo_parts = [...this.configFormData.umop]; // 直接使用 umop，它已经包含完整的规则
      }

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
    checkPlatformConflict(newRules) {
      const conflictConfigs = [];

      // 遍历现有的配置文件，排除名为 "default" 的配置
      for (const config of this.configInfoList) {
        if (config.name === 'default') {
          continue; // 跳过 default 配置
        }

        if (config.umop && config.umop.length > 0) {
          // 检查是否有冲突
          const hasConflict = this.hasUmoConflict(newRules, config.umop);

          if (hasConflict) {
            conflictConfigs.push(config);
          }
        }
      }

      return conflictConfigs;
    },
    
    hasUmoConflict(newRules, existingRules) {
      // 检查新规则与现有规则是否有冲突
      for (const newRule of newRules) {
        for (const existingRule of existingRules) {
          if (this.isUmoMatch(newRule, existingRule) || this.isUmoMatch(existingRule, newRule)) {
            return true;
          }
        }
      }
      return false;
    },
    
    isUmoMatch(p1, p2) {
      // 判断 p2 umo 是否逻辑包含于 p1 umo
      // 基于后端的 _is_umo_match 逻辑
      
      // 先标准化规则格式
      const p1_normalized = this.normalizeUmoRule(p1);
      const p2_normalized = this.normalizeUmoRule(p2);
      
      const p1_parts = p1_normalized.split(":");
      const p2_parts = p2_normalized.split(":");

      if (p1_parts.length !== 3 || p2_parts.length !== 3) {
        return false; // 非法格式
      }

      // 检查每个部分是否匹配
      return p1_parts.every((p, index) => {
        const t = p2_parts[index];
        return p === "" || p === "*" || p === t;
      });
    },
    
    normalizeUmoRule(rule) {
      // 标准化规则格式
      if (typeof rule !== 'string') {
        return "*:*:*";
      }
      
      const parts = rule.split(":");
      
      if (parts.length === 2 && parts[1] === "") {
        // 传统格式 "platform::" -> "platform:*:*"
        return `${parts[0] || "*"}:*:*`;
      } else if (parts.length === 3) {
        // 已经是完整格式，只需要处理空字符串
        return parts.map(part => part === "" ? "*" : part).join(":");
      } else if (parts.length === 1) {
        // 只有平台 "platform" -> "platform:*:*"
        return `${parts[0] || "*"}:*:*`;
      }
      
      // 默认返回通配符
      return "*:*:*";
    },
    
    getDetailedConflictInfo(newRules) {
      const conflictDetails = [];
      
      // 获取所有配置文件及其优先级（按创建时间排序，早创建的优先级高）
      const sortedConfigs = [...this.configInfoList]
        .filter(config => config.name !== 'default')
        .sort((a, b) => {
          // 假设按字母顺序排序作为优先级（实际应该按创建时间）
          return a.id.localeCompare(b.id);
        });

      for (const config of sortedConfigs) {
        if (!config.umop || config.umop.length === 0) continue;
        
        const conflictingRules = [];
        
        for (const newRule of newRules) {
          for (const existingRule of config.umop) {
            if (this.isUmoMatch(newRule, existingRule) || this.isUmoMatch(existingRule, newRule)) {
              conflictingRules.push({
                newRule: newRule,
                existingRule: existingRule,
                matchType: this.getMatchType(newRule, existingRule)
              });
            }
          }
        }
        
        if (conflictingRules.length > 0) {
          conflictDetails.push({
            config: config,
            conflicts: conflictingRules
          });
        }
      }
      
      return conflictDetails;
    },
    
    getMatchType(rule1, rule2) {
      const r1_normalized = this.normalizeUmoRule(rule1);
      const r2_normalized = this.normalizeUmoRule(rule2);
      
      const isR1MatchR2 = this.isUmoMatch(rule1, rule2);
      const isR2MatchR1 = this.isUmoMatch(rule2, rule1);
      
      if (isR1MatchR2 && isR2MatchR1) {
        return 'exact'; // 完全匹配
      } else if (isR1MatchR2) {
        return 'new_covers_existing'; // 新规则覆盖现有规则
      } else if (isR2MatchR1) {
        return 'existing_covers_new'; // 现有规则覆盖新规则
      }
      
      return 'overlap'; // 部分重叠
    },
    
    formatConflictMessage(conflictDetails) {
      if (conflictDetails.length === 0) return '';
      
      let message = '⚠️ <strong>规则冲突警告：</strong><br><br>';
      
      // 按优先级排序（最先创建的配置文件优先级最高）
      const sortedDetails = [...conflictDetails].sort((a, b) => 
        a.config.id.localeCompare(b.config.id)
      );
      
      sortedDetails.forEach((detail, index) => {
        const configName = detail.config.name || detail.config.id;
        message += `<strong>${index + 1}. 与配置文件 "${configName}" 冲突：</strong><br>`;
        
        detail.conflicts.forEach(conflict => {
          const newRuleFormatted = this.formatRuleForDisplay(conflict.newRule);
          const existingRuleFormatted = this.formatRuleForDisplay(conflict.existingRule);
          
          switch (conflict.matchType) {
            case 'exact':
              message += `规则完全相同: <code>${newRuleFormatted}</code><br>`;
              message += `<span style="color: orange;">"${configName}" 将覆盖当前配置</span><br>`;
              break;
            case 'new_covers_existing':
              message += `当前规则 <code>${newRuleFormatted}</code> 包含现有规则 <code>${existingRuleFormatted}</code><br>`;
              message += `<span style="color: red;">"${configName}" 的规则将优先匹配</span><br>`;
              break;
            case 'existing_covers_new':
              message += `现有规则 <code>${existingRuleFormatted}</code> 包含当前规则 <code>${newRuleFormatted}</code><br>`;
              message += `<span style="color: red;">"${configName}" 的规则将优先匹配</span><br>`;
              break;
            case 'overlap':
              message += `规则重叠: <code>${newRuleFormatted}</code> ↔ <code>${existingRuleFormatted}</code><br>`;
              message += `<span style="color: orange;">"${configName}" 在匹配范围内优先</span><br>`;
              break;
          }
        });
        
        if (index < sortedDetails.length - 1) {
          message += '<br>';
        }
      });
      
      message += '<br><small><strong>💡 说明：</strong> 您仍可创建此配置文件。AstrBot 按配置文件创建顺序匹配规则，先创建的配置文件优先级更高。当多个配置文件的规则匹配同一个消息会话来源时，优先级最高的配置文件会生效（default 配置文件除外）。</small>';
      
      return message;
    },
    
    formatRuleForDisplay(rule) {
      const parts = this.normalizeUmoRule(rule).split(':');
      const platform = parts[0] === '*' || parts[0] === '' ? '任意平台' : parts[0];
      const messageType = parts[1] === '*' || parts[1] === '' ? '任意消息' : this.getMessageTypeLabel(parts[1]);
      const sessionId = parts[2] === '*' || parts[2] === '' ? '任意会话' : parts[2];
      
      return `${platform}:${messageType}:${sessionId}`;
    },
    
    getMessageTypeLabel(messageType) {
      const typeMap = {
        'GroupMessage': '群组消息',
        'FriendMessage': '私聊消息',
      };
      return typeMap[messageType] || messageType;
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
      this.resetCustomRules();
    },
    startEditConfig(config) {
      this.appliedToRadioValue = "1";
      this.showConfigForm = true;
      this.isEditingConfig = true;
      this.editingConfigId = config.id;

      this.parseExistingCustomRules(config.umop || []);

      this.configFormData = {
        name: config.name || '',
        umop: [...(config.umop || [])],
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
      this.resetCustomRules();
    },
    saveConfigForm() {
      if (!this.configFormData.name || !this.configFormData.umop.length) {
        this.save_message = "请填写配置名称和选择应用平台";
        this.save_message_snack = true;
        this.save_message_success = "error";
        return;
      }

      if (this.isEditingConfig) {
        this.updateConfigInfo();
      } else {
        this.createNewConfig();
      }
    },
    
    // 自定义规则相关方法
    addCustomRule() {
      this.customRules.push({
        platform: '*',
        messageType: '*',
        sessionId: '*'
      });
      this.updateCustomRulesFromBuilder();
    },
    
    removeCustomRule(index) {
      if (this.customRules.length > 1) {
        this.customRules.splice(index, 1);
        this.updateCustomRulesFromBuilder();
      }
    },
    
    updateCustomRule(index) {
      this.updateCustomRulesFromBuilder();
    },
    
    updateCustomRulesFromBuilder() {
      // 从规则构建器更新 umop
      const rules = this.customRules.map(rule => {
        const platform = rule.platform === '*' ? '' : rule.platform;
        const messageType = rule.messageType === '*' ? '' : rule.messageType;
        const sessionId = rule.sessionId === '*' ? '' : (rule.sessionId || '');
        return `${platform}:${messageType}:${sessionId}`;
      });
      
      this.configFormData.umop = rules;
      this.syncManualRulesText();
      // 触发冲突检测
      this.checkPlatformConflictOnForm();
    },
    
    updateManualRules() {
      // 从手动输入更新 umop
      const rules = this.manualRulesText
        .split('\n')
        .map(rule => rule.trim())
        .filter(rule => rule);
      
      this.configFormData.umop = rules;
      this.syncCustomRulesFromManual();
      // 触发冲突检测
      this.checkPlatformConflictOnForm();
    },
    
    syncManualRulesText() {
      // 同步到手动输入文本区域
      this.manualRulesText = this.configFormData.umop.join('\n');
    },
    
    syncCustomRulesFromManual() {
      // 从手动输入同步到规则构建器
      this.customRules = this.configFormData.umop.map(rule => {
        const parts = rule.split(':');
        return {
          platform: parts[0] || '*',
          messageType: parts[1] || '*',
          sessionId: parts[2] || '*'
        };
      });
    },
    
    resetCustomRules() {
      this.customRuleInputMode = 'builder'; // 重置为快速构建模式
      this.customRules = [
        {
          platform: '*',
          messageType: '*',
          sessionId: '*'
        }
      ];
      this.manualRulesText = '';
      if (this.appliedToRadioValue === '1') {
        this.updateCustomRulesFromBuilder();
      }
    },
    
    parseExistingCustomRules(umop) {
      // 解析现有的自定义规则
      if (!umop || umop.length === 0) {
        this.resetCustomRules();
        return;
      }
      
      this.customRules = umop.map(rule => {
        const parts = rule.split(':');
        return {
          platform: parts[0] || '*',
          messageType: parts[1] || '*', 
          sessionId: parts[2] || '*'
        };
      });
      
      this.syncManualRulesText();
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

      // 准备用于冲突检测的规则列表
      let rulesToCheck = [];
      
      if (this.appliedToRadioValue === '0') {
        // 平台模式：转换为标准UMO格式
        rulesToCheck = this.configFormData.umop.map(platform => `${platform}:*:*`);
      } else {
        // 自定义模式：直接使用规则
        rulesToCheck = [...this.configFormData.umop];
      }

      // 检查与其他配置文件的冲突
      let conflictDetails = this.getDetailedConflictInfo(rulesToCheck);

      // 如果是编辑模式，排除当前编辑的配置文件
      if (this.isEditingConfig && this.editingConfigId) {
        conflictDetails = conflictDetails.filter(detail => detail.config.id !== this.editingConfigId);
      }

      if (conflictDetails.length > 0) {
        this.conflictMessage = this.formatConflictMessage(conflictDetails);
      } else {
        this.conflictMessage = '';
      }
    },
    updateConfigInfo() {
      let umo_parts = [];
      
      if (this.appliedToRadioValue === '0') {
        // 修正为 umo part 形式 - 指定平台
        umo_parts = this.configFormData.umop.map(platform => platform + "::");
      } else if (this.appliedToRadioValue === '1') {
        // 自定义规则
        umo_parts = [...this.configFormData.umop]; // 直接使用 umop，它已经包含完整的规则
      }

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
        const parts = umop[i].split(":");
        if (parts.length === 3) {
          // 自定义规则格式 platform:messageType:sessionId
          const platform = parts[0] || "*";
          const messageType = parts[1] || "*";
          const sessionId = parts[2] || "*";
          if (platform === "*" && messageType === "*" && sessionId === "*") {
            return "所有平台";
          }
          ret += `${platform}:${messageType}:${sessionId},`;
        } else {
          // 传统平台格式
          let platformPart = umop[i].split(":")[0];
          if (platformPart === "") {
            return "所有平台";
          } else {
            ret += platformPart + ",";
          }
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

/* 冲突消息样式 */
.text-warning code {
  background-color: rgba(255, 193, 7, 0.1);
  color: #e65100;
  padding: 2px 4px;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 500;
}

.text-warning strong {
  color: #f57c00;
}

.text-warning small {
  color: #6c757d;
  font-style: italic;
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