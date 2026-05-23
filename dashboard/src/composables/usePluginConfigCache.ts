import axios from 'axios'
import type { ApiResponse, PluginConfigCacheApi, PluginConfigCacheEntry } from '@/components/extension/mod-manager/types'

const DEFAULT_TTL_MS = 10 * 60 * 1000

function deepClone<T>(value: T): T {
  if (typeof structuredClone === 'function') {
    return structuredClone(value)
  }
  return JSON.parse(JSON.stringify(value)) as T
}

function now() {
  return Date.now()
}

type PluginConfigGetPayload = {
  metadata: Record<string, any>
  config: Record<string, any>
}

type PluginConfigGetResponse = ApiResponse<PluginConfigGetPayload>

type PluginConfigUpdateResponse = ApiResponse<unknown>

const cache = new Map<string, PluginConfigCacheEntry>()

async function fetchPluginConfig(pluginName: string): Promise<PluginConfigGetPayload> {
  const response = await axios.get<PluginConfigGetResponse>('/api/config/get', {
    params: { plugin_name: pluginName }
  })

  if (response.data?.status !== 'ok') {
    const message = response.data?.message || 'Failed to fetch plugin config'
    throw new Error(message)
  }

  const payload = response.data.data
  return {
    metadata: deepClone(payload?.metadata || {}),
    config: deepClone(payload?.config || {})
  }
}

async function updatePluginConfig(pluginName: string, config: Record<string, any>): Promise<void> {
  const response = await axios.post<PluginConfigUpdateResponse>(
    '/api/config/plugin/update',
    config,
    { params: { plugin_name: pluginName } }
  )

  if (response.data?.status !== 'ok') {
    const message = response.data?.message || `Failed to save plugin config: ${pluginName}`
    throw new Error(message)
  }
}

function ensureEntry(pluginName: string): PluginConfigCacheEntry {
  const existing = cache.get(pluginName)
  if (existing) return existing

  const entry: PluginConfigCacheEntry = {
    metadata: {},
    config: {},
    fetchedAt: 0
  }
  cache.set(pluginName, entry)
  return entry
}

function isStaleInternal(entry: PluginConfigCacheEntry, ttlMs: number) {
  if (!entry.fetchedAt) return true
  return now() - entry.fetchedAt > ttlMs
}

function startRefresh(pluginName: string, entry: PluginConfigCacheEntry) {
  if (entry.inFlight) return entry.inFlight

  const inFlight = (async () => {
    const payload = await fetchPluginConfig(pluginName)
    entry.metadata = payload.metadata
    entry.config = payload.config
    entry.fetchedAt = now()
  })()

  const cleanup = () => {
    if (entry.inFlight === wrapped) {
      entry.inFlight = undefined
    }
  }

  const wrapped = inFlight.then(
    () => {
      cleanup()
    },
    (err) => {
      cleanup()
      throw err
    }
  )

  entry.inFlight = wrapped
  return wrapped
}

export function usePluginConfigCache(options?: { ttlMs?: number }): PluginConfigCacheApi & {
  save: (pluginName: string, config: Record<string, any>) => Promise<void>
} {
  const ttlMs = options?.ttlMs ?? DEFAULT_TTL_MS

  function get(pluginName: string) {
    return cache.get(pluginName)
  }

  function invalidate(pluginName: string) {
    cache.delete(pluginName)
  }

  function isStale(pluginName: string) {
    const entry = cache.get(pluginName)
    if (!entry) return true
    return isStaleInternal(entry, ttlMs)
  }

  async function getOrFetch(pluginName: string): Promise<PluginConfigCacheEntry> {
    const entry = ensureEntry(pluginName)

    const stale = isStaleInternal(entry, ttlMs)
    const hasValue = Boolean(entry.fetchedAt)

    if (!stale && hasValue) {
      return entry
    }

    if (entry.inFlight) {
      await entry.inFlight
      return entry
    }

    if (hasValue && stale) {
      // 过期：立即返回旧值，并后台刷新
      startRefresh(pluginName, entry).catch(() => {})
      return entry
    }

    // 首次加载：需要阻塞等待结果
    await startRefresh(pluginName, entry)
    return entry
  }

  async function prefetch(pluginName: string): Promise<void> {
    try {
      await getOrFetch(pluginName)
    } catch {
      // 预加载不阻塞 UI，不向外抛错
    }
  }

  async function save(pluginName: string, config: Record<string, any>): Promise<void> {
    await updatePluginConfig(pluginName, config)
    const entry = ensureEntry(pluginName)
    entry.config = deepClone(config)
    entry.fetchedAt = now()
    // metadata 不变；如需同步元数据，调用 invalidate + getOrFetch
  }

  async function updateConfig(pluginName: string, config: Record<string, any>): Promise<void> {
    await save(pluginName, config)
  }

  return {
    get,
    prefetch,
    getOrFetch,
    updateConfig,
    invalidate,
    isStale,
    save
  }
}