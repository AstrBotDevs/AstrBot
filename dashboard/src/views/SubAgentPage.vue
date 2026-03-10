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

    <v-card class="rounded-lg mb-6 border-thin" variant="flat" border>
      <v-card-text>
        <div class="text-subtitle-1 font-weight-bold mb-1">{{ tf('section.globalSettings', 'Global Settings') }}</div>
        <div class="text-caption text-medium-emphasis">
          {{ mainStateDescription }}
        </div>

        <v-divider class="my-4" />

        <v-row dense>
          <v-col cols="12" md="6">
            <v-switch
              v-model="cfg.main_enable"
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
          <v-col cols="12">
            <v-textarea
              v-model="cfg.router_system_prompt"
              :label="tf('form.routerPrompt', 'Router system prompt')"
              variant="outlined"
              density="comfortable"
              auto-grow
              hide-details="auto"
              prepend-inner-icon="mdi-source-branch"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field
              v-model="cfg.max_concurrent_subagent_runs"
              :label="tf('form.maxConcurrentRuns', 'Max concurrent subagent runs')"
              type="number"
              variant="outlined"
              density="comfortable"
              hide-details="auto"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field
              v-model="cfg.max_nested_depth"
              :label="tf('form.maxNestedDepth', 'Max nested handoff depth')"
              type="number"
              variant="outlined"
              density="comfortable"
              hide-details="auto"
            />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card class="rounded-lg mb-6 border-thin" variant="flat" border>
      <v-card-text>
        <div class="text-subtitle-1 font-weight-bold mb-1">{{ tf('section.advancedSettings', 'Runtime and Execution Settings') }}</div>
        <div class="text-caption text-medium-emphasis">
          {{ tf('section.advancedHint', 'Tune retries, worker polling, and optional execution overrides for subagent handoff.') }}
        </div>

        <v-divider class="my-4" />

        <v-expansion-panels variant="accordion" class="subagent-settings-panels">
          <v-expansion-panel elevation="0" class="border-thin rounded-lg">
            <v-expansion-panel-title>
              <div>
                <div class="text-subtitle-2 font-weight-bold">
                  {{ tf('section.runtime', 'Runtime') }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{ tf('section.runtimeHint', 'Retry policy for queued subagent tasks.') }}
                </div>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-row dense>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="cfg.runtime.max_attempts"
                    :label="tf('form.maxAttempts', 'Max retry attempts')"
                    type="number"
                    variant="outlined"
                    density="comfortable"
                    hide-details="auto"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="cfg.runtime.base_delay_ms"
                    :label="tf('form.baseDelayMs', 'Base retry delay (ms)')"
                    type="number"
                    variant="outlined"
                    density="comfortable"
                    hide-details="auto"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="cfg.runtime.max_delay_ms"
                    :label="tf('form.maxDelayMs', 'Max retry delay (ms)')"
                    type="number"
                    variant="outlined"
                    density="comfortable"
                    hide-details="auto"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="cfg.runtime.jitter_ratio"
                    :label="tf('form.jitterRatio', 'Retry jitter ratio (0-1)')"
                    type="number"
                    step="0.01"
                    variant="outlined"
                    density="comfortable"
                    hide-details="auto"
                  />
                </v-col>
              </v-row>
            </v-expansion-panel-text>
          </v-expansion-panel>

          <v-expansion-panel elevation="0" class="border-thin rounded-lg">
            <v-expansion-panel-title>
              <div>
                <div class="text-subtitle-2 font-weight-bold">
                  {{ tf('section.worker', 'Worker') }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{ tf('section.workerHint', 'Background worker polling and backoff settings.') }}
                </div>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-row dense>
                <v-col cols="12" md="4">
                  <v-text-field
                    v-model="cfg.worker.poll_interval"
                    :label="tf('form.pollInterval', 'Poll interval (seconds)')"
                    type="number"
                    step="0.1"
                    variant="outlined"
                    density="comfortable"
                    hide-details="auto"
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <v-text-field
                    v-model="cfg.worker.batch_size"
                    :label="tf('form.batchSize', 'Batch size')"
                    type="number"
                    variant="outlined"
                    density="comfortable"
                    hide-details="auto"
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <v-text-field
                    v-model="cfg.worker.error_retry_max_interval"
                    :label="tf('form.errorRetryMaxInterval', 'Worker error retry max interval (seconds)')"
                    type="number"
                    step="0.1"
                    variant="outlined"
                    density="comfortable"
                    hide-details="auto"
                  />
                </v-col>
              </v-row>
            </v-expansion-panel-text>
          </v-expansion-panel>

          <v-expansion-panel elevation="0" class="border-thin rounded-lg">
            <v-expansion-panel-title>
              <div>
                <div class="text-subtitle-2 font-weight-bold">
                  {{ tf('section.execution', 'Execution Overrides') }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{ tf('section.executionHint', 'Leave empty to follow Provider Settings for the current session.') }}
                </div>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-row dense>
                <v-col cols="12" md="6" xl="3">
                  <v-select
                    v-model="cfg.execution.computer_use_runtime"
                    :items="executionRuntimeOptions"
                    item-title="title"
                    item-value="value"
                    :label="tf('form.computerUseRuntime', 'Computer use runtime override')"
                    variant="outlined"
                    density="comfortable"
                    hide-details="auto"
                    clearable
                  />
                </v-col>
                <v-col cols="12" md="6" xl="3">
                  <v-text-field
                    v-model="cfg.execution.default_max_steps"
                    :label="tf('form.defaultMaxSteps', 'Default max steps override')"
                    type="number"
                    variant="outlined"
                    density="comfortable"
                    hide-details="auto"
                  />
                </v-col>
                <v-col cols="12" md="6" xl="3">
                  <v-text-field
                    v-model="cfg.execution.tool_call_timeout"
                    :label="tf('form.toolCallTimeout', 'Tool call timeout override (seconds)')"
                    type="number"
                    variant="outlined"
                    density="comfortable"
                    hide-details="auto"
                  />
                </v-col>
                <v-col cols="12" md="6" xl="3">
                  <v-select
                    v-model="cfg.execution.streaming_response"
                    :items="streamingOverrideOptions"
                    item-title="title"
                    item-value="value"
                    :label="tf('form.streamingResponse', 'Streaming response override')"
                    variant="outlined"
                    density="comfortable"
                    hide-details="auto"
                  />
                </v-col>
              </v-row>
            </v-expansion-panel-text>
          </v-expansion-panel>

          <v-expansion-panel elevation="0" class="border-thin rounded-lg">
            <v-expansion-panel-title>
              <div>
                <div class="text-subtitle-2 font-weight-bold">
                  {{ tf('section.expertSettings', 'Expert Settings') }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{ tf('section.expertHint', 'Rarely needed. Adjust error classification only if you need custom retry semantics.') }}
                </div>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <div class="text-caption font-weight-bold text-medium-emphasis mb-2">
                {{ tf('section.errorClassifier', 'Error Classifier') }}
              </div>
              <div class="d-flex flex-column gap-3">
                <v-select
                  v-model="cfg.error_classifier.type"
                  :items="errorClassifierTypeOptions"
                  item-title="title"
                  item-value="value"
                  :label="tf('form.errorClassifierType', 'Classifier type')"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                />
                <v-select
                  v-model="cfg.error_classifier.default_class"
                  :items="errorClassOptions"
                  item-title="title"
                  item-value="value"
                  :label="tf('form.errorDefaultClass', 'Default error class')"
                  variant="outlined"
                  density="comfortable"
                  hide-details="auto"
                />
                <v-combobox
                  v-model="cfg.error_classifier.fatal_exceptions"
                  :label="tf('form.fatalExceptions', 'Fatal exception class names')"
                  variant="outlined"
                  density="comfortable"
                  chips
                  multiple
                  clearable
                  hide-details="auto"
                />
                <v-combobox
                  v-model="cfg.error_classifier.transient_exceptions"
                  :label="tf('form.transientExceptions', 'Transient exception class names')"
                  variant="outlined"
                  density="comfortable"
                  chips
                  multiple
                  clearable
                  hide-details="auto"
                />
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </v-card-text>
    </v-card>

    <div class="d-flex align-center justify-space-between mb-4">
      <div class="d-flex align-center gap-2">
        <v-icon icon="mdi-robot" color="primary" size="small" />
        <div class="text-h6 font-weight-bold">{{ tf('section.title', 'SubAgents') }}</div>
        <v-chip size="small" variant="tonal" color="primary" class="ml-2">
          {{ cfg.agents.length }}
        </v-chip>
      </div>
      <v-btn prepend-icon="mdi-plus" color="primary" @click="addAgent">
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
            <v-badge
              dot
              :color="agent.enabled ? 'success' : 'grey'"
              inline
              class="mr-2"
            />
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
                      <PersonaSelector v-model="agent.persona_id" />
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

                <v-textarea
                  v-model="agent.instructions"
                  :label="tf('form.instructions', 'Custom SubAgent instructions')"
                  :hint="getAgentInstructionsHint(agent)"
                  :placeholder="tf('form.instructionsPlaceholder', 'Write custom instructions for this SubAgent')"
                  variant="outlined"
                  density="comfortable"
                  auto-grow
                  hide-details="auto"
                  prepend-inner-icon="mdi-script-text-outline"
                />
              </div>
            </v-col>

            <v-col cols="12" md="6">
              <div class="persona-preview-shell">
                <div class="text-subtitle-2 font-weight-bold mb-2">
                  {{ tf('cards.personaPreview', 'Persona quick preview') }}
                </div>
                <div class="text-caption text-medium-emphasis mb-3">
                  {{
                    agent.persona_id
                      ? tf('cards.personaPreviewHint', 'Shows the selected Persona system prompt and tool profile that this SubAgent will inherit.')
                      : tf('cards.personaPreviewEmptyHint', 'Choose a Persona to preview what this SubAgent will inherit.')
                  }}
                </div>
                <PersonaQuickPreview :model-value="agent.persona_id" class="h-100" />
              </div>
            </v-col>

            <v-col cols="12">
              <v-card variant="outlined" class="pa-4 subagent-section-card">
                <div class="text-subtitle-2 font-weight-bold mb-2">
                  {{ tf('section.toolSettings', 'Tool settings') }}
                </div>
                <div class="text-caption text-medium-emphasis mb-3">
                  {{ tf('section.toolSettingsHint', 'Control whether this SubAgent inherits Persona tools, uses selected tools only, or runs without tools.') }}
                </div>
                <v-row dense>
                  <v-col cols="12" md="4">
                    <v-select
                      v-model="agent.tools_scope"
                      :items="toolsScopeOptions"
                      item-title="title"
                      item-value="value"
                      :label="tf('form.toolsScope', 'Tool scope')"
                      variant="outlined"
                      density="comfortable"
                      hide-details="auto"
                    />
                  </v-col>

                  <v-col cols="12" md="5" v-if="agent.tools_scope === 'list'">
                    <v-select
                      v-model="agent.tools"
                      :items="availableTools"
                      item-title="name"
                      item-value="name"
                      :label="tf('form.toolsList', 'Allowed tools')"
                      :hint="tf('form.toolsListHint', 'Choose the tools this SubAgent can use directly.')"
                      :menu-props="{ maxHeight: 320 }"
                      variant="outlined"
                      density="comfortable"
                      hide-details="auto"
                      chips
                      multiple
                      clearable
                      closable-chips
                    >
                      <template #item="{ props, item }">
                        <v-list-item
                          v-bind="props"
                          :title="item.raw.name"
                          :subtitle="item.raw.description || item.raw.name"
                        />
                      </template>
                    </v-select>
                  </v-col>

                  <v-col
                    cols="12"
                    :md="agent.tools_scope === 'list' ? 3 : 4"
                  >
                    <v-text-field
                      v-model="agent.max_steps"
                      :label="tf('form.agentMaxSteps', 'Agent max steps')"
                      :hint="tf('form.agentMaxStepsHint', 'Defaults to 200 when not customized.')"
                      type="number"
                      variant="outlined"
                      density="comfortable"
                      hide-details="auto"
                    />
                  </v-col>
                </v-row>
              </v-card>
            </v-col>
          </v-row>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

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
type ErrorClass = 'fatal' | 'transient' | 'retryable'

