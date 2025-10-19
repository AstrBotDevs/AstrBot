<template>
  <div class="sessions-tab">
    <v-card elevation="2">
      <v-card-title class="d-flex align-center pa-4">
        <span>{{ t('sessions.title') }}</span>
        <v-spacer />
        <v-btn
          prepend-icon="mdi-plus"
          color="primary"
          variant="elevated"
          size="small"
          @click="showAddDialog = true"
        >
          {{ t('sessions.add') }}
        </v-btn>
      </v-card-title>

      <v-card-subtitle class="px-4 pb-4">
        {{ t('sessions.subtitle') }}
      </v-card-subtitle>

      <v-divider />

      <v-card-text class="pa-0">
        <v-data-table
          :headers="headers"
          :items="sessions"
          :loading="loading"
        >
          <template #item.scope="{ item }">
            <v-chip :color="item.scope === 'session' ? 'primary' : 'secondary'" size="small" variant="tonal">
              {{ item.scope === 'session' ? t('sessions.scopeSession') : t('sessions.scopePlatform') }}
            </v-chip>
          </template>

          <template #item.enable_rerank="{ item }">
            <v-icon :color="item.enable_rerank ? 'success' : 'grey'">
              {{ item.enable_rerank ? 'mdi-check-circle' : 'mdi-close-circle' }}
            </v-icon>
          </template>

          <template #item.actions="{ item }">
            <v-btn
              icon="mdi-delete"
              variant="text"
              size="small"
              color="error"
              @click="confirmDelete(item)"
            />
          </template>

          <template #no-data>
            <div class="text-center py-8">
              <v-icon size="64" color="grey-lighten-2">mdi-account-multiple-outline</v-icon>
              <p class="mt-4 text-medium-emphasis">{{ t('sessions.empty') }}</p>
            </div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- 添加配置对话框 -->
    <v-dialog v-model="showAddDialog" max-width="500px" persistent>
      <v-card>
        <v-card-title class="pa-4">
          <span class="text-h6">{{ t('sessions.add') }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="closeAddDialog" />
        </v-card-title>

        <v-divider />

        <v-card-text class="pa-6">
          <v-form ref="formRef">
            <v-select
              v-model="formData.scope"
              :items="scopeOptions"
              :label="t('sessions.scope')"
              variant="outlined"
              class="mb-4"
            />

            <v-text-field
              v-model="formData.scope_id"
              :label="t('sessions.scopeId')"
              :placeholder="formData.scope === 'session' ? 'platform:xxx:session_id' : 'platform_id'"
              variant="outlined"
              required
              class="mb-4"
            />

            <v-text-field
              v-model.number="formData.top_k"
              :label="t('sessions.topK')"
              type="number"
              variant="outlined"
              class="mb-4"
            />

            <v-checkbox
              v-model="formData.enable_rerank"
              :label="t('sessions.enableRerank')"
              color="primary"
            />
          </v-form>
        </v-card-text>

        <v-divider />

        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="closeAddDialog">取消</v-btn>
          <v-btn
            color="primary"
            variant="elevated"
            @click="addSession"
            :loading="saving"
          >
            添加
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="showDeleteDialog" max-width="400px">
      <v-card>
        <v-card-title class="pa-4 text-h6">确认删除</v-card-title>
        <v-divider />
        <v-card-text class="pa-6">
          <p>{{ t('sessions.deleteConfirm') }}</p>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="showDeleteDialog = false">取消</v-btn>
          <v-btn
            color="error"
            variant="elevated"
            @click="deleteSession"
            :loading="deleting"
          >
            删除
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

const { tm: t } = useModuleI18n('features/knowledge-base/detail')

const props = defineProps<{
  kbId: string
}>()

// 状态
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const sessions = ref<any[]>([])
const showAddDialog = ref(false)
const showDeleteDialog = ref(false)
const deleteTarget = ref<any>(null)
const formRef = ref()

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
  scope: 'session',
  scope_id: '',
  top_k: 5,
  enable_rerank: true
})

// 表格列
const headers = [
  { title: t('sessions.scope'), key: 'scope' },
  { title: t('sessions.scopeId'), key: 'scope_id' },
  { title: t('sessions.topK'), key: 'top_k' },
  { title: t('sessions.enableRerank'), key: 'enable_rerank' },
  { title: t('sessions.actions'), key: 'actions', sortable: false, align: 'end' }
]

// 范围选项
const scopeOptions = [
  { title: t('sessions.scopeSession'), value: 'session' },
  { title: t('sessions.scopePlatform'), value: 'platform' }
]

// 加载会话配置
const loadSessions = async () => {
  loading.value = true
  try {
    const response = await axios.get('/api/kb/session/config/list')
    if (response.data.status === 'ok') {
      // 过滤出使用当前知识库的配置
      sessions.value = response.data.data.items.filter((item: any) => {
        const kbIds = JSON.parse(item.kb_ids || '[]')
        return kbIds.includes(props.kbId)
      })
    }
  } catch (error) {
    console.error('Failed to load session configs:', error)
    showSnackbar('加载会话配置失败', 'error')
  } finally {
    loading.value = false
  }
}

// 添加会话配置
const addSession = async () => {
  const { valid } = await formRef.value.validate()
  if (!valid) return

  saving.value = true
  try {
    const response = await axios.post('/api/kb/session/config', {
      scope: formData.value.scope,
      scope_id: formData.value.scope_id,
      kb_ids: [props.kbId],
      top_k: formData.value.top_k,
      enable_rerank: formData.value.enable_rerank
    })

    if (response.data.status === 'ok') {
      showSnackbar(t('sessions.addSuccess'))
      closeAddDialog()
      await loadSessions()
    } else {
      showSnackbar(response.data.message || t('sessions.addFailed'), 'error')
    }
  } catch (error) {
    console.error('Failed to add session config:', error)
    showSnackbar(t('sessions.addFailed'), 'error')
  } finally {
    saving.value = false
  }
}

// 确认删除
const confirmDelete = (session: any) => {
  deleteTarget.value = session
  showDeleteDialog.value = true
}

// 删除会话配置
const deleteSession = async () => {
  if (!deleteTarget.value) return

  deleting.value = true
  try {
    const response = await axios.post('/api/kb/session/config/delete', {
      scope: deleteTarget.value.scope,
      scope_id: deleteTarget.value.scope_id
    })

    if (response.data.status === 'ok') {
      showSnackbar(t('sessions.deleteSuccess'))
      showDeleteDialog.value = false
      await loadSessions()
    } else {
      showSnackbar(response.data.message || t('sessions.deleteFailed'), 'error')
    }
  } catch (error) {
    console.error('Failed to delete session config:', error)
    showSnackbar(t('sessions.deleteFailed'), 'error')
  } finally {
    deleting.value = false
  }
}

// 关闭添加对话框
const closeAddDialog = () => {
  showAddDialog.value = false
  formData.value = {
    scope: 'session',
    scope_id: '',
    top_k: 5,
    enable_rerank: true
  }
  formRef.value?.reset()
}

onMounted(() => {
  loadSessions()
})
</script>

<style scoped>
.sessions-tab {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
