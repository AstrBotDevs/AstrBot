<template>
  <div class="platform-page">
    <v-container fluid class="pa-0">
      <!-- 页面标题 -->
      <v-row>
        <v-col cols="12">
          <h1 class="text-h4 font-weight-bold mb-2">
            <v-icon size="x-large" color="primary" class="me-2">mdi-connection</v-icon>平台适配器管理
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-4">
            管理机器人的平台适配器，连接到不同的聊天平台
          </p>
        </v-col>
      </v-row>

      <!-- 平台适配器部分 -->
      <v-card class="mb-6" elevation="2">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon color="primary" class="me-2">mdi-apps</v-icon>
          <span class="text-h6">平台适配器</span>
          <v-chip color="info" size="small" class="ml-2">{{ config_data.platform?.length || 0 }}</v-chip>
          <v-spacer></v-spacer>
          <v-menu>
            <template v-slot:activator="{ props }">
              <v-btn color="primary" prepend-icon="mdi-plus" variant="tonal" v-bind="props">
                新增适配器
              </v-btn>
            </template>
            <v-list @update:selected="addFromDefaultConfigTmpl($event)">
              <v-list-item 
                v-for="(item, index) in metadata['platform_group']?.metadata?.platform?.config_template || {}" 
                :key="index" 
                rounded="xl" 
                :value="index"
              >
                <v-list-item-title>{{ index }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>
        </v-card-title>

        <v-divider></v-divider>

        <v-card-text class="px-4 py-3">
          <item-card-grid
            :items="config_data.platform || []"
            title-field="id" 
            enabled-field="enable"
            empty-icon="mdi-connection"
            empty-text="暂无平台适配器，点击 新增适配器 添加"
            @toggle-enabled="platformStatusChange"
            @delete="deletePlatform"
            @edit="editPlatform"
          >
            <template v-slot:item-details="{ item }">
              <div class="d-flex align-center mb-2">
                <v-icon size="small" color="grey" class="me-2">mdi-tag</v-icon>
                <span class="text-caption text-medium-emphasis">
                  适配器类型: 
                  <v-chip size="x-small" color="primary" class="ml-1">{{ item.type }}</v-chip>
                </span>
              </div>
              <div v-if="item.token" class="d-flex align-center mb-2">
                <v-icon size="small" color="grey" class="me-2">mdi-key</v-icon>
                <span class="text-caption text-medium-emphasis">Token: ••••••••</span>
              </div>
              <div v-if="item.description" class="d-flex align-center">
                <v-icon size="small" color="grey" class="me-2">mdi-information-outline</v-icon>
                <span class="text-caption text-medium-emphasis text-truncate">{{ item.description }}</span>
              </div>
            </template>
          </item-card-grid>
        </v-card-text>
      </v-card>

      <!-- 日志部分 -->
      <v-card elevation="2">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon color="primary" class="me-2">mdi-console-line</v-icon>
          <span class="text-h6">平台日志</span>
          <v-spacer></v-spacer>
          <v-btn variant="text" color="primary" @click="showConsole = !showConsole">
            {{ showConsole ? '收起' : '展开' }}
            <v-icon>{{ showConsole ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-expand-transition>
          <v-card-text class="pa-0" v-if="showConsole">
            <ConsoleDisplayer style="background-color: #1e1e1e; height: 300px; border-radius: 0"></ConsoleDisplayer>
          </v-card-text>
        </v-expand-transition>
      </v-card>
    </v-container>

    <!-- 配置对话框 -->
    <v-dialog v-model="showPlatformCfg" persistent>
      <v-card>
        <v-card-title class="bg-primary text-white py-3">
          <v-icon color="white" class="me-2">{{ updatingMode ? 'mdi-pencil' : 'mdi-plus' }}</v-icon>
          <span>{{ updatingMode ? '编辑' : '新增' }} {{ newSelectedPlatformName }} 平台适配器</span>
        </v-card-title>
        
        <v-card-text class="py-4">
          <v-row>
            <v-col cols="12" md="8">
              <AstrBotConfig :iterable="newSelectedPlatformConfig"
                :metadata="metadata['platform_group']?.metadata"
                metadataKey="platform" />
            </v-col>
            <v-col cols="12" md="4">
              <v-btn :loading="iframeLoading" @click="refreshIframe" variant="tonal" color="primary" style="float: right;">
                <v-icon>mdi-refresh</v-icon>
                刷新
              </v-btn>
              <iframe v-show="!iframeLoading"
                :src="store.getTutorialLink(newSelectedPlatformConfig.type)"
                @load="iframeLoading = false" style="width: 100%; border: none; height: 100%; min-height: 400px;">
              </iframe>
            </v-col>
          </v-row>
        </v-card-text>
        
        <v-divider></v-divider>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showPlatformCfg = false" :disabled="loading">
            取消
          </v-btn>
          <v-btn color="primary" @click="newPlatform" :loading="loading">
            保存
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar :timeout="3000" elevation="24" :color="save_message_success" v-model="save_message_snack"
      location="top">
      {{ save_message }}
    </v-snackbar>
    
    <WaitingForRestart ref="wfr"></WaitingForRestart>
  </div>
</template>

<script>
import axios from 'axios';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import ItemCardGrid from '@/components/shared/ItemCardGrid.vue';
import { useCommonStore } from '@/stores/common';

export default {
  name: 'PlatformPage',
  components: {
    AstrBotConfig,
    WaitingForRestart,
    ConsoleDisplayer,
    ItemCardGrid
  },
  data() {
    return {
      config_data: {},
      fetched: false,
      metadata: {},
      showPlatformCfg: false,

      newSelectedPlatformName: '',
      newSelectedPlatformConfig: {},
      updatingMode: false,

      loading: false,

      save_message_snack: false,
      save_message: "",
      save_message_success: "success",

      showConsole: false,
      iframeLoading: true,

      store: useCommonStore()
    }
  },

  mounted() {
    this.getConfig();
  },

  methods: {
    refreshIframe() {
      this.iframeLoading = true;
      const iframe = document.querySelector('iframe');
      iframe.src = iframe.src + '?t=' + new Date().getTime();
    },
    
    getConfig() {
      axios.get('/api/config/get').then((res) => {
        this.config_data = res.data.data.config;
        this.fetched = true
        this.metadata = res.data.data.metadata;
      }).catch((err) => {
        this.showError(err);
      });
    },

    addFromDefaultConfigTmpl(index) {
      this.newSelectedPlatformName = index[0];
      this.showPlatformCfg = true;
      this.updatingMode = false;
      this.newSelectedPlatformConfig = JSON.parse(JSON.stringify(
        this.metadata['platform_group']?.metadata?.platform?.config_template[index[0]] || {}
      ));
    },

    editPlatform(platform) {
      this.newSelectedPlatformName = platform.id;
      this.newSelectedPlatformConfig = JSON.parse(JSON.stringify(platform));
      this.updatingMode = true;
      this.showPlatformCfg = true;
    },

    newPlatform() {
      this.loading = true;
      if (this.updatingMode) {
        axios.post('/api/config/platform/update', {
          id: this.newSelectedPlatformName,
          config: this.newSelectedPlatformConfig
        }).then((res) => {
          this.loading = false;
          this.showPlatformCfg = false;
          this.getConfig();
          this.$refs.wfr.check();
          this.showSuccess(res.data.message || "更新成功!");
        }).catch((err) => {
          this.loading = false;
          this.showError(err.response?.data?.message || err.message);
        });
        this.updatingMode = false;
      } else {
        axios.post('/api/config/platform/new', this.newSelectedPlatformConfig).then((res) => {
          this.loading = false;
          this.showPlatformCfg = false;
          this.getConfig();
          this.showSuccess(res.data.message || "添加成功!");
        }).catch((err) => {
          this.loading = false;
          this.showError(err.response?.data?.message || err.message);
        });
      }
    },

    deletePlatform(platform) {
      if (confirm(`确定要删除平台适配器 ${platform.id} 吗?`)) {
        axios.post('/api/config/platform/delete', { id: platform.id }).then((res) => {
          this.getConfig();
          this.$refs.wfr.check();
          this.showSuccess(res.data.message || "删除成功!");
        }).catch((err) => {
          this.showError(err.response?.data?.message || err.message);
        });
      }
    },

    platformStatusChange(platform) {
      platform.enable = !platform.enable; // 切换状态
      
      axios.post('/api/config/platform/update', {
        id: platform.id,
        config: platform
      }).then((res) => {
        this.getConfig();
        this.$refs.wfr.check();
        this.showSuccess(res.data.message || "状态更新成功!");
      }).catch((err) => {
        platform.enable = !platform.enable; // 发生错误时回滚状态
        this.showError(err.response?.data?.message || err.message);
      });
    },
    
    showSuccess(message) {
      this.save_message = message;
      this.save_message_success = "success";
      this.save_message_snack = true;
    },
    
    showError(message) {
      this.save_message = message;
      this.save_message_success = "error";
      this.save_message_snack = true;
    }
  }
}
</script>

<style scoped>
.platform-page {
  padding: 20px;
  padding-top: 8px;
}
</style>