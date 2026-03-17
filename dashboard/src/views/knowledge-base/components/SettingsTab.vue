<template>
  <div class="settings-tab">
    <v-card elevation="2">
      <v-card-title class="pa-4">{{ t('settings.title') }}</v-card-title>
      <v-divider />

      <v-card-text class="pa-6">
        <v-form ref="formRef">
          <!-- 基本设置 -->
          <h3 class="text-h6 mb-4">{{ t('settings.basic') }}</h3>

          <v-row>
            <v-col cols="12" md="6">
              <v-text-field
                v-model.number="formData.chunk_size"
                :label="t('settings.chunkSize')"
                type="number"
                variant="outlined"
                density="comfortable"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model.number="formData.chunk_overlap"
                :label="t('settings.chunkOverlap')"
                type="number"
                variant="outlined"
                density="comfortable"
              />
            </v-col>
          </v-row>

          <!-- 检索设置 -->
          <h3 class="text-h6 mb-4 mt-6">{{ t('settings.retrieval') }}</h3>

          <v-row>
            <v-col cols="12" md="6">
              <v-text-field
                v-model.number="formData.top_k_dense"
                :label="t('settings.topKDense')"
                type="number"
                variant="outlined"
                density="comfortable"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model.number="formData.top_k_sparse"
                :label="t('settings.topKSparse')"
                type="number"
                variant="outlined"
                density="comfortable"
              />
            </v-col>
            <!-- <v-col cols="12" md="4">
              <v-text-field
                v-model.number="formData.top_m_final"
                :label="t('settings.topMFinal')"
                type="number"
                variant="outlined"
                density="comfortable"
              />
            </v-col> -->
          </v-row>

          <!-- 模型设置 -->
          <h3 class="text-h6 mb-4 mt-6">{{ t('settings.embeddingProvider') }}</h3>

          <v-row>
            <v-col cols="12" md="6">
              <v-select
                v-model="formData.embedding_provider_id"
                :items="embeddingProviders"
                :item-title="item => item.embedding_model || item.id"
                :item-value="'id'"
                :label="t('settings.embeddingProvider')"
                variant="outlined"
                density="comfortable"
                @update:model-value="handleEmbeddingProviderChange"
                :disabled="true"
              />
            </v-col>
            <v-col cols="12" md="6">
              <v-select
                v-model="formData.rerank_provider_id"
                :items="rerankProviders"
                :item-title="item => item.rerank_model || item.id"
                :item-value="'id'"
                :label="t('settings.rerankProvider')"
                variant="outlined"
                density="comfortable"
                clearable
              />
            </v-col>
          </v-row>

          <v-alert type="info" variant="tonal" class="mt-4">
            {{ t('settings.tips') }}
          </v-alert>

          <v-alert type="warning" variant="tonal" class="mt-4" v-if="showEmbeddingWarning">
            <strong>注意:</strong> 修改嵌入模型会导致现有的向量数据失效,建议重新上传文档。不同的嵌入模型生成的向量不兼容,可能导致检索结果不准确。
          </v-alert>
        </v-form>
      </v-card-text>

      <v-divider />

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn
          color="primary"
          variant="elevated"
          prepend-icon="mdi-content-save"
          @click="saveSettings"
          :loading="saving"
        >
          {{ t('settings.save') }}
        </v-btn>
      </v-card-actions>
    </v-card>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>

    <!-- Embedding Provider修改确认对话框 -->
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
import { ref, watch, onMounted } from 'vue'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

const { tm: t } = useModuleI18n('features/knowledge-base/detail')

const props = defineProps<{
  kb: any
}>()

const emit = defineEmits(['updated'])

// 状态
const saving = ref(false)
const formRef = ref()
const embeddingProviders = ref<any[]>([])
const rerankProviders = ref<any[]>([])
const originalEmbeddingProvider = ref('')
const showEmbeddingWarning = ref(false)
const embeddingChangeDialog = ref(false)
const pendingEmbeddingProvider = ref('')

const snackbar = ref({
  show: false,
  text: '',
  color: 'success'
})

const showSnackbar = (text: string, color: string = 'success') => {
  snackbar.value.text = text
  snackbar.value.color = color
  snackbar.value.show = true
}

// 表单数据
const formData = ref({
  chunk_size: 512,
  chunk_overlap: 50,
  top_k_dense: 50,
  top_k_sparse: 50,
  embedding_provider_id: '',
  rerank_provider_id: ''
})

// 监听 kb 变化,更新表单
watch(() => props.kb, (kb) => {
  if (kb) {
    formData.value = {
      chunk_size: kb.chunk_size || 512,
      chunk_overlap: kb.chunk_overlap || 50,
      top_k_dense: kb.top_k_dense || 50,
      top_k_sparse: kb.top_k_sparse || 50,
      // top_m_final: kb.top_m_final || 5,
      embedding_provider_id: kb.embedding_provider_id || '',
      rerank_provider_id: kb.rerank_provider_id || ''
    }
    // 保存原始的embedding provider
    originalEmbeddingProvider.value = kb.embedding_provider_id || ''
  }
}, { immediate: true })

// 加载提供商列表
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

// 处理embedding provider变更
const handleEmbeddingProviderChange = (newValue: string) => {
  if (newValue && newValue !== originalEmbeddingProvider.value) {
    // 显示警告并需要确认
    showEmbeddingWarning.value = true
    pendingEmbeddingProvider.value = newValue
    embeddingChangeDialog.value = true
  } else {
    showEmbeddingWarning.value = false
  }
}

// 确认修改embedding provider
const confirmEmbeddingChange = () => {
  formData.value.embedding_provider_id = pendingEmbeddingProvider.value
  embeddingChangeDialog.value = false
  showEmbeddingWarning.value = true
}

// 取消修改embedding provider
const cancelEmbeddingChange = () => {
  formData.value.embedding_provider_id = originalEmbeddingProvider.value
  embeddingChangeDialog.value = false
  showEmbeddingWarning.value = false
  pendingEmbeddingProvider.value = ''
}

// 保存设置
const saveSettings = async () => {
  const { valid } = await formRef.value.validate()
  if (!valid) return

  saving.value = true
  try {
    const response = await axios.post('/api/kb/update', {
      kb_id: props.kb.kb_id,
      chunk_size: formData.value.chunk_size,
      chunk_overlap: formData.value.chunk_overlap,
      top_k_dense: formData.value.top_k_dense,
      top_k_sparse: formData.value.top_k_sparse,
      // top_m_final: formData.value.top_m_final,
      rerank_provider_id: formData.value.rerank_provider_id
    })

    if (response.data.status === 'ok') {
      showSnackbar(t('settings.saveSuccess'))
      emit('updated')
    } else {
      showSnackbar(response.data.message || t('settings.saveFailed'), 'error')
    }
  } catch (error) {
    console.error('Failed to save settings:', error)
    showSnackbar(t('settings.saveFailed'), 'error')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadProviders()
})
</script>

<style scoped>
.settings-tab {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
