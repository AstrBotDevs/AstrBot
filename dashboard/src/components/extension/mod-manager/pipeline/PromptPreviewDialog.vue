<script setup lang="ts">
import { computed, mergeProps } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import type { LlmPromptPreview, SystemPromptSegment } from './pipelineSnapshotTypes'

const { tm } = useModuleI18n('features/extension')

const props = defineProps<{
  show: boolean
  preview: LlmPromptPreview | null
}>()

const emit = defineEmits<{
  (e: 'update:show', value: boolean): void
}>()

const _show = computed({
  get() {
    return props.show
  },
  set(value: boolean) {
    emit('update:show', value)
  }
})

const hasPreview = computed(() => Boolean(props.preview))

const injectedBy = computed(() => (props.preview?.injected_by ?? []).filter(Boolean))

const executedHandlers = computed(() => (props.preview?.render_executed_handlers ?? []).filter(Boolean))
const renderWarnings = computed(() => (props.preview?.render_warnings ?? []).filter(Boolean))

const renderedSystemPrompt = computed(() => String(props.preview?.rendered_system_prompt ?? props.preview?.system_prompt ?? ''))
const renderedPrompt = computed(() => String(props.preview?.rendered_prompt ?? props.preview?.prompt ?? ''))

const showFinalPrompt = computed(() => renderedPrompt.value.trim().length > 0)

const systemPromptSegments = computed<SystemPromptSegment[]>(() => props.preview?.rendered_system_prompt_segments ?? [])
const useSegmentedSystemPrompt = computed(() => systemPromptSegments.value.length > 0)

const extraUserContentSegments = computed<SystemPromptSegment[]>(() => props.preview?.rendered_extra_user_content_segments ?? [])
const useSegmentedExtraUserContent = computed(() => extraUserContentSegments.value.length > 0)

const finalPromptSegments = computed<SystemPromptSegment[]>(() => {
  const out: SystemPromptSegment[] = []

  const sys = systemPromptSegments.value
  const extra = extraUserContentSegments.value

  if (sys.length) {
    out.push(...sys)
  } else {
    const sysText = String(renderedSystemPrompt.value ?? '')
    if (sysText) out.push({ text: sysText, source: null, sources: null })
  }

  if (extra.length) {
    if (out.length) out.push({ text: '\n\n', source: null, sources: null })
    out.push(...extra)
  }

  return out
})

type PromptRenderBlock =
  | { kind: 'text'; text: string; seg: SystemPromptSegment }
  | { kind: 'newline'; text: '\n' }

const splitWithNewlines = (text: string): Array<{ kind: 'text'; text: string } | { kind: 'newline'; text: '\n' }> => {
  const parts = String(text ?? '').split('\n')
  const out: Array<{ kind: 'text'; text: string } | { kind: 'newline'; text: '\n' }> = []
  for (let i = 0; i < parts.length; i++) {
    if (i > 0) out.push({ kind: 'newline', text: '\n' })
    const t = parts[i]
    if (t) out.push({ kind: 'text', text: t })
  }
  return out
}

const finalPromptBlocks = computed<PromptRenderBlock[]>(() => {
  const out: PromptRenderBlock[] = []
  for (const seg of finalPromptSegments.value) {
    const text = String(seg?.text ?? '')
    if (!text) continue
    for (const p of splitWithNewlines(text)) {
      if (p.kind === 'newline') out.push({ kind: 'newline', text: '\n' })
      else out.push({ kind: 'text', text: p.text, seg })
    }
  }
  return out
})

const useSegmentedFinalPrompt = computed(() => useSegmentedSystemPrompt.value || useSegmentedExtraUserContent.value)
const finalPromptText = computed(() => finalPromptSegments.value.map((s) => String(s?.text ?? '')).join(''))

const contextsSummary = computed(() => {
  const ctx = props.preview?.contexts
  if (!ctx) return '—'
  if (!ctx.present) return 'present=false'
  const parts: string[] = ['present=true']
  if (ctx.source) parts.push(`source=${ctx.source}`)
  if (typeof ctx.count === 'number') parts.push(`count=${ctx.count}`)
  if (ctx.note) parts.push(`note=${ctx.note}`)
  return parts.join(', ')
})

const renderWarningsText = computed(() => renderWarnings.value.map((x) => `- ${x}`).join('\n'))

