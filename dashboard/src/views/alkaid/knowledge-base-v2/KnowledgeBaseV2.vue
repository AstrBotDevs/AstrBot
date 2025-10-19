<template>
  <div class="kb-v2-container">
    <!-- 警告提示 -->
    <v-alert
      v-if="showCompatibilityWarning"
      type="warning"
      variant="tonal"
      closable
      class="mb-4"
      @click:close="showCompatibilityWarning = false"
    >
      <strong>兼容性提示:</strong> 此为 AstrBot 原生知识库系统。如您已安装知识库插件,建议不要同时使用两个知识库系统,以避免配置冲突。
    </v-alert>

    <!-- 知识库列表视图 -->
    <div v-if="kbCollections.length > 0 || loading">
      <div class="d-flex align-center justify-space-between mb-4">
        <div>
          <h2>{{ tm('list.title') }}</h2>
          <small class="text-medium-emphasis">{{ tm('list.subtitle') }}</small>
        </div>
        <v-icon
          size="small"
          color="grey"
          @click="openUrl('https://astrbot.app/use/knowledge-base.html')"
        >
          mdi-information-outline
        </v-icon>
      </div>

      <!-- 操作按钮组 -->
      <div class="action-buttons mb-4">
        <v-btn prepend-icon="mdi-plus" variant="tonal" color="primary" @click="showCreateDialog = true">
          {{ tm('list.create') }}
        </v-btn>
        <v-btn prepend-icon="mdi-account-cog" variant="tonal" color="info" @click="showSessionConfigDialog = true">
          {{ tm('list.sessionConfig') }}
        </v-btn>
        <v-btn prepend-icon="mdi-refresh" variant="tonal" @click="loadKnowledgeBases" :loading="loading">
          {{ tm('list.refresh') }}
        </v-btn>
      </div>

      <!-- 知识库网格 -->
      <div v-if="loading && kbCollections.length === 0" class="text-center py-8">
        <v-progress-circular indeterminate color="primary"></v-progress-circular>
        <p class="mt-4">{{ tm('list.loading') }}</p>
      </div>

      <div v-else class="kb-grid">
        <v-card
          v-for="(kb, index) in kbCollections"
          :key="index"
          class="kb-card"
          @click="openKnowledgeBase(kb)"
          hover
        >
          <div class="book-spine"></div>
          <div class="book-content">
            <div class="kb-emoji">{{ kb.emoji || '📚' }}</div>
            <div class="kb-name">{{ kb.kb_name }}</div>
            <div class="kb-stats">
              <div class="stat-item">
                <v-icon size="small">mdi-file-document</v-icon>
                <span>{{ kb.doc_count || 0 }} {{ tm('list.documents') }}</span>
              </div>
              <div class="stat-item">
                <v-icon size="small">mdi-text-box</v-icon>
                <span>{{ kb.chunk_count || 0 }} {{ tm('list.chunks') }}</span>
              </div>
            </div>
            <div class="kb-actions">
              <v-btn
                icon
                variant="text"
                size="small"
                color="info"
                @click.stop="editKnowledgeBase(kb)"
              >
                <v-icon>mdi-pencil</v-icon>
              </v-btn>
              <v-btn
                icon
                variant="text"
                size="small"
                color="error"
                @click.stop="confirmDelete(kb)"
              >
                <v-icon>mdi-delete</v-icon>
              </v-btn>
            </div>
          </div>
        </v-card>
      </div>
    </div>

    <!-- 空状态 -->
    <div
      v-else
      class="d-flex align-center justify-center flex-column"
      style="min-height: 400px"
    >
      <v-icon size="80" color="grey-lighten-1">mdi-book-open-variant</v-icon>
      <h2 class="mt-4">{{ tm('empty.title') }}</h2>
      <p class="text-medium-emphasis mt-2">{{ tm('empty.subtitle') }}</p>
      <v-btn
        class="mt-4"
        variant="tonal"
        color="primary"
        prepend-icon="mdi-plus"
        @click="showCreateDialog = true"
      >
        {{ tm('empty.create') }}
      </v-btn>
    </div>

    <!-- 创建/编辑知识库对话框 -->
    <v-dialog v-model="showCreateDialog" max-width="600px">
      <v-card>
        <v-card-title class="d-flex align-center">
          <span class="text-h5">{{ editingKB ? tm('editDialog.title') : tm('createDialog.title') }}</span>
          <v-spacer></v-spacer>
          <v-btn variant="plain" icon @click="showCreateDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-card-text>
          <div class="text-center mb-4">
            <span class="emoji-display" @click="showEmojiPicker = true">
              {{ newKB.emoji || '📚' }}
            </span>
          </div>

          <v-form @submit.prevent="submitCreateForm">
            <v-text-field
              v-model="newKB.kb_name"
              :label="tm('createDialog.nameLabel')"
              :placeholder="tm('createDialog.namePlaceholder')"
              variant="outlined"
              required
              class="mb-2"
            ></v-text-field>

            <v-textarea
              v-model="newKB.description"
              :label="tm('createDialog.descriptionLabel')"
              :placeholder="tm('createDialog.descriptionPlaceholder')"
              variant="outlined"
              rows="3"
              class="mb-2"
            ></v-textarea>

            <v-select
              v-model="newKB.embedding_provider_id"
              :items="embeddingProviderConfigs"
              :item-props="embeddingModelProps"
              :label="tm('createDialog.embeddingModelLabel')"
              variant="outlined"
              density="comfortable"
              class="mb-2"
            ></v-select>

            <v-select
              v-model="newKB.rerank_provider_id"
              :items="rerankProviderConfigs"
              :item-props="rerankModelProps"
              :label="tm('createDialog.rerankModelLabel')"
              variant="outlined"
              density="comfortable"
              clearable
            ></v-select>

            <small class="text-medium-emphasis">{{ tm('createDialog.tips') }}</small>
          </v-form>
        </v-card-text>

        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="showCreateDialog = false">
            {{ tm('createDialog.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="text"
            @click="submitCreateForm"
            :loading="creating"
          >
            {{ editingKB ? tm('editDialog.save') : tm('createDialog.create') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Emoji 选择器对话框 -->
    <v-dialog v-model="showEmojiPicker" max-width="500px">
      <v-card>
        <v-card-title>{{ tm('emojiPicker.title') }}</v-card-title>
        <v-card-text>
          <div class="emoji-picker">
            <div v-for="(category, catIndex) in emojiCategories" :key="catIndex" class="mb-4">
              <div class="text-subtitle-2 mb-2">{{ tm(`emojiPicker.categories.${category.key}`) }}</div>
              <div class="emoji-grid">
                <div
                  v-for="(emoji, emojiIndex) in category.emojis"
                  :key="emojiIndex"
                  class="emoji-item"
                  @click="selectEmoji(emoji)"
                >
                  {{ emoji }}
                </div>
              </div>
            </div>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" variant="text" @click="showEmojiPicker = false">
            {{ tm('emojiPicker.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 知识库详情对话框 -->
    <v-dialog v-model="showDetailDialog" max-width="1200px" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center">
          <div class="emoji-sm me-2">{{ currentKB.emoji || '📚' }}</div>
          <span>{{ currentKB.kb_name }}</span>
          <v-spacer></v-spacer>
          <v-btn variant="plain" icon @click="showDetailDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>

        <v-card-subtitle v-if="currentKB.description">
          {{ currentKB.description }}
        </v-card-subtitle>

        <v-card-text>
          <v-tabs v-model="activeTab">
            <v-tab value="documents">{{ tm('detailDialog.tabs.documents') }}</v-tab>
            <v-tab value="search">{{ tm('detailDialog.tabs.search') }}</v-tab>
            <v-tab value="settings">{{ tm('detailDialog.tabs.settings') }}</v-tab>
          </v-tabs>

          <v-window v-model="activeTab" class="mt-4">
            <v-window-item value="documents">
              <DocumentListPanel v-if="currentKB.kb_id" :kb="currentKB" />
            </v-window-item>

            <v-window-item value="search">
              <SearchPanel v-if="currentKB.kb_id" :kb="currentKB" />
            </v-window-item>

            <v-window-item value="settings">
              <KBSettingsPanel
                v-if="currentKB.kb_id"
                :kb="currentKB"
                @updated="onKBUpdated"
              />
            </v-window-item>
          </v-window>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="showDeleteDialog" max-width="450px">
      <v-card>
        <v-card-title class="text-h5">{{ tm('deleteDialog.title') }}</v-card-title>
        <v-card-text>
          <p>{{ tm('deleteDialog.confirmText', { name: deleteTarget.kb_name }) }}</p>
          <p class="text-error mt-2">{{ tm('deleteDialog.warning') }}</p>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="grey" variant="text" @click="showDeleteDialog = false">
            {{ tm('deleteDialog.cancel') }}
          </v-btn>
          <v-btn color="error" variant="text" @click="deleteKnowledgeBase" :loading="deleting">
            {{ tm('deleteDialog.delete') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 会话配置对话框 -->
    <v-dialog v-model="showSessionConfigDialog" max-width="900px" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center">
          <span>{{ tm('sessionConfig.title') }}</span>
          <v-spacer></v-spacer>
          <v-btn variant="plain" icon @click="showSessionConfigDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text>
          <SessionConfigPanel />
        </v-card-text>
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
import DocumentListPanel from './components/DocumentListPanel.vue';
import SearchPanel from './components/SearchPanel.vue';
import KBSettingsPanel from './components/KBSettingsPanel.vue';
import SessionConfigPanel from './components/SessionConfigPanel.vue';

export default {
  name: 'KnowledgeBaseV2',
  components: {
    DocumentListPanel,
    SearchPanel,
    KBSettingsPanel,
    SessionConfigPanel,
  },
  setup() {
    const { tm } = useModuleI18n('features/alkaid/knowledge-base-v2/index');
    return { tm };
  },
  data() {
    return {
      showCompatibilityWarning: true,
      kbCollections: [],
      loading: false,
      creating: false,
      deleting: false,
      showCreateDialog: false,
      showEmojiPicker: false,
      showDetailDialog: false,
      showDeleteDialog: false,
      showSessionConfigDialog: false,
      editingKB: null,
      currentKB: {},
      deleteTarget: {},
      activeTab: 'documents',
      newKB: {
        kb_name: '',
        description: '',
        emoji: '📚',
        embedding_provider_id: null,
        rerank_provider_id: null,
      },
      embeddingProviderConfigs: [],
      rerankProviderConfigs: [],
      emojiCategories: [
        {
          key: 'books',
          emojis: ['📚', '📖', '📕', '📗', '📘', '📙', '📓', '📔', '📒', '📑', '🗂️', '📂', '📁', '🗃️', '🗄️'],
        },
        {
          key: 'emotions',
          emojis: ['😀', '😃', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '🙃', '😉', '😊', '😇', '🥰', '😍'],
        },
        {
          key: 'objects',
          emojis: ['💡', '🔬', '🔭', '🗿', '🏆', '🎯', '🎓', '🔑', '🔒', '🔓', '🔔', '🔕', '🔨', '🛠️', '⚙️'],
        },
        {
          key: 'symbols',
          emojis: ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '⭐', '🌟', '✨', '💫', '⚡', '🔥'],
        },
      ],
      snackbar: {
        show: false,
        text: '',
        color: 'success',
      },
    };
  },
  mounted() {
    this.loadKnowledgeBases();
    this.loadProviderConfigs();
  },
  methods: {
    embeddingModelProps(providerConfig) {
      return {
        title: providerConfig.embedding_model || providerConfig.id,
        subtitle: this.tm('createDialog.providerInfo', {
          id: providerConfig.id,
          dimensions: providerConfig.embedding_dimensions || 'N/A',
        }),
      };
    },
    rerankModelProps(providerConfig) {
      return {
        title: providerConfig.rerank_model || providerConfig.id,
        subtitle: this.tm('createDialog.rerankProviderInfo', {
          id: providerConfig.id,
        }),
      };
    },
    async loadKnowledgeBases() {
      this.loading = true;
      try {
        const response = await axios.get('/api/kb/list');
        if (response.data.status === 'ok') {
          this.kbCollections = response.data.data.items || [];
        } else {
          this.showSnackbar(response.data.message || this.tm('messages.loadFailed'), 'error');
        }
      } catch (error) {
        console.error('Error loading knowledge bases:', error);
        this.showSnackbar(this.tm('messages.loadError'), 'error');
      } finally {
        this.loading = false;
      }
    },
    async loadProviderConfigs() {
      try {
        const response = await axios.get('/api/config/provider/list', {
          params: { provider_type: 'embedding,rerank' },
        });
        if (response.data.status === 'ok') {
          this.embeddingProviderConfigs = response.data.data.filter(
            (p) => p.provider_type === 'embedding'
          );
          this.rerankProviderConfigs = response.data.data.filter(
            (p) => p.provider_type === 'rerank'
          );
        }
      } catch (error) {
        console.error('Error loading provider configs:', error);
      }
    },
    openKnowledgeBase(kb) {
      this.currentKB = kb;
      this.activeTab = 'documents';
      this.showDetailDialog = true;
    },
    editKnowledgeBase(kb) {
      this.editingKB = kb;
      this.newKB = {
        kb_name: kb.kb_name,
        description: kb.description || '',
        emoji: kb.emoji || '📚',
        embedding_provider_id: kb.embedding_provider_id,
        rerank_provider_id: kb.rerank_provider_id,
      };
      this.showCreateDialog = true;
    },
    async submitCreateForm() {
      if (!this.newKB.kb_name) {
        this.showSnackbar(this.tm('messages.nameRequired'), 'warning');
        return;
      }

      this.creating = true;
      try {
        const payload = {
          kb_name: this.newKB.kb_name,
          description: this.newKB.description,
          emoji: this.newKB.emoji || '📚',
          embedding_provider_id: this.newKB.embedding_provider_id,
          rerank_provider_id: this.newKB.rerank_provider_id,
        };

        let response;
        if (this.editingKB) {
          response = await axios.post('/api/kb/update', {
            kb_id: this.editingKB.kb_id,
            ...payload,
          });
        } else {
          response = await axios.post('/api/kb/create', payload);
        }

        if (response.data.status === 'ok') {
          this.showSnackbar(
            this.editingKB ? this.tm('messages.updateSuccess') : this.tm('messages.createSuccess')
          );
          this.showCreateDialog = false;
          this.resetNewKB();
          this.loadKnowledgeBases();
        } else {
          this.showSnackbar(response.data.message || this.tm('messages.saveFailed'), 'error');
        }
      } catch (error) {
        console.error('Error saving knowledge base:', error);
        this.showSnackbar(this.tm('messages.saveError'), 'error');
      } finally {
        this.creating = false;
      }
    },
    confirmDelete(kb) {
      this.deleteTarget = kb;
      this.showDeleteDialog = true;
    },
    async deleteKnowledgeBase() {
      if (!this.deleteTarget.kb_id) {
        return;
      }

      this.deleting = true;
      try {
        const response = await axios.post('/api/kb/delete', {
          kb_id: this.deleteTarget.kb_id,
        });

        if (response.data.status === 'ok') {
          this.showSnackbar(this.tm('messages.deleteSuccess'));
          this.showDeleteDialog = false;
          this.loadKnowledgeBases();
        } else {
          this.showSnackbar(response.data.message || this.tm('messages.deleteFailed'), 'error');
        }
      } catch (error) {
        console.error('Error deleting knowledge base:', error);
        this.showSnackbar(this.tm('messages.deleteError'), 'error');
      } finally {
        this.deleting = false;
      }
    },
    selectEmoji(emoji) {
      this.newKB.emoji = emoji;
      this.showEmojiPicker = false;
    },
    resetNewKB() {
      this.editingKB = null;
      this.newKB = {
        kb_name: '',
        description: '',
        emoji: '📚',
        embedding_provider_id: null,
        rerank_provider_id: null,
      };
    },
    onKBUpdated() {
      this.loadKnowledgeBases();
      this.showDetailDialog = false;
    },
    openUrl(url) {
      window.open(url, '_blank');
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
.kb-v2-container {
  padding: 16px;
}

.action-buttons {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 24px;
  margin-top: 16px;
}

.kb-card {
  height: 280px;
  overflow: hidden;
  position: relative;
  cursor: pointer;
  display: flex;
  transition: all 0.3s ease;
}

.kb-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15) !important;
}

.book-spine {
  width: 12px;
  background: linear-gradient(180deg, #5c6bc0 0%, #3f51b5 100%);
  height: 100%;
  border-radius: 2px 0 0 2px;
}

.book-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: linear-gradient(145deg, #f5f7fa 0%, #e4e8f0 100%);
  position: relative;
}

.kb-emoji {
  font-size: 48px;
  margin-bottom: 16px;
}

.kb-name {
  font-weight: bold;
  font-size: 18px;
  margin-bottom: 12px;
  text-align: center;
  color: #333;
}

.kb-stats {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 14px;
  color: #666;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.kb-actions {
  position: absolute;
  bottom: 12px;
  right: 12px;
  display: flex;
  gap: 8px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.kb-card:hover .kb-actions {
  opacity: 1;
}

.emoji-display {
  font-size: 64px;
  cursor: pointer;
  transition: transform 0.2s ease;
  display: inline-block;
}

.emoji-display:hover {
  transform: scale(1.1);
}

.emoji-sm {
  font-size: 24px;
}

.emoji-picker {
  max-height: 400px;
  overflow-y: auto;
}

.emoji-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 8px;
}

.emoji-item {
  font-size: 28px;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 4px;
  transition: background-color 0.2s ease;
}

.emoji-item:hover {
  background-color: rgba(0, 0, 0, 0.05);
}
</style>
