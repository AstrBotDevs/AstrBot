<template>
  <div class="error-analysis-page">
    <v-container fluid class="pa-0">
      <v-row class="px-4 py-3 align-center">
        <v-col cols="12" md="8">
          <h1 class="text-h1 font-weight-bold mb-2">
            <v-icon class="me-2">mdi-alert-decagram-outline</v-icon>鎶ラ敊璇婃柇
          </h1>
          <p class="text-subtitle-1 text-medium-emphasis mb-0">
            鑷姩璁板綍 ERROR/CRITICAL 鏃ュ織锛岀粨鍚堟簮鐮佷笂涓嬫枃杩涜 AI 鍒嗘瀽锛屽苟鏀寔缁х画杩介棶銆?
          </p>
        </v-col>
        <v-col cols="12" md="4" class="d-flex justify-end">
          <v-btn color="primary" prepend-icon="mdi-content-save-outline" :loading="savingSettings" @click="saveSettings">
            淇濆瓨璁剧疆
          </v-btn>
        </v-col>
      </v-row>

      <v-card class="mx-4 mb-4" elevation="0" variant="outlined">
        <v-card-title>璇婃柇璁剧疆</v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="4">
              <v-select
                v-model="settings.provider_id"
                :items="providerOptions"
                item-title="title"
                item-value="value"
                label="鍒嗘瀽妯″瀷"
                variant="solo-filled"
                flat
                clearable
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-select
                v-model="settings.scope"
                :items="scopeOptions"
                item-title="title"
                item-value="value"
                label="鍒嗘瀽鑼冨洿"
                variant="solo-filled"
                flat
              />
            </v-col>
            <v-col cols="12" md="5" v-if="settings.scope === 'selected_plugins'">
              <v-select
                v-model="settings.selected_plugins"
                :items="pluginOptions"
                item-title="title"
                item-value="value"
                label="鎸囧畾鎻掍欢"
                multiple
                chips
                variant="solo-filled"
                flat
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-switch v-model="settings.auto_analyze" color="primary" label="鑷姩鍒嗘瀽" inset />
            </v-col>
            <v-col cols="12" md="3">
              <v-switch v-model="settings.passive_record" color="primary" label="涓诲姩璁板綍" inset />
            </v-col>
            <v-col cols="12" md="3">
              <v-switch v-model="settings.include_source_context" color="primary" label="Include Source Context" inset />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field v-model.number="settings.dedupe_window_sec" type="number" label="Dedupe Window (sec)" variant="solo-filled" flat />
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <v-card class="mx-4 mb-4" elevation="0" variant="outlined">
        <v-card-title class="d-flex align-center">
          闂鍗＄墖
          <v-spacer />
          <v-select
            v-model="statusFilter"
            :items="statusOptions"
            item-title="title"
            item-value="value"
            label="Status Filter"
            variant="solo-filled"
            flat
            clearable
            hide-details
            style="max-width: 220px;"
          />
        </v-card-title>
        <v-card-text>
          <v-progress-linear v-if="loadingRecords" indeterminate color="primary" class="mb-3" />
          <v-row v-if="records.length">
            <v-col v-for="record in records" :key="record.id" cols="12">
              <v-card elevation="0" variant="tonal">
                <v-card-text>
                  <div class="d-flex flex-wrap align-center ga-2 mb-2">
                    <v-chip size="small" :color="statusColor(record.status)">{{ record.status }}</v-chip>
                    <v-chip size="small" :color="severityColor(record.severity)" variant="outlined">
                      {{ record.severity || 'unknown' }}
                    </v-chip>
                    <span class="text-body-2 text-medium-emphasis">{{ record.target_type }} / {{ record.target_name }}</span>
                    <v-spacer />
                    <span class="text-caption text-medium-emphasis">{{ formatTime(record.updated_at) }}</span>
                  </div>
                  <div class="text-body-1 font-weight-medium mb-1">{{ record.summary || 'No summary' }}</div>
                  <div class="text-body-2 text-medium-emphasis mb-3">{{ record.analysis?.reason || record.error_message || '' }}</div>
                  <div class="d-flex flex-wrap ga-2">
                    <v-btn size="small" variant="outlined" prepend-icon="mdi-file-document-outline" @click="openDetail(record)">
                      鏌ョ湅璇︽儏
                    </v-btn>
                    <v-btn size="small" variant="outlined" prepend-icon="mdi-refresh" :loading="manualRunningId === record.id" @click="reanalyze(record)">
                      閲嶆柊鍒嗘瀽
                    </v-btn>
                    <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-chat-outline" @click="openAsk(record)">
                      璇㈤棶 AI
                    </v-btn>
                    <v-btn size="small" color="grey" variant="text" prepend-icon="mdi-eye-off-outline" @click="ignoreRecord(record)">
                      蹇界暐
                    </v-btn>
                  </div>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>
          <div v-else class="text-medium-emphasis">鏆傛棤璇婃柇璁板綍</div>
        </v-card-text>
      </v-card>
    </v-container>

    <v-dialog v-model="detailDialog" max-width="1100">
      <v-card>
        <v-card-title class="d-flex align-center">
          璇婃柇璇︽儏
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="detailDialog = false" />
        </v-card-title>
        <v-card-text v-if="activeRecord">
          <v-row>
            <v-col cols="12" md="6">
              <v-textarea :model-value="activeRecord.log_excerpt || ''" label="鍘熷鏃ュ織" rows="8" variant="solo-filled" flat readonly />
            </v-col>
            <v-col cols="12" md="6">
              <v-textarea :model-value="activeRecord.traceback || ''" label="Traceback" rows="8" variant="solo-filled" flat readonly />
            </v-col>
            <v-col cols="12">
              <v-textarea :model-value="formatAnalysis(activeRecord.analysis)" label="AI 鍒嗘瀽缁撴灉" rows="10" variant="solo-filled" flat readonly />
            </v-col>
            <v-col cols="12" v-if="activeRecord.related_files?.length">
              <div class="text-subtitle-1 mb-2">鐩稿叧婧愮爜鐗囨</div>
              <v-expansion-panels variant="accordion">
                <v-expansion-panel v-for="(file, index) in activeRecord.related_files" :key="`${file.path}-${index}`">
                  <v-expansion-panel-title>
                    {{ file.path }} ({{ file.start_line }} - {{ file.end_line }})
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <pre class="source-block">{{ file.content }}</pre>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
    </v-dialog>

    <v-dialog v-model="askDialog" max-width="900">
      <v-card>
        <v-card-title class="d-flex align-center">
          杩介棶 AI
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" @click="askDialog = false" />
        </v-card-title>
        <v-card-text>
          <div class="text-body-2 text-medium-emphasis mb-3">
            {{ activeRecord?.summary || '' }}
          </div>
          <div class="ask-history mb-3">
            <div v-for="(msg, index) in qaMessages" :key="index" class="mb-2">
              <div class="text-caption text-medium-emphasis">{{ msg.role === 'assistant' ? 'AI' : 'User' }}</div>
              <div class="text-body-2">{{ msg.content }}</div>
            </div>
            <div v-if="streamingAnswer" class="mb-2">
              <div class="text-caption text-medium-emphasis">AI</div>
              <div class="text-body-2">{{ streamingAnswer }}</div>
            </div>
          </div>
          <v-textarea
            v-model="question"
            label="缁х画鎻愰棶"
            rows="3"
            auto-grow
            variant="solo-filled"
            flat
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="askDialog = false">鍏抽棴</v-btn>
          <v-btn color="primary" :loading="asking" @click="askAI">Send</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="top">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import axios from 'axios'
