<template>
  <div class="provider-page">
    <v-container fluid class="pa-0">
      <!-- 页面标题 -->
      <v-row>
        <v-col cols="12">
          <h1 class="text-h4 font-weight-bold mb-2">
            <v-icon size="x-large" color="primary" class="me-2">mdi-creation</v-icon>服务提供商管理
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-4">
            管理AI服务提供商，连接到不同的大语言模型
          </p>
        </v-col>
      </v-row>

      <!-- 服务提供商部分 -->
      <v-card class="mb-6" elevation="2">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon color="primary" class="me-2">mdi-api</v-icon>
          <span class="text-h6">服务提供商</span>
          <v-chip color="info" size="small" class="ml-2">{{ config_data.provider?.length || 0 }}</v-chip>
          <v-spacer></v-spacer>
          <v-menu>
            <template v-slot:activator="{ props }">
              <v-btn color="primary" prepend-icon="mdi-plus" variant="tonal" v-bind="props">
                新增服务提供商
              </v-btn>
            </template>
            <v-list @update:selected="addFromDefaultConfigTmpl($event)">
              <v-list-item 
                v-for="(item, index) in metadata['provider_group']?.metadata?.provider?.config_template || {}" 
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
            :items="config_data.provider || []"
            title-field="id" 
            enabled-field="enable"
            empty-icon="mdi-api-off"
            empty-text="暂无服务提供商，点击 新增服务提供商 添加"
            @toggle-enabled="providerStatusChange"
            @delete="deleteProvider"
            @edit="configExistingProvider"
          >
            <template v-slot:item-details="{ item }">
              <div class="d-flex align-center mb-2">
                <v-icon size="small" color="grey" class="me-2">mdi-tag</v-icon>
                <span class="text-caption text-medium-emphasis">
                  提供商类型: 
                  <v-chip size="x-small" color="primary" class="ml-1">{{ item.type }}</v-chip>
                </span>
              </div>
              <div v-if="item.api_base" class="d-flex align-center mb-2">
                <v-icon size="small" color="grey" class="me-2">mdi-web</v-icon>
                <span class="text-caption text-medium-emphasis text-truncate" :title="item.api_base">
                  API Base: {{ item.api_base }}
                </span>
              </div>
              <div v-if="item.api_key" class="d-flex align-center">
                <v-icon size="small" color="grey" class="me-2">mdi-key</v-icon>
                <span class="text-caption text-medium-emphasis">API Key: ••••••••</span>
              </div>
            </template>
          </item-card-grid>
        </v-card-text>
      </v-card>

      <!-- 日志部分 -->
      <v-card elevation="2">
        <v-card-title class="d-flex align-center py-3 px-4">
          <v-icon color="primary" class="me-2">mdi-console-line</v-icon>
          <span class="text-h6">服务日志</span>
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
    <v-dialog v-model="showProviderCfg" width="900" persistent>
      <v-card>
        <v-card-title class="bg-primary text-white py-3">
          <v-icon color="white" class="me-2">{{ updatingMode ? 'mdi-pencil' : 'mdi-plus' }}</v-icon>
          <span>{{ updatingMode ? '编辑' : '新增' }} {{ newSelectedProviderName }} 服务提供商</span>
        </v-card-title>
        
        <v-card-text class="py-4">
          <AstrBotConfig 
            :iterable="newSelectedProviderConfig"
            :metadata="metadata['provider_group']?.metadata"
            metadataKey="provider" 
          />
        </v-card-text>
        
        <v-divider></v-divider>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="showProviderCfg = false" :disabled="loading">
            取消
          </v-btn>
          <v-btn color="primary" @click="newProvider" :loading="loading">
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

