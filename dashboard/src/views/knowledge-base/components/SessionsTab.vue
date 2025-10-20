<template>
  <div class="sessions-tab">
    <v-card elevation="2">
      <v-card-title class="d-flex align-center pa-4">
        <span>{{ t('sessions.title') }}</span>
        <v-spacer />
        <v-btn
          prepend-icon="mdi-refresh"
          variant="tonal"
          size="small"
          @click="loadSessions"
          :loading="loading"
        >
          {{ t('sessions.refresh') }}
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
              icon="mdi-open-in-new"
              variant="text"
              size="small"
              color="primary"
              @click="goToSessionManagement(item)"
              :title="t('sessions.viewInSessionManagement')"
            />
          </template>

          <template #no-data>
            <div class="text-center py-8">
              <v-icon size="64" color="grey-lighten-2">mdi-account-multiple-outline</v-icon>
              <p class="mt-4 text-medium-emphasis">{{ t('sessions.empty') }}</p>
              <v-btn
                class="mt-4"
                prepend-icon="mdi-cog"
                variant="tonal"
                color="primary"
                @click="goToSessionManagement()"
              >
                {{ t('sessions.goToSessionManagement') }}
              </v-btn>
            </div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <!-- 消息提示 -->
    <v-snackbar v-model="snackbar.show" :color="snackbar.color">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

const { tm: t } = useModuleI18n('features/knowledge-base/detail')
const router = useRouter()

const props = defineProps<{
  kbId: string
}>()

// 状态
const loading = ref(false)
const sessions = ref<any[]>([])

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

// 表格列
const headers = [
  { title: t('sessions.scope'), key: 'scope' },
  { title: t('sessions.scopeId'), key: 'scope_id' },
  { title: t('sessions.topK'), key: 'top_k' },
  { title: t('sessions.enableRerank'), key: 'enable_rerank' },
  { title: t('sessions.actions'), key: 'actions', sortable: false, align: 'end' }
]

// 加载使用该知识库的会话
const loadSessions = async () => {
  loading.value = true
  console.log('[SessionsTab] 开始加载会话列表, kb_id:', props.kbId)

  try {
    const url = '/api/kb/session/config/list_by_kb'
    const params = { kb_id: props.kbId }
    console.log('[SessionsTab] 请求URL:', url, '参数:', params)

    const response = await axios.get(url, { params })
    console.log('[SessionsTab] 响应状态:', response.status)
    console.log('[SessionsTab] 响应数据:', response.data)

    if (response.data.status === 'ok') {
      sessions.value = response.data.data.sessions
      console.log('[SessionsTab] 成功加载会话列表, 数量:', sessions.value.length)
    } else {
      console.error('[SessionsTab] API返回错误:', response.data.message)
      showSnackbar(response.data.message || t('sessions.loadFailed'), 'error')
    }
  } catch (error) {
    console.error('[SessionsTab] 请求失败:', error)
    if (error.response) {
      console.error('[SessionsTab] 错误响应状态:', error.response.status)
      console.error('[SessionsTab] 错误响应数据:', error.response.data)
    } else if (error.request) {
      console.error('[SessionsTab] 请求未收到响应:', error.request)
    } else {
      console.error('[SessionsTab] 请求配置错误:', error.message)
    }
    showSnackbar(t('sessions.loadFailed'), 'error')
  } finally {
    loading.value = false
  }
}

// 跳转到会话管理页面
const goToSessionManagement = (session?: any) => {
  router.push({ name: 'SessionManagement' })
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
