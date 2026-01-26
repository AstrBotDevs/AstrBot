<template>
  <div class="subagent-page">
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <h2 class="text-h5 font-weight-bold">SubAgent 编排</h2>
        <div class="text-body-2 text-medium-emphasis">
          主 LLM 只负责聊天与分派（handoff），工具挂载在各个 SubAgent 上。
        </div>
      </div>

      <div class="d-flex align-center" style="gap: 8px;">
        <v-btn variant="tonal" color="primary" :loading="loading" @click="reload">刷新</v-btn>
        <v-btn variant="flat" color="primary" :loading="saving" @click="save">保存</v-btn>
      </div>
    </div>

    <v-card class="rounded-lg" variant="flat">
      <v-card-text>
        <v-row>
          <v-col cols="12" md="6">
            <v-switch
              v-model="cfg.main_enable"
              inset
              color="primary"
              label="启用 SubAgent 分派模式（主 LLM 仅通过 transfer_to_* 委派）"
              hide-details
            />
          </v-col>
        </v-row>

        <div class="text-caption text-medium-emphasis mt-1">
          启用后：主 LLM 只会看到 transfer_to_*，不会直接注入/调用其他工具；所有工具调用交给 SubAgent 完成。
          关闭后：恢复原有行为（按 persona 选择并直接注入工具）。
        </div>

        <v-alert
          type="info"
          variant="tonal"
          class="mt-3"
        >
          Router Prompt 当前使用系统内置默认值，暂不支持在 WebUI 中自定义。
        </v-alert>

        <div class="d-flex align-center justify-space-between mt-6 mb-2">
          <div class="text-subtitle-1 font-weight-bold">SubAgents</div>
          <v-btn
            size="small"
            variant="tonal"
            color="primary"
            @click="addAgent"
          >
            新增 SubAgent
          </v-btn>
        </div>

        <v-expansion-panels variant="accordion" multiple>
          <v-expansion-panel
            v-for="(agent, idx) in cfg.agents"
            :key="agent.__key"
          >
            <v-expansion-panel-title>
              <div class="d-flex align-center justify-space-between" style="width: 100%;">
                <div class="d-flex align-center" style="gap: 10px; min-width: 0;">
                  <v-chip
                    :color="agent.enabled ? 'success' : 'grey'"
                    size="small"
                    variant="tonal"
                  >
                    {{ agent.enabled ? '启用' : '停用' }}
                  </v-chip>
                  <div class="text-body-1 font-weight-medium text-truncate" style="max-width: 520px;">
                    {{ agent.name || '未命名 SubAgent' }}
                  </div>
                </div>

                <div class="d-flex align-center" style="gap: 8px;">
                  <v-btn
                    size="small"
                    variant="text"
                    color="error"
                    @click.stop="removeAgent(idx)"
                  >
                    删除
                  </v-btn>
                </div>
              </div>
            </v-expansion-panel-title>

            <v-expansion-panel-text>
              <v-row>
                <v-col cols="12" md="4">
                  <v-text-field
                    v-model="agent.name"
                    label="Agent 名称（用于 transfer_to_{name}）"
                    variant="outlined"
                    density="comfortable"
                    hint="建议使用英文小写+下划线，且全局唯一"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12" md="3">
                  <v-switch
                    v-model="agent.enabled"
                    inset
                    color="primary"
                    label="启用"
                    hide-details
                  />
                </v-col>
                <v-col cols="12" md="5">
                  <v-autocomplete
                    v-model="agent.tools"
                    :items="toolOptions"
                    item-title="title"
                    item-value="value"
                    label="分配工具（多选）"
                    variant="outlined"
                    density="comfortable"
                    multiple
                    chips
                    closable-chips
                    :loading="toolsLoading"
                    :disabled="toolsLoading"
                    clearable
                  />
                </v-col>
              </v-row>

              <v-textarea
                v-model="agent.description"
                label="SubAgent 描述 / 指令"
                variant="outlined"
                rows="3"
                auto-grow
                hint="主 LLM 主要通过这里的描述来决定是否 handoff 到该 SubAgent。"
                persistent-hint
              />

              <div class="mt-3">
                <div class="text-caption text-medium-emphasis">预览：主 LLM 将看到的 handoff 工具</div>
                <div class="d-flex align-center" style="gap: 8px; flex-wrap: wrap;">
                  <v-chip size="small" variant="outlined" color="primary">
                    transfer_to_{{ agent.name || '...' }}
                  </v-chip>
                  <v-chip
                    v-for="t in (agent.tools || [])"
                    :key="t"
                    size="small"
                    variant="tonal"
                    color="secondary"
                  >
                    {{ t }}
                  </v-chip>
                </div>
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>

      </v-card-text>
    </v-card>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="3000">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import axios from 'axios'

