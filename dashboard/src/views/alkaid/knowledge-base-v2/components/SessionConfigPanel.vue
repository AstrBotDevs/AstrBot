<template>
  <div class="session-config-panel">
    <!-- 说明提示 -->
    <v-alert type="info" variant="tonal" class="mb-4" border="start">
      <div class="text-subtitle-2 mb-2">
        <v-icon start>mdi-information-outline</v-icon>
        {{ tm('info.title') }}
      </div>
      <p class="text-caption">{{ tm('info.description') }}</p>
      <ul class="text-caption mt-2">
        <li>{{ tm('info.platformLevel') }}</li>
        <li>{{ tm('info.sessionLevel') }}</li>
      </ul>
    </v-alert>

    <!-- 操作按钮组 -->
    <div class="d-flex justify-space-between align-center mb-4">
      <h3>{{ tm('list.title') }}</h3>
      <div class="d-flex gap-2">
        <v-btn
          prepend-icon="mdi-refresh"
          variant="text"
          @click="loadConfigs"
          :loading="loading"
        >
          {{ tm('list.refresh') }}
        </v-btn>
        <v-btn
          prepend-icon="mdi-plus"
          variant="tonal"
          color="primary"
          @click="openCreateDialog"
        >
          {{ tm('list.add') }}
        </v-btn>
      </div>
    </div>

    <!-- 配置列表 -->
    <v-data-table
      :headers="headers"
      :items="configs"
      :loading="loading"
      items-per-page="10"
      class="elevation-1"
    >
      <template v-slot:item.scope="{ item }">
        <v-chip
          :color="item.scope === 'platform' ? 'primary' : 'secondary'"
          size="small"
          variant="tonal"
        >
          <v-icon start size="small">
            {{ item.scope === 'platform' ? 'mdi-desktop-classic' : 'mdi-chat' }}
          </v-icon>
          {{ item.scope === 'platform' ? tm('scope.platform') : tm('scope.session') }}
        </v-chip>
      </template>

      <template v-slot:item.scope_id="{ item }">
        <code class="scope-id-code">{{ item.scope_id }}</code>
      </template>

      <template v-slot:item.kb_ids="{ item }">
        <div class="kb-list">
          <v-chip
            v-for="kbId in (item.kb_ids || [])"
            :key="kbId"
            size="small"
            variant="outlined"
            class="mr-1 mb-1"
          >
            <v-icon start size="small">mdi-book-open-variant</v-icon>
            {{ getKBName(kbId) }}
          </v-chip>
          <span v-if="!item.kb_ids || item.kb_ids.length === 0" class="text-medium-emphasis">
            {{ tm('list.noKB') }}
          </span>
        </div>
      </template>

      <template v-slot:item.created_at="{ item }">
        {{ formatDate(item.created_at) }}
      </template>

      <template v-slot:item.actions="{ item }">
        <v-btn
          variant="text"
          size="small"
          prepend-icon="mdi-pencil"
          @click="editConfig(item)"
        >
          {{ tm('actions.edit') }}
        </v-btn>
        <v-btn
          variant="text"
          size="small"
          color="error"
          prepend-icon="mdi-delete"
          @click="confirmDelete(item)"
        >
          {{ tm('actions.delete') }}
        </v-btn>
      </template>

      <template v-slot:no-data>
        <div class="text-center py-8">
          <v-icon size="64" color="grey-lighten-2">mdi-cog-outline</v-icon>
          <p class="text-medium-emphasis mt-4">{{ tm('empty.noConfigs') }}</p>
          <v-btn
            class="mt-2"
            variant="tonal"
            color="primary"
            prepend-icon="mdi-plus"
            @click="openCreateDialog"
          >
            {{ tm('empty.createFirst') }}
          </v-btn>
        </div>
      </template>
    </v-data-table>

    <!-- 新增/编辑配置对话框 -->
    <v-dialog v-model="showConfigDialog" max-width="700px" persistent>
      <v-card>
        <v-card-title class="d-flex align-center">
          <v-icon start>mdi-cog</v-icon>
          <span>{{ editingConfig ? tm('dialog.editTitle') : tm('dialog.addTitle') }}</span>
          <v-spacer></v-spacer>
          <v-btn variant="plain" icon @click="closeConfigDialog">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-card-text>
          <v-form ref="configForm" @submit.prevent="saveConfig">
            <!-- 配置范围选择 -->
            <v-radio-group
              v-model="configForm.scope"
              :label="tm('dialog.scopeLabel')"
              class="mb-2"
            >
              <v-radio :label="tm('scope.platform')" value="platform">
                <template v-slot:label>
                  <div class="d-flex align-center">
                    <v-icon start>mdi-desktop-classic</v-icon>
                    <span>{{ tm('scope.platform') }}</span>
                    <v-tooltip location="top">
                      <template v-slot:activator="{ props }">
                        <v-icon v-bind="props" size="small" class="ml-2">
                          mdi-information-outline
                        </v-icon>
                      </template>
                      <span>{{ tm('dialog.platformTooltip') }}</span>
                    </v-tooltip>
                  </div>
                </template>
              </v-radio>
              <v-radio :label="tm('scope.session')" value="session">
                <template v-slot:label>
                  <div class="d-flex align-center">
                    <v-icon start>mdi-chat</v-icon>
                    <span>{{ tm('scope.session') }}</span>
                    <v-tooltip location="top">
                      <template v-slot:activator="{ props }">
                        <v-icon v-bind="props" size="small" class="ml-2">
                          mdi-information-outline
                        </v-icon>
                      </template>
                      <span>{{ tm('dialog.sessionTooltip') }}</span>
                    </v-tooltip>
                  </div>
                </template>
              </v-radio>
            </v-radio-group>

            <!-- 标识输入 -->
            <v-text-field
              v-model="configForm.scope_id"
              :label="configForm.scope === 'platform' ? tm('dialog.platformIdLabel') : tm('dialog.sessionIdLabel')"
              :placeholder="configForm.scope === 'platform' ? tm('dialog.platformIdPlaceholder') : tm('dialog.sessionIdPlaceholder')"
              :hint="configForm.scope === 'platform' ? tm('dialog.platformIdHint') : tm('dialog.sessionIdHint')"
              persistent-hint
              variant="outlined"
              class="mb-4"
              required
            ></v-text-field>

            <!-- 知识库选择 -->
            <v-select
              v-model="configForm.kb_ids"
              :items="availableKBs"
              item-title="kb_name"
              item-value="kb_id"
              :label="tm('dialog.kbLabel')"
              :placeholder="tm('dialog.kbPlaceholder')"
              :hint="tm('dialog.kbHint')"
              persistent-hint
              variant="outlined"
              multiple
              chips
              closable-chips
              class="mb-2"
              required
            >
              <template v-slot:chip="{ props, item }">
                <v-chip v-bind="props" :text="item.raw.kb_name">
                  <template v-slot:prepend>
                    <span class="mr-1">{{ item.raw.emoji || '📚' }}</span>
                  </template>
                </v-chip>
              </template>

              <template v-slot:item="{ props, item }">
                <v-list-item v-bind="props">
                  <template v-slot:prepend>
                    <span class="emoji-icon">{{ item.raw.emoji || '📚' }}</span>
                  </template>
                  <v-list-item-subtitle>
                    {{ item.raw.doc_count || 0 }} 个文档 | {{ item.raw.chunk_count || 0 }} 个块
                  </v-list-item-subtitle>
                </v-list-item>
              </template>
            </v-select>

            <!-- 检索参数（可选） -->
            <v-expansion-panels class="mt-4">
              <v-expansion-panel>
                <v-expansion-panel-title>
                  <v-icon start>mdi-tune</v-icon>
                  {{ tm('dialog.advancedSettings') }}
                </v-expansion-panel-title>
                <v-expansion-panel-text>
                  <v-row>
                    <v-col cols="12" md="6">
                      <v-text-field
                        v-model.number="configForm.top_k"
                        :label="tm('dialog.topKLabel')"
                        :hint="tm('dialog.topKHint')"
                        persistent-hint
                        type="number"
                        variant="outlined"
                        min="1"
                        max="50"
                      ></v-text-field>
                    </v-col>
                    <v-col cols="12" md="6">
                      <v-switch
                        v-model="configForm.enable_rerank"
                        :label="tm('dialog.enableRerankLabel')"
                        color="primary"
                      ></v-switch>
                    </v-col>
                  </v-row>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </v-form>
        </v-card-text>

        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn @click="closeConfigDialog">{{ tm('dialog.cancel') }}</v-btn>
          <v-btn
            color="primary"
            @click="saveConfig"
            :loading="saving"
          >
            {{ tm('dialog.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="showDeleteDialog" max-width="450px">
      <v-card>
        <v-card-title class="text-h5">{{ tm('delete.title') }}</v-card-title>
        <v-card-text>
          <p>{{ tm('delete.confirmText') }}</p>
          <v-alert type="warning" variant="tonal" class="mt-4" density="compact">
            {{ tm('delete.warning') }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn @click="showDeleteDialog = false">{{ tm('delete.cancel') }}</v-btn>
          <v-btn color="error" @click="deleteConfig" :loading="deleting">
            {{ tm('delete.delete') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script>
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';

export default {
  name: 'SessionConfigPanel',
  setup() {
    const { tm } = useModuleI18n('features/alkaid/knowledge-base-v2/session-config');
    return { tm };
  },
  data() {
    return {
      configs: [],
      availableKBs: [],
      loading: false,
      saving: false,
      deleting: false,
      showConfigDialog: false,
      showDeleteDialog: false,
      editingConfig: null,
      deleteTarget: null,
      configForm: {
        scope: 'session',
        scope_id: '',
        kb_ids: [],
        top_k: 5,
        enable_rerank: true,
      },
      headers: [
        { title: '范围', key: 'scope', width: '12%' },
        { title: '标识', key: 'scope_id', width: '23%' },
        { title: '关联知识库', key: 'kb_ids', width: '35%' },
        { title: '创建时间', key: 'created_at', width: '15%' },
        { title: '操作', key: 'actions', width: '15%', sortable: false },
      ],
      snackbar: {
        show: false,
        text: '',
        color: 'success',
      },
    };
  },
  mounted() {
    this.loadConfigs();
    this.loadAvailableKBs();
  },
  methods: {
    async loadConfigs() {
      this.loading = true;
      try {
        const response = await axios.get('/api/kb/session/config/list');
        if (response.data.status === 'ok') {
          this.configs = response.data.data.items || [];
        } else {
          this.showSnackbar(response.data.message || this.tm('messages.loadFailed'), 'error');
        }
      } catch (error) {
        console.error('Error loading configs:', error);
        this.showSnackbar(this.tm('messages.loadError'), 'error');
      } finally {
        this.loading = false;
      }
    },
    async loadAvailableKBs() {
      try {
        const response = await axios.get('/api/kb/list');
        if (response.data.status === 'ok') {
          this.availableKBs = response.data.data.items || [];
        }
      } catch (error) {
        console.error('Error loading KBs:', error);
      }
    },
    getKBName(kbId) {
      const kb = this.availableKBs.find((k) => k.kb_id === kbId);
      return kb ? kb.kb_name : kbId;
    },
    formatDate(dateString) {
      if (!dateString) return '';
      return new Date(dateString).toLocaleString();
    },
    openCreateDialog() {
      this.editingConfig = null;
      this.resetForm();
      this.showConfigDialog = true;
    },
    editConfig(config) {
      this.editingConfig = config;
      this.configForm = {
        scope: config.scope,
        scope_id: config.scope_id,
        kb_ids: config.kb_ids || [],
        top_k: config.top_k || 5,
        enable_rerank: config.enable_rerank !== undefined ? config.enable_rerank : true,
      };
      this.showConfigDialog = true;
    },
    closeConfigDialog() {
      this.showConfigDialog = false;
      this.resetForm();
    },
    async saveConfig() {
      // 表单验证
      if (!this.configForm.scope_id || !this.configForm.scope_id.trim()) {
        this.showSnackbar(this.tm('messages.scopeIdRequired'), 'warning');
        return;
      }

      if (!this.configForm.kb_ids || this.configForm.kb_ids.length === 0) {
        this.showSnackbar(this.tm('messages.kbIdsRequired'), 'warning');
        return;
      }

      this.saving = true;
      try {
        const payload = {
          scope: this.configForm.scope,
          scope_id: this.configForm.scope_id,
          kb_ids: this.configForm.kb_ids,
          top_k: this.configForm.top_k,
          enable_rerank: this.configForm.enable_rerank,
        };

        const response = await axios.post('/api/kb/session/config/set', payload);

        if (response.data.status === 'ok') {
          this.showSnackbar(
            this.editingConfig ? this.tm('messages.updateSuccess') : this.tm('messages.createSuccess')
          );
          this.closeConfigDialog();
          this.loadConfigs();
        } else {
          this.showSnackbar(response.data.message || this.tm('messages.saveFailed'), 'error');
        }
      } catch (error) {
        console.error('Error saving config:', error);
        this.showSnackbar(this.tm('messages.saveError'), 'error');
      } finally {
        this.saving = false;
      }
    },
    confirmDelete(config) {
      this.deleteTarget = config;
      this.showDeleteDialog = true;
    },
    async deleteConfig() {
      if (!this.deleteTarget) return;

      this.deleting = true;
      try {
        const response = await axios.post('/api/kb/session/config/delete', {
          scope: this.deleteTarget.scope,
          scope_id: this.deleteTarget.scope_id,
        });

        if (response.data.status === 'ok') {
          this.showSnackbar(this.tm('messages.deleteSuccess'));
          this.showDeleteDialog = false;
          this.loadConfigs();
        } else {
          this.showSnackbar(response.data.message || this.tm('messages.deleteFailed'), 'error');
        }
      } catch (error) {
        console.error('Error deleting config:', error);
        this.showSnackbar(this.tm('messages.deleteError'), 'error');
      } finally {
        this.deleting = false;
      }
    },
    resetForm() {
      this.editingConfig = null;
      this.configForm = {
        scope: 'session',
        scope_id: '',
        kb_ids: [],
        top_k: 5,
        enable_rerank: true,
      };
    },
    showSnackbar(text, color = 'success') {
      this.snackbar.text = text;
      this.snackbar.color = color;
      this.snackbar.show = true;
    },
  },
};
</script>

<style scoped>
.kb-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  max-width: 400px;
}

.scope-id-code {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 2px 8px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 0.85rem;
}

.emoji-icon {
  font-size: 24px;
  margin-right: 8px;
}
</style>
