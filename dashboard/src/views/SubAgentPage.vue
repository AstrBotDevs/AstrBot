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
          <v-col cols="12" md="8">
            <v-select
              v-model="cfg.main_mode"
              :items="mainModes"
              item-title="label"
              item-value="value"
              label="SubAgent 模式"
              variant="outlined"
              density="comfortable"
              hide-details
            />
          </v-col>
        </v-row>

        <div class="text-caption text-medium-emphasis mt-1">
          <div v-if="cfg.main_mode === 'disabled'">
            不启动：SubAgent 关闭；主 LLM 按 persona 规则挂载工具（默认全部），并直接调用。
          </div>
          <div v-else-if="cfg.main_mode === 'unassigned_to_main'">
            启动：SubAgent 可分派；未分配给任何 SubAgent 的工具仍挂载到主 LLM 上。
          </div>
          <div v-else>
            启动：仅 SubAgent；主 LLM 只保留 transfer_to_* 这类委派工具，不挂载其他工具。
          </div>
        </div>

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
              <div class="subagent-panel-title">
                <div class="subagent-title-left">
                  <v-chip
                    :color="agent.enabled ? 'success' : 'grey'"
                    size="small"
                    variant="tonal"
                  >
                    {{ agent.enabled ? '启用' : '停用' }}
                  </v-chip>

                  <div class="subagent-title-text">
                    <div class="subagent-title-name">{{ agent.name || '未命名 SubAgent' }}</div>
                    <div class="subagent-title-sub">transfer_to_{{ agent.name || '...' }}</div>
                  </div>
                </div>

                <div class="subagent-title-right">
                  <v-switch
                    v-model="agent.enabled"
                    inset
                    color="primary"
                    hide-details
                    class="subagent-enabled-inline"
                    @click.stop
                  >
                    <template #label>启用</template>
                  </v-switch>

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
              <v-row class="subagent-grid">
                <v-col cols="12" md="5">
                  <v-text-field
                    v-model="agent.name"
                    label="Agent 名称（用于 transfer_to_{name}）"
                    variant="outlined"
                    density="comfortable"
                    hint="建议使用英文小写+下划线，且全局唯一"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12" md="7" class="subagent-actions">
                  <ProviderSelector
                    v-model="agent.provider_id"
                    provider-type="chat_completion"
                    label="Chat Provider（可选）"
                    hint="留空表示跟随全局默认 provider。"
                    persistent-hint
                    clearable
                    class="subagent-provider"
                  />
                </v-col>
                <v-col cols="12">
                  <v-autocomplete
                    v-model="agent.__tool_group"
                    :items="toolGroupOptions"
                    item-title="title"
                    item-value="value"
                    label="选择插件/来源"
                    variant="outlined"
                    density="comfortable"
                    class="subagent-tools"
                    :loading="toolsLoading"
                    :disabled="toolsLoading"
                    clearable
                    @update:modelValue="onGroupChanged(agent)"
                  />
                </v-col>

                <v-col cols="12">
                  <v-autocomplete
                    v-model="agent.__tool_group_selected"
                    :items="getToolOptionsByGroup(agent.__tool_group)"
                    item-title="title"
                    item-value="value"
                    label="选择该插件下的工具（多选）"
                    variant="outlined"
                    density="comfortable"
                    class="subagent-tools"
                    multiple
                    chips
                    closable-chips
                    :menu-props="{ maxHeight: 380 }"
                    :max-chips="8"
                    :loading="toolsLoading"
                    :disabled="toolsLoading || !agent.__tool_group"
                    clearable
                    @update:modelValue="syncGroupSelectionToAgentTools(agent)"
                  />

                  <div class="text-caption text-medium-emphasis mt-1">
                    已分配：{{ (agent.tools || []).length }} 个工具
                  </div>
                </v-col>
              </v-row>

              <v-textarea
                v-model="agent.public_description"
                label="对主 LLM 的描述（用于决定是否 handoff）"
                variant="outlined"
                rows="3"
                auto-grow
                hint="这段会作为 transfer_to_* 工具的描述给主 LLM 看，建议简短明确。"
                persistent-hint
              />

              <v-textarea
                v-model="agent.system_prompt"
                label="SubAgent System Prompt（该 SubAgent 自己的指令）"
                variant="outlined"
                rows="4"
                auto-grow
                hint="这段只给该 SubAgent 自己作为 system prompt 使用，可以更长、更严格。"
                persistent-hint
                class="mt-3"
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
import ProviderSelector from '@/components/shared/ProviderSelector.vue'

type ToolOption = { title: string; value: string }

type ToolGroup = {
  key: string
  label: string
  options: ToolOption[]
}

