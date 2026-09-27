import { shallowRef } from 'vue'
import { parseSponsorCatalog, SPONSOR_CACHE_TTL, SPONSOR_CATALOG_URL } from './sponsorCatalogSchema.mjs'

export interface SponsorPreset {
  id: string
  title: string
  logo: string
  subtitle: string
  order: number
  api_base: string
  website_url?: string
  help_url?: string
  template: string
  i18n?: Record<string, { title?: string; subtitle?: string }>
}

interface Catalog {
  version: number
  updated_at: string
  sponsors: SponsorPreset[]
}

export const sponsorCatalog = shallowRef<Catalog | null>(null)
const cacheKey = 'astrbot:sponsor-catalog:v2'
let loadedAt = 0
let inFlight: Promise<void> | null = null

/**
 * Load public sponsor presets with a six-hour cache and offline fallback.
 *
 * Returns:
 *   A promise that resolves after using the cache or attempting a refresh.
 */
export function loadSponsorCatalog(): Promise<void> {
  if (inFlight) return inFlight
  if (loadedAt > 0 && Date.now() >= loadedAt && Date.now() - loadedAt < SPONSOR_CACHE_TTL) return Promise.resolve()
  inFlight = (async () => {
    const now = Date.now()
    try {
      const cached = JSON.parse(localStorage.getItem(cacheKey) || 'null')
      if (cached && Number.isFinite(cached.fetchedAt) && cached.fetchedAt > 0 && cached.fetchedAt <= now) {
        sponsorCatalog.value = parseSponsorCatalog(cached.catalog) as unknown as Catalog
        if (now - cached.fetchedAt < SPONSOR_CACHE_TTL) {
          loadedAt = cached.fetchedAt
          return
        }
      }
    } catch {
      // Unavailable storage or corrupt cache must not prevent provider setup.
    }
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)
    try {
      const response = await fetch(SPONSOR_CATALOG_URL, {
        signal: controller.signal,
        credentials: 'omit',
        headers: { Accept: 'application/json' }
      })
      if (!response.ok) throw new Error(`Sponsor catalog returned ${response.status}`)
      const catalog = parseSponsorCatalog(await response.json()) as unknown as Catalog
      sponsorCatalog.value = catalog
      loadedAt = Date.now()
      try {
        localStorage.setItem(cacheKey, JSON.stringify({ fetchedAt: loadedAt, catalog }))
      } catch {
        // The in-memory catalog remains usable when storage is full or disabled.
      }
    } catch {
      // Keep the last valid catalog, or use built-in presets on the first visit.
    } finally {
      clearTimeout(timeout)
    }
  })().finally(() => { inFlight = null })
  return inFlight
}
