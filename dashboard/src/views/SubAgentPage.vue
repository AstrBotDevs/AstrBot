<template>
  <div class="subagent-page">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <div class="d-flex align-center gap-2 mb-1">
          <h2 class="text-h5 font-weight-bold">{{ tf('page.title', 'SubAgent Orchestration') }}</h2>
          <v-chip size="x-small" color="orange-darken-2" variant="tonal" label class="font-weight-bold">
            {{ tf('page.beta', 'Experimental') }}
          </v-chip>
        </div>
        <div class="text-body-2 text-medium-emphasis">
          {{ tf('page.subtitle', 'The main LLM can use its own tools directly and delegate tasks to SubAgents via handoff.') }}
        </div>
      </div>

      <div class="d-flex align-center gap-2">
        <v-btn
          variant="text"
          color="primary"
          prepend-icon="mdi-refresh"
          :loading="loading"
          @click="reload"
        >
          {{ tf('actions.refresh', 'Refresh') }}
        </v-btn>
        <v-btn
          variant="flat"
          color="primary"
          prepend-icon="mdi-content-save"
          :loading="saving"
          @click="save"
        >
          {{ tf('actions.save', 'Save') }}
        </v-btn>
      </div>
    </div>

    <!-- Global Settings Card -->
    <v-card class="rounded-lg mb-6 border-thin" variant="flat" border>
      <v-card-text>
        <div class="d-flex align-center justify-space-between">
          <div>
            <div class="text-subtitle-1 font-weight-bold mb-1">{{ tf('section.globalSettings', 'Global Settings') }}</div>
            <div class="text-caption text-medium-emphasis">
              {{ mainStateDescription }}
            </div>
          </div>
        </div>

        <v-divider class="my-4" />

        <v-row dense>
          <v-col cols="12" md="6">
            <v-switch
              v-model="cfg.main_enable"
              :label="tf('switches.enable', 'Enable SubAgent orchestration')"
              color="primary"
              hide-details
              inset
              density="comfortable"
            >
              <template #label>
                <div class="d-flex flex-column">
                  <span class="text-body-2 font-weight-medium">{{ tf('switches.enable', 'Enable SubAgent orchestration') }}</span>
                  <span class="text-caption text-medium-emphasis">{{ tf('switches.enableHint', 'Enable sub-agent functionality') }}</span>
                </div>
              </template>
            </v-switch>
          </v-col>
          <v-col cols="12" md="6">
            <v-switch
              v-model="cfg.remove_main_duplicate_tools"
              :disabled="!cfg.main_enable"
              :label="tf('switches.dedupe', 'Deduplicate main LLM tools (hide tools duplicated by SubAgents)')"
              color="primary"
              hide-details
              inset
              density="comfortable"
            >
              <template #label>
                <div class="d-flex flex-column">
                  <span class="text-body-2 font-weight-medium">{{ tf('switches.dedupe', 'Deduplicate main LLM tools (hide tools duplicated by SubAgents)') }}</span>
                  <span class="text-caption text-medium-emphasis">{{ tf('switches.dedupeHint', 'Remove duplicate tools from main agent') }}</span>
                </div>
              </template>
            </v-switch>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- Agents List Section -->
    <div class="d-flex align-center justify-space-between mb-4">
      <div class="d-flex align-center gap-2">
        <v-icon icon="mdi-robot" color="primary" size="small" />
        <div class="text-h6 font-weight-bold">{{ tf('section.title', 'SubAgents') }}</div>
        <v-chip size="small" variant="tonal" color="primary" class="ml-2">
          {{ cfg.agents.length }}
        </v-chip>
      </div>
      <v-btn
        prepend-icon="mdi-plus"
        color="primary"
        @click="addAgent"
      >
        {{ tf('actions.add', 'Add SubAgent') }}
      </v-btn>
    </div>

    <v-expansion-panels variant="popout" class="subagent-panels">
      <v-expansion-panel
        v-for="(agent, idx) in cfg.agents"
        :key="agent.__key"
        elevation="0"
        class="border-thin mb-2 rounded-lg"
        :class="{ 'border-primary': agent.enabled }"
      >
        <v-expansion-panel-title class="py-3">
          <div class="d-flex align-center w-100 gap-4">
            <!-- Status Indicator -->
            <v-badge
              dot
              :color="agent.enabled ? 'success' : 'grey'"
              inline
              class="mr-2"
            />

            <!-- Agent Info -->
            <div class="d-flex flex-column flex-grow-1" style="min-width: 0;">
              <div class="d-flex align-center gap-2">
                <span class="text-subtitle-1 font-weight-bold text-truncate">
                  {{ agent.name || tf('cards.unnamed', 'Untitled SubAgent') }}
                </span>
              </div>
              <div class="text-caption text-medium-emphasis text-truncate">
                {{ agent.public_description || tf('cards.noDescription', 'No description') }}
              </div>
            </div>

            <!-- Controls (stop propagation on clicks) -->
            <div class="d-flex align-center gap-2 flex-shrink-0" @click.stop>
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
        </v-expansion-panel-title>

        <v-expansion-panel-text>
          <v-divider class="mb-4" />
          <v-row>
            <!-- Left Column: Form -->
            <v-col cols="12" md="6">
              <div class="d-flex flex-column gap-4">
                <v-text-field
                  v-model="agent.name"
                  :label="tf('form.nameLabel', 'Agent name (used for transfer_to_{name})')"
                  :rules="[
                    v => !!v || tf('messages.nameRequired', 'Name is required'),
                    v => (v || '').trim().length <= 256 || tf('messages.nameInvalid', 'Invalid SubAgent name')
                  ]"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                  prepend-inner-icon="mdi-account"
                />

                <div class="d-flex flex-column gap-1">
                  <div class="text-caption text-medium-emphasis ml-1">{{ tf('form.providerLabel', 'Chat Provider (optional)') }}</div>
                  <v-card variant="outlined" class="pa-0 border-thin rounded bg-transparent" style="border-color: rgba(var(--v-border-color), var(--v-border-opacity));">
                    <div class="pa-3">
                      <ProviderSelector
                        v-model="agent.provider_id"
                        provider-type="chat_completion"
                        variant="outlined"
                        density="comfortable"
                        clearable
                      />
                    </div>
                  </v-card>
                </div>

                <div class="d-flex flex-column gap-1">
                  <div class="text-caption text-medium-emphasis ml-1">{{ tf('form.personaLabel', 'Choose Persona') }}</div>
                  <v-card variant="outlined" class="pa-0 border-thin rounded bg-transparent" style="border-color: rgba(var(--v-border-color), var(--v-border-opacity));">
                    <div class="pa-3">
                      <PersonaSelector
                        v-model="agent.persona_id"
                      />
                    </div>
                  </v-card>
                </div>

                <v-textarea
                  v-model="agent.public_description"
                  :label="tf('form.descriptionLabel', 'Description for the main LLM (used to decide handoff)')"
                  variant="outlined"
                  density="comfortable"
                  auto-grow
                  hide-details="auto"
                  prepend-inner-icon="mdi-text"
                />
              </div>
            </v-col>

            <!-- Right Column: Preview -->
            <v-col cols="12" md="6">
              <div class="h-100">
                <div class="text-caption font-weight-bold text-medium-emphasis mb-2 ml-1">
                  {{ tf('cards.personaPreview', 'Persona Preview') }}
                </div>
                <PersonaQuickPreview
                  :model-value="agent.persona_id"
                  class="h-100"
                />
              </div>
            </v-col>
          </v-row>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <!-- Empty State -->
    <div v-if="cfg.agents.length === 0" class="d-flex flex-column align-center justify-center py-12 text-medium-emphasis">
      <v-icon icon="mdi-robot-off" size="64" class="mb-4 opacity-50" />
      <div class="text-h6">{{ tf('empty.title', 'No Agents Configured') }}</div>
      <div class="text-body-2 mb-4">{{ tf('empty.subtitle', 'Add a new sub-agent to get started') }}</div>
      <v-btn color="primary" variant="tonal" @click="addAgent">
        {{ tf('empty.action', 'Create First Agent') }}
      </v-btn>
    </div>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="3000" location="top">
      {{ snackbar.message }}
      <template #actions>
         <v-btn variant="text" @click="snackbar.show = false">{{ tf('actions.close', 'Close') }}</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import ProviderSelector from '@/components/shared/ProviderSelector.vue'