type SubAgentItem = {
  __key: string
  name: string
  public_description: string
  system_prompt: string
  tools: string[]
  enabled: boolean
  provider_id?: string
  // UI-only: current tool group selection state
  __tool_group?: string
  __tool_group_selected?: string[]
}

type MainMode = 'disabled' | 'unassigned_to_main' | 'handoff_only'

type SubAgentConfig = {
  main_mode: MainMode
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

const mainModes: Array<{ label: string; value: MainMode }> = [
  { label: '不启动：SubAgent 关闭（主 LLM 按 persona 挂载工具）', value: 'disabled' },
  { label: '启动：未分配工具仍挂载到主 LLM', value: 'unassigned_to_main' },
  { label: '启动：仅 SubAgent（主 LLM 仅 transfer_to_*）', value: 'handoff_only' }
]

const cfg = ref<SubAgentConfig>({
  main_mode: 'disabled',
  agents: []
})


const toolGroups = ref<ToolGroup[]>([])
const toolGroupOptions = ref<{ title: string; value: string }[]>([])

function modulePathToLabel(mp: unknown): string {
  const raw = (mp ?? '').toString().trim()
  if (!raw) return '其他/未归类'
  // Typical module paths look like:
  // - data.plugins.<plugin_name>.main
  // - astrbot.builtin_stars.<star_name>.main
  // - astrbot.plugins.<plugin_name>.main
  // We strip common prefixes and the trailing ".main" for display.
  const trimmed = raw.replace(/\.main$/, '')
  if (trimmed.startsWith('data.plugins.')) return trimmed.replace(/^data\.plugins\./, '')
  if (trimmed.startsWith('astrbot.builtin_stars.')) return `builtin: ${trimmed.replace(/^astrbot\.builtin_stars\./, '')}`
  if (trimmed.startsWith('astrbot.plugins.')) return trimmed.replace(/^astrbot\.plugins\./, '')
  if (raw.startsWith('plugins.')) return raw.replace(/^plugins\./, '')
  if (raw.startsWith('builtin_stars.')) return `builtin: ${raw.replace(/^builtin_stars\./, '')}`
  if (raw.startsWith('core.')) return `core: ${raw.replace(/^core\./, '')}`
  return raw
}

function rebuildToolGroupOptions() {
  toolGroupOptions.value = toolGroups.value.map(g => ({ title: g.label, value: g.key }))
}

function getToolOptionsByGroup(groupKey: string | undefined): ToolOption[] {
  if (!groupKey) return []
  return toolGroups.value.find(g => g.key === groupKey)?.options ?? []
}

function onGroupChanged(agent: SubAgentItem) {
  // When switching groups, reflect already-assigned tools for that group.
  const groupOptions = getToolOptionsByGroup(agent.__tool_group)
  const allowed = new Set(groupOptions.map(o => o.value))
  agent.__tool_group_selected = (agent.tools || []).filter(t => allowed.has(t))
}

function syncGroupSelectionToAgentTools(agent: SubAgentItem) {
  const groupOptions = getToolOptionsByGroup(agent.__tool_group)
  const allowed = new Set(groupOptions.map(o => o.value))

  const selected = Array.isArray(agent.__tool_group_selected)
    ? agent.__tool_group_selected
    : []

  // Replace only tools belonging to this group; keep tools from other groups intact.
  const kept = (agent.tools || []).filter(t => !allowed.has(t))
  const merged = [...kept, ...selected.filter(t => allowed.has(t))]

  const seen = new Set<string>()
  agent.tools = merged.filter(t => (seen.has(t) ? false : (seen.add(t), true)))
}

function normalizeConfig(raw: any): SubAgentConfig {
  const main_enable = !!raw?.main_enable
  const policy = (raw?.main_tools_policy ?? '').toString().trim()
  const main_mode: MainMode = !main_enable
    ? 'disabled'
    : (policy === 'unassigned_to_main' ? 'unassigned_to_main' : 'handoff_only')
  const agentsRaw = Array.isArray(raw?.agents) ? raw.agents : []

  const agents: SubAgentItem[] = agentsRaw.map((a: any, i: number) => {
    const name = (a?.name ?? '').toString()
    const public_description = (a?.public_description ?? '').toString()
    const system_prompt = (a?.system_prompt ?? '').toString()
    const tools = Array.isArray(a?.tools) ? a.tools.map((x: any) => String(x)) : []
    const enabled = a?.enabled !== false
    const provider_id = (a?.provider_id ?? undefined) as (string | undefined)

    return {
      __key: `${Date.now()}_${i}_${Math.random().toString(16).slice(2)}`,
      name,
      public_description,
      system_prompt,
      tools,
      enabled
      ,
      provider_id,
      __tool_group: undefined,
      __tool_group_selected: []
    }
  })

  return { main_mode, agents }
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
      const groups = new Map<string, ToolOption[]>()
      for (const t of list) {
        if (!t?.name) continue
        const name = String(t.name)
        const desc = (t.description ?? '').toString().trim()
        const mp = (t.handler_module_path ?? '').toString()
        const key = mp || '__other__'
        const options = groups.get(key) ?? []
        options.push({ title: desc ? `${name} — ${desc}` : name, value: name })
        groups.set(key, options)
      }

      toolGroups.value = Array.from(groups.entries())
        .map(([key, options]) => ({
          key,
          label: modulePathToLabel(key === '__other__' ? '' : key),
          options: options.sort((a, b) => a.value.localeCompare(b.value))
        }))
        .sort((a, b) => a.label.localeCompare(b.label))

      rebuildToolGroupOptions()
    } else {
      toast(res.data.message || '获取工具列表失败', 'error')
    }
  } catch {
    // Fallback to existing tools list endpoint
    try {
      const res2 = await axios.get('/api/tools/list')
      if (res2.data.status === 'ok') {
        const list = Array.isArray(res2.data.data) ? res2.data.data : []
        const options = list
          .filter((t: any) => !!t?.name)
          .map((t: any) => {
            const name = String(t.name)
            const desc = (t.description ?? '').toString().trim()
            return { title: desc ? `${name} — ${desc}` : name, value: name }
          })
          .sort((a: ToolOption, b: ToolOption) => a.value.localeCompare(b.value))

        toolGroups.value = [
          {
            key: '__all__',
            label: '全部工具',
            options
          }
        ]
        rebuildToolGroupOptions()
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
    public_description: '',
    system_prompt: '',
    tools: [],
    enabled: true,
    provider_id: undefined,
    __tool_group: undefined,
    __tool_group_selected: []
  })
}

