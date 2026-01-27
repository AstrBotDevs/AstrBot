import axios from 'axios'
import { computed, onMounted, ref } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { ApiResponse, CommandConflictGroup, ConflictStats } from '@/components/extension/mod-manager/types'

type ConflictsResponse = ApiResponse<CommandConflictGroup[]>

export function useCommandConflicts(): {
  conflicts: Ref<CommandConflictGroup[]>
  conflictStats: ComputedRef<ConflictStats>
  loading: Ref<boolean>
  error: Ref<string | null>
  refresh: () => Promise<void>
} {
  const conflicts = ref<CommandConflictGroup[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const conflictStats = computed<ConflictStats>(() => {
    const byPlugin = new Map<string, { count: number; keys: Set<string> }>()
    let total = 0

    for (const group of conflicts.value || []) {
      const conflictKey = group?.conflict_key || ''
      const handlers = group?.handlers || []
      for (const handler of handlers) {
        const pluginName = handler?.plugin || ''
        if (!pluginName) continue

        total += 1

        let entry = byPlugin.get(pluginName)
        if (!entry) {
          entry = { count: 0, keys: new Set<string>() }
          byPlugin.set(pluginName, entry)
        }

        entry.count += 1
        if (conflictKey) {
          entry.keys.add(conflictKey)
        }
      }
    }

    return { byPlugin, total }
  })

  async function refresh() {
    loading.value = true
    error.value = null

    try {
      const response = await axios.get<ConflictsResponse>('/api/commands/conflicts')
      if (response.data?.status !== 'ok') {
        throw new Error(response.data?.message || 'Failed to load command conflicts')
      }

      const payload = response.data.data
      conflicts.value = Array.isArray(payload) ? payload : []
    } catch (err: any) {
      error.value = err.response?.data?.message || err.message || String(err)
      conflicts.value = []
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    refresh()
  })

  return {
    conflicts,
    conflictStats,
    loading,
    error,
    refresh
  }
}