type ToolOption = { title: string; value: string }

type SubAgentItem = {
  __key: string
  name: string
  description: string
  tools: string[]
  enabled: boolean
}

type SubAgentConfig = {
  main_enable: boolean
  main_tools_policy: 'handoff_only' | 'persona'
  agents: SubAgentItem[]
}

const loading = ref(false)
const saving = ref(false)
const toolsLoading = ref(false)

const snackbar = ref({
  show: false,
  message: '',
  color: 'success'
})

function toast(message: string, color: 'success' | 'error' | 'warning' = 'success') {
  snackbar.value = { show: true, message, color }
}

const mainToolPolicies = [
  { label: 'handoff_only（主 LLM 仅 transfer_to_*）', value: 'handoff_only' },
  { label: 'persona（仍按 persona 选择工具）', value: 'persona' }
]

const cfg = ref<SubAgentConfig>({
  main_enable: false,
  main_tools_policy: 'handoff_only',
  agents: []
})


const toolOptions = ref<ToolOption[]>([])

function normalizeConfig(raw: any): SubAgentConfig {
  const main_enable = !!raw?.main_enable
  const main_tools_policy = (raw?.main_tools_policy === 'persona' ? 'persona' : 'handoff_only')
  const agentsRaw = Array.isArray(raw?.agents) ? raw.agents : []

  const agents: SubAgentItem[] = agentsRaw.map((a: any, i: number) => {
    const name = (a?.name ?? '').toString()
    const description = (a?.description ?? '').toString()
    const tools = Array.isArray(a?.tools) ? a.tools.map((x: any) => String(x)) : []
    const enabled = a?.enabled !== false

    return {
      __key: `${Date.now()}_${i}_${Math.random().toString(16).slice(2)}`,
      name,
      description,
      tools,
      enabled
    }
  })

  return { main_enable, main_tools_policy, agents }
}

async function loadConfig() {
  loading.value = true
  try {
    const res = await axios.get('/api/subagent/config')
    if (res.data.status === 'ok') {
      cfg.value = normalizeConfig(res.data.data)
    } else {
      toast(res.data.message || '获取配置失败', 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || '获取配置失败', 'error')
  } finally {
    loading.value = false
  }
}

async function loadTools() {
  toolsLoading.value = true
  try {
    // Prefer our dedicated endpoint (includes handler_module_path)
    const res = await axios.get('/api/subagent/available-tools')
    if (res.data.status === 'ok') {
      const list = Array.isArray(res.data.data) ? res.data.data : []
      toolOptions.value = list
        .filter((t: any) => !!t?.name)
        .map((t: any) => {
          const name = String(t.name)
          const desc = (t.description ?? '').toString().trim()
          return { title: desc ? `${name} — ${desc}` : name, value: name }
        })
    } else {
      toast(res.data.message || '获取工具列表失败', 'error')
    }
  } catch {
    // Fallback to existing tools list endpoint
    try {
      const res2 = await axios.get('/api/tools/list')
      if (res2.data.status === 'ok') {
        const list = Array.isArray(res2.data.data) ? res2.data.data : []
        toolOptions.value = list
          .filter((t: any) => !!t?.name)
          .map((t: any) => {
            const name = String(t.name)
            const desc = (t.description ?? '').toString().trim()
            return { title: desc ? `${name} — ${desc}` : name, value: name }
          })
      }
    } catch {
      toast('获取工具列表失败', 'error')
    }
  } finally {
    toolsLoading.value = false
  }
}

function addAgent() {
  cfg.value.agents.push({
    __key: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
    name: '',
    description: '',
    tools: [],
    enabled: true
  })
}

function removeAgent(idx: number) {
  cfg.value.agents.splice(idx, 1)
}

async function save() {
  saving.value = true
  try {
    // Strip UI-only fields
    const payload = {
      main_enable: cfg.value.main_enable,
      // Reserved for future; backend treats main_enable as handoff-only.
      main_tools_policy: 'handoff_only',
      agents: cfg.value.agents.map(a => ({
        name: a.name,
        description: a.description,
        tools: a.tools,
        enabled: a.enabled
      }))
    }

    const res = await axios.post('/api/subagent/config', payload)
    if (res.data.status === 'ok') {
      toast(res.data.message || '保存成功', 'success')
    } else {
      toast(res.data.message || '保存失败', 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || '保存失败', 'error')
  } finally {
    saving.value = false
  }
}

async function reload() {
  await Promise.all([loadConfig(), loadTools()])
}

onMounted(() => {
  reload()
})
</script>

<style scoped>
.subagent-page {
  padding: 20px;
  padding-top: 8px;
  padding-bottom: 40px;
}
</style>
