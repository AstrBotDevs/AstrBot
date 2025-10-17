<template>
  <v-dialog v-model="showDialog" max-width="800px" height="90%">
    <v-card
      :title="updatingMode ? `${tm('dialog.edit')} ${updatingPlatformConfig.id} ${tm('dialog.adapter')}` : tm('dialog.addPlatform')">
      <v-card-text class="pa-4 ml-2" style="overflow-y: auto;">
        <div class="d-flex align-start" style="width: 100%;">
          <div>
            <v-icon icon="mdi-numeric-1-circle" class="mr-3"></v-icon>
          </div>
          <div style="flex: 1;">
            <h3>
              选择消息平台类别
            </h3>
            <small style="color: grey;">想把机器人接入到哪里？如 QQ、企业微信、飞书、Discord、Telegram 等。</small>
            <div>

              <div v-if="!updatingMode">
                <v-select v-model="selectedPlatformType" :items="Object.keys(platformTemplates)" item-title="name"
                  item-value="name" label="消息平台类别" variant="outlined" rounded="md" dense hide-details class="mt-6"
                  style="max-width: 30%; min-width: 300px;">

                  <template v-slot:item="{ props: itemProps, item }">
                    <v-list-item v-bind="itemProps">
                      <template v-slot:prepend>
                        <img :src="getPlatformIcon(platformTemplates[item.raw].type)"
                          style="width: 32px; height: 32px; object-fit: contain; margin-right: 16px;" />
                      </template>
                    </v-list-item>
                  </template>

                </v-select>
                <div class="mt-3" v-if="selectedPlatformConfig">
                  <v-btn color="info" variant="tonal" @click="openTutorial" class="mt-2">
                    <v-icon start>mdi-book-open-variant</v-icon>
                    {{ tm('dialog.viewTutorial') }}
                  </v-btn>
                  <div class="mt-2">
                    <AstrBotConfig :iterable="selectedPlatformConfig" :metadata="metadata['platform_group']?.metadata"
                      metadataKey="platform" />
                  </div>
                </div>
              </div>
              <div v-else>
                <v-text-field label="消息平台类别" variant="outlined" rounded="md" dense hide-details class="mt-6"
                  style="max-width: 30%; min-width: 300px;" v-model="updatingPlatformConfig.type"
                  disabled></v-text-field>
                <div class="mt-3">
                  <div class="mt-2">
                    <AstrBotConfig :iterable="updatingPlatformConfig" :metadata="metadata['platform_group']?.metadata"
                      metadataKey="platform" />
                  </div>
                </div>
              </div>

            </div>
          </div>
        </div>

        <div class="d-flex align-start mt-6">
          <div>
            <v-icon icon="mdi-numeric-2-circle" class="mr-3"></v-icon>
          </div>
          <div style="flex: 1;">
            <div class="d-flex align-center justify-space-between">
              <div>
                <div class="d-flex align-center">
                  <h3>
                    配置文件
                  </h3>
                  <v-chip size="x-small" color="primary" variant="tonal" rounded="sm" class="ml-2" v-if="!updatingMode">可选</v-chip>
                </div>
                <small style="color: grey;">想如何配置机器人？配置文件包含了聊天模型、人格、知识库、插件范围等丰富的机器人配置项。</small>
                <small style="color: grey;" v-if="!updatingMode">默认使用默认配置文件 “default”。您也可以稍后配置。</small>
                <small style="color: grey;" v-if="updatingMode">配置文件的修改请前往「配置文件」页。</small>
              </div>
              <div>
                <v-btn variant="plain" icon @click="showConfigSection = !showConfigSection" class="mt-2">
                  <v-icon>{{ showConfigSection ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
                </v-btn>
              </div>

            </div>

            <div v-if="showConfigSection">
              <div v-if="!updatingMode">
                <v-radio-group class="mt-2" v-model="aBConfigRadioVal" hide-details="true">
                  <v-radio value="0">
                    <template v-slot:label>
                      <span>使用现有配置文件</span>
                    </template>
                  </v-radio>
                  <v-select v-if="aBConfigRadioVal === '0'" v-model="selectedAbConfId" :items="configInfoList"
                    item-title="name" item-value="id" label="选择配置文件" variant="outlined" rounded="md" dense hide-details
                    style="max-width: 30%; min-width: 200px;" class="ml-10 my-2">
                  </v-select>
                  <v-radio value="1" label="创建新配置文件">
                  </v-radio>
                  <div class="d-flex align-center" v-if="aBConfigRadioVal === '1'">
                    <v-text-field v-model="selectedAbConfId" label="新配置文件名称" variant="outlined" rounded="md" dense
                      hide-details style="max-width: 30%; min-width: 200px;" class="ml-10 my-2">
                    </v-text-field>
                  </div>

                </v-radio-group>

                <!-- 现有配置文件预览区域 -->
                <div v-if="aBConfigRadioVal === '0' && selectedAbConfId" class="mt-4">
                  <div v-if="configPreviewLoading" class="d-flex justify-center py-4">
                    <v-progress-circular indeterminate color="primary"></v-progress-circular>
                  </div>
                  <div v-else-if="selectedConfigData && selectedConfigMetadata" class="config-preview-container">
                    <h4 class="mb-3">配置文件预览</h4>
                    <AstrBotCoreConfigWrapper :metadata="selectedConfigMetadata" :config_data="selectedConfigData" readonly="true"/>
                  </div>
                  <div v-else class="text-center py-4 text-grey">
                    <v-icon>mdi-information-outline</v-icon>
                    <p class="mt-2">无法加载配置文件预览</p>
                  </div>
                </div>


                <!-- 新配置文件编辑区域 -->
                <div v-if="aBConfigRadioVal === '1'" class="mt-4">
                  <div v-if="newConfigLoading" class="d-flex justify-center py-4">
                    <v-progress-circular indeterminate color="primary"></v-progress-circular>
                  </div>
                  <div v-else-if="newConfigData && newConfigMetadata" class="config-preview-container">
                    <h4 class="mb-3">使用新的配置文件</h4>
                    <AstrBotCoreConfigWrapper :metadata="newConfigMetadata" :config_data="newConfigData" />
                  </div>
                  <div v-else class="text-center py-4 text-grey">
                    <v-icon>mdi-information-outline</v-icon>
                    <p class="mt-2">无法加载默认配置模板</p>
                  </div>
                </div>

              </div>

              <div v-else>
                <v-data-table :headers="configTableHeaders" :items="platformConfigs" item-value="id"
                  no-data-text="该平台暂无关联的配置文件" hide-default-footer :items-per-page="-1" class="mt-2" variant="outlined">
                  <template v-slot:item.scope="{ item }">
                    <v-chip v-for="(umop, index) in item.umop" :key="index"
                      v-show="isUmopMatchPlatform(umop, updatingPlatformConfig.id)" size="small" color="primary"
                      variant="tonal" rounded="md" class="mr-1 mb-1">
                      {{ formatUmopScope(umop) }}
                    </v-chip>
                  </template>
                  <template v-slot:item.name="{ item }">
                    <span> {{ item.name }} </span>
                    <v-chip v-if="item.name === 'default'" size="x-small" variant="tonal" rounded="sm"
                      class="ml-2">兜底配置</v-chip>
                  </template>
                </v-data-table>
                <small class="ml-2">Tips: 暂时无法在此更新配置文件，请前往「配置文件」页更新。</small>
              </div>
            </div>


          </div>
        </div>

      </v-card-text>

      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn text @click="closeDialog">{{ tm('dialog.cancel') }}</v-btn>
        <v-btn :disabled="!canSave" color="primary" v-if="!updatingMode" @click="newPlatform" :loading="loading">{{
          tm('dialog.save') }}</v-btn>
        <v-btn :disabled="!selectedAbConfId" color="primary" v-else @click="newPlatform" :loading="loading">{{
          tm('dialog.save') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ID冲突确认对话框 -->
  <v-dialog v-model="showIdConflictDialog" max-width="450" persistent>
    <v-card>
      <v-card-title class="text-h6 bg-warning d-flex align-center">
        <v-icon start class="me-2">mdi-alert-circle-outline</v-icon>
        {{ tm('dialog.idConflict.title') }}
      </v-card-title>
      <v-card-text class="py-4 text-body-1 text-medium-emphasis">
        {{ tm('dialog.idConflict.message', { id: conflictId }) }}
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="handleIdConflictConfirm(false)">{{ tm('dialog.idConflict.confirm')
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 安全警告对话框 -->
  <v-dialog v-model="showOneBotEmptyTokenWarnDialog" max-width="600" persistent>
    <v-card>
      <v-card-title>
        {{ tm('dialog.securityWarning.title') }}
      </v-card-title>
      <v-card-text class="py-4">
        <p>{{ tm('dialog.securityWarning.aiocqhttpTokenMissing') }}</p>
        <span><a
            href="https://docs.astrbot.app/deploy/platform/aiocqhttp/napcat.html#%E9%99%84%E5%BD%95-%E5%A2%9E%E5%BC%BA%E8%BF%9E%E6%8E%A5%E5%AE%89%E5%85%A8%E6%80%A7"
            target="_blank">{{ tm('dialog.securityWarning.learnMore') }}</a></span>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer></v-spacer>
        <v-btn color="error" @click="handleOneBotEmptyTokenWarningDismiss(true)">
          无视警告并继续创建
        </v-btn>
        <v-btn color="primary" @click="handleOneBotEmptyTokenWarningDismiss(false)">
          重新修改
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';
import { getPlatformIcon, getPlatformDescription, getTutorialLink } from '@/utils/platformUtils';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import AstrBotCoreConfigWrapper from '@/components/config/AstrBotCoreConfigWrapper.vue';

export default {
  name: 'AddNewPlatform',
  components: { AstrBotConfig, AstrBotCoreConfigWrapper },
  emits: ['update:show', 'show-toast', 'refresh-config', 'edit-platform-config'],
  props: {
    show: {
      type: Boolean,
      default: false
    },
    metadata: {
      type: Object,
      default: () => ({})
    },
    config_data: {
      type: Object,
      default: () => ({})
    },
    updatingMode: {
      type: Boolean,
      default: false
    },
    updatingPlatformConfig: {
      type: Object,
      default: null
    }
  },
  data() {
    return {
      selectedPlatformType: null,
      selectedPlatformConfig: null,

      aBConfigRadioVal: '0',
      selectedAbConfId: 'default',
      configInfoList: [],

      // 选中的配置文件预览数据
      selectedConfigData: null,
      selectedConfigMetadata: null,
      configPreviewLoading: false,

      // 新配置文件相关数据
      newConfigData: null,
      newConfigMetadata: null,
      newConfigLoading: false,

      // 平台配置文件表格
      platformConfigs: [],
      configTableHeaders: [
        { title: '与此实例关联的配置文件 ID', key: 'name', sortable: false },
        { title: '在此实例下的应用范围 (UMOP)', key: 'scope', sortable: false },
      ],

      // ID冲突确认对话框
      showIdConflictDialog: false,
      conflictId: '',
      idConflictResolve: null,

      // OneBot Empty Token Warning #2639
      showOneBotEmptyTokenWarnDialog: false,
      oneBotEmptyTokenWarningResolve: null,

      loading: false,

      showConfigSection: false,
    };
  },
  setup() {
    const { tm } = useModuleI18n('features/platform');
    return { tm };
  },
  computed: {
    showDialog: {
      get() {
        return this.show;
      },
      set(value) {
        this.$emit('update:show', value);
      }
    },
    platformTemplates() {
      return this.metadata['platform_group']?.metadata?.platform?.config_template || {};
    },
    canSave() {
      // 基本条件：必须选择平台类型
      if (!this.selectedPlatformType) {
        return false;
      }

      // 如果是使用现有配置文件模式
      if (this.aBConfigRadioVal === '0') {
        return !!this.selectedAbConfId;
      }

      // 如果是创建新配置文件模式
      if (this.aBConfigRadioVal === '1') {
        // 需要配置文件名称，且新配置数据已加载
        return !!(this.selectedAbConfId && this.newConfigData);
      }

      return false;
    }
  },
  watch: {
    selectedPlatformType(newType) {
      if (newType && this.platformTemplates[newType]) {
        this.selectedPlatformConfig = JSON.parse(JSON.stringify(this.platformTemplates[newType]));
      } else {
        this.selectedPlatformConfig = null;
      }
    },
    selectedAbConfId(newConfigId) {
      // 当选择配置文件改变时，获取配置文件数据用于预览
      if (!this.updatingMode && this.aBConfigRadioVal === '0' && newConfigId) {
        this.getConfigForPreview(newConfigId);
      } else {
        this.selectedConfigData = null;
        this.selectedConfigMetadata = null;
      }
    },
    aBConfigRadioVal(newVal) {
      // 当切换到创建新配置文件时，获取默认配置模板
      if (newVal === '1') {
        this.selectedConfigData = null;
        this.selectedConfigMetadata = null;
        this.selectedAbConfId = null;
        this.getDefaultConfigTemplate();
      } else if (newVal === '0') {
        // 如果切换回使用现有配置文件但没有选择配置文件，重置为默认
        this.newConfigData = null;
        this.newConfigMetadata = null;
        if (!this.selectedAbConfId) {
          this.selectedAbConfId = 'default';
        }
      }
    },
    showIdConflictDialog(newValue) {
      if (!newValue && this.idConflictResolve) {
        this.idConflictResolve(false);
        this.idConflictResolve = null;
      }
    },
    showOneBotEmptyTokenWarnDialog(newValue) {
      if (!newValue && this.oneBotEmptyTokenWarningResolve) {
        this.oneBotEmptyTokenWarningResolve(true);
        this.oneBotEmptyTokenWarningResolve = null;
      }
    },
    // 监听更新模式变化，获取相关配置文件
    updatingPlatformConfig: {
      handler(newConfig) {
        if (this.updatingMode && newConfig && newConfig.id) {
          this.getPlatformConfigs(newConfig.id);
        }
      },
      immediate: true
    },
    showConfigSection(newValue) {
      if (newValue && !this.updatingMode && this.aBConfigRadioVal === '0') {
        this.getConfigForPreview(this.selectedAbConfId);
      }
    }
  },
  methods: {
    getPlatformIcon,
    getPlatformDescription,
    resetForm() {
      this.selectedPlatformType = null;
      this.selectedPlatformConfig = null;

      this.aBConfigRadioVal = '0';
      this.selectedAbConfId = 'default';

      // 重置配置预览数据
      this.selectedConfigData = null;
      this.selectedConfigMetadata = null;
      this.configPreviewLoading = false;

      // 重置新配置文件数据
      this.newConfigData = null;
      this.newConfigMetadata = null;
      this.newConfigLoading = false;

      this.showConfigSection = false;
    },
    closeDialog() {
      this.resetForm();

      this.showDialog = false;
    },
    async getConfigInfoList() {
      await axios.get('/api/config/abconfs').then((res) => {
        this.configInfoList = res.data.data.info_list;
      })
    },

    // 获取配置文件数据用于预览
    async getConfigForPreview(configId) {
      if (!configId) {
        this.selectedConfigData = null;
        this.selectedConfigMetadata = null;
        return;
      }

      this.configPreviewLoading = true;
      try {
        const response = await axios.get('/api/config/abconf', {
          params: { id: configId }
        });

        this.selectedConfigData = response.data.data.config;
        this.selectedConfigMetadata = response.data.data.metadata;
      } catch (error) {
        console.error('获取配置文件预览数据失败:', error);
        this.selectedConfigData = null;
        this.selectedConfigMetadata = null;
      } finally {
        this.configPreviewLoading = false;
      }
    },

    // 获取默认配置模板用于创建新配置文件
    async getDefaultConfigTemplate() {
      this.newConfigLoading = true;
      try {
        const response = await axios.get('/api/config/default');
        this.newConfigData = response.data.data.config;
        this.newConfigMetadata = response.data.data.metadata;
      } catch (error) {
        console.error('获取默认配置模板失败:', error);
        this.newConfigData = null;
        this.newConfigMetadata = null;
      } finally {
        this.newConfigLoading = false;
      }
    },
    openTutorial() {
      const tutorialUrl = getTutorialLink(this.selectedPlatformConfig.type);
      window.open(tutorialUrl, '_blank');
    },
    newPlatform() {
      this.loading = true;
      if (this.updatingMode) {
        if (this.updatingPlatformConfig.type === 'aiocqhttp') {
          const token = this.updatingPlatformConfig.ws_reverse_token;
          if (!token || token.trim() === '') {
            this.showOneBotEmptyTokenWarning().then((continueWithWarning) => {
              if (continueWithWarning) {
                this.updatePlatform();
              } else {
                this.loading = false;
              }
            });
            return;
          }
        }
        this.updatePlatform();
      } else {
        this.savePlatform();
      }
    },
    updatePlatform() {
      let id = this.updatingPlatformConfig.id;
      if (!id) {
        this.loading = false;
        this.showError('更新失败，缺少平台 ID。');
        return;
      }
      axios.post('/api/config/platform/update', {
        id: id,
        config: this.updatingPlatformConfig
      }).then((res) => {
        this.loading = false;
        this.showDialog = false;
        this.resetForm();
        this.$emit('refresh-config');
        this.showSuccess(res.data.message || '更新成功');
      }).catch((err) => {
        this.loading = false;
        this.showError(err.response?.data?.message || err.message);
      });
      this.updatingMode = false;
    },
    async savePlatform() {
      // 检查 ID 是否已存在
      const existingPlatform = this.config_data.platform?.find(p => p.id === this.selectedPlatformConfig.id);
      if (existingPlatform || this.selectedPlatformConfig.id === 'webchat') {
        const confirmed = await this.confirmIdConflict(this.selectedPlatformConfig.id);
        if (!confirmed) {
          this.loading = false;
          return; // 如果用户取消，则中止保存
        }
      }

      // 检查 aiocqhttp 适配器的安全设置
      if (this.selectedPlatformConfig.type === 'aiocqhttp') {
        const token = this.selectedPlatformConfig.ws_reverse_token;
        if (!token || token.trim() === '') {
          const continueWithWarning = await this.showOneBotEmptyTokenWarning();
          if (!continueWithWarning) {
            return;
          }
        }
      }

      try {
        // 先保存平台配置
        const res = await axios.post('/api/config/platform/new', this.selectedPlatformConfig);

        // 平台保存成功后，处理配置文件
        await this.handleConfigFile();

        this.loading = false;
        this.showDialog = false;
        this.resetForm();
        this.$emit('refresh-config');
        this.showSuccess(res.data.message || '平台添加成功，配置文件已更新');
      } catch (err) {
        this.loading = false;
        this.showError(err.response?.data?.message || err.message);
      }
    },

    async handleConfigFile() {
      if (!this.selectedAbConfId) {
        return;
      }

      const platformId = this.selectedPlatformConfig.id;
      // 生成默认的UMOP：平台ID:*:*（表示该平台的所有消息类型和会话）
      const newUmop = `${platformId}:*:*`;

      if (this.aBConfigRadioVal === '0') {
        // 使用现有配置文件，更新其UMOP
        await this.updateExistingConfigUmop(this.selectedAbConfId, newUmop);
      } else if (this.aBConfigRadioVal === '1') {
        // 创建新配置文件
        await this.createNewConfigFile(this.selectedAbConfId, newUmop);
      }
    },

    async updateExistingConfigUmop(configId, newUmop) {
      try {
        // 先获取现有配置文件信息
        await this.getConfigInfoList(); // 确保configInfoList是最新的
        const existingConfig = this.configInfoList.find(conf => conf.id === configId);

        if (!existingConfig) {
          throw new Error(`配置文件 ID ${configId} 不存在`);
        }

        // 获取现有的UMOP数组，如果不存在则创建新数组
        let currentUmop = existingConfig.umop || [];

        // 检查是否已存在相同的UMOP
        if (!currentUmop.includes(newUmop)) {
          currentUmop.push(newUmop);
        }

        // 更新配置文件的UMOP
        await axios.post('/api/config/abconf/update', {
          id: configId,
          umo_parts: currentUmop
        });

        console.log(`成功更新配置文件 ${configId} 的UMOP`);
      } catch (err) {
        console.error('更新配置文件UMOP失败:', err);
        throw new Error(`更新配置文件失败: ${err.response?.data?.message || err.message}`);
      }
    },

    async createNewConfigFile(configName, newUmop) {
      try {
        // 准备配置数据，如果是创建模式且有新配置数据，使用用户填写的配置
        const configData = this.aBConfigRadioVal === '1' && this.newConfigData
          ? this.newConfigData
          : undefined;

        // 创建新的配置文件
        const createRes = await axios.post('/api/config/abconf/new', {
          name: configName,
          umo_parts: [newUmop],
          config: configData  // 传入用户配置的数据
        });

        console.log(`成功创建新配置文件 ${configName}，ID: ${createRes.data.data.conf_id}`);
      } catch (err) {
        console.error('创建新配置文件失败:', err);
        throw new Error(`创建新配置文件失败: ${err.response?.data?.message || err.message}`);
      }
    },

    confirmIdConflict(id) {
      this.conflictId = id;
      this.showIdConflictDialog = true;
      return new Promise((resolve) => {
        this.idConflictResolve = resolve;
      });
    },

    handleIdConflictConfirm(confirmed) {
      if (this.idConflictResolve) {
        this.idConflictResolve(confirmed);
      }
      this.showIdConflictDialog = false;
    },

    showOneBotEmptyTokenWarning() {
      this.showOneBotEmptyTokenWarnDialog = true;
      return new Promise((resolve) => {
        this.oneBotEmptyTokenWarningResolve = resolve;
      });
    },

    handleOneBotEmptyTokenWarningDismiss(continueWithWarning) {
      this.showOneBotEmptyTokenWarnDialog = false;
      if (this.oneBotEmptyTokenWarningResolve) {
        this.oneBotEmptyTokenWarningResolve(continueWithWarning);
        this.oneBotEmptyTokenWarningResolve = null;
      }

      if (!continueWithWarning) {
        this.loading = false;
      }
    },

    showSuccess(message) {
      this.$emit('show-toast', { message: message, type: 'success' });
    },

    showError(message) {
      this.$emit('show-toast', { message: message, type: 'error' });
    },

    // 获取该平台适配器使用的所有配置文件
    getPlatformConfigs(platformId) {
      if (!platformId) {
        this.platformConfigs = [];
        return;
      }

      axios.get('/api/config/abconfs').then((res) => {
        const allConfigs = res.data.data.info_list;

        // 过滤出使用该平台的配置文件
        this.platformConfigs = allConfigs.filter(config => {
          if (!config.umop || config.umop.length === 0) {
            return false;
          }

          // 检查UMOP是否匹配该平台
          return config.umop.some(umop => {
            return this.isUmopMatchPlatform(umop, platformId);
          });
        });
      }).catch((err) => {
        console.error('获取平台配置文件失败:', err);
        this.platformConfigs = [];
      });
    },

    isUmopMatchPlatform(umop, platformId) {
      if (!umop) return false;
      const parts = umop.split(':');
      if (parts.length !== 3) return false;
      const platform = parts[0];
      return platform === platformId || platform === '' || platform === '*';
    },

    // 格式化UMOP显示
    formatUmopScope(umop) {
      if (!umop) return '';

      const parts = umop.split(':');
      if (parts.length !== 3) return umop;

      const [platform, messageType, sessionId] = parts;

      // 格式化各部分
      // const platformText = platform === '' || platform === '*' ? '全部平台' : platform;
      const messageTypeText = this.getMessageTypeLabel(messageType === '' || messageType === '*' ? '*' : messageType);
      const sessionText = sessionId === '' || sessionId === '*' ? '全部会话' : sessionId;

      return `${messageTypeText}:${sessionText}`;
    },

    // 获取消息类型标签
    getMessageTypeLabel(messageType) {
      const typeMap = {
        '*': '全部消息',
        '': '全部消息',
        'GroupMessage': '群组消息',
        'FriendMessage': '私聊消息'
      };
      return typeMap[messageType] || messageType;
    },

    // 编辑平台配置文件
    editPlatformConfig(config) {
      this.$emit('edit-platform-config', config);
    },

  },
  mounted() {
    this.getConfigInfoList();
    this.getConfigForPreview(this.selectedAbConfId);
    if (this.updatingMode && this.updatingPlatformConfig && this.updatingPlatformConfig.id) {
      this.getPlatformConfigs(this.updatingPlatformConfig.id);
    }
  }
}
</script>

