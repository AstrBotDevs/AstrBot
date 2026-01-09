import axios from 'axios'
import { onMounted, ref, unref } from 'vue'
import type { Ref } from 'vue'
import type { ApiResponse } from '@/components/extension/mod-manager/types'
import type { PipelineSnapshot, SnapshotScopeMode } from '@/components/extension/mod-manager/pipeline/pipelineSnapshotTypes'

type PipelineSnapshotResponse = ApiResponse<PipelineSnapshot>

export interface UsePipelineSnapshotOptions {
  scopeMode?: SnapshotScopeMode | Ref<SnapshotScopeMode>
  umo?: string | null | Ref<string | null>
  autoRefresh?: boolean
  render?: boolean | Ref<boolean>
  previewPrompt?: string | Ref<string>
}

export interface PipelineSnapshotRefreshOptions {
  scopeMode?: SnapshotScopeMode
  umo?: string | null
  forceRefresh?: boolean
  render?: boolean
  previewPrompt?: string
}

export function usePipelineSnapshot(options: UsePipelineSnapshotOptions = {}): {
  snapshot: Ref<PipelineSnapshot | null>
  loading: Ref<boolean>
  error: Ref<string | null>
  refresh: (opts?: PipelineSnapshotRefreshOptions) => Promise<void>
} {
  const snapshot = ref<PipelineSnapshot | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const readDefaults = (): { scopeMode: SnapshotScopeMode; umo: string | null; render: boolean; previewPrompt: string } => {
    const scopeMode = (unref(options.scopeMode) ?? 'global') as SnapshotScopeMode
    const umo = (unref(options.umo) ?? null) as string | null
    const render = Boolean(unref(options.render) ?? true)

    const previewPromptRaw = unref(options.previewPrompt)
    const previewPrompt = String(previewPromptRaw ?? '').trim()

    return { scopeMode, umo, render, previewPrompt }
  }

  async function refresh(opts: PipelineSnapshotRefreshOptions = {}) {
    const defaults = readDefaults()
    const scopeMode = opts.scopeMode ?? defaults.scopeMode
    const umo = opts.umo ?? defaults.umo
    const forceRefresh = opts.forceRefresh ?? false
    const render = opts.render ?? defaults.render
    const previewPrompt = String(opts.previewPrompt ?? defaults.previewPrompt ?? '').trim()

    loading.value = true
    error.value = null

    try {
      const response = await axios.get<PipelineSnapshotResponse>('/api/pipeline/snapshot', {
        params: {
          umo: scopeMode === 'session' ? (umo || undefined) : undefined,
          force_refresh: forceRefresh ? true : undefined,
          render: render ? true : undefined,
          preview_prompt: render && previewPrompt ? previewPrompt : undefined
        }
      })

      if (response.data?.status !== 'ok') {
        throw new Error(response.data?.message || 'Failed to load pipeline snapshot')
      }

      const payload = response.data.data
      snapshot.value = payload || null
    } catch (err: any) {
      error.value = err.response?.data?.message || err.message || String(err)
      snapshot.value = null
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    if (options.autoRefresh === false) return
    refresh()
  })

  return {
    snapshot,
    loading,
    error,
    refresh
  }
}