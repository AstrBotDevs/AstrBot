<template>
  <v-dialog v-model="showDialog" max-width="800px" height="90%" @after-enter="prepareData">
    <v-card
      :title="updatingMode ? `${tm('dialog.edit')} ${updatingPlatformConfig.id} ${tm('dialog.adapter')}` : tm('dialog.addPlatform')">
  <v-card-text ref="dialogScrollContainer" class="pa-4 ml-2" style="overflow-y: auto;">
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
                  <v-chip size="x-small" color="primary" variant="tonal" rounded="sm" class="ml-2"
                    v-if="!updatingMode">可选</v-chip>
                </div>
                <small style="color: grey;">想如何配置机器人？配置文件包含了聊天模型、人格、知识库、插件范围等丰富的机器人配置项。</small>
                <small style="color: grey;" v-if="!updatingMode">默认使用默认配置文件 “default”。您也可以稍后配置。</small>
              </div>
              <div>
                <v-btn variant="plain" icon @click="toggleConfigSection" class="mt-2">
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
                  <div class="d-flex align-center ml-10 my-2" v-if="aBConfigRadioVal === '0'">
                    <v-select v-model="selectedAbConfId" :items="configInfoList" item-title="name"
                      item-value="id" label="选择配置文件" variant="outlined" rounded="md" dense hide-details
                      style="max-width: 30%; min-width: 200px;">
                    </v-select>
                    <v-btn icon variant="text" density="comfortable" class="ml-2"
                      :disabled="!selectedAbConfId" @click="openConfigDrawer(selectedAbConfId)">
                      <v-icon>mdi-arrow-top-right-thick</v-icon>
                    </v-btn>
                  </div>
                  <v-radio value="1" label="创建新配置文件">
                  </v-radio>
                  <div class="d-flex align-center" v-if="aBConfigRadioVal === '1'">
                    <v-text-field v-model="selectedAbConfId" label="新配置文件名称" variant="outlined" rounded="md" dense
                      hide-details style="max-width: 30%; min-width: 200px;" class="ml-10 my-2">
                    </v-text-field>
                  </div>

                </v-radio-group>

                <!-- 现有配置文件预览区域 -->
                <!-- <div v-if="aBConfigRadioVal === '0' && selectedAbConfId" class="mt-4">
                  <div v-if="configPreviewLoading" class="d-flex justify-center py-4">
                    <v-progress-circular indeterminate color="primary"></v-progress-circular>
                  </div>
                  <div v-else-if="selectedConfigData && selectedConfigMetadata" class="config-preview-container">
                    <h4 class="mb-3">配置文件预览</h4>
                    <AstrBotCoreConfigWrapper :metadata="selectedConfigMetadata" :config_data="selectedConfigData"
                      readonly="true" />
                  </div>
                  <div v-else class="text-center py-4 text-grey">
                    <v-icon>mdi-information-outline</v-icon>
                    <p class="mt-2">无法加载配置文件预览</p>
                  </div>
                </div> -->

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
                <div class="mb-3 d-flex align-center justify-space-between">
                  <div>
                    <v-btn v-if="isEditingRoutes" color="primary" variant="tonal" @click="addNewRoute" size="small">
                      <v-icon start>mdi-plus</v-icon>
                      添加路由规则
                    </v-btn>
                  </div>
                  <v-btn :color="isEditingRoutes ? 'grey' : 'primary'" variant="tonal" size="small"
                    @click="toggleEditMode">
                    <v-icon start>{{ isEditingRoutes ? 'mdi-eye' : 'mdi-pencil' }}</v-icon>
                    {{ isEditingRoutes ? '查看' : '编辑' }}
                  </v-btn>
                </div>

                <v-data-table :headers="routeTableHeaders" :items="platformRoutes" item-value="umop"
                  no-data-text="该平台暂无路由规则，将使用默认配置文件" hide-default-footer :items-per-page="-1" class="mt-2"
                  variant="outlined">

                  <template v-slot:item.source="{ item }">
                    <div class="d-flex align-center" style="min-width: 250px;">
                      <v-select v-if="isEditingRoutes" v-model="item.messageType" :items="messageTypeOptions"
                        item-title="label" item-value="value" variant="outlined" density="compact" hide-details
                        style="max-width: 140px;">
                      </v-select>
                      <small v-else>{{ getMessageTypeLabel(item.messageType) }}</small>
                      <small class="mx-1">:</small>
                      <v-text-field v-if="isEditingRoutes" v-model="item.sessionId" variant="outlined" density="compact"
                        hide-details placeholder="会话ID或*">
                      </v-text-field>
                      <small v-else>{{ item.sessionId === '*' ? '全部会话' : item.sessionId }}</small>
                    </div>
                  </template>

                  <template v-slot:item.configId="{ item }">
                    <div class="d-flex align-center">
                      <v-select v-if="isEditingRoutes" v-model="item.configId" :items="configInfoList"
                        item-title="name" item-value="id" variant="outlined" density="compact"
                        style="min-width: 200px;" hide-details>
                      </v-select>
                      <div v-else>
                        <small>{{ getConfigName(item.configId) }}</small>
                      </div>
                      <v-btn icon variant="text" density="compact" class="ml-2"
                        :disabled="!item.configId" @click="openConfigDrawer(item.configId)">
                        <v-icon size="18">mdi-arrow-top-right-thick</v-icon>
                      </v-btn>
                    </div>
                    <small v-if="configInfoList.findIndex(c => c.id === item.configId) === -1" style="color: red;"
                      class="ml-2">配置文件不存在</small>
                  </template>

                  <template v-slot:item.actions="{ item, index }">
                    <div v-if="isEditingRoutes" class="d-flex align-center">
                      <v-btn icon size="x-small" variant="text" @click="moveRouteUp(index)" :disabled="index === 0">
                        <v-icon>mdi-arrow-up</v-icon>
                      </v-btn>
                      <v-btn icon size="x-small" variant="text" @click="moveRouteDown(index)"
                        :disabled="index === platformRoutes.length - 1">
                        <v-icon>mdi-arrow-down</v-icon>
                      </v-btn>
                      <v-btn icon size="x-small" variant="text" color="error" @click="deleteRoute(index)">
                        <v-icon>mdi-delete</v-icon>
                      </v-btn>
                    </div>
                    <span v-else class="text-grey">-</span>
                  </template>

                </v-data-table>
                <small class="ml-2 mt-2 d-block" style="color: grey">*消息下发时，根据会话来源按顺序从上到下匹配首个符合条件的配置文件。使用 * 表示匹配所有。使用 /sid 指令获取会话
                  ID。全部不匹配时将使用默认配置文件。</small>
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

  <v-overlay
    v-model="showConfigDrawer"
    class="config-drawer-overlay"
    location="right"
    transition="slide-x-reverse-transition"
    :scrim="true"
    @click:outside="closeConfigDrawer"
  >
    <v-card class="config-drawer-card" elevation="12">
      <div class="config-drawer-header">
        <div>
          <span class="text-h6">配置文件管理</span>
          <div v-if="configDrawerTargetId" class="text-caption text-grey">
            ID: {{ configDrawerTargetId }}
          </div>
        </div>
        <v-btn icon variant="text" @click="closeConfigDrawer">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </div>
      <v-divider></v-divider>
      <div class="config-drawer-content">
        <ConfigPage v-if="showConfigDrawer" :initial-config-id="configDrawerTargetId" />
      </div>
    </v-card>
  </v-overlay>