import PersonaSelector from '@/components/shared/PersonaSelector.vue'
import PersonaQuickPreview from '@/components/shared/PersonaQuickPreview.vue'
import { useModuleI18n } from '@/i18n/composables'

type ToolsScope = 'all' | 'none' | 'list' | 'persona'

type SubAgentItem = {

  __key: string
  name: string
  persona_id: string
  public_description: string
  enabled: boolean
  provider_id?: string
  tools_scope?: ToolsScope
  tools?: string[]
  max_steps?: number
  instructions?: string
}

type SubAgentConfig = {
  main_enable: boolean
  remove_main_duplicate_tools: boolean
  error_classifier?: {
    type?: string
    fatal_exceptions?: string[]
    transient_exceptions?: string[]
    default_class?: string
  }
  agents: SubAgentItem[]
}

const { tm } = useModuleI18n('features/subagent')

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

function tf(
  key: string,
  fallback: string,
  params?: Record<string, string | number>
): string {
  const translated = tm(key, params)
  if (
    !translated ||
    translated.startsWith('[MISSING:') ||
    translated.startsWith('[INVALID:')
  ) {
    return fallback
  }
  return translated
}

const cfg = ref<SubAgentConfig>({
  main_enable: false,
  remove_main_duplicate_tools: false,
  error_classifier: {
    type: 'default',
    fatal_exceptions: ['ValueError', 'PermissionError', 'KeyError'],
    transient_exceptions: [
      'asyncio.TimeoutError',
      'TimeoutError',
      'ConnectionError',
      'ConnectionResetError'
    ],
    default_class: 'transient'
  },
  agents: []
})

