<template>
  <div class="dashboard-page subagent-page" :class="{ 'is-dark': isDark }">
    <v-container fluid class="dashboard-shell pa-4 pa-md-6">
      <div class="dashboard-header">
        <div class="dashboard-header-main">
          <div class="dashboard-eyebrow">{{ tm('header.eyebrow') }}</div>
          <div class="d-flex align-center flex-wrap" style="gap: 8px;">
            <h1 class="dashboard-title">{{ tm('page.title') }}</h1>
            <v-chip size="x-small" color="orange-darken-2" variant="tonal" label>
              {{ tm('page.beta') }}
            </v-chip>
          </div>
          <p class="dashboard-subtitle">{{ tm('page.subtitle') }}</p>
        </div>

        <div class="dashboard-header-actions">
          <v-btn variant="text" color="primary" prepend-icon="mdi-refresh" :loading="loading" @click="reload">
            {{ tm('actions.refresh') }}
          </v-btn>
          <v-btn variant="tonal" color="primary" prepend-icon="mdi-content-save" :loading="saving" @click="save">
            {{ tm('actions.save') }}
          </v-btn>
        </div>
      </div>

      <div v-if="hasUnsavedChanges" class="unsaved-banner">
        <v-icon size="18" color="warning">mdi-alert-circle-outline</v-icon>
        <span>{{ tm('messages.unsavedChangesNotice') }}</span>
      </div>

      <!-- ============================================ -->
      <!-- 第一部分：子代理编排 (subagent_orchestrator) -->
      <!-- ============================================ -->
      <div class="config-section mb-6">
        <div class="dashboard-section-head">
          <div>
            <div class="dashboard-section-title">{{ tm('section.orchestratorTitle') }}</div>
            <div class="dashboard-section-subtitle">{{ tm('section.orchestratorSubtitle') }}</div>
          </div>
        </div>

        <div class="dashboard-section-head mt-4">
          <div>
            <div class="dashboard-section-title">{{ tm('section.globalSettings') }}</div>
            <div class="dashboard-section-subtitle">{{ mainStateDescription }}</div>
          </div>
        </div>

        <div class="dashboard-form-grid global-settings-grid mb-5">
          <div class="setting-card">
            <div class="setting-card-head">
              <div>
                <div class="setting-title">{{ tm('switches.enable') }}</div>
                <div class="setting-subtitle">{{ tm('switches.enableHint') }}</div>
              </div>
              <v-switch
                v-model="cfg.main_enable"
                color="primary"
                hide-details
                inset
                density="comfortable"
              />
            </div>
          </div>

          <div class="setting-card">
            <div class="setting-card-head">
              <div>
                <div class="setting-title">{{ tm('switches.dedupe') }}</div>
                <div class="setting-subtitle">{{ tm('switches.dedupeHint') }}</div>
              </div>
              <v-switch
                v-model="cfg.remove_main_duplicate_tools"
                :disabled="!cfg.main_enable"
                color="primary"
                hide-details
                inset
                density="comfortable"
              />
            </div>
          </div>
        </div>

        <!-- 子代理列表 -->
        <div class="dashboard-section-head">
          <div>
            <div class="dashboard-section-title">{{ tm('section.title') }}</div>
            <div class="dashboard-section-subtitle">{{ tm('section.subtitle') }}</div>
          </div>
          <div class="dashboard-section-actions">
            <div class="dashboard-pill">
              <v-icon size="16">mdi-robot-outline</v-icon>
              <span>{{ cfg.agents.length }}</span>
            </div>
            <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="addAgent">
              {{ tm('actions.add') }}
            </v-btn>
          </div>
        </div>

        <div v-if="cfg.agents.length === 0" class="dashboard-card dashboard-card--padded empty-card">
          <div class="empty-wrap">
            <v-icon icon="mdi-robot-off" size="60" class="mb-4" />
            <div class="empty-title">{{ tm('empty.title') }}</div>
            <div class="dashboard-empty mb-4">{{ tm('empty.subtitle') }}</div>
            <v-btn color="primary" variant="tonal" @click="addAgent">
              {{ tm('empty.action') }}
            </v-btn>
          </div>
        </div>

        <div v-else class="subagent-list">
          <section
            v-for="(agent, idx) in cfg.agents"
            :key="agent.__key"
            class="dashboard-card dashboard-card--padded agent-panel"
          >
            <div class="agent-summary">
              <div class="agent-summary-main">
                <div class="agent-summary-top">
                  <v-badge dot :color="agent.enabled ? 'success' : 'grey'" inline />
                  <span class="agent-name">{{ agent.name || tm('cards.unnamed') }}</span>
                  <v-chip size="x-small" variant="tonal" :color="agent.enabled ? 'success' : 'default'">
                    {{ agent.enabled ? tm('cards.statusEnabled') : tm('cards.statusDisabled') }}
                  </v-chip>
                </div>
                <div class="agent-summary-desc">
                  {{ agent.public_description || tm('cards.noDescription') }}
                </div>
              </div>
              <div class="agent-summary-actions">
                <v-btn
                  :append-icon="isAgentExpanded(agent.__key) ? 'mdi-chevron-up' : 'mdi-chevron-down'"
                  variant="text"
                  color="default"
                  density="comfortable"
                  @click="toggleAgentExpanded(agent.__key)"
                >
                  {{ isAgentExpanded(agent.__key) ? tm('actions.collapse') : tm('actions.expand') }}
                </v-btn>
                <v-switch
                  v-model="agent.enabled"
                  color="success"
                  hide-details
                  inset
                  density="compact"
                />
                <v-btn
                  icon="mdi-delete-outline"
                  variant="text"
                  color="error"
                  density="comfortable"
                  @click="removeAgent(idx)"
                />
              </div>
            </div>

            <v-expand-transition>
              <div v-show="isAgentExpanded(agent.__key)" class="agent-edit-grid">
                <section class="dashboard-card dashboard-card--padded inner-card">
                  <div class="dashboard-section-title section-mini-title">{{ tm('section.agentSetup') }}</div>
                  <div class="dashboard-form-grid dashboard-form-grid--single">
                    <v-text-field
                      v-model="agent.name"
                      :label="tm('form.nameLabel')"
                      :rules="[v => !!v || tm('messages.nameRequired'), v => /^[a-z][a-z0-9_]*$/.test(v) || tm('messages.namePattern')]"
                      variant="outlined"
                      density="comfortable"
                      hide-details="auto"
                    />

                    <div class="selector-wrap">
                      <div class="selector-label">{{ tm('form.providerLabel') }}</div>
                      <div class="selector-card">
                        <ProviderSelector
                          v-model="agent.provider_id"
                          provider-type="chat_completion"
                          variant="outlined"
                          density="comfortable"
                          clearable
                        />
                      </div>
                    </div>

                    <div class="selector-wrap">
                      <div class="selector-label">{{ tm('form.personaLabel') }}</div>
                      <div class="selector-card">
                        <PersonaSelector v-model="agent.persona_id" />
                      </div>
                    </div>

                    <v-textarea
                      v-model="agent.public_description"
                      :label="tm('form.descriptionLabel')"
                      variant="outlined"
                      density="comfortable"
                      auto-grow
                      hide-details="auto"
                    />
                  </div>
                </section>

                <section class="dashboard-card dashboard-card--padded inner-card">
                  <div class="dashboard-section-title section-mini-title">{{ tm('cards.personaPreview') }}</div>
                  <div class="dashboard-section-subtitle">{{ tm('cards.previewHint') }}</div>
                  <div class="persona-preview-wrap">
                    <PersonaQuickPreview :model-value="agent.persona_id" class="h-100" />
                  </div>
                </section>
              </div>
            </v-expand-transition>
          </section>
        </div>
      </div>

      <!-- ============================================ -->
      <!-- 第二部分：增强子代理 (enhanced_subagent)   -->
      <!-- ============================================ -->
      <v-divider class="mb-6" />

      <div class="config-section">
        <div class="dashboard-section-head">
          <div>
            <div class="dashboard-section-title">{{ tm('section.enhancedSettings') }}</div>
            <div class="dashboard-section-subtitle">{{ tm('section.enhancedSettingsHint') }}</div>
          </div>
        </div>

        <!-- 启用增强子代理 -->
        <div class="dashboard-form-grid global-settings-grid mb-5">
          <div class="setting-card">
            <div class="setting-card-head">
              <div>
                <div class="setting-title">{{ tm('enhancedSwitches.enable') }}</div>
                <div class="setting-subtitle">{{ tm('enhancedSwitches.enableHint') }}</div>
              </div>
              <v-switch
                v-model="enhancedCfg.enabled"
                color="primary"
                hide-details
                inset
                density="comfortable"
              />
            </div>
          </div>
        </div>

        <v-expand-transition>
          <div v-show="enhancedCfg.enabled">
            <!-- 运行参数 -->
            <div class="dashboard-section-head mt-4">
              <div>
                <div class="dashboard-section-title">{{ tm('enhancedSection.runtimeParams') }}</div>
                <div class="dashboard-section-subtitle">{{ tm('enhancedSection.runtimeParamsHint') }}</div>
              </div>
            </div>

            <div class="dashboard-form-grid global-settings-grid mb-5">
              <!-- 最大子代理数量 -->
              <div class="setting-card">
                <div class="setting-card-head">
                  <div>
                    <div class="setting-title">{{ tm('enhancedFields.maxSubagentCount') }}</div>
                    <div class="setting-subtitle">{{ tm('enhancedFields.maxSubagentCountHint') }}</div>
                  </div>
                  <v-text-field
                    v-model.number="enhancedCfg.max_subagent_count"
                    type="number"
                    density="compact"
                    variant="outlined"
                    style="width: 120px;"
                    hide-details
                  />
                </div>
              </div>

              <!-- 自动清理开关 -->
              <div class="setting-card">
                <div class="setting-card-head">
                  <div>
                    <div class="setting-title">{{ tm('enhancedSwitches.autoCleanup') }}</div>
                    <div class="setting-subtitle">{{ tm('enhancedSwitches.autoCleanupHint') }}</div>
                  </div>
                  <v-switch
                    v-model="enhancedCfg.auto_cleanup_per_turn"
                    color="primary"
                    hide-details
                    inset
                    density="comfortable"
                  />
                </div>
              </div>

              <!-- 最大历史消息数 -->
              <div class="setting-card">
                <div class="setting-card-head">
                  <div>
                    <div class="setting-title">{{ tm('enhancedFields.maxSubagentHistory') }}</div>
                    <div class="setting-subtitle">{{ tm('enhancedFields.maxSubagentHistoryHint') }}</div>
                  </div>
                  <v-text-field
                    v-model.number="enhancedCfg.max_subagent_history"
                    type="number"
                    density="compact"
                    variant="outlined"
                    style="width: 120px;"
                    hide-details
                  />
                </div>
              </div>

              <!-- 执行超时时间 -->
              <div class="setting-card">
                <div class="setting-card-head">
                  <div>
                    <div class="setting-title">{{ tm('enhancedFields.executionTimeout') }}</div>
                    <div class="setting-subtitle">{{ tm('enhancedFields.executionTimeoutHint') }}</div>
                  </div>
                  <v-text-field
                    v-model.number="enhancedCfg.execution_timeout"
                    type="number"
                    density="compact"
                    variant="outlined"
                    style="width: 120px;"
                    hide-details
                  />
                </div>
              </div>
            </div>

            <!-- 共享上下文 -->
            <div class="dashboard-section-head mt-4">
              <div>
                <div class="dashboard-section-title">{{ tm('enhancedSection.sharedContext') }}</div>
                <div class="dashboard-section-subtitle">{{ tm('enhancedSection.sharedContextHint') }}</div>
              </div>
            </div>

            <div class="dashboard-form-grid global-settings-grid mb-5">
              <div class="setting-card">
                <div class="setting-card-head">
                  <div>
                    <div class="setting-title">{{ tm('enhancedSwitches.sharedContext') }}</div>
                    <div class="setting-subtitle">{{ tm('enhancedSwitches.sharedContextHint') }}</div>
                  </div>
                  <v-switch
                    v-model="enhancedCfg.shared_context_enabled"
                    color="primary"
                    hide-details
                    inset
                    density="comfortable"
                  />
                </div>
              </div>

              <div class="setting-card">
                <div class="setting-card-head">
                  <div>
                    <div class="setting-title">{{ tm('enhancedFields.sharedContextMaxlen') }}</div>
                    <div class="setting-subtitle">{{ tm('enhancedFields.sharedContextMaxlenHint') }}</div>
                  </div>
                  <v-text-field
                    v-model.number="enhancedCfg.shared_context_maxlen"
                    type="number"
                    density="compact"
                    variant="outlined"
                    style="width: 120px;"
                    hide-details
                  />
                </div>
              </div>
            </div>

            <!-- 工具策略 -->
            <div class="dashboard-section-head mt-4">
              <div>
                <div class="dashboard-section-title">{{ tm('enhancedSection.toolStrategy') }}</div>
                <div class="dashboard-section-subtitle">{{ tm('enhancedSection.toolStrategyHint') }}</div>
              </div>
            </div>

            <!-- 工具黑名单 -->
            <div class="dashboard-card dashboard-card--padded mb-4">
              <div class="dashboard-section-title section-mini-title">{{ tm('enhancedTools.blacklist') }}</div>
              <div class="dashboard-section-subtitle mb-3">{{ tm('enhancedTools.blacklistHint') }}</div>
              <div class="d-flex flex-wrap ga-2">
                <v-chip
                  v-for="(tool, idx) in enhancedCfg.tools_blacklist"
                  :key="tool"
                  closable
                  color="error"
                  variant="outlined"
                  size="small"
                  @click:close="removeToolFromBlacklist(idx)"
                >
                  {{ tool }}
                </v-chip>
                <v-chip
                  v-if="enhancedCfg.tools_blacklist.length === 0"
                  color="grey"
                  variant="text"
                  size="small"
                >
                  {{ tm('enhancedTools.emptyBlacklist') }}
                </v-chip>
              </div>
              <div class="mt-3">
                <v-btn
                  size="small"
                  variant="tonal"
                  color="primary"
                  @click="showToolSelectorDialog = true; toolSelectorMode = 'blacklist'"
                >
                  <v-icon start>mdi-plus</v-icon>
                  {{ tm('enhancedTools.addTool') }}
                </v-btn>
              </div>
            </div>

            <!-- 固有工具名单 -->
            <div class="dashboard-card dashboard-card--padded mb-4">
              <div class="dashboard-section-title section-mini-title">{{ tm('enhancedTools.inherent') }}</div>
              <div class="dashboard-section-subtitle mb-3">{{ tm('enhancedTools.inherentHint') }}</div>
              <div class="d-flex flex-wrap ga-2">
                <v-chip
                  v-for="(tool, idx) in enhancedCfg.tools_inherent"
                  :key="tool"
                  closable
                  color="success"
                  variant="outlined"
                  size="small"
                  @click:close="removeToolFromInherent(idx)"
                >
                  {{ tool }}
                </v-chip>
                <v-chip
                  v-if="enhancedCfg.tools_inherent.length === 0"
                  color="grey"
                  variant="text"
                  size="small"
                >
                  {{ tm('enhancedTools.emptyInherent') }}
                </v-chip>
              </div>
              <div class="mt-3">
                <v-btn
                  size="small"
                  variant="tonal"
                  color="success"
                  @click="showToolSelectorDialog = true; toolSelectorMode = 'inherent'"
                >
                  <v-icon start>mdi-plus</v-icon>
                  {{ tm('enhancedTools.addTool') }}
                </v-btn>
              </div>
            </div>
          </div>
        </v-expand-transition>
      </div>

      <!-- 工具选择器对话框 -->
      <v-dialog v-model="showToolSelectorDialog" max-width="600" scrollable>
        <v-card>
          <v-card-title>
            {{ toolSelectorMode === 'blacklist' ? tm('enhancedTools.selectBlacklistTool') : tm('enhancedTools.selectInherentTool') }}
          </v-card-title>
          <v-divider />
          <v-card-text style="max-height: 400px;">
            <v-list>
              <v-list-item
                v-for="tool in availableTools"
                :key="tool.name"
                @click="addToolToList(tool.name)"
                :disabled="isToolInTargetList(tool.name)"
              >
                <v-list-item-title>{{ tool.name }}</v-list-item-title>
                <v-list-item-subtitle>{{ tool.description }}</v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </v-card-text>
          <v-divider />
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="showToolSelectorDialog = false">
              {{ tm('actions.close') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="3000" location="top">
        {{ snackbar.message }}
        <template #actions>
          <v-btn variant="text" @click="snackbar.show = false">{{ tm('actions.close') }}</v-btn>
        </template>
      </v-snackbar>
    </v-container>
  </div>
</template>

<script setup lang="ts">
import axios from 'axios'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useTheme } from 'vuetify'
import PersonaQuickPreview from '@/components/shared/PersonaQuickPreview.vue'
import PersonaSelector from '@/components/shared/PersonaSelector.vue'
import ProviderSelector from '@/components/shared/ProviderSelector.vue'
import { useModuleI18n } from '@/i18n/composables'
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog'

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

type EnhancedSubagentConfig = {
  enabled: boolean
  max_subagent_count: number
  auto_cleanup_per_turn: boolean
  shared_context_enabled: boolean
  shared_context_maxlen: number
  max_subagent_history: number
  execution_timeout: number
  tools_blacklist: string[]
  tools_inherent: string[]
}

type AvailableTool = {
  name: string
  description: string
  parameters: any
  active: boolean
  handler_module_path: string
}

const { tm } = useModuleI18n('features/subagent')
const theme = useTheme()
const confirmDialog = useConfirmDialog()

const loading = ref(false)
const saving = ref(false)
const isDark = computed(() => theme.global.current.value.dark)

const snackbar = ref({
  show: false,
  message: '',
  color: 'success'
})
const expandedAgents = ref<Record<string, boolean>>({})
const initialSnapshot = ref('')
const enhancedInitialSnapshot = ref('')
const hasLoaded = ref(false)

// 工具选择器相关
const showToolSelectorDialog = ref(false)
const toolSelectorMode = ref<'blacklist' | 'inherent'>('blacklist')
const availableTools = ref<AvailableTool[]>([])

function toast(message: string, color: 'success' | 'error' | 'warning' = 'success') {
  snackbar.value = { show: true, message, color }
}

const cfg = ref<SubAgentConfig>({
  main_enable: false,
  remove_main_duplicate_tools: false,
  agents: []
})

const enhancedCfg = ref<EnhancedSubagentConfig>({
  enabled: false,
  max_subagent_count: 3,
  auto_cleanup_per_turn: true,
  shared_context_enabled: false,
  shared_context_maxlen: 200,
  max_subagent_history: 500,
  execution_timeout: 600,
  tools_blacklist: [],
  tools_inherent: []
})

const mainStateDescription = computed(() =>
  cfg.value.main_enable ? tm('description.enabled') : tm('description.disabled')
)

const hasUnsavedChanges = computed(() => {
  if (!hasLoaded.value) return false
  const orchestratorChanged = serializeConfig(cfg.value) !== initialSnapshot.value
  const enhancedChanged = serializeEnhancedConfig(enhancedCfg.value) !== enhancedInitialSnapshot.value
  return orchestratorChanged || enhancedChanged
})

function normalizeConfig(raw: any): SubAgentConfig {
  // 兼容新旧格式：
  // 新格式: raw 直接包含 main_enable, agents 等字段
  // 旧格式: raw.subagent_orchestrator 包含这些字段
  const orchData = raw?.subagent_orchestrator || raw || {}
  const main_enable = !!orchData?.main_enable
  const remove_main_duplicate_tools = !!orchData?.remove_main_duplicate_tools
  const agentsRaw = Array.isArray(orchData?.agents) ? orchData.agents : []

  const agents: SubAgentItem[] = agentsRaw.map((a: any, i: number) => ({
    __key: `${Date.now()}_${i}_${Math.random().toString(16).slice(2)}`,
    name: (a?.name ?? '').toString(),
    persona_id: (a?.persona_id ?? '').toString(),
    public_description: (a?.public_description ?? '').toString(),
    enabled: a?.enabled !== false,
    provider_id: (a?.provider_id ?? undefined) as string | undefined
  }))

  return { main_enable, remove_main_duplicate_tools, agents }
}

function normalizeEnhancedConfig(raw: any): EnhancedSubagentConfig {
  return {
    enabled: !!raw?.enabled,
    max_subagent_count: Number(raw?.max_subagent_count) || 3,
    auto_cleanup_per_turn: raw?.auto_cleanup_per_turn !== false,
    shared_context_enabled: !!raw?.shared_context_enabled,
    shared_context_maxlen: Number(raw?.shared_context_maxlen) || 200,
    max_subagent_history: Number(raw?.max_subagent_history) || 500,
    execution_timeout: Number(raw?.execution_timeout) || 600,
    tools_blacklist: Array.isArray(raw?.tools_blacklist) ? raw.tools_blacklist : [],
    tools_inherent: Array.isArray(raw?.tools_inherent) ? raw.tools_inherent : []
  }
}

function serializeConfig(config: SubAgentConfig): string {
  return JSON.stringify({
    main_enable: config.main_enable,
    remove_main_duplicate_tools: config.remove_main_duplicate_tools,
    agents: config.agents.map((agent) => ({
      name: agent.name,
      persona_id: agent.persona_id,
      public_description: agent.public_description,
      enabled: agent.enabled,
      provider_id: agent.provider_id ?? null
    }))
  })
}

function serializeEnhancedConfig(config: EnhancedSubagentConfig): string {
  return JSON.stringify(config)
}

async function loadAvailableTools() {
  try {
    const res = await axios.get('/api/subagent/available-tools')
    if (res.data.status === 'ok') {
      availableTools.value = res.data.data
    }
  } catch (e) {
    console.error('Failed to load available tools:', e)
  }
}

async function loadConfig() {
  loading.value = true
  try {
    const res = await axios.get('/api/subagent/config')
    if (res.data.status === 'ok') {
      const data = res.data.data
      // 兼容新旧格式：data 可能直接包含字段，或通过 subagent_orchestrator 嵌套
      cfg.value = normalizeConfig(data.subagent_orchestrator || data)
      enhancedCfg.value = normalizeEnhancedConfig(data.enhanced_subagent || {})
      expandedAgents.value = Object.fromEntries(cfg.value.agents.map((agent) => [agent.__key, false]))
      initialSnapshot.value = serializeConfig(cfg.value)
      enhancedInitialSnapshot.value = serializeEnhancedConfig(enhancedCfg.value)
      hasLoaded.value = true
    } else {
      toast(res.data.message || tm('messages.loadConfigFailed'), 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm('messages.loadConfigFailed'), 'error')
  } finally {
    loading.value = false
  }
}

function addAgent() {
  const key = `${Date.now()}_${Math.random().toString(16).slice(2)}`
  cfg.value.agents.push({
    __key: key,
    name: '',
    persona_id: '',
    public_description: '',
    enabled: true,
    provider_id: undefined
  })
  expandedAgents.value[key] = false
}

function removeAgent(idx: number) {
  const [removed] = cfg.value.agents.splice(idx, 1)
  if (removed) {
    delete expandedAgents.value[removed.__key]
  }
}

function isAgentExpanded(key: string): boolean {
  return expandedAgents.value[key] !== false
}

function toggleAgentExpanded(key: string) {
  expandedAgents.value[key] = !isAgentExpanded(key)
}

function validateBeforeSave(): boolean {
  const nameRe = /^[a-z][a-z0-9_]{0,63}$/
  const seen = new Set<string>()

  for (const agent of cfg.value.agents) {
    const name = (agent.name || '').trim()
    if (!name) {
      toast(tm('messages.nameMissing'), 'warning')
      return false
    }
    if (!nameRe.test(name)) {
      toast(tm('messages.nameInvalid'), 'warning')
      return false
    }
    if (seen.has(name)) {
      toast(tm('messages.nameDuplicate', { name }), 'warning')
      return false
    }
    seen.add(name)
    if (!agent.persona_id) {
      toast(tm('messages.personaMissing', { name }), 'warning')
      return false
    }
  }

  return true
}

async function save() {
  if (!validateBeforeSave()) return
  saving.value = true
  try {
    const payload = {
      subagent_orchestrator: {
        main_enable: cfg.value.main_enable,
        remove_main_duplicate_tools: cfg.value.remove_main_duplicate_tools,
        agents: cfg.value.agents.map((agent) => ({
          name: agent.name,
          persona_id: agent.persona_id,
          public_description: agent.public_description,
          enabled: agent.enabled,
          provider_id: agent.provider_id
        }))
      },
      enhanced_subagent: enhancedCfg.value
    }

    const res = await axios.post('/api/subagent/config', payload)
    if (res.data.status === 'ok') {
      initialSnapshot.value = serializeConfig(cfg.value)
      enhancedInitialSnapshot.value = serializeEnhancedConfig(enhancedCfg.value)
      hasLoaded.value = true
      toast(res.data.message || tm('messages.saveSuccess'), 'success')
    } else {
      toast(res.data.message || tm('messages.saveFailed'), 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tm('messages.saveFailed'), 'error')
  } finally {
    saving.value = false
  }
}

async function reload() {
  if (hasUnsavedChanges.value) {
    const confirmed = await askForConfirmation(
      tm('messages.unsavedChangesReloadConfirm'),
      confirmDialog
    )
    if (!confirmed) {
      return
    }
  }
  await loadConfig()
}

async function confirmLeaveIfNeeded(): Promise<boolean> {
  if (!hasUnsavedChanges.value) {
    return true
  }

  return askForConfirmation(
    tm('messages.unsavedChangesLeaveConfirm'),
    confirmDialog
  )
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!hasUnsavedChanges.value) {
    return
  }

  event.preventDefault()
  event.returnValue = ''
}

// 工具列表操作
function addToolToList(toolName: string) {
  if (toolSelectorMode.value === 'blacklist') {
    if (!enhancedCfg.value.tools_blacklist.includes(toolName)) {
      enhancedCfg.value.tools_blacklist.push(toolName)
    }
  } else if (toolSelectorMode.value === 'inherent') {
    if (!enhancedCfg.value.tools_inherent.includes(toolName)) {
      enhancedCfg.value.tools_inherent.push(toolName)
    }
  }
  showToolSelectorDialog.value = false
}

function removeToolFromBlacklist(idx: number) {
  enhancedCfg.value.tools_blacklist.splice(idx, 1)
}

function removeToolFromInherent(idx: number) {
  enhancedCfg.value.tools_inherent.splice(idx, 1)
}

function isToolInTargetList(toolName: string): boolean {
  if (toolSelectorMode.value === 'blacklist') {
    return enhancedCfg.value.tools_blacklist.includes(toolName)
  } else {
    return enhancedCfg.value.tools_inherent.includes(toolName)
  }
}

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  loadConfig()
  loadAvailableTools()
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

onBeforeRouteLeave(async () => {
  return await confirmLeaveIfNeeded()
})
</script>

<style scoped>
@import '@/styles/dashboard-shell.css';

.subagent-page {
  padding-bottom: 40px;
}

.config-section {
  padding-top: 0;
}

.unsaved-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  margin-bottom: 18px;
  border: 1px solid rgba(var(--v-theme-warning), 0.22);
  border-radius: 12px;
  background: rgba(var(--v-theme-warning), 0.08);
  color: var(--dashboard-text);
  font-size: 13px;
  line-height: 1.5;
}

.setting-card {
  border: 1px solid var(--dashboard-border);
  border-radius: 14px;
  padding: 18px;
  background: rgba(var(--v-theme-primary), 0.02);
}

.setting-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.setting-title {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
}

.setting-subtitle {
  margin-top: 6px;
  color: var(--dashboard-muted);
  font-size: 13px;
  line-height: 1.6;
}

.empty-card {
  min-height: 280px;
}

.empty-wrap {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--dashboard-muted);
}

.empty-title {
  font-size: 20px;
  font-weight: 650;
  color: var(--dashboard-text);
  margin-bottom: 8px;
}

.subagent-list {
  display: grid;
  gap: 16px;
}

.agent-panel {
  display: grid;
  gap: 18px;
}

.agent-summary {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  width: 100%;
}

.agent-summary-main {
  min-width: 0;
  flex: 1;
}

.agent-summary-top {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.agent-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 18px;
  font-weight: 650;
}

.agent-summary-desc {
  margin-top: 8px;
  color: var(--dashboard-muted);
  font-size: 13px;
  line-height: 1.6;
}

.agent-summary-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.agent-edit-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.inner-card {
  min-width: 0;
}

.section-mini-title {
  margin-bottom: 4px;
}

.selector-wrap {
  display: grid;
  gap: 8px;
}

.selector-label {
  color: var(--dashboard-muted);
  font-size: 13px;
  font-weight: 500;
}

.selector-card {
  border: 1px solid var(--dashboard-border);
  border-radius: 12px;
  padding: 14px;
  background: transparent;
}

.persona-preview-wrap {
  min-height: 320px;
}

@media (max-width: 1080px) {
  .agent-edit-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .setting-card-head,
  .agent-summary {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