const systemPromptEmptyHint = computed(() => {
  const systemPrompt = String(renderedSystemPrompt.value ?? '').trim()
  if (systemPrompt) return ''

  const list = injectedBy.value
  const hasPersonaOverwrite = list.some((x) => x?.field === 'persona_prompt' && x?.mutation === 'overwrite')
  const hasAnyPersona = list.some((x) => x?.field === 'persona_prompt')

  const lines: string[] = []
  lines.push('当前预览渲染出的 System Prompt 为空。')

  if (hasPersonaOverwrite || hasAnyPersona) {
    lines.push('注意：persona_prompt 的 injected_by 主要用于展示“注入链路”，不一定会直接转化为 System Prompt 文本。')
  }

  if (renderWarnings.value.length) {
    lines.push('本次 Dry-run 执行出现告警/拦截：请查看下方 Render Warnings。')
  } else {
    lines.push('常见原因：未设置默认 Persona / 当前 Persona 的系统提示词为空 / 当前 UMO 不属于任何会话配置。')
  }

  return lines.join('\n')
})

const hasOverwriteConflict = computed(() => {
  const list = injectedBy.value
  const overwritesPrompt = list.filter((x) => x?.field === 'prompt' && x?.mutation === 'overwrite').length
  const overwritesSystem = list.filter((x) => x?.field === 'system_prompt' && x?.mutation === 'overwrite').length
  return overwritesPrompt > 1 || overwritesSystem > 1
})

const statusLabel = (s: any) => String(s || 'unknown')
const statusColor = (s: any) => {
  const v = String(s || '')
  if (v === 'executed') return 'success'
  if (v === 'blocked') return 'warning'
  if (v === 'errored') return 'error'
  return 'secondary'
}

function getPluginColor(pluginName: string): { border: string } {
  let hash = 0
  for (let i = 0; i < pluginName.length; i++) {
    hash = pluginName.charCodeAt(i) + ((hash << 5) - hash)
  }
  const hue = Math.abs(hash) % 360
  return {
    border: `hsl(${hue}, 70%, 45%)`
  }
}

const isWhitespaceOnly = (text: unknown) => /^\s+$/.test(String(text ?? ''))

const segmentStyle = (seg: SystemPromptSegment) => {
  if (isWhitespaceOnly(seg?.text)) {
    return { borderLeft: '0' }
  }

  const source = seg.source
  if (!source?.plugin) {
    return { borderLeft: '0' }
  }
  const color = getPluginColor(String(source.plugin))
  return { borderLeftColor: color.border }
}

const segmentSources = (seg: SystemPromptSegment): SystemPromptSegment['source'][] => {
  const srcs = (seg.sources ?? []).filter(Boolean) as any[]
  if (srcs.length) return srcs as any
  return seg.source ? [seg.source] : []
}

const segmentTooltipText = (seg: SystemPromptSegment) => {
  const sources = segmentSources(seg)
  if (!sources.length) return '—'
  if (sources.length === 1) {
    const s = sources[0] as any
    return [
      `plugin: ${s.plugin}`,
      `handler: ${s.handler}`,
      `priority: ${s.priority}`,
      `field: ${s.field}`,
      `mutation: ${s.mutation}`,
      `status: ${s.status}`
    ].join('\n')
  }
  const lines: string[] = []
  lines.push(`sources: ${sources.length}`)
  for (const s of sources as any[]) {
    lines.push(`- ${s.plugin} | ${s.handler} | P${s.priority} | ${s.field}:${s.mutation} | ${s.status}`)
  }
  return lines.join('\n')
}

const formatSegmentCopyText = (seg: SystemPromptSegment, textOverride?: string) => {
  const parts: string[] = []
  if (seg.source) {
    parts.push(segmentTooltipText(seg))
    parts.push('')
  } else {
    parts.push('source: unknown')
    parts.push('')
  }
  parts.push(String(textOverride ?? seg.text ?? ''))
  return parts.join('\n')
}

const copyToClipboard = async (text: string) => {
  const content = String(text ?? '')
  const navAny = navigator as any
  if (navAny?.clipboard?.writeText) {
    await navAny.clipboard.writeText(content)
    return
  }

  const el = document.createElement('textarea')
  el.value = content
  el.setAttribute('readonly', 'true')
  el.style.position = 'fixed'
  el.style.left = '-9999px'
  el.style.top = '0'
  document.body.appendChild(el)
  el.select()
  document.execCommand('copy')
  document.body.removeChild(el)
}