</template>


<script>
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';
import { getPlatformIcon, getPlatformDescription, getTutorialLink } from '@/utils/platformUtils';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import AstrBotCoreConfigWrapper from '@/components/config/AstrBotCoreConfigWrapper.vue';
import ConfigPage from '@/views/ConfigPage.vue';

export default {
  name: 'AddNewPlatform',
  components: { AstrBotConfig, AstrBotCoreConfigWrapper, ConfigPage },
  emits: ['update:show', 'show-toast', 'refresh-config'],
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

      // 平台配置文件表格（已弃用，改用 platformRoutes）
      platformConfigs: [],
      configTableHeaders: [
        { title: '与此实例关联的配置文件 ID', key: 'name', sortable: false },
        { title: '在此实例下的应用范围', key: 'scope', sortable: false },
      ],

      // 平台路由表
      platformRoutes: [],
      routeTableHeaders: [
        { title: '消息会话来源(消息类型:会话 ID)', key: 'source', sortable: false, width: '60%' },
        { title: '使用配置文件', key: 'configId', sortable: false, width: '20%' },
        { title: '操作', key: 'actions', sortable: false, align: 'center', width: '20%' },
      ],
      messageTypeOptions: [
        { label: '全部消息', value: '*' },
        { label: '群组消息(GroupMessage)', value: 'GroupMessage' },
        { label: '私聊消息(FriendMessage)', value: 'FriendMessage' },
      ],
      isEditingRoutes: false, // 编辑模式开关

      // ID冲突确认对话框
      showIdConflictDialog: false,
      conflictId: '',
      idConflictResolve: null,

      // OneBot Empty Token Warning #2639
      showOneBotEmptyTokenWarnDialog: false,
      oneBotEmptyTokenWarningResolve: null,

      loading: false,

      showConfigSection: false,

      // 配置抽屉
      showConfigDrawer: false,
      configDrawerTargetId: null,

      // 保存更新前的平台 ID，防止用户修改 ID 后丢失原始定位
      originalUpdatingPlatformId: null,
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

      if (!this.isPlatformIdValid(this.selectedPlatformConfig?.id)) {
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
          this.originalUpdatingPlatformId = newConfig.id;
          this.getPlatformConfigs(newConfig.id);
        }
      },
      immediate: true
    },
    showConfigSection(newValue) {
      if (newValue && !this.updatingMode && this.aBConfigRadioVal === '0') {
        this.getConfigForPreview(this.selectedAbConfId);
      }
      if (newValue) {
        this.$nextTick(() => {
          this.scrollDialogToBottom();
        });
      }
    },
    // 监听编辑模式变化，自动展开配置文件部分
    updatingMode: {
      handler(newValue) {
        if (newValue) {
          this.showConfigSection = true;
          // 编辑模式下默认不开启路由编辑模式，用户需要手动点击
          this.isEditingRoutes = false;
        }
      },
      immediate: true
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
      this.isEditingRoutes = false; // 重置编辑模式

      this.showConfigDrawer = false;
      this.configDrawerTargetId = null;

      this.originalUpdatingPlatformId = null;
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
    openConfigDrawer(configId) {
      const targetId = configId || 'default';

      if (configId && this.configInfoList.findIndex(c => c.id === configId) === -1) {
        this.showError('目标配置文件不存在，已打开配置页面以便检查。');
      }

      this.configDrawerTargetId = targetId;
      this.showConfigDrawer = true;
    },
    closeConfigDrawer() {
      this.showConfigDrawer = false;
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
    async updatePlatform() {
      const id = this.originalUpdatingPlatformId || this.updatingPlatformConfig.id;
      if (!id) {
        this.loading = false;
        this.showError('更新失败，缺少平台 ID。');
        return;
      }

      if (!this.isPlatformIdValid(id)) {
        this.loading = false;
        this.showError(this.tm('dialog.invalidPlatformId'));
        return;
      }

      try {
        // 更新平台配置
        let resp = await axios.post('/api/config/platform/update', {
          id: id,
          config: this.updatingPlatformConfig
        })

        if (resp.data.status === 'error') {
          throw new Error(resp.data.message || '平台更新失败');
        }
        
        // 同时更新路由表
        await this.saveRoutesInternal();

        this.loading = false;
        this.showDialog = false;
        this.resetForm();
        this.$emit('refresh-config');
        this.showSuccess('更新成功');
      } catch (err) {
        this.loading = false;
        this.showError(err.response?.data?.message || err.message);
      }
    },
    async savePlatform() {
      if (!this.isPlatformIdValid(this.selectedPlatformConfig?.id)) {
        this.loading = false;
        this.showError(this.tm('dialog.invalidPlatformId'));
        return;
      }

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

      let configId = null;

      // 第一步：创建或获取配置文件ID
      if (this.aBConfigRadioVal === '0') {
        // 使用现有配置文件
        configId = this.selectedAbConfId;
      } else if (this.aBConfigRadioVal === '1') {
        // 创建新配置文件
        configId = await this.createNewConfigFile(this.selectedAbConfId);
      }

      if (!configId) {
        throw new Error('无法获取配置文件ID');
      }

      // 第二步：统一更新路由表
      await this.updateRoutingTable(newUmop, configId);
    },

    async updateRoutingTable(umop, configId) {
      try {
        await axios.post('/api/config/umo_abconf_route/update', {
          umo: umop,
          conf_id: configId
        });

        console.log(`成功更新路由表: ${umop} -> ${configId}`);
      } catch (err) {
        console.error('更新路由表失败:', err);
        throw new Error(`更新路由表失败: ${err.response?.data?.message || err.message}`);
      }
    },

    async createNewConfigFile(configName) {
      try {
        // 准备配置数据，如果是创建模式且有新配置数据，使用用户填写的配置
        const configData = this.aBConfigRadioVal === '1' && this.newConfigData
          ? this.newConfigData
          : undefined;

        // 创建新的配置文件（不传入umop）
        const createRes = await axios.post('/api/config/abconf/new', {
          name: configName,
          config: configData  // 传入用户配置的数据
        });

        const newConfigId = createRes.data.data.conf_id;
        console.log(`成功创建新配置文件 ${configName}，ID: ${newConfigId}`);

        return newConfigId;
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

    isPlatformIdValid(id) {
      if (!id) {
        return false;
      }
      return !/[!:]/.test(id);
    },

    // 获取该平台适配器使用的所有配置文件（新版本：直接操作路由表）
    async getPlatformConfigs(platformId) {
      if (!platformId) {
        this.platformRoutes = [];
        return;
      }

      try {
        // 获取路由表 (UMOP -> conf_id)
        const routesRes = await axios.get('/api/config/umo_abconf_routes');
        const routingTable = routesRes.data.data.routing;

        // 过滤出属于该平台的路由，并保持顺序
        const routes = [];
        for (const [umop, confId] of Object.entries(routingTable)) {
          if (this.isUmopMatchPlatform(umop, platformId)) {
            const parts = umop.split(':');
            if (parts.length === 3) {
              routes.push({
                umop: umop,
                originalUmop: umop, // 保存原始 UMOP 用于更新时查找
                messageType: parts[1] === '' || parts[1] === '*' ? '*' : parts[1],
                sessionId: parts[2] === '' || parts[2] === '*' ? '*' : parts[2],
                configId: confId
              });
            }
          }
        }

        this.platformRoutes = routes;

        // 如果没有路由，添加一个默认的空路由供用户编辑
        if (this.platformRoutes.length === 0) {
          this.platformRoutes.push({
            umop: null,
            originalUmop: null,
            messageType: '*',
            sessionId: '*',
            configId: 'default'
          });
        }
      } catch (err) {
        console.error('获取平台路由配置失败:', err);
        this.platformRoutes = [];
      }
    },

    // 添加新路由
    addNewRoute() {
      this.platformRoutes.push({
        umop: null,
        originalUmop: null,
        messageType: '*',
        sessionId: '*',
        configId: 'default'
      });
    },

    // 删除路由
    deleteRoute(index) {
      this.platformRoutes.splice(index, 1);
    },

    // 上移路由
    moveRouteUp(index) {
      if (index > 0) {
        const temp = this.platformRoutes[index];
        this.platformRoutes[index] = this.platformRoutes[index - 1];
        this.platformRoutes[index - 1] = temp;
        // 强制更新视图
        this.platformRoutes = [...this.platformRoutes];
      }
    },

    // 下移路由
    moveRouteDown(index) {
      if (index < this.platformRoutes.length - 1) {
        const temp = this.platformRoutes[index];
        this.platformRoutes[index] = this.platformRoutes[index + 1];
        this.platformRoutes[index + 1] = temp;
        // 强制更新视图
        this.platformRoutes = [...this.platformRoutes];
      }
    },

    // 内部保存路由表方法（不显示成功提示）
    async saveRoutesInternal() {
      const originalPlatformId = this.originalUpdatingPlatformId || this.updatingPlatformConfig?.id;
      const newPlatformId = this.updatingPlatformConfig?.id || originalPlatformId;

      if (!originalPlatformId && !newPlatformId) {
        throw new Error('无法获取平台 ID');
      }

      try {
        // 获取完整的路由表
        const routesRes = await axios.get('/api/config/umo_abconf_routes');
        const fullRoutingTable = routesRes.data.data.routing;

        // 删除该平台的所有旧路由
        for (const umop in fullRoutingTable) {
          if (
            (originalPlatformId && this.isUmopMatchPlatform(umop, originalPlatformId)) ||
            (newPlatformId && this.isUmopMatchPlatform(umop, newPlatformId))
          ) {
            delete fullRoutingTable[umop];
          }
        }

        // 添加新路由（按顺序）
        for (const route of this.platformRoutes) {
          const messageType = route.messageType === '*' ? '*' : route.messageType;
          const sessionId = route.sessionId === '*' ? '*' : route.sessionId;
          const platformIdForRoute = newPlatformId || originalPlatformId;
          const newUmop = `${platformIdForRoute}:${messageType}:${sessionId}`;

          if (route.configId) {
            fullRoutingTable[newUmop] = route.configId;
          }
        }

        // 使用 update_all 更新整个路由表
        await axios.post('/api/config/umo_abconf_route/update_all', {
          routing: fullRoutingTable
        });
      } catch (err) {
        console.error('保存路由表失败:', err);
        throw new Error(`保存路由表失败: ${err.response?.data?.message || err.message}`);
      }
    },

    // 切换编辑模式
    toggleEditMode() {
      this.isEditingRoutes = !this.isEditingRoutes;
    },
    toggleConfigSection() {
      this.showConfigSection = !this.showConfigSection;
    },

    // 根据配置文件ID获取名称
    getConfigName(configId) {
      const config = this.configInfoList.find(c => c.id === configId);
      return config ? config.name : configId;
    },

    isUmopMatchPlatform(umop, platformId) {
      if (!umop) return false;
      const parts = umop.split(':');
      if (parts.length !== 3) return false;
      const platform = parts[0];
      return platform === platformId || platform === '' || platform === '*';
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

    toggleShowConfigSection() {
      this.showConfigSection = false;
      this.showConfigSection = true;
    },

    prepareData() {
      this.getConfigInfoList();
      this.getConfigForPreview(this.selectedAbConfId);
      if (this.updatingMode && this.updatingPlatformConfig && this.updatingPlatformConfig.id) {
        this.getPlatformConfigs(this.updatingPlatformConfig.id);
      }
    },
    scrollDialogToBottom() {
      const containerRef = this.$refs.dialogScrollContainer;
      const el = containerRef?.$el || containerRef;
      if (!el) {
        return;
      }
      const scrollOptions = { top: el.scrollHeight, behavior: 'smooth' };
      if (typeof el.scrollTo === 'function') {
        el.scrollTo(scrollOptions);
      } else {
        el.scrollTop = el.scrollHeight;
      }
    }

  },
}
</script>

<style>
.v-select__selection-text {
  font-size: 12px;
}

.config-drawer-overlay {
  align-items: stretch;
  justify-content: flex-end;
}

.config-drawer-card {
  width: clamp(320px, 60vw, 820px);
  height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  margin: 16px;
}

.config-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px 20px;
}

.config-drawer-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px 16px 24px 16px;
}
</style>
