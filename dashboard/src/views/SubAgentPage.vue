<template>
  <div class="subagent-page">
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <div class="d-flex align-center" style="gap: 8px;">
          <h2 class="text-h5 font-weight-bold">SubAgent 编排</h2>
          <v-chip size="x-small" color="orange-darken-2" variant="tonal" label>Beta</v-chip>
        </div>
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
            <v-switch v-model="cfg.main_enable" label="启用 SubAgent 编排"
              inset color="primary" hide-details density="comfortable" />
          </v-col>
          <v-col cols="12" md="6">
            <v-switch v-model="cfg.remove_main_duplicate_tools" :disabled="!cfg.main_enable"
              label="主 LLM 去重重复工具（与 SubAgent 重叠的工具将被隐藏）"
              inset color="primary" hide-details density="comfortable" />
          </v-col>
        </v-row>

        <div class="text-caption text-medium-emphasis mt-1">
          <div v-if="!cfg.main_enable">
            不启动：SubAgent 关闭；主 LLM 按 persona 规则挂载工具（默认全部），并直接调用。
          </div>
          <div v-else>
            启动：主 LLM 会保留自身工具并挂载 transfer_to_* 委派工具。
            若开启“去重重复工具”，与 SubAgent 指定的工具重叠部分会从主 LLM 工具集中移除。
          </div>
        </div>

        <div class="d-flex align-center justify-space-between mt-6 mb-2">
          <div class="text-subtitle-1 font-weight-bold">SubAgents</div>
          <v-btn size="small" variant="tonal" color="primary" @click="addAgent">
            新增 SubAgent
          </v-btn>
        </div>

        <v-expansion-panels variant="accordion" multiple>
          <v-expansion-panel v-for="(agent, idx) in cfg.agents" :key="agent.__key">
            <v-expansion-panel-title>
              <div class="subagent-panel-title">
                <div class="subagent-title-left">
                  <v-chip :color="agent.enabled ? 'success' : 'grey'" size="small" variant="tonal">
                    {{ agent.enabled ? '启用' : '停用' }}
                  </v-chip>

                  <div class="subagent-title-text">
                    <div class="subagent-title-name">{{ agent.name || '未命名 SubAgent' }}</div>
                    <div class="subagent-title-sub">transfer_to_{{ agent.name || '...' }}</div>
                  </div>
                </div>

                <div class="subagent-title-right">
                  <v-switch v-model="agent.enabled" inset color="primary" hide-details class="subagent-enabled-inline"
                    @click.stop>
                    <template #label>启用</template>
                  </v-switch>

                  <v-btn size="small" variant="text" color="error" @click.stop="removeAgent(idx)">
                    删除
                  </v-btn>
                </div>
              </div>
            </v-expansion-panel-title>

            <v-expansion-panel-text>
              <v-row class="subagent-grid">
                <v-col cols="12" md="5">
                  <v-text-field v-model="agent.name" label="Agent 名称（用于 transfer_to_{name}）" variant="outlined"
                    density="comfortable" hint="建议使用英文小写+下划线，且全局唯一" persistent-hint />
                </v-col>
                <v-col cols="12" md="7" class="subagent-actions">
                  <ProviderSelector v-model="agent.provider_id" provider-type="chat_completion"
                    label="Chat Provider（可选）" hint="留空表示跟随全局默认 provider。" persistent-hint clearable
                    class="subagent-provider" />
                </v-col>
                <v-col cols="12" md="6">
                  <v-autocomplete v-model="agent.persona_id" :items="personaOptions" item-title="title"
                    item-value="value" label="选择 Persona" variant="outlined" density="comfortable" clearable
                    :loading="personaLoading" :disabled="personaLoading" hint="SubAgent 将直接继承所选 Persona 的系统设定与工具。"
                    persistent-hint />
                </v-col>

                <v-col cols="12" md="6">
                  <v-text-field v-model="agent.public_description" label="对主 LLM 的描述（用于决定是否 handoff）" variant="outlined"
                    density="comfortable" hint="这段会作为 transfer_to_* 工具的描述给主 LLM 看，建议简短明确。" persistent-hint />
                </v-col>
              </v-row>

              <div class="mt-3">
                <div class="text-caption text-medium-emphasis">预览：主 LLM 将看到的 handoff 工具</div>
                <div class="d-flex align-center" style="gap: 8px; flex-wrap: wrap;">
                  <v-chip size="small" variant="outlined" color="primary">
                    transfer_to_{{ agent.name || '...' }}
                  </v-chip>
                  <v-chip size="small" variant="tonal" color="secondary" v-if="agent.persona_id">
                    Persona: {{ agent.persona_id }}
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

type SubAgentItem = {
  __key: string
  name: string
  persona_id: string
  public_description: string
  enabled: boolean
  provider_id?: string
}

type SubAgentConfig = {
  main_enable: boolean
  remove_main_duplicate_tools: boolean
  agents: SubAgentItem[]
}

const loading = ref(false)
const saving = ref(false)

const snackbar = ref({
  show: false,
  message: '',
  color: 'success'
})

function toast(message: string, color: 'success' | 'error' | 'warning' = 'success') {
  snackbar.value = { show: true, message, color }
}

const cfg = ref<SubAgentConfig>({
  main_enable: false,
  remove_main_duplicate_tools: false,
  agents: []
})

const personaOptions = ref<{ title: string; value: string }[]>([])
const personaLoading = ref(false)

function normalizeConfig(raw: any): SubAgentConfig {
  const main_enable = !!raw?.main_enable
  const remove_main_duplicate_tools = !!raw?.remove_main_duplicate_tools
  const agentsRaw = Array.isArray(raw?.agents) ? raw.agents : []

  const agents: SubAgentItem[] = agentsRaw.map((a: any, i: number) => {
    const name = (a?.name ?? '').toString()
    const persona_id = (a?.persona_id ?? '').toString()
    const public_description = (a?.public_description ?? '').toString()
    const enabled = a?.enabled !== false
    const provider_id = (a?.provider_id ?? undefined) as (string | undefined)

    return {
      __key: `${Date.now()}_${i}_${Math.random().toString(16).slice(2)}`,
      name,
      persona_id,
      public_description,
      enabled
      ,
      provider_id
    }
  })

  return { main_enable, remove_main_duplicate_tools, agents }
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

async function loadPersonas() {
  personaLoading.value = true
  try {
    const res = await axios.get('/api/persona/list')
    if (res.data.status === 'ok') {
      const list = Array.isArray(res.data.data) ? res.data.data : []
      personaOptions.value = list.map((p: any) => ({
        title: p.persona_id,
        value: p.persona_id
      }))
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || '获取 Persona 列表失败', 'error')
  } finally {
    personaLoading.value = false
  }
}

function addAgent() {
  cfg.value.agents.push({
    __key: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
    name: '',
    persona_id: '',
    public_description: '',
    enabled: true,
    provider_id: undefined
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
    if (!a.persona_id) {
      toast(`SubAgent ${name} 未选择 Persona`, 'warning')
      return false
    }
  }
  return true
}

async function save() {
  if (!validateBeforeSave()) return
  saving.value = true
  try {
    // Strip UI-only fields
    const payload = {
      main_enable: cfg.value.main_enable,
      remove_main_duplicate_tools: cfg.value.remove_main_duplicate_tools,
      agents: cfg.value.agents.map(a => ({
        name: a.name,
        persona_id: a.persona_id,
        public_description: a.public_description,
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
  await Promise.all([loadConfig(), loadPersonas()])
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