const copySegment = async (seg: SystemPromptSegment, textOverride?: string) => {
  await copyToClipboard(formatSegmentCopyText(seg, textOverride))
}

const close = () => emit('update:show', false)
</script>

<template>
  <v-dialog v-model="_show" max-width="980">
    <v-card class="ppd">
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2" color="primary">mdi-text-box-search-outline</v-icon>
        <span class="text-h6">{{ tm('pipeline.promptPreview.title') }}</span>
        <v-spacer />
        <v-btn icon variant="text" @click="close">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>

      <v-divider />

      <v-card-text class="ppd__body">
        <div v-if="!hasPreview" class="ppd__empty">
          <v-icon size="56" color="info" class="mb-2">mdi-text-box-remove-outline</v-icon>
          <div class="text-h6 mb-1">{{ tm('pipeline.promptPreview.emptyTitle') }}</div>
          <div class="text-body-2 text-medium-emphasis">{{ tm('pipeline.promptPreview.emptyHint') }}</div>
        </div>

        <template v-else>
          <v-alert v-if="hasOverwriteConflict" type="warning" variant="tonal" density="comfortable" class="mb-4">
            {{ tm('pipeline.promptPreview.overwriteWarn') }}
          </v-alert>

          <div class="d-flex flex-wrap ga-2 mb-3">
            <v-chip size="small" color="secondary" variant="tonal" class="font-weight-medium">
              {{ tm('pipeline.promptPreview.contexts') }}: {{ contextsSummary }}
            </v-chip>
            <v-chip size="small" color="secondary" variant="tonal" class="font-weight-medium">
              {{ tm('pipeline.promptPreview.injectedBy') }}: {{ injectedBy.length }}
            </v-chip>
            <v-chip
              v-if="executedHandlers.length"
              size="small"
              color="secondary"
              variant="tonal"
              class="font-weight-medium"
            >
              Dry-run handlers: {{ executedHandlers.length }}
            </v-chip>
            <v-chip v-if="renderWarnings.length" size="small" color="warning" variant="tonal" class="font-weight-medium">
              Render warnings: {{ renderWarnings.length }}
            </v-chip>
          </div>

          <v-alert
            v-if="renderWarnings.length"
            type="warning"
            variant="tonal"
            density="comfortable"
            class="mb-4"
            style="white-space: pre-wrap"
          >
            <div class="font-weight-bold mb-2">Render Warnings</div>
            {{ renderWarningsText }}
          </v-alert>

          <v-card variant="tonal" class="mb-4">
            <v-card-title class="text-subtitle-1 font-weight-bold">最终提示词（system_prompt + extra_user_content_parts）</v-card-title>
            <v-card-text>
              <template v-if="useSegmentedFinalPrompt">
                <div class="ppd__seg-pre">
                  <template v-for="(block, idx) in finalPromptBlocks" :key="idx">
                    <template v-if="block.kind === 'newline'">{{ block.text }}</template>

                    <template v-else>
                      <template v-if="block.seg.source">
                        <v-menu location="bottom" :close-on-content-click="false">
                          <template #activator="{ props: menuProps }">
                            <v-tooltip location="top">
                              <template #activator="{ props: tooltipProps }">
                                <span
                                  v-bind="mergeProps(menuProps, tooltipProps)"
                                  class="ppd__seg ppd__seg--clickable"
                                  :style="segmentStyle(block.seg)"
                                >
                                  {{ block.text }}
                                </span>
                              </template>
                              <span class="ppd__tooltip-text">{{ segmentTooltipText(block.seg) }}</span>
                            </v-tooltip>
                          </template>

                          <v-card class="ppd__seg-pop" rounded="lg" variant="tonal">
                            <v-card-title class="text-subtitle-2 font-weight-bold d-flex align-center">
                              Segment Source
                              <v-spacer />
                              <v-btn icon variant="text" size="small" @click="copySegment(block.seg, block.text)">
                                <v-icon size="18">mdi-content-copy</v-icon>
                              </v-btn>
                            </v-card-title>
                            <v-divider />
                            <v-card-text class="text-body-2">
                              <div v-if="(block.seg.sources?.length ?? 0) > 1" class="text-caption text-medium-emphasis mb-2">
                                sources: {{ block.seg.sources?.length ?? 0 }}
                              </div>

                              <div class="ppd__seg-meta">
                                <template
                                  v-for="(s, si) in (block.seg.sources?.length ? block.seg.sources : [block.seg.source])"
                                  :key="si"
                                >
                                  <template v-if="s">
                                    <div class="ppd__seg-row">
                                      <div class="ppd__seg-k">{{ tm('pipeline.promptPreview.headers.plugin') }}</div>
                                      <div class="ppd__seg-v">{{ s.plugin }}</div>
                                    </div>
                                    <div class="ppd__seg-row">
                                      <div class="ppd__seg-k">{{ tm('pipeline.promptPreview.headers.handler') }}</div>
                                      <div class="ppd__seg-v ppd__mono">{{ s.handler }}</div>
                                    </div>
                                    <div class="ppd__seg-row">
                                      <div class="ppd__seg-k">{{ tm('pipeline.promptPreview.headers.priority') }}</div>
                                      <div class="ppd__seg-v ppd__mono">P{{ s.priority }}</div>
                                    </div>
                                    <div class="ppd__seg-row">
                                      <div class="ppd__seg-k">{{ tm('pipeline.promptPreview.headers.field') }}</div>
                                      <div class="ppd__seg-v ppd__mono">{{ s.field }}</div>
                                    </div>
                                    <div class="ppd__seg-row">
                                      <div class="ppd__seg-k">{{ tm('pipeline.promptPreview.headers.mutation') }}</div>
                                      <div class="ppd__seg-v ppd__mono">{{ s.mutation }}</div>
                                    </div>
                                    <div class="ppd__seg-row">
                                      <div class="ppd__seg-k">status</div>
                                      <div class="ppd__seg-v ppd__mono">{{ s.status }}</div>
                                    </div>
                                    <v-divider
                                      v-if="(block.seg.sources?.length ?? 0) > 1 && si < (block.seg.sources?.length ?? 0) - 1"
                                      class="my-2"
                                    />
                                  </template>
                                </template>
                              </div>
                            </v-card-text>
                          </v-card>
                        </v-menu>
                      </template>

                      <template v-else>{{ block.text }}</template>
                    </template>
                  </template>
                </div>
              </template>

              <template v-else>
                <pre class="ppd__pre"><code>{{ finalPromptText.trim() ? finalPromptText : '—' }}</code></pre>
              </template>
            </v-card-text>
          </v-card>

          <v-alert
            v-if="systemPromptEmptyHint"
            type="info"
            variant="tonal"
            density="comfortable"
            class="mb-4"
            style="white-space: pre-wrap"
          >
            {{ systemPromptEmptyHint }}
          </v-alert>


          <v-card v-if="showFinalPrompt" variant="tonal" class="mb-4">
            <v-card-title class="text-subtitle-1 font-weight-bold">{{ tm('pipeline.promptPreview.finalPrompt') }}</v-card-title>
            <v-card-text>
              <pre class="ppd__pre"><code>{{ renderedPrompt }}</code></pre>
            </v-card-text>
          </v-card>

          <v-card variant="tonal" class="mb-4">
            <v-card-title class="text-subtitle-1 font-weight-bold">{{ tm('pipeline.promptPreview.chain') }}</v-card-title>
            <v-card-text>
              <v-table density="compact" class="ppd__table">
                <thead>
                  <tr>
                    <th class="text-left">{{ tm('pipeline.promptPreview.headers.plugin') }}</th>
                    <th class="text-left">{{ tm('pipeline.promptPreview.headers.handler') }}</th>
                    <th class="text-left">{{ tm('pipeline.promptPreview.headers.priority') }}</th>
                    <th class="text-left">{{ tm('pipeline.promptPreview.headers.field') }}</th>
                    <th class="text-left">{{ tm('pipeline.promptPreview.headers.mutation') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(item, idx) in injectedBy" :key="idx">
                    <td class="text-truncate" style="max-width: 200px">
                      {{ item.plugin?.display_name || item.plugin?.name || '—' }}
                    </td>
                    <td class="ppd__mono text-truncate" style="max-width: 360px">
                      {{ item.handler?.handler_full_name || '—' }}
                    </td>
                    <td class="ppd__mono">P{{ item.priority }}</td>
                    <td class="ppd__mono">{{ item.field }}</td>
                    <td class="ppd__mono">{{ item.mutation }}</td>
                  </tr>
                </tbody>
              </v-table>
            </v-card-text>
          </v-card>

          <v-card v-if="executedHandlers.length" variant="tonal" class="mb-4">
            <v-card-title class="text-subtitle-1 font-weight-bold">Dry-run 执行链路（OnLLMRequestEvent）</v-card-title>
            <v-card-text>
              <v-table density="compact" class="ppd__table">
                <thead>
                  <tr>
                    <th class="text-left">Plugin</th>
                    <th class="text-left">Handler</th>
                    <th class="text-left">P</th>
                    <th class="text-left">Status</th>
                    <th class="text-left">Stop</th>
                    <th class="text-left">Diff</th>
                    <th class="text-left">Blocked</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(h, idx) in executedHandlers" :key="idx">
                    <td class="text-truncate" style="max-width: 200px">
                      {{ h.plugin?.display_name || h.plugin?.name || '—' }}
                    </td>
                    <td class="ppd__mono text-truncate" style="max-width: 360px">
                      {{ h.handler?.handler_full_name || '—' }}
                    </td>
                    <td class="ppd__mono">P{{ h.priority }}</td>
                    <td>
                      <v-chip :color="statusColor(h.status)" size="x-small" variant="tonal">
                        {{ statusLabel(h.status) }}
                      </v-chip>
                      <div v-if="h.error" class="text-caption text-medium-emphasis" style="max-width: 320px">
                        {{ h.error }}
                      </div>
                    </td>
                    <td class="ppd__mono">{{ h.stop_event ? 'true' : 'false' }}</td>
                    <td class="ppd__mono">
                      <span v-if="h.diff?.prompt?.changed">prompt</span>
                      <span v-if="h.diff?.system_prompt?.changed"> system</span>
                      <span v-if="!h.diff?.prompt?.changed && !h.diff?.system_prompt?.changed">—</span>
                    </td>
                    <td class="ppd__mono" style="max-width: 260px; white-space: normal">
                      <div v-if="(h.blocked?.length ?? 0) > 0">
                        <div class="ppd__mono">{{ h.blocked?.length ?? 0 }}</div>
                        <div
                          v-for="(b, bi) in (h.blocked ?? []).slice(0, 2)"
                          :key="bi"
                          class="text-caption text-medium-emphasis"
                        >
                          {{ b.action }}: {{ b.reason }}
                        </div>
                        <div v-if="(h.blocked?.length ?? 0) > 2" class="text-caption text-medium-emphasis">...</div>
                      </div>
                      <span v-else>—</span>
                    </td>
                  </tr>
                </tbody>
              </v-table>

              <div v-if="executedHandlers.some((h) => (h.blocked?.length ?? 0) > 0)" class="text-caption mt-3">
                blocked 详情请结合后端返回的 reason（send/request_llm 等会被预览策略阻止）。
              </div>
            </v-card-text>
          </v-card>
        </template>
      </v-card-text>

      <v-divider />

      <v-card-actions>
        <v-spacer />
        <v-btn color="primary" variant="tonal" @click="close">{{ tm('pipeline.promptPreview.close') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.ppd__body {
  max-height: 74vh;
  overflow-y: auto;
}

.ppd__empty {
  height: 52vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.ppd__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.ppd__pre {
  margin: 0;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.8);
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.55;
}

.ppd__seg-pre {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.8);
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.55;
}

.ppd__seg {
  display: inline;
  border-left: 3px solid transparent;
  padding: 0 0 0 8px;
  margin: 0;
  border-radius: 0;
  background: transparent;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}

.ppd__seg--clickable {
  cursor: pointer;
}

.ppd__seg--clickable:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.ppd__seg--unknown {
  opacity: 0.8;
}

.ppd__seg-pop {
  max-width: min(520px, 92vw);
}

.ppd__seg-meta {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.ppd__seg-row {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 10px;
  align-items: start;
}

.ppd__seg-k {
  font-weight: 800;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.ppd__seg-v {
  color: rgba(var(--v-theme-on-surface), 0.92);
}

.ppd__table :deep(th) {
  font-weight: 800;
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.ppd__table :deep(td) {
  font-size: 12px;
}
</style>