const mainStateDescription = computed(() =>
  cfg.value.main_enable
    ? tf(
      'description.enabled',
      'When on: the main LLM keeps its own tools and mounts transfer_to_* delegate tools.'
    )
    : tf(
      'description.disabled',
      'When off: SubAgent is disabled and the main LLM calls tools directly.'
    )
)

function inferToolsScope(a: any): ToolsScope {
  const explicitScope = (a?.tools_scope ?? '').toString().toLowerCase()
  if (explicitScope === 'all' || explicitScope === 'none' || explicitScope === 'list' || explicitScope === 'persona') {
    return explicitScope as ToolsScope
  }
  if (Array.isArray(a?.tools)) {
    return a.tools.length === 0 ? 'none' : 'list'
  }
  if ((a?.persona_id ?? '').toString().trim()) {
    return 'persona'
  }
  return 'all'
}

function normalizeConfig(raw: any): SubAgentConfig {
  const main_enable = !!raw?.main_enable
  const remove_main_duplicate_tools = !!raw?.remove_main_duplicate_tools
  const error_classifier = raw?.error_classifier && typeof raw.error_classifier === 'object'
    ? {
      type: (raw.error_classifier.type ?? 'default').toString(),
      fatal_exceptions: Array.isArray(raw.error_classifier.fatal_exceptions)
        ? raw.error_classifier.fatal_exceptions.map((x: any) => (x ?? '').toString()).filter((x: string) => !!x)
        : ['ValueError', 'PermissionError', 'KeyError'],
      transient_exceptions: Array.isArray(raw.error_classifier.transient_exceptions)
        ? raw.error_classifier.transient_exceptions.map((x: any) => (x ?? '').toString()).filter((x: string) => !!x)
        : ['asyncio.TimeoutError', 'TimeoutError', 'ConnectionError', 'ConnectionResetError'],
      default_class: (raw.error_classifier.default_class ?? 'transient').toString()
    }
    : {
      type: 'default',
      fatal_exceptions: ['ValueError', 'PermissionError', 'KeyError'],
      transient_exceptions: ['asyncio.TimeoutError', 'TimeoutError', 'ConnectionError', 'ConnectionResetError'],
      default_class: 'transient'
    }
  const agentsRaw = Array.isArray(raw?.agents) ? raw.agents : []

  const agents: SubAgentItem[] = agentsRaw.map((a: any, i: number) => {
    const name = (a?.name ?? '').toString()
    const persona_id = (a?.persona_id ?? '').toString()
    const public_description = (a?.public_description ?? '').toString()
    const instructions = (a?.instructions ?? a?.system_prompt ?? '').toString()
    const enabled = a?.enabled !== false
    const provider_id = (a?.provider_id ?? undefined) as string | undefined
    const tools_scope = inferToolsScope(a)
    const tools = Array.isArray(a?.tools)
      ? a.tools.map((t: any) => (t ?? '').toString().trim()).filter((t: string) => !!t)
      : undefined
    const max_steps =
      a?.max_steps === null || a?.max_steps === undefined || a?.max_steps === ''
        ? undefined
        : Number(a.max_steps)

    return {
      __key: `${Date.now()}_${i}_${Math.random().toString(16).slice(2)}`,
      name,
      persona_id,
      public_description,
      enabled,
      provider_id,
      tools_scope,
      tools,
      max_steps: Number.isFinite(max_steps) ? max_steps : undefined,
      instructions
    }
  })

  return { main_enable, remove_main_duplicate_tools, error_classifier, agents }
}

