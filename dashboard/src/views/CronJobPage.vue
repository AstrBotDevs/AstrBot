<template>
  <div class="cron-page">
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <div class="d-flex align-center" style="gap: 8px;">
          <h2 class="text-h5 font-weight-bold">未来任务管理</h2>
          <v-chip size="x-small" color="orange-darken-2" variant="tonal" label>Beta</v-chip>
        </div>
        <div class="text-body-2 text-medium-emphasis">
          查看给 AstrBot 布置的未来任务。AstrBot 将会被自动唤醒、执行任务，然后将结果告知任务布置方。
          主动发送结果仅支持以下平台：
          <span v-if="proactivePlatforms.length">
            {{ proactivePlatforms.map((p) => `${p.display_name || p.name}(${p.id})`).join('、') }}
          </span>
          <span v-else>暂无支持主动消息的平台，请在平台设置中开启。</span>
        </div>
      </div>
      <div class="d-flex align-center" style="gap: 8px;">
        <v-btn variant="tonal" color="primary" @click="openCreate">新建任务</v-btn>
        <v-btn variant="tonal" color="primary" :loading="loading" @click="loadJobs">刷新</v-btn>
      </div>
    </div>

    <v-card class="rounded-lg" variant="flat">
      <v-card-text>
        <div class="d-flex align-center justify-space-between mb-3">
          <div class="text-subtitle-1 font-weight-bold">已注册任务</div>
        </div>

        <v-alert v-if="!jobs.length && !loading" type="info" variant="tonal">暂无任务。</v-alert>

        <v-data-table :items="jobs" :headers="headers" :loading="loading" item-key="job_id" density="comfortable"
          class="elevation-0">
          <template #item.name="{ item }">
            <div class="font-weight-medium">{{ item.name }}</div>
            <div class="text-caption text-medium-emphasis">{{ item.description }}</div>
          </template>
          <template #item.type="{ item }">
            <v-chip size="small" :color="item.run_once ? 'orange' : 'primary'" variant="tonal">
              {{ item.run_once ? '一次性' : (item.job_type || 'active_agent') }}
            </v-chip>
          </template>
          <template #item.cron_expression="{ item }">
            <div v-if="item.run_once">{{ formatTime(item.run_at) }}</div>
            <div v-else>
              <div>{{ item.cron_expression || '—' }}</div>
              <div class="text-caption text-medium-emphasis">{{ item.timezone || 'local' }}</div>
            </div>
          </template>
          <template #item.next_run_time="{ item }">{{ formatTime(item.next_run_time) }}</template>
          <template #item.last_run_at="{ item }">{{ formatTime(item.last_run_at) }}</template>
          <template #item.note="{ item }">{{ item.note || '—' }}</template>
          <template #item.actions="{ item }">
            <div class="d-flex" style="gap: 8px;">
              <v-switch v-model="item.enabled" inset density="compact" hide-details color="primary"
                @change="toggleJob(item)" />
              <v-btn size="small" variant="text" color="primary" @click="deleteJob(item)">删除</v-btn>
            </div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="2600">
      {{ snackbar.message }}
    </v-snackbar>

    <v-dialog v-model="createDialog" max-width="560">
      <v-card>
        <v-card-title class="text-h6">新建任务</v-card-title>
        <v-card-text>
          <v-switch v-model="newJob.run_once" label="一次性任务" inset color="primary" hide-details />
          <v-text-field v-model="newJob.name" label="任务名称" variant="outlined" density="comfortable" />
          <v-text-field v-model="newJob.note" label="任务说明" variant="outlined" density="comfortable" />
          <v-text-field
            v-if="!newJob.run_once"
            v-model="newJob.cron_expression"
            label="Cron 表达式"
            placeholder="0 9 * * *"
            variant="outlined"
            density="comfortable"
          />
          <v-text-field
            v-else
            v-model="newJob.run_at"
            label="执行时间"
            type="datetime-local"
            variant="outlined"
            density="comfortable"
          />
          <v-text-field
            v-model="newJob.session"
            label="目标 session (platform_id:message_type:session_id)"
            variant="outlined"
            density="comfortable"
          />
          <v-text-field
            v-model="newJob.timezone"
            label="时区（可选，如 Asia/Shanghai）"
            variant="outlined"
            density="comfortable"
          />
          <v-switch v-model="newJob.enabled" label="启用" inset color="primary" hide-details />
        </v-card-text>
        <v-card-actions class="justify-end">
          <v-btn variant="text" @click="createDialog = false">取消</v-btn>
          <v-btn variant="tonal" color="primary" :loading="creating" @click="createJob">创建</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import axios from 'axios'

const loading = ref(false)
const jobs = ref<any[]>([])
const proactivePlatforms = ref<{ id: string; name: string; display_name?: string }[]>([])
const createDialog = ref(false)
const creating = ref(false)
const newJob = ref({
  run_once: false,
  name: '',
  note: '',
  cron_expression: '',
  run_at: '',
  session: '',
  timezone: '',
  enabled: true
})

const snackbar = ref({ show: false, message: '', color: 'success' })

const headers = [
  { title: '名称', key: 'name', minWidth: '200px' },
  { title: '类型', key: 'type', width: 110 },
  { title: 'Cron', key: 'cron_expression', minWidth: '160px' },
  { title: '下一次执行', key: 'next_run_time', minWidth: '160px' },
  { title: '最近执行', key: 'last_run_at', minWidth: '160px' },
  { title: '说明', key: 'note', minWidth: '220px' },
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

async function loadPlatforms() {
  try {
    const res = await axios.get('/api/platform/stats')
    if (res.data.status === 'ok' && Array.isArray(res.data.data?.platforms)) {
      proactivePlatforms.value = res.data.data.platforms
        .filter((p: any) => p?.meta?.support_proactive_message)
        .map((p: any) => ({
          id: p?.id || p?.meta?.id || 'unknown',
          name: p?.meta?.name || p?.type || '',
          display_name: p?.meta?.display_name || p?.display_name
        }))
    }
  } catch (e) {
    // ignore platform fetch errors in UI; subtitle will show fallback
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

function openCreate() {
  resetNewJob()
  createDialog.value = true
}

function resetNewJob() {
  newJob.value = {
    run_once: false,
    name: '',
    note: '',
    cron_expression: '',
    run_at: '',
    session: '',
    timezone: '',
    enabled: true
  }
}

async function createJob() {
  if (!newJob.value.session) {
    toast('请填写 session', 'warning')
    return
  }
  if (!newJob.value.note) {
    toast('请填写说明', 'warning')
    return
  }
  if (!newJob.value.run_once && !newJob.value.cron_expression) {
    toast('请填写 Cron 表达式', 'warning')
    return
  }
  if (newJob.value.run_once && !newJob.value.run_at) {
    toast('请选择执行时间', 'warning')
    return
  }
  creating.value = true
  try {
    const payload: any = { ...newJob.value }
    const res = await axios.post('/api/cron/jobs', payload)
    if (res.data.status === 'ok') {
      toast('创建成功')
      createDialog.value = false
      resetNewJob()
      await loadJobs()
    } else {
      toast(res.data.message || '创建失败', 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || '创建失败', 'error')
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  loadJobs()
  loadPlatforms()
})
</script>

<style scoped>
.cron-page {
  padding: 20px;
  padding-top: 8px;
  padding-bottom: 40px;
}
</style>