import { EventSourcePolyfill } from 'event-source-polyfill'
import { onMounted, onUnmounted, ref, watch } from 'vue'

const loadingRecords = ref(false)
const savingSettings = ref(false)
const manualRunningId = ref('')
const records = ref([])
const providerOptions = ref([])
const pluginOptions = ref([])
const statusFilter = ref('')
const detailDialog = ref(false)
const askDialog = ref(false)
const activeRecord = ref(null)
const question = ref('')
const streamingAnswer = ref('')
const asking = ref(false)
const qaMessages = ref([])
const snackbar = ref({ show: false, message: '', color: 'success' })
let eventSource = null
let eventRetryTimer = null

const settings = ref({
  auto_analyze: false,
  passive_record: true,
  provider_id: '',
  scope: 'all',
  selected_plugins: [],
  levels: ['ERROR', 'CRITICAL'],
  include_source_context: true,
  dedupe_window_sec: 600
})

const scopeOptions = [
  { title: 'All', value: 'all' },
  { title: 'Core Only', value: 'core' },
  { title: 'All Plugins', value: 'all_plugins' },
  { title: 'Selected Plugins', value: 'selected_plugins' }
]

const statusOptions = [
  { title: 'Analyzing', value: 'analyzing' },
  { title: 'Pending', value: 'pending' },
  { title: 'Done', value: 'done' },
  { title: 'Failed', value: 'failed' },
  { title: 'Ignored', value: 'ignored' }
]

