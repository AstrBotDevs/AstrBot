<template>
  <div class="cron-page">
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <h2 class="text-h5 font-weight-bold">Cron Job 管理</h2>
        <div class="text-body-2 text-medium-emphasis">查看、创建与管理定时任务（ActiveAgent & 后台任务）。</div>
      </div>
      <div class="d-flex align-center" style="gap: 8px;">
        <v-btn variant="tonal" color="primary" :loading="loading" @click="loadJobs">刷新</v-btn>
      </div>
    </div>

    <v-card class="rounded-lg mb-6" variant="flat">
      <v-card-text>
        <div class="text-subtitle-1 font-weight-bold mb-3">新建主动型 Agent 定时任务</div>
        <v-row dense>
          <v-col cols="12" md="4">
            <v-text-field v-model="form.name" label="任务名称" variant="outlined" density="comfortable" hide-details />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model="form.cron_expression" label="Cron 表达式" variant="outlined" density="comfortable" placeholder="0 8 * * *" hide-details />
            <div class="text-caption text-medium-emphasis mt-1">使用标准 5 段 Cron，例：0 8 * * * 表示每天 8:00。</div>
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model="form.session" label="Session (platform:type:id)" variant="outlined" density="comfortable" placeholder="webchat:friend:SESSION_ID" hide-details />
            <div class="text-caption text-medium-emphasis mt-1">从聊天侧栏或 Session 管理中复制 unified_msg_origin。</div>
          </v-col>
          <v-col cols="12">
            <v-textarea v-model="form.note" label="给未来 Agent 的说明" variant="outlined" rows="3" auto-grow hide-details />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model="form.persona_id" label="Persona (可选)" variant="outlined" density="comfortable" hide-details />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model="form.provider_id" label="Provider ID (可选)" variant="outlined" density="comfortable" hide-details />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model="form.timezone" label="时区 (可选, 例如 Asia/Shanghai)" variant="outlined" density="comfortable" hide-details />
          </v-col>
          <v-col cols="12" md="3">
            <v-switch v-model="form.enabled" inset color="primary" label="启用" hide-details />
          </v-col>
          <v-col cols="12" class="d-flex justify-end">
            <v-btn color="primary" variant="flat" :loading="saving" @click="createJob">创建任务</v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card class="rounded-lg" variant="flat">
      <v-card-text>
        <div class="d-flex align-center justify-space-between mb-3">
          <div class="text-subtitle-1 font-weight-bold">已注册任务</div>
        </div>

        <v-alert v-if="!jobs.length && !loading" type="info" variant="tonal">暂无定时任务。</v-alert>

        <v-data-table
          :items="jobs"
          :headers="headers"
          :loading="loading"
          item-key="job_id"
          density="comfortable"
          class="elevation-0"
        >
          <template #item.name="{ item }">
            <div class="font-weight-medium">{{ item.name }}</div>
            <div class="text-caption text-medium-emphasis">{{ item.description }}</div>
          </template>
          <template #item.type="{ item }">
            <v-chip size="small" color="primary" variant="tonal">{{ item.job_type }}</v-chip>
          </template>
          <template #item.cron_expression="{ item }">
            <div>{{ item.cron_expression || '—' }}</div>
            <div class="text-caption text-medium-emphasis">{{ item.timezone || 'local' }}</div>
          </template>
          <template #item.next_run_time="{ item }">{{ formatTime(item.next_run_time) }}</template>
          <template #item.status="{ item }">
            <v-chip :color="statusColor(item.status)" size="small" variant="flat">{{ item.status }}</v-chip>
          </template>
          <template #item.actions="{ item }">
            <div class="d-flex" style="gap: 8px;">
              <v-switch
                v-model="item.enabled"
                inset
                density="compact"
                hide-details
                color="primary"
                @change="toggleJob(item)"
              />
              <v-btn size="small" variant="text" color="primary" @click="deleteJob(item)">删除</v-btn>
            </div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="2600">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import axios from 'axios'

const loading = ref(false)
const saving = ref(false)
const jobs = ref<any[]>([])

const form = ref({
  name: 'active_agent_task',
  cron_expression: '',
  session: '',
  note: '',
  persona_id: '',
  provider_id: '',
  timezone: '',
  enabled: true
})

const snackbar = ref({ show: false, message: '', color: 'success' })

const headers = [
  { title: '名称', key: 'name', minWidth: 200 },
  { title: '类型', key: 'type', width: 110 },
  { title: 'Cron', key: 'cron_expression', minWidth: 160 },
  { title: '下一次执行', key: 'next_run_time', minWidth: 160 },
  { title: '状态', key: 'status', width: 120 },
  { title: '操作', key: 'actions', width: 160, sortable: false }
]

function toast(message: string, color: 'success' | 'error' | 'warning' = 'success') {
  snackbar.value = { show: true, message, color }
}

function formatTime(val: any): string {
  if (!val) return '—'
  try {
    return new Date(val).toLocaleString()
  } catch (e) {
    return String(val)
  }
}

function statusColor(status: string) {
  switch ((status || '').toLowerCase()) {
    case 'running':
      return 'blue'
    case 'failed':
      return 'error'
    case 'completed':
      return 'success'
    default:
      return 'secondary'
  }
}

async function loadJobs() {
  loading.value = true
  try {
    const res = await axios.get('/api/cron/jobs')
    if (res.data.status === 'ok') {
      jobs.value = Array.isArray(res.data.data) ? res.data.data : []
    } else {
      toast(res.data.message || '获取任务失败', 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || '获取任务失败', 'error')
  } finally {
    loading.value = false
  }
}

async function createJob() {
  if (!form.value.cron_expression || !form.value.session || !form.value.note) {
    toast('请填写 cron、session 和说明', 'warning')
    return
  }
  saving.value = true
  try {
    const payload = { ...form.value, job_type: 'active_agent' }
    const res = await axios.post('/api/cron/jobs', payload)
    if (res.data.status === 'ok') {
      toast('创建成功')
      await loadJobs()
    } else {
      toast(res.data.message || '创建失败', 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || '创建失败', 'error')
  } finally {
    saving.value = false
  }
}

async function toggleJob(job: any) {
  try {
    const res = await axios.patch(`/api/cron/jobs/${job.job_id}`, { enabled: job.enabled })
    if (res.data.status !== 'ok') {
      toast(res.data.message || '更新失败', 'error')
      await loadJobs()
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || '更新失败', 'error')
    await loadJobs()
  }
}

async function deleteJob(job: any) {
  try {
    const res = await axios.delete(`/api/cron/jobs/${job.job_id}`)
    if (res.data.status === 'ok') {
      toast('已删除')
      jobs.value = jobs.value.filter((j) => j.job_id !== job.job_id)
    } else {
      toast(res.data.message || '删除失败', 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || '删除失败', 'error')
  }
}

onMounted(() => {
  loadJobs()
})
</script>

<style scoped>
.cron-page {
  padding: 20px;
  padding-top: 8px;
  padding-bottom: 40px;
}
</style>