type SelectOption<T> = {
  title: string
  value: T
}

type AvailableToolItem = {
  name: string
  description: string
}

type SubAgentItem = {
  __key: string
  name: string
  persona_id: string
  public_description: string
  enabled: boolean
  provider_id?: string
  tools_scope: ToolsScope
  tools?: string[]
  instructions: string
  max_steps: number | string
  extensions?: Record<string, unknown>
}

type SubAgentRuntimeConfig = {
  max_attempts: number | string
  base_delay_ms: number | string
  max_delay_ms: number | string
  jitter_ratio: number | string
}

type SubAgentWorkerConfig = {
  poll_interval: number | string
  batch_size: number | string
  error_retry_max_interval: number | string
}

type SubAgentExecutionConfig = {
  computer_use_runtime: string | null
  default_max_steps: number | string | null
  streaming_response: boolean | null
  tool_call_timeout: number | string | null
}

type SubAgentConfig = {
  main_enable: boolean
  remove_main_duplicate_tools: boolean
  router_system_prompt: string
  max_concurrent_subagent_runs: number | string
  max_nested_depth: number | string
  runtime: SubAgentRuntimeConfig
  worker: SubAgentWorkerConfig
  execution: SubAgentExecutionConfig
  error_classifier: {
    type: string
    fatal_exceptions: string[]
    transient_exceptions: string[]
    default_class: ErrorClass
  }
  extensions?: Record<string, unknown>
  agents: SubAgentItem[]
}