function showMessage(message, color = 'success') {
  snackbar.value = { show: true, message, color }
}

function statusColor(status) {
  const map = {
    pending: 'grey',
    analyzing: 'blue',
    done: 'success',
    failed: 'error',
    ignored: 'grey-darken-1'
  }
  return map[status] || 'grey'
}

function severityColor(severity) {
  const map = {
    low: 'green',
    medium: 'amber',
    high: 'red',
    critical: 'purple',
    unknown: 'grey'
  }
  return map[severity] || 'grey'
}

function formatTime(ts) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString()
}

function formatAnalysis(analysis) {
  if (!analysis) return ''
  try {
    return JSON.stringify(analysis, null, 2)
  } catch {
    return String(analysis || '')
  }
}

function upsertRecord(record) {
  const index = records.value.findIndex(item => item.id === record.id)
  if (index === -1) {
    records.value.unshift(record)
    return
  }
  records.value[index] = record
}

async function loadSettings() {
  const res = await axios.get('/api/error-analysis/settings')
  if (res.data.status === 'ok') {
    settings.value = { ...settings.value, ...res.data.data }
  }
}

async function saveSettings() {
  savingSettings.value = true
  try {
    const res = await axios.post('/api/error-analysis/settings', settings.value)
    if (res.data.status === 'ok') {
      settings.value = { ...settings.value, ...res.data.data }
      showMessage('Settings saved')
    } else {
      showMessage(res.data.message || '淇濆瓨澶辫触', 'error')
    }
  } catch (err) {
    showMessage(err.response?.data?.message || err.message || '淇濆瓨澶辫触', 'error')
  } finally {
    savingSettings.value = false
  }
}

async function loadProviders() {
  const res = await axios.get('/api/config/provider/list?provider_type=chat_completion')
  if (res.data.status === 'ok' && Array.isArray(res.data.data)) {
    providerOptions.value = res.data.data.map(item => ({
      title: item.id,
      value: item.id
    }))
  }
}

async function loadPlugins() {
  const res = await axios.get('/api/plugin/get')
  if (res.data.status === 'ok' && Array.isArray(res.data.data)) {
    pluginOptions.value = res.data.data.map(item => ({
      title: item.name,
      value: item.name
    }))
  }
}

async function loadRecords() {
  loadingRecords.value = true
  try {
    const params = {}
    if (statusFilter.value) {
      params.status = statusFilter.value
    }
    const res = await axios.get('/api/error-analysis/records', { params })
    if (res.data.status === 'ok') {
      records.value = res.data.data.items || []
    }
  } finally {
    loadingRecords.value = false
  }
}

