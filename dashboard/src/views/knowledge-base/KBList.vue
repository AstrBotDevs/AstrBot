<template>
  <div class="kb-list-page">
    <div v-if="loading && kbList.length === 0" class="loading-container">
      <v-progress-circular indeterminate color="primary" size="64" />
      <p class="mt-4 text-medium-emphasis">{{ t('list.loading') }}</p>
    </div>

    <div v-else-if="kbList.length > 0" class="kb-list">
      <OutlinedActionListItem
        v-for="kb in kbList"
        :key="kb.kb_id"
        :title="kb.kb_name"
        :clickable="!kb.init_error"
        @click="navigateToDetail(kb.kb_id)"
      >
        <template #title-prepend>
          <span class="kb-list-emoji">{{ kb.emoji || '📚' }}</span>
        </template>

        <template #title-extra>
          <v-chip
            v-if="kb.init_error"
            color="error"
            size="x-small"
            variant="tonal"
          >
            {{ t('list.initError') }}
          </v-chip>
        </template>

        <div v-if="!kb.init_error" class="kb-description text-body-2 text-medium-emphasis">
          {{ kb.description || '暂无描述' }}
        </div>

        <div v-if="kb.init_error" class="kb-error-panel">
            <div class="kb-error-title">
              <v-icon size="16" color="error">mdi-close-circle</v-icon>
              <span>{{ t('list.initError') }}</span>
            </div>
            <div class="kb-error-detail" :title="kb.init_error">{{ kb.init_error }}</div>
        </div>

        <div class="kb-stats" v-if="!kb.init_error">
            <div class="stat-item">
              <v-icon size="small">mdi-file-document</v-icon>
              <span>{{ kb.doc_count || 0 }} {{ t('list.documents') }}</span>
            </div>
            <div class="stat-item">
              <v-icon size="small">mdi-text-box</v-icon>
              <span>{{ kb.chunk_count || 0 }} {{ t('list.chunks') }}</span>
            </div>
        </div>

        <template #actions>
          <v-tooltip v-if="!kb.init_error" :text="t('card.edit')" location="top">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-pencil-outline"
                variant="text"
                size="small"
                class="list-action-icon-btn"
                @click.stop="editKB(kb)"
              />
            </template>
          </v-tooltip>

          <v-tooltip :text="t('card.delete')" location="top">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-delete-outline"
                variant="text"
                size="small"
                class="list-action-icon-btn"
                @click.stop="confirmDelete(kb)"
              />
            </template>
          </v-tooltip>
        </template>
      </OutlinedActionListItem>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <v-icon size="100" color="grey-lighten-2">mdi-book-open-variant</v-icon>
      <h2 class="mt-4">{{ t('list.empty') }}</h2>
      <v-btn class="mt-6" prepend-icon="mdi-plus" color="primary" variant="elevated" size="large"
        @click="showCreateDialog = true">
        {{ t('list.create') }}
      </v-btn>
    </div>

    <div class="kb-fab-stack">
      <v-tooltip :text="t('list.refresh')" location="left">
        <template #activator="{ props }">
          <v-btn
            v-bind="props"
            color="darkprimary"
            icon="mdi-refresh"
            size="x-large"
            variant="elevated"
            class="kb-fab"
            :loading="loading"
            @click="loadKnowledgeBases()"
          />
        </template>
      </v-tooltip>
      <v-tooltip :text="t('list.create')" location="left">
        <template #activator="{ props }">
          <v-btn
            v-bind="props"
            color="darkprimary"
            icon="mdi-plus"
            size="x-large"
            variant="elevated"
            class="kb-fab"
            @click="showCreateDialog = true"
          />
        </template>
      </v-tooltip>
    </div>

    <!-- 创建/编辑对话框 -->
    <v-dialog v-model="showCreateDialog" max-width="600px" persistent>
      <v-card>
        <v-card-title class="d-flex align-center">
          <span class="text-h5">{{ editingKB ? t('edit.title') : t('create.title') }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="closeCreateDialog" />
        </v-card-title>

        <v-divider />

        <v-card-text class="pa-6">
          <!-- Emoji 选择器 -->
          <div class="text-center mb-6">
            <div class="emoji-display" @click="showEmojiPicker = true">
              {{ formData.emoji }}
            </div>
            <p class="text-caption text-medium-emphasis mt-2">{{ t('create.emojiLabel') }}</p>
          </div>

          <!-- 表单 -->
          <v-form ref="formRef" @submit.prevent="submitForm">
            <v-text-field v-model="formData.kb_name" :label="t('create.nameLabel')"
              :placeholder="t('create.namePlaceholder')" variant="outlined"
              :rules="[v => !!v || t('create.nameRequired')]" required class="mb-4" hint="后续如修改知识库名称，需重新在配置文件更新。" persistent-hint />

            <v-textarea v-model="formData.description" :label="t('create.descriptionLabel')"
              :placeholder="t('create.descriptionPlaceholder')" variant="outlined" rows="3" class="mb-4" />

            <v-select v-model="formData.embedding_provider_id" :items="embeddingProviders"
              :item-title="item => item.embedding_model || item.id" :item-value="'id'"
              :label="t('create.embeddingModelLabel')" variant="outlined" class="mb-4" :disabled="editingKB !== null" hint="嵌入模型选择后无法修改，如需更换请创建新的知识库。" persistent-hint>
              <template #item="{ props, item }">
                <v-list-item v-bind="props">
                  <template #subtitle>
                    {{ t('create.providerInfo', {
                      id: item.raw.id,
                      dimensions: item.raw.embedding_dimensions || 'N/A'
                    }) }}
                  </template>
                </v-list-item>
              </template>
            </v-select>

            <v-select v-model="formData.rerank_provider_id" :items="rerankProviders"
              :item-title="item => item.rerank_model || item.id" :item-value="'id'"
              :label="t('create.rerankModelLabel')" variant="outlined" clearable class="mb-2">
              <template #item="{ props, item }">
                <v-list-item v-bind="props">
                  <template #subtitle>
                    {{ t('create.rerankProviderInfo', { id: item.raw.id }) }}
                  </template>
                </v-list-item>
              </template>
            </v-select>
          </v-form>
        </v-card-text>

        <v-divider />

        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="closeCreateDialog">
            {{ t('create.cancel') }}
          </v-btn>
          <v-btn color="primary" variant="elevated" @click="submitForm" :loading="saving">
            {{ editingKB ? t('edit.submit') : t('create.submit') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Emoji 选择器对话框 -->
    <v-dialog v-model="showEmojiPicker" max-width="500px">
      <v-card>
        <v-card-title class="pa-4">{{ t('emoji.title') }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-4">
          <div v-for="category in emojiCategories" :key="category.key" class="mb-4">
            <p class="text-subtitle-2 mb-2">{{ t(`emoji.categories.${category.key}`) }}</p>
            <div class="emoji-grid">
              <div v-for="emoji in category.emojis" :key="emoji" class="emoji-item" @click="selectEmoji(emoji)">
                {{ emoji }}
              </div>
            </div>
          </div>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="showEmojiPicker = false">
            {{ t('emoji.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="showDeleteDialog" max-width="450px" persistent>
      <v-card>
        <v-card-title class="pa-4 text-h6">{{ t('delete.title') }}</v-card-title>
        <v-divider />
        <v-card-text class="pa-6">
          <p>{{ t('delete.confirmText', { name: deleteTarget?.kb_name || '' }) }}</p>
          <v-alert type="error" variant="tonal" density="compact" class="mt-4">
            {{ t('delete.warning') }}
          </v-alert>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="cancelDelete">
            {{ t('delete.cancel') }}
          </v-btn>
          <v-btn color="error" variant="elevated" @click="deleteKB" :loading="deleting">
            {{ t('delete.confirm') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>

    <div class="position-absolute" style="bottom: 0px; right: 16px;">
      <small @click="router.push('/alkaid/knowledge-base')"><a style="text-decoration: underline; cursor: pointer;">切换到旧版知识库</a></small>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'
import OutlinedActionListItem from '@/components/shared/OutlinedActionListItem.vue'

const { tm: t } = useModuleI18n('features/knowledge-base/index')
const router = useRouter()

// 状态
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const kbList = ref<any[]>([])
const embeddingProviders = ref<any[]>([])
const rerankProviders = ref<any[]>([])
const originalEmbeddingProvider = ref<string | null>(null)
const showEmbeddingWarning = ref(false)
const embeddingChangeDialog = ref(false)
const pendingEmbeddingProvider = ref<string | null>(null)

// 对话框
const showCreateDialog = ref(false)
const showEmojiPicker = ref(false)
const showDeleteDialog = ref(false)

// Snackbar 通知
const snackbar = ref({
  show: false,
  text: '',
  color: 'success'
})

// 表单
const formRef = ref()
const editingKB = ref<any>(null)
const deleteTarget = ref<any>(null)
const formData = ref({
  kb_name: '',
  description: '',
  emoji: '📚',
  embedding_provider_id: null,
  rerank_provider_id: null
})

// Emoji 分类
const emojiCategories = [
  {
    key: 'books',
    emojis: ['📚', '📖', '📕', '📗', '📘', '📙', '📓', '📔', '📒', '📑', '🗂️', '📂', '📁', '🗃️', '🗄️']
  },
  {
    key: 'emotions',
    emojis: ['😀', '😃', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '🙃', '😉', '😊', '😇', '🥰', '😍']
  },
  {
    key: 'objects',
    emojis: ['💡', '🔬', '🔭', '🗿', '🏆', '🎯', '🎓', '🔑', '🔒', '🔓', '🔔', '🔕', '🔨', '🛠️', '⚙️']
  },
  {
    key: 'symbols',
    emojis: ['❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '⭐', '🌟', '✨', '💫', '⚡', '🔥']
  }
]

// 加载知识库列表
const loadKnowledgeBases = async (refreshStats = false) => {
  loading.value = true
  try {
    const params: any = {}
    if (refreshStats) {
      params.refresh_stats = 'true'
    }

    const response = await axios.get('/api/kb/list', { params })
    if (response.data.status === 'ok') {
      kbList.value = response.data.data.items || []
    } else {
      showSnackbar(response.data.message || t('messages.loadError'), 'error')
    }
  } catch (error) {
    console.error('Failed to load knowledge bases:', error)
    showSnackbar(t('messages.loadError'), 'error')
  } finally {
    loading.value = false
  }
}

// 加载提供商配置
const loadProviders = async () => {
  try {
    const response = await axios.get('/api/config/provider/list', {
      params: { provider_type: 'embedding,rerank' }
    })
    if (response.data.status === 'ok') {
      embeddingProviders.value = response.data.data.filter(
        (p: any) => p.provider_type === 'embedding'
      )
      rerankProviders.value = response.data.data.filter(
        (p: any) => p.provider_type === 'rerank'
      )
    }
  } catch (error) {
    console.error('Failed to load providers:', error)
  }
}

// 导航到详情页
const navigateToDetail = (kbId: string) => {
  router.push({ name: 'NativeKBDetail', params: { kbId } })
}

// 编辑知识库
const editKB = (kb: any) => {
  editingKB.value = kb
  originalEmbeddingProvider.value = kb.embedding_provider_id
  formData.value = {
    kb_name: kb.kb_name,
    description: kb.description || '',
    emoji: kb.emoji || '📚',
    embedding_provider_id: kb.embedding_provider_id,
    rerank_provider_id: kb.rerank_provider_id
  }
  showCreateDialog.value = true
}

// 确认删除
const confirmDelete = (kb: any) => {
  deleteTarget.value = kb
  showDeleteDialog.value = true
}

// 取消删除
const cancelDelete = () => {
  showDeleteDialog.value = false
  deleteTarget.value = null
}

// 删除知识库
const deleteKB = async () => {
  if (!deleteTarget.value) return

  deleting.value = true
  try {
    const response = await axios.post('/api/kb/delete', {
      kb_id: deleteTarget.value.kb_id
    })

    console.log('Delete response:', response.data) // 调试日志

    if (response.data.status === 'ok') {
      showSnackbar(t('messages.deleteSuccess'))
      // 先刷新列表，再关闭对话框
      await loadKnowledgeBases()
      showDeleteDialog.value = false
      deleteTarget.value = null
    } else {
      showSnackbar(response.data.message || t('messages.deleteFailed'), 'error')
    }
  } catch (error) {
    console.error('Failed to delete knowledge base:', error)
    showSnackbar(t('messages.deleteFailed'), 'error')
  } finally {
    deleting.value = false
  }
}

// 提交表单
const submitForm = async () => {
  const { valid } = await formRef.value.validate()
  if (!valid) return

  saving.value = true
  try {
    const payload = {
      kb_name: formData.value.kb_name,
      description: formData.value.description,
      emoji: formData.value.emoji,
      embedding_provider_id: formData.value.embedding_provider_id,
      rerank_provider_id: formData.value.rerank_provider_id
    }

    let response
    if (editingKB.value) {
      response = await axios.post('/api/kb/update', {
        kb_id: editingKB.value.kb_id,
        ...payload
      })
    } else {
      response = await axios.post('/api/kb/create', payload)
    }

    if (response.data.status === 'ok') {
      showSnackbar(editingKB.value ? t('messages.updateSuccess') : t('messages.createSuccess'))
      closeCreateDialog()
      await loadKnowledgeBases()
    } else {
      showSnackbar(response.data.message || (editingKB.value ? t('messages.updateFailed') : t('messages.createFailed')), 'error')
    }
  } catch (error) {
    console.error('Failed to save knowledge base:', error)
    showSnackbar(editingKB.value ? t('messages.updateFailed') : t('messages.createFailed'), 'error')
  } finally {
    saving.value = false
  }
}

// 关闭创建对话框
const closeCreateDialog = () => {
  showCreateDialog.value = false
  editingKB.value = null
  originalEmbeddingProvider.value = null
  showEmbeddingWarning.value = false
  pendingEmbeddingProvider.value = null
  formData.value = {
    kb_name: '',
    description: '',
    emoji: '📚',
    embedding_provider_id: null,
    rerank_provider_id: null
  }
  formRef.value?.reset()
}

// 选择 emoji
const selectEmoji = (emoji: string) => {
  formData.value.emoji = emoji
  showEmojiPicker.value = false
}

// 显示通知
const showSnackbar = (text: string, color: string = 'success') => {
  snackbar.value.text = text
  snackbar.value.color = color
  snackbar.value.show = true
}

onMounted(() => {
  loadKnowledgeBases(true)  // 首次加载时刷新统计信息
  loadProviders()
})
</script>

<style scoped>
.kb-list-page {
  width: 100%;
}

.kb-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kb-list-emoji {
  font-size: 1.25rem;
  line-height: 1;
}

.kb-description {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
  overflow: hidden;
}

.kb-stats {
  display: flex;
  gap: 16px;
  margin-top: 6px;
}

.kb-error-panel {
  width: 100%;
  text-align: left;
  background: rgba(var(--v-theme-error), 0.08);
  border: 1px solid rgba(var(--v-theme-error), 0.18);
  border-radius: 10px;
  padding: 10px 12px;
}

.kb-error-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  font-weight: 600;
  color: rgb(var(--v-theme-error));
  margin-bottom: 4px;
}

.kb-error-detail {
  font-size: 0.78rem;
  line-height: 1.35;
  color: rgba(var(--v-theme-on-surface), 0.82);
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.875rem;
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.list-action-icon-btn {
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.list-action-icon-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface));
}

.kb-fab-stack {
  align-items: center;
  bottom: 52px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: fixed;
  right: 52px;
  z-index: 10000;
}

.kb-fab {
  border-radius: 16px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.kb-fab:hover {
  box-shadow: 0 12px 20px rgba(var(--v-theme-primary), 0.4);
  transform: translateY(-4px) scale(1.05);
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  text-align: center;
}

/* 加载状态 */
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

/* Emoji 显示和选择器 */
.emoji-display {
  font-size: 72px;
  cursor: pointer;
  transition: transform 0.2s ease;
  display: inline-block;
  padding: 0px 16px;
  border-radius: 12px;
  background: rgba(var(--v-theme-primary), 0.05);
}

.emoji-display:hover {
  transform: scale(1.1);
  background: rgba(var(--v-theme-primary), 0.1);
}

.emoji-grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 8px;
}

.emoji-item {
  font-size: 32px;
  padding: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.2s ease;
}

.emoji-item:hover {
  background: rgba(var(--v-theme-primary), 0.1);
  transform: scale(1.2);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .emoji-grid {
    grid-template-columns: repeat(6, 1fr);
  }
}
</style>