function removeAgent(idx: number) {
  cfg.value.agents.splice(idx, 1)
}

function validateBeforeSave(): boolean {
  const nameRe = /^[a-z][a-z0-9_]{0,63}$/
  const seen = new Set<string>()
  for (const a of cfg.value.agents) {
    const name = (a.name || '').trim()
    if (!name) {
      toast('存在未填写名称的 SubAgent', 'warning')
      return false
    }
    if (!nameRe.test(name)) {
      toast('SubAgent 名称不合法：仅允许英文小写字母/数字/下划线，且需以字母开头', 'warning')
      return false
    }
    if (seen.has(name)) {
      toast(`SubAgent 名称重复：${name}`, 'warning')
      return false
    }
    seen.add(name)
  }
  return true
}

async function save() {
  if (!validateBeforeSave()) return
  saving.value = true
  try {
    // Strip UI-only fields
    const mode = cfg.value.main_mode
    const payload = {
      main_enable: mode !== 'disabled',
      main_tools_policy: mode,
      agents: cfg.value.agents.map(a => ({
        name: a.name,
        public_description: a.public_description,
        system_prompt: a.system_prompt,
        tools: a.tools,
        enabled: a.enabled,
        provider_id: a.provider_id
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

  // Initialize UI-only selections after tools load.
  for (const a of cfg.value.agents) {
    if (!a.__tool_group) a.__tool_group = undefined
    if (!Array.isArray(a.__tool_group_selected)) a.__tool_group_selected = []
  }
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

.subagent-panel-title {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.subagent-title-left {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
}

.subagent-title-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.subagent-title-name {
  font-weight: 600;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 520px;
}

.subagent-title-sub {
  font-size: 12px;
  opacity: 0.72;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 520px;
}


.subagent-title-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.subagent-actions {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.subagent-provider {
  flex: 1;
  min-width: 260px;
}

.subagent-enabled-inline {
  margin-right: 2px;
}

/* Keep the switch compact inside the expansion-panel title row. */
.subagent-enabled-inline :deep(.v-input__details) {
  display: none;
}

.subagent-enabled-inline :deep(.v-selection-control) {
  min-height: 32px;
}
</style>

<style>
/*
  Vuetify renders selected chips inside the input control and will grow the
  field height as chips wrap. For subagent tool assignment this quickly becomes
  unwieldy, so we cap the chip area height and allow scrolling.

  Note: this must be a non-scoped style so it can reach Vuetify's internal
  elements.
*/
.subagent-tools .v-field__input {
  max-height: 160px;
  overflow-y: auto;
  align-content: flex-start;
}

/* Small breathing room so the scrollbar doesn't overlap chip close icons. */
.subagent-tools .v-field__input {
  padding-right: 6px;
}

</style>