export default {
  name: 'ProviderPage',
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
      showProviderCfg: false,

      newSelectedProviderName: '',
      newSelectedProviderConfig: {},
      updatingMode: false,

      loading: false,

      save_message_snack: false,
      save_message: "",
      save_message_success: "success",

      showConsole: false,
    }
  },

  mounted() {
    this.getConfig();
  },

  methods: {
    getConfig() {
      axios.get('/api/config/get').then((res) => {
        this.config_data = res.data.data.config;
        this.fetched = true
        this.metadata = res.data.data.metadata;
      }).catch((err) => {
        this.showError(err.response?.data?.message || err.message);
      });
    },

    addFromDefaultConfigTmpl(index) {
      this.newSelectedProviderName = index[0];
      this.showProviderCfg = true;
      this.updatingMode = false;
      this.newSelectedProviderConfig = JSON.parse(JSON.stringify(
        this.metadata['provider_group']?.metadata?.provider?.config_template[index[0]] || {}
      ));
    },

    configExistingProvider(provider) {
      this.newSelectedProviderName = provider.id;
      this.newSelectedProviderConfig = {};

      // 比对默认配置模版，看看是否有更新
      let templates = this.metadata['provider_group']?.metadata?.provider?.config_template || {};
      let defaultConfig = {};
      for (let key in templates) {
        if (templates[key]?.type === provider.type) {
          defaultConfig = templates[key];
          break;
        }
      }
      
      const mergeConfigWithOrder = (target, source, reference) => {
        // 首先复制所有source中的属性到target
        if (source && typeof source === 'object' && !Array.isArray(source)) {
          for (let key in source) {
            if (source.hasOwnProperty(key)) {
              if (typeof source[key] === 'object' && source[key] !== null) {
                target[key] = Array.isArray(source[key]) ? [...source[key]] : {...source[key]};
              } else {
                target[key] = source[key];
              }
            }
          }
        }
        
        // 然后根据reference的结构添加或覆盖属性
        for (let key in reference) {
          if (typeof reference[key] === 'object' && reference[key] !== null) {
            if (!(key in target)) {
              target[key] = Array.isArray(reference[key]) ? [] : {};
            }
            mergeConfigWithOrder(
              target[key], 
              source && source[key] ? source[key] : {}, 
              reference[key]
            );
          } else if (!(key in target)) {
            // 只有当target中不存在该键时才从reference复制
            target[key] = reference[key];
          }
        }
      };
      
      if (defaultConfig) {
        mergeConfigWithOrder(this.newSelectedProviderConfig, provider, defaultConfig);
      }

      this.showProviderCfg = true;
      this.updatingMode = true;
    },

    newProvider() {
      this.loading = true;
      if (this.updatingMode) {
        axios.post('/api/config/provider/update', {
          id: this.newSelectedProviderName,
          config: this.newSelectedProviderConfig
        }).then((res) => {
          this.loading = false;
          this.showProviderCfg = false;
          this.getConfig();
          this.showSuccess(res.data.message || "更新成功!");
        }).catch((err) => {
          this.loading = false;
          this.showError(err.response?.data?.message || err.message);
        });
        this.updatingMode = false;
      } else {
        axios.post('/api/config/provider/new', this.newSelectedProviderConfig).then((res) => {
          this.loading = false;
          this.showProviderCfg = false;
          this.getConfig();
          this.showSuccess(res.data.message || "添加成功!");
        }).catch((err) => {
          this.loading = false;
          this.showError(err.response?.data?.message || err.message);
        });
      }
    },

    deleteProvider(provider) {
      if (confirm(`确定要删除服务提供商 ${provider.id} 吗?`)) {
        axios.post('/api/config/provider/delete', { id: provider.id }).then((res) => {
          this.getConfig();
          this.showSuccess(res.data.message || "删除成功!");
        }).catch((err) => {
          this.showError(err.response?.data?.message || err.message);
        });
      }
    },

    providerStatusChange(provider) {
      provider.enable = !provider.enable; // 切换状态
      
      axios.post('/api/config/provider/update', {
        id: provider.id,
        config: provider
      }).then((res) => {
        this.getConfig();
        this.showSuccess(res.data.message || "状态更新成功!");
      }).catch((err) => {
        provider.enable = !provider.enable; // 发生错误时回滚状态
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
.provider-page {
  padding: 20px;
  padding-top: 8px;
}
</style>