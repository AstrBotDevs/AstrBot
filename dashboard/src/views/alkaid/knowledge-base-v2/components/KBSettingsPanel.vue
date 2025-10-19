<template>
  <div class="kb-settings-panel">
    <v-form @submit.prevent="saveSettings">
      <!-- 基本信息 -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title>
          <v-icon start>mdi-information-outline</v-icon>
          {{ tm('basic.title') }}
        </v-card-title>
        <v-card-text>
          <v-text-field
            v-model="settings.kb_name"
            :label="tm('basic.nameLabel')"
            :placeholder="tm('basic.namePlaceholder')"
            variant="outlined"
            class="mb-2"
            required
          ></v-text-field>

          <v-textarea
            v-model="settings.description"
            :label="tm('basic.descriptionLabel')"
            :placeholder="tm('basic.descriptionPlaceholder')"
            variant="outlined"
            rows="3"
          ></v-textarea>
        </v-card-text>
      </v-card>

      <!-- 模型配置 -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title>
          <v-icon start>mdi-brain</v-icon>
          {{ tm('models.title') }}
        </v-card-title>
        <v-card-text>
          <v-select
            v-model="settings.embedding_provider_id"
            :items="embeddingProviders"
            :label="tm('models.embeddingLabel')"
            :hint="tm('models.embeddingHint')"
            persistent-hint
            variant="outlined"
            item-title="embedding_model"
            item-value="id"
            class="mb-4"
          >
            <template v-slot:item="{ props, item }">
              <v-list-item v-bind="props">
                <v-list-item-subtitle>
                  Provider ID: {{ item.raw.id }} | 维度: {{ item.raw.embedding_dimensions }}
                </v-list-item-subtitle>
              </v-list-item>
            </template>
          </v-select>

          <v-select
            v-model="settings.rerank_provider_id"
            :items="rerankProviders"
            :label="tm('models.rerankLabel')"
            :hint="tm('models.rerankHint')"
            persistent-hint
            variant="outlined"
            item-title="rerank_model"
            item-value="id"
            clearable
          >
            <template v-slot:item="{ props, item }">
              <v-list-item v-bind="props">
                <v-list-item-subtitle>
                  Provider ID: {{ item.raw.id }}
                </v-list-item-subtitle>
              </v-list-item>
            </template>
          </v-select>
        </v-card-text>
      </v-card>

      <!-- 分块参数配置 -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title>
          <v-icon start>mdi-puzzle-outline</v-icon>
          {{ tm('chunking.title') }}
        </v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="6">
              <v-text-field
                v-model.number="settings.chunk_size"
                :label="tm('chunking.chunkSizeLabel')"
                :hint="tm('chunking.chunkSizeHint')"
                persistent-hint
                type="number"
                variant="outlined"
                min="50"
                max="2000"
              ></v-text-field>
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model.number="settings.chunk_overlap"
                :label="tm('chunking.chunkOverlapLabel')"
                :hint="tm('chunking.chunkOverlapHint')"
                persistent-hint
                type="number"
                variant="outlined"
                min="0"
                :max="settings.chunk_size ? settings.chunk_size / 2 : 100"
              ></v-text-field>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 检索参数配置 -->
      <v-card variant="outlined" class="mb-4">
        <v-card-title>
          <v-icon start>mdi-magnify</v-icon>
          {{ tm('retrieval.title') }}
        </v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="4">
              <v-text-field
                v-model.number="settings.top_k_dense"
                :label="tm('retrieval.topKDenseLabel')"
                :hint="tm('retrieval.topKDenseHint')"
                persistent-hint
                type="number"
                variant="outlined"
                min="1"
                max="100"
              ></v-text-field>
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field
                v-model.number="settings.top_k_sparse"
                :label="tm('retrieval.topKSparseLabel')"
                :hint="tm('retrieval.topKSparseHint')"
                persistent-hint
                type="number"
                variant="outlined"
                min="1"
                max="100"
              ></v-text-field>
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field
                v-model.number="settings.top_m_final"
                :label="tm('retrieval.topMFinalLabel')"
                :hint="tm('retrieval.topMFinalHint')"
                persistent-hint
                type="number"
                variant="outlined"
                min="1"
                max="50"
              ></v-text-field>
            </v-col>
          </v-row>

          <v-switch
            v-model="settings.enable_rerank"
            :label="tm('retrieval.enableRerankLabel')"
            color="primary"
            class="mt-2"
          ></v-switch>
        </v-card-text>
      </v-card>

      <!-- 操作按钮 -->
      <div class="text-center">
        <v-btn
          color="primary"
          type="submit"
          :loading="saving"
          prepend-icon="mdi-content-save"
          size="large"
        >
          {{ tm('actions.save') }}
        </v-btn>
      </div>
    </v-form>

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
  name: 'KBSettingsPanel',
  props: {
    kb: {
      type: Object,
      required: true,
    },
  },
  setup() {
    const { tm } = useModuleI18n('features/alkaid/knowledge-base-v2/settings');
    return { tm };
  },
  data() {
    return {
      settings: {
        kb_name: '',
        description: '',
        embedding_provider_id: null,
        rerank_provider_id: null,
        chunk_size: 512,
        chunk_overlap: 50,
        top_k_dense: 50,
        top_k_sparse: 50,
        top_m_final: 5,
        enable_rerank: true,
      },
      embeddingProviders: [],
      rerankProviders: [],
      saving: false,
      snackbar: {
        show: false,
        text: '',
        color: 'success',
      },
    };
  },
  mounted() {
    this.loadSettings();
    this.loadProviders();
  },
  methods: {
    loadSettings() {
      this.settings = {
        kb_name: this.kb.kb_name,
        description: this.kb.description || '',
        embedding_provider_id: this.kb.embedding_provider_id,
        rerank_provider_id: this.kb.rerank_provider_id,
        chunk_size: this.kb.chunk_size || 512,
        chunk_overlap: this.kb.chunk_overlap || 50,
        top_k_dense: this.kb.top_k_dense || 50,
        top_k_sparse: this.kb.top_k_sparse || 50,
        top_m_final: this.kb.top_m_final || 5,
        enable_rerank: this.kb.enable_rerank !== undefined ? this.kb.enable_rerank : true,
      };
    },
    async loadProviders() {
      try {
        const response = await axios.get('/api/config/provider/list', {
          params: { provider_type: 'embedding,rerank' },
        });
        if (response.data.status === 'ok') {
          this.embeddingProviders = response.data.data.filter((p) => p.provider_type === 'embedding');
          this.rerankProviders = response.data.data.filter((p) => p.provider_type === 'rerank');
        }
      } catch (error) {
        console.error('Error loading providers:', error);
        this.showSnackbar(this.tm('messages.loadProvidersError'), 'error');
      }
    },
    async saveSettings() {
      // 表单验证
      if (!this.settings.kb_name || !this.settings.kb_name.trim()) {
        this.showSnackbar(this.tm('messages.nameRequired'), 'warning');
        return;
      }

      if (!this.settings.embedding_provider_id) {
        this.showSnackbar(this.tm('messages.embeddingRequired'), 'warning');
        return;
      }

      this.saving = true;
      try {
        const response = await axios.post('/api/kb/update', {
          kb_id: this.kb.kb_id,
          ...this.settings,
        });

        if (response.data.status === 'ok') {
          this.showSnackbar(this.tm('messages.saveSuccess'));
          this.$emit('updated');
        } else {
          this.showSnackbar(response.data.message || this.tm('messages.saveFailed'), 'error');
        }
      } catch (error) {
        console.error('Error saving settings:', error);
        this.showSnackbar(this.tm('messages.saveError'), 'error');
      } finally {
        this.saving = false;
      }
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
.kb-settings-panel {
  max-width: 900px;
  margin: 0 auto;
}
</style>
