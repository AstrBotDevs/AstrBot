<script setup lang="ts">
import { computed } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import type { PipelineStageId } from './pipelineSnapshotTypes'
import type { TraceRow } from './traceGrouping'

const { tm } = useModuleI18n('features/extension')

const props = defineProps<{
  row: TraceRow | null
}>()

const emit = defineEmits<{
  (e: 'select-plugin', pluginName: string): void
  (e: 'navigate-pipeline', payload: { stageId: PipelineStageId; participantId: string }): void
}>()

const pluginName = computed(() => props.row?.participant?.plugin?.name || '')
const pluginDisplay = computed(() => props.row?.participant?.plugin?.display_name || props.row?.participant?.plugin?.name || '—')

const handlerFullName = computed(() => props.row?.participant?.handler?.handler_full_name || '—')
const handlerName = computed(() => props.row?.participant?.handler?.handler_name || props.row?.participant?.handler?.handler_full_name || '—')

const stageTitle = computed(() => props.row?.stageTitle || props.row?.stageId || '—')
const stageId = computed(() => props.row?.stageId || null)

const target = computed(() => String(props.row?.effect?.target || '—'))
const op = computed(() => String(props.row?.effect?.op || '—'))
const confidence = computed(() => String(props.row?.effect?.confidence || 'unknown'))
const evidence = computed(() => (typeof props.row?.effect?.evidence === 'string' ? props.row?.effect?.evidence : ''))

const locationText = computed(() => {
  const modulePath = props.row?.participant?.handler?.handler_module_path || ''
  const lineno = props.row?.effect?.lineno
  const col = props.row?.effect?.col
  const parts: string[] = []
  if (modulePath) parts.push(modulePath)
  if (typeof lineno === 'number') parts.push(`line=${lineno}`)
  if (typeof col === 'number') parts.push(`col=${col}`)
  return parts.length ? parts.join('  ') : '—'
})

const confidenceLabel = (cRaw: string) => {
  const c = String(cRaw || '')
  if (c === 'high') return '高'
  if (c === 'medium') return '中'
  if (c === 'low') return '低'
  if (c === 'unknown') return '未知'
  return '—'
}

const confidenceColor = (cRaw: string) => {
  const c = String(cRaw || '')
  if (c === 'high') return 'success'
  if (c === 'medium') return 'warning'
  if (c === 'low') return 'grey'
  return 'secondary'
}

const openPlugin = () => {
  if (!pluginName.value) return
  emit('select-plugin', pluginName.value)
}

const navigatePipeline = () => {
  const stage = stageId.value
  const participantId = props.row?.participantId
  if (!stage || !participantId) return
  emit('navigate-pipeline', { stageId: stage, participantId })
}
</script>

<template>
  <v-card class="tip h-100 d-flex flex-column" rounded="lg" variant="flat">
    <div class="px-4 py-3 d-flex align-start ga-3">
      <div class="d-flex flex-column" style="min-width: 0">
        <div class="text-subtitle-1 font-weight-bold tip__title">
          影响点详情
        </div>

        <div v-if="row" class="mt-1 text-caption text-medium-emphasis d-flex align-center flex-wrap ga-2">
          <v-chip size="x-small" color="info" variant="tonal" class="font-weight-bold">
            target: {{ target }}
          </v-chip>
          <v-chip size="x-small" color="secondary" variant="tonal" class="font-weight-bold">
            op: {{ op }}
          </v-chip>
          <v-chip size="x-small" :color="confidenceColor(confidence)" variant="tonal" class="font-weight-bold">
            置信度 {{ confidenceLabel(confidence) }}
          </v-chip>
        </div>

        <div v-else class="mt-1 text-caption text-medium-emphasis">
          请在左侧鱼骨图选择一个具体影响点
        </div>
      </div>

      <v-spacer />

      <v-btn
        v-if="row"
        size="small"
        color="secondary"
        variant="tonal"
        class="font-weight-medium"
        @click="navigatePipeline"
      >
        <v-icon start>mdi-open-in-new</v-icon>
        跳转到执行链路
      </v-btn>
    </div>

    <v-divider />

    <div class="tip__scroll pa-3">
      <div v-if="!row" class="h-100 d-flex flex-column align-center justify-center pa-8">
        <v-icon size="56" color="info" class="mb-2">mdi-map-marker-path</v-icon>
        <div class="text-h6 mb-1">未选择影响点</div>
        <div class="text-body-2 text-medium-emphasis">点击左侧鱼骨图的影响点节点以查看详情。</div>
      </div>

      <div v-else class="d-flex flex-column ga-4">
        <div class="tip__section">
          <div class="text-subtitle-2 font-weight-bold mb-2">基本信息</div>

          <div class="d-flex flex-column ga-2">
            <div class="tip__kv">
              <div class="tip__k">阶段</div>
              <div class="tip__v">{{ stageTitle }}</div>
            </div>

            <div class="tip__kv">
              <div class="tip__k">插件</div>
              <div class="tip__v">
                <span class="tip__plugin-link" role="button" tabindex="0" @click="openPlugin" @keydown.enter="openPlugin">
                  {{ pluginDisplay }}
                </span>
                <span class="tip__muted ml-2">{{ pluginName }}</span>
              </div>
            </div>

            <div class="tip__kv">
              <div class="tip__k">处理器</div>
              <div class="tip__v">
                <div class="tip__mono tip__wrap">{{ handlerFullName }}</div>
                <div class="tip__muted text-caption">{{ handlerName }}</div>
              </div>
            </div>

            <div class="tip__kv">
              <div class="tip__k">影响操作</div>
              <div class="tip__v tip__mono tip__wrap">{{ target }}  ·  {{ op }}</div>
            </div>
          </div>
        </div>

        <div class="tip__section">
          <div class="text-subtitle-2 font-weight-bold mb-2">推断依据</div>
          <div v-if="evidence" class="tip__mono tip__wrap tip__evidence">{{ evidence }}</div>
          <div v-else class="text-body-2 text-medium-emphasis">—</div>
        </div>

        <div class="tip__section">
          <div class="text-subtitle-2 font-weight-bold mb-2">代码位置</div>
          <div class="tip__mono tip__wrap">{{ locationText }}</div>
          <div class="mt-1 text-caption text-medium-emphasis">
            位置来自 effects 的 lineno/col 与处理器 module_path（若后端提供）。
          </div>
        </div>
      </div>
    </div>
  </v-card>
</template>

<style scoped>
.tip {
  min-height: 0;
}

.tip__scroll {
  min-height: 0;
  overflow-y: auto;
}

.tip__title {
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.tip__mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.tip__wrap {
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  min-width: 0;
}

.tip__kv {
  display: grid;
  grid-template-columns: 84px 1fr;
  gap: 10px;
  align-items: start;
}

.tip__k {
  color: rgba(var(--v-theme-on-surface), 0.7);
  font-weight: 700;
  font-size: 12px;
}

.tip__v {
  min-width: 0;
}

.tip__muted {
  color: rgba(var(--v-theme-on-surface), 0.62);
}

.tip__plugin-link {
  cursor: pointer;
  text-decoration: underline;
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
  overflow-wrap: anywhere;
  word-break: break-word;
  max-width: 100%;
}

.tip__plugin-link:hover {
  color: rgb(var(--v-theme-info));
}

.tip__section {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 12px;
  padding: 12px;
  background: rgba(var(--v-theme-surface), 0.75);
}

.tip__evidence {
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(var(--v-theme-surface-variant), 0.12);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
</style>