const { tm } = useModuleI18n('features/subagent')
const DEFAULT_AGENT_MAX_STEPS = 200

const loading = ref(false)
const saving = ref(false)
const availableTools = ref<AvailableToolItem[]>([])

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

function createAgentKey(index = 0): string {
  return `${Date.now()}_${index}_${Math.random().toString(16).slice(2)}`
}

function toNumberOrDefault(value: unknown, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function toNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function toNullableString(value: unknown): string | null {
  const normalized = (value ?? '').toString().trim()
  return normalized || null
}

function toPositiveNumberOrNull(value: unknown): number | null {
  const parsed = toNullableNumber(value)
  if (parsed === null || parsed <= 0) {
    return null
  }
  return parsed
}

function normalizeStringList(value: unknown, fallback: string[]): string[] {
  if (!Array.isArray(value)) {
    return [...fallback]
  }
  return value
    .map((item) => (item ?? '').toString().trim())
    .filter((item) => !!item)
}

function inferToolsScope(agent: any): ToolsScope {
  const explicitScope = (agent?.tools_scope ?? '').toString().toLowerCase()
  if (explicitScope === 'all' || explicitScope === 'none' || explicitScope === 'list' || explicitScope === 'persona') {
    return explicitScope as ToolsScope
  }
  if (Array.isArray(agent?.tools)) {
    return agent.tools.length === 0 ? 'none' : 'list'
  }
  if ((agent?.persona_id ?? '').toString().trim()) {
    return 'persona'
  }
  return 'all'
}

function getAgentInstructionsHint(agent: SubAgentItem): string {
  if (agent.persona_id) {
    return tf(
      'form.instructionsDisabledHint',
      'A Persona is selected, so its system prompt takes precedence. Clear Persona if you want to use custom instructions here.'
    )
  }
  return tf(
    'form.instructionsHint',
    'Used as this SubAgent\'s system prompt when no Persona is selected.'
  )
}

function normalizeAgentMaxSteps(agent: any): number | string {
  if (!Object.prototype.hasOwnProperty.call(agent ?? {}, 'max_steps')) {
    return DEFAULT_AGENT_MAX_STEPS
  }
  const maxSteps = toPositiveNumberOrNull(agent?.max_steps)
  return maxSteps ?? ''
}

function normalizeAgent(agent: any, index: number): SubAgentItem {
  return {
    __key: createAgentKey(index),
    name: (agent?.name ?? '').toString(),
    persona_id: (agent?.persona_id ?? '').toString(),
    public_description: (agent?.public_description ?? '').toString(),
    enabled: agent?.enabled !== false,
    provider_id: toNullableString(agent?.provider_id) ?? undefined,
    tools_scope: inferToolsScope(agent),
    tools: Array.isArray(agent?.tools)
      ? agent.tools.map((item: unknown) => (item ?? '').toString().trim()).filter((item: string) => !!item)
      : undefined,
    instructions: (agent?.instructions ?? agent?.system_prompt ?? '').toString(),
    max_steps: normalizeAgentMaxSteps(agent),
    extensions: Object.fromEntries(
      Object.entries(agent ?? {}).filter(([key]) => key.startsWith('x-'))
    )
  }
}

const cfg = ref<SubAgentConfig>({
  main_enable: false,
  remove_main_duplicate_tools: false,
  router_system_prompt: '',
  max_concurrent_subagent_runs: 8,
  max_nested_depth: 2,
  runtime: {
    max_attempts: 3,
    base_delay_ms: 500,
    max_delay_ms: 30000,
    jitter_ratio: 0.1
  },
  worker: {
    poll_interval: 1.0,
    batch_size: 8,
    error_retry_max_interval: 30.0
  },
  execution: {
    computer_use_runtime: null,
    default_max_steps: null,
    streaming_response: null,
    tool_call_timeout: null
  },
  extensions: {},
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

const toolsScopeOptions = computed<SelectOption<ToolsScope>[]>(() => [
  { title: tf('form.toolsScopeAll', 'All tools'), value: 'all' },
  { title: tf('form.toolsScopePersona', 'Follow persona tools'), value: 'persona' },
  { title: tf('form.toolsScopeList', 'Selected tools only'), value: 'list' },
  { title: tf('form.toolsScopeNone', 'No tools'), value: 'none' }
])

const errorClassOptions = computed<SelectOption<ErrorClass>[]>(() => [
  { title: tf('form.errorClassFatal', 'fatal'), value: 'fatal' },
  { title: tf('form.errorClassTransient', 'transient'), value: 'transient' },
  { title: tf('form.errorClassRetryable', 'retryable'), value: 'retryable' }
])

const errorClassifierTypeOptions = computed<SelectOption<string>[]>(() => [
  { title: tf('form.errorClassifierDefault', 'default'), value: 'default' }
])

const executionRuntimeOptions = computed<SelectOption<string | null>[]>(() => [
  { title: tf('form.followProvider', 'Follow Provider Settings'), value: null },
  { title: tf('form.runtimeNone', 'none'), value: 'none' },
  { title: tf('form.runtimeLocal', 'local'), value: 'local' },
  { title: tf('form.runtimeSandbox', 'sandbox'), value: 'sandbox' }
])

const streamingOverrideOptions = computed<SelectOption<boolean | null>[]>(() => [
  { title: tf('form.followProvider', 'Follow Provider Settings'), value: null },
  { title: tf('form.streamingFalse', 'Disabled'), value: false },
  { title: tf('form.streamingTrue', 'Enabled'), value: true }
])

function normalizeConfig(raw: any): SubAgentConfig {
  const errorClassifierRaw = raw?.error_classifier && typeof raw.error_classifier === 'object'
    ? raw.error_classifier
    : {}

  return {
    main_enable: !!raw?.main_enable,
    remove_main_duplicate_tools: !!raw?.remove_main_duplicate_tools,
    router_system_prompt: (raw?.router_system_prompt ?? '').toString(),
    max_concurrent_subagent_runs: toNumberOrDefault(raw?.max_concurrent_subagent_runs, 8),
    max_nested_depth: toNumberOrDefault(raw?.max_nested_depth, 2),
    runtime: {
      max_attempts: toNumberOrDefault(raw?.runtime?.max_attempts, 3),
      base_delay_ms: toNumberOrDefault(raw?.runtime?.base_delay_ms, 500),
      max_delay_ms: toNumberOrDefault(raw?.runtime?.max_delay_ms, 30000),
      jitter_ratio: toNumberOrDefault(raw?.runtime?.jitter_ratio, 0.1)
    },
    worker: {
      poll_interval: toNumberOrDefault(raw?.worker?.poll_interval, 1.0),
      batch_size: toNumberOrDefault(raw?.worker?.batch_size, 8),
      error_retry_max_interval: toNumberOrDefault(raw?.worker?.error_retry_max_interval, 30.0)
    },
    execution: {
      computer_use_runtime: toNullableString(raw?.execution?.computer_use_runtime),
      default_max_steps: toNullableNumber(raw?.execution?.default_max_steps),
      streaming_response:
        typeof raw?.execution?.streaming_response === 'boolean'
          ? raw.execution.streaming_response
          : null,
      tool_call_timeout: toNullableNumber(raw?.execution?.tool_call_timeout)
    },
    error_classifier: {
      type: (errorClassifierRaw.type ?? 'default').toString(),
      fatal_exceptions: normalizeStringList(errorClassifierRaw.fatal_exceptions, ['ValueError', 'PermissionError', 'KeyError']),
      transient_exceptions: normalizeStringList(
        errorClassifierRaw.transient_exceptions,
        ['asyncio.TimeoutError', 'TimeoutError', 'ConnectionError', 'ConnectionResetError']
      ),
      default_class: (
        ['fatal', 'transient', 'retryable'].includes((errorClassifierRaw.default_class ?? 'transient').toString())
          ? errorClassifierRaw.default_class
          : 'transient'
      ) as ErrorClass
    },
    extensions: Object.fromEntries(
      Object.entries(raw ?? {}).filter(([key]) => key.startsWith('x-'))
    ),
    agents: Array.isArray(raw?.agents) ? raw.agents.map((agent: unknown, index: number) => normalizeAgent(agent, index)) : []
  }
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

async function loadAvailableTools() {
  try {
    const res = await axios.get('/api/subagent/available-tools')
    if (res.data.status === 'ok' && Array.isArray(res.data.data)) {
      availableTools.value = res.data.data
        .map((item: any) => ({
          name: (item?.name ?? '').toString(),
          description: (item?.description ?? '').toString()
        }))
        .filter((item: AvailableToolItem) => !!item.name)
    }
  } catch {
    availableTools.value = []
  }
}

function addAgent() {
  cfg.value.agents.push({
    __key: createAgentKey(),
    name: '',
    persona_id: '',
    public_description: '',
    enabled: true,
    provider_id: undefined,
    tools_scope: 'all',
    tools: [],
    instructions: '',
    max_steps: DEFAULT_AGENT_MAX_STEPS,
    extensions: {}
  })
}

function removeAgent(index: number) {
  cfg.value.agents.splice(index, 1)
}

function validateBeforeSave(): boolean {
  const seen = new Set<string>()
  for (const agent of cfg.value.agents) {
    const name = (agent.name || '').trim()
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
  if (!validateBeforeSave()) {
    return
  }
  saving.value = true
  try {
    const payload = {
      main_enable: cfg.value.main_enable,
      remove_main_duplicate_tools: cfg.value.remove_main_duplicate_tools,
      router_system_prompt: cfg.value.router_system_prompt,
      max_concurrent_subagent_runs: toNumberOrDefault(cfg.value.max_concurrent_subagent_runs, 8),
      max_nested_depth: toNumberOrDefault(cfg.value.max_nested_depth, 2),
      runtime: {
        max_attempts: toNumberOrDefault(cfg.value.runtime.max_attempts, 3),
        base_delay_ms: toNumberOrDefault(cfg.value.runtime.base_delay_ms, 500),
        max_delay_ms: toNumberOrDefault(cfg.value.runtime.max_delay_ms, 30000),
        jitter_ratio: toNumberOrDefault(cfg.value.runtime.jitter_ratio, 0.1)
      },
      worker: {
        poll_interval: toNumberOrDefault(cfg.value.worker.poll_interval, 1.0),
        batch_size: toNumberOrDefault(cfg.value.worker.batch_size, 8),
        error_retry_max_interval: toNumberOrDefault(cfg.value.worker.error_retry_max_interval, 30.0)
      },
      execution: {
        computer_use_runtime: toNullableString(cfg.value.execution.computer_use_runtime),
        default_max_steps: toNullableNumber(cfg.value.execution.default_max_steps),
        streaming_response: cfg.value.execution.streaming_response,
        tool_call_timeout: toNullableNumber(cfg.value.execution.tool_call_timeout)
      },
      ...(cfg.value.extensions ?? {}),
      error_classifier: {
        type: (cfg.value.error_classifier.type || 'default').toString(),
        fatal_exceptions: normalizeStringList(cfg.value.error_classifier.fatal_exceptions, ['ValueError', 'PermissionError', 'KeyError']),
        transient_exceptions: normalizeStringList(
          cfg.value.error_classifier.transient_exceptions,
          ['asyncio.TimeoutError', 'TimeoutError', 'ConnectionError', 'ConnectionResetError']
        ),
        default_class: cfg.value.error_classifier.default_class
      },
      agents: cfg.value.agents.map((agent) => ({
        ...(agent.extensions ?? {}),
        name: agent.name,
        persona_id: toNullableString(agent.persona_id),
        public_description: agent.public_description,
        enabled: agent.enabled,
        provider_id: toNullableString(agent.provider_id),
        tools_scope: agent.tools_scope || inferToolsScope(agent),
        tools:
          (agent.tools_scope || inferToolsScope(agent)) === 'list'
            ? normalizeStringList(agent.tools, [])
            : null,
        max_steps: toPositiveNumberOrNull(agent.max_steps),
        instructions: (agent.instructions || '').toString(),
        system_prompt: (agent.instructions || '').toString()
      }))
    }

    const res = await axios.post('/api/subagent/config', payload)
    if (res.data.status === 'ok') {
      toast(res.data.message || tf('messages.saveSuccess', 'Saved successfully'), 'success')
      cfg.value = normalizeConfig(payload)
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
  await Promise.all([loadConfig(), loadAvailableTools()])
}

onMounted(() => {
  reload()
})
</script>

<style scoped>
.subagent-page {
  padding: 24px;
  max-width: 1280px;
  margin: 0 auto;
}

.subagent-panels :deep(.v-expansion-panel-text__wrapper) {
  padding: 16px;
  padding-bottom: 42px;
}

.subagent-section-card {
  border-color: rgba(var(--v-border-color), var(--v-border-opacity));
}

.persona-preview-shell {
  padding: 4px 4px 0;
}

.gap-2 {
  gap: 8px;
}

.gap-3 {
  gap: 12px;
}

.gap-4 {
  gap: 16px;
}
</style>
