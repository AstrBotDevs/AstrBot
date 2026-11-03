<template>
  <section class="dashboard-card dashboard-card--padded">
    <div class="d-flex align-center justify-space-between mb-3">
      <h2 class="text-h5">{{ tm('progress.title') }}</h2>
      <v-btn variant="text" :loading="loading" prepend-icon="mdi-refresh" @click="reload">
        {{ tm('actions.refresh') }}
      </v-btn>
    </div>
    <p class="text-body-2 mb-3">{{ tm('progress.hint') }}</p>
    <v-alert v-if="error" type="error" variant="tonal" class="mb-3">{{ error }}</v-alert>
    <v-table v-if="workers.length" hover>
      <thead><tr>
        <th>{{ tm('progress.worker') }}</th><th>{{ tm('progress.state') }}</th>
        <th>{{ tm('progress.task') }}</th><th>{{ tm('progress.steps') }}</th>
      </tr></thead>
      <tbody><tr v-for="worker in workers" :key="worker.agent_id" @click="inspect(worker.agent_id)" class="cursor-pointer">
        <td>{{ worker.name }}</td><td>{{ tm(`progress.states.${worker.state}`) }}</td>
        <td class="worker-task">{{ worker.task }}</td><td>{{ worker.completed_steps }}</td>
      </tr></tbody>
    </v-table>
    <p v-else class="text-medium-emphasis py-4">{{ tm('progress.empty') }}</p>
    <v-dialog v-model="dialog" max-width="900" scrollable>
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ selected?.name }}</v-card-title>
        <v-card-text>
          <v-progress-linear v-if="detailLoading" indeterminate />
          <template v-if="selected">
            <p class="mb-3">{{ selected.task }}</p>
            <v-alert v-if="selected.error" type="error" variant="tonal">{{ selected.error }}</v-alert>
            <pre v-if="selected.result" class="worker-content mb-4">{{ selected.result }}</pre>
            <div v-for="(message, index) in selected.messages" :key="index" class="mb-4">
              <strong>{{ message.role }}</strong>
              <pre class="worker-content">{{ formatContent(message.content) }}</pre>
            </div>
          </template>
        </v-card-text>
        <v-card-actions><v-spacer /><v-btn variant="text" @click="dialog = false">{{ tm('actions.close') }}</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </section>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { subagentApi, type SubAgentWorker } from '@/api/v1'
import { useModuleI18n } from '@/i18n/composables'

const { tm } = useModuleI18n('features/subagent')
const workers = ref<SubAgentWorker[]>([])
const selected = ref<SubAgentWorker | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const dialog = ref(false)
const error = ref('')
let timer: ReturnType<typeof setInterval> | undefined
let mounted = true

async function reload() {
  if (loading.value) return
  loading.value = true
  try {
    const response = await subagentApi.runtime()
    if (mounted) {
      workers.value = response.data.data?.agents ?? []
      error.value = ''
    }
  } catch {
    if (mounted) error.value = tm('progress.loadFailed')
  } finally {
    if (mounted) loading.value = false
  }
}

async function inspect(agentId: string) {
  selected.value = workers.value.find(worker => worker.agent_id === agentId) ?? null
  dialog.value = true
  detailLoading.value = true
  try {
    const response = await subagentApi.runtime(agentId)
    if (mounted && selected.value?.agent_id === agentId) selected.value = response.data.data?.agents[0] ?? null
  } catch {
    if (mounted) error.value = tm('progress.loadFailed')
  } finally {
    if (mounted) detailLoading.value = false
  }
}

function formatContent(content: unknown) {
  if (typeof content === 'string') return content
  return JSON.stringify(content, null, 2)
}

onMounted(() => {
  reload()
  timer = setInterval(reload, 3000)
})
onBeforeUnmount(() => {
  mounted = false
  clearInterval(timer)
})
</script>

<style scoped>
.worker-content { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
.worker-task { max-width: 400px; white-space: normal; overflow-wrap: anywhere; }
</style>