async function reanalyze(record) {
  manualRunningId.value = record.id
  try {
    const res = await axios.post('/api/error-analysis/analyze', {
      record_id: record.id,
      provider_id: settings.value.provider_id || undefined
    })
    if (res.data.status === 'ok') {
      upsertRecord(res.data.data)
      showMessage('Re-analyzed')
    } else {
      showMessage(res.data.message || '鍒嗘瀽澶辫触', 'error')
    }
  } catch (err) {
    showMessage(err.response?.data?.message || err.message || '鍒嗘瀽澶辫触', 'error')
  } finally {
    manualRunningId.value = ''
  }
}

async function ignoreRecord(record) {
  try {
    const res = await axios.post('/api/error-analysis/ignore', { record_id: record.id })
    if (res.data.status === 'ok') {
      upsertRecord(res.data.data)
      showMessage('Ignored')
    } else {
      showMessage(res.data.message || '鎿嶄綔澶辫触', 'error')
    }
  } catch (err) {
    showMessage(err.response?.data?.message || err.message || '鎿嶄綔澶辫触', 'error')
  }
}

function openDetail(record) {
  activeRecord.value = record
  detailDialog.value = true
}

function openAsk(record) {
  activeRecord.value = record
  qaMessages.value = Array.isArray(record.qa_messages) ? [...record.qa_messages] : []
  question.value = ''
  streamingAnswer.value = ''
  askDialog.value = true
}

async function askAI() {
  if (!activeRecord.value || !question.value.trim()) {
    return
  }
  asking.value = true
  streamingAnswer.value = ''
  let hadError = false
  try {
    const token = localStorage.getItem('token')
    const response = await fetch('/api/error-analysis/ask/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: token ? `Bearer ${token}` : ''
      },
      body: JSON.stringify({
        record_id: activeRecord.value.id,
        question: question.value,
        provider_id: settings.value.provider_id || undefined
      })
    })
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No stream body')
    }
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const chunks = buffer.split('\n\n')
      buffer = chunks.pop() || ''
      for (const chunk of chunks) {
        const line = chunk
          .split('\n')
          .find(content => content.startsWith('data:'))
        if (!line) continue
        const payload = JSON.parse(line.slice(5).trim())
        if (payload.type === 'delta') {
          streamingAnswer.value += payload.data || ''
        } else if (payload.type === 'done') {
          if (hadError || !streamingAnswer.value.trim()) {
            continue
          }
          qaMessages.value.push({ role: 'user', content: question.value })
          qaMessages.value.push({ role: 'assistant', content: streamingAnswer.value })
          question.value = ''
          await loadRecords()
        } else if (payload.type === 'error') {
          hadError = true
          showMessage(payload.message || '杩介棶澶辫触', 'error')
        }
      }
    }
  } catch (err) {
    showMessage(err.message || '杩介棶澶辫触', 'error')
  } finally {
    asking.value = false
  }
}

function connectEvents() {
  if (eventRetryTimer) {
    clearTimeout(eventRetryTimer)
    eventRetryTimer = null
  }
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  const token = localStorage.getItem('token')
  eventSource = new EventSourcePolyfill('/api/error-analysis/events', {
    headers: {
      Authorization: token ? `Bearer ${token}` : ''
    },
    heartbeatTimeout: 300000,
    withCredentials: true
  })
  eventSource.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data)
      if (payload.type === 'record_created' || payload.type === 'record_updated') {
        upsertRecord(payload.record)
      }
    } catch {
      // noop
    }
  }
  eventSource.onerror = () => {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    eventRetryTimer = setTimeout(connectEvents, 2000)
  }
}

watch(statusFilter, () => {
  loadRecords()
})

onMounted(async () => {
  await Promise.all([loadSettings(), loadProviders(), loadPlugins(), loadRecords()])
  connectEvents()
})

onUnmounted(() => {
  if (eventRetryTimer) {
    clearTimeout(eventRetryTimer)
    eventRetryTimer = null
  }
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
})
</script>

<style scoped>
.error-analysis-page {
  padding: 20px;
  padding-top: 8px;
  padding-bottom: 40px;
}

.source-block {
  background: #111827;
  color: #d1d5db;
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  margin: 0;
}

.ask-history {
  max-height: 340px;
  overflow-y: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  padding: 12px;
}
</style>