async function loadConfig() {
  loading.value = true
  try {
    const res = await axios.get('/api/subagent/config')
    if (res.data.status === 'ok') {
      cfg.value = normalizeConfig(res.data.data)
    } else {
      toast(res.data.message || tf('messages.loadConfigFailed', 'Failed to load config'), 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tf('messages.loadConfigFailed', 'Failed to load config'), 'error')
  } finally {
    loading.value = false
  }
}

function addAgent() {
  cfg.value.agents.push({
    __key: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
    name: '',
    persona_id: '',
    public_description: '',
    enabled: true,
    provider_id: undefined,
    tools_scope: 'persona',
    tools: [],
    max_steps: undefined,
    instructions: ''
  })
}

function removeAgent(idx: number) {
  cfg.value.agents.splice(idx, 1)
}

function validateBeforeSave(): boolean {
  const seen = new Set<string>()
  for (const a of cfg.value.agents) {
    const name = (a.name || '').trim()
    if (!name) {
      toast(tf('messages.nameMissing', 'A SubAgent is missing a name'), 'warning')
      return false
    }
    if (name.length > 256) {
      toast(tf('messages.nameInvalid', 'Invalid SubAgent name'), 'warning')
      return false
    }
    if (seen.has(name)) {
      toast(
        tf('messages.nameDuplicate', `Duplicate SubAgent name: ${name}`, { name }),
        'warning'
      )
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
    const payload = {
      main_enable: cfg.value.main_enable,
      remove_main_duplicate_tools: cfg.value.remove_main_duplicate_tools,
      error_classifier: cfg.value.error_classifier ?? {
        type: 'default',
        fatal_exceptions: ['ValueError', 'PermissionError', 'KeyError'],
        transient_exceptions: ['asyncio.TimeoutError', 'TimeoutError', 'ConnectionError', 'ConnectionResetError'],
        default_class: 'transient'
      },
      agents: cfg.value.agents.map((a) => ({
        name: a.name,
        persona_id: a.persona_id,
        public_description: a.public_description,
        enabled: a.enabled,
        provider_id: a.provider_id,
        tools_scope: a.tools_scope || inferToolsScope(a),
        tools:
          (a.tools_scope || inferToolsScope(a)) === 'list'
            ? Array.isArray(a.tools)
              ? a.tools
              : []
            : null,
        max_steps: a.max_steps ?? null,
        instructions: a.instructions ?? '',
        system_prompt: a.instructions ?? ''
      }))
    }

    const res = await axios.post('/api/subagent/config', payload)
    if (res.data.status === 'ok') {
      toast(res.data.message || tf('messages.saveSuccess', 'Saved successfully'), 'success')
    } else {
      toast(res.data.message || tf('messages.saveFailed', 'Failed to save'), 'error')
    }
  } catch (e: any) {
    toast(e?.response?.data?.message || tf('messages.saveFailed', 'Failed to save'), 'error')
  } finally {
    saving.value = false
  }
}

async function reload() {
  await Promise.all([loadConfig()])
}

onMounted(() => {
  reload()
})
</script>

<style scoped>
.subagent-page {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

.subagent-panels :deep(.v-expansion-panel-text__wrapper) {
  padding: 16px;
  padding-bottom: 42px;
}

.gap-2 {
  gap: 8px;
}

.gap-4 {
  gap: 16px;
}
</style>
