<template>
  <div class="kb-list-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <div>
        <h1 class="text-h4 mb-2">{{ t('list.title') }}</h1>
        <p class="text-subtitle-1 text-medium-emphasis">{{ t('list.subtitle') }}</p>
      </div>
      <v-btn
        icon="mdi-information-outline"
        variant="text"
        size="small"
        color="grey"
        href="https://astrbot.app/use/knowledge-base.html"
        target="_blank"
      />
    </div>

    <!-- 操作按钮栏 -->
    <div class="action-bar mb-6">
      <v-btn
        prepend-icon="mdi-plus"
        color="primary"
        variant="elevated"
        @click="showCreateDialog = true"
      >
        {{ t('list.create') }}
      </v-btn>
      <v-btn
        prepend-icon="mdi-refresh"
        variant="tonal"
        @click="loadKnowledgeBases"
        :loading="loading"
      >
        {{ t('list.refresh') }}
      </v-btn>
    </div>

    <!-- 知识库网格 -->
    <div v-if="loading && kbList.length === 0" class="loading-container">
      <v-progress-circular indeterminate color="primary" size="64" />
      <p class="mt-4 text-medium-emphasis">{{ t('list.loading') }}</p>
    </div>

    <div v-else-if="kbList.length > 0" class="kb-grid">
      <v-card
        v-for="kb in kbList"
        :key="kb.kb_id"
        class="kb-card"
        elevation="2"
        hover
        @click="navigateToDetail(kb.kb_id)"
      >
        <div class="kb-card-content">
          <div class="kb-emoji">{{ kb.emoji || '📚' }}</div>
          <h3 class="kb-name">{{ kb.kb_name }}</h3>
          <p class="kb-description text-medium-emphasis">{{ kb.description || '暂无描述' }}</p>

          <div class="kb-stats mt-4">
            <div class="stat-item">
              <v-icon size="small" color="primary">mdi-file-document</v-icon>
              <span>{{ kb.doc_count || 0 }} {{ t('list.documents') }}</span>
            </div>
            <div class="stat-item">
              <v-icon size="small" color="secondary">mdi-text-box</v-icon>
              <span>{{ kb.chunk_count || 0 }} {{ t('list.chunks') }}</span>
            </div>
          </div>

          <div class="kb-actions">
            <v-btn
              icon="mdi-pencil"
              size="small"
              variant="text"
              color="info"
              @click.stop="editKB(kb)"
            />
            <v-btn
              icon="mdi-delete"
              size="small"
              variant="text"
              color="error"
              @click.stop="confirmDelete(kb)"
            />
          </div>
        </div>
      </v-card>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <v-icon size="100" color="grey-lighten-2">mdi-book-open-variant</v-icon>
      <h2 class="mt-4">{{ t('list.empty') }}</h2>
      <v-btn
        class="mt-6"
        prepend-icon="mdi-plus"
        color="primary"
        variant="elevated"
        size="large"
        @click="showCreateDialog = true"
      >
        {{ t('list.create') }}
      </v-btn>
    </div>

    <!-- 创建/编辑对话框 -->
    <v-dialog v-model="showCreateDialog" max-width="600px" persistent>
      <v-card>
        <v-card-title class="d-flex align-center pa-4">
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
            <v-text-field
              v-model="formData.kb_name"
              :label="t('create.nameLabel')"
              :placeholder="t('create.namePlaceholder')"
              variant="outlined"
              :rules="[v => !!v || t('create.nameRequired')]"
              required
              class="mb-4"
            />

            <v-textarea
              v-model="formData.description"
              :label="t('create.descriptionLabel')"
              :placeholder="t('create.descriptionPlaceholder')"
              variant="outlined"
              rows="3"
              class="mb-4"
            />

            <v-select
              v-model="formData.embedding_provider_id"
              :items="embeddingProviders"
              :item-title="item => item.embedding_model || item.id"
              :item-value="'id'"
              :label="t('create.embeddingModelLabel')"
              variant="outlined"
              class="mb-4"
              @update:model-value="handleEmbeddingProviderChange"
            >
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

            <v-alert type="warning" variant="tonal" density="compact" class="mb-4" v-if="editingKB && showEmbeddingWarning">
              <strong>注意:</strong> 修改嵌入模型会导致现有的向量数据失效,建议重新上传文档。不同的嵌入模型生成的向量不兼容,可能导致检索结果不准确。
            </v-alert>

            <v-select
              v-model="formData.rerank_provider_id"
              :items="rerankProviders"
              :item-title="item => item.rerank_model || item.id"
              :item-value="'id'"
              :label="t('create.rerankModelLabel')"
              variant="outlined"
              clearable
              class="mb-2"
            >
              <template #item="{ props, item }">
                <v-list-item v-bind="props">
                  <template #subtitle>
                    {{ t('create.rerankProviderInfo', { id: item.raw.id }) }}
                  </template>
                </v-list-item>
              </template>
            </v-select>

            <v-alert type="info" variant="tonal" density="compact" class="mt-4">
              {{ t('create.tips') }}
            </v-alert>
          </v-form>
        </v-card-text>

        <v-divider />

        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="closeCreateDialog">
            {{ t('create.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="elevated"
            @click="submitForm"
            :loading="saving"
          >
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
              <div
                v-for="emoji in category.emojis"
                :key="emoji"
                class="emoji-item"
                @click="selectEmoji(emoji)"
              >
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
          <v-btn
            color="error"
            variant="elevated"
            @click="deleteKB"
            :loading="deleting"
          >
            {{ t('delete.confirm') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>

    <!-- Embedding Provider 修改确认对话框 -->
    <v-dialog v-model="embeddingChangeDialog" max-width="500px" persistent>
      <v-card>
        <v-card-title class="bg-warning text-white">
          <v-icon class="mr-2">mdi-alert</v-icon>
          确认修改嵌入模型
        </v-card-title>
        <v-card-text class="pa-6">
          <v-alert type="warning" variant="tonal" class="mb-4">
            <strong>警告:</strong> 修改嵌入模型将导致以下影响:
          </v-alert>
          <ul class="text-body-2">
            <li>现有的向量数据将失效</li>
            <li>检索功能可能无法正常工作</li>
            <li>建议删除现有文档后重新上传</li>
            <li>不同嵌入模型生成的向量不兼容</li>
          </ul>
          <div class="mt-4 text-body-2">
            您确定要将嵌入模型从 <strong>{{ originalEmbeddingProvider }}</strong> 修改为 <strong>{{ pendingEmbeddingProvider }}</strong> 吗?
          </div>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="cancelEmbeddingChange">
            取消
          </v-btn>
          <v-btn color="warning" variant="elevated" @click="confirmEmbeddingChange">
            确认修改
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

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

// 处理 embedding provider 变更
const handleEmbeddingProviderChange = (newValue: string | null) => {
  // 检测是否修改了embedding provider
  if (newValue && originalEmbeddingProvider.value && newValue !== originalEmbeddingProvider.value) {
    // 显示二次确认对话框
    showEmbeddingWarning.value = true
    pendingEmbeddingProvider.value = newValue
    embeddingChangeDialog.value = true
  } else {
    showEmbeddingWarning.value = false
  }
}

// 确认修改 embedding provider
const confirmEmbeddingChange = () => {
  if (pendingEmbeddingProvider.value) {
    formData.value.embedding_provider_id = pendingEmbeddingProvider.value
    // 更新原始值,这样下次比较时不会重复弹窗
    originalEmbeddingProvider.value = pendingEmbeddingProvider.value
  }
  embeddingChangeDialog.value = false
  showEmbeddingWarning.value = true
}

// 取消修改 embedding provider
const cancelEmbeddingChange = () => {
  // 恢复到原始值
  formData.value.embedding_provider_id = originalEmbeddingProvider.value
  embeddingChangeDialog.value = false
  showEmbeddingWarning.value = false
  pendingEmbeddingProvider.value = null
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
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 32px;
}

.action-bar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

/* 知识库网格 */
.kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 24px;
}

.kb-card {
  position: relative;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.kb-card:hover {
  transform: translateY(-8px);
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.15) !important;
}

.kb-card-content {
  padding: 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  min-height: 260px;
  position: relative;
}

.kb-emoji {
  font-size: 56px;
  margin-bottom: 16px;
  animation: float 3s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.kb-name {
  font-size: 1.25rem;
  font-weight: 600;
  margin-bottom: 8px;
  color: rgb(var(--v-theme-on-surface));
}

.kb-description {
  font-size: 0.875rem;
  line-height: 1.5;
  max-height: 3em;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.kb-stats {
  display: flex;
  gap: 16px;
  width: 100%;
  justify-content: center;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.875rem;
  color: rgb(var(--v-theme-on-surface));
  font-weight: 500;
}

.kb-actions {
  position: absolute;
  bottom: 16px;
  right: 16px;
  display: flex;
  gap: 8px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.kb-card:hover .kb-actions {
  opacity: 1;
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
  padding: 16px;
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
  .kb-list-page {
    padding: 16px;
  }

  .kb-grid {
    grid-template-columns: 1fr;
  }

  .emoji-grid {
    grid-template-columns: repeat(6, 1fr);
  }
}
</